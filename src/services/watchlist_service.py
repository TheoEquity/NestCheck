# -*- coding: utf-8 -*-
"""Watchlist service."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.repositories.watchlist_repo import WatchlistConflictError, WatchlistRepository
from src.services.watchlist_signal_service import WatchlistSignalService
from src.storage import AlertRuleRecord, AlertTriggerRecord, WatchlistItem


VALID_MARKETS = {"cn", "hk", "us"}
VALID_ASSET_CATEGORIES = {"fund", "stock", "wealth"}
VALID_PRIORITIES = {"low", "medium", "high"}
VALID_FREQUENCIES = {"daily", "weekly", "manual"}
logger = logging.getLogger(__name__)


class WatchlistNotFoundError(ValueError):
    pass


class WatchlistService:
    def __init__(self, repo: Optional[WatchlistRepository] = None):
        self.repo = repo or WatchlistRepository()

    def create_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        row = self.repo.create_item(self._normalize_payload(payload))
        row.name = self._resolve_official_name(row)
        self.repo._update_item_name(row.id, row.name)
        if row.asset_category == "fund":
            self._seed_fund_nav(row.symbol)
        signal_summary = None
        if row.asset_category in ("stock", "fund") and row.watch_enabled:
            try:
                WatchlistSignalService().refresh_item(row)
                signal_summary = WatchlistSignalService().latest_signals_for_items([row.id]).get(row.id)
            except Exception as exc:
                logger.warning("Watchlist initial signal refresh failed for %s: %s", row.symbol, exc, exc_info=True)
        quote_summary = self.repo.quote_summary_for_items([row]).get(row.id, {})
        return self._serialize_item(row, quote_summary=quote_summary, signal_summary=signal_summary)

    def list_items(
        self,
        *,
        asset_category: Optional[str] = None,
        watch_enabled: Optional[bool] = None,
    ) -> Dict[str, Any]:
        rows, total = self.repo.list_items(asset_category=asset_category, watch_enabled=watch_enabled)
        summaries = self.repo.alert_summary_for_items(rows)
        quote_summaries = self.repo.quote_summary_for_items(rows)
        analysis_summaries = self.repo.stock_analysis_summary_for_items(rows)
        signal_summaries = WatchlistSignalService().latest_signals_for_items([row.id for row in rows])
        return {
            "items": [
                self._serialize_item(
                    row,
                    summaries.get(row.id),
                    analysis_summaries.get(row.id),
                    quote_summaries.get(row.id),
                    signal_summaries.get(row.id),
                )
                for row in rows
            ],
            "total": total,
            "market_review": self.repo.latest_market_review_summary(),
        }

    def get_item(self, item_id: int) -> Dict[str, Any]:
        row = self.repo.get_item(item_id)
        if row is None:
            raise WatchlistNotFoundError(f"关注标的不存在: {item_id}")
        summary = self.repo.alert_summary_for_items([row]).get(row.id)
        analysis_summary = self.repo.stock_analysis_summary_for_items([row]).get(row.id)
        quote_summary = self.repo.quote_summary_for_items([row]).get(row.id)
        signal_summary = WatchlistSignalService().latest_signals_for_items([row.id]).get(row.id)
        return self._serialize_item(row, summary, analysis_summary, quote_summary, signal_summary)

    def update_item(self, item_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        fields = self._normalize_payload(payload, partial=True)
        if not fields:
            raise ValueError("No fields provided for update")
        row = self.repo.update_item(item_id, fields)
        if row is None:
            raise WatchlistNotFoundError(f"关注标的不存在: {item_id}")
        return self._serialize_item(row)

    def delete_item(self, item_id: int) -> bool:
        return self.repo.delete_item(item_id)

    def move_item(self, item_id: int, direction: str) -> Dict[str, Any]:
        normalized = str(direction or "").strip().lower()
        if normalized not in {"up", "down"}:
            raise ValueError("direction must be one of ['up', 'down']")
        row = self.repo.move_item(item_id, normalized)
        if row is None:
            raise WatchlistNotFoundError(f"关注标的不存在: {item_id}")
        return self.get_item(row.id)

    def related_alerts(self, item_id: int) -> Dict[str, List[Dict[str, Any]]]:
        row = self.repo.get_item(item_id)
        if row is None:
            raise WatchlistNotFoundError(f"关注标的不存在: {item_id}")
        related = self.repo.related_alerts(row)
        return {
            "rules": [self._serialize_alert_rule(item) for item in related["rules"]],
            "triggers": [self._serialize_alert_trigger(item) for item in related["triggers"]],
        }

    def _normalize_payload(self, payload: Dict[str, Any], *, partial: bool = False) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}
        for key, value in payload.items():
            if value is None:
                if partial:
                    fields[key] = None
                continue
            fields[key] = value

        if "market" in fields:
            market = str(fields["market"]).strip().lower()
            if market not in VALID_MARKETS:
                raise ValueError(f"market must be one of {sorted(VALID_MARKETS)}")
            fields["market"] = market
        elif not partial:
            fields["market"] = "cn"

        if "symbol" in fields:
            symbol = str(fields["symbol"]).strip()
            if not symbol:
                raise ValueError("symbol is required")
            fields["symbol"] = symbol.upper()

        if "name" in fields and fields["name"] is not None:
            fields["name"] = str(fields["name"]).strip() or None

        if "currency" in fields:
            fields["currency"] = str(fields["currency"]).strip().upper() or "CNY"
        elif not partial:
            fields["currency"] = "CNY"

        if "asset_category" in fields:
            category = str(fields["asset_category"]).strip().lower()
            if category not in VALID_ASSET_CATEGORIES:
                raise ValueError(f"asset_category must be one of {sorted(VALID_ASSET_CATEGORIES)}")
            fields["asset_category"] = category
        elif not partial:
            fields["asset_category"] = "stock"

        if "watch_priority" in fields:
            priority = str(fields["watch_priority"]).strip().lower()
            if priority not in VALID_PRIORITIES:
                raise ValueError(f"watch_priority must be one of {sorted(VALID_PRIORITIES)}")
            fields["watch_priority"] = priority
        elif not partial:
            fields["watch_priority"] = "medium"

        if "analysis_frequency" in fields:
            frequency = str(fields["analysis_frequency"]).strip().lower()
            if frequency not in VALID_FREQUENCIES:
                raise ValueError(f"analysis_frequency must be one of {sorted(VALID_FREQUENCIES)}")
            fields["analysis_frequency"] = frequency
        elif not partial:
            fields["analysis_frequency"] = "daily"

        if "watch_tags" in fields:
            fields["watch_tags"] = self._dump_tags(fields["watch_tags"])

        for key in ("asset_subcategory", "asset_risk_class", "watch_reason", "source", "notes"):
            if key in fields and fields[key] is not None:
                fields[key] = str(fields[key]).strip() or None

        if "source" not in fields and not partial:
            fields["source"] = "manual"

        return fields

    @staticmethod
    def _dump_tags(value: Any) -> str:
        if isinstance(value, str):
            tags = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, list):
            tags = [str(item).strip() for item in value if str(item).strip()]
        else:
            tags = []
        return json.dumps(tags, ensure_ascii=False)

    @staticmethod
    def _load_tags(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except Exception:
            pass
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _serialize_item(
        self,
        row: WatchlistItem,
        summary: Optional[Dict[str, Any]] = None,
        analysis_summary: Optional[Dict[str, Any]] = None,
        quote_summary: Optional[Dict[str, Any]] = None,
        signal_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        summary = summary or {}
        analysis_summary = analysis_summary or {}
        quote_summary = quote_summary or {}
        signal_summary = signal_summary or {}
        return {
            "id": row.id,
            "market": row.market,
            "symbol": row.symbol,
            "display_symbol": self._display_symbol(row),
            "name": row.name,
            "currency": row.currency,
            "asset_category": row.asset_category,
            "asset_subcategory": row.asset_subcategory,
            "asset_risk_class": row.asset_risk_class,
            "watch_priority": row.watch_priority,
            "watch_tags": self._load_tags(row.watch_tags),
            "watch_reason": row.watch_reason,
            "watch_enabled": row.watch_enabled,
            "analysis_enabled": row.analysis_enabled,
            "analysis_frequency": row.analysis_frequency,
            "alert_enabled": row.alert_enabled,
            "source": row.source,
            "sort_order": int(row.sort_order or 0),
            "notes": row.notes,
            "alert_rule_count": int(summary.get("alert_rule_count") or 0),
            "alert_trigger_count": int(summary.get("alert_trigger_count") or 0),
            "latest_alert_triggered_at": summary.get("latest_alert_triggered_at"),
            "latest_price": quote_summary.get("latest_price"),
            "latest_change_pct": quote_summary.get("latest_change_pct"),
            "signal_as_of_date": signal_summary.get("as_of_date"),
            "signal_verdict_code": signal_summary.get("verdict_code"),
            "signal_reason": signal_summary.get("reason"),
            "signal_lights": signal_summary.get("lights") or [],
            "signal_data_quality_flags": signal_summary.get("data_quality_flags") or [],
            "latest_analysis_id": analysis_summary.get("latest_analysis_id"),
            "latest_analysis_at": analysis_summary.get("latest_analysis_at"),
            "latest_analysis_summary": analysis_summary.get("latest_analysis_summary"),
            "latest_operation_advice": analysis_summary.get("latest_operation_advice"),
            "latest_trend_prediction": analysis_summary.get("latest_trend_prediction"),
            "created_at": self._dt(row.created_at),
            "updated_at": self._dt(row.updated_at),
        }

    def _resolve_official_name(self, row: WatchlistItem) -> str:
        """Resolve the official name from data sources. Falls back to the current name."""
        try:
            if row.asset_category == "fund":
                return self._resolve_fund_name(row.symbol)
            if row.asset_category == "stock":
                return self._resolve_stock_name(row)
        except Exception as exc:
            logger.debug("Name resolution failed for %s/%s: %s", row.asset_category, row.symbol, exc)
        return row.name or row.symbol

    @staticmethod
    def _resolve_fund_name(fund_code: str) -> str:
        from src.storage import FundInfo, get_db
        from src.repositories.fund_repo import FundRepository
        db = get_db()
        with db.get_session() as session:
            info = session.query(FundInfo).filter_by(fund_code=fund_code).first()
            if info and info.fund_name:
                return info.fund_name
        try:
            import akshare as ak
            df = ak.fund_name_em()
            if df is not None and not df.empty:
                match = df[df["基金代码"].astype(str) == fund_code]
                if not match.empty:
                    name = str(match.iloc[0].get("基金简称", "")).strip()
                    if name:
                        fund_repo = FundRepository()
                        fund_repo.upsert_fund_info({
                            "fund_code": fund_code,
                            "fund_name": name,
                            "fund_type": str(match.iloc[0].get("基金类型", "")).strip() or None,
                        })
                        return name
        except Exception as e:
            logger.debug("akshare fund_name_em failed [%s]: %s", fund_code, e)
        return fund_code

    def _resolve_stock_name(self, row: WatchlistItem) -> str:
        try:
            from data_provider.base import DataFetcherManager
            manager = DataFetcherManager()
            code = row.symbol
            market = str(row.market or "cn").lower()
            if market == "cn":
                if code.startswith(("6", "9")):
                    code = f"{code}.SH"
                elif code.startswith(("0", "2", "3")):
                    code = f"{code}.SZ"
                elif code.startswith(("4", "8")):
                    code = f"{code}.BJ"
            name = manager.get_stock_name(code, allow_realtime=True)
            if name:
                return name
        except Exception as e:
            logger.debug("Stock name resolution failed [%s]: %s", row.symbol, e)
        return row.name or row.symbol

    def _seed_fund_nav(self, fund_code: str) -> None:
        """Fetch and persist fund NAV data so the watchlist can display price/change."""
        try:
            from src.services.fund_service import FundService
            FundService().fetch_and_save_nav(fund_code, days=90)
        except Exception as e:
            logger.debug("Seed fund NAV failed [%s]: %s", fund_code, e)

    @staticmethod
    def _display_symbol(row: WatchlistItem) -> str:
        symbol = str(row.symbol or "").strip()
        upper = symbol.upper()
        if "." in upper:
            return upper
        market = str(row.market or "").lower()
        if market == "cn" and len(symbol) == 6 and symbol.isdigit():
            if symbol.startswith(("6", "9")):
                return f"{symbol}.SH"
            if symbol.startswith(("0", "2", "3")):
                return f"{symbol}.SZ"
            if symbol.startswith(("4", "8")):
                return f"{symbol}.BJ"
        if market == "hk" and symbol.isdigit():
            return f"{symbol.zfill(5)}.HK"
        return upper

    @staticmethod
    def _serialize_alert_rule(row: AlertRuleRecord) -> Dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "target_scope": row.target_scope,
            "target": row.target,
            "alert_type": row.alert_type,
            "severity": row.severity,
            "enabled": row.enabled,
            "source": row.source,
            "updated_at": WatchlistService._dt(row.updated_at),
        }

    @staticmethod
    def _serialize_alert_trigger(row: AlertTriggerRecord) -> Dict[str, Any]:
        return {
            "id": row.id,
            "rule_id": row.rule_id,
            "target": row.target,
            "observed_value": row.observed_value,
            "threshold": row.threshold,
            "reason": row.reason,
            "data_source": row.data_source,
            "data_timestamp": WatchlistService._dt(row.data_timestamp),
            "triggered_at": WatchlistService._dt(row.triggered_at),
            "status": row.status,
        }

    @staticmethod
    def _dt(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None
