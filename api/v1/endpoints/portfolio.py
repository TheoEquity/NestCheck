# -*- coding: utf-8 -*-
"""Portfolio endpoints (P0 core account + snapshot workflow)."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from api.v1.schemas.common import ErrorResponse
from api.v1.schemas.portfolio import (
    PortfolioAccountCreateRequest,
    PortfolioAccountItem,
    PortfolioAccountListResponse,
    PortfolioAccountUpdateRequest,
    PortfolioCashLedgerListResponse,
    PortfolioCashLedgerCreateRequest,
    PortfolioCorporateActionListResponse,
    PortfolioCorporateActionCreateRequest,
    PortfolioDeleteResponse,
    PortfolioEventCreatedResponse,
    PortfolioLatestFxRateListResponse,
    PortfolioFxRefreshResponse,
    PortfolioImportBrokerListResponse,
    PortfolioImportCommitResponse,
    PortfolioImportParseResponse,
    PortfolioInitializeRequest,
    PortfolioInitializeResponse,
    PortfolioPositionAdjustRequest,
    PortfolioPositionAdjustResponse,
    PortfolioPositionListResponse,
    PortfolioImportTradeItem,
    PortfolioRiskResponse,
    PortfolioSnapshotResponse,
    PortfolioTradeListResponse,
    PortfolioTradeCreateRequest,
    AssetCategoryDefinitionItem,
    AssetCategoryDefinitionListResponse,
    AssetSubcategoryDefinitionItem,
    AssetRiskDefinitionItem,
    AssetRiskDefinitionListResponse,
    AssetRiskDefinitionUpdateRequest,
    AssetAllocationSolveRequest,
    AssetAllocationSolveResponse,
    AssetAllocationPlanItem,
    AssetAllocationPlanListResponse,
    AssetAllocationPlanCreateRequest,
    AssetAllocationPlanActivateResponse,
    PortfolioFundStatusResponse,
    PortfolioFundResetRequest,
    PortfolioFundResetResponse,
)
from src.services.portfolio_import_service import PortfolioImportService
from src.services.portfolio_risk_service import PortfolioRiskService
from src.services.portfolio_service import (
    PortfolioBusyError,
    PortfolioConflictError,
    PortfolioOversellError,
    PortfolioService,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": "validation_error", "message": str(exc)},
    )


def _internal_error(message: str, exc: Exception) -> HTTPException:
    logger.error(f"{message}: {exc}", exc_info=True)
    return HTTPException(
        status_code=500,
        detail={"error": "internal_error", "message": f"{message}: {str(exc)}"},
    )


def _conflict_error(*, error: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"error": error, "message": message},
    )


def _serialize_import_record(item: dict) -> PortfolioImportTradeItem:
    payload = dict(item)
    trade_date = payload.get("trade_date")
    if isinstance(trade_date, date):
        payload["trade_date"] = trade_date.isoformat()
    else:
        payload["trade_date"] = str(trade_date)
    return PortfolioImportTradeItem(**payload)


@router.post(
    "/accounts",
    response_model=PortfolioAccountItem,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Create portfolio account",
)
def create_account(request: PortfolioAccountCreateRequest) -> PortfolioAccountItem:
    service = PortfolioService()
    try:
        row = service.create_account(
            name=request.name,
            broker=request.broker,
            market=request.market,
            base_currency=request.base_currency,
            owner_id=request.owner_id,
        )
        return PortfolioAccountItem(**row)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create account failed", exc)


@router.get(
    "/accounts",
    response_model=PortfolioAccountListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List portfolio accounts",
)
def list_accounts(
    include_inactive: bool = Query(False, description="Whether to include inactive accounts"),
) -> PortfolioAccountListResponse:
    service = PortfolioService()
    try:
        rows = service.list_accounts(include_inactive=include_inactive)
        return PortfolioAccountListResponse(accounts=[PortfolioAccountItem(**item) for item in rows])
    except Exception as exc:
        raise _internal_error("List accounts failed", exc)


@router.put(
    "/accounts/{account_id}",
    response_model=PortfolioAccountItem,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Update portfolio account",
)
def update_account(account_id: int, request: PortfolioAccountUpdateRequest) -> PortfolioAccountItem:
    service = PortfolioService()
    try:
        updated = service.update_account(
            account_id,
            name=request.name,
            broker=request.broker,
            market=request.market,
            base_currency=request.base_currency,
            owner_id=request.owner_id,
            is_active=request.is_active,
        )
        if updated is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"Account not found: {account_id}"},
            )
        return PortfolioAccountItem(**updated)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Update account failed", exc)


@router.delete(
    "/accounts/{account_id}",
    response_model=PortfolioDeleteResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Delete portfolio account and related assets",
)
def delete_account(account_id: int) -> PortfolioDeleteResponse:
    service = PortfolioService()
    try:
        ok = service.delete_account(account_id)
        if not ok:
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": f"Account not found: {account_id}"},
            )
        return PortfolioDeleteResponse(deleted=1)
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error("Delete account failed", exc)


@router.post(
    "/initialize",
    response_model=PortfolioInitializeResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Initialize portfolio by directly writing positions and cash (bypasses event replay)",
)
def initialize_portfolio(request: PortfolioInitializeRequest) -> PortfolioInitializeResponse:
    service = PortfolioService()
    try:
        result = service.initialize_portfolio(
            account_id=request.account_id,
            init_date=request.init_date,
            assets=[asset.model_dump() for asset in request.assets],
            cash_items=[item.model_dump() for item in request.cash_items],
        )
        return PortfolioInitializeResponse(**result)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Initialize portfolio failed", exc)


@router.post(
    "/trades",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Record trade event",
)
def create_trade(request: PortfolioTradeCreateRequest) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.record_trade(
            account_id=request.account_id,
            asset_category=request.asset_category,
            asset_subcategory=request.asset_subcategory,
            asset_risk_class=request.asset_risk_class,
            symbol=request.symbol,
            name=request.name,
            trade_date=request.trade_date,
            available_date=request.available_date,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            fee=request.fee,
            tax=request.tax,
            market=request.market,
            currency=request.currency,
            trade_uid=request.trade_uid,
            note=request.note,
        )
        return PortfolioEventCreatedResponse(**data)
    except PortfolioBusyError as exc:
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except PortfolioOversellError as exc:
        raise _conflict_error(error="portfolio_oversell", message=str(exc))
    except PortfolioConflictError as exc:
        raise _conflict_error(error="conflict", message=str(exc))
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create trade failed", exc)


@router.get(
    "/trades",
    response_model=PortfolioTradeListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List trade events",
)
def list_trades(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    date_from: Optional[date] = Query(None, description="Trade date from"),
    date_to: Optional[date] = Query(None, description="Trade date to"),
    symbol: Optional[str] = Query(None, description="Optional stock symbol filter"),
    side: Optional[str] = Query(None, description="Optional side filter: buy/sell"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortfolioTradeListResponse:
    service = PortfolioService()
    try:
        data = service.list_trade_events(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbol=symbol,
            side=side,
            page=page,
            page_size=page_size,
        )
        return PortfolioTradeListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List trade events failed", exc)


@router.post(
    "/cash-ledger",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Record cash event",
)
def create_cash_ledger(request: PortfolioCashLedgerCreateRequest) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.record_cash_ledger(
            account_id=request.account_id,
            asset_category=request.asset_category,
            asset_subcategory=request.asset_subcategory,
            asset_risk_class=request.asset_risk_class,
            event_date=request.event_date,
            direction=request.direction,
            amount=request.amount,
            currency=request.currency,
            note=request.note,
        )
        return PortfolioEventCreatedResponse(**data)
    except PortfolioBusyError as exc:
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create cash ledger event failed", exc)


@router.get(
    "/cash-ledger",
    response_model=PortfolioCashLedgerListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List cash ledger events",
)
def list_cash_ledger(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    date_from: Optional[date] = Query(None, description="Cash event date from"),
    date_to: Optional[date] = Query(None, description="Cash event date to"),
    direction: Optional[str] = Query(None, description="Optional direction filter: in/out"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortfolioCashLedgerListResponse:
    service = PortfolioService()
    try:
        data = service.list_cash_ledger_events(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            direction=direction,
            page=page,
            page_size=page_size,
        )
        return PortfolioCashLedgerListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List cash ledger events failed", exc)


@router.post(
    "/corporate-actions",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Record corporate action event",
)
def create_corporate_action(request: PortfolioCorporateActionCreateRequest) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.record_corporate_action(
            account_id=request.account_id,
            symbol=request.symbol,
            asset_category=request.asset_category,
            asset_subcategory=request.asset_subcategory,
            effective_date=request.effective_date,
            action_type=request.action_type,
            market=request.market,
            currency=request.currency,
            dividend_amount=request.dividend_amount,
            split_ratio=request.split_ratio,
            note=request.note,
        )
        return PortfolioEventCreatedResponse(**data)
    except PortfolioBusyError as exc:
        raise _conflict_error(error="portfolio_busy", message=str(exc))
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create corporate action event failed", exc)


@router.get(
    "/corporate-actions",
    response_model=PortfolioCorporateActionListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List corporate action events",
)
def list_corporate_actions(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    date_from: Optional[date] = Query(None, description="Corporate action effective date from"),
    date_to: Optional[date] = Query(None, description="Corporate action effective date to"),
    symbol: Optional[str] = Query(None, description="Optional stock symbol filter"),
    action_type: Optional[str] = Query(None, description="Optional corporate action type filter"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PortfolioCorporateActionListResponse:
    service = PortfolioService()
    try:
        data = service.list_corporate_action_events(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbol=symbol,
            action_type=action_type,
            page=page,
            page_size=page_size,
        )
        return PortfolioCorporateActionListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List corporate action events failed", exc)


@router.get(
    "/positions",
    response_model=PortfolioPositionListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="List current portfolio positions",
)
def list_positions(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    cost_method: str = Query("fifo", description="Cost method: fifo or avg"),
) -> PortfolioPositionListResponse:
    service = PortfolioService()
    try:
        data = service.list_positions(account_id=account_id, cost_method=cost_method)
        return PortfolioPositionListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("List positions failed", exc)


@router.get(
    "/positions/open-dates",
    response_model=PortfolioPositionListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List tracked open-date positions",
)
def list_open_date_positions() -> PortfolioPositionListResponse:
    service = PortfolioService()
    try:
        data = service.list_open_date_positions()
        return PortfolioPositionListResponse(**data)
    except Exception as exc:
        raise _internal_error("List open-date positions failed", exc)


@router.post(
    "/positions/open-dates/{trade_id}/dismiss",
    response_model=PortfolioEventCreatedResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Dismiss one open-date watch item",
)
def dismiss_open_date_position(trade_id: int) -> PortfolioEventCreatedResponse:
    service = PortfolioService()
    try:
        data = service.disable_open_date_watch(trade_id)
        return PortfolioEventCreatedResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Dismiss open-date position failed", exc)


@router.post(
    "/positions/{position_id}/adjust",
    response_model=PortfolioPositionAdjustResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Manually adjust a single position (quantity, avg_cost, or last_price)",
)
def adjust_position(
    position_id: int,
    body: PortfolioPositionAdjustRequest,
    account_id: Optional[int] = Query(None, description="Optional account id for extra scoping"),
) -> PortfolioPositionAdjustResponse:
    service = PortfolioService()
    try:
        data = service.adjust_position(
            position_id=position_id,
            account_id=account_id,
            quantity=body.quantity,
            avg_cost=body.avg_cost,
            last_price=body.last_price,
        )
        return PortfolioPositionAdjustResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Adjust position failed", exc)


@router.get(
    "/snapshot",
    response_model=PortfolioSnapshotResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get portfolio snapshot",
)
def get_snapshot(
    account_id: Optional[int] = Query(None, description="Optional account id, default returns all accounts"),
    as_of: Optional[date] = Query(None, description="Snapshot date, default today"),
    cost_method: str = Query("fifo", description="Cost method: fifo or avg"),
) -> PortfolioSnapshotResponse:
    service = PortfolioService()
    try:
        data = service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
        )
        return PortfolioSnapshotResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Get snapshot failed", exc)


@router.post(
    "/imports/csv/parse",
    response_model=PortfolioImportParseResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Parse broker CSV into normalized trade records",
)
def parse_csv_import(
    broker: str = Form(..., description="Broker id: huatai/citic/cmb"),
    file: UploadFile = File(...),
) -> PortfolioImportParseResponse:
    importer = PortfolioImportService()
    try:
        content = file.file.read()
        parsed = importer.parse_trade_csv(broker=broker, content=content)
        return PortfolioImportParseResponse(
            broker=parsed["broker"],
            record_count=parsed["record_count"],
            skipped_count=parsed["skipped_count"],
            error_count=parsed["error_count"],
            records=[_serialize_import_record(item) for item in parsed.get("records", [])],
            errors=list(parsed.get("errors", [])),
        )
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Parse CSV import failed", exc)


@router.get(
    "/imports/csv/brokers",
    response_model=PortfolioImportBrokerListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List supported broker CSV parsers",
)
def list_csv_brokers() -> PortfolioImportBrokerListResponse:
    importer = PortfolioImportService()
    try:
        return PortfolioImportBrokerListResponse(brokers=importer.list_supported_brokers())
    except Exception as exc:
        raise _internal_error("List CSV brokers failed", exc)


@router.post(
    "/imports/csv/commit",
    response_model=PortfolioImportCommitResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Parse and commit broker CSV with dedup",
)
def commit_csv_import(
    account_id: int = Form(...),
    broker: str = Form(..., description="Broker id: huatai/citic/cmb"),
    dry_run: bool = Form(False),
    file: UploadFile = File(...),
) -> PortfolioImportCommitResponse:
    importer = PortfolioImportService()
    try:
        content = file.file.read()
        parsed = importer.parse_trade_csv(broker=broker, content=content)
        result = importer.commit_trade_records(
            account_id=account_id,
            broker=parsed["broker"],
            records=list(parsed.get("records", [])),
            dry_run=dry_run,
        )
        return PortfolioImportCommitResponse(**result)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Commit CSV import failed", exc)


@router.post(
    "/fx/refresh",
    response_model=PortfolioFxRefreshResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Refresh FX cache online with stale fallback",
)
def refresh_fx_rates(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="Rate date, default today"),
) -> PortfolioFxRefreshResponse:
    service = PortfolioService()
    try:
        data = service.refresh_fx_rates(account_id=account_id, as_of=as_of)
        return PortfolioFxRefreshResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Refresh FX rates failed", exc)


@router.get(
    "/fx/latest",
    response_model=PortfolioLatestFxRateListResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get latest cached FX rates",
)
def get_latest_fx_rates(
    to_currency: str = Query("CNY", description="Quote currency, default CNY"),
    as_of: Optional[date] = Query(None, description="Rate date, default today"),
) -> PortfolioLatestFxRateListResponse:
    service = PortfolioService()
    try:
        data = service.get_latest_fx_rates(to_currency=to_currency, as_of=as_of)
        return PortfolioLatestFxRateListResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Get latest FX rates failed", exc)


@router.get(
    "/risk",
    response_model=PortfolioRiskResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Get portfolio risk report",
)
def get_risk_report(
    account_id: Optional[int] = Query(None, description="Optional account id"),
    as_of: Optional[date] = Query(None, description="Risk report date, default today"),
    cost_method: str = Query("fifo", description="Cost method: fifo or avg"),
) -> PortfolioRiskResponse:
    service = PortfolioRiskService()
    try:
        data = service.get_risk_report(account_id=account_id, as_of=as_of, cost_method=cost_method)
        return PortfolioRiskResponse(**data)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Get risk report failed", exc)


@router.post(
    "/prices/refresh",
    response_model=dict,
    responses={500: {"model": ErrorResponse}},
    summary="Refresh all cached prices (positions, indices, FX rates)",
)
def refresh_all_prices() -> dict:
    svc = PortfolioService()
    try:
        result = svc.refresh_all_prices()
        return result
    except Exception as exc:
        raise _internal_error("Refresh prices failed", exc)


@router.get(
    "/risk-definitions",
    response_model=AssetRiskDefinitionListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get asset risk class definitions (R1-R5)",
)
def get_risk_definitions() -> AssetRiskDefinitionListResponse:
    """Get all active asset risk class definitions."""
    from src.storage import get_db, AssetRiskDefinition

    db = get_db()
    try:
        with db.get_session() as session:
            definitions = session.query(AssetRiskDefinition).filter(
                AssetRiskDefinition.is_active == True
            ).order_by(AssetRiskDefinition.asset_risk_class).all()

            items = [
                AssetRiskDefinitionItem(
                    asset_risk_class=d.asset_risk_class,
                    name=d.name,
                    expected_return=d.expected_return,
                    volatility=d.volatility,
                    max_drawdown=d.max_drawdown,
                    equity_weight=d.equity_weight,
                    description=d.description,
                )
                for d in definitions
            ]

            return AssetRiskDefinitionListResponse(definitions=items)
    except Exception as exc:
        raise _internal_error("Get risk definitions failed", exc)


@router.post(
    "/allocation/solve",
    response_model=AssetAllocationSolveResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Solve optimal asset allocation with SLSQP",
)
def solve_asset_allocation(request: AssetAllocationSolveRequest) -> AssetAllocationSolveResponse:
    """Solve asset allocation using active R1-R5 definitions and SLSQP.

    Allocation values in response are percentages (0-100), while return/drawdown/volatility
    are decimals (0.08 = 8%).
    """
    try:
        import numpy as np
        from scipy.optimize import minimize
        from src.storage import get_db, AssetRiskDefinition

        db = get_db()
        required_classes = ["R1", "R2", "R3", "R4", "R5"]
        with db.get_session() as session:
            rows = session.query(AssetRiskDefinition).filter(
                AssetRiskDefinition.is_active == True
            ).all()

        definitions = {row.asset_risk_class: row for row in rows}
        if any(code not in definitions for code in required_classes):
            raise ValueError("Risk class definitions must include R1-R5")

        expected_returns = np.array([float(definitions[code].expected_return or 0.0) for code in required_classes])
        drawdowns = np.array([float(definitions[code].max_drawdown or 0.0) for code in required_classes])
        volatilities = np.array([float(definitions[code].volatility or 0.0) for code in required_classes])

        raw_target_min = request.target_return_min if request.target_return_min is not None else 0.0
        raw_target_max = request.target_return_max if request.target_return_max is not None else raw_target_min
        target_min = min(raw_target_min, raw_target_max)
        target_max = max(raw_target_min, raw_target_max)
        target = target_max or target_min
        max_drawdown_tolerance = request.max_drawdown_tolerance if request.max_drawdown_tolerance is not None else 1.0
        raw_base_min = request.base_ratio_min if request.base_ratio_min is not None else 0.0
        raw_base_max = request.base_ratio_max if request.base_ratio_max is not None else 1.0
        base_min = min(raw_base_min, raw_base_max)
        base_max = max(raw_base_min, raw_base_max)
        raw_opportunity_min = request.opportunity_ratio_min if request.opportunity_ratio_min is not None else 0.0
        raw_opportunity_max = request.opportunity_ratio_max if request.opportunity_ratio_max is not None else 1.0
        opportunity_min = min(raw_opportunity_min, raw_opportunity_max)
        opportunity_max = max(raw_opportunity_min, raw_opportunity_max)

        alpha = 1000.0
        beta = 1.0
        gamma = 0.25
        initial = np.array([0.10, 0.10, 0.20, 0.50, 0.10])

        def objective(weights: np.ndarray) -> float:
            portfolio_return = float(np.dot(weights, expected_returns))
            portfolio_drawdown = float(np.dot(weights, drawdowns))
            portfolio_volatility = float(np.dot(weights, volatilities))
            if portfolio_return < target_min:
                target_distance = target_min - portfolio_return
            elif portfolio_return > target_max:
                target_distance = portfolio_return - target_max
            else:
                target_distance = abs(portfolio_return - target)
            return alpha * target_distance ** 2 + beta * portfolio_drawdown ** 2 + gamma * portfolio_volatility ** 2

        constraints = [
            {"type": "eq", "fun": lambda weights: np.sum(weights) - 1.0},
            {"type": "ineq", "fun": lambda weights: weights[0] - base_min},
            {"type": "ineq", "fun": lambda weights: base_max - weights[0]},
            {"type": "ineq", "fun": lambda weights: weights[3] + weights[4] - opportunity_min},
            {"type": "ineq", "fun": lambda weights: opportunity_max - (weights[3] + weights[4])},
            {"type": "ineq", "fun": lambda weights: max_drawdown_tolerance - float(np.dot(weights, drawdowns))},
        ]
        bounds = [(0.0, 1.0) for _ in required_classes]
        result = minimize(objective, initial, bounds=bounds, constraints=constraints, method="SLSQP")

        if not result.success:
            raise ValueError("Unable to solve optimal allocation")

        weights = np.clip(result.x, 0.0, 1.0)
        weights = weights / np.sum(weights)
        return AssetAllocationSolveResponse(
            expected_return=float(np.dot(weights, expected_returns)),
            max_drawdown=float(np.dot(weights, drawdowns)),
            volatility=float(np.dot(weights, volatilities)),
            allocation={code: round(float(weight * 100), 2) for code, weight in zip(required_classes, weights)},
            method="SLSQP",
        )
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Solve asset allocation failed", exc)


def _build_allocation_plan_item(plan) -> AssetAllocationPlanItem:
    generated_at = plan.generated_at
    if isinstance(generated_at, datetime):
        generated_at_text = generated_at.isoformat()
    else:
        generated_at_text = str(generated_at)
    return AssetAllocationPlanItem(
        id=plan.id,
        is_active=bool(plan.is_active),
        generated_at=generated_at_text,
        r1_ratio=float(plan.r1_ratio or 0.0),
        r2_ratio=float(plan.r2_ratio or 0.0),
        r3_ratio=float(plan.r3_ratio or 0.0),
        r4_ratio=float(plan.r4_ratio or 0.0),
        r5_ratio=float(plan.r5_ratio or 0.0),
        expected_return=float(plan.expected_return) if plan.expected_return is not None else None,
        max_drawdown=float(plan.max_drawdown) if plan.max_drawdown is not None else None,
    )


def _calculate_allocation_plan_metrics(session, ratios: list[float]) -> tuple[float, float]:
    from src.storage import AssetRiskDefinition

    required_classes = ["R1", "R2", "R3", "R4", "R5"]
    definitions = {
        item.asset_risk_class.upper(): item
        for item in session.query(AssetRiskDefinition).filter(AssetRiskDefinition.is_active == True).all()
    }
    if not all(code in definitions for code in required_classes):
        raise ValueError("风险等级定义不完整，需包含 R1-R5")

    expected_return = 0.0
    max_drawdown = 0.0
    for code, ratio in zip(required_classes, ratios):
        definition = definitions[code]
        weight = ratio / 100.0
        expected_return += weight * float(definition.expected_return or 0.0)
        max_drawdown += weight * float(definition.max_drawdown or 0.0)
    return expected_return, max_drawdown


@router.get(
    "/allocation/plans",
    response_model=AssetAllocationPlanListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="List saved asset allocation plans",
)
def list_asset_allocation_plans() -> AssetAllocationPlanListResponse:
    """List saved asset allocation plans ordered by generation time."""
    try:
        from src.storage import get_db, AssetAllocationPlan

        db = get_db()
        with db.get_session() as session:
            plans = session.query(AssetAllocationPlan).order_by(
                AssetAllocationPlan.generated_at.desc(),
                AssetAllocationPlan.id.desc(),
            ).all()
            return AssetAllocationPlanListResponse(plans=[_build_allocation_plan_item(plan) for plan in plans])
    except Exception as exc:
        raise _internal_error("List asset allocation plans failed", exc)


@router.post(
    "/allocation/plans",
    response_model=AssetAllocationPlanItem,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Create asset allocation plan",
)
def create_asset_allocation_plan(request: AssetAllocationPlanCreateRequest) -> AssetAllocationPlanItem:
    """Create a saved asset allocation plan from R1-R5 ratios."""
    try:
        from src.storage import get_db, AssetAllocationPlan

        ratios = [request.r1_ratio, request.r2_ratio, request.r3_ratio, request.r4_ratio, request.r5_ratio]
        total_ratio = sum(ratios)
        if abs(total_ratio - 100.0) > 0.05:
            raise ValueError("Allocation ratios must sum to 100%")

        db = get_db()
        with db.get_session() as session:
            expected_return, max_drawdown = _calculate_allocation_plan_metrics(session, ratios)
            plan = AssetAllocationPlan(
                is_active=False,
                generated_at=datetime.now(),
                r1_ratio=request.r1_ratio,
                r2_ratio=request.r2_ratio,
                r3_ratio=request.r3_ratio,
                r4_ratio=request.r4_ratio,
                r5_ratio=request.r5_ratio,
                expected_return=expected_return,
                max_drawdown=max_drawdown,
            )
            session.add(plan)
            session.commit()
            session.refresh(plan)
            return _build_allocation_plan_item(plan)
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Create asset allocation plan failed", exc)


@router.put(
    "/allocation/plans/{plan_id}/activate",
    response_model=AssetAllocationPlanActivateResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Activate asset allocation plan",
)
def activate_asset_allocation_plan(plan_id: int) -> AssetAllocationPlanActivateResponse:
    """Toggle active state for a saved allocation plan."""
    try:
        from src.storage import get_db, AssetAllocationPlan

        db = get_db()
        with db.get_session() as session:
            plan = session.query(AssetAllocationPlan).filter(AssetAllocationPlan.id == plan_id).first()
            if plan is None:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "not_found", "message": f"Allocation plan not found: {plan_id}"},
                )
            if plan.is_active:
                plan.is_active = False
                plan.updated_at = datetime.now()
                session.commit()
                return AssetAllocationPlanActivateResponse(active_plan_id=None, is_active=False)

            other_active = session.query(AssetAllocationPlan).filter(
                AssetAllocationPlan.is_active == True,
                AssetAllocationPlan.id != plan_id,
            ).first()
            if other_active is not None:
                raise ValueError("已有其他生效配置计划，请先取消其生效状态")

            plan.is_active = True
            plan.updated_at = datetime.now()
            session.commit()
            return AssetAllocationPlanActivateResponse(active_plan_id=plan_id, is_active=True)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Activate asset allocation plan failed", exc)


@router.delete(
    "/allocation/plans/{plan_id}",
    response_model=PortfolioDeleteResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Delete asset allocation plan",
)
def delete_asset_allocation_plan(plan_id: int) -> PortfolioDeleteResponse:
    """Delete an inactive asset allocation plan."""
    try:
        from src.storage import get_db, AssetAllocationPlan

        db = get_db()
        with db.get_session() as session:
            plan = session.query(AssetAllocationPlan).filter(AssetAllocationPlan.id == plan_id).first()
            if plan is None:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "not_found", "message": f"Allocation plan not found: {plan_id}"},
                )
            if plan.is_active:
                raise ValueError("生效中的配置计划需先取消生效，再删除")
            session.delete(plan)
            session.commit()
            return PortfolioDeleteResponse(deleted=1)
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Delete asset allocation plan failed", exc)


@router.put(
    "/risk-definitions/{risk_class}",
    response_model=AssetRiskDefinitionItem,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Update asset risk class definition",
)
def update_risk_definition(
    risk_class: str,
    request: AssetRiskDefinitionUpdateRequest,
) -> AssetRiskDefinitionItem:
    """Update a single asset risk class definition (R1-R5)."""
    from src.storage import get_db, AssetRiskDefinition
    from sqlalchemy import update

    db = get_db()
    try:
        with db.get_session() as session:
            existing = session.query(AssetRiskDefinition).filter(
                AssetRiskDefinition.asset_risk_class == risk_class.upper()
            ).first()

            if not existing:
                raise HTTPException(status_code=404, detail=f"Risk class {risk_class} not found")

            update_data = request.model_dump(exclude_unset=True)

            session.execute(
                update(AssetRiskDefinition)
                .where(AssetRiskDefinition.asset_risk_class == risk_class.upper())
                .values(**update_data)
            )
            session.commit()

            updated = session.query(AssetRiskDefinition).filter(
                AssetRiskDefinition.asset_risk_class == risk_class.upper()
            ).first()

            return AssetRiskDefinitionItem(
                asset_risk_class=updated.asset_risk_class,
                name=updated.name,
                expected_return=updated.expected_return,
                volatility=updated.volatility,
                max_drawdown=updated.max_drawdown,
                equity_weight=updated.equity_weight,
                description=updated.description,
            )
    except HTTPException:
        raise
    except ValueError as exc:
        raise _bad_request(exc)
    except Exception as exc:
        raise _internal_error("Update risk definition failed", exc)


def _load_asset_category_definitions() -> AssetCategoryDefinitionListResponse:
    from src.storage import get_db, AssetCategoryDefinition

    db = get_db()
    with db.get_session() as session:
        rows = session.query(AssetCategoryDefinition).filter(
            AssetCategoryDefinition.is_active == True
        ).order_by(
            AssetCategoryDefinition.sort_order.asc(),
            AssetCategoryDefinition.id.asc(),
        ).all()

        categories: dict[str, AssetCategoryDefinitionItem] = {}
        for row in rows:
            item = categories.get(row.category_code)
            if item is None:
                item = AssetCategoryDefinitionItem(
                    code=row.category_code,
                    name=row.category_name,
                    default_risk_class=row.default_risk_class,
                    subcategories=[],
                )
                categories[row.category_code] = item

            if row.subcategory_code or row.subcategory_name:
                item.subcategories.append(AssetSubcategoryDefinitionItem(
                    code=row.subcategory_code,
                    name=row.subcategory_name,
                    default_risk_class=row.default_risk_class,
                ))

        return AssetCategoryDefinitionListResponse(definitions=list(categories.values()))


@router.get(
    "/asset-category-definitions",
    response_model=AssetCategoryDefinitionListResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get asset category and subcategory definitions",
)
def get_asset_category_definitions() -> AssetCategoryDefinitionListResponse:
    """Return asset category definitions from asset_category_definitions."""
    try:
        return _load_asset_category_definitions()
    except Exception as exc:
        raise _internal_error("Get asset category definitions failed", exc)


@router.get(
    "/asset-categories",
    response_model=dict,
    responses={500: {"model": ErrorResponse}},
    summary="Get asset category definitions",
)
def get_asset_categories() -> dict:
    """Return asset category codes from asset_category_definitions."""
    try:
        definitions = _load_asset_category_definitions().definitions
        return {"categories": [item.code for item in definitions]}
    except Exception as exc:
        raise _internal_error("Get asset categories failed", exc)


@router.get(
    "/fund-status",
    response_model=PortfolioFundStatusResponse,
    responses={500: {"model": ErrorResponse}},
    summary="Get global fund status",
)
def get_fund_status() -> PortfolioFundStatusResponse:
    """Return global fund NAV, shares and total_equity."""
    from src.storage import get_db, PortfolioFundValue
    from src.services.portfolio_service import PortfolioService, round_internal_fund_nav, round_money, round_share

    db = get_db()
    with db.get_session() as session:
        latest_fv = (
            session.query(PortfolioFundValue)
            .order_by(PortfolioFundValue.record_date.desc())
            .first()
        )

        service = PortfolioService()
        total_equity = round_money(service.get_management_total_equity())

        return PortfolioFundStatusResponse(
            fund_inception_date=latest_fv.record_date.isoformat() if latest_fv else None,
            latest_nav=round_internal_fund_nav(latest_fv.fund_nav) if latest_fv else None,
            latest_nav_date=latest_fv.record_date.isoformat() if latest_fv else None,
            latest_shares=round_share(latest_fv.fund_shares) if latest_fv else None,
            total_equity=total_equity,
        )


@router.post(
    "/fund-reset",
    response_model=PortfolioFundResetResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Reset fund NAV to 1 and set shares to current total equity",
)
def reset_fund(_payload: PortfolioFundResetRequest) -> PortfolioFundResetResponse:
    """Reset fund NAV to 1.0 and set shares = current total_equity."""
    from datetime import date as date_type

    from src.storage import get_db, PortfolioFundValue
    from src.services.portfolio_service import PortfolioService, round_internal_fund_nav, round_money, round_share

    db = get_db()
    try:
        with db.get_session() as session:
            service = PortfolioService()
            total_equity = round_money(service.get_management_total_equity())

            if total_equity <= 0:
                raise HTTPException(status_code=400, detail={"error": "bad_request", "message": "Total equity must be positive to reset fund"})

            today = date_type.today()

            fv_record = PortfolioFundValue(
                record_date=today,
                fund_shares=round_share(total_equity),
                fund_nav=round_internal_fund_nav(1.0),
                total_equity=round_money(total_equity),
            )
            session.add(fv_record)
            session.commit()

            return PortfolioFundResetResponse(
                fund_inception_date=today.isoformat(),
                fund_shares=round_share(total_equity),
                fund_nav=round_internal_fund_nav(1.0),
                total_equity=round_money(total_equity),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise _internal_error("Reset fund failed", exc)
