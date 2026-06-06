# -*- coding: utf-8 -*-
"""Portfolio service for P0 account/events/snapshot workflow."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import and_, select

from data_provider.base import canonical_stock_code, normalize_stock_code
from src.config import get_config
from src.repositories.portfolio_repo import (
    DuplicateTradeDedupHashError,
    DuplicateTradeUidError,
    PortfolioBusyError as RepoPortfolioBusyError,
    PortfolioRepository,
)

logger = logging.getLogger(__name__)

PortfolioBusyError = RepoPortfolioBusyError

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency path
    yf = None

EPS = 1e-8
VALID_MARKETS = {"cn", "hk", "us"}
VALID_COST_METHODS = {"fifo", "avg"}
VALID_SIDES = {"buy", "sell"}
VALID_CASH_DIRECTIONS = {"in", "out"}
VALID_CORPORATE_ACTIONS = {"cash_dividend"}
PORTFOLIO_FX_REFRESH_DISABLED_REASON = "portfolio_fx_update_disabled"

REALTIME_ASSET_RISK_CLASSES = {"R4", "R5"}


class PortfolioConflictError(Exception):
    """Raised when request conflicts with existing portfolio state."""


class PortfolioOversellError(ValueError):
    """Raised when a sell would exceed the available position quantity."""

    def __init__(
        self,
        *,
        symbol: str,
        trade_date: Optional[date],
        requested_quantity: float,
        available_quantity: float,
    ) -> None:
        self.symbol = symbol
        self.trade_date = trade_date
        self.requested_quantity = float(requested_quantity)
        self.available_quantity = max(0.0, float(available_quantity))
        date_hint = f" on {trade_date.isoformat()}" if trade_date is not None else ""
        super().__init__(
            "Oversell detected for "
            f"{symbol}{date_hint}: requested={round(self.requested_quantity, 8)}, "
            f"available={round(self.available_quantity, 8)}"
        )


@dataclass
class _AvgState:
    quantity: float = 0.0
    total_cost: float = 0.0
    name: Optional[str] = None
    asset_category: Optional[str] = None
    asset_subcategory: Optional[str] = None
    asset_risk_class: Optional[str] = None


@dataclass(frozen=True)
class _ResolvedPositionPrice:
    price: float
    source: str
    price_date: Optional[date]
    is_stale: bool
    is_available: bool
    provider: Optional[str] = None
    change_pct: Optional[float] = None


@dataclass(frozen=True)
class _RealtimePositionQuote:
    price: float
    provider: Optional[str]
    name: Optional[str]
    change_pct: Optional[float]


@dataclass
class _PositionMetadata:
    name: Optional[str] = None
    asset_category: Optional[str] = None
    asset_subcategory: Optional[str] = None
    asset_risk_class: Optional[str] = None


class PortfolioService:
    """Business logic for account CRUD, event writes, and snapshot replay."""

    def __init__(self, repo: Optional[PortfolioRepository] = None):
        self.repo = repo or PortfolioRepository()

    # ------------------------------------------------------------------
    # Account CRUD
    # ------------------------------------------------------------------
    def create_account(
        self,
        *,
        name: str,
        broker: Optional[str],
        market: str,
        base_currency: str,
        owner_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        name_norm = (name or "").strip()
        if not name_norm:
            raise ValueError("name is required")
        market_norm = self._normalize_market(market)
        base_currency_norm = self._normalize_currency(base_currency)
        row = self.repo.create_account(
            name=name_norm,
            broker=(broker or "").strip() or None,
            market=market_norm,
            base_currency=base_currency_norm,
            owner_id=(owner_id or "").strip() or None,
        )
        return self._account_to_dict(row)

    def list_accounts(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        rows = self.repo.list_accounts(include_inactive=include_inactive)
        return [self._account_to_dict(r) for r in rows]

    def update_account(
        self,
        account_id: int,
        *,
        name: Optional[str] = None,
        broker: Optional[str] = None,
        market: Optional[str] = None,
        base_currency: Optional[str] = None,
        owner_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        fields: Dict[str, Any] = {}
        if name is not None:
            name_norm = name.strip()
            if not name_norm:
                raise ValueError("name is required")
            fields["name"] = name_norm
        if broker is not None:
            fields["broker"] = broker.strip() or None
        if market is not None:
            fields["market"] = self._normalize_market(market)
        if base_currency is not None:
            fields["base_currency"] = self._normalize_currency(base_currency)
        if owner_id is not None:
            fields["owner_id"] = owner_id.strip() or None
        if is_active is not None:
            fields["is_active"] = bool(is_active)
        if not fields:
            raise ValueError("No fields provided for update")

        row = self.repo.update_account(account_id, fields)
        if row is None:
            return None
        return self._account_to_dict(row)

    def deactivate_account(self, account_id: int) -> bool:
        return self.repo.deactivate_account(account_id)

    def delete_account(self, account_id: int) -> bool:
        return self.repo.delete_account(account_id)

    # ------------------------------------------------------------------
    # Initialization (direct write to asset tables, bypassing event replay)
    # ------------------------------------------------------------------
    def initialize_portfolio(
        self,
        *,
        account_id: int,
        init_date: date,
        assets: List[Dict[str, Any]],
        cash_items: List[Dict[str, Any]],
        cost_method: str = "fifo",
    ) -> Dict[str, Any]:
        """Initialize an account's portfolio by directly writing positions.

        This bypasses the event replay system. It clears all existing event records
        (trades, cash ledger, cash dividend events) and cached positions, then writes
        all initial holdings (securities + cash) directly into portfolio_positions.
        Cash is treated as an asset class and written to portfolio_positions alongside
        securities.

        Args:
            account_id: Target account id
            init_date: Initialization date
            assets: List of asset dicts with keys: symbol, name, market, currency,
                    quantity, avg_cost, asset_category, asset_subcategory, asset_risk_class
            cash_items: List of cash dicts with keys: name, amount, currency,
                        asset_category
            cost_method: Cost method for position cache (default: fifo)

        Returns:
            Dict with asset_count, cash_count, and cleared event counts
        """
        account = self._require_active_account(account_id)
        method = self._normalize_cost_method(cost_method)

        # Step 1: Clear all existing event records and cached positions
        cleared = self.repo.clear_account_events(account_id=account_id)

        # Step 2: Build position records for securities
        position_rows: List[Dict[str, Any]] = []
        lot_rows: List[Dict[str, Any]] = []

        for asset in assets:
            symbol = self._normalize_symbol_for_storage(asset.get("symbol", ""))
            if not symbol:
                raise ValueError(f"Asset symbol is required, got: {asset.get('symbol')}")

            market = self._normalize_market(asset.get("market", account.market))
            currency = self._normalize_currency(asset.get("currency", account.base_currency))
            quantity = float(asset.get("quantity", 0))
            avg_cost = float(asset.get("avg_cost", 0))
            if quantity <= 0:
                raise ValueError(f"Asset quantity must be > 0 for {symbol}")
            if avg_cost <= 0:
                raise ValueError(f"Asset avg_cost must be > 0 for {symbol}")

            total_cost = quantity * avg_cost
            name = (asset.get("name") or "").strip() or None
            asset_category = (asset.get("asset_category") or "").strip() or None
            asset_subcategory = (asset.get("asset_subcategory") or "").strip() or None
            asset_risk_class = (asset.get("asset_risk_class") or "").strip().upper() or None

            position_rows.append({
                "symbol": symbol,
                "name": name,
                "market": market,
                "currency": currency,
                "quantity": quantity,
                "avg_cost": avg_cost,
                "total_cost": total_cost,
                "last_price": 0.0,
                "market_value_base": 0.0,
                "unrealized_pnl_base": 0.0,
                "asset_category": asset_category,
                "asset_subcategory": asset_subcategory,
                "asset_risk_class": asset_risk_class,
            })

            lot_rows.append({
                "symbol": symbol,
                "market": market,
                "currency": currency,
                "open_date": init_date,
                "remaining_quantity": quantity,
                "unit_cost": avg_cost,
                "source_trade_id": None,
                "asset_category": asset_category,
                "asset_subcategory": asset_subcategory,
                "asset_risk_class": asset_risk_class,
            })

        # Step 3: Build position records for cash (cash is also an asset)
        cash_written = 0
        for cash in cash_items:
            amount = float(cash.get("amount", 0))
            if amount <= 0:
                continue

            cash_currency = self._normalize_currency(cash.get("currency", account.base_currency))
            name = (cash.get("name") or "").strip() or None
            asset_category = (cash.get("asset_category") or "cash").strip() or "cash"
            asset_risk_class = cash.get("asset_risk_class")

            # Use a special symbol for cash holdings
            cash_symbol = f"CASH_{cash_currency}"

            position_rows.append({
                "symbol": cash_symbol,
                "name": name,
                "market": account.market,
                "currency": cash_currency,
                "quantity": amount,
                "avg_cost": 1.0,
                "total_cost": amount,
                "last_price": 1.0,
                "market_value_base": 0.0,
                "unrealized_pnl_base": 0.0,
                "asset_category": asset_category,
                "asset_subcategory": None,
                "asset_risk_class": asset_risk_class,
            })

            # Cash does not need lot records
            cash_written += 1

        # Step 4: Write all positions (securities + cash) in one transaction
        self.repo.replace_positions_and_lots(
            account_id=account_id,
            cost_method=method,
            positions=position_rows,
            lots=lot_rows,
            valuation_currency=account.base_currency,
        )

        return {
            "account_id": account_id,
            "asset_count": len(position_rows) - cash_written,
            "cash_count": cash_written,
            "cleared_trade_count": cleared["trade_count"],
            "cleared_cash_count": cleared["cash_count"],
            "cleared_corporate_count": cleared["corporate_count"],
        }
    # ------------------------------------------------------------------
    # Event writes
    # ------------------------------------------------------------------
    def record_trade(
        self,
        *,
        account_id: int,
        asset_category: Optional[str] = None,
        asset_subcategory: Optional[str] = None,
        asset_risk_class: Optional[str] = None,
        symbol: str,
        name: Optional[str] = None,
        trade_date: date,
        side: str,
        quantity: float,
        price: float,
        fee: float = 0.0,
        tax: float = 0.0,
        market: Optional[str] = None,
        currency: Optional[str] = None,
        trade_uid: Optional[str] = None,
        dedup_hash: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        side_norm = (side or "").strip().lower()
        if side_norm not in VALID_SIDES:
            raise ValueError("side must be buy or sell")
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be > 0")
        if fee < 0 or tax < 0:
            raise ValueError("fee and tax must be >= 0")
        symbol_norm = self._normalize_symbol_for_storage(symbol)
        if not symbol_norm:
            raise ValueError("symbol is required")
        trade_uid_norm = (trade_uid or "").strip() or None
        dedup_hash_norm = (dedup_hash or "").strip() or None
        try:
            with self.repo.portfolio_write_session() as session:
                account = self._require_active_account_in_session(session=session, account_id=account_id)
                market_norm = self._normalize_market(market or account.market)
                currency_norm = self._normalize_currency(currency or self._default_currency_for_market(market_norm))
                name_norm = (name or "").strip() or None
                asset_category_norm = (asset_category or "").strip() or None
                asset_subcategory_norm = (asset_subcategory or "").strip() or None
                asset_risk_class_norm = (asset_risk_class or "").strip().upper() or None
                self._validate_trade_identity(
                    account_id=account_id,
                    trade_uid=trade_uid_norm,
                    dedup_hash=dedup_hash_norm,
                    session=session,
                    )
                realized_pnl = self._apply_trade_to_master_positions(
                    session=session,
                    account=account,
                    symbol=symbol_norm,
                    name=name_norm,
                    market=market_norm,
                    currency=currency_norm,
                    trade_date=trade_date,
                    side=side_norm,
                    quantity=float(quantity),
                    price=float(price),
                    fee=float(fee),
                    tax=float(tax),
                    asset_category=asset_category_norm,
                    asset_subcategory=asset_subcategory_norm,
                    asset_risk_class=asset_risk_class_norm,
                )
                row = self.repo.add_trade_in_session(
                    session=session,
                    account_id=account_id,
                    trade_uid=trade_uid_norm,
                    asset_category=asset_category_norm,
                    asset_subcategory=asset_subcategory_norm,
                    asset_risk_class=asset_risk_class_norm,
                    symbol=symbol_norm,
                    name=name_norm,
                    market=market_norm,
                    currency=currency_norm,
                    trade_date=trade_date,
                    side=side_norm,
                    quantity=float(quantity),
                    price=float(price),
                    fee=float(fee),
                    tax=float(tax),
                    realized_pnl=realized_pnl,
                    note=(note or "").strip() or None,
                    dedup_hash=dedup_hash_norm,
                )
                return {"id": int(row.id)}
        except (DuplicateTradeUidError, DuplicateTradeDedupHashError) as exc:
            raise PortfolioConflictError(str(exc)) from exc

    def record_cash_ledger(
        self,
        *,
        account_id: int,
        asset_category: Optional[str] = None,
        asset_subcategory: Optional[str] = None,
        asset_risk_class: Optional[str] = None,
        event_date: date,
        direction: str,
        amount: float,
        currency: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        direction_norm = (direction or "").strip().lower()
        if direction_norm not in VALID_CASH_DIRECTIONS:
            raise ValueError("direction must be in or out")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        with self.repo.portfolio_write_session() as session:
            account = self._require_active_account_in_session(session=session, account_id=account_id)
            currency_norm = self._normalize_currency(currency or account.base_currency)
            amount_delta = float(amount) if direction_norm == "in" else -float(amount)
            self._apply_cash_delta(
                session=session,
                account=account,
                market=account.market,
                currency=currency_norm,
                trade_date=event_date,
                amount_delta=amount_delta,
            )
            row = self.repo.add_cash_ledger_in_session(
                session=session,
                account_id=account_id,
                asset_category=(asset_category or "cash").strip() or "cash",
                asset_subcategory=(asset_subcategory or "").strip() or None,
                asset_risk_class=(asset_risk_class or "R1").strip().upper() or "R1",
                event_date=event_date,
                direction=direction_norm,
                amount=float(amount),
                currency=currency_norm,
                note=(note or "").strip() or None,
            )
            return {"id": int(row.id)}

    def record_corporate_action(
        self,
        *,
        account_id: int,
        symbol: str,
        asset_category: Optional[str] = None,
        asset_subcategory: Optional[str] = None,
        effective_date: date,
        action_type: str,
        market: Optional[str] = None,
        currency: Optional[str] = None,
        dividend_amount: Optional[float] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        action_type_norm = (action_type or "").strip().lower()
        if action_type_norm not in VALID_CORPORATE_ACTIONS:
            raise ValueError("action_type must be cash_dividend")

        if dividend_amount is None or dividend_amount <= 0:
            raise ValueError("dividend_amount must be > 0 for cash_dividend")
        with self.repo.portfolio_write_session() as session:
            account = self._require_active_account_in_session(session=session, account_id=account_id)
            market_norm = self._normalize_market(market or account.market)
            currency_norm = self._normalize_currency(currency or self._default_currency_for_market(market_norm))
            symbol_norm = self._normalize_symbol_for_storage(symbol)
            if not symbol_norm:
                raise ValueError("symbol is required")
            dividend_amount_value = float(dividend_amount)
            self._apply_cash_delta(
                session=session,
                account=account,
                market=market_norm,
                currency=currency_norm,
                trade_date=effective_date,
                amount_delta=dividend_amount_value,
            )
            self._apply_realized_pnl_to_position(
                session=session,
                account=account,
                symbol=symbol_norm,
                market=market_norm,
                currency=currency_norm,
                event_date=effective_date,
                realized_pnl=dividend_amount_value,
            )
            row = self.repo.add_corporate_action_in_session(
                session=session,
                account_id=account_id,
                symbol=symbol_norm,
                market=market_norm,
                currency=currency_norm,
                asset_category=(asset_category or "").strip() or None,
                asset_subcategory=(asset_subcategory or "").strip() or None,
                effective_date=effective_date,
                action_type=action_type_norm,
                cash_dividend_per_share=dividend_amount_value,
                realized_pnl=dividend_amount_value,
                note=(note or "").strip() or None,
            )
            return {"id": int(row.id)}

    def _apply_trade_to_master_positions(
        self,
        *,
        session: Any,
        account: Any,
        symbol: str,
        name: Optional[str],
        market: str,
        currency: str,
        trade_date: date,
        side: str,
        quantity: float,
        price: float,
        fee: float,
        tax: float,
        asset_category: Optional[str],
        asset_subcategory: Optional[str],
        asset_risk_class: Optional[str],
    ) -> float:
        from src.storage import PortfolioPosition

        method = "fifo"
        position = self.repo.get_position_in_session(
            session=session,
            account_id=int(account.id),
            symbol=symbol,
            market=market,
            currency=currency,
            cost_method=method,
        )
        old_quantity = float(position.quantity or 0.0) if position else 0.0
        old_avg_cost = float(position.avg_cost or 0.0) if position else 0.0
        realized_pnl = 0.0

        if side == "buy":
            total_quantity = old_quantity + quantity
            total_cost = old_avg_cost * old_quantity + price * quantity + fee + tax
            next_avg_cost = total_cost / total_quantity
            if position is None:
                position = PortfolioPosition(
                    account_id=int(account.id),
                    cost_method=method,
                    symbol=symbol,
                    name=name,
                    market=market,
                    currency=currency,
                    quantity=total_quantity,
                    avg_cost=next_avg_cost,
                    total_cost=total_quantity * next_avg_cost,
                    last_price=0.0,
                    market_value_base=0.0,
                    unrealized_pnl_base=0.0,
                    realized_pnl_base=0.0,
                    asset_category=asset_category,
                    asset_subcategory=asset_subcategory,
                    asset_risk_class=asset_risk_class,
                    valuation_currency=account.base_currency,
                )
                session.add(position)
            else:
                position.quantity = total_quantity
                position.avg_cost = next_avg_cost
                position.total_cost = total_quantity * next_avg_cost
                position.name = name or position.name
                position.asset_category = asset_category or position.asset_category
                position.asset_subcategory = asset_subcategory or position.asset_subcategory
                position.asset_risk_class = asset_risk_class or position.asset_risk_class
                position.updated_at = datetime.now()
            self._apply_cash_delta(
                session=session,
                account=account,
                market=market,
                currency=currency,
                trade_date=trade_date,
                amount_delta=-(price * quantity + fee + tax),
            )
            return 0.0

        if position is None or old_quantity + EPS < quantity:
            raise PortfolioOversellError(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=old_quantity,
            )

        next_quantity = old_quantity - quantity
        if next_quantity <= EPS:
            next_quantity = 0.0
        realized_pnl = (price - old_avg_cost) * quantity - fee - tax
        realized_pnl_base, _, _ = self._convert_amount(
            amount=realized_pnl,
            from_currency=currency,
            to_currency="CNY",
            as_of_date=trade_date,
        )
        position.quantity = next_quantity
        position.total_cost = next_quantity * old_avg_cost
        position.realized_pnl_base = float(position.realized_pnl_base or 0.0) + realized_pnl_base
        position.name = name or position.name
        position.asset_category = asset_category or position.asset_category
        position.asset_subcategory = asset_subcategory or position.asset_subcategory
        position.asset_risk_class = asset_risk_class or position.asset_risk_class
        position.updated_at = datetime.now()
        self._apply_cash_delta(
            session=session,
            account=account,
            market=market,
            currency=currency,
            trade_date=trade_date,
            amount_delta=price * quantity - fee - tax,
        )
        return realized_pnl

    def _apply_cash_delta(
        self,
        *,
        session: Any,
        account: Any,
        market: str,
        currency: str,
        trade_date: date,
        amount_delta: float,
    ) -> None:
        from src.storage import PortfolioPosition

        method = "fifo"
        cash_symbol = f"CASH_{currency}"
        cash_position = self.repo.get_position_in_session(
            session=session,
            account_id=int(account.id),
            symbol=cash_symbol,
            market=market,
            currency=currency,
            cost_method=method,
        )
        if cash_position is None:
            cash_position = PortfolioPosition(
                account_id=int(account.id),
                cost_method=method,
                symbol=cash_symbol,
                name=f"现金 {currency}",
                market=market,
                currency=currency,
                quantity=0.0,
                avg_cost=1.0,
                total_cost=0.0,
                last_price=1.0,
                market_value_base=0.0,
                unrealized_pnl_base=0.0,
                realized_pnl_base=0.0,
                asset_category="cash",
                asset_subcategory=None,
                asset_risk_class="R1",
                valuation_currency=account.base_currency,
            )
            session.add(cash_position)
        cash_position.quantity = float(cash_position.quantity or 0.0) + amount_delta
        cash_position.avg_cost = 1.0
        cash_position.total_cost = float(cash_position.quantity or 0.0)
        cash_position.last_price = 1.0
        cash_position.updated_at = datetime.now()
        self.repo._invalidate_account_cache_in_session(
            session=session,
            account_id=int(account.id),
            from_date=trade_date,
        )

    def _apply_realized_pnl_to_position(
        self,
        *,
        session: Any,
        account: Any,
        symbol: str,
        market: str,
        currency: str,
        event_date: date,
        realized_pnl: float,
    ) -> None:
        position = self.repo.get_position_in_session(
            session=session,
            account_id=int(account.id),
            symbol=symbol,
            market=market,
            currency=currency,
            cost_method="fifo",
        )
        if position is None:
            return
        realized_pnl_base, _, _ = self._convert_amount(
            amount=realized_pnl,
            from_currency=currency,
            to_currency="CNY",
            as_of_date=event_date,
        )
        position.realized_pnl_base = float(position.realized_pnl_base or 0.0) + realized_pnl_base
        position.updated_at = datetime.now()

    def list_trade_events(
        self,
        *,
        account_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if account_id is not None:
            self._require_active_account(account_id)
        page, page_size = self._validate_paging(page=page, page_size=page_size)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        symbol_filters: Optional[List[str]] = None
        if symbol is not None and symbol.strip():
            symbol_filters = self._build_symbol_filter_values(symbol)
            if not symbol_filters:
                raise ValueError("symbol is invalid")

        side_norm: Optional[str] = None
        if side is not None and side.strip():
            side_norm = side.strip().lower()
            if side_norm not in VALID_SIDES:
                raise ValueError("side must be buy or sell")

        rows, total = self.repo.query_trades(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbols=symbol_filters,
            side=side_norm,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._trade_row_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_cash_ledger_events(
        self,
        *,
        account_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        direction: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if account_id is not None:
            self._require_active_account(account_id)
        page, page_size = self._validate_paging(page=page, page_size=page_size)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        direction_norm: Optional[str] = None
        if direction is not None and direction.strip():
            direction_norm = direction.strip().lower()
            if direction_norm not in VALID_CASH_DIRECTIONS:
                raise ValueError("direction must be in or out")

        rows, total = self.repo.query_cash_ledger(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            direction=direction_norm,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._cash_ledger_row_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_corporate_action_events(
        self,
        *,
        account_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        symbol: Optional[str] = None,
        action_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if account_id is not None:
            self._require_active_account(account_id)
        page, page_size = self._validate_paging(page=page, page_size=page_size)
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must be <= date_to")

        symbol_filters: Optional[List[str]] = None
        if symbol is not None and symbol.strip():
            symbol_filters = self._build_symbol_filter_values(symbol)
            if not symbol_filters:
                raise ValueError("symbol is invalid")

        action_norm: Optional[str] = None
        if action_type is not None and action_type.strip():
            action_norm = action_type.strip().lower()
            if action_norm not in VALID_CORPORATE_ACTIONS:
                raise ValueError("action_type must be cash_dividend")

        rows, total = self.repo.query_corporate_actions(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            symbols=symbol_filters,
            action_type=action_norm,
            page=page,
            page_size=page_size,
        )
        return {
            "items": [self._corporate_action_row_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # ------------------------------------------------------------------
    # Snapshot replay
    # ------------------------------------------------------------------
    def get_portfolio_snapshot(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
    ) -> Dict[str, Any]:
        as_of_date = as_of or date.today()
        method = self._normalize_cost_method(cost_method)

        if account_id is not None:
            account = self._require_active_account(account_id)
            account_rows = [account]
        else:
            account_rows = self.repo.list_accounts(include_inactive=False)

        accounts_payload: List[Dict[str, Any]] = []
        aggregate_currency = "CNY"
        aggregate = {
            "total_cash": 0.0,
            "total_market_value": 0.0,
            "total_equity": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "fee_total": 0.0,
            "tax_total": 0.0,
            "fx_stale": False,
        }

        for account in account_rows:
            # Read directly from portfolio_positions instead of event replay.
            account_snapshot = self._build_snapshot_from_positions(
                account=account,
                as_of_date=as_of_date,
                cost_method=method,
            )

            # Do not replace positions - they are the source of truth.
            # Only update snapshot records for historical tracking.
            # DISABLED: self.repo.replace_positions_lots_and_snapshot(...)

            accounts_payload.append(account_snapshot["public"])

            cash_cny, stale_cash, _ = self._convert_amount(
                amount=account_snapshot["total_cash"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            mv_cny, stale_mv, _ = self._convert_amount(
                amount=account_snapshot["total_market_value"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            eq_cny, stale_eq, _ = self._convert_amount(
                amount=account_snapshot["total_equity"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            realized_cny, stale_realized, _ = self._convert_amount(
                amount=account_snapshot["realized_pnl"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            unrealized_cny, stale_unrealized, _ = self._convert_amount(
                amount=account_snapshot["unrealized_pnl"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            fee_cny, stale_fee, _ = self._convert_amount(
                amount=account_snapshot["fee_total"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )
            tax_cny, stale_tax, _ = self._convert_amount(
                amount=account_snapshot["tax_total"],
                from_currency=account.base_currency,
                to_currency=aggregate_currency,
                as_of_date=as_of_date,
            )

            aggregate["total_cash"] += cash_cny
            aggregate["total_market_value"] += mv_cny
            aggregate["total_equity"] += eq_cny
            aggregate["realized_pnl"] += realized_cny
            aggregate["unrealized_pnl"] += unrealized_cny
            aggregate["fee_total"] += fee_cny
            aggregate["tax_total"] += tax_cny
            aggregate["fx_stale"] = aggregate["fx_stale"] or any(
                [
                    stale_cash,
                    stale_mv,
                    stale_eq,
                    stale_realized,
                    stale_unrealized,
                    stale_fee,
                    stale_tax,
                ]
            )

        return {
            "as_of": as_of_date.isoformat(),
            "cost_method": method,
            "currency": aggregate_currency,
            "account_count": len(account_rows),
            "total_cash": round(aggregate["total_cash"], 6),
            "total_market_value": round(aggregate["total_market_value"], 6),
            "total_equity": round(aggregate["total_equity"], 6),
            "realized_pnl": round(aggregate["realized_pnl"], 6),
            "unrealized_pnl": round(aggregate["unrealized_pnl"], 6),
            "fee_total": round(aggregate["fee_total"], 6),
            "tax_total": round(aggregate["tax_total"], 6),
            "fx_stale": aggregate["fx_stale"],
            "accounts": accounts_payload,
        }

    def refresh_fx_rates(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Refresh account FX pairs online with stale fallback when fetch fails."""
        as_of_date = as_of or date.today()
        config = get_config()
        refresh_enabled = bool(getattr(config, "portfolio_fx_update_enabled", True))
        if account_id is not None:
            account_rows = [self._require_active_account(account_id)]
        else:
            account_rows = self.repo.list_accounts(include_inactive=False)

        summary = {
            "as_of": as_of_date.isoformat(),
            "account_count": len(account_rows),
            "refresh_enabled": refresh_enabled,
            "disabled_reason": None if refresh_enabled else PORTFOLIO_FX_REFRESH_DISABLED_REASON,
            "pair_count": 0,
            "updated_count": 0,
            "stale_count": 0,
            "error_count": 0,
        }
        for account in account_rows:
            item = self._refresh_account_fx_rates(
                account=account,
                as_of_date=as_of_date,
                refresh_enabled=refresh_enabled,
            )
            summary["pair_count"] += item["pair_count"]
            summary["updated_count"] += item["updated_count"]
            summary["stale_count"] += item["stale_count"]
            summary["error_count"] += item["error_count"]
        return summary

    def get_latest_fx_rates(
        self,
        *,
        to_currency: str = "CNY",
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        as_of_date = as_of or date.today()
        target_currency = self._normalize_currency(to_currency)
        rows = self.repo.list_latest_fx_rates(to_currency=target_currency, as_of=as_of_date)
        return {
            "as_of": as_of_date.isoformat(),
            "to_currency": target_currency,
            "items": [
                {
                    "pair": f"{target_currency}/{row.from_currency}",
                    "from_currency": row.from_currency,
                    "to_currency": row.to_currency,
                    "rate": float(row.rate),
                    "rate_date": row.rate_date.isoformat(),
                    "source": row.source or "unknown",
                    "is_stale": bool(row.is_stale),
                }
                for row in sorted(rows, key=lambda item: item.from_currency)
            ],
        }

    def list_positions(
        self,
        *,
        account_id: Optional[int] = None,
        cost_method: str = "fifo",
    ) -> Dict[str, Any]:
        method = self._normalize_cost_method(cost_method)
        self._sync_realized_pnl_base_from_events(account_id=account_id, cost_method=method)
        rows = self.repo.list_positions(account_id=account_id, cost_method=method)
        items: List[Dict[str, Any]] = []
        as_of_date = date.today()
        valuation_currency = "CNY"
        for position, account in rows:
            qty = float(position.quantity or 0.0)
            avg_cost_val = float(position.avg_cost or 0.0)
            last_price = float(position.last_price or 0.0)
            total_cost = float(position.total_cost or 0.0)
            local_market_value = qty * last_price
            market_base, stale_market, _ = self._convert_amount(
                amount=local_market_value,
                from_currency=position.currency,
                to_currency=valuation_currency,
                as_of_date=as_of_date,
            )
            cost_base, stale_cost, _ = self._convert_amount(
                amount=total_cost,
                from_currency=position.currency,
                to_currency=valuation_currency,
                as_of_date=as_of_date,
            )
            unrealized = market_base - cost_base
            unrealized_pct = None
            if abs(cost_base) > EPS:
                unrealized_pct = unrealized / cost_base * 100.0
            items.append(
                {
                    "id": int(position.id),
                    "account_id": int(account.id),
                    "account_name": account.name,
                    "owner_id": account.owner_id,
                    "base_currency": account.base_currency,
                    "cost_method": position.cost_method,
                    "symbol": position.symbol,
                    "name": position.name or None,
                    "market": position.market,
                    "currency": position.currency,
                    "quantity": qty,
                    "avg_cost": avg_cost_val,
                    "total_cost": total_cost,
                    "last_price": round(last_price, 8),
                    "price_change_pct": round(float(position.price_change_pct), 8) if position.price_change_pct is not None else None,
                    "market_value_base": round(market_base, 8),
                    "unrealized_pnl_base": round(unrealized, 8),
                    "realized_pnl_base": round(float(position.realized_pnl_base or 0.0), 8),
                    "unrealized_pnl_pct": round(unrealized_pct, 8) if unrealized_pct is not None else None,
                    "asset_category": position.asset_category,
                    "asset_subcategory": position.asset_subcategory,
                    "asset_risk_class": position.asset_risk_class,
                    "valuation_currency": valuation_currency,
                    "price_source": "cached",
                    "price_provider": None,
                    "price_date": position.updated_at.isoformat() if position.updated_at else None,
                    "price_stale": (position.last_price is not None and position.last_price <= 0) or stale_market or stale_cost,
                    "price_available": position.last_price is not None and position.last_price > 0,
                    "updated_at": position.updated_at.isoformat() if position.updated_at else None,
                }
            )
        return {"items": items, "total": len(items)}

    def _sync_realized_pnl_base_from_events(
        self,
        *,
        account_id: Optional[int],
        cost_method: str,
    ) -> None:
        if cost_method != "fifo":
            return
        from src.storage import PortfolioPosition

        accounts = [self._require_active_account(account_id)] if account_id is not None else self.repo.list_accounts(include_inactive=False)
        today = date.today()
        with self.repo.portfolio_write_session() as session:
            for account in accounts:
                realized_by_key: Dict[Tuple[str, str, str], float] = defaultdict(float)
                for trade in self.repo.list_trades_in_session(session=session, account_id=int(account.id), as_of=today):
                    amount = float(trade.realized_pnl or 0.0)
                    if abs(amount) <= EPS:
                        continue
                    converted, _, _ = self._convert_amount(
                        amount=amount,
                        from_currency=str(trade.currency or account.base_currency),
                        to_currency="CNY",
                        as_of_date=trade.trade_date,
                    )
                    realized_by_key[(trade.symbol, trade.market, trade.currency)] += converted
                for action in self.repo.list_corporate_actions_in_session(session=session, account_id=int(account.id), as_of=today):
                    amount = float(action.realized_pnl or action.cash_dividend_per_share or 0.0)
                    if abs(amount) <= EPS:
                        continue
                    converted, _, _ = self._convert_amount(
                        amount=amount,
                        from_currency=str(action.currency or account.base_currency),
                        to_currency="CNY",
                        as_of_date=action.effective_date,
                    )
                    realized_by_key[(action.symbol, action.market, action.currency)] += converted

                positions = session.execute(
                    select(PortfolioPosition).where(
                        and_(
                            PortfolioPosition.account_id == int(account.id),
                            PortfolioPosition.cost_method == cost_method,
                        )
                    )
                ).scalars().all()
                for position in positions:
                    key = (position.symbol, position.market, position.currency)
                    next_value = round(float(realized_by_key.get(key, 0.0)), 8)
                    if abs(float(position.realized_pnl_base or 0.0) - next_value) <= EPS:
                        continue
                    position.realized_pnl_base = next_value
                    position.updated_at = datetime.now()

    def realtime_revalue_positions(
        self,
        *,
        account_id: Optional[int] = None,
        cost_method: str = "fifo",
    ) -> Dict[str, Any]:
        data = self.list_positions(account_id=account_id, cost_method=cost_method)
        items: List[Dict[str, Any]] = []
        refreshed = 0
        failed = 0
        failures: List[str] = []
        today = date.today()

        for item in data["items"]:
            asset_category = (item.get("asset_category") or "").strip().lower()
            if asset_category != "stock":
                items.append(item)
                continue

            symbol = self._normalize_symbol_for_position(str(item.get("symbol") or ""))
            quote = self._fetch_realtime_position_price(symbol)
            if quote is None:
                failed += 1
                failures.append(str(item.get("symbol") or ""))
                items.append(item)
                continue

            qty = float(item.get("quantity") or 0.0)
            total_cost = float(item.get("total_cost") or 0.0)
            currency = str(item.get("currency") or "CNY")
            local_market_value = qty * quote.price
            market_base, stale_market, _ = self._convert_amount(
                amount=local_market_value,
                from_currency=currency,
                to_currency="CNY",
                as_of_date=today,
            )
            cost_base, stale_cost, _ = self._convert_amount(
                amount=total_cost,
                from_currency=currency,
                to_currency="CNY",
                as_of_date=today,
            )
            unrealized = market_base - cost_base
            unrealized_pct = (unrealized / cost_base * 100.0) if abs(cost_base) > EPS else None
            updated_item = dict(item)
            updated_item.update({
                "name": quote.name or item.get("name"),
                "last_price": round(float(quote.price), 8),
                "price_change_pct": round(float(quote.change_pct), 8) if quote.change_pct is not None else None,
                "market_value_base": round(market_base, 8),
                "unrealized_pnl_base": round(unrealized, 8),
                "unrealized_pnl_pct": round(unrealized_pct, 8) if unrealized_pct is not None else None,
                "price_source": "realtime_quote",
                "price_provider": quote.provider,
                "price_date": today.isoformat(),
                "price_stale": stale_market or stale_cost,
                "price_available": True,
            })
            items.append(updated_item)
            refreshed += 1

        return {"items": items, "total": len(items), "refreshed": refreshed, "failed": failed, "failures": failures[:20]}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _validate_trade_identity(
        self,
        *,
        account_id: int,
        trade_uid: Optional[str],
        dedup_hash: Optional[str],
        session: Optional[Any] = None,
    ) -> None:
        if trade_uid and self._has_trade_uid(account_id=account_id, trade_uid=trade_uid, session=session):
            raise PortfolioConflictError(f"Duplicate trade_uid for account_id={account_id}: {trade_uid}")
        if dedup_hash and self._has_trade_dedup_hash(account_id=account_id, dedup_hash=dedup_hash, session=session):
            raise PortfolioConflictError(f"Duplicate dedup_hash for account_id={account_id}: {dedup_hash}")

    def _validate_sell_quantity(
        self,
        *,
        account_id: int,
        symbol: str,
        market: str,
        currency: str,
        trade_date: date,
        quantity: float,
        session: Optional[Any] = None,
    ) -> None:
        key = (
            self._normalize_symbol_for_position(symbol),
            self._normalize_market(market),
            self._normalize_currency(currency),
        )
        available_quantity = self._calculate_available_quantity(
            account_id=account_id,
            key=key,
            as_of_date=trade_date,
            session=session,
        )
        if available_quantity + EPS < quantity:
            raise PortfolioOversellError(
                symbol=key[0],
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=available_quantity,
            )

    def _calculate_available_quantity(
        self,
        *,
        account_id: int,
        key: Tuple[str, str, str],
        as_of_date: date,
        session: Optional[Any] = None,
    ) -> float:
        if session is None:
            trades = self.repo.list_trades(account_id, as_of=as_of_date)
            corporate_actions = self.repo.list_corporate_actions(account_id, as_of=as_of_date)
        else:
            trades = self.repo.list_trades_in_session(session=session, account_id=account_id, as_of=as_of_date)
            corporate_actions = self.repo.list_corporate_actions_in_session(
                session=session,
                account_id=account_id,
                as_of=as_of_date,
            )

        events = []
        for row in corporate_actions:
            event_key = (
                self._normalize_symbol_for_position(row.symbol),
                self._normalize_market(row.market),
                self._normalize_currency(row.currency),
            )
            if event_key == key:
                events.append(("corp", row.effective_date, row.id, row))
        for row in trades:
            event_key = (
                self._normalize_symbol_for_position(row.symbol),
                self._normalize_market(row.market),
                self._normalize_currency(row.currency),
            )
            if event_key == key:
                events.append(("trade", row.trade_date, row.id, row))

        # Quantity validation only depends on position-changing events for one symbol.
        # Cash ledger entries do not affect shares held, so we keep the same corp->trade
        # ordering as full replay without pulling unrelated cash events into this path.
        event_priority = {"corp": 1, "trade": 2}
        events.sort(key=lambda item: (item[1], event_priority[item[0]], item[2]))

        quantity_held = 0.0
        for event_type, event_date, _, event in events:
            if event_type == "corp":
                continue

            qty = float(event.quantity or 0.0)
            if qty <= 0:
                raise ValueError(f"Invalid trade quantity for {key[0]}")
            side = (event.side or "").strip().lower()
            if side == "buy":
                quantity_held += qty
                continue
            if side != "sell":
                raise ValueError(f"Unsupported trade side: {event.side}")
            if quantity_held + EPS < qty:
                raise PortfolioOversellError(
                    symbol=key[0],
                    trade_date=event_date,
                    requested_quantity=qty,
                    available_quantity=quantity_held,
                )
            quantity_held -= qty
            if quantity_held <= EPS:
                quantity_held = 0.0

        return quantity_held

    def _build_snapshot_from_positions(
        self,
        *,
        account: Any,
        as_of_date: date,
        cost_method: str,
    ) -> Dict[str, Any]:
        """Build snapshot by reading directly from portfolio_positions (source of truth).

        This bypasses event replay and treats portfolio_positions as the authoritative
        record of current holdings. Cash is managed as an asset class within positions.
        """
        from src.storage import PortfolioPosition

        with self.repo.db.get_session() as session:
            rows = session.execute(
                select(PortfolioPosition)
                .where(
                    and_(
                        PortfolioPosition.account_id == account.id,
                        PortfolioPosition.cost_method == cost_method,
                    )
                )
            ).scalars().all()

        positions_cache: List[Dict[str, Any]] = []
        cash_by_currency: List[Dict[str, Any]] = []
        total_cash = 0.0
        total_market_value = 0.0
        total_cost = 0.0
        realized_pnl_base = 0.0
        fx_stale = False

        for pos in rows:
            is_cash = pos.asset_category == "cash" or pos.symbol.startswith("CASH_")
            qty = float(pos.quantity or 0)
            avg_cost = float(pos.avg_cost or 0)
            last_price = float(pos.last_price or avg_cost) if not is_cash else 1.0

            market_value = qty * last_price
            total_cost += qty * avg_cost
            total_market_value += market_value
            realized_pnl_base += float(pos.realized_pnl_base or 0.0)

            if is_cash:
                total_cash += market_value
                cash_by_currency.append({
                    "currency": pos.currency,
                    "amount": market_value,
                    "amount_base": market_value,  # Will be converted later
                })

            positions_cache.append({
                "symbol": pos.symbol,
                "name": pos.name,
                "market": pos.market,
                "currency": pos.currency,
                "quantity": qty,
                "avg_cost": avg_cost,
                "total_cost": qty * avg_cost,
                "last_price": last_price,
                "market_value_base": market_value,
                "unrealized_pnl_base": market_value - (qty * avg_cost),
                "realized_pnl_base": float(pos.realized_pnl_base or 0.0),
                "asset_category": pos.asset_category,
                "asset_subcategory": pos.asset_subcategory,
                "asset_risk_class": pos.asset_risk_class,
            })

        total_equity = total_cash + total_market_value

        # Convert cash to base currency and collect FX rates
        for cash_item in cash_by_currency:
            if cash_item["currency"] != account.base_currency:
                converted, stale, source = self._convert_amount(
                    amount=cash_item["amount"],
                    from_currency=cash_item["currency"],
                    to_currency=account.base_currency,
                    as_of_date=as_of_date,
                )
                cash_item["amount_base"] = converted
                if stale or source == "fallback_1_to_1":
                    fx_stale = True
            else:
                cash_item["amount_base"] = cash_item["amount"]

        # Generate FX rates for non-base currencies
        fx_rates: List[Dict[str, Any]] = []
        for currency in sorted({item["currency"] for item in cash_by_currency if item["currency"] != account.base_currency}):
            converted_one, stale_rate, source = self._convert_amount(
                amount=1.0,
                from_currency=currency,
                to_currency=account.base_currency,
                as_of_date=as_of_date,
            )
            fx_rates.append({
                "pair": f"{account.base_currency}/{currency}",
                "rate": round(float(converted_one), 6),
                "is_stale": bool(stale_rate or source == "fallback_1_to_1"),
            })

        account_payload = {
            "account_id": account.id,
            "account_name": account.name,
            "owner_id": account.owner_id,
            "broker": account.broker,
            "market": account.market,
            "base_currency": account.base_currency,
            "as_of": as_of_date.isoformat(),
            "cost_method": cost_method,
            "total_cash": round(total_cash, 6),
            "total_market_value": round(total_market_value, 6),
            "total_equity": round(total_equity, 6),
            "realized_pnl": round(realized_pnl_base, 6),
            "unrealized_pnl": round(total_market_value - total_cost, 6),
            "fee_total": 0.0,
            "tax_total": 0.0,
            "fx_stale": fx_stale,
            "cash_by_currency": [],
            "fx_rates": [],
            "positions": positions_cache,
        }

        return {
            "public": account_payload,
            "payload": account_payload,
            "positions_cache": positions_cache,
            "lots_cache": [],
            "total_cash": total_cash,
            "total_market_value": total_market_value,
            "total_equity": total_equity,
            "realized_pnl": realized_pnl_base,
            "unrealized_pnl": total_market_value - total_cost,
            "fee_total": 0.0,
            "tax_total": 0.0,
        }

    def _replay_account(self, *, account: Any, as_of_date: date, cost_method: str) -> Dict[str, Any]:
        trades = self.repo.list_trades(account.id, as_of=as_of_date)
        cash_ledger = self.repo.list_cash_ledger(account.id, as_of=as_of_date)
        corporate_actions = self.repo.list_corporate_actions(account.id, as_of=as_of_date)

        events = []
        for row in cash_ledger:
            events.append(("cash", row.event_date, row.id, row))
        for row in trades:
            events.append(("trade", row.trade_date, row.id, row))
        for row in corporate_actions:
            events.append(("corp", row.effective_date, row.id, row))

        # Same-day deterministic ordering: cash -> cash dividend -> trade.
        event_priority = {"cash": 0, "corp": 1, "trade": 2}
        events.sort(key=lambda item: (item[1], event_priority[item[0]], item[2]))

        cash_balances: Dict[str, float] = defaultdict(float)
        fees_total_base = 0.0
        taxes_total_base = 0.0
        realized_pnl_base = 0.0
        fx_stale = False

        fifo_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        avg_state: Dict[Tuple[str, str, str], _AvgState] = defaultdict(_AvgState)
        position_metadata: Dict[Tuple[str, str, str], _PositionMetadata] = defaultdict(_PositionMetadata)

        for event_type, event_date, _, event in events:
            if event_type == "cash":
                currency = self._normalize_currency(event.currency)
                amount = float(event.amount or 0.0)
                if event.direction == "in":
                    cash_balances[currency] += amount
                elif event.direction == "out":
                    cash_balances[currency] -= amount
                else:
                    raise ValueError(f"Unsupported cash direction: {event.direction}")
                continue

            if event_type == "trade":
                key = (
                    self._normalize_symbol_for_position(event.symbol),
                    self._normalize_market(event.market),
                    self._normalize_currency(event.currency),
                )
                qty = float(event.quantity or 0.0)
                price = float(event.price or 0.0)
                fee = float(event.fee or 0.0)
                tax = float(event.tax or 0.0)
                if qty <= 0 or price <= 0:
                    raise ValueError(f"Invalid trade quantity or price for {event.symbol}")

                gross = qty * price
                side = (event.side or "").lower().strip()
                if side == "buy":
                    metadata = position_metadata[key]
                    metadata.name = self._extract_asset_name_from_note(event.note) or metadata.name
                    metadata.asset_category = (event.asset_category or "").strip() or metadata.asset_category
                    metadata.asset_subcategory = (event.asset_subcategory or "").strip() or metadata.asset_subcategory
                    metadata.asset_risk_class = (event.asset_risk_class or "").strip().upper() or metadata.asset_risk_class
                if side == "buy":
                    cash_balances[key[2]] -= (gross + fee + tax)
                    if cost_method == "fifo":
                        unit_cost = (gross + fee + tax) / qty
                        fifo_lots[key].append(
                            {
                                "symbol": key[0],
                                "market": key[1],
                                "currency": key[2],
                                "open_date": event_date,
                                "remaining_quantity": qty,
                                "unit_cost": unit_cost,
                                "source_trade_id": event.id,
                                "asset_category": position_metadata[key].asset_category,
                                "asset_subcategory": position_metadata[key].asset_subcategory,
                                "asset_risk_class": position_metadata[key].asset_risk_class,
                            }
                        )
                    else:
                        state = avg_state[key]
                        state.quantity += qty
                        state.total_cost += (gross + fee + tax)
                        state.name = position_metadata[key].name
                        state.asset_category = position_metadata[key].asset_category
                        state.asset_subcategory = position_metadata[key].asset_subcategory
                        state.asset_risk_class = position_metadata[key].asset_risk_class
                elif side == "sell":
                    cash_balances[key[2]] += (gross - fee - tax)
                    proceeds_net = gross - fee - tax
                    if cost_method == "fifo":
                        cost_basis = self._consume_fifo_lots(
                            fifo_lots[key],
                            qty,
                            key[0],
                            event_date,
                        )
                    else:
                        cost_basis = self._consume_avg_position(
                            avg_state[key],
                            qty,
                            key[0],
                            event_date,
                        )
                    realized_local = proceeds_net - cost_basis
                    realized_base, stale_realized, _ = self._convert_amount(
                        amount=realized_local,
                        from_currency=key[2],
                        to_currency=account.base_currency,
                        as_of_date=event_date,
                    )
                    realized_pnl_base += realized_base
                    fx_stale = fx_stale or stale_realized
                else:
                    raise ValueError(f"Unsupported trade side: {event.side}")

                fee_base, stale_fee, _ = self._convert_amount(
                    amount=fee,
                    from_currency=key[2],
                    to_currency=account.base_currency,
                    as_of_date=event_date,
                )
                tax_base, stale_tax, _ = self._convert_amount(
                    amount=tax,
                    from_currency=key[2],
                    to_currency=account.base_currency,
                    as_of_date=event_date,
                )
                fees_total_base += fee_base
                taxes_total_base += tax_base
                fx_stale = fx_stale or stale_fee or stale_tax
                continue

            if event_type == "corp":
                key = (
                    self._normalize_symbol_for_position(event.symbol),
                    self._normalize_market(event.market),
                    self._normalize_currency(event.currency),
                )
                action_type = (event.action_type or "").strip().lower()
                if action_type == "cash_dividend":
                    dividend_amount = float(event.realized_pnl or event.cash_dividend_per_share or 0.0)
                    if dividend_amount > 0:
                        cash_balances[key[2]] += dividend_amount
                        dividend_base, stale_dividend, _ = self._convert_amount(
                            amount=dividend_amount,
                            from_currency=key[2],
                            to_currency=account.base_currency,
                            as_of_date=event_date,
                        )
                        realized_pnl_base += dividend_base
                        fx_stale = fx_stale or stale_dividend
                else:
                    raise ValueError(f"Unsupported cash dividend event type: {event.action_type}")

        position_rows, lot_rows, market_value_base, total_cost_base, stale_pos = self._build_positions(
            account=account,
            as_of_date=as_of_date,
            cost_method=cost_method,
            fifo_lots=fifo_lots,
            avg_state=avg_state,
            position_metadata=position_metadata,
        )
        fx_stale = fx_stale or stale_pos

        total_cash_base = 0.0
        cash_by_currency: List[Dict[str, Any]] = []
        for currency, amount in cash_balances.items():
            converted, stale, _ = self._convert_amount(
                amount=amount,
                from_currency=currency,
                to_currency=account.base_currency,
                as_of_date=as_of_date,
            )
            total_cash_base += converted
            fx_stale = fx_stale or stale
            cash_by_currency.append(
                {
                    "currency": currency,
                    "amount": round(float(amount), 6),
                    "amount_base": round(float(converted), 6),
                }
            )

        fx_rates: List[Dict[str, Any]] = []
        for currency in sorted({item["currency"] for item in cash_by_currency if item["currency"] != account.base_currency}):
            converted_one, stale_rate, source = self._convert_amount(
                amount=1.0,
                from_currency=currency,
                to_currency=account.base_currency,
                as_of_date=as_of_date,
            )
            fx_rates.append(
                {
                    "pair": f"{account.base_currency}/{currency}",
                    "rate": round(float(converted_one), 6),
                    "is_stale": bool(stale_rate or source == "fallback_1_to_1"),
                }
            )

        unrealized_pnl_base = market_value_base - total_cost_base
        total_equity_base = total_cash_base + market_value_base

        account_payload = {
            "account_id": account.id,
            "account_name": account.name,
            "owner_id": account.owner_id,
            "broker": account.broker,
            "market": account.market,
            "base_currency": account.base_currency,
            "as_of": as_of_date.isoformat(),
            "cost_method": cost_method,
            "total_cash": round(total_cash_base, 6),
            "total_market_value": round(market_value_base, 6),
            "total_equity": round(total_equity_base, 6),
            "realized_pnl": round(realized_pnl_base, 6),
            "unrealized_pnl": round(unrealized_pnl_base, 6),
            "fee_total": round(fees_total_base, 6),
            "tax_total": round(taxes_total_base, 6),
            "fx_stale": fx_stale,
            "cash_by_currency": cash_by_currency,
            "fx_rates": fx_rates,
            "positions": position_rows,
        }

        return {
            "public": account_payload,
            "payload": account_payload,
            "positions_cache": position_rows,
            "lots_cache": lot_rows,
            "total_cash": float(total_cash_base),
            "total_market_value": float(market_value_base),
            "total_equity": float(total_equity_base),
            "realized_pnl": float(realized_pnl_base),
            "unrealized_pnl": float(unrealized_pnl_base),
            "fee_total": float(fees_total_base),
            "tax_total": float(taxes_total_base),
            "fx_stale": fx_stale,
        }

    def _build_positions(
        self,
        *,
        account: Any,
        as_of_date: date,
        cost_method: str,
        fifo_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]],
        avg_state: Dict[Tuple[str, str, str], _AvgState],
        position_metadata: Dict[Tuple[str, str, str], _PositionMetadata],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float, float, bool]:
        position_rows: List[Dict[str, Any]] = []
        lot_rows: List[Dict[str, Any]] = []
        market_value_base = 0.0
        total_cost_base = 0.0
        fx_stale = False

        keys: Iterable[Tuple[str, str, str]]
        if cost_method == "fifo":
            keys = list(fifo_lots.keys())
        else:
            keys = list(avg_state.keys())

        for key in sorted(keys):
            symbol, market, currency = key
            metadata = position_metadata.get(key, _PositionMetadata())

            if cost_method == "fifo":
                active_lots = [lot for lot in fifo_lots[key] if lot["remaining_quantity"] > EPS]
                qty = sum(float(lot["remaining_quantity"]) for lot in active_lots)
                if qty <= EPS:
                    continue
                total_cost = sum(float(lot["remaining_quantity"]) * float(lot["unit_cost"]) for lot in active_lots)
                avg_cost = total_cost / qty
                lot_rows.extend(active_lots)
            else:
                state = avg_state[key]
                qty = float(state.quantity)
                total_cost = float(state.total_cost)
                if qty <= EPS:
                    continue
                avg_cost = total_cost / qty
                metadata = _PositionMetadata(
                    name=state.name,
                    asset_category=state.asset_category,
                    asset_subcategory=state.asset_subcategory,
                    asset_risk_class=state.asset_risk_class,
                )
                lot_rows.append(
                    {
                        "symbol": symbol,
                        "market": market,
                        "currency": currency,
                        "open_date": as_of_date,
                        "remaining_quantity": qty,
                        "unit_cost": avg_cost,
                        "source_trade_id": None,
                    }
                )

            price_info = self._resolve_cached_position_price(
                symbol=symbol, market=market, currency=currency,
                account_base_currency=account.base_currency, as_of_date=as_of_date,
                asset_category=metadata.asset_category,
            )
            last_price = price_info["price"]

            if price_info["available"]:
                local_market_value = qty * float(last_price)
                market_base, stale_market, _ = self._convert_amount(
                    amount=local_market_value,
                    from_currency=currency,
                    to_currency=account.base_currency,
                    as_of_date=as_of_date,
                )
                cost_base, stale_cost, _ = self._convert_amount(
                    amount=total_cost,
                    from_currency=currency,
                    to_currency=account.base_currency,
                    as_of_date=as_of_date,
                )
                unrealized_base = market_base - cost_base
                fx_stale = fx_stale or stale_market or stale_cost
            else:
                market_base = 0.0
                cost_base = 0.0
                unrealized_base = 0.0

            unrealized_pct = None
            if abs(cost_base) > EPS:
                unrealized_pct = unrealized_base / cost_base * 100.0

            position_rows.append(
                    {
                        "symbol": symbol,
                        "market": market,
                        "currency": currency,
                        "name": metadata.name,
                        "quantity": round(qty, 8),
                    "avg_cost": round(avg_cost, 8),
                    "total_cost": round(total_cost, 8),
                    "last_price": round(float(last_price), 8),
                    "market_value_base": round(market_base, 8),
                    "unrealized_pnl_base": round(unrealized_base, 8),
                    "unrealized_pnl_pct": round(unrealized_pct, 8) if unrealized_pct is not None else None,
                    "asset_category": metadata.asset_category,
                    "asset_subcategory": metadata.asset_subcategory,
                    "asset_risk_class": metadata.asset_risk_class,
                    "valuation_currency": account.base_currency,
                    "price_source": price_info["source"],
                    "price_provider": price_info["provider"],
                    "price_date": price_info["price_date"],
                    "price_stale": price_info["stale"],
                    "price_available": price_info["available"],
                }
            )

            market_value_base += market_base
            total_cost_base += cost_base

        return position_rows, lot_rows, market_value_base, total_cost_base, fx_stale

    def _resolve_cached_position_price(
        self,
        *,
        symbol: str,
        market: str,
        currency: str,
        account_base_currency: str,
        as_of_date: date,
        asset_category: Optional[str],
    ) -> Dict[str, Any]:
        """Read price from cached portfolio_positions.last_price instead of real-time APIs."""
        from src.storage import get_db, PortfolioPosition

        db = get_db()
        with db.get_session() as s:
            pos = s.query(PortfolioPosition).filter_by(
                symbol=self._normalize_symbol_for_storage(symbol),
                currency=currency,
                market=market,
                cost_method="fifo",
            ).first()
            if pos is None:
                pos = s.query(PortfolioPosition).filter_by(
                    symbol=symbol,
                ).first()

            if pos and pos.last_price and pos.last_price > 0:
                return {
                    "price": float(pos.last_price),
                    "source": "cached",
                    "provider": None,
                    "price_date": pos.updated_at.isoformat() if pos.updated_at else None,
                    "stale": False,
                    "available": True,
                }

        return {
            "price": 0.0,
            "source": "missing",
            "provider": None,
            "price_date": None,
            "stale": True,
            "available": False,
        }

    def _resolve_position_price(
        self,
        *,
        symbol: str,
        as_of_date: date,
        asset_category: Optional[str] = None,
    ) -> _ResolvedPositionPrice:
        today = date.today()

        if (asset_category or "").lower() == "fund":
            fund_nav, fund_date = self._fetch_fund_nav(symbol)
            if fund_nav is not None and fund_nav > 0:
                return _ResolvedPositionPrice(
                    price=float(fund_nav),
                    source="fund_nav",
                    price_date=fund_date,
                    is_stale=(fund_date < as_of_date if fund_date else True),
                    is_available=True,
                    provider="akshare",
                )

            close = self.repo.get_latest_close_with_date(symbol=symbol, as_of=as_of_date)
            if close is not None:
                close_price, close_date = close
                if close_price > 0:
                    return _ResolvedPositionPrice(
                        price=float(close_price),
                        source="history_close",
                        price_date=close_date,
                        is_stale=close_date < as_of_date,
                        is_available=True,
                    )
            return _ResolvedPositionPrice(
                price=0.0,
                source="missing",
                price_date=None,
                is_stale=True,
                is_available=False,
            )

        if as_of_date == today:
            realtime_quote = self._fetch_realtime_position_price(symbol)
            if realtime_quote is not None and realtime_quote.price > 0:
                return _ResolvedPositionPrice(
                    price=float(realtime_quote.price),
                    source="realtime_quote",
                    price_date=today,
                    is_stale=False,
                    is_available=True,
                    provider=realtime_quote.provider,
                    change_pct=realtime_quote.change_pct,
                )

        close = self.repo.get_latest_close_with_date(symbol=symbol, as_of=as_of_date)
        if close is not None:
            close_price, close_date = close
            if close_price > 0:
                return _ResolvedPositionPrice(
                    price=float(close_price),
                    source="history_close",
                    price_date=close_date,
                    is_stale=close_date < as_of_date,
                    is_available=True,
                )

        return _ResolvedPositionPrice(
            price=0.0,
            source="missing",
            price_date=None,
            is_stale=True,
            is_available=False,
        )

    @staticmethod
    def _fetch_realtime_position_price(symbol: str) -> Optional[_RealtimePositionQuote]:
        try:
            from data_provider.base import DataFetcherManager

            quote = DataFetcherManager().get_realtime_quote(symbol, log_final_failure=False)
        except Exception as exc:
            logger.warning("Failed to fetch realtime portfolio price for %s: %s", symbol, exc)
            return None

        if quote is None:
            return None

        price = getattr(quote, "price", None)
        try:
            numeric_price = float(price)
        except (TypeError, ValueError):
            return None

        if numeric_price <= 0:
            return None

        source = getattr(quote, "source", None)
        provider = getattr(source, "value", None) or (str(source) if source is not None else None)
        name = getattr(quote, "name", None)
        change_pct = getattr(quote, "change_pct", None)
        try:
            numeric_change_pct = float(change_pct) if change_pct is not None else None
        except (TypeError, ValueError):
            numeric_change_pct = None
        return _RealtimePositionQuote(numeric_price, provider, name, numeric_change_pct)

    @staticmethod
    def _fetch_fund_nav(symbol: str) -> Tuple[Optional[float], Optional[str]]:
        """Fetch open fund NAV from Akshare (fund_open_fund_info_em)."""
        try:
            import akshare as ak
        except ImportError:
            return None, None

        try:
            info = ak.fund_individual_basic_info_xq(symbol=symbol)
            name = None
            for _, row in info.iterrows():
                if "基金名称" in str(row.get("item", "")):
                    name = str(row.get("value", ""))
                    break
        except Exception:
            name = None

        try:
            df = ak.fund_open_fund_info_em(symbol=symbol, indicator="单位净值走势", period="3月")
        except Exception as exc:
            logger.warning("Failed to fetch fund NAV for %s: %s", symbol, exc)
            return None, name

        if df is None or df.empty:
            return None, name

        latest = df.iloc[-1]
        try:
            nav_str = str(latest.get("单位净值", ""))
            nav = float(nav_str) if nav_str else None
        except (TypeError, ValueError):
            return None, name

        if nav is None or nav <= 0:
            return None, name

        return nav, name
        return numeric_price, provider

    @staticmethod
    def _normalize_symbol_for_storage(symbol: str) -> str:
        return canonical_stock_code(symbol)

    @staticmethod
    def _extract_asset_name_from_note(note: Optional[str]) -> Optional[str]:
        for segment in (note or "").split("|"):
            entry = segment.strip()
            if entry.startswith("name:"):
                value = entry[5:].strip()
                return value or None
        return None

    def adjust_position(
        self,
        *,
        position_id: int,
        account_id: Optional[int],
        quantity: Optional[float] = None,
        avg_cost: Optional[float] = None,
        last_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Manually adjust a single position's quantity, avg_cost, or last_price."""
        fields: Dict[str, Any] = {}
        if quantity is not None:
            fields["quantity"] = float(quantity)
        if avg_cost is not None:
            fields["avg_cost"] = float(avg_cost)
        if last_price is not None:
            fields["last_price"] = float(last_price)

        if not fields:
            raise ValueError("At least one of quantity, avg_cost, last_price must be provided")

        updated = self.repo.update_position_fields(
            position_id=position_id,
            account_id=account_id,
            fields=fields,
        )
        if updated is None:
            raise ValueError(f"Position not found: id={position_id}")

        return {
            "id": updated.id,
            "symbol": updated.symbol,
            "market": updated.market,
            "currency": updated.currency,
            "quantity": float(updated.quantity or 0),
            "avg_cost": float(updated.avg_cost or 0),
            "last_price": float(updated.last_price or 0),
            "total_cost": float(updated.total_cost or 0),
            "updated_at": updated.updated_at.isoformat() if updated.updated_at else None,
        }

    @staticmethod
    def _normalize_symbol_for_position(symbol: str) -> str:
        if not (symbol or "").strip():
            return ""

        raw = canonical_stock_code(symbol)
        if len(raw) >= 8 and raw[:2] in {"SH", "SZ", "BJ"} and raw[2:].isdigit():
            return raw

        if "." in raw:
            base, suffix = raw.rsplit(".", 1)
            if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
                exchange = "SH" if suffix == "SS" else suffix
                return f"{exchange}{base}"

        return canonical_stock_code(normalize_stock_code(symbol))

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        Canonicalization for symbol filtering with exchange-qualified input preservation.

        Keep explicit A-share exchange annotations (SH/SZ/BJ) intact to avoid collapsing
        different exchange variants of the same 6-digit core code.
        """
        raw = canonical_stock_code(symbol)
        if not raw:
            return ""

        if len(raw) >= 8 and raw[:2] in {"SH", "SZ", "BJ"} and raw[2:].isdigit():
            return raw

        if "." in raw:
            base, suffix = raw.rsplit(".", 1)
            if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
                exchange = "SH" if suffix == "SS" else suffix
                return f"{exchange}{base}"

        return canonical_stock_code(normalize_stock_code(symbol))

    @classmethod
    def _build_symbol_filter_values(cls, symbol: str) -> List[str]:
        original = (symbol or "").strip().upper()
        normalized = cls._normalize_symbol(original)
        if not normalized:
            return []

        seen: Set[str] = set()
        values: List[str] = []

        def _add(value: Optional[str]) -> None:
            candidate = (value or "").strip().upper()
            if candidate and candidate not in seen:
                seen.add(candidate)
                values.append(candidate)

        _add(original)
        _add(normalized)

        if normalized.startswith("HK"):
            hk_digits = normalized[2:]
            if hk_digits.isdigit() and len(hk_digits) == 5:
                legacy_hk_digits = str(int(hk_digits))
                _add(f"HK{hk_digits}")
                _add(f"HK{legacy_hk_digits}")
                _add(f"{hk_digits}.HK")
                _add(f"{legacy_hk_digits}.HK")
            return values

        explicit_exchange: Optional[str] = None
        if len(original) >= 8 and original[:2] in {"SH", "SZ", "BJ"} and original[2:].isdigit():
            explicit_exchange = original[:2]
            explicit_code = original[2:]
        elif "." in original:
            base, suffix = original.rsplit(".", 1)
            if base.isdigit() and suffix in {"SH", "SS", "SZ", "BJ"}:
                explicit_exchange = "SH" if suffix == "SS" else suffix
                explicit_code = base
            else:
                explicit_code = None
        else:
            explicit_code = None

        if normalized.isdigit():
            if len(normalized) == 6:
                exchanges = [explicit_exchange] if explicit_exchange else ["SH", "SZ", "BJ"]
                for exchange in exchanges:
                    if exchange is None:
                        continue
                    _add(f"{exchange}{normalized}")
                    _add(f"{normalized}.{'SS' if exchange == 'SH' else exchange}")
                    if exchange == "SH":
                        _add(f"{normalized}.SH")
            return values

        if explicit_exchange is not None and explicit_code is not None and explicit_code.isdigit():
            if len(explicit_code) == 6:
                _add(f"{explicit_exchange}{explicit_code}")
                _add(f"{explicit_code}.{'SS' if explicit_exchange == 'SH' else explicit_exchange}")
                if explicit_exchange == "SH":
                    _add(f"{explicit_code}.SH")
            elif len(normalized) == 5:
                _add(f"HK{normalized}")
                _add(f"{normalized}.HK")

        return values

    @staticmethod
    def _consume_fifo_lots(
        lots: List[Dict[str, Any]],
        quantity: float,
        symbol: str,
        trade_date: Optional[date] = None,
    ) -> float:
        remaining = quantity
        cost_basis = 0.0
        while remaining > EPS:
            if not lots:
                raise PortfolioOversellError(
                    symbol=symbol,
                    trade_date=trade_date,
                    requested_quantity=quantity,
                    available_quantity=quantity - remaining,
                )
            head = lots[0]
            take = min(remaining, float(head["remaining_quantity"]))
            cost_basis += take * float(head["unit_cost"])
            head["remaining_quantity"] = float(head["remaining_quantity"]) - take
            remaining -= take
            if head["remaining_quantity"] <= EPS:
                lots.pop(0)
        return cost_basis

    @staticmethod
    def _consume_avg_position(
        state: _AvgState,
        quantity: float,
        symbol: str,
        trade_date: Optional[date] = None,
    ) -> float:
        if state.quantity + EPS < quantity:
            raise PortfolioOversellError(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=state.quantity,
            )
        if state.quantity <= EPS:
            raise PortfolioOversellError(
                symbol=symbol,
                trade_date=trade_date,
                requested_quantity=quantity,
                available_quantity=0.0,
            )
        avg_cost = state.total_cost / state.quantity
        cost_basis = avg_cost * quantity
        state.quantity -= quantity
        state.total_cost -= cost_basis
        if state.quantity <= EPS:
            state.quantity = 0.0
            state.total_cost = 0.0
        return cost_basis

    @staticmethod
    def _held_quantity(
        *,
        key: Tuple[str, str, str],
        cost_method: str,
        fifo_lots: Dict[Tuple[str, str, str], List[Dict[str, Any]]],
        avg_state: Dict[Tuple[str, str, str], _AvgState],
    ) -> float:
        if cost_method == "fifo":
            return sum(float(lot["remaining_quantity"]) for lot in fifo_lots.get(key, []))
        return float(avg_state.get(key, _AvgState()).quantity)

    def _convert_amount(
        self,
        *,
        amount: float,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Tuple[float, bool, str]:
        from_norm = self._normalize_currency(from_currency)
        to_norm = self._normalize_currency(to_currency)
        if abs(amount) <= EPS:
            return 0.0, False, "zero"
        if from_norm == to_norm:
            return float(amount), False, "identity"

        direct = self.repo.get_latest_fx_rate(
            from_currency=from_norm,
            to_currency=to_norm,
            as_of=as_of_date,
        )
        if direct is not None and direct.rate > 0:
            return float(amount) * float(direct.rate), bool(direct.is_stale), "direct_rate"

        inverse = self.repo.get_latest_fx_rate(
            from_currency=to_norm,
            to_currency=from_norm,
            as_of=as_of_date,
        )
        if inverse is not None and inverse.rate > 0:
            return float(amount) / float(inverse.rate), bool(inverse.is_stale), "inverse_rate"

        # P0 fallback: keep pipeline available even when FX cache is missing.
        return float(amount), True, "fallback_1_to_1"

    def convert_amount(
        self,
        *,
        amount: float,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Tuple[float, bool, str]:
        """Public conversion entry for cross-service consumers."""
        return self._convert_amount(
            amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            as_of_date=as_of_date,
        )

    def _list_account_refresh_fx_currencies(
        self,
        *,
        account: Any,
        as_of_date: date,
        strict: bool = True,
    ) -> List[str]:
        """Return distinct non-base currencies participating in refresh for one account."""
        base_currency = self._normalize_currency(account.base_currency)
        currencies: Set[str] = set()
        rows = list(self.repo.list_trades(account.id, as_of=as_of_date))
        rows.extend(self.repo.list_cash_ledger(account.id, as_of=as_of_date))
        for row in rows:
            try:
                currency = self._normalize_currency(row.currency)
            except ValueError:
                if strict:
                    raise
                logger.warning(
                    "Skip invalid FX refresh currency for account %s on %s: %r",
                    account.id,
                    as_of_date.isoformat(),
                    getattr(row, "currency", None),
                )
                continue
            if currency != base_currency:
                currencies.add(currency)
        return sorted(currencies)

    def _refresh_account_fx_rates(
        self,
        *,
        account: Any,
        as_of_date: date,
        refresh_enabled: bool,
    ) -> Dict[str, int]:
        """Refresh FX pairs for one account and keep stale fallback on failures."""
        refresh_currencies = self._list_account_refresh_fx_currencies(
            account=account,
            as_of_date=as_of_date,
            strict=refresh_enabled,
        )
        if not refresh_enabled:
            return {
                "pair_count": len(refresh_currencies),
                "updated_count": 0,
                "stale_count": 0,
                "error_count": 0,
            }

        base_currency = self._normalize_currency(account.base_currency)
        summary = {
            "pair_count": len(refresh_currencies),
            "updated_count": 0,
            "stale_count": 0,
            "error_count": 0,
        }
        for from_currency in refresh_currencies:
            try:
                rate = self._fetch_fx_rate_from_yfinance(
                    from_currency=from_currency,
                    to_currency=base_currency,
                    as_of_date=as_of_date,
                )
                if rate is not None and rate > 0:
                    self.repo.save_fx_rate(
                        from_currency=from_currency,
                        to_currency=base_currency,
                        rate_date=as_of_date,
                        rate=rate,
                        source="yfinance",
                        is_stale=False,
                    )
                    summary["updated_count"] += 1
                    continue
            except Exception as exc:
                logger.warning(
                    "FX online fetch failed for %s/%s on %s: %s",
                    from_currency,
                    base_currency,
                    as_of_date.isoformat(),
                    exc,
                )

            fallback = self.repo.get_latest_fx_rate(
                from_currency=from_currency,
                to_currency=base_currency,
                as_of=as_of_date,
            )
            if fallback is not None and float(fallback.rate or 0.0) > 0:
                self.repo.save_fx_rate(
                    from_currency=from_currency,
                    to_currency=base_currency,
                    rate_date=as_of_date,
                    rate=float(fallback.rate),
                    source=(fallback.source or "cache_fallback"),
                    is_stale=True,
                )
                summary["stale_count"] += 1
            else:
                summary["error_count"] += 1
        return summary

    @staticmethod
    def _fetch_fx_rate_from_yfinance(
        *,
        from_currency: str,
        to_currency: str,
        as_of_date: date,
    ) -> Optional[float]:
        """Fetch latest available FX close rate around as_of date."""
        if yf is None:
            return None
        symbol = f"{from_currency}{to_currency}=X"
        ticker = yf.Ticker(symbol)
        history = ticker.history(
            start=(as_of_date - timedelta(days=7)).isoformat(),
            end=(as_of_date + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
        )
        if history is None or history.empty or "Close" not in history:
            return None
        close = history["Close"].dropna()
        if close.empty:
            return None
        value = float(close.iloc[-1])
        if value <= 0:
            return None
        return value

    def _require_active_account(self, account_id: int) -> Any:
        account = self.repo.get_account(account_id, include_inactive=False)
        if account is None:
            raise ValueError(f"Active account not found: {account_id}")
        return account

    def _require_active_account_in_session(self, *, session: Any, account_id: int) -> Any:
        account = self.repo.get_account_in_session(
            session=session,
            account_id=account_id,
            include_inactive=False,
        )
        if account is None:
            raise ValueError(f"Active account not found: {account_id}")
        return account

    def _has_trade_uid(self, *, account_id: int, trade_uid: str, session: Optional[Any] = None) -> bool:
        if session is None:
            return self.repo.has_trade_uid(account_id, trade_uid)
        return self.repo.has_trade_uid_in_session(session=session, account_id=account_id, trade_uid=trade_uid)

    def _has_trade_dedup_hash(
        self,
        *,
        account_id: int,
        dedup_hash: str,
        session: Optional[Any] = None,
    ) -> bool:
        if session is None:
            return self.repo.has_trade_dedup_hash(account_id, dedup_hash)
        return self.repo.has_trade_dedup_hash_in_session(
            session=session,
            account_id=account_id,
            dedup_hash=dedup_hash,
        )

    @staticmethod
    def _account_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": row.id,
            "owner_id": row.owner_id,
            "name": row.name,
            "broker": row.broker,
            "market": row.market,
            "base_currency": row.base_currency,
            "is_active": bool(row.is_active),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _trade_row_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": int(row.id),
            "account_id": int(row.account_id),
            "trade_uid": row.trade_uid,
            "asset_category": row.asset_category,
            "asset_subcategory": row.asset_subcategory,
            "asset_risk_class": row.asset_risk_class,
            "symbol": row.symbol,
            "name": row.name,
            "market": row.market,
            "currency": row.currency,
            "trade_date": row.trade_date.isoformat() if row.trade_date else "",
            "side": row.side,
            "quantity": float(row.quantity),
            "price": float(row.price),
            "fee": float(row.fee),
            "tax": float(row.tax),
            "realized_pnl": float(row.realized_pnl or 0.0),
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _cash_ledger_row_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": int(row.id),
            "account_id": int(row.account_id),
            "asset_category": row.asset_category,
            "asset_subcategory": row.asset_subcategory,
            "asset_risk_class": row.asset_risk_class,
            "event_date": row.event_date.isoformat() if row.event_date else "",
            "direction": row.direction,
            "amount": float(row.amount),
            "currency": row.currency,
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _corporate_action_row_to_dict(row: Any) -> Dict[str, Any]:
        return {
            "id": int(row.id),
            "account_id": int(row.account_id),
            "symbol": row.symbol,
            "market": row.market,
            "currency": row.currency,
            "asset_category": row.asset_category,
            "asset_subcategory": row.asset_subcategory,
            "effective_date": row.effective_date.isoformat() if row.effective_date else "",
            "action_type": row.action_type,
            "dividend_amount": (
                float(row.cash_dividend_per_share) if row.cash_dividend_per_share is not None else None
            ),
            "realized_pnl": float(row.realized_pnl or 0.0),
            "note": row.note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def _validate_paging(*, page: int, page_size: int) -> Tuple[int, int]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be in [1, 100]")
        return page, page_size

    @staticmethod
    def _normalize_market(value: str) -> str:
        market = (value or "").strip().lower()
        if market not in VALID_MARKETS:
            raise ValueError("market must be one of: cn, hk, us")
        return market

    @staticmethod
    def _normalize_currency(value: str) -> str:
        currency = (value or "").strip().upper()
        if not currency:
            raise ValueError("currency is required")
        return currency

    @staticmethod
    def _normalize_cost_method(value: str) -> str:
        method = (value or "").strip().lower()
        if method not in VALID_COST_METHODS:
            raise ValueError("cost_method must be fifo or avg")
        return method

    @staticmethod
    def _default_currency_for_market(market: str) -> str:
        if market == "hk":
            return "HKD"
        if market == "us":
            return "USD"
        return "CNY"

    # ------------------------------------------------------------------
    # Price refresh operations (batch update of cached prices)
    # ------------------------------------------------------------------

    def refresh_all_prices(
        self,
        *,
        refresh_positions: bool = True,
        refresh_indices: bool = True,
        refresh_fx: bool = False,
    ) -> Dict[str, Any]:
        """Refresh non-cash position prices and dashboard market quotes."""
        results: Dict[str, Any] = {}

        if refresh_positions:
            results["positions"] = self._refresh_position_prices()

        if refresh_indices:
            results["indices"] = self._refresh_index_prices()

        if refresh_fx:
            results["fx"] = self._refresh_fx_rates()

        return results

    def _refresh_position_prices(self) -> Dict[str, Any]:
        from src.storage import get_db, PortfolioPosition

        db = get_db()
        with db.get_session() as s:
            positions = s.query(PortfolioPosition).filter(
                PortfolioPosition.quantity > EPS,
                PortfolioPosition.asset_category.in_(("stock", "fund")),
            ).all()

        refreshed = 0
        failed = 0
        failures: List[str] = []

        for position in positions:
            asset_cat = position.asset_category
            symbol = self._normalize_symbol_for_position(position.symbol)
            quote = self._resolve_latest_price_with_name(symbol, asset_cat)

            if quote is not None and quote.price > 0:
                with db.get_session() as s:
                    s.query(PortfolioPosition).filter_by(id=position.id).update({
                        PortfolioPosition.last_price: quote.price,
                        PortfolioPosition.price_change_pct: quote.change_pct,
                        PortfolioPosition.name: quote.name or position.name,
                        PortfolioPosition.updated_at: datetime.now(),
                    })
                    s.commit()
                refreshed += 1
            else:
                failed += 1
                failures.append(f"{position.symbol} (resolved=missing)")

        return {"refreshed": refreshed, "failed": failed, "failures": failures[:20]}

    def _refresh_index_prices(self) -> Dict[str, Any]:
        from data_provider.base import DataFetcherManager
        from src.services.market_trend_service import MARKET_INDICES
        from src.storage import StockDaily, get_db

        manager = DataFetcherManager()
        refreshed = 0
        failed = 0
        failures: List[str] = []

        for idx_cfg in MARKET_INDICES:
            code = idx_cfg["code"]
            try:
                quote = manager.get_realtime_quote(code, log_final_failure=False)
                if quote is None or getattr(quote, "price", None) is None or float(quote.price) <= 0:
                    failed += 1
                    failures.append(f"{code} not found")
                    continue
                today = date.today()
                with get_db().get_session() as s:
                    row = s.query(StockDaily).filter_by(code=code, date=today).one_or_none()
                    if row is None:
                        row = StockDaily(code=code, date=today)
                        s.add(row)
                    price = float(quote.price)
                    row.close = price
                    row.open = getattr(quote, "open_price", None) or price
                    row.high = getattr(quote, "high", None) or price
                    row.low = getattr(quote, "low", None) or price
                    row.volume = getattr(quote, "volume", None)
                    row.amount = getattr(quote, "amount", None)
                    row.pct_chg = getattr(quote, "change_pct", None)
                    row.data_source = "realtime_quote"
                    row.updated_at = datetime.now()
                    s.commit()
                refreshed += 1
            except Exception as e:
                failed += 1
                failures.append(f"{code}: {e}")

        return {"refreshed": refreshed, "failed": failed, "failures": failures[:20]}

    def _refresh_fx_rates(self) -> Dict[str, Any]:
        from src.storage import get_db, PortfolioFxRate

        refreshed = 0
        failed = 0
        failures: List[str] = []

        try:
            import akshare as ak
            currency_df = ak.currency_boc_safe()
            if currency_df is not None and not currency_df.empty:
                # Get the last row (most recent date - data is sorted ascending by date)
                latest_row = currency_df.iloc[-1]
                
                # Map Chinese names to currency codes
                target_currencies = {
                    "美元": "USD",
                    "港元": "HKD", 
                    "欧元": "EUR",
                    "英镑": "GBP",
                    "日元": "JPY",
                }
                
                for cn_name, currency_code in target_currencies.items():
                    if cn_name in latest_row.index:
                        try:
                            rate = float(latest_row[cn_name])
                            if rate > 0:
                                # BOC rates are per 100 units, convert to per 1 unit
                                rate = rate / 100.0
                                db = get_db()
                                with db.get_session() as s:
                                    existing = s.query(PortfolioFxRate).filter_by(
                                        from_currency=currency_code,
                                        to_currency="CNY",
                                        is_stale=False,
                                    ).first()

                                    if existing:
                                        existing.rate = rate
                                        existing.updated_at = datetime.now()
                                        existing.is_stale = False
                                        existing.rate_date = date.today()
                                    else:
                                        s.add(PortfolioFxRate(
                                            from_currency=currency_code,
                                            to_currency="CNY",
                                            rate_date=date.today(),
                                            rate=rate,
                                            source="boc",
                                            is_stale=False,
                                        ))
                                    s.commit()
                                    refreshed += 1
                            else:
                                failed += 1
                                failures.append(f"{currency_code}/CNY (rate={rate})")
                        except (TypeError, ValueError, KeyError) as e:
                            failed += 1
                            failures.append(f"{currency_code}/CNY ({e})")
                    else:
                        failed += 1
                        failures.append(f"{currency_code}/CNY (column not found)")
            else:
                failed += 5
                failures.append("Currency data not available")
        except ImportError:
            failures.append("akshare not installed")
        except Exception as e:
            failures.append(f"FX fetch failed: {e}")
            failed += 5

        return {"refreshed": refreshed, "failed": failed, "failures": failures[:20]}

    def _resolve_latest_price(self, symbol: str, asset_category: Optional[str]) -> Tuple[Optional[float], str]:
        """Resolve latest price for a symbol (price, source)."""
        result = self._resolve_latest_price_with_name(symbol, asset_category)
        return (result.price, result.provider or "realtime_quote") if result is not None else (None, "missing")

    def _resolve_latest_price_with_name(self, symbol: str, asset_category: Optional[str]) -> Optional[_RealtimePositionQuote]:
        if (asset_category or "").lower() == "fund":
            fund_nav, fund_name = self._fetch_fund_nav(symbol)
            if fund_nav is not None and fund_nav > 0:
                return _RealtimePositionQuote(fund_nav, "fund_nav", fund_name, None)
        else:
            realtime_quote = self._fetch_realtime_position_price(symbol)
            if realtime_quote is not None and realtime_quote.price > 0:
                return realtime_quote

        return None
