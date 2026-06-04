# -*- coding: utf-8 -*-
"""
定时任务管理 API

提供任务列表、执行历史、统计信息查询、配置更新、启用/禁用等功能
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from api.v1.schemas.common import ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/tasks",
    response_model=List[Dict[str, Any]],
    responses={
        200: {"description": "任务列表查询成功"},
        500: {"description": "服务器内部错误", "model": ErrorResponse},
    },
    summary="获取定时任务列表",
    description="返回所有已注册的定时任务定义及其状态",
)
def list_scheduler_tasks() -> List[Dict[str, Any]]:
    """获取所有定时任务列表（合并定义与运行时统计）"""
    try:
        from src.task_history import task_history
        from src.services.task_definition_service import list_tasks, ensure_seed_tasks

        ensure_seed_tasks()
        definitions = list_tasks()
        result = []

        for task_def in definitions:
            task_key = task_def["task_key"]
            stats = task_history.get_stats(task_key, days=7)
            history = task_history.get_history(task_key, limit=5)

            # 计算成功率
            success_rate = None
            total_runs = stats["total_runs"]
            if total_runs > 0:
                success_count = stats.get("success_count", 0)
                success_rate = f"{success_count}/{total_runs} ({success_count / total_runs * 100:.0f}%)"
            elif history:
                success_count = sum(1 for h in history if h.get("status") == "success")
                success_rate = f"{success_count}/{len(history)} ({success_count / len(history) * 100:.0f}%)"

            # 下次运行时间
            next_run = "-"
            if task_def["enabled"]:
                if task_def["schedule_type"] == "daily":
                    t = task_def.get("schedule_time") or getattr(_get_config(), 'schedule_time', '18:00')
                    next_run = f"每日 {t}"
                elif task_def["schedule_type"] == "interval":
                    secs = task_def.get("interval_seconds") or 300
                    next_run = f"每 {secs} 秒"

            result.append({
                "id": task_def["id"],
                "task_key": task_key,
                "name": task_def["name"],
                "description": task_def["description"] or "-",
                "schedule_type": task_def["schedule_type"],
                "schedule_time": task_def.get("schedule_time"),
                "interval_seconds": task_def.get("interval_seconds"),
                "enabled": task_def["enabled"],
                "success_rate": success_rate,
                "total_runs": stats["total_runs"],
                "last_run": history[0]["executed_at"] if history else None,
                "last_status": history[0]["status"] if history else None,
                "next_run": next_run,
            })

        return result
    except Exception as e:
        logger.exception("获取任务列表失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


def _get_config():
    """延迟获取配置"""
    from src.config import get_config
    return get_config()


@router.get(
    "/tasks/{task_name}/history",
    response_model=List[Dict[str, Any]],
    responses={
        200: {"description": "历史记录查询成功"},
        404: {"description": "任务不存在", "model": ErrorResponse},
        500: {"description": "服务器内部错误", "model": ErrorResponse},
    },
    summary="获取任务执行历史",
    description="返回指定任务的执行历史记录",
)
def get_task_history(task_name: str, limit: int = 50) -> List[Dict[str, Any]]:
    """获取任务执行历史"""
    try:
        from src.task_history import task_history
        from src.services.task_definition_service import get_task

        if not get_task(task_name):
            raise HTTPException(status_code=404, detail=f"任务 '{task_name}' 不存在")

        history = task_history.get_history(task_name, limit=limit)
        return history
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取任务历史失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/tasks/{task_name}/stats",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "统计信息查询成功"},
        404: {"description": "任务不存在", "model": ErrorResponse},
        500: {"description": "服务器内部错误", "model": ErrorResponse},
    },
    summary="获取任务统计信息",
    description="返回指定任务的执行统计信息（成功率、耗时等）",
)
def get_task_stats(task_name: str, days: int = 7) -> Dict[str, Any]:
    """获取任务执行统计信息"""
    try:
        from src.task_history import task_history
        from src.services.task_definition_service import get_task

        if not get_task(task_name):
            raise HTTPException(status_code=404, detail=f"任务 '{task_name}' 不存在")

        stats = task_history.get_stats(task_name, days=days)
        if stats["total_runs"] == 0:
            raise HTTPException(status_code=404, detail=f"任务 '{task_name}' 不存在或无执行记录")

        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取任务统计失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/history",
    response_model=List[Dict[str, Any]],
    responses={
        200: {"description": "全局历史查询成功"},
        500: {"description": "服务器内部错误", "model": ErrorResponse},
    },
    summary="获取所有任务执行历史",
    description="返回所有任务的执行记录（按时间倒序）",
)
def get_all_task_history(limit: int = 100) -> List[Dict[str, Any]]:
    """获取所有任务执行历史"""
    try:
        from src.task_history import task_history
        from src.services.task_definition_service import ensure_seed_tasks, list_tasks

        ensure_seed_tasks()
        active_task_keys = {task["task_key"] for task in list_tasks()}
        all_history = []
        for task_name in task_history.get_all_tasks():
            if task_name not in active_task_keys:
                continue
            history = task_history.get_history(task_name, limit=20)
            all_history.extend(history)

        all_history.sort(key=lambda x: x["executed_at"], reverse=True)
        return all_history[:limit]
    except Exception as e:
        logger.exception("获取全局历史失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/tasks/{task_name}/trigger",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "任务触发成功"},
        404: {"description": "任务不存在", "model": ErrorResponse},
        500: {"description": "任务执行失败", "model": ErrorResponse},
    },
    summary="手动触发定时任务",
    description="手动触发指定任务的执行",
)
def trigger_scheduler_task(task_name: str) -> Dict[str, Any]:
    """手动触发定时任务"""
    try:
        from src.task_history import task_history
        from src.services.task_definition_service import get_task

        if not get_task(task_name):
            raise HTTPException(status_code=404, detail=f"任务 '{task_name}' 不存在")

        def trigger_wrapper():
            start_time = time.time()
            try:
                if task_name == "market_cache_refresh":
                    from src.services.portfolio_service import PortfolioService
                    from src.storage import get_db, PortfolioPosition, StockDaily
                    from src.services.portfolio_service import EPS
                    import akshare as ak
                    import yfinance as yf

                    svc = PortfolioService()
                    result = svc.refresh_all_prices(refresh_fx=True)

                    # R2/R3 holdings
                    try:
                        db = get_db()
                        with db.get_session() as s:
                            r2r3_positions = s.query(PortfolioPosition).filter(
                                PortfolioPosition.quantity > EPS,
                                PortfolioPosition.asset_risk_class.in_({"R2", "R3"}),
                            ).all()
                        for position in r2r3_positions:
                            symbol = svc._normalize_symbol_for_position(position.symbol)
                            quote = svc._resolve_latest_price_with_name(symbol, position.asset_category)
                            if quote is not None and quote.price > 0:
                                with db.get_session() as s2:
                                    s2.query(PortfolioPosition).filter_by(id=position.id).update({
                                        PortfolioPosition.last_price: quote.price,
                                        PortfolioPosition.price_change_pct: quote.change_pct,
                                        PortfolioPosition.name: quote.name or position.name,
                                        PortfolioPosition.updated_at: datetime.now(),
                                    })
                                    s2.commit()
                    except Exception as exc:
                        logger.warning("R2/R3 price refresh failed: %s", exc)

                    # cn_vix / us_vix / bond
                    try:
                        today = date.today()
                        try:
                            df = ak.index_option_300etf_qvix()
                            if not df.empty:
                                with get_db().get_session() as s:
                                    s.query(StockDaily).filter_by(code="cn_vix", date=today).delete()
                                    s.add(StockDaily(code="cn_vix", date=today, close=float(df.iloc[-1]["qvix"]), data_source="akshare", updated_at=datetime.now()))
                                    s.commit()
                        except Exception as exc:
                            logger.warning("cn_vix failed: %s", exc)
                        try:
                            vix = yf.Ticker("^VIX")
                            hist = vix.history(period="2d")
                            if not hist.empty:
                                with get_db().get_session() as s:
                                    s.query(StockDaily).filter_by(code="us_vix", date=today).delete()
                                    s.add(StockDaily(code="us_vix", date=today, close=float(hist["Close"].iloc[-1]), data_source="yfinance", updated_at=datetime.now()))
                                    s.commit()
                        except Exception as exc:
                            logger.warning("us_vix failed: %s", exc)
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
                            logger.warning("Bond indices failed: %s", exc)
                    except Exception as exc:
                        logger.warning("Market risk indices refresh failed: %s", exc)

                    from src.services.market_cache_service import (
                        MARKET_CACHE_BUILDERS,
                        refresh_market_cache,
                        refresh_trend_realtime_quotes,
                    )
                    from src.services.sector_etf_service import refresh_sector_etf_daily_data

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
                elif task_name == "seasonality_cache_refresh":
                    logger.warning("全年择时缓存刷新已合并到价格刷新任务中，不再单独触发")
                    return {"status": "skipped", "message": "全年择时缓存刷新已合并到价格刷新任务"}
                elif task_name == "agent_event_monitor":
                    logger.warning("Agent 事件监控为后台常驻任务，不支持手动触发")
                    return {"status": "skipped", "message": "Agent 事件监控为后台常驻任务"}
                else:
                    raise ValueError(f"未知任务：{task_name}")

                duration_ms = int((time.time() - start_time) * 1000)
                task_history.record(task_name, "success", duration_ms=duration_ms)
                return {"status": "success", "duration_ms": duration_ms}
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                task_history.record(task_name, "failed", duration_ms=duration_ms, error=str(e))
                raise

        # Long-running tasks: offload to background thread so the HTTP
        # client doesn't timeout. Short/instant tasks run inline.
        background_tasks = {"market_cache_refresh"}
        if task_name in background_tasks:

            def run_in_thread():
                try:
                    result_data = trigger_wrapper()
                    logger.info("Background task '%s' done: %s", task_name, result_data.get("status"))
                except Exception as e:
                    logger.error("Background task '%s' failed: %s", task_name, e)

            thread = threading.Thread(target=run_in_thread)
            thread.start()
            return {"status": "accepted", "message": f"任务 '{task_name}' 已提交后台执行"}

        result = {"status": "running", "message": "任务执行中"}

        def run_in_thread():
            try:
                result_data = trigger_wrapper()
                result.update(result_data)
            except Exception as e:
                result.update({"status": "failed", "error": str(e)})

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join(timeout=300)

        if result.get("status") == "running":
            result = {"status": "timeout", "message": "任务执行超时，但可能仍在后台运行"}

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("手动触发任务失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/tasks/{task_name}/schedule",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "定时配置更新成功"},
        400: {"description": "无效的定时配置", "model": ErrorResponse},
        404: {"description": "任务不存在", "model": ErrorResponse},
        500: {"description": "服务器内部错误", "model": ErrorResponse},
    },
    summary="更新定时任务配置",
    description="更新指定任务的定时配置（频率、时间等）",
)
def update_scheduler_task_schedule(
    task_name: str,
    schedule_config: Dict[str, Any]
) -> Dict[str, Any]:
    """更新定时任务配置"""
    try:
        from src.services.task_definition_service import get_task, update_task

        task_def = get_task(task_name)
        if not task_def:
            raise HTTPException(status_code=404, detail=f"任务 '{task_name}' 不存在")

        updates = {}
        if "schedule_time" in schedule_config:
            schedule_time = str(schedule_config["schedule_time"]).strip()
            if schedule_time and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule_time):
                raise HTTPException(status_code=400, detail=f"无效的时间格式：{schedule_time}，应为 HH:MM 格式")
            updates["schedule_time"] = schedule_time or None

        if "interval_seconds" in schedule_config:
            interval = int(schedule_config["interval_seconds"])
            if interval <= 0:
                raise HTTPException(status_code=400, detail="interval_seconds 必须大于 0")
            updates["interval_seconds"] = interval

        if "schedule_type" in schedule_config:
            st = schedule_config["schedule_type"]
            if st not in ("daily", "interval", "cron"):
                raise HTTPException(status_code=400, detail=f"无效的 schedule_type: {st}")
            updates["schedule_type"] = st

        if not updates:
            raise HTTPException(status_code=400, detail="缺少 schedule_time / interval_seconds / schedule_type 配置项")

        result = update_task(task_name, **updates)

        return {
            "success": True,
            "message": "定时配置已更新",
            **result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("更新定时配置失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/tasks/{task_name}/status",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "状态更新成功"},
        404: {"description": "任务不存在", "model": ErrorResponse},
        500: {"description": "服务器内部错误", "model": ErrorResponse},
    },
    summary="启用/禁用定时任务",
    description="切换指定任务的启用或禁用状态",
)
def toggle_scheduler_task_status(task_name: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """启用/禁用定时任务"""
    try:
        from src.services.task_definition_service import toggle_task

        enabled = bool(body.get("enabled", False))
        result = toggle_task(task_name, enabled)
        if not result:
            raise HTTPException(status_code=404, detail=f"任务 '{task_name}' 不存在")

        return {
            "success": True,
            "message": f"任务已{'启用' if enabled else '禁用'}",
            "enabled": enabled,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("切换任务状态失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/next-run",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "查询成功"},
        500: {"description": "服务器内部错误", "model": ErrorResponse},
    },
    summary="获取任务下次执行时间",
    description="获取所有任务的下次执行时间",
)
def get_all_next_run_times() -> Dict[str, Any]:
    """获取所有任务下次执行时间"""
    try:
        from src.services.task_definition_service import list_tasks, ensure_seed_tasks

        ensure_seed_tasks()
        tasks = list_tasks()
        config = _get_config()

        result = {}
        for task in tasks:
            key = task["task_key"]
            if task["enabled"]:
                if task["schedule_type"] == "daily":
                    t = task.get("schedule_time") or getattr(config, 'schedule_time', '18:00')
                    result[key] = {"next_run": f"每日 {t}", "schedule_time": t}
                elif task["schedule_type"] == "interval":
                    secs = task.get("interval_seconds") or 300
                    result[key] = {"next_run": f"每 {secs} 秒", "interval": secs}
                else:
                    result[key] = {"next_run": "已启用"}
            else:
                result[key] = {"next_run": "已禁用"}

        return result
    except Exception as e:
        logger.exception("获取下次执行时间失败：%s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/tasks/init-market-data",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "初始化成功"},
        500: {"description": "服务器内部错误", "model": ErrorResponse},
    },
    summary="初始化大盘与情绪历史数据",
    description="一次性全量拉取过去 5 年的大盘指数与情绪指标数据并入库",
)
def init_market_data() -> Dict[str, Any]:
    """手动触发大盘历史数据全量初始化"""
    try:
        from src.services.market_sync_service import sync_market_data
        
        def do_init():
            logger.info("[Init] 开始全量初始化大盘与情绪数据 (5年)...")
            sync_market_data(days=1825)
            logger.info("[Init] 全量初始化完成。")
            
        # 在后台线程执行以避免长时间阻塞 API 响应
        t = threading.Thread(target=do_init)
        t.start()
        
        return {"status": "running", "message": "初始化任务已在后台启动，预计需要数分钟，请查看日志确认进度"}
    except Exception as e:
        logger.exception("初始化大盘数据失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
