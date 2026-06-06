# -*- coding: utf-8 -*-
"""
Market tools — wraps DataFetcherManager market-level methods as agent tools.

Tools:
- get_market_indices: major market index data
- get_sector_rankings: sector performance rankings
- get_a_share_market_context: compact A-share market dashboard context
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
        compact.append({
            "key": key,
            "label": item.get("label"),
            "code": item.get("code"),
            "close": item.get("daily_close") or item.get("close"),
            "daily_pct_chg": item.get("daily_pct_chg"),
            "ma10": item.get("ma10"),
            "ma20": item.get("ma20"),
            "ma50": item.get("ma50"),
            "trend_label": item.get("trend_label") or item.get("trend"),
            "support_distance_pct": item.get("support_distance_pct"),
            "volatility_label": item.get("volatility_label"),
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


ALL_MARKET_TOOLS = [
    get_market_indices_tool,
    get_sector_rankings_tool,
    get_a_share_market_context_tool,
]
