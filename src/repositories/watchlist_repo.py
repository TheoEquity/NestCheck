# -*- coding: utf-8 -*-
"""Watchlist repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy.exc import IntegrityError

from src.storage import AlertRuleRecord, AlertTriggerRecord, AnalysisHistory, DatabaseManager, MarketQuote, WatchlistItem


class WatchlistConflictError(ValueError):
    """Raised when a watchlist item violates uniqueness."""


class WatchlistRepository:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def create_item(self, fields: Dict[str, Any]) -> WatchlistItem:
        with self.db.get_session() as session:
            row = WatchlistItem(**fields)
            session.add(row)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise WatchlistConflictError("关注标的已存在") from exc
            session.refresh(row)
            return row

    def get_item(self, item_id: int) -> Optional[WatchlistItem]:
        with self.db.get_session() as session:
            return session.execute(
                select(WatchlistItem).where(WatchlistItem.id == item_id).limit(1)
            ).scalar_one_or_none()

    def list_items(
        self,
        *,
        asset_category: Optional[str] = None,
        watch_enabled: Optional[bool] = None,
    ) -> Tuple[List[WatchlistItem], int]:
        conditions = []
        if asset_category:
            conditions.append(WatchlistItem.asset_category == asset_category)
        if watch_enabled is not None:
            conditions.append(WatchlistItem.watch_enabled.is_(watch_enabled))
        where_clause = and_(*conditions) if conditions else True
        with self.db.get_session() as session:
            total = session.execute(
                select(func.count(WatchlistItem.id)).select_from(WatchlistItem).where(where_clause)
            ).scalar() or 0
            rows = session.execute(
                select(WatchlistItem)
                .where(where_clause)
                .order_by(WatchlistItem.asset_category.asc(), WatchlistItem.market.asc(), WatchlistItem.symbol.asc())
            ).scalars().all()
            return list(rows), int(total)

    def list_analysis_targets(self, frequency: str = "daily") -> List[WatchlistItem]:
        """获取需进行分析的标的列表。
        
        Args:
            frequency: 分析频率，默认仅获取每日 (daily) 关注的标的。
            
        Returns:
            符合频率且启用的关注标的列表。
        """
        with self.db.get_session() as session:
            stmt = (
                select(WatchlistItem)
                .where(
                    WatchlistItem.watch_enabled == True,
                    WatchlistItem.analysis_enabled == True,
                    WatchlistItem.analysis_frequency == frequency,
                )
                .order_by(WatchlistItem.id.asc())
            )
            rows = session.execute(stmt).scalars().all()
            return list(rows)

    def update_item(self, item_id: int, fields: Dict[str, Any]) -> Optional[WatchlistItem]:
        with self.db.get_session() as session:
            row = session.execute(
                select(WatchlistItem).where(WatchlistItem.id == item_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return None
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = datetime.now()
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise WatchlistConflictError("关注标的已存在") from exc
            session.refresh(row)
            return row

    def delete_item(self, item_id: int) -> bool:
        with self.db.get_session() as session:
            result = session.execute(delete(WatchlistItem).where(WatchlistItem.id == item_id))
            session.commit()
            return bool(result.rowcount)

    def alert_summary_for_items(self, items: List[WatchlistItem]) -> Dict[int, Dict[str, Any]]:
        summary = {
            item.id: {
                "alert_rule_count": 0,
                "alert_trigger_count": 0,
                "latest_alert_triggered_at": None,
            }
            for item in items
        }
        if not items:
            return summary

        with self.db.get_session() as session:
            for item in items:
                targets = self._targets_for_item(item)
                rule_count = session.execute(
                    select(func.count(AlertRuleRecord.id)).where(AlertRuleRecord.target.in_(targets))
                ).scalar() or 0
                trigger_count = session.execute(
                    select(func.count(AlertTriggerRecord.id)).where(AlertTriggerRecord.target.in_(targets))
                ).scalar() or 0
                latest = session.execute(
                    select(func.max(AlertTriggerRecord.triggered_at)).where(AlertTriggerRecord.target.in_(targets))
                ).scalar()
                summary[item.id] = {
                    "alert_rule_count": int(rule_count),
                    "alert_trigger_count": int(trigger_count),
                    "latest_alert_triggered_at": latest.isoformat() if latest else None,
                }
        return summary

    def quote_summary_for_items(self, items: List[WatchlistItem]) -> Dict[int, Dict[str, Any]]:
        stock_items = [item for item in items if item.asset_category == "stock"]
        summary: Dict[int, Dict[str, Any]] = {}
        if not stock_items:
            return summary

        with self.db.get_session() as session:
            for item in stock_items:
                row = session.execute(
                    select(MarketQuote)
                    .where(MarketQuote.code == item.symbol, MarketQuote.market == item.market)
                    .order_by(desc(MarketQuote.updated_at), desc(MarketQuote.id))
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    continue
                summary[item.id] = {
                    "latest_price": row.latest_price,
                    "latest_change_pct": row.pct_change,
                }
        return summary

    def stock_analysis_summary_for_items(self, items: List[WatchlistItem]) -> Dict[int, Dict[str, Any]]:
        stock_items = [item for item in items if item.asset_category == "stock"]
        summary: Dict[int, Dict[str, Any]] = {}
        if not stock_items:
            return summary

        with self.db.get_session() as session:
            for item in stock_items:
                symbol = str(item.symbol or "").strip().upper()
                row = session.execute(
                    select(AnalysisHistory)
                    .where(
                        or_(AnalysisHistory.code == symbol, AnalysisHistory.code.like(f"{symbol}.%")),
                        AnalysisHistory.report_type != "market_review",
                    )
                    .order_by(desc(AnalysisHistory.created_at), desc(AnalysisHistory.id))
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    continue
                summary[item.id] = {
                    "latest_analysis_id": row.id,
                    "latest_analysis_at": row.created_at.isoformat() if row.created_at else None,
                    "latest_analysis_summary": row.analysis_summary,
                    "latest_operation_advice": row.operation_advice,
                    "latest_trend_prediction": row.trend_prediction,
                }
        return summary

    def latest_market_review_summary(self) -> Dict[str, Any]:
        with self.db.get_session() as session:
            row = session.execute(
                select(AnalysisHistory)
                .where(AnalysisHistory.report_type == "market_review")
                .order_by(desc(AnalysisHistory.created_at), desc(AnalysisHistory.id))
                .limit(1)
            ).scalar_one_or_none()
            if row is None:
                return {}
            market_review_text = row.news_content or row.analysis_summary
            return {
                "latest_analysis_id": row.id,
                "latest_analysis_at": row.created_at.isoformat() if row.created_at else None,
                "latest_analysis_summary": self._market_review_excerpt(market_review_text),
                "latest_analysis_sections": self._market_review_sections(market_review_text),
                "latest_operation_advice": row.operation_advice,
                "latest_trend_prediction": row.trend_prediction,
            }

    def related_alerts(self, item: WatchlistItem, *, limit: int = 20) -> Dict[str, List[Any]]:
        targets = self._targets_for_item(item)
        safe_limit = max(1, min(int(limit), 100))
        with self.db.get_session() as session:
            rules = session.execute(
                select(AlertRuleRecord)
                .where(or_(AlertRuleRecord.target.in_(targets), AlertRuleRecord.target_scope == "watchlist"))
                .order_by(desc(AlertRuleRecord.updated_at), desc(AlertRuleRecord.id))
                .limit(safe_limit)
            ).scalars().all()
            triggers = session.execute(
                select(AlertTriggerRecord)
                .where(AlertTriggerRecord.target.in_(targets))
                .order_by(desc(AlertTriggerRecord.triggered_at), desc(AlertTriggerRecord.id))
                .limit(safe_limit)
            ).scalars().all()
            return {"rules": list(rules), "triggers": list(triggers)}

    @staticmethod
    def _targets_for_item(item: WatchlistItem) -> List[str]:
        values = {
            str(item.symbol or "").strip(),
            f"{item.market}:{item.symbol}".strip(),
            f"{item.asset_category}:{item.market}:{item.symbol}".strip(),
            str(item.id),
            f"watchlist:{item.id}",
        }
        return [value for value in values if value and value != ":" and value != "::"]

    @staticmethod
    def _market_review_excerpt(text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        for line in lines:
            if line.startswith(">"):
                return line.lstrip(">").strip()
        for line in lines:
            if not line.startswith("#"):
                return line
        return lines[0].lstrip("#").strip() if lines else None

    @staticmethod
    def _market_review_sections(text: Optional[str]) -> Dict[str, str]:
        if not text:
            return {}

        sections: List[Tuple[str, List[str]]] = []
        current_title = ""
        current_lines: List[str] = []
        for raw_line in str(text).splitlines():
            line = raw_line.strip()
            if line.startswith("###"):
                if current_title or current_lines:
                    sections.append((current_title, current_lines))
                current_title = line.lstrip("#").strip()
                current_lines = []
            elif line and not line.startswith("#") and not line.startswith(">"):
                current_lines.append(line)
        if current_title or current_lines:
            sections.append((current_title, current_lines))

        return {
            "market_status": WatchlistRepository._pick_section(sections, ("盘面", "总览")),
            "main_themes": WatchlistRepository._pick_section(sections, ("板块主线", "主线", "板块")),
            "risk_alert": WatchlistRepository._pick_section(sections, ("风险提示", "风险")),
            "tomorrow_watch": WatchlistRepository._pick_section(sections, ("明日交易计划", "明日", "交易计划")),
        }

    @staticmethod
    def _pick_section(sections: List[Tuple[str, List[str]]], keywords: Tuple[str, ...]) -> str:
        for title, lines in sections:
            if any(keyword in title for keyword in keywords):
                return WatchlistRepository._compact_section(lines)
        return ""

    @staticmethod
    def _compact_section(lines: List[str], *, max_chars: int = 220) -> str:
        text = " ".join(line.lstrip("- ").strip() for line in lines if line.strip())
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars].rstrip()}..."
