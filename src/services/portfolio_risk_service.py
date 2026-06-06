# -*- coding: utf-8 -*-
"""Portfolio risk service for concentration, drawdown and stop-loss proximity."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from src.config import Config, get_config
from src.repositories.portfolio_repo import PortfolioRepository
from src.services.portfolio_service import PortfolioService


class PortfolioRiskService:
    """Compute portfolio risk blocks on top of replayed snapshot data."""

    def __init__(
        self,
        *,
        repo: Optional[PortfolioRepository] = None,
        portfolio_service: Optional[PortfolioService] = None,
        config: Optional[Config] = None,
    ):
        self.repo = repo or PortfolioRepository()
        self.portfolio_service = portfolio_service or PortfolioService(repo=self.repo)
        self.config = config or get_config()

    def get_risk_report(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[date] = None,
        cost_method: str = "fifo",
    ) -> Dict[str, Any]:
        as_of_date = as_of or date.today()
        snapshot = self.portfolio_service.get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of_date,
            cost_method=cost_method,
        )

        thresholds = {
            "concentration_alert_pct": self._resolve_concentration_threshold(snapshot, as_of_date),
            "drawdown_alert_pct": self._resolve_drawdown_threshold(),
            "stop_loss_alert_pct": float(getattr(self.config, "portfolio_risk_stop_loss_alert_pct", 10.0)),
            "stop_loss_near_ratio": float(getattr(self.config, "portfolio_risk_stop_loss_near_ratio", 0.8)),
            "lookback_days": int(getattr(self.config, "portfolio_risk_lookback_days", 180)),
        }

        concentration = self._build_concentration(
            snapshot,
            thresholds["concentration_alert_pct"],
            as_of_date=as_of_date,
        )
        single_name_concentration = self._build_single_name_concentration(
            snapshot,
            as_of_date=as_of_date,
        )
        self._ensure_drawdown_snapshot_window(
            account_id=account_id,
            as_of_date=as_of_date,
            cost_method=cost_method,
            lookback_days=thresholds["lookback_days"],
        )
        drawdown = self._build_drawdown(
            account_id=account_id,
            as_of_date=as_of_date,
            cost_method=cost_method,
            threshold_pct=thresholds["drawdown_alert_pct"],
            lookback_days=thresholds["lookback_days"],
        )
        stop_loss = self._build_stop_loss(snapshot, thresholds)

        return {
            "as_of": as_of_date.isoformat(),
            "account_id": account_id,
            "cost_method": cost_method,
            "currency": snapshot["currency"],
            "thresholds": thresholds,
            "concentration": concentration,
            "single_name_concentration": single_name_concentration,
            "drawdown": drawdown,
            "stop_loss": stop_loss,
        }

    @staticmethod
    def _resolve_drawdown_threshold() -> float:
        """Resolve drawdown alert threshold from active allocation plan.

        Returns max_drawdown * 0.9 from the active plan, or defaults to 6.0 (%)
        when no active plan exists.
        """
        from src.storage import get_db, AssetAllocationPlan

        db = get_db()
        try:
            with db.get_session() as session:
                active_plan = session.query(AssetAllocationPlan).filter(
                    AssetAllocationPlan.is_active == True
                ).first()
                if active_plan and active_plan.max_drawdown is not None:
                    return float(active_plan.max_drawdown) * 90.0
        except Exception:
            pass
        return 6.0

    @staticmethod
    def _resolve_concentration_threshold(snapshot: Dict[str, Any], as_of_date: date) -> float:
        """Resolve concentration alert threshold from active allocation plan.

        Computes the actual R4+R5 weight from current positions and compares
        with the planned R4+R5 ratio. Returns the planned ratio as threshold.
        When no active plan exists, defaults to 35.0.
        """
        from src.storage import get_db, AssetAllocationPlan

        db = get_db()
        try:
            with db.get_session() as session:
                active_plan = session.query(AssetAllocationPlan).filter(
                    AssetAllocationPlan.is_active == True
                ).first()
                if active_plan:
                    return float(active_plan.r4_ratio or 0.0) + float(active_plan.r5_ratio or 0.0)
        except Exception:
            pass
        return 35.0

    def _ensure_drawdown_snapshot_window(
        self,
        *,
        account_id: Optional[int],
        as_of_date: date,
        cost_method: str,
        lookback_days: int,
    ) -> None:
        if lookback_days <= 0:
            return

        start_date = self._resolve_backfill_start_date(
            account_id=account_id,
            as_of_date=as_of_date,
            lookback_days=lookback_days,
        )
        if start_date > as_of_date:
            return

        existing_rows = self.repo.list_daily_snapshots_for_risk(
            as_of=as_of_date,
            cost_method=cost_method,
            account_id=account_id,
            lookback_days=lookback_days,
        )
        if account_id is not None:
            existing_dates = {row.snapshot_date for row in existing_rows if int(row.account_id) == int(account_id)}
            current_date = start_date
            while current_date <= as_of_date:
                if current_date not in existing_dates:
                    self.portfolio_service.get_portfolio_snapshot(
                        account_id=account_id,
                        as_of=current_date,
                        cost_method=cost_method,
                    )
                    existing_dates.add(current_date)
                current_date += timedelta(days=1)
            return

        account_ids = [int(account.id) for account in self.repo.list_accounts(include_inactive=False)]
        if not account_ids:
            return
        existing_pairs = {(int(row.account_id), row.snapshot_date) for row in existing_rows}
        current_date = start_date
        while current_date <= as_of_date:
            if not all((aid, current_date) in existing_pairs for aid in account_ids):
                self.portfolio_service.get_portfolio_snapshot(
                    account_id=None,
                    as_of=current_date,
                    cost_method=cost_method,
                )
                for aid in account_ids:
                    existing_pairs.add((aid, current_date))
            current_date += timedelta(days=1)

    def _resolve_backfill_start_date(
        self,
        *,
        account_id: Optional[int],
        as_of_date: date,
        lookback_days: int,
    ) -> date:
        window_start = as_of_date - timedelta(days=lookback_days)
        if account_id is not None:
            first_activity = self.repo.get_first_activity_date(account_id=account_id, as_of=as_of_date)
            return max(window_start, first_activity or as_of_date)

        first_activity_candidates: List[date] = []
        for account in self.repo.list_accounts(include_inactive=False):
            first_activity = self.repo.get_first_activity_date(account_id=int(account.id), as_of=as_of_date)
            if first_activity is not None:
                first_activity_candidates.append(first_activity)
        if not first_activity_candidates:
            return as_of_date
        return max(window_start, min(first_activity_candidates))

    def _build_concentration(self, snapshot: Dict[str, Any], threshold_pct: float, *, as_of_date: date) -> Dict[str, Any]:
        """Build concentration risk block based on R4+R5 equity allocation.

        Compares actual R4+R5 weight against the planned ratio from active
        allocation plan. Alert triggers when actual exceeds planned.
        """
        total_mv = float(snapshot.get("total_equity", 0.0) or 0.0)
        r4_r5_exposure = 0.0
        exposure_by_symbol: Dict[str, float] = {}

        for account in snapshot.get("accounts", []):
            for pos in account.get("positions", []):
                symbol = str(pos.get("symbol") or "").strip().upper()
                if not symbol:
                    continue
                market_value = float(pos.get("market_value_base") or 0.0)
                valuation_currency = str(pos.get("valuation_currency") or account.get("base_currency") or "CNY")
                converted, _, _ = self.portfolio_service.convert_amount(
                    amount=market_value,
                    from_currency=valuation_currency,
                    to_currency="CNY",
                    as_of_date=as_of_date,
                )
                exposure_by_symbol[symbol] = exposure_by_symbol.get(symbol, 0.0) + converted

                risk_class = str(pos.get("asset_risk_class") or "").strip().upper()
                if risk_class in ("R4", "R5"):
                    r4_r5_exposure += converted

        r4_r5_weight = (r4_r5_exposure / total_mv * 100.0) if total_mv > 0 else 0.0

        rows = []
        for symbol, exposure in sorted(exposure_by_symbol.items(), key=lambda item: item[1], reverse=True):
            weight = (exposure / total_mv * 100.0) if total_mv > 0 else 0.0
            rows.append(
                {
                    "symbol": symbol,
                    "market_value_base": round(exposure, 6),
                    "weight_pct": round(weight, 4),
                    "is_alert": False,
                }
            )

        return {
            "total_market_value": round(total_mv, 6),
            "top_weight_pct": round(r4_r5_weight, 4),
            "alert": bool(threshold_pct > 0 and r4_r5_weight > threshold_pct),
            "top_positions": rows[:10],
            "r4_r5_planned_pct": round(threshold_pct, 4),
            "r4_r5_actual_pct": round(r4_r5_weight, 4),
        }

    def _build_single_name_concentration(
        self,
        snapshot: Dict[str, Any],
        *,
        as_of_date: date,
    ) -> Dict[str, Any]:
        """Build single-name concentration risk block.

        Alerts when:
        - Any single stock exceeds 50% of total stock assets
        - Any single fund exceeds 30% of total fund assets
        Returns count of breached items separately for stocks and funds.
        """
        thresholds = {
            "stock_alert_pct": 50.0,
            "fund_alert_pct": 30.0,
        }

        total_by_category: Dict[str, float] = {}
        exposure_by_name: Dict[str, Dict[str, float]] = {}

        for account in snapshot.get("accounts", []):
            for pos in account.get("positions", []):
                category = str(pos.get("asset_category") or "").strip().lower()
                symbol = str(pos.get("symbol") or "").strip().upper()
                if not category or not symbol:
                    continue
                if category not in ("stock", "fund"):
                    continue

                market_value = float(pos.get("market_value_base") or 0.0)
                valuation_currency = str(pos.get("valuation_currency") or account.get("base_currency") or "CNY")
                converted, _, _ = self.portfolio_service.convert_amount(
                    amount=market_value,
                    from_currency=valuation_currency,
                    to_currency="CNY",
                    as_of_date=as_of_date,
                )

                total_by_category[category] = total_by_category.get(category, 0.0) + converted
                if category not in exposure_by_name:
                    exposure_by_name[category] = {}
                exposure_by_name[category][symbol] = exposure_by_name[category].get(symbol, 0.0) + converted

        stock_breach_count = 0
        fund_breach_count = 0
        alerts: List[Dict[str, Any]] = []

        for category, names in exposure_by_name.items():
            total = total_by_category.get(category, 0.0)
            threshold = thresholds.get(f"{category}_alert_pct", 50.0)

            for symbol, exposure in sorted(names.items(), key=lambda item: item[1], reverse=True):
                weight = (exposure / total * 100.0) if total > 0 else 0.0
                is_alert = weight > threshold
                if is_alert:
                    if category == "stock":
                        stock_breach_count += 1
                    else:
                        fund_breach_count += 1
                alerts.append(
                    {
                        "symbol": symbol,
                        "asset_category": category,
                        "market_value_base": round(exposure, 6),
                        "weight_pct": round(weight, 4),
                        "threshold_pct": threshold,
                        "is_alert": is_alert,
                    }
                )

        return {
            "alert": stock_breach_count > 0 or fund_breach_count > 0,
            "stock_breach_count": stock_breach_count,
            "fund_breach_count": fund_breach_count,
            "thresholds": thresholds,
            "items": alerts[:20],
        }

    def _build_drawdown(
        self,
        *,
        account_id: Optional[int],
        as_of_date: date,
        cost_method: str,
        threshold_pct: float,
        lookback_days: int,
    ) -> Dict[str, Any]:
        rows = self.repo.list_daily_snapshots_for_risk(
            as_of=as_of_date,
            cost_method=cost_method,
            account_id=account_id,
            lookback_days=lookback_days,
        )
        if not rows:
            return {
                "series_points": 0,
                "max_drawdown_pct": 0.0,
                "current_drawdown_pct": 0.0,
                "alert": False,
                "fx_stale": False,
            }

        grouped: Dict[str, float] = {}
        stale_flag = False
        for row in rows:
            key = row.snapshot_date.isoformat()
            converted, stale, _ = self.portfolio_service.convert_amount(
                amount=float(row.total_equity or 0.0),
                from_currency=str(row.base_currency or "CNY"),
                to_currency="CNY",
                as_of_date=row.snapshot_date,
            )
            grouped[key] = grouped.get(key, 0.0) + converted
            stale_flag = stale_flag or stale or bool(row.fx_stale)

        series: List[Tuple[str, float]] = sorted(grouped.items(), key=lambda item: item[0])
        peak = 0.0
        max_drawdown = 0.0
        current_drawdown = 0.0
        for _, equity in series:
            peak = max(peak, equity)
            if peak <= 0:
                drawdown = 0.0
            else:
                drawdown = (peak - equity) / peak * 100.0
            max_drawdown = max(max_drawdown, drawdown)
            current_drawdown = drawdown

        return {
            "series_points": len(series),
            "max_drawdown_pct": round(max_drawdown, 4),
            "current_drawdown_pct": round(current_drawdown, 4),
            "alert": bool(max_drawdown >= threshold_pct),
            "fx_stale": stale_flag,
        }

    @staticmethod
    def _build_stop_loss(snapshot: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
        stop_loss_pct = float(thresholds["stop_loss_alert_pct"])

        warnings: List[Dict[str, Any]] = []
        for account in snapshot.get("accounts", []):
            for pos in account.get("positions", []):
                avg_cost = float(pos.get("avg_cost", 0.0) or 0.0)
                last_price = float(pos.get("last_price", 0.0) or 0.0)
                if avg_cost <= 0:
                    continue
                loss_pct = max(0.0, (avg_cost - last_price) / avg_cost * 100.0)
                if loss_pct <= 0:
                    continue
                warnings.append(
                    {
                        "account_id": account.get("account_id"),
                        "symbol": pos.get("symbol"),
                        "asset_category": str(pos.get("asset_category") or "").strip().lower(),
                        "avg_cost": round(avg_cost, 8),
                        "last_price": round(last_price, 8),
                        "loss_pct": round(loss_pct, 4),
                        "is_triggered": bool(loss_pct >= stop_loss_pct),
                    }
                )

        warnings.sort(key=lambda item: item["loss_pct"], reverse=True)
        return {
            "triggered_count": sum(1 for w in warnings if w["is_triggered"]),
            "near_count": len([w for w in warnings if not w["is_triggered"] and w["loss_pct"] > 0]),
            "items": warnings[:20],
        }
