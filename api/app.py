# -*- coding: utf-8 -*-
"""
===================================
FastAPI 应用工厂模块
===================================

职责：
1. 创建和配置 FastAPI 应用实例
2. 配置 CORS 中间件
3. 注册路由和异常处理器
4. 托管前端静态文件（生产模式）

使用方式：
    from api.app import create_app
    app = create_app()
"""

import logging
import mimetypes
import os
import re
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

PORTFOLIO_PRICE_REFRESH_TASK_KEY = "market_cache_refresh"
PORTFOLIO_PRICE_REFRESH_TIMES = ((8, 30), (20, 30))

# Match src="/assets/foo.js" / href="/assets/foo.css" produced by the
# vite build. Used by the startup self-check to surface packaging
# mismatches early (see GitHub #1064 / #1065 / #1050).
_INDEX_ASSET_REF_PATTERN = re.compile(
    r"""(?:src|href)\s*=\s*["'](/assets/[^"']+)["']""",
    re.IGNORECASE,
)
_SAFE_MISSING_ASSET_MEDIA_TYPES = frozenset({"text/css", "text/javascript"})
_FRONTEND_INDEX_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _frontend_index_response(static_dir: Path) -> FileResponse:
    return FileResponse(
        static_dir / "index.html",
        headers=_FRONTEND_INDEX_NO_CACHE_HEADERS,
    )


def _check_frontend_assets_consistency(static_dir: Path) -> List[str]:
    """
    Verify that ``index.html`` only references assets that actually exist
    under ``static_dir``. Returns the list of missing references; an empty
    list means the bundle is consistent.

    Logs an actionable error when a mismatch is detected so the root cause
    is visible in ``logs/desktop.log`` instead of surfacing as a silent
    blank page.
    """
    index_html = static_dir / "index.html"
    if not index_html.is_file():
        return []
    try:
        html = index_html.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Failed to read %s for asset check: %s", index_html, exc)
        return []

    missing: List[str] = []
    for match in _INDEX_ASSET_REF_PATTERN.finditer(html):
        ref = match.group(1)
        candidate = static_dir / ref.lstrip("/")
        if not candidate.is_file() and ref not in missing:
            missing.append(ref)

    if missing:
        logger.error(
            "Frontend bundle is inconsistent: index.html references %d asset(s) "
            "that are not present on disk under %s. This will surface as a "
            "blank page in the desktop app (see GitHub #1064 / #1065). "
            "Missing: %s. Re-run the frontend build and make sure the packaging "
            "step copies the freshly generated static/ directory.",
            len(missing),
            static_dir,
            ", ".join(missing),
        )
    return missing


async def _startup_catch_up_check():
    """Check at startup whether today's full sync has run. If not, trigger it asynchronously."""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from src.storage import MarketCache, get_db
    from src.task_history import task_history
    from src.services.scheduler_jobs import run_daily_market_cache_refresh

    beijing_tz = timezone(timedelta(hours=8))
    await asyncio.sleep(45)

    try:
        now = datetime.now(beijing_tz)
        today = now.date()

        is_fresh = False
        with get_db().get_session() as s:
            trend_row = s.query(MarketCache).filter_by(cache_key="trend").one_or_none()
            if trend_row and trend_row.created_at.date() == today:
                is_fresh = True

        if not is_fresh:
            for item in task_history.get_history("market_cache_refresh", limit=5):
                try:
                    executed_at = datetime.fromisoformat(item["executed_at"])
                    if executed_at.tzinfo is None:
                        executed_at = executed_at.replace(tzinfo=beijing_tz)
                    else:
                        executed_at = executed_at.astimezone(beijing_tz)
                    if executed_at.date() == today and item.get("status") == "success":
                        is_fresh = True
                        break
                except Exception:
                    continue

        if not is_fresh:
            logger.info("Startup catch-up: No fresh data for %s. Triggering full daily sync.", today)
            with ThreadPoolExecutor(max_workers=1) as executor:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(executor, run_daily_market_cache_refresh)
            task_history.record("market_cache_refresh", "success", duration_ms=0)
            logger.info("Startup catch-up: Full sync finished.")
        else:
            logger.info("Startup catch-up: Data for %s is up-to-date. Skipping.", today)
    except Exception as exc:
        logger.warning("Startup catch-up check failed: %s", exc)


def _resolve_asset_path(assets_dir: Path, asset_path: str) -> Optional[Path]:
    """Resolve a requested asset path while keeping it confined to assets_dir."""
    decoded_path = unquote(asset_path)
    if not decoded_path or decoded_path.startswith(("/", "\\")):
        return None
    if "\x00" in decoded_path:
        return None
    if "\\" in decoded_path:
        return None
    if ":" in decoded_path.split("/", 1)[0]:
        return None

    assets_root = assets_dir.resolve()
    candidate = (assets_root / decoded_path).resolve()
    if not candidate.is_relative_to(assets_root):
        return None
    return candidate


def _missing_asset_media_type(asset_path: str) -> str:
    """Return a safe media type for a missing asset response."""
    content_type, _ = mimetypes.guess_type(asset_path)
    if content_type in _SAFE_MISSING_ASSET_MEDIA_TYPES:
        return content_type
    return "text/plain"

from api.v1 import api_v1_router
from api.middlewares.auth import add_auth_middleware
from api.middlewares.error_handler import add_error_handlers
from api.v1.schemas.common import HealthResponse
from src.services.system_config_service import SystemConfigService


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Initialize and release shared services for the app lifecycle."""
    app.state.system_config_service = SystemConfigService()

    # Seed scheduled task definitions into DB
    try:
        from src.services.task_definition_service import ensure_seed_tasks
        ensure_seed_tasks()
    except Exception:
        logger.exception("Failed to seed scheduled task definitions")

    try:
        from src.storage import get_db
        removed = get_db().cleanup_agent_data_cache()
        if removed:
            logger.info("Cleaned up expired agent data cache rows: %s", removed)
    except Exception:
        logger.exception("Failed to clean up expired agent data cache")

    # Start background price refresh task (daily at 08:30 and 20:30 Beijing time)
    refresh_task = asyncio.create_task(_daily_portfolio_price_refresh())
    app.state._price_refresh_task = refresh_task

    market_refresh_task = asyncio.create_task(_daily_market_cache_refresh_loop())
    app.state._market_refresh_task = market_refresh_task

    startup_catch_up_task = asyncio.create_task(_startup_catch_up_check())
    app.state._startup_catch_up_task = startup_catch_up_task

    try:
        yield
    finally:
        refresh_task.cancel()
        market_refresh_task.cancel()
        if hasattr(app.state, "_startup_catch_up_task"):
            app.state._startup_catch_up_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
        try:
            await market_refresh_task
        except asyncio.CancelledError:
            pass
        if hasattr(app.state, "system_config_service"):
            delattr(app.state, "system_config_service")
        if hasattr(app.state, "_price_refresh_task"):
            delattr(app.state, "_price_refresh_task")
        if hasattr(app.state, "_market_refresh_task"):
            delattr(app.state, "_market_refresh_task")


async def _daily_portfolio_price_refresh():
    """Refresh portfolio positions prices at 08:30 and 20:30 Beijing time.

    Past due slots are skipped on startup; only upcoming scheduled slots will
    be triggered. Missed slots should be re-run manually via the scheduler UI.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    # Use Beijing time (UTC+8) for all time-based checks
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    today = now.date()
    
    last_refresh_slots = set()

    # Startup check: Mark past slots as handled to avoid immediate execution.
    # Intentionally skip catch-up; rely on scheduled runs or manual triggers.
    try:
        for slot in PORTFOLIO_PRICE_REFRESH_TIMES:
            if _is_refresh_slot_due(now, slot):
                last_refresh_slots.add((today, slot))
                logger.info("Startup: Slot %02d:%02d is past; marked as handled", slot[0], slot[1])
    except Exception as exc:
        logger.error("Startup check failed: %s", exc, exc_info=True)
    
    # Wait before entering the regular check loop so server can start normally
    await asyncio.sleep(30)

    with ThreadPoolExecutor(max_workers=1) as executor:
        while True:
            try:
                # Use Beijing time (UTC+8) for time-based checks
                now = datetime.now(beijing_tz)
                today = now.date()
                for slot in PORTFOLIO_PRICE_REFRESH_TIMES:
                    slot_key = (today, slot)
                    if _is_refresh_slot_due(now, slot) and slot_key not in last_refresh_slots:
                        logger.info("Daily portfolio price refresh started for %02d:%02d", slot[0], slot[1])
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(executor, _run_price_refresh_with_history)
                        last_refresh_slots.add(slot_key)
                        logger.info("Daily portfolio price refresh completed for %02d:%02d", slot[0], slot[1])
                        break

                if len(last_refresh_slots) > len(PORTFOLIO_PRICE_REFRESH_TIMES) * 2:
                    last_refresh_slots = {
                        item for item in last_refresh_slots
                        if item[0] >= today - timedelta(days=1)
                    }
            except Exception as exc:
                logger.error("Portfolio price refresh error: %s", exc)

            await asyncio.sleep(30)  # Check every 30 seconds


def _is_refresh_slot_due(now: datetime, slot: tuple[int, int]) -> bool:
    hour, minute = slot
    return now.hour > hour or (now.hour == hour and now.minute >= minute)


def _has_price_refresh_history_for_slot(day, slot: tuple[int, int], beijing_tz) -> bool:
    from src.task_history import task_history

    slot_start = datetime.combine(day, datetime.min.time()).replace(
        hour=slot[0], minute=slot[1], tzinfo=beijing_tz,
    )
    slot_end = slot_start + timedelta(hours=1)
    for item in task_history.get_history(PORTFOLIO_PRICE_REFRESH_TASK_KEY, limit=20):
        try:
            executed_at = datetime.fromisoformat(item["executed_at"])
        except (TypeError, ValueError):
            continue
        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=beijing_tz)
        else:
            executed_at = executed_at.astimezone(beijing_tz)
        if slot_start <= executed_at < slot_end:
            return True
    return False


def _run_price_refresh_with_history():
    """Run price refresh and record automatic scheduler history."""
    import time
    from src.task_history import task_history

    start = time.time()
    try:
        _run_price_refresh()
        task_history.record(
            PORTFOLIO_PRICE_REFRESH_TASK_KEY,
            "success",
            duration_ms=int((time.time() - start) * 1000),
        )
    except Exception as exc:
        task_history.record(
            PORTFOLIO_PRICE_REFRESH_TASK_KEY,
            "failed",
            duration_ms=int((time.time() - start) * 1000),
            error=str(exc),
        )
        raise


def _run_price_refresh():
    """Synchronous wrapper for price refresh (runs in thread pool)."""
    from src.services.portfolio_service import PortfolioService

    svc = PortfolioService()
    result = svc.refresh_all_prices(refresh_fx=True)
    pos = result.get("positions", {})
    idx = result.get("indices", {})
    fx = result.get("fx", {"refreshed": 0, "failed": 0})
    fund_nav = result.get("fund_nav") or {}
    logger.info(
        "Price refresh: pos=%d/%d, indices=%d/%d, fx=%d/%d, fund_nav=%s",
        pos.get("refreshed", 0), pos.get("failed", 0),
        idx.get("refreshed", 0), idx.get("failed", 0),
        fx.get("refreshed", 0), fx.get("failed", 0),
        fund_nav.get("fund_nav", "skipped"),
    )

    try:
        # cn_vix / us_vix / bond_cn_10y / bond_us_10y (for risk & radar caches)
        from src.storage import StockDaily, get_db

        import akshare as ak
        import yfinance as yf

        today = date.today()

        try:
            df = ak.index_option_300etf_qvix()
            if not df.empty:
                with get_db().get_session() as s:
                    s.query(StockDaily).filter_by(code="cn_vix", date=today).delete()
                    s.add(StockDaily(code="cn_vix", date=today, close=float(df.iloc[-1]["qvix"]), data_source="akshare", updated_at=datetime.now()))
                    s.commit()
        except Exception as exc:
            logger.warning("Failed to refresh cn_vix: %s", exc)

        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="2d")
            if not hist.empty:
                with get_db().get_session() as s:
                    s.query(StockDaily).filter_by(code="us_vix", date=today).delete()
                    s.add(StockDaily(code="us_vix", date=today, close=float(hist["Close"].iloc[-1]), data_source="yfinance", updated_at=datetime.now()))
                    s.commit()
        except Exception as exc:
            logger.warning("Failed to refresh us_vix: %s", exc)

        try:
            df = ak.bond_zh_us_rate()
            if not df.empty:
                for i in range(len(df) - 1, max(0, len(df) - 10), -1):
                    row = df.iloc[i]
                    us_val = row.get("美国国债收益率10年")
                    cn_val = row.get("中国国债收益率10年")
                    if str(us_val) != "nan" and us_val is not None and str(cn_val) != "nan" and cn_val is not None:
                        with get_db().get_session() as s:
                            s.query(StockDaily).filter_by(code="bond_us_10y", date=today).delete()
                            s.query(StockDaily).filter_by(code="bond_cn_10y", date=today).delete()
                            s.add(StockDaily(code="bond_cn_10y", date=today, close=float(cn_val), data_source="akshare", updated_at=datetime.now()))
                            s.add(StockDaily(code="bond_us_10y", date=today, close=float(us_val), data_source="akshare", updated_at=datetime.now()))
                            s.commit()
                        break
        except Exception as exc:
            logger.warning("Failed to refresh bond indices: %s", exc)
    except Exception as exc:
        logger.warning("Risk indices refresh failed: %s", exc)

    # Rebuild all 6 market_cache keys
    try:
        from src.services.sector_etf_service import refresh_sector_etf_daily_data
        from src.services.market_cache_service import (
            MARKET_CACHE_BUILDERS,
            refresh_market_cache,
            refresh_trend_realtime_quotes,
        )

        sector_result = refresh_sector_etf_daily_data()
        logger.info(
            "Sector ETF refresh: refreshed=%d, failed=%d",
            sector_result.get("refreshed", 0),
            sector_result.get("failed", 0),
        )

        from src.services.watchlist_signal_service import WatchlistSignalService

        signal_result = WatchlistSignalService().refresh_enabled_stocks()
        logger.info(
            "Watchlist signal refresh: success=%d, failed=%d",
            signal_result.get("success", 0),
            signal_result.get("failed", 0),
        )

        fund_result = WatchlistSignalService().refresh_enabled_funds()
        logger.info(
            "Watchlist fund signal refresh: success=%d, failed=%d",
            fund_result.get("success", 0),
            fund_result.get("failed", 0),
        )

        for cache_key in MARKET_CACHE_BUILDERS:
            if cache_key == "trend":
                refresh_trend_realtime_quotes()
            else:
                refresh_market_cache(cache_key)
            logger.info("Market cache key rebuilt: %s", cache_key)
    except Exception as exc:
        logger.warning("Market cache rebuild failed: %s", exc)


async def _daily_market_cache_refresh_loop():
    """Refresh market dashboard cache periodically (every 5 minutes) to keep
    real-time fields up-to-date. Old cached data is always served until replaced."""
    from concurrent.futures import ThreadPoolExecutor

    refresh_interval_seconds = 300  # 5 minutes

    with ThreadPoolExecutor(max_workers=1) as executor:
        await asyncio.sleep(30)  # wait for server to start normally
        while True:
            # Use Beijing time (UTC+8) for trading hour checks
            now = datetime.now(timezone.utc).replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
            # Only refresh during A-share trading hours (Monday-Friday, 9:00-15:00 Beijing time)
            if now.weekday() < 5 and 9 <= now.hour < 15:
                try:
                    logger.info("Market cache refresh started")
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(executor, _run_market_cache_refresh)
                    logger.info("Market cache refresh completed")
                except Exception as exc:
                    logger.error("Market cache refresh error: %s", exc, exc_info=True)

            await asyncio.sleep(refresh_interval_seconds)


def _run_market_cache_refresh():
    """Synchronous wrapper for market cache refresh."""
    from src.services.market_cache_service import refresh_all_market_caches

    result = refresh_all_market_caches()
    items = result.get("items", {})
    ok_count = sum(1 for item in items.values() if item.get("status") == "success")
    logger.info("Market cache refresh: success=%d/%d", ok_count, len(items))


def create_app(static_dir: Optional[Path] = None) -> FastAPI:
    """
    创建并配置 FastAPI 应用实例
    
    Args:
        static_dir: 静态文件目录路径（可选，默认为项目根目录下的 static）
        
    Returns:
        配置完成的 FastAPI 应用实例
    """
    # 默认静态文件目录
    if static_dir is None:
        static_dir = Path(__file__).parent.parent / "static"
    
    # 创建 FastAPI 实例
    app = FastAPI(
        title="Daily Stock Analysis API",
        description=(
            "A股/港股/美股自选股智能分析系统 API\n\n"
            "## 功能模块\n"
            "- 股票分析：触发 AI 智能分析\n"
            "- 历史记录：查询历史分析报告\n"
            "- 股票数据：获取行情数据\n\n"
            "## 认证方式\n"
            "支持可选的运行时认证（通过 WebUI 设置页面启用/关闭）"
        ),
        version="1.0.0",
        lifespan=app_lifespan,
    )
    
    # ============================================================
    # CORS 配置
    # ============================================================
    
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    
    # 从环境变量添加额外的允许来源
    extra_origins = os.environ.get("CORS_ORIGINS", "")
    if extra_origins:
        allowed_origins.extend([o.strip() for o in extra_origins.split(",") if o.strip()])
    
    # 允许所有来源（开发/演示用）
    allow_all_origins = os.environ.get("CORS_ALLOW_ALL", "").lower() == "true"
    allow_credentials = not allow_all_origins
    if allow_all_origins:
        allowed_origins = ["*"]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    add_auth_middleware(app)
    
    # ============================================================
    # 注册路由
    # ============================================================
    
    app.include_router(api_v1_router)
    add_error_handlers(app)
    
    # ============================================================
    # 根路由和健康检查
    # ============================================================
    
    has_frontend = static_dir.exists() and (static_dir / "index.html").exists()
    
    if has_frontend:
        # Surface bundle inconsistencies as soon as the app starts so that
        # blank-page reports (#1064 / #1065 / #1050) can be diagnosed from
        # logs/desktop.log instead of via browser devtools.
        _check_frontend_assets_consistency(static_dir)

        @app.get("/", include_in_schema=False)
        async def root():
            """根路由 - 返回前端页面"""
            return _frontend_index_response(static_dir)
    else:
        _FRONTEND_NOT_BUILT_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DSA - Frontend Not Built</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#0a0e17;color:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,monospace}
  .card{max-width:580px;padding:2.5rem;border:1px solid #1e293b;border-radius:12px;background:#111827}
  h1{font-size:1.25rem;color:#38bdf8;margin-bottom:.75rem}
  p{font-size:.9rem;line-height:1.7;color:#94a3b8;margin-bottom:.5rem}
  code{background:#1e293b;padding:2px 8px;border-radius:4px;font-size:.85rem;color:#67e8f9}
  .hint{margin-top:1.25rem;padding:.75rem 1rem;border-left:3px solid #f59e0b;background:#1c1917;border-radius:0 6px 6px 0}
  .hint p{color:#fbbf24;margin:0}
  a{color:#38bdf8;text-decoration:none}
  a:hover{text-decoration:underline}
  .status{margin-top:1rem;font-size:.8rem;color:#475569}
</style></head><body><div class="card">
<h1>&#9888;&#65039; Frontend Not Built</h1>
<p>API is running, but the Web UI has not been built yet.</p>
<p>Build the frontend first:</p>
<p><code>cd apps/dsa-web &amp;&amp; npm install &amp;&amp; npm run build</code></p>
<p>Or start with auto-build:</p>
<p><code>python main.py --serve-only</code></p>
<div class="hint"><p>If you only need the API, visit <a href="/docs">/docs</a> for the interactive API documentation.</p></div>
<p class="status">API Version 1.0.0 &bull; <a href="/api/health">/api/health</a></p>
</div></body></html>"""

        @app.get("/", include_in_schema=False)
        async def root():
            """根路由 - 前端未构建时返回引导页面"""
            return HTMLResponse(content=_FRONTEND_NOT_BUILT_HTML)
    
    @app.get(
        "/api/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="健康检查",
        description="用于负载均衡器或监控系统检查服务状态"
    )
    async def health_check() -> HealthResponse:
        """健康检查接口"""
        return HealthResponse(
            status="ok",
            timestamp=datetime.now().isoformat()
        )
    
    # ============================================================
    # 静态文件托管（前端 SPA）
    # ============================================================
    
    if has_frontend:
        # Serve `/assets/*` explicitly so that misses return a plain-text
        # 404 with the correct Content-Type instead of the default JSON
        # error response. JSON for a JS/CSS request is what masked the
        # blank-page root cause in #1064; here we make it obvious that the
        # static file simply does not exist on disk.
        assets_dir = static_dir / "assets"

        assets_static_files = StaticFiles(directory=str(assets_dir), check_dir=False)
        assets_root = assets_dir.resolve()

        @app.api_route(
            "/assets/{asset_path:path}",
            methods=["GET", "HEAD"],
            include_in_schema=False,
        )
        async def serve_asset(request: Request, asset_path: str):
            file_path = _resolve_asset_path(assets_dir, asset_path)
            if file_path is None:
                if not Path(asset_path).suffix:
                    return _frontend_index_response(static_dir)
                return Response(
                    content="not found",
                    status_code=404,
                    media_type="text/plain",
                )
            if file_path.is_file():
                relative_path = file_path.relative_to(assets_root).as_posix()
                return await assets_static_files.get_response(relative_path, request.scope)
            if not Path(asset_path).suffix:
                return _frontend_index_response(static_dir)
            return Response(
                content="asset not found",
                status_code=404,
                media_type=_missing_asset_media_type(asset_path),
            )

        # SPA 路由回退
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(request: Request, full_path: str):
            """SPA 路由回退 - 非 API 路由返回 index.html"""
            if full_path == "api" or full_path.startswith("api/"):
                return JSONResponse(
                    status_code=404,
                    content={"error": "not_found", "message": f"API endpoint /{full_path} not found"}
                )

            # Reuse the same containment check as /assets/* so that requests
            # like `/%2e%2e/%2e%2e/etc/passwd` cannot escape static_dir via
            # the SPA fallback. Starlette's :path converter does not collapse
            # `..` segments, so static_dir / full_path can resolve outside
            # the bundle root if served unchecked.
            file_path = _resolve_asset_path(static_dir, full_path) if full_path else None
            if file_path is not None and file_path.is_file():
                if file_path == (static_dir / "index.html").resolve():
                    return _frontend_index_response(static_dir)
                # Issue #520: Explicitly resolve MIME type to avoid
                # browsers rejecting JS modules served as text/plain.
                content_type, _ = mimetypes.guess_type(str(file_path))
                return FileResponse(file_path, media_type=content_type)

            return _frontend_index_response(static_dir)
    
    return app


# 默认应用实例（供 uvicorn 直接使用）
app = create_app()
