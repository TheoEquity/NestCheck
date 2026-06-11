# -*- coding: utf-8 -*-
"""Watchlist repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, desc, func, select
from sqlalchemy.exc import IntegrityError

from src.storage import (
    AnalysisHistory,
    DatabaseManager,
    FundDailyNav,
    MarketQuote,
    StockDaily,
    WatchlistIndicatorSnapshot,
    WatchlistItem,
    WatchlistSignalSnapshot,
)


class WatchlistConflictError(ValueError):
    """Raised when a watchlist item violates uniqueness."""


class WatchlistRepository:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    def create_item(self, fields: Dict[str, Any]) -> WatchlistItem:
        with self.db.get_session() as session:
            if "sort_order" not in fields:
                max_order = session.execute(select(func.max(WatchlistItem.sort_order))).scalar()
                fields["sort_order"] = int(max_order or 0) + 1
            row = WatchlistItem(**fields)
            session.add(row)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise WatchlistConflictError("关注标的已存在") from exc
            session.refresh(row)
            return row

    def _update_item_name(self, item_id: int, name: str) -> None:
        from sqlalchemy import update
        with self.db.get_session() as session:
            session.execute(
                update(WatchlistItem)
                .where(WatchlistItem.id == item_id)
                .values(name=name, updated_at=datetime.now())
            )
            session.commit()

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
                .order_by(WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
            ).scalars().all()
            return list(rows), int(total)

    def move_item(self, item_id: int, direction: str) -> Optional[WatchlistItem]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(WatchlistItem).order_by(WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
            ).scalars().all()
            items = list(rows)
            index = next((idx for idx, item in enumerate(items) if item.id == item_id), None)
            if index is None:
                return None
            target_index = index - 1 if direction == "up" else index + 1
            if target_index < 0 or target_index >= len(items):
                return items[index]

            items[index], items[target_index] = items[target_index], items[index]
            now = datetime.now()
            for sort_order, item in enumerate(items, start=1):
                item.sort_order = sort_order
                item.updated_at = now
            session.commit()
            moved = items[target_index]
            session.refresh(moved)
            return moved

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
            row = session.execute(
                select(WatchlistItem).where(WatchlistItem.id == item_id).limit(1)
            ).scalar_one_or_none()
            if row is None:
                return False
            session.execute(delete(WatchlistIndicatorSnapshot).where(WatchlistIndicatorSnapshot.watchlist_item_id == item_id))
            session.execute(delete(WatchlistSignalSnapshot).where(WatchlistSignalSnapshot.watchlist_item_id == item_id))
            result = session.execute(delete(WatchlistItem).where(WatchlistItem.id == item_id))
            remaining = session.execute(
                select(WatchlistItem).order_by(WatchlistItem.sort_order.asc(), WatchlistItem.id.asc())
            ).scalars().all()
            now = datetime.now()
            for sort_order, item in enumerate(remaining, start=1):
                item.sort_order = sort_order
                item.updated_at = now
            session.commit()
            return bool(result.rowcount)

    def quote_summary_for_items(self, items: List[WatchlistItem]) -> Dict[int, Dict[str, Any]]:
        stock_items = [item for item in items if item.asset_category == "stock"]
        fund_items = [item for item in items if item.asset_category == "fund"]
        summary: Dict[int, Dict[str, Any]] = {}

        if stock_items:
            with self.db.get_session() as session:
                for item in stock_items:
                    row = session.execute(
                        select(MarketQuote)
                        .where(MarketQuote.code == item.symbol, MarketQuote.market == item.market)
                        .order_by(desc(MarketQuote.updated_at), desc(MarketQuote.id))
                        .limit(1)
                    ).scalar_one_or_none()
                    if row is None:
                        daily = session.execute(
                            select(StockDaily)
                            .where(StockDaily.code == item.symbol)
                            .order_by(desc(StockDaily.date), desc(StockDaily.id))
                            .limit(1)
                        ).scalar_one_or_none()
                        if daily is None:
                            continue
                        summary[item.id] = {
                            "latest_price": daily.close,
                            "latest_change_pct": daily.pct_chg,
                        }
                        continue
                    summary[item.id] = {
                        "latest_price": row.latest_price,
                        "latest_change_pct": row.pct_change,
                    }

        if fund_items:
            # Watchlist 基金的净值从 WatchlistIndicatorSnapshot 取，独立于持仓资产的 FundDailyNav
            from src.storage import WatchlistIndicatorSnapshot
            with self.db.get_session() as session:
                for item in fund_items:
                    indicator = session.execute(
                        select(WatchlistIndicatorSnapshot)
                        .where(WatchlistIndicatorSnapshot.watchlist_item_id == item.id)
                        .order_by(desc(WatchlistIndicatorSnapshot.as_of_date))
                        .limit(1)
                    ).scalar_one_or_none()
                    if indicator is None or indicator.price is None:
                        continue
                    summary[item.id] = {
                        "latest_price": indicator.price,
                        "latest_change_pct": indicator.price_change_pct,
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
