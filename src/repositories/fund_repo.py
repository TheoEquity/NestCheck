# -*- coding: utf-8 -*-
"""
===================================
基金数据访问层
===================================

职责：
1. 封装基金信息、净值、持仓、报告等数据库操作
2. 提供查询和写入接口
"""

import json
import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import pandas as pd
from sqlalchemy import and_, desc, select, func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.storage import (
    DatabaseManager,
    FundInfo,
    FundDailyNav,
    FundHolding,
    FundPerformance,
    FundReport,
)

logger = logging.getLogger(__name__)


class FundRepository:
    """基金数据访问层"""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager.get_instance()

    # -------- FundInfo --------

    def get_fund_info(self, fund_code: str) -> Optional[FundInfo]:
        """获取基金基本信息"""
        try:
            with self.db.get_session() as session:
                return session.execute(
                    select(FundInfo).where(FundInfo.fund_code == fund_code)
                ).scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取基金信息失败: {e}")
            return None

    def search_funds(self, keyword: str, limit: int = 20) -> List[FundInfo]:
        """按名称/代码模糊搜索基金"""
        try:
            pattern = f"%{keyword}%"
            with self.db.get_session() as session:
                return (
                    session.execute(
                        select(FundInfo)
                        .where(
                            and_(
                                FundInfo.status == "normal",
                                (FundInfo.fund_code.like(pattern))
                                | (FundInfo.fund_name.like(pattern)),
                            )
                        )
                        .order_by(FundInfo.fund_name)
                        .limit(limit)
                    )
                    .scalars()
                    .all()
                )
        except Exception as e:
            logger.error(f"搜索基金失败: {e}")
            return []

    def upsert_fund_info(self, data: Dict[str, Any]) -> Optional[FundInfo]:
        """新增或更新基金信息"""
        try:
            with self.db.get_session() as session:
                existing = session.execute(
                    select(FundInfo).where(FundInfo.fund_code == data["fund_code"])
                ).scalar_one_or_none()
                if existing:
                    for k, v in data.items():
                        if k not in ("fund_code", "id"):
                            setattr(existing, k, v)
                    existing.updated_at = datetime.now()
                else:
                    fund = FundInfo(**data)
                    session.add(fund)
                session.commit()
                return existing or fund
        except Exception as e:
            logger.error(f"保存基金信息失败: {e}")
            return None

    # -------- FundDailyNav --------

    def get_latest_nav_date(self, fund_code: str) -> Optional[date]:
        """获取该基金最近一个净值日期"""
        try:
            with self.db.get_session() as session:
                row = session.execute(
                    select(FundDailyNav.nav_date)
                    .where(FundDailyNav.fund_code == fund_code)
                    .order_by(desc(FundDailyNav.nav_date))
                    .limit(1)
                ).scalar_one_or_none()
                return row
        except Exception as e:
            logger.error(f"获取最新净值日期失败: {e}")
            return None

    def get_nav_history(
        self,
        fund_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 500,
    ) -> List[FundDailyNav]:
        """获取基金净值历史"""
        try:
            with self.db.get_session() as session:
                q = select(FundDailyNav).where(
                    FundDailyNav.fund_code == fund_code
                )
                if start_date:
                    q = q.where(FundDailyNav.nav_date >= start_date)
                if end_date:
                    q = q.where(FundDailyNav.nav_date <= end_date)
                q = q.order_by(desc(FundDailyNav.nav_date)).limit(limit)
                return list(session.execute(q).scalars().all())
        except Exception as e:
            logger.error(f"获取净值历史失败: {e}")
            return []

    def save_nav_batch(self, records: List[Dict[str, Any]]) -> int:
        """批量保存净值数据（幂等 upsert）"""
        if not records:
            return 0
        try:
            with self.db.get_session() as session:
                stmt = (
                    sqlite_insert(FundDailyNav)
                    .values(records)
                    .on_conflict_do_update(
                        index_elements=["fund_code", "nav_date"],
                        set_={
                            "unit_nav": sqlite_insert(FundDailyNav).excluded.unit_nav,
                            "accumulated_nav": sqlite_insert(FundDailyNav).excluded.accumulated_nav,
                            "daily_return": sqlite_insert(FundDailyNav).excluded.daily_return,
                            "daily_change": sqlite_insert(FundDailyNav).excluded.daily_change,
                            "updated_at": datetime.now(),
                        },
                    )
                )
                session.execute(stmt)
                session.commit()
                return len(records)
        except Exception as e:
            logger.error(f"批量保存净值失败: {e}")
            return 0

    # -------- FundHolding --------

    def get_latest_holdings(self, fund_code: str) -> List[FundHolding]:
        """获取基金最新一期前十大持仓"""
        try:
            with self.db.get_session() as session:
                # 先找最新报告期
                latest_date = session.execute(
                    select(FundHolding.report_date)
                    .where(FundHolding.fund_code == fund_code)
                    .order_by(desc(FundHolding.report_date))
                    .limit(1)
                ).scalar_one_or_none()

                if not latest_date:
                    return []

                return (
                    session.execute(
                        select(FundHolding)
                        .where(
                            and_(
                                FundHolding.fund_code == fund_code,
                                FundHolding.report_date == latest_date,
                            )
                        )
                        .order_by(FundHolding.rank)
                    )
                    .scalars()
                    .all()
                )
        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            return []

    def save_holdings(self, records: List[Dict[str, Any]]) -> int:
        """保存持仓数据"""
        if not records:
            return 0
        try:
            with self.db.get_session() as session:
                stmt = (
                    sqlite_insert(FundHolding)
                    .values(records)
                    .on_conflict_do_update(
                        index_elements=["fund_code", "report_date", "stock_code"],
                        set_={
                            "stock_name": sqlite_insert(FundHolding).excluded.stock_name,
                            "stock_market": sqlite_insert(FundHolding).excluded.stock_market,
                            "holding_pct": sqlite_insert(FundHolding).excluded.holding_pct,
                            "holding_shares": sqlite_insert(FundHolding).excluded.holding_shares,
                            "holding_amount": sqlite_insert(FundHolding).excluded.holding_amount,
                            "rank": sqlite_insert(FundHolding).excluded.rank,
                            "updated_at": datetime.now(),
                        },
                    )
                )
                session.execute(stmt)
                session.commit()
                return len(records)
        except Exception as e:
            logger.error(f"保存持仓失败: {e}")
            return 0

    # -------- FundPerformance --------

    def upsert_performance(self, records: List[Dict[str, Any]]) -> int:
        """保存业绩指标"""
        if not records:
            return 0
        try:
            with self.db.get_session() as session:
                stmt = (
                    sqlite_insert(FundPerformance)
                    .values(records)
                    .on_conflict_do_update(
                        index_elements=["fund_code", "calc_date", "period"],
                        set_={
                            "return_pct": sqlite_insert(FundPerformance).excluded.return_pct,
                            "benchmark_return": sqlite_insert(FundPerformance).excluded.benchmark_return,
                            "excess_return": sqlite_insert(FundPerformance).excluded.excess_return,
                            "max_drawdown": sqlite_insert(FundPerformance).excluded.max_drawdown,
                            "sharpe_ratio": sqlite_insert(FundPerformance).excluded.sharpe_ratio,
                            "volatility": sqlite_insert(FundPerformance).excluded.volatility,
                            "updated_at": datetime.now(),
                        },
                    )
                )
                session.execute(stmt)
                session.commit()
                return len(records)
        except Exception as e:
            logger.error(f"保存业绩指标失败: {e}")
            return 0

    # -------- FundReport --------

    def get_latest_report(self, fund_code: str) -> Optional[FundReport]:
        """获取最新的分析报告"""
        try:
            with self.db.get_session() as session:
                return session.execute(
                    select(FundReport)
                    .where(FundReport.fund_code == fund_code)
                    .order_by(desc(FundReport.created_at))
                    .limit(1)
                ).scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取报告失败: {e}")
            return None

    def create_report(
        self,
        fund_code: str,
        query_text: str,
        report_markdown: str,
        report_json: Optional[Dict[str, Any]] = None,
        analysis_duration: Optional[float] = None,
        data_sources: Optional[List[str]] = None,
    ) -> Optional[FundReport]:
        """创建分析报告"""
        try:
            with self.db.get_session() as session:
                report = FundReport(
                    fund_code=fund_code,
                    query_text=query_text,
                    report_markdown=report_markdown,
                    report_json=json.dumps(report_json, ensure_ascii=False) if report_json else None,
                    analysis_duration=analysis_duration,
                    data_sources=json.dumps(data_sources, ensure_ascii=False) if data_sources else None,
                    status="completed",
                )
                session.add(report)
                session.commit()
                return report
        except Exception as e:
            logger.error(f"创建报告失败: {e}")
            return None

    def save_nav_dataframe(self, df: pd.DataFrame, fund_code: str) -> int:
        """保存 DataFrame 格式的净值数据"""
        if df.empty:
            return 0
        records = []
        for _, row in df.iterrows():
            rec = {
                "fund_code": fund_code,
                "nav_date": row.get("nav_date"),
                "unit_nav": row.get("unit_nav"),
                "accumulated_nav": row.get("accumulated_nav"),
                "daily_return": row.get("daily_return"),
                "daily_change": row.get("daily_change"),
            }
            if rec["nav_date"] is not None:
                records.append(rec)
        return self.save_nav_batch(records)
