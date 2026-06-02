# -*- coding: utf-8 -*-
"""Watchlist API schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WatchlistItemCreateRequest(BaseModel):
    market: str = Field("cn", min_length=1, max_length=8)
    symbol: str = Field(..., min_length=1, max_length=32)
    name: Optional[str] = Field(None, max_length=100)
    currency: str = Field("CNY", min_length=3, max_length=8)
    asset_category: str = Field("stock", min_length=1, max_length=32)
    asset_subcategory: Optional[str] = Field(None, max_length=64)
    asset_risk_class: Optional[str] = Field(None, max_length=8)
    watch_priority: str = Field("medium", max_length=16)
    watch_tags: List[str] = Field(default_factory=list)
    watch_reason: Optional[str] = None
    watch_enabled: bool = True
    analysis_enabled: bool = True
    analysis_frequency: str = Field("daily", max_length=16)
    alert_enabled: bool = True
    source: str = Field("manual", max_length=32)
    notes: Optional[str] = None


class WatchlistItemUpdateRequest(BaseModel):
    market: Optional[str] = Field(None, min_length=1, max_length=8)
    symbol: Optional[str] = Field(None, min_length=1, max_length=32)
    name: Optional[str] = Field(None, max_length=100)
    currency: Optional[str] = Field(None, min_length=3, max_length=8)
    asset_category: Optional[str] = Field(None, min_length=1, max_length=32)
    asset_subcategory: Optional[str] = Field(None, max_length=64)
    asset_risk_class: Optional[str] = Field(None, max_length=8)
    watch_priority: Optional[str] = Field(None, max_length=16)
    watch_tags: Optional[List[str]] = None
    watch_reason: Optional[str] = None
    watch_enabled: Optional[bool] = None
    analysis_enabled: Optional[bool] = None
    analysis_frequency: Optional[str] = Field(None, max_length=16)
    alert_enabled: Optional[bool] = None
    source: Optional[str] = Field(None, max_length=32)
    notes: Optional[str] = None


class WatchlistItem(BaseModel):
    id: int
    market: str
    symbol: str
    name: Optional[str] = None
    currency: str
    asset_category: str
    asset_subcategory: Optional[str] = None
    asset_risk_class: Optional[str] = None
    watch_priority: str
    watch_tags: List[str] = Field(default_factory=list)
    watch_reason: Optional[str] = None
    watch_enabled: bool
    analysis_enabled: bool
    analysis_frequency: str
    alert_enabled: bool
    source: str
    notes: Optional[str] = None
    alert_rule_count: int = 0
    alert_trigger_count: int = 0
    latest_alert_triggered_at: Optional[str] = None
    latest_price: Optional[float] = None
    latest_change_pct: Optional[float] = None
    latest_analysis_id: Optional[int] = None
    latest_analysis_at: Optional[str] = None
    latest_analysis_summary: Optional[str] = None
    latest_analysis_content: Optional[str] = None
    latest_operation_advice: Optional[str] = None
    latest_trend_prediction: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WatchlistMarketReview(BaseModel):
    latest_analysis_id: Optional[int] = None
    latest_analysis_at: Optional[str] = None
    latest_analysis_summary: Optional[str] = None
    latest_analysis_sections: Dict[str, str] = Field(default_factory=dict)
    latest_operation_advice: Optional[str] = None
    latest_trend_prediction: Optional[str] = None


class WatchlistItemListResponse(BaseModel):
    items: List[WatchlistItem] = Field(default_factory=list)
    total: int
    market_review: Optional[WatchlistMarketReview] = None


class WatchlistDeleteResponse(BaseModel):
    deleted: int


class WatchlistRelatedAlertsResponse(BaseModel):
    rules: List[Dict[str, Any]] = Field(default_factory=list)
    triggers: List[Dict[str, Any]] = Field(default_factory=list)
