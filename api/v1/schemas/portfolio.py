# -*- coding: utf-8 -*-
"""Portfolio API schemas."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class PortfolioAccountCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    broker: Optional[str] = Field(None, max_length=64)
    market: Literal["cn", "hk", "us"] = "cn"
    base_currency: str = Field("CNY", min_length=3, max_length=8)
    owner_id: Optional[str] = Field(None, max_length=64)


class PortfolioAccountUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    broker: Optional[str] = Field(None, max_length=64)
    market: Optional[Literal["cn", "hk", "us"]] = None
    base_currency: Optional[str] = Field(None, min_length=3, max_length=8)
    owner_id: Optional[str] = Field(None, max_length=64)
    is_active: Optional[bool] = None


class PortfolioAccountItem(BaseModel):
    id: int
    owner_id: Optional[str] = None
    name: str
    broker: Optional[str] = None
    market: str
    base_currency: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PortfolioAccountListResponse(BaseModel):
    accounts: List[PortfolioAccountItem] = Field(default_factory=list)


class PortfolioTradeCreateRequest(BaseModel):
    account_id: int
    asset_category: Optional[str] = Field(None, max_length=32)
    asset_subcategory: Optional[str] = Field(None, max_length=64)
    asset_risk_class: Optional[str] = Field(None, max_length=8)
    symbol: str = Field(..., min_length=1, max_length=16)
    name: Optional[str] = Field(None, max_length=64)
    trade_date: date
    available_date: Optional[date] = None
    side: Literal["buy", "sell"]
    quantity: float = Field(..., gt=0)
    price: float = Field(..., gt=0)
    fee: float = Field(0.0, ge=0)
    tax: float = Field(0.0, ge=0)
    market: Optional[Literal["cn", "hk", "us"]] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=8)
    trade_uid: Optional[str] = Field(None, max_length=128)
    note: Optional[str] = Field(None, max_length=255)


class PortfolioCashLedgerCreateRequest(BaseModel):
    account_id: int
    asset_category: Optional[str] = Field(None, max_length=32)
    asset_subcategory: Optional[str] = Field(None, max_length=64)
    asset_risk_class: Optional[str] = Field(None, max_length=8)
    event_date: date
    direction: Literal["in", "out"]
    amount: float = Field(..., gt=0)
    currency: Optional[str] = Field(None, min_length=3, max_length=8)
    note: Optional[str] = Field(None, max_length=255)


class PortfolioCorporateActionCreateRequest(BaseModel):
    account_id: int
    symbol: str = Field(..., min_length=1, max_length=16)
    asset_category: Optional[str] = Field(None, max_length=32)
    asset_subcategory: Optional[str] = Field(None, max_length=64)
    effective_date: date
    action_type: Literal["cash_dividend", "stock_split"] = "cash_dividend"
    market: Optional[Literal["cn", "hk", "us"]] = None
    currency: Optional[str] = Field(None, min_length=3, max_length=8)
    dividend_amount: Optional[float] = Field(None, gt=0)
    cash_dividend_per_share: Optional[float] = Field(None, gt=0, exclude=True)
    split_ratio: Optional[float] = Field(None, gt=0)
    note: Optional[str] = Field(None, max_length=255)

    @model_validator(mode="after")
    def normalize_dividend_amount(self) -> "PortfolioCorporateActionCreateRequest":
        if self.action_type != "cash_dividend":
            return self
        if self.dividend_amount is None:
            self.dividend_amount = self.cash_dividend_per_share
        if self.dividend_amount is None or self.dividend_amount <= 0:
            raise ValueError("dividend_amount must be > 0 for cash_dividend")
        return self


class PortfolioEventCreatedResponse(BaseModel):
    id: int


class PortfolioDeleteResponse(BaseModel):
    deleted: int


class PortfolioTradeListItem(BaseModel):
    id: int
    account_id: int
    trade_uid: Optional[str] = None
    asset_category: Optional[str] = None
    asset_subcategory: Optional[str] = None
    asset_risk_class: Optional[str] = None
    symbol: str
    name: Optional[str] = None
    market: str
    currency: str
    trade_date: str
    available_date: Optional[str] = None
    open_watch_enabled: bool = True
    side: str
    quantity: float
    price: float
    fee: float
    tax: float
    realized_pnl: float = 0.0
    note: Optional[str] = None
    created_at: Optional[str] = None


class PortfolioTradeListResponse(BaseModel):
    items: List[PortfolioTradeListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class PortfolioCashLedgerListItem(BaseModel):
    id: int
    account_id: int
    asset_category: Optional[str] = None
    asset_subcategory: Optional[str] = None
    asset_risk_class: Optional[str] = None
    event_date: str
    direction: str
    amount: float
    currency: str
    note: Optional[str] = None
    created_at: Optional[str] = None


class PortfolioCashLedgerListResponse(BaseModel):
    items: List[PortfolioCashLedgerListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class PortfolioCorporateActionListItem(BaseModel):
    id: int
    account_id: int
    symbol: str
    market: str
    currency: str
    asset_category: Optional[str] = None
    asset_subcategory: Optional[str] = None
    effective_date: str
    action_type: str
    dividend_amount: Optional[float] = None
    split_ratio: Optional[float] = None
    realized_pnl: float = 0.0
    note: Optional[str] = None
    created_at: Optional[str] = None


class PortfolioCorporateActionListResponse(BaseModel):
    items: List[PortfolioCorporateActionListItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class PortfolioPositionItem(BaseModel):
    id: int
    symbol: str
    market: str
    currency: str
    quantity: float
    avg_cost: float
    total_cost: float
    last_price: float
    price_change_pct: Optional[float] = None
    market_value_base: float
    unrealized_pnl_base: float
    realized_pnl_base: float = 0.0
    unrealized_pnl_pct: Optional[float] = None
    asset_category: Optional[str] = None
    asset_subcategory: Optional[str] = None
    asset_risk_class: Optional[str] = None
    valuation_currency: str
    price_source: str = "unknown"
    price_provider: Optional[str] = None
    price_date: Optional[str] = None
    price_stale: bool = False
    price_available: bool = True
    name: Optional[str] = None
    available_date: Optional[str] = None
    open_watch_enabled: bool = True


class PortfolioPositionRecordItem(PortfolioPositionItem):
    account_id: int
    account_name: str
    owner_id: Optional[str] = None
    base_currency: str
    cost_method: str
    updated_at: Optional[str] = None


class PortfolioPositionListResponse(BaseModel):
    items: List[PortfolioPositionRecordItem] = Field(default_factory=list)
    total: int


class PortfolioCashByCurrencyItem(BaseModel):
    currency: str
    amount: float
    amount_base: float


class PortfolioFxRateItem(BaseModel):
    pair: str
    rate: float
    is_stale: bool = False


class PortfolioAccountSnapshot(BaseModel):
    account_id: int
    account_name: str
    owner_id: Optional[str] = None
    broker: Optional[str] = None
    market: str
    base_currency: str
    as_of: str
    cost_method: str
    total_cash: float
    total_market_value: float
    total_equity: float
    realized_pnl: float
    unrealized_pnl: float
    fee_total: float
    tax_total: float
    fx_stale: bool
    cash_by_currency: List[PortfolioCashByCurrencyItem] = Field(default_factory=list)
    fx_rates: List[PortfolioFxRateItem] = Field(default_factory=list)
    positions: List[PortfolioPositionItem] = Field(default_factory=list)


class PortfolioSnapshotResponse(BaseModel):
    as_of: str
    cost_method: str
    currency: str
    account_count: int
    total_cash: float
    total_market_value: float
    total_equity: float
    realized_pnl: float
    unrealized_pnl: float
    fee_total: float
    tax_total: float
    fx_stale: bool
    accounts: List[PortfolioAccountSnapshot] = Field(default_factory=list)


class PortfolioImportTradeItem(BaseModel):
    trade_date: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    fee: float
    tax: float
    trade_uid: Optional[str] = None
    dedup_hash: str
    currency: Optional[str] = None


class PortfolioImportParseResponse(BaseModel):
    broker: str
    record_count: int
    skipped_count: int
    error_count: int
    records: List[PortfolioImportTradeItem] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


class PortfolioImportCommitResponse(BaseModel):
    account_id: int
    record_count: int
    inserted_count: int
    duplicate_count: int
    failed_count: int
    dry_run: bool
    errors: List[str] = Field(default_factory=list)


class PortfolioImportBrokerItem(BaseModel):
    broker: str
    aliases: List[str] = Field(default_factory=list)
    display_name: Optional[str] = None


class PortfolioImportBrokerListResponse(BaseModel):
    brokers: List[PortfolioImportBrokerItem] = Field(default_factory=list)


class PortfolioFxRefreshResponse(BaseModel):
    as_of: str
    account_count: int
    refresh_enabled: bool
    disabled_reason: Optional[str] = None
    pair_count: int
    updated_count: int
    stale_count: int
    error_count: int


class PortfolioLatestFxRateItem(BaseModel):
    pair: str
    from_currency: str
    to_currency: str
    rate: float
    rate_date: str
    source: str
    is_stale: bool = False


class PortfolioLatestFxRateListResponse(BaseModel):
    as_of: str
    to_currency: str
    items: List[PortfolioLatestFxRateItem] = Field(default_factory=list)


class PortfolioRiskResponse(BaseModel):
    as_of: str
    account_id: Optional[int] = None
    cost_method: str
    currency: str
    thresholds: Dict[str, Any] = Field(default_factory=dict)
    concentration: Dict[str, Any] = Field(default_factory=dict)
    single_name_concentration: Dict[str, Any] = Field(default_factory=dict)
    drawdown: Dict[str, Any] = Field(default_factory=dict)
    stop_loss: Dict[str, Any] = Field(default_factory=dict)


class PortfolioPositionAdjustRequest(BaseModel):
    quantity: Optional[float] = None
    avg_cost: Optional[float] = None
    last_price: Optional[float] = None


class PortfolioPositionAdjustResponse(BaseModel):
    id: int
    symbol: str
    market: str
    currency: str
    quantity: float
    avg_cost: float
    last_price: float
    total_cost: float
    updated_at: Optional[str] = None


class PortfolioInitializeAssetRow(BaseModel):
    asset_category: str = Field(..., max_length=32)
    asset_subcategory: Optional[str] = Field(None, max_length=64)
    asset_risk_class: Optional[str] = Field(None, max_length=8)
    symbol: str = Field(..., min_length=1, max_length=16)
    name: Optional[str] = Field(None, max_length=64)
    market: Literal["cn", "hk", "us"]
    quantity: float = Field(..., gt=0)
    avg_cost: float = Field(..., gt=0)
    last_price: Optional[float] = Field(None, ge=0)
    currency: str = Field(..., min_length=3, max_length=8)
    note: Optional[str] = Field(None, max_length=255)


class PortfolioInitializeCashRow(BaseModel):
    asset_category: str = Field("cash", max_length=32)
    asset_risk_class: Optional[str] = Field(None, max_length=8)
    name: Optional[str] = Field(None, max_length=64)
    amount: float = Field(..., gt=0)
    currency: str = Field(..., min_length=3, max_length=8)
    note: Optional[str] = Field(None, max_length=255)


class PortfolioInitializeRequest(BaseModel):
    account_id: int
    init_date: date
    assets: List[PortfolioInitializeAssetRow] = Field(default_factory=list)
    cash_items: List[PortfolioInitializeCashRow] = Field(default_factory=list)


class PortfolioInitializeResponse(BaseModel):
    account_id: int
    asset_count: int
    cash_count: int
    cleared_trade_count: int
    cleared_cash_count: int
    cleared_corporate_count: int


class AssetRiskDefinitionItem(BaseModel):
    """Asset risk class definition item (R1-R5)."""
    asset_risk_class: str = Field(..., max_length=8, description="Risk class code (R1-R5)")
    name: str = Field(..., max_length=64, description="Risk class name")
    expected_return: Optional[float] = Field(None, ge=0, le=1, description="Expected annual return (0.0-1.0)")
    volatility: Optional[float] = Field(None, ge=0, le=1, description="Annual volatility (0.0-1.0)")
    max_drawdown: Optional[float] = Field(None, ge=0, le=1, description="Maximum drawdown (0.0-1.0)")
    equity_weight: float = Field(..., ge=0, le=1, description="Equity weight for ratio calculation (0.0-1.0)")
    description: Optional[str] = Field(None, max_length=255, description="Description")


class AssetRiskDefinitionListResponse(BaseModel):
    """Response for listing asset risk definitions."""
    definitions: List[AssetRiskDefinitionItem] = Field(default_factory=list)


class AssetSubcategoryDefinitionItem(BaseModel):
    """Asset subcategory definition item."""
    code: str = Field("", max_length=64)
    name: str = Field("", max_length=64)
    default_risk_class: Optional[str] = Field(None, max_length=8)


class AssetCategoryDefinitionItem(BaseModel):
    """Asset category definition item."""
    code: str = Field(..., max_length=32)
    name: str = Field(..., max_length=64)
    default_risk_class: Optional[str] = Field(None, max_length=8)
    subcategories: List[AssetSubcategoryDefinitionItem] = Field(default_factory=list)


class AssetCategoryDefinitionListResponse(BaseModel):
    """Response for listing asset category definitions."""
    definitions: List[AssetCategoryDefinitionItem] = Field(default_factory=list)


class AssetRiskDefinitionUpdateRequest(BaseModel):
    """Request for updating asset risk definition."""
    name: Optional[str] = Field(None, max_length=64)
    expected_return: Optional[float] = Field(None, ge=0, le=1)
    volatility: Optional[float] = Field(None, ge=0, le=1)
    max_drawdown: Optional[float] = Field(None, ge=0, le=1)
    equity_weight: Optional[float] = Field(None, ge=0, le=1)
    description: Optional[str] = Field(None, max_length=255)


class AssetAllocationSolveRequest(BaseModel):
    """Request for solving target asset allocation."""
    target_return_min: Optional[float] = Field(None, ge=0, le=1)
    target_return_max: Optional[float] = Field(None, ge=0, le=1)
    max_drawdown_tolerance: Optional[float] = Field(None, ge=0, le=1)
    base_ratio_min: Optional[float] = Field(None, ge=0, le=1)
    base_ratio_max: Optional[float] = Field(None, ge=0, le=1)
    opportunity_ratio_min: Optional[float] = Field(None, ge=0, le=1)
    opportunity_ratio_max: Optional[float] = Field(None, ge=0, le=1)


class AssetAllocationSolveResponse(BaseModel):
    """Response for solved asset allocation."""
    expected_return: float
    max_drawdown: float
    volatility: float
    allocation: Dict[str, float]
    method: str = "SLSQP"


class AssetAllocationPlanItem(BaseModel):
    """Saved asset allocation plan item."""
    id: int
    is_active: bool
    generated_at: str
    r1_ratio: float
    r2_ratio: float
    r3_ratio: float
    r4_ratio: float
    r5_ratio: float
    expected_return: Optional[float] = None
    max_drawdown: Optional[float] = None


class AssetAllocationPlanListResponse(BaseModel):
    """Response for listing asset allocation plans."""
    plans: List[AssetAllocationPlanItem] = Field(default_factory=list)


class AssetAllocationPlanCreateRequest(BaseModel):
    """Request for creating an asset allocation plan."""
    r1_ratio: float = Field(..., ge=0, le=100)
    r2_ratio: float = Field(..., ge=0, le=100)
    r3_ratio: float = Field(..., ge=0, le=100)
    r4_ratio: float = Field(..., ge=0, le=100)
    r5_ratio: float = Field(..., ge=0, le=100)


class AssetAllocationPlanActivateResponse(BaseModel):
    """Response for activating an asset allocation plan."""
    active_plan_id: Optional[int] = None
    is_active: bool


class PortfolioFundStatusResponse(BaseModel):
    """Global fund status."""
    fund_inception_date: Optional[str] = None
    latest_nav: Optional[float] = None
    latest_nav_date: Optional[str] = None
    latest_shares: Optional[float] = None
    total_equity: float


class PortfolioFundResetResponse(BaseModel):
    """Response for resetting fund NAV."""
    fund_inception_date: Optional[str] = None
    fund_shares: float
    fund_nav: float
    total_equity: float


class PortfolioFundResetRequest(BaseModel):
    """Request to reset fund NAV."""
    pass
