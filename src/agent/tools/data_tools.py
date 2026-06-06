# -*- coding: utf-8 -*-
"""
Data tools — wraps DataFetcherManager methods as agent-callable tools.

Tools:
- get_realtime_quote: real-time stock quote
- get_daily_history: historical OHLCV data
- get_chip_distribution: chip distribution analysis
- get_analysis_context: historical analysis context from DB
"""

import logging
import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from src.agent.tools.registry import ToolParameter, ToolDefinition
from src.agent.runtime_context import get_agent_topic_key, is_agent_chat_mode

logger = logging.getLogger(__name__)

_fetcher_manager_singleton = None
_fetcher_manager_lock = Lock()
_DAILY_HISTORY_DEFAULT_DAYS = 60
_DAILY_HISTORY_MAX_DAYS = 365


def _get_fetcher_manager():
    """Return a module-level singleton DataFetcherManager.

    Re-creating the manager on every tool call causes Tushare re-init overhead
    (~2 s each) and prevents circuit-breaker cooldown from taking effect across
    consecutive tool calls within the same agent run.
    """
    from data_provider import DataFetcherManager
    global _fetcher_manager_singleton
    if _fetcher_manager_singleton is None:
        with _fetcher_manager_lock:
            if _fetcher_manager_singleton is None:
                _fetcher_manager_singleton = DataFetcherManager()
    return _fetcher_manager_singleton


def reset_fetcher_manager() -> None:
    """Clear the cached DataFetcherManager so runtime config reloads take effect."""
    global _fetcher_manager_singleton
    with _fetcher_manager_lock:
        _fetcher_manager_singleton = None


def _get_db():
    """Lazy import for DatabaseManager."""
    from src.storage import get_db
    return get_db()


def _normalize_history_days(days: Any) -> Tuple[int, Dict[str, Any]]:
    """Normalize LLM-provided history window and return response metadata."""
    requested_days = days
    warning = None
    try:
        if isinstance(days, bool):
            raise ValueError("bool is not a valid days value")
        effective_days = int(days)
    except (TypeError, ValueError):
        effective_days = _DAILY_HISTORY_DEFAULT_DAYS
        warning = (
            f"Invalid days value {requested_days!r}; "
            f"using default {_DAILY_HISTORY_DEFAULT_DAYS}."
        )

    if effective_days < 1:
        effective_days = 1
        warning = f"days must be >= 1; using {effective_days}."
    elif effective_days > _DAILY_HISTORY_MAX_DAYS:
        effective_days = _DAILY_HISTORY_MAX_DAYS
        warning = f"days exceeds max {_DAILY_HISTORY_MAX_DAYS}; truncated."

    metadata: Dict[str, Any] = {}
    if warning is not None:
        metadata.update(
            {
                "warning": warning,
                "requested_days": requested_days,
                "effective_days": effective_days,
            }
        )
    return effective_days, metadata


def _history_code_candidates(stock_code: str) -> Tuple[List[str], str]:
    """Return cache lookup candidates plus canonical write code."""
    from data_provider.base import canonical_stock_code, normalize_stock_code

    raw_code = str(stock_code or "").strip()
    normalized_code = canonical_stock_code(normalize_stock_code(raw_code))
    candidates: List[str] = []
    for candidate in (canonical_stock_code(raw_code), normalized_code):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates, normalized_code


def _append_history_metadata(response: dict, metadata: Dict[str, Any]) -> dict:
    if metadata:
        response.update(metadata)
    return response


def _agent_cache_key(data_type: str, symbol: str, params: Dict[str, Any]) -> str:
    payload = json.dumps(params or {}, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    topic_key = get_agent_topic_key() or "adhoc"
    return f"{topic_key}:{data_type}:{symbol}:{digest}"


def _save_agent_cache(
    *,
    data_type: str,
    symbol: str,
    payload: Any,
    params: Optional[Dict[str, Any]] = None,
    source: Optional[str] = None,
    ttl_seconds: int = 86400,
) -> None:
    try:
        _get_db().save_agent_data_cache(
            cache_key=_agent_cache_key(data_type, symbol, params or {}),
            topic_key=get_agent_topic_key(),
            data_type=data_type,
            symbol=symbol,
            params=params or {},
            payload=payload,
            source=source,
            as_of=str(date.today()),
            ttl_seconds=ttl_seconds,
        )
    except Exception as exc:
        logger.warning("Agent data cache save failed for %s/%s: %s", data_type, symbol, exc)


def _get_agent_cache(
    *,
    data_type: str,
    symbol: str,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    try:
        return _get_db().get_agent_data_cache(
            _agent_cache_key(data_type, symbol, params or {})
        )
    except Exception as exc:
        logger.warning("Agent data cache read failed for %s/%s: %s", data_type, symbol, exc)
        return None


def _compact_fundamental_context(fundamental_context: dict) -> dict:
    """Reduce token footprint for tool responses while keeping key semantics."""
    if not isinstance(fundamental_context, dict):
        return {}
    blocks = (
        "valuation",
        "growth",
        "earnings",
        "institution",
        "capital_flow",
        "dragon_tiger",
        "boards",
    )
    compact = {
        "market": fundamental_context.get("market"),
        "status": fundamental_context.get("status"),
        "coverage": fundamental_context.get("coverage", {}),
    }
    for block in blocks:
        payload = fundamental_context.get(block, {})
        if isinstance(payload, dict):
            compact[block] = {
                "status": payload.get("status"),
                "data": payload.get("data", {}),
            }
        else:
            compact[block] = {"status": "failed", "data": {}}
    return compact


def _compact_portfolio_snapshot(snapshot: dict, include_positions: bool = False, top_n: int = 5) -> dict:
    """Shrink portfolio snapshot payload for default tool responses."""
    if not isinstance(snapshot, dict):
        return {}
    compact_accounts = []
    for account in snapshot.get("accounts", []) or []:
        if not isinstance(account, dict):
            continue
        positions = list(account.get("positions") or [])
        positions = sorted(
            positions,
            key=lambda item: float((item or {}).get("market_value_base") or 0.0),
            reverse=True,
        )
        account_payload = {
            "account_id": account.get("account_id"),
            "account_name": account.get("account_name"),
            "market": account.get("market"),
            "base_currency": account.get("base_currency"),
            "total_equity": account.get("total_equity"),
            "total_market_value": account.get("total_market_value"),
            "total_cash": account.get("total_cash"),
            "realized_pnl": account.get("realized_pnl"),
            "unrealized_pnl": account.get("unrealized_pnl"),
            "fx_stale": account.get("fx_stale"),
        }
        if include_positions:
            account_payload["positions"] = positions
        else:
            account_payload["position_count"] = len(positions)
            account_payload["top_positions"] = positions[:top_n]
        compact_accounts.append(account_payload)

    return {
        "as_of": snapshot.get("as_of"),
        "cost_method": snapshot.get("cost_method"),
        "currency": snapshot.get("currency"),
        "account_count": snapshot.get("account_count"),
        "total_cash": snapshot.get("total_cash"),
        "total_market_value": snapshot.get("total_market_value"),
        "total_equity": snapshot.get("total_equity"),
        "realized_pnl": snapshot.get("realized_pnl"),
        "unrealized_pnl": snapshot.get("unrealized_pnl"),
        "fx_stale": snapshot.get("fx_stale"),
        "accounts": compact_accounts,
    }


def _compact_portfolio_risk(risk: dict, top_n: int = 10) -> dict:
    """Shrink portfolio risk payload for tool responses."""
    if not isinstance(risk, dict):
        return {}
    concentration = risk.get("concentration", {}) or {}
    top_positions = list(concentration.get("top_positions") or [])
    top_positions = sorted(
        top_positions,
        key=lambda item: float((item or {}).get("weight_pct") or 0.0),
        reverse=True,
    )[:top_n]
    stop_loss = risk.get("stop_loss", {}) or {}
    stop_items = list(stop_loss.get("items") or [])
    stop_items = sorted(
        stop_items,
        key=lambda item: float((item or {}).get("loss_pct") or 0.0),
        reverse=True,
    )[:top_n]
    drawdown = risk.get("drawdown", {}) or {}
    return {
        "as_of": risk.get("as_of"),
        "currency": risk.get("currency"),
        "cost_method": risk.get("cost_method"),
        "thresholds": risk.get("thresholds", {}),
        "concentration": {
            "alert": concentration.get("alert", False),
            "top_weight_pct": concentration.get("top_weight_pct"),
            "top_positions": top_positions,
        },
        "drawdown": {
            "alert": drawdown.get("alert", False),
            "max_drawdown_pct": drawdown.get("max_drawdown_pct"),
            "current_drawdown_pct": drawdown.get("current_drawdown_pct"),
            "fx_stale": drawdown.get("fx_stale", False),
        },
        "stop_loss": {
            "near_alert": stop_loss.get("near_alert", False),
            "triggered_count": stop_loss.get("triggered_count", 0),
            "near_count": stop_loss.get("near_count", 0),
            "items": stop_items,
        },
    }


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, str):
            cleaned = value.strip().replace("%", "").replace(",", "")
            if not cleaned or cleaned.lower() in {"nan", "nat", "none", "--", "---"}:
                return None
            return float(cleaned)
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none", "--", "---"}:
        return None
    return text


def _normalize_fund_code(fund_code: str) -> str:
    raw = str(fund_code or "").strip().upper()
    if raw.endswith(".OF"):
        raw = raw[:-3]
    return raw.zfill(6) if raw.isdigit() and len(raw) <= 6 else raw


def _df_records(df: Any, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if df is None or not hasattr(df, "empty") or df.empty:
        return []
    records = df.head(limit).to_dict("records") if limit else df.to_dict("records")
    return [{str(k): v for k, v in row.items()} for row in records]


def _compact_records(
    records: List[Dict[str, Any]],
    columns: List[str],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    for row in records[:limit]:
        item = {}
        for column in columns:
            value = row.get(column)
            cleaned = _clean_text(value)
            if cleaned is not None:
                item[column] = cleaned
        if item:
            compact.append(item)
    return compact


def _nav_rows(nav_df: Any) -> List[Dict[str, Any]]:
    rows = _df_records(nav_df)
    parsed_rows: List[Dict[str, Any]] = []
    for row in rows:
        nav_date_raw = row.get("净值日期")
        nav_value = _safe_float(row.get("单位净值"))
        if nav_date_raw is None or nav_value is None:
            continue
        try:
            nav_date = datetime.fromisoformat(str(nav_date_raw)[:10]).date()
        except ValueError:
            continue
        parsed_rows.append({"date": nav_date, "nav": nav_value, "daily_return_pct": _safe_float(row.get("日增长率"))})
    return sorted(parsed_rows, key=lambda item: item["date"])


def _nearest_nav_before(rows: List[Dict[str, Any]], target: date) -> Optional[Dict[str, Any]]:
    candidate = None
    for row in rows:
        if row["date"] <= target:
            candidate = row
        else:
            break
    return candidate


def _period_return(rows: List[Dict[str, Any]], days: int) -> Optional[float]:
    if len(rows) < 2:
        return None
    latest = rows[-1]
    start = _nearest_nav_before(rows, latest["date"] - timedelta(days=days))
    if not start or not start.get("nav"):
        return None
    return round((latest["nav"] / start["nav"] - 1) * 100, 2)


def _max_drawdown(rows: List[Dict[str, Any]], days: Optional[int] = None) -> Optional[float]:
    if len(rows) < 2:
        return None
    sample = rows
    if days is not None:
        start_date = rows[-1]["date"] - timedelta(days=days)
        sample = [row for row in rows if row["date"] >= start_date]
    peak = None
    max_dd = 0.0
    for row in sample:
        nav = row["nav"]
        peak = nav if peak is None else max(peak, nav)
        if peak:
            max_dd = min(max_dd, nav / peak - 1)
    return round(abs(max_dd) * 100, 2)


def _monthly_win_rate(rows: List[Dict[str, Any]], months: int = 12) -> Optional[float]:
    if len(rows) < 2:
        return None
    start_date = rows[-1]["date"] - timedelta(days=months * 31)
    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        if row["date"] < start_date:
            continue
        key = row["date"].strftime("%Y-%m")
        buckets.setdefault(key, []).append(row)
    wins = 0
    total = 0
    for bucket_rows in buckets.values():
        if len(bucket_rows) < 2:
            continue
        total += 1
        if bucket_rows[-1]["nav"] > bucket_rows[0]["nav"]:
            wins += 1
    if total == 0:
        return None
    return round(wins / total * 100, 2)


def _fund_performance_from_nav(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"status": "empty"}
    latest = rows[-1]
    one_year_return = _period_return(rows, 365)
    one_year_dd = _max_drawdown(rows, 365)
    calmar = None
    if one_year_return is not None and one_year_dd and one_year_dd > 0:
        calmar = round(one_year_return / one_year_dd, 3)
    return {
        "status": "ok",
        "latest_nav": latest["nav"],
        "latest_nav_date": latest["date"].isoformat(),
        "latest_daily_return_pct": latest.get("daily_return_pct"),
        "period_returns_pct": {
            "1m": _period_return(rows, 30),
            "3m": _period_return(rows, 90),
            "6m": _period_return(rows, 180),
            "1y": one_year_return,
            "3y": _period_return(rows, 365 * 3),
        },
        "max_drawdown_pct": {
            "1y": one_year_dd,
            "all": _max_drawdown(rows),
        },
        "calmar_ratio_1y": calmar,
        "monthly_win_rate_12m_pct": _monthly_win_rate(rows, 12),
        "data_points": len(rows),
    }


def _map_fund_rank_category(fund_type: Optional[str]) -> str:
    text = str(fund_type or "").upper()
    if "QDII" in text:
        return "QDII"
    if "FOF" in text:
        return "FOF"
    if "指数" in text:
        return "指数型"
    if "债" in text:
        return "债券型"
    if "股票" in text:
        return "股票型"
    if "混合" in text:
        return "混合型"
    return "全部"


def _rank_bucket_label(rank: int, total: int, bucket_size_pct: int = 20) -> str:
    if total <= 0:
        return "unknown"
    bucket_count = max(1, int(100 / bucket_size_pct))
    bucket_index = min(bucket_count - 1, int(((max(1, rank) - 1) / total) * bucket_count))
    start = bucket_index * bucket_size_pct
    end = min(100, start + bucket_size_pct)
    return f"{start}-{end}%"


def _fund_rank_profiles(records: List[Dict[str, Any]], periods: List[str]) -> Dict[str, Dict[str, Any]]:
    profiles: Dict[str, Dict[str, Any]] = {}
    for period in periods:
        valid_rows = []
        for row in records:
            value = _safe_float(row.get(period))
            code = _normalize_fund_code(row.get("基金代码"))
            if code and value is not None:
                valid_rows.append((code, value))
        valid_rows.sort(key=lambda item: item[1], reverse=True)
        total = len(valid_rows)
        for rank, (code, value) in enumerate(valid_rows, start=1):
            profiles.setdefault(code, {})[period] = {
                "return_pct": value,
                "rank": rank,
                "total": total,
                "percentile_bucket": _rank_bucket_label(rank, total),
            }
    return profiles


def _parse_chinese_amount_yi(value: Any) -> Optional[float]:
    text = _clean_text(value)
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    number = _safe_float(match.group(0)) if match else None
    if number is None:
        return None
    if "万" in text:
        return round(number / 10000, 4)
    if "亿" in text:
        return round(number, 4)
    return round(number, 4)


def _fund_scale_yi_from_overview(row: Dict[str, Any], unit_nav: Optional[float]) -> Optional[float]:
    share_yi = _parse_chinese_amount_yi(row.get("份额规模"))
    if share_yi is not None and unit_nav is not None:
        return round(share_yi * unit_nav, 2)
    return _parse_chinese_amount_yi(row.get("净资产规模"))


def _fund_one_year_drawdown_from_analysis(records: List[Dict[str, Any]]) -> Optional[float]:
    for row in records:
        period = _clean_text(row.get("周期"))
        drawdown = _safe_float(row.get("最大回撤"))
        if period == "近1年":
            return abs(drawdown) if drawdown is not None else None
    return None


# ============================================================
# get_realtime_quote
# ============================================================

def _handle_get_realtime_quote(stock_code: str) -> dict:
    """Get real-time stock quote."""
    manager = _get_fetcher_manager()
    quote = manager.get_realtime_quote(stock_code)
    if quote is None:
        return {
            "error": f"No realtime quote available for {stock_code}",
            "retriable": False,
            "note": "All data sources unavailable (network or circuit-breaker). Skip this tool and proceed with historical data only.",
        }

    return {
        "code": quote.code,
        "name": quote.name,
        "price": quote.price,
        "change_pct": quote.change_pct,
        "change_amount": quote.change_amount,
        "volume": quote.volume,
        "amount": quote.amount,
        "volume_ratio": quote.volume_ratio,
        "turnover_rate": quote.turnover_rate,
        "amplitude": quote.amplitude,
        "open": quote.open_price,
        "high": quote.high,
        "low": quote.low,
        "pre_close": quote.pre_close,
        "pe_ratio": quote.pe_ratio,
        "pb_ratio": quote.pb_ratio,
        "total_mv": quote.total_mv,
        "circ_mv": quote.circ_mv,
        "change_60d": quote.change_60d,
        "source": quote.source.value if hasattr(quote.source, 'value') else str(quote.source),
    }


get_realtime_quote_tool = ToolDefinition(
    name="get_realtime_quote",
    description="Get real-time stock quote including price, change%, volume ratio, "
                "turnover rate, PE, PB, market cap. Returns live market data.",
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="Stock code, e.g., '600519' (A-share), 'AAPL' (US), 'hk00700' (HK)",
        ),
    ],
    handler=_handle_get_realtime_quote,
    category="data",
)


# ============================================================
# get_daily_history
# ============================================================

def _handle_get_daily_history(stock_code: str, days: int = 60) -> dict:
    """Get daily OHLCV history data."""
    effective_days, metadata = _normalize_history_days(days)
    _, normalized_code = _history_code_candidates(stock_code)
    cache_params = {"stock_code": stock_code, "days": effective_days}

    if is_agent_chat_mode():
        cached = _get_agent_cache(
            data_type="daily_history",
            symbol=normalized_code,
            params=cache_params,
        )
        if cached is not None:
            records = list(cached.get("payload") or [])
            return _append_history_metadata({
                "code": normalized_code,
                "source": cached.get("source") or "agent_data_cache",
                "cache_hit": True,
                "requested_days": effective_days,
                "effective_days": effective_days,
                "actual_records": len(records),
                "partial_cache": len(records) < effective_days,
                "total_records": len(records),
                "data": records,
            }, metadata)

    from src.services.history_loader import load_history_df
    df, source = load_history_df(stock_code, days=effective_days)

    if df is None or df.empty:
        return _append_history_metadata(
            {"error": f"No historical data available for {stock_code}"},
            metadata,
        )

    if source != "db_cache":
        if is_agent_chat_mode():
            _save_agent_cache(
                data_type="daily_history",
                symbol=normalized_code,
                payload=df.tail(min(effective_days, len(df))).to_dict(orient="records"),
                params=cache_params,
                source=source,
                ttl_seconds=86400,
            )
        else:
            try:
                saved_count = _get_db().save_daily_data(df, normalized_code, source)
                logger.info(
                    "Agent daily history persisted for %s (source=%s, new_records=%s)",
                    normalized_code,
                    source,
                    saved_count,
                )
            except Exception as exc:
                logger.warning(
                    "Agent daily history persistence failed for %s: %s",
                    normalized_code,
                    exc,
                )

    # Convert DataFrame to list of dicts (last N records)
    records = df.tail(min(effective_days, len(df))).to_dict(orient="records")
    # Ensure date is string
    for r in records:
        if "date" in r:
            r["date"] = str(r["date"])

    response_code = stock_code
    if source == "db_cache" and records:
        response_code = records[-1].get("code") or response_code

    return _append_history_metadata({
        "code": response_code,
        "source": source,
        "cache_hit": source == "db_cache",
        "requested_days": effective_days,
        "effective_days": effective_days,
        "actual_records": len(records),
        "partial_cache": source == "db_cache" and len(records) < effective_days,
        "total_records": len(records),
        "data": records,
    }, metadata)


get_daily_history_tool = ToolDefinition(
    name="get_daily_history",
    description="Get daily OHLCV (open, high, low, close, volume) historical data "
                "with MA5/MA10/MA20 indicators. Returns the last N trading days.",
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="Stock code, e.g., '600519' (A-share), 'AAPL' (US)",
        ),
        ToolParameter(
            name="days",
            type="integer",
            description="Number of trading days to fetch (default: 60)",
            required=False,
            default=60,
        ),
    ],
    handler=_handle_get_daily_history,
    category="data",
)


# ============================================================
# get_chip_distribution
# ============================================================

def _handle_get_chip_distribution(stock_code: str) -> dict:
    """Get chip distribution data."""
    manager = _get_fetcher_manager()
    chip = manager.get_chip_distribution(stock_code)

    if chip is None:
        return {"error": f"No chip distribution data available for {stock_code}"}

    return {
        "code": chip.code,
        "date": chip.date,
        "source": chip.source,
        "profit_ratio": chip.profit_ratio,
        "avg_cost": chip.avg_cost,
        "cost_90_low": chip.cost_90_low,
        "cost_90_high": chip.cost_90_high,
        "concentration_90": chip.concentration_90,
        "cost_70_low": chip.cost_70_low,
        "cost_70_high": chip.cost_70_high,
        "concentration_70": chip.concentration_70,
    }


get_chip_distribution_tool = ToolDefinition(
    name="get_chip_distribution",
    description="Get chip distribution analysis for a stock. Returns profit ratio, "
                "average cost, chip concentration at 90% and 70% levels. "
                "Useful for judging support/resistance and holding structure.",
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="A-share stock code, e.g., '600519'",
        ),
    ],
    handler=_handle_get_chip_distribution,
    category="data",
)


# ============================================================
# get_analysis_context
# ============================================================

def _handle_get_analysis_context(stock_code: str) -> dict:
    """Get stored analysis context from database."""
    db = _get_db()
    context = db.get_analysis_context(stock_code)

    if context is None:
        return {"error": f"No analysis context in DB for {stock_code}"}

    # Return safely serializable version (remove raw_data to save tokens)
    safe_context = {}
    for k, v in context.items():
        if k == "raw_data":
            safe_context["has_raw_data"] = True
            safe_context["raw_data_count"] = len(v) if isinstance(v, list) else 0
        else:
            safe_context[k] = v

    return safe_context


get_analysis_context_tool = ToolDefinition(
    name="get_analysis_context",
    description="Get historical analysis context from the database for a stock. "
                "Returns today's and yesterday's OHLCV data, MA alignment status, "
                "volume and price changes. Provides the technical data foundation.",
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="Stock code, e.g., '600519'",
        ),
    ],
    handler=_handle_get_analysis_context,
    category="data",
)


# ============================================================
# get_stock_info
# ============================================================

def _handle_get_stock_info(stock_code: str) -> dict:
    """Get stock fundamental information through unified fundamental context."""
    manager = _get_fetcher_manager()
    try:
        fundamental_context = manager.get_fundamental_context(stock_code)
    except Exception as e:
        logger.warning(f"get_stock_info via fundamental pipeline failed for {stock_code}: {e}")
        fundamental_context = manager.build_failed_fundamental_context(stock_code, str(e))

    compact_context = _compact_fundamental_context(fundamental_context)
    valuation = compact_context.get("valuation", {}).get("data", {})
    sector_rankings = compact_context.get("boards", {}).get("data", {})
    belong_boards = manager.get_belong_boards(stock_code)

    stock_name = stock_code.upper()
    try:
        stock_name = manager.get_stock_name(stock_code) or stock_name
    except Exception:
        pass

    return {
        "code": stock_code.upper(),
        "name": stock_name,
        "pe_ratio": valuation.get("pe_ratio"),
        "pb_ratio": valuation.get("pb_ratio"),
        "total_mv": valuation.get("total_mv"),
        "circ_mv": valuation.get("circ_mv"),
        "fundamental_context": compact_context,
        "belong_boards": belong_boards,
        # Compatibility alias for existing callers; prefer belong_boards.
        # Planned for future deprecation in a major version.
        "boards": belong_boards,
        "sector_rankings": sector_rankings,
    }


get_stock_info_tool = ToolDefinition(
    name="get_stock_info",
    description="Get stock fundamental information: valuation, growth, earnings, institution flow, "
                "stock sector membership (belong_boards; boards is compatibility alias) and "
                "sector rankings. Returns a compact fundamental_context to reduce token usage.",
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="A-share stock code, e.g., '600519'",
        ),
    ],
    handler=_handle_get_stock_info,
    category="data",
)


# ============================================================
# get_portfolio_snapshot
# ============================================================

def _handle_get_portfolio_snapshot(
    account_id: Optional[int] = None,
    cost_method: str = "fifo",
    include_positions: bool = False,
    include_risk: bool = True,
    as_of: Optional[str] = None,
) -> dict:
    """Get compact portfolio snapshot for account-aware suggestions."""
    method = (cost_method or "fifo").strip().lower()
    if method not in {"fifo", "avg"}:
        return {"error": "cost_method must be fifo or avg"}

    as_of_date = None
    if as_of:
        try:
            as_of_date = date.fromisoformat(str(as_of).strip())
        except ValueError:
            return {"error": "as_of must be YYYY-MM-DD"}

    try:
        from src.services.portfolio_service import PortfolioService
        from src.services.portfolio_risk_service import PortfolioRiskService
    except Exception as exc:
        logger.warning("get_portfolio_snapshot unavailable: %s", exc)
        return {"status": "not_supported", "error": f"portfolio module unavailable: {exc}"}

    try:
        portfolio_service = PortfolioService()
        snapshot = portfolio_service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of_date,
            cost_method=method,
        )
        result = {
            "status": "ok",
            "snapshot": _compact_portfolio_snapshot(snapshot, include_positions=bool(include_positions)),
        }
        if include_risk:
            try:
                risk_service = PortfolioRiskService(portfolio_service=portfolio_service)
                risk = risk_service.get_risk_report(
                    account_id=account_id,
                    as_of=as_of_date,
                    cost_method=method,
                )
                result["risk"] = {"status": "ok", **_compact_portfolio_risk(risk)}
            except Exception as risk_exc:
                logger.warning("get_portfolio_snapshot risk block failed: %s", risk_exc)
                result["risk"] = {"status": "failed", "error": str(risk_exc)}
        return result
    except Exception as exc:
        logger.warning("get_portfolio_snapshot failed: %s", exc)
        return {"status": "failed", "error": f"failed to fetch portfolio snapshot: {exc}"}


get_portfolio_snapshot_tool = ToolDefinition(
    name="get_portfolio_snapshot",
    description="Get portfolio snapshot summary and optional risk blocks. "
                "Default returns compact summary for lower token usage; "
                "set include_positions=true to include full position details.",
    parameters=[
        ToolParameter(
            name="account_id",
            type="integer",
            description="Optional account id; omit to use all active accounts.",
            required=False,
            default=None,
        ),
        ToolParameter(
            name="cost_method",
            type="string",
            description="Cost method: fifo or avg (default: fifo).",
            required=False,
            default="fifo",
            enum=["fifo", "avg"],
        ),
        ToolParameter(
            name="include_positions",
            type="boolean",
            description="Whether to include full positions in snapshot output (default: false).",
            required=False,
            default=False,
        ),
        ToolParameter(
            name="include_risk",
            type="boolean",
            description="Whether to include risk summary block (default: true).",
            required=False,
            default=True,
        ),
        ToolParameter(
            name="as_of",
            type="string",
            description="Optional snapshot date in YYYY-MM-DD format (default: today).",
            required=False,
            default=None,
        ),
    ],
    handler=_handle_get_portfolio_snapshot,
    category="data",
)


# ============================================================
# get_fund_analysis_context
# ============================================================

def _handle_get_fund_analysis_context(fund_code: str, report_year: Optional[str] = None) -> dict:
    """Aggregate open-end fund context for fund AI Q&A."""
    code = _normalize_fund_code(fund_code)
    if not code:
        return {"status": "failed", "error": "fund_code is required"}

    year = str(report_year or date.today().year).strip()
    flags: List[str] = []
    result: Dict[str, Any] = {
        "status": "ok",
        "fund_code": code,
        "report_year": year,
        "source": "akshare",
        "profile": {"status": "empty"},
        "performance": {"status": "empty"},
        "risk_metrics": {"status": "empty"},
        "holding_experience": {"status": "empty"},
        "holdings": {"status": "empty"},
        "data_flags": flags,
    }

    try:
        import akshare as ak
    except Exception as exc:
        return {"status": "failed", "fund_code": code, "error": f"akshare unavailable: {exc}"}

    try:
        overview_df = ak.fund_overview_em(symbol=code)
        overview = _df_records(overview_df, limit=1)
        if overview:
            row = overview[0]
            result["profile"] = {
                "status": "ok",
                "fund_full_name": _clean_text(row.get("基金全称")),
                "fund_short_name": _clean_text(row.get("基金简称")),
                "fund_code_display": _clean_text(row.get("基金代码")),
                "fund_type": _clean_text(row.get("基金类型")),
                "issue_date": _clean_text(row.get("发行日期")),
                "inception": _clean_text(row.get("成立日期/规模")),
                "net_asset_size": _clean_text(row.get("净资产规模")),
                "share_size": _clean_text(row.get("份额规模")),
                "manager_company": _clean_text(row.get("基金管理人")),
                "custodian": _clean_text(row.get("基金托管人")),
                "fund_managers": _clean_text(row.get("基金经理人")),
                "dividend_since_inception": _clean_text(row.get("成立来分红")),
                "management_fee": _clean_text(row.get("管理费率")),
                "custody_fee": _clean_text(row.get("托管费率")),
                "sales_service_fee": _clean_text(row.get("销售服务费率")),
                "benchmark": _clean_text(row.get("业绩比较基准")),
                "tracking_target": _clean_text(row.get("跟踪标的")),
            }
        else:
            flags.append("fund_overview_empty")
    except Exception as exc:
        flags.append(f"fund_overview_failed: {exc}")

    try:
        purchase_df = ak.fund_purchase_em()
        if hasattr(purchase_df, "empty") and not purchase_df.empty and "基金代码" in purchase_df.columns:
            matched = purchase_df[purchase_df["基金代码"].astype(str).str.zfill(6) == code]
            records = _df_records(matched, limit=1)
            if records:
                row = records[0]
                result["trading"] = {
                    "status": "ok",
                    "latest_nav_or_income": _clean_text(row.get("最新净值/万份收益")),
                    "latest_report_time": _clean_text(row.get("最新净值/万份收益-报告时间")),
                    "subscription_status": _clean_text(row.get("申购状态")),
                    "redemption_status": _clean_text(row.get("赎回状态")),
                    "next_open_date": _clean_text(row.get("下一开放日")),
                    "min_purchase_amount": _clean_text(row.get("购买起点")),
                    "daily_purchase_limit": _clean_text(row.get("日累计限定金额")),
                    "fee": _clean_text(row.get("手续费")),
                }
    except Exception as exc:
        flags.append(f"fund_purchase_failed: {exc}")

    try:
        nav_df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        nav_rows = _nav_rows(nav_df)
        result["performance"] = _fund_performance_from_nav(nav_rows)
    except Exception as exc:
        flags.append(f"fund_nav_failed: {exc}")

    try:
        analysis_df = ak.fund_individual_analysis_xq(symbol=code, timeout=15)
        rows = _compact_records(
            _df_records(analysis_df),
            ["周期", "较同类风险收益比", "较同类抗风险波动", "年化波动率", "年化夏普比率", "最大回撤"],
            limit=5,
        )
        if rows:
            result["risk_metrics"] = {"status": "ok", "periods": rows}
    except Exception as exc:
        flags.append(f"fund_risk_metrics_failed: {exc}")

    try:
        achievement_df = ak.fund_individual_achievement_xq(symbol=code, timeout=15)
        rows = _compact_records(
            _df_records(achievement_df),
            ["业绩类型", "周期", "本产品区间收益", "本产品最大回撒", "周期收益同类排名"],
            limit=6,
        )
        if rows:
            result["achievement"] = {"status": "ok", "periods": rows}
    except Exception as exc:
        flags.append(f"fund_achievement_failed: {exc}")

    try:
        probability_df = ak.fund_individual_profit_probability_xq(symbol=code, timeout=15)
        rows = _compact_records(
            _df_records(probability_df),
            ["持有时长", "盈利概率", "平均收益"],
            limit=5,
        )
        if rows:
            result["holding_experience"] = {"status": "ok", "periods": rows}
    except Exception as exc:
        flags.append(f"fund_profit_probability_failed: {exc}")

    try:
        stock_hold_df = ak.fund_portfolio_hold_em(symbol=code, date=year)
        stock_rows = _compact_records(
            _df_records(stock_hold_df),
            ["股票代码", "股票名称", "占净值比例", "持股数", "持仓市值", "季度"],
            limit=8,
        )
        top_weight = sum((_safe_float(row.get("占净值比例")) or 0.0) for row in stock_rows)
        result["holdings"] = {
            "status": "ok" if stock_rows else "empty",
            "top_stocks": stock_rows,
            "top_stock_weight_pct": round(top_weight, 2) if stock_rows else None,
        }
    except Exception as exc:
        flags.append(f"fund_stock_holdings_failed: {exc}")

    try:
        industry_df = ak.fund_portfolio_industry_allocation_em(symbol=code, date=year)
        industry_rows = _compact_records(
            _df_records(industry_df),
            ["行业类别", "占净值比例", "市值", "截止时间"],
            limit=6,
        )
        result.setdefault("holdings", {})["industry_allocation"] = industry_rows
    except Exception as exc:
        flags.append(f"fund_industry_allocation_failed: {exc}")

    try:
        bond_hold_df = ak.fund_portfolio_bond_hold_em(symbol=code, date=year)
        bond_rows = _compact_records(
            _df_records(bond_hold_df),
            ["债券代码", "债券名称", "占净值比例", "持仓市值", "季度"],
            limit=5,
        )
        result.setdefault("holdings", {})["top_bonds"] = bond_rows
    except Exception as exc:
        flags.append(f"fund_bond_holdings_failed: {exc}")

    if flags:
        result["status"] = "partial"
    return result


get_fund_analysis_context_tool = ToolDefinition(
    name="get_fund_analysis_context",
    description=(
        "Get aggregated open-end fund analysis context from AkShare, including profile, NAV performance, "
        "risk metrics, holding experience, stock/bond holdings and industry allocation. "
        "Use this as the primary tool for fund manager, holding, performance, drawdown, risk and buy/hold Q&A. "
        "ETF-specific market quote is not included."
    ),
    parameters=[
        ToolParameter(
            name="fund_code",
            type="string",
            description="6-digit fund code, e.g., '000001'.",
        ),
        ToolParameter(
            name="report_year",
            type="string",
            description="Optional portfolio report year, e.g., '2024'. Defaults to current year.",
            required=False,
            default=None,
        ),
    ],
    handler=_handle_get_fund_analysis_context,
    category="data",
)


# ============================================================
# get_similar_funds_by_rank_profile
# ============================================================

def _handle_get_similar_funds_by_rank_profile(fund_code: str, limit: int = 10, min_scale_yi: float = 5.0) -> dict:
    """Find open-end funds with the same category and similar return-rank profile."""
    code = _normalize_fund_code(fund_code)
    if not code:
        return {"status": "failed", "error": "fund_code is required"}

    result_limit = max(1, min(int(limit or 10), 20))
    min_scale = max(0.0, float(min_scale_yi if min_scale_yi is not None else 5.0))
    periods = ["近3月", "近1年", "近3年"]
    flags: List[str] = []

    try:
        import akshare as ak
    except Exception as exc:
        return {"status": "failed", "fund_code": code, "error": f"akshare unavailable: {exc}"}

    fund_type = None
    fund_name = None
    try:
        overview = _df_records(ak.fund_overview_em(symbol=code), limit=1)
        if overview:
            fund_type = _clean_text(overview[0].get("基金类型"))
            fund_name = _clean_text(overview[0].get("基金简称")) or _clean_text(overview[0].get("基金全称"))
    except Exception as exc:
        flags.append(f"fund_overview_failed: {exc}")

    category = _map_fund_rank_category(fund_type)
    try:
        rank_df = ak.fund_open_fund_rank_em(symbol=category)
        records = _df_records(rank_df)
    except Exception as exc:
        return {
            "status": "failed",
            "fund_code": code,
            "fund_name": fund_name,
            "fund_type": fund_type,
            "rank_category": category,
            "error": f"fund rank fetch failed: {exc}",
            "data_flags": flags,
        }

    current_row = None
    normalized_records = []
    for row in records:
        row_code = _normalize_fund_code(row.get("基金代码"))
        if not row_code:
            continue
        normalized = dict(row)
        normalized["基金代码"] = row_code
        normalized_records.append(normalized)
        if row_code == code:
            current_row = normalized

    if current_row is None:
        return {
            "status": "empty",
            "fund_code": code,
            "fund_name": fund_name,
            "fund_type": fund_type,
            "rank_category": category,
            "message": "current fund not found in open fund rank table",
            "data_flags": flags,
        }

    profiles = _fund_rank_profiles(normalized_records, periods)
    current_profile = profiles.get(code, {})
    matched_periods = [period for period in periods if period in current_profile]
    missing_periods = [period for period in periods if period not in current_profile]
    for period in missing_periods:
        flags.append(f"current_{period}_rank_missing")

    if not matched_periods:
        return {
            "status": "empty",
            "fund_code": code,
            "fund_name": fund_name or _clean_text(current_row.get("基金简称")),
            "fund_type": fund_type,
            "rank_category": category,
            "rank_profile": {},
            "similar_funds": [],
            "data_flags": flags,
        }

    current_buckets = {
        period: current_profile[period]["percentile_bucket"]
        for period in matched_periods
    }
    candidate_pool = []
    for row in normalized_records:
        row_code = row.get("基金代码")
        if row_code == code:
            continue
        profile = profiles.get(row_code, {})
        if not all(profile.get(period, {}).get("percentile_bucket") == bucket for period, bucket in current_buckets.items()):
            continue
        diff = sum(
            abs((profile[period].get("return_pct") or 0.0) - (current_profile[period].get("return_pct") or 0.0))
            for period in matched_periods
        )
        candidate_pool.append({
            "fund_code": row_code,
            "fund_name": _clean_text(row.get("基金简称")),
            "date": _clean_text(row.get("日期")),
            "unit_nav": _safe_float(row.get("单位净值")),
            "period_returns_pct": {
                period: profile[period]["return_pct"]
                for period in matched_periods
                if period in profile
            },
            "rank_profile": {
                period: profile[period]
                for period in matched_periods
                if period in profile
            },
            "fee": _clean_text(row.get("手续费")),
            "matched_periods": len(matched_periods),
            "return_diff_sum_pct": round(diff, 2),
        })

    candidate_pool.sort(key=lambda item: (item["return_diff_sum_pct"], item["fund_code"]))
    candidates = []
    filtered_small_scale = 0
    scale_checked = 0
    for item in candidate_pool:
        if len(candidates) >= result_limit:
            break
        scale_yi = None
        try:
            overview_rows = _df_records(ak.fund_overview_em(symbol=item["fund_code"]), limit=1)
            if overview_rows:
                scale_yi = _fund_scale_yi_from_overview(overview_rows[0], item.get("unit_nav"))
        except Exception as exc:
            flags.append(f"candidate_scale_failed_{item['fund_code']}: {exc}")
        scale_checked += 1
        item["estimated_scale_yi"] = scale_yi
        if scale_yi is not None and scale_yi < min_scale:
            filtered_small_scale += 1
            continue
        try:
            analysis_rows = _df_records(ak.fund_individual_analysis_xq(symbol=item["fund_code"], timeout=15))
            item["max_drawdown_1y_pct"] = _fund_one_year_drawdown_from_analysis(analysis_rows)
        except Exception as exc:
            item["max_drawdown_1y_pct"] = None
            flags.append(f"candidate_drawdown_failed_{item['fund_code']}: {exc}")
        candidates.append(item)

    return {
        "status": "ok",
        "fund_code": code,
        "fund_name": fund_name or _clean_text(current_row.get("基金简称")),
        "fund_type": fund_type,
        "rank_category": category,
        "bucket_size_pct": 20,
        "min_scale_yi": min_scale,
        "matched_periods": matched_periods,
        "rank_profile": current_profile,
        "display_only_fields": ["max_drawdown_1y_pct"],
        "similar_count": len(candidates),
        "candidate_pool_count": len(candidate_pool),
        "scale_checked_count": scale_checked,
        "filtered_small_scale_count": filtered_small_scale,
        "similar_funds": candidates,
        "data_flags": flags,
    }


get_similar_funds_by_rank_profile_tool = ToolDefinition(
    name="get_similar_funds_by_rank_profile",
    description=(
        "Find funds similar to the current open-end fund by category and 20-percentile return-rank buckets. "
        "Use only when the user asks for peer funds, similar funds, alternatives, or comparable funds. "
        "It compares same-category funds across available 3-month, 1-year and 3-year return rankings, "
        "excludes funds with estimated scale below 500M CNY by default, and includes 1-year max drawdown "
        "for display only."
    ),
    parameters=[
        ToolParameter(
            name="fund_code",
            type="string",
            description="6-digit fund code, e.g., '000001'.",
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum number of similar funds to return, default 10, max 20.",
            required=False,
            default=10,
        ),
        ToolParameter(
            name="min_scale_yi",
            type="number",
            description="Minimum estimated fund scale in 100M CNY, default 5. Funds below this scale are excluded.",
            required=False,
            default=5.0,
        ),
    ],
    handler=_handle_get_similar_funds_by_rank_profile,
    category="data",
)


# ============================================================
# Export all data tools
# ============================================================

ALL_DATA_TOOLS = [
    get_realtime_quote_tool,
    get_daily_history_tool,
    get_chip_distribution_tool,
    get_analysis_context_tool,
    get_stock_info_tool,
    get_portfolio_snapshot_tool,
    get_fund_analysis_context_tool,
    get_similar_funds_by_rank_profile_tool,
]


# ============================================================
# get_capital_flow
# ============================================================

def _handle_get_capital_flow(stock_code: str) -> dict:
    """Get main-force capital flow data for a stock."""
    manager = _get_fetcher_manager()
    try:
        ctx = manager.get_capital_flow_context(stock_code)
    except Exception as exc:
        logger.warning("get_capital_flow failed for %s: %s", stock_code, exc)
        return {
            "stock_code": stock_code,
            "status": "error",
            "error": f"capital flow fetch failed: {exc}",
        }

    status = ctx.get("status", "not_supported")
    if status == "not_supported":
        return {
            "stock_code": stock_code,
            "status": "not_supported",
            "note": "Capital flow data is only available for A-share stocks (not ETFs/indices).",
        }

    data = ctx.get("data", {})
    stock_flow = data.get("stock_flow") or {}
    sector_rankings = data.get("sector_rankings") or {}
    errors = ctx.get("errors") or []

    return {
        "stock_code": stock_code,
        "status": status,
        "main_net_inflow": stock_flow.get("main_net_inflow"),
        "inflow_5d": stock_flow.get("inflow_5d"),
        "inflow_10d": stock_flow.get("inflow_10d"),
        "sector_rankings": {
            "top_inflow_sectors": sector_rankings.get("top", [])[:3],
            "top_outflow_sectors": sector_rankings.get("bottom", [])[:3],
        },
        "errors": errors,
    }


get_capital_flow_tool = ToolDefinition(
    name="get_capital_flow",
    description=(
        "Get main-force (主力) capital flow data for an A-share stock. "
        "Returns today's net inflow, 5-day and 10-day cumulative inflows, "
        "and top sector-level capital flow rankings. "
        "Only supported for A-share individual stocks (not ETFs, indices, HK, or US stocks)."
    ),
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="A-share stock code, e.g., '600519'",
        ),
    ],
    handler=_handle_get_capital_flow,
    category="data",
)


ALL_DATA_TOOLS.append(get_capital_flow_tool)
