# -*- coding: utf-8 -*-
"""
Market tools — wraps DataFetcherManager market-level methods as agent tools.

Tools:
- get_market_indices: major market index data
- get_sector_rankings: sector performance rankings
- get_a_share_market_context: compact A-share market dashboard context
- get_china_bond_market_context: compact China bond market context
"""

import logging
from typing import Any

from src.agent.tools.registry import ToolParameter, ToolDefinition

logger = logging.getLogger(__name__)


def _safe_slice(value: Any, limit: int = 5) -> list:
    if isinstance(value, list):
        return value[:limit]
    return []


def _compact_trend(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload, dict) else {}
    if not isinstance(data, dict):
        return {}
    compact = []
    for key, item in data.items():
        if not isinstance(item, dict):
            continue
        environment = item.get("environment") if isinstance(item.get("environment"), dict) else {}
        weekly_data = item.get("weekly_data") if isinstance(item.get("weekly_data"), list) else []
        compact.append({
            "key": key,
            "label": item.get("label"),
            "code": item.get("code"),
            "close": item.get("daily_close") or item.get("close"),
            "daily_pct_chg": item.get("daily_pct_chg"),
            "ma10": item.get("ma10"),
            "ma20": item.get("ma20"),
            "ma50": item.get("ma50"),
            "trend_label": environment.get("label"),
            "trend": environment.get("trend"),
            "volatility": environment.get("volatility"),
            "support_distance_pct": environment.get("support_pct"),
            "support_status": environment.get("support_status"),
            "color": environment.get("color"),
            "recent_weeks": weekly_data[-4:],
        })
    return {
        "snapshot_date": payload.get("snapshot_date"),
        "indices": compact[:12],
        "cache": payload.get("_cache", {}),
    }


def _compact_sector_dashboard(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    return {
        "snapshot_date": payload.get("snapshot_date"),
        "benchmark": payload.get("benchmark"),
        "top_gainers": _safe_slice(payload.get("top_gainers"), 5),
        "top_losers": _safe_slice(payload.get("top_losers"), 5),
        "monthly_rankings": _safe_slice(payload.get("monthly_rankings"), 10),
    }


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _load_bond_yield_series(code: str, days: int = 90) -> dict:
    from src.storage import get_db

    df = get_db().get_daily_history_df(code, days=days)
    if df is None or df.empty:
        return {"code": code, "status": "missing", "history": []}

    df = df.sort_values("date")
    history = []
    for _, row in df.tail(20).iterrows():
        date_value = row.get("date")
        history.append({
            "date": date_value.isoformat() if hasattr(date_value, "isoformat") else str(date_value),
            "yield": _round_or_none(_safe_float(row.get("close")), 4),
        })

    latest = _safe_float(df.iloc[-1].get("close"))
    prev_week = _safe_float(df.iloc[-6].get("close")) if len(df) >= 6 else None
    prev_month = _safe_float(df.iloc[-21].get("close")) if len(df) >= 21 else None
    latest_date = df.iloc[-1].get("date")

    return {
        "code": code,
        "status": "ok",
        "date": latest_date.isoformat() if hasattr(latest_date, "isoformat") else str(latest_date),
        "yield": _round_or_none(latest, 4),
        "week_change_bp": _round_or_none((latest - prev_week) * 100, 2) if latest is not None and prev_week is not None else None,
        "month_change_bp": _round_or_none((latest - prev_month) * 100, 2) if latest is not None and prev_month is not None else None,
        "history": history,
    }


def _compact_bond_related_risk(value: dict) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        "bond_spread": value.get("bond_spread") or value.get("bondSpread"),
        "chinese_vix": value.get("chinese_vix"),
        "us_vix": value.get("us_vix"),
        "fx": value.get("fx"),
        "cache": value.get("_cache", {}),
    }


def _compact_bond_related_correlation(value: dict) -> dict:
    if not isinstance(value, dict):
        return {}
    labels = value.get("labels") if isinstance(value.get("labels"), list) else []
    matrix = value.get("matrix") if isinstance(value.get("matrix"), list) else []
    bond_index = next((idx for idx, label in enumerate(labels) if "债券" in str(label)), None)
    if bond_index is None:
        return {"labels": _safe_slice(labels, 12), "matrix": _safe_slice(matrix, 12), "cache": value.get("_cache", {})}
    return {
        "labels": labels,
        "bond_row": matrix[bond_index] if bond_index < len(matrix) else [],
        "cache": value.get("_cache", {}),
    }


def _get_fetcher_manager():
    """Lazy import to avoid circular deps."""
    from data_provider import DataFetcherManager
    return DataFetcherManager()


# ============================================================
# get_market_indices
# ============================================================

def _handle_get_market_indices(region: str = "cn") -> dict:
    """Get major market indices."""
    manager = _get_fetcher_manager()
    indices = manager.get_main_indices(region=region)

    if not indices:
        return {"error": f"No market index data available for region '{region}'"}

    return {
        "region": region,
        "indices_count": len(indices),
        "indices": indices,
    }


get_market_indices_tool = ToolDefinition(
    name="get_market_indices",
    description="Get major market indices (e.g., Shanghai Composite, Shenzhen Component, "
                "CSI 300 for China; S&P 500, Nasdaq, Dow for US). Provides market overview.",
    parameters=[
        ToolParameter(
            name="region",
            type="string",
            description="Market region: 'cn' for China A-shares, 'hk' for Hong Kong, 'us' for US stocks (default: 'cn')",
            required=False,
            default="cn",
            enum=["cn", "hk", "us"],
        ),
    ],
    handler=_handle_get_market_indices,
    category="market",
)


# ============================================================
# get_sector_rankings
# ============================================================

def _handle_get_sector_rankings(top_n: int = 10) -> dict:
    """Get sector performance rankings."""
    manager = _get_fetcher_manager()
    result = manager.get_sector_rankings(n=top_n)

    if result is None:
        return {"error": "No sector ranking data available"}

    # get_sector_rankings returns Tuple[List[Dict], List[Dict]]
    # (top_sectors, bottom_sectors)
    if isinstance(result, tuple) and len(result) == 2:
        top_sectors, bottom_sectors = result
        return {
            "top_sectors": top_sectors,
            "bottom_sectors": bottom_sectors,
        }
    elif isinstance(result, list):
        return {"sectors": result}
    else:
        return {"data": str(result)}


get_sector_rankings_tool = ToolDefinition(
    name="get_sector_rankings",
    description="Get sector/industry performance rankings. Returns top N and bottom N "
                "sectors by daily change percentage. Useful for sector rotation analysis.",
    parameters=[
        ToolParameter(
            name="top_n",
            type="integer",
            description="Number of top/bottom sectors to return (default: 10)",
            required=False,
            default=10,
        ),
    ],
    handler=_handle_get_sector_rankings,
    category="market",
)


# ============================================================
# get_a_share_market_context
# ============================================================

def _handle_get_a_share_market_context() -> dict:
    """Get compact A-share market context from cached dashboard services."""
    from src.services.market_cache_service import get_market_cache_payload
    from src.services.sector_etf_service import get_sector_etf_dashboard

    payload: dict[str, Any] = {"region": "cn", "market": "A股"}
    for cache_key in ("trend", "risk", "radar", "correlation", "equity_ratio"):
        try:
            value = get_market_cache_payload(cache_key, force_refresh=False)
            if cache_key == "trend":
                payload[cache_key] = _compact_trend(value)
            elif cache_key == "correlation":
                payload[cache_key] = {
                    "labels": _safe_slice(value.get("labels"), 12),
                    "matrix": _safe_slice(value.get("matrix"), 12),
                    "cache": value.get("_cache", {}),
                }
            else:
                payload[cache_key] = value
        except Exception as exc:
            payload[cache_key] = {"status": "failed", "error": str(exc)}

    try:
        payload["sector_etf"] = _compact_sector_dashboard(get_sector_etf_dashboard(force_refresh=False))
    except Exception as exc:
        payload["sector_etf"] = {"status": "failed", "error": str(exc)}
    return payload


get_a_share_market_context_tool = ToolDefinition(
    name="get_a_share_market_context",
    description=(
        "Get compact China A-share market context, including broad index trends, "
        "risk radar, correlation, equity ratio and sector ETF temperature."
    ),
    parameters=[],
    handler=_handle_get_a_share_market_context,
    category="market",
)


# ============================================================
# get_china_bond_market_context
# ============================================================

def _handle_get_china_bond_market_context() -> dict:
    """Get compact China bond market context from local yield history and market caches."""
    from src.services.market_cache_service import get_market_cache_payload

    cn_10y = _load_bond_yield_series("bond_cn_10y")
    us_10y = _load_bond_yield_series("bond_us_10y")
    cn_yield = _safe_float(cn_10y.get("yield"))
    us_yield = _safe_float(us_10y.get("yield"))
    spread = us_yield - cn_yield if cn_yield is not None and us_yield is not None else None

    payload: dict[str, Any] = {
        "region": "cn",
        "market": "中国债市",
        "instruments": {
            "cn_10y": cn_10y,
            "us_10y": us_10y,
        },
        "cn_us_10y_spread": {
            "value_pct": _round_or_none(spread, 4),
            "value_bp": _round_or_none(spread * 100, 2) if spread is not None else None,
            "description": "美国10年期国债收益率 - 中国10年期国债收益率",
        },
    }

    try:
        payload["risk"] = _compact_bond_related_risk(get_market_cache_payload("risk", force_refresh=False))
    except Exception as exc:
        payload["risk"] = {"status": "failed", "error": str(exc)}

    try:
        payload["correlation"] = _compact_bond_related_correlation(get_market_cache_payload("correlation", force_refresh=False))
    except Exception as exc:
        payload["correlation"] = {"status": "failed", "error": str(exc)}

    try:
        equity_ratio = get_market_cache_payload("equity_ratio", force_refresh=False)
        payload["equity_ratio"] = {
            "equity_ratio": equity_ratio.get("equity_ratio"),
            "planned_equity_ratio": equity_ratio.get("planned_equity_ratio"),
            "cache": equity_ratio.get("_cache", {}),
        }
    except Exception as exc:
        payload["equity_ratio"] = {"status": "failed", "error": str(exc)}

    return payload


get_china_bond_market_context_tool = ToolDefinition(
    name="get_china_bond_market_context",
    description=(
        "Get compact China bond market context, including China/US 10Y yields, "
        "spread, recent basis-point changes, risk cache and stock-bond correlation."
    ),
    parameters=[],
    handler=_handle_get_china_bond_market_context,
    category="market",
)


ALL_MARKET_TOOLS = [
    get_market_indices_tool,
    get_sector_rankings_tool,
    get_a_share_market_context_tool,
    get_china_bond_market_context_tool,
]
