# -*- coding: utf-8 -*-
"""Watchlist endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.watchlist import (
    WatchlistDeleteResponse,
    WatchlistItem,
    WatchlistItemCreateRequest,
    WatchlistItemListResponse,
    WatchlistItemUpdateRequest,
    WatchlistRelatedAlertsResponse,
)
from src.repositories.watchlist_repo import WatchlistConflictError
from src.services.watchlist_service import WatchlistNotFoundError, WatchlistService

logger = logging.getLogger(__name__)
router = APIRouter()


def _bad_request(exc: Exception, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": "validation_error", "message": str(exc)})


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail={"error": "not_found", "message": str(exc)})


def _internal_error(message: str, exc: Exception) -> HTTPException:
    logger.error("%s: %s", message, exc, exc_info=True)
    return HTTPException(status_code=500, detail={"error": "internal_error", "message": f"{message}: {str(exc)}"})


@router.get("/items", response_model=WatchlistItemListResponse, responses={500: {"model": ErrorResponse}})
def list_items(
    asset_category: Optional[str] = Query(None),
    watch_enabled: Optional[bool] = Query(None),
) -> WatchlistItemListResponse:
    service = WatchlistService()
    try:
        return WatchlistItemListResponse(**service.list_items(asset_category=asset_category, watch_enabled=watch_enabled))
    except Exception as exc:
        raise _internal_error("List watchlist items failed", exc)


@router.post("/items", response_model=WatchlistItem, responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def create_item(request: WatchlistItemCreateRequest) -> WatchlistItem:
    service = WatchlistService()
    try:
        return WatchlistItem(**service.create_item(request.model_dump()))
    except WatchlistConflictError as exc:
        raise _bad_request(exc, status_code=409)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create watchlist item failed", exc)


@router.get("/items/{item_id}", response_model=WatchlistItem, responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def get_item(item_id: int) -> WatchlistItem:
    service = WatchlistService()
    try:
        return WatchlistItem(**service.get_item(item_id))
    except WatchlistNotFoundError as exc:
        raise _not_found(exc)
    except Exception as exc:
        raise _internal_error("Get watchlist item failed", exc)


@router.patch("/items/{item_id}", response_model=WatchlistItem, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def update_item(item_id: int, request: WatchlistItemUpdateRequest) -> WatchlistItem:
    service = WatchlistService()
    try:
        return WatchlistItem(**service.update_item(item_id, request.model_dump(exclude_unset=True)))
    except WatchlistNotFoundError as exc:
        raise _not_found(exc)
    except WatchlistConflictError as exc:
        raise _bad_request(exc, status_code=409)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Update watchlist item failed", exc)


@router.delete("/items/{item_id}", response_model=WatchlistDeleteResponse, responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def delete_item(item_id: int) -> WatchlistDeleteResponse:
    service = WatchlistService()
    try:
        deleted = service.delete_item(item_id)
        if not deleted:
            raise WatchlistNotFoundError(f"关注标的不存在: {item_id}")
        return WatchlistDeleteResponse(deleted=1)
    except WatchlistNotFoundError as exc:
        raise _not_found(exc)
    except Exception as exc:
        raise _internal_error("Delete watchlist item failed", exc)


@router.get("/items/{item_id}/alerts", response_model=WatchlistRelatedAlertsResponse, responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}})
def get_item_alerts(item_id: int) -> WatchlistRelatedAlertsResponse:
    service = WatchlistService()
    try:
        return WatchlistRelatedAlertsResponse(**service.related_alerts(item_id))
    except WatchlistNotFoundError as exc:
        raise _not_found(exc)
    except Exception as exc:
        raise _internal_error("Get watchlist related alerts failed", exc)
