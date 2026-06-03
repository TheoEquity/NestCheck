# -*- coding: utf-8 -*-
"""Market indices and quotes endpoint."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from src.storage import get_db, MarketQuote
from src.services.market_cache_service import get_market_cache_payload, refresh_all_market_caches, MARKET_CACHE_BUILDERS

logger = logging.getLogger(__name__)

router = APIRouter()


def _internal_error(message: str, exc: Exception) -> HTTPException:
    logger.error(f"{message}: {exc}", exc_info=True)
    return HTTPException(
        status_code=500,
        detail={"error": "internal_error", "message": f"{message}: {str(exc)}"},
    )


@router.get(
    "/indices",
    response_model=list,
    summary="Get latest market index quotes",
)
def get_market_indices() -> list:
    try:
        db = get_db()
        with db.get_session() as s:
            rows = s.query(MarketQuote).filter_by(
                category="index", is_stale=False
            ).order_by(MarketQuote.updated_at.desc()).all()

            return [
                {
                    "code": r.code,
                    "name": r.name,
                    "latest_price": r.latest_price,
                    "pct_change": r.pct_change,
                    "volume": r.volume,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]
    except Exception as exc:
        raise _internal_error("Get market indices failed", exc)


@router.get(
    "/risk",
    response_model=dict,
    summary="Get market risk indicators",
)
def get_market_risk() -> dict:
    try:
        return get_market_cache_payload("risk")
    except Exception as exc:
        raise _internal_error("Get market risk failed", exc)


@router.get(
    "/snapshot",
    response_model=dict,
    summary="Get real-time market index snapshot",
)
def get_market_snapshot(force_refresh: bool = Query(False, alias="force_refresh")) -> dict:
    try:
        from src.services.market_snapshot_service import get_market_snapshot
        return get_market_snapshot(force_refresh=force_refresh)
    except Exception as exc:
        raise _internal_error("Get market snapshot failed", exc)


@router.get(
    "/trend",
    response_model=dict,
    summary="Get market weekly trends with environment labels",
)
def get_market_trend() -> dict:
    try:
        return get_market_cache_payload("trend")
    except Exception as exc:
        raise _internal_error("Get market trend failed", exc)


@router.get(
    "/sector-etfs",
    response_model=dict,
    summary="Get sector ETF hard-indicator rankings",
)
def get_sector_etfs(force_refresh: bool = Query(False, alias="force_refresh")) -> dict:
    try:
        from src.services.sector_etf_service import get_sector_etf_dashboard
        return get_sector_etf_dashboard(force_refresh=force_refresh)
    except Exception as exc:
        raise _internal_error("Get sector ETFs failed", exc)


@router.get(
    "/sector-etfs/configs",
    response_model=list,
    summary="Get fixed sector ETF representative configuration",
)
def get_sector_etf_configs() -> list:
    try:
        from src.services.sector_etf_service import list_sector_etf_configs
        return list_sector_etf_configs()
    except Exception as exc:
        raise _internal_error("Get sector ETF configs failed", exc)


@router.patch(
    "/sector-etfs/configs/{sector}",
    response_model=dict,
    summary="Update representative ETF for a fixed sector",
)
def update_sector_etf_config(sector: str, payload: Dict[str, Any]) -> dict:
    try:
        from src.services.sector_etf_service import update_sector_etf_config as _update
        return _update(sector, payload)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"行业不存在：{sector}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise _internal_error("Update sector ETF config failed", exc)


@router.get(
    "/seasonality",
    response_model=dict,
    summary="Get monthly seasonality statistics for CSI 300",
)
def get_market_seasonality() -> dict:
    try:
        return get_market_cache_payload("seasonality")
    except Exception as exc:
        raise _internal_error("Get monthly seasonality failed", exc)


@router.get(
    "/radar",
    response_model=dict,
    summary="Get 6-dimension risk radar scores",
)
def get_risk_radar() -> dict:
    try:
        return get_market_cache_payload("radar")
    except Exception as exc:
        raise _internal_error("Get risk radar failed", exc)


@router.get(
    "/correlation",
    response_model=dict,
    summary="Get 60-day rolling asset correlation matrix",
)
def get_correlation_matrix() -> dict:
    try:
        return get_market_cache_payload("correlation")
    except Exception as exc:
        raise _internal_error("Get correlation matrix failed", exc)


@router.post(
    "/refresh",
    response_model=dict,
    summary="Refresh cached market dashboard payloads",
)
def refresh_market_dashboard() -> dict:
    try:
        return refresh_all_market_caches()
    except Exception as exc:
        raise _internal_error("Refresh market dashboard failed", exc)


@router.get(
    "/equity-ratio",
    response_model=dict,
    summary="Get current portfolio equity ratio vs total assets (CNY)",
)
def get_equity_ratio() -> dict:
    try:
        return get_market_cache_payload("equity_ratio")
    except Exception as exc:
        raise _internal_error("Get equity ratio failed", exc)
