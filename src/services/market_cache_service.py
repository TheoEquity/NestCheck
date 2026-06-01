# -*- coding: utf-8 -*-
"""SQLite-backed market dashboard cache and refresh service.

Cache model: permanent storage, continuously updated by background tasks.
No TTL — old cached data remains valid until explicitly replaced.
On refresh failure, the last valid payload is always served to the frontend.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from src.storage import MarketCache, get_db
from src.services.correlation_service import get_correlation_heatmap_data
from src.services.equity_ratio_service import calculate_equity_ratio
from src.services.market_risk_radar_service import get_risk_radar_data
from src.services.market_risk_service import calculate_market_risk
from src.services.market_trend_service import get_market_trend_data, get_monthly_seasonality
from src.services.market_trend_service import MARKET_INDICES

logger = logging.getLogger(__name__)

# The set of market dashboard builders — each produces one cache entry.
MARKET_CACHE_BUILDERS = {
    "trend": get_market_trend_data,
    "seasonality": get_monthly_seasonality,
    "radar": get_risk_radar_data,
    "correlation": get_correlation_heatmap_data,
    "risk": calculate_market_risk,
    "equity_ratio": calculate_equity_ratio,
}

FREQUENT_MARKET_CACHE_KEYS = ["trend"]


def _now() -> datetime:
    return datetime.now()


def _is_valid(row: MarketCache) -> bool:
    """Whether the cached row is usable (no expiry check — permanent cache)."""
    return row.status == "success"


def _parse_payload(row: MarketCache) -> Dict[str, Any]:
    payload = json.loads(row.payload)
    if isinstance(payload, dict):
        payload.setdefault("_cache", {})
        payload["_cache"].update(
            {
                "key": row.cache_key,
                "status": row.status,
                "refreshed_at": row.refreshed_at.isoformat() if row.refreshed_at else None,
                "expires_at": None,
            }
        )
        return payload
    return {"data": payload}


def _write_cache(
    cache_key: str,
    payload: Dict[str, Any],
    *,
    status: str = "success",
    error: Optional[str] = None,
) -> None:
    """Persist a market dashboard payload to SQLite with no expiry."""
    db = get_db()
    refreshed_at = _now()
    payload_text = json.dumps(payload, ensure_ascii=False, default=str)

    def _op(session):
        row = session.query(MarketCache).filter_by(cache_key=cache_key).one_or_none()
        if row is None:
            row = MarketCache(cache_key=cache_key, created_at=refreshed_at)
            session.add(row)
        row.payload = payload_text
        row.status = status
        row.error = error
        row.version = 1
        row.refreshed_at = refreshed_at
        row.expires_at = None  # permanent cache, never expires
        row.updated_at = refreshed_at

    db._run_write_transaction(f"market_cache:{cache_key}", _op)


def _read_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    """Read the latest valid cached payload. Returns None only when no valid cache exists."""
    db = get_db()
    with db.get_session() as session:
        row = session.query(MarketCache).filter_by(cache_key=cache_key).one_or_none()
        if row is None or not _is_valid(row):
            return None
        return _parse_payload(row)


def refresh_market_cache(cache_key: str) -> None:
    """Recalculate one market dashboard payload and persist it to SQLite.

    On failure the old cached entry is left untouched so the frontend
    always has something to display.
    """
    if cache_key not in MARKET_CACHE_BUILDERS:
        raise ValueError(f"Unknown market cache key: {cache_key}")

    builder = MARKET_CACHE_BUILDERS[cache_key]
    import inspect
    sig = inspect.signature(builder)
    if "use_file_cache" in sig.parameters:
        payload = builder(use_file_cache=False)
    else:
        payload = builder()
    _write_cache(cache_key, payload)


def get_market_cache_payload(cache_key: str, *, force_refresh: bool = False) -> Dict[str, Any]:
    """Return cached payload directly, never trigger background refresh.

    If no valid cache exists and force_refresh is False, return a minimal
    placeholder so the frontend always receives a 200 with something to render.
    """
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached

    if force_refresh:
        try:
            refresh_market_cache(cache_key)
        except Exception as exc:
            logger.error("Market cache initial build failed: %s, key=%s", exc, cache_key)
        cached = _read_cache(cache_key)
        if cached is not None:
            return cached

    if force_refresh:
        raise ValueError(f"No cached market data for '{cache_key}' — build failed")

    # Return safe placeholder so frontend never shows blank
    return _empty_builder_payload(cache_key)


def _empty_builder_payload(cache_key: str) -> Dict[str, Any]:
    """Return a minimal safe JSON structure for the given cache key."""
    if cache_key == "trend":
        return {"snapshot_date": "", "data": {}, "_cache": {"key": cache_key, "status": "empty"}}
    if cache_key == "seasonality":
        return {"months": [], "avg_returns": [], "win_rates": [], "years_stat": 0,
                "_cache": {"key": cache_key, "status": "empty"}}
    if cache_key == "radar":
        return {"label": "unknown", "volatility": 0, "drawdown": 0, "risk_score": 0,
                "_cache": {"key": cache_key, "status": "empty"}}
    if cache_key == "correlation":
        return {"labels": [], "matrix": [], "_cache": {"key": cache_key, "status": "empty"}}
    if cache_key == "risk":
        return {"chinese_vix": {"value": 0}, "_cache": {"key": cache_key, "status": "empty"}}
    if cache_key == "equity_ratio":
        return {"equity_ratio": 0, "planned_equity_ratio": None,
                "active_allocation_plan_id": None, "active_allocation_plan_generated_at": None,
                "total_cny": 0, "equity_cny": 0,
                "_cache": {"key": cache_key, "status": "empty"}}
    return {"_cache": {"key": cache_key, "status": "empty"}}


def _current_week_friday() -> str:
    today = _now().date()
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    return friday.isoformat()


def _recalculate_tail_ma(weekly_data: list, window: int) -> Optional[float]:
    closes = []
    for row in weekly_data[-window:]:
        try:
            closes.append(float(row.get("close")))
        except (TypeError, ValueError):
            continue
    if not closes:
        return None
    return round(sum(closes) / len(closes), 2)


def _sync_current_week_quote(entry: Dict[str, Any], price_val: float) -> None:
    weekly_data = entry.get("weekly_data")
    if not isinstance(weekly_data, list):
        return

    week_date = _current_week_friday()
    current_row = None
    if weekly_data and isinstance(weekly_data[-1], dict) and weekly_data[-1].get("date") == week_date:
        current_row = weekly_data[-1]
    elif weekly_data:
        prev_row = weekly_data[-1]
        if isinstance(prev_row, dict):
            current_row = {
                "date": week_date,
                "open": price_val,
                "high": price_val,
                "low": price_val,
                "close": price_val,
                "volume": 0,
                "ma10": None,
                "ma20": None,
                "ma50": None,
            }
            weekly_data.append(current_row)
            if len(weekly_data) > 60:
                del weekly_data[:-60]

    if current_row is None:
        return

    current_row["close"] = round(price_val, 2)
    try:
        current_row["high"] = round(max(float(current_row.get("high") or price_val), price_val), 2)
    except (TypeError, ValueError):
        current_row["high"] = round(price_val, 2)
    try:
        current_row["low"] = round(min(float(current_row.get("low") or price_val), price_val), 2)
    except (TypeError, ValueError):
        current_row["low"] = round(price_val, 2)
    current_row.setdefault("open", round(price_val, 2))
    current_row["ma10"] = _recalculate_tail_ma(weekly_data, 10)
    current_row["ma20"] = _recalculate_tail_ma(weekly_data, 20)
    current_row["ma50"] = _recalculate_tail_ma(weekly_data, 50)
    entry["ma10"] = current_row["ma10"]
    entry["ma20"] = current_row["ma20"]
    entry["ma50"] = current_row["ma50"]


def refresh_all_market_caches() -> Dict[str, Any]:
    """Refresh frequently changing market dashboard payloads. Failures are caught individually —
    previous valid cache remains intact for each failed entry."""
    results: Dict[str, Any] = {"refreshed_at": _now().isoformat(), "items": {}}
    for cache_key in FREQUENT_MARKET_CACHE_KEYS:
        try:
            if cache_key == "trend":
                refresh_trend_realtime_quotes()
            else:
                refresh_market_cache(cache_key)
            results["items"][cache_key] = {
                "status": "success",
                "refreshed_at": _now().isoformat(),
            }
        except Exception as exc:
            logger.error("Market cache refresh failed: %s, key=%s — old cache preserved", exc, cache_key)
            results["items"][cache_key] = {"status": "failed", "error": str(exc)}
    return results


def refresh_trend_realtime_quotes() -> Dict[str, Any]:
    """Refresh only the 12 dashboard quote fields in market_cache.trend."""
    from data_provider.base import DataFetcherManager

    payload = _read_cache("trend")
    if payload is None:
        refresh_market_cache("trend")
        payload = _read_cache("trend")
    if payload is None:
        raise ValueError("No cached trend payload available")

    data = payload.setdefault("data", {})
    manager = DataFetcherManager()
    refreshed = 0
    failed = 0
    failures = []

    for item in MARKET_INDICES:
        key = item["key"]
        code = item["code"]
        try:
            quote = manager.get_realtime_quote(code, log_final_failure=False)
            price = getattr(quote, "price", None) if quote is not None else None
            price_val = float(price)
            if price_val <= 0:
                raise ValueError("empty realtime price")
            change_pct = getattr(quote, "change_pct", None)
            change_pct_val = float(change_pct) if change_pct is not None else None
            entry = data.setdefault(key, {"label": item["label"], "code": code})
            entry["close"] = price_val
            entry["daily_close"] = round(price_val, 2)
            entry["daily_pct_chg"] = round(change_pct_val, 2) if change_pct_val is not None else None
            _sync_current_week_quote(entry, price_val)
            refreshed += 1
        except Exception as exc:
            failed += 1
            failures.append(f"{code}: {exc}")

    payload["snapshot_date"] = _now().strftime("%Y-%m-%d")
    payload.pop("_cache", None)
    _write_cache("trend", payload)
    return {"refreshed": refreshed, "failed": failed, "failures": failures[:20]}
