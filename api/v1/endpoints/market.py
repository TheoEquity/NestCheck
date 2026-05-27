# -*- coding: utf-8 -*-
"""Market indices and quotes endpoint."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from src.storage import get_db, MarketQuote

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
