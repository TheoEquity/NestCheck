# -*- coding: utf-8 -*-
"""
===================================
基金数据服务层
===================================

职责：
1. 从 AKShare 获取基金数据并落库
2. 提供基金搜索、净值、持仓、业绩指标查询
3. 协调数据获取和存储流程
"""

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd

from src.repositories.fund_repo import FundRepository
from src.services.portfolio_service import round_asset_price

logger = logging.getLogger(__name__)


class FundService:
    """基金数据服务"""

    def __init__(self, repo: Optional[FundRepository] = None):
        self.repo = repo or FundRepository()

    # ================================================================
    # 基金搜索
    # ================================================================

    def search(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索基金（仅查本地，不触发外部 API 调用）
        """
        local = self.repo.search_funds(keyword, limit)
        return [f.to_dict() for f in local]

    def get_info(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取基金基本信息"""
        fund = self.repo.get_fund_info(fund_code)
        if fund:
            return fund.to_dict()
        return None

    def seed_asset_input(
        self,
        fund_code: str,
        fund_name: Optional[str] = None,
        fund_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """使用用户输入的资产主数据初始化基金基础信息。"""
        code = (fund_code or "").strip()
        if not code:
            return None
        name = (fund_name or "").strip() or code
        self.repo.upsert_fund_info({
            "fund_code": code,
            "fund_name": name,
            "fund_type": fund_type or "基金",
            "status": "normal",
        })
        return self.get_info(code)

    # ================================================================
    # 净值数据
    # ================================================================

    def fetch_and_save_nav(self, fund_code: str, days: int = 365 * 3) -> Tuple[int, int]:
        """
        获取并保存基金净值数据

        Returns:
            (total_rows, new_rows) — 总行数 / 新增行数
        """
        import akshare as ak
        try:
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
            if df is None or df.empty:
                return 0, 0
            return self._persist_nav(df, fund_code)
        except Exception as e:
            logger.error(f"获取基金净值失败 [{fund_code}]: {e}")
            return 0, 0

    def fetch_and_save_accumulated_nav(self, fund_code: str) -> int:
        """获取并更新累计净值（单位净值已包含大部分信息，此为辅助）"""
        import akshare as ak
        try:
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="累计净值走势")
            if df is None or df.empty:
                return 0
            return self._update_accumulated_nav(df, fund_code)
        except Exception as e:
            logger.error(f"获取累计净值失败 [{fund_code}]: {e}")
            return 0

    def get_nav_history(
        self,
        fund_code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        """获取净值历史"""
        sd = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
        ed = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
        rows = self.repo.get_nav_history(fund_code, start_date=sd, end_date=ed, limit=limit)
        return [r.to_dict() for r in rows]

    # ================================================================
    # 持仓数据
    # ================================================================

    def fetch_and_save_holdings(self, fund_code: str) -> int:
        """获取并保存最新一期持仓明细"""
        import akshare as ak
        try:
            df = ak.fund_portfolio_hold_em(symbol=fund_code)
            if df is None or df.empty:
                return 0
            return self._persist_holdings(df, fund_code)
        except Exception as e:
            logger.error(f"获取基金持仓失败 [{fund_code}]: {e}")
            return 0

    def get_holdings(self, fund_code: str) -> List[Dict[str, Any]]:
        """获取最新一期前十大持仓"""
        rows = self.repo.get_latest_holdings(fund_code)
        return [r.to_dict() for r in rows]

    # ================================================================
    # 完整数据刷新（一键获取基金所有数据）
    # ================================================================

    def refresh_fund(self, fund_code: str) -> Dict[str, Any]:
        """
        刷新单只基金的完整数据

        Returns:
            {"info": ..., "nav_count": n, "holding_count": n}
        """
        # 1. 先确保基金基本信息存在
        info = self.get_info(fund_code)
        if not info:
            self._seed_single_fund(fund_code)

        # 2. 获取净值
        nav_total, nav_new = self.fetch_and_save_nav(fund_code)

        # 3. 获取持仓
        holding_count = self.fetch_and_save_holdings(fund_code)

        return {
            "fund_code": fund_code,
            "info": self.get_info(fund_code),
            "nav_total": nav_total,
            "nav_new": nav_new,
            "holding_count": holding_count,
        }

    # ================================================================
    # 内部方法
    # ================================================================

    def _seed_fund_list(self, keyword: str) -> None:
        """从 AKShare 获取基金列表并批量落库"""
        import akshare as ak
        df = ak.fund_name_em()
        if df is None or df.empty:
            return
        for _, row in df.iterrows():
            self.repo.upsert_fund_info({
                "fund_code": str(row.get("基金代码", "")).strip(),
                "fund_name": str(row.get("基金简称", "")).strip(),
                "fund_type": str(row.get("基金类型", "")).strip() or None,
            })

    def _seed_single_fund(self, fund_code: str) -> None:
        """获取单个基金信息并落库"""
        import akshare as ak
        try:
            # 先尝试从基金列表匹配
            df = ak.fund_name_em()
            if df is None or df.empty:
                return
            match = df[df["基金代码"].astype(str) == fund_code]
            if not match.empty:
                row = match.iloc[0]
                self.repo.upsert_fund_info({
                    "fund_code": fund_code,
                    "fund_name": str(row.get("基金简称", "")).strip(),
                    "fund_type": str(row.get("基金类型", "")).strip() or None,
                })
        except Exception as e:
            logger.error(f"获取基金信息失败 [{fund_code}]: {e}")

    def _persist_nav(self, df: pd.DataFrame, fund_code: str) -> Tuple[int, int]:
        """解析并保存净值数据"""
        # AKShare 开放式基金净值接口返回列: 日期, 单位净值, 累计净值, 日增长率
        records = []
        for _, row in df.iterrows():
            nav_date = row.get("净值日期") or row.get("date") or row.get("日期")
            if nav_date:
                try:
                    nav_date = pd.to_datetime(nav_date).date()
                except Exception:
                    continue
                records.append({
                    "fund_code": fund_code,
                    "nav_date": nav_date,
                    "unit_nav": self._round_nav(self._safe_float(row.get("单位净值") or row.get("unit_nav")), fund_code),
                    "accumulated_nav": self._round_nav(self._safe_float(row.get("累计净值") or row.get("accumulated_nav")), fund_code),
                    "daily_return": self._safe_float(row.get("日增长率") or row.get("daily_return")),
                    "daily_change": None,
                })

        latest_date = self.repo.get_latest_nav_date(fund_code)
        new_count = 0
        if latest_date:
            records = [r for r in records if r["nav_date"] > latest_date]
            new_count = len(records)
        else:
            new_count = len(records)

        saved = self.repo.save_nav_batch(records)
        return len(records) + (self.repo.get_nav_history(fund_code, limit=1).__len__() if latest_date else 0), new_count

    def _update_accumulated_nav(self, df: pd.DataFrame, fund_code: str) -> int:
        """补充累计净值到已有记录"""
        count = 0
        for _, row in df.iterrows():
            nav_date = row.get("净值日期") or row.get("date") or row.get("日期")
            if nav_date:
                try:
                    nav_date = pd.to_datetime(nav_date).date()
                except Exception:
                    continue
                acc_nav = self._safe_float(row.get("累计净值") or row.get("accumulated_nav"))
                if acc_nav:
                    # SQLite upsert by saving again with accumulated_nav
                    self.repo.save_nav_batch([{
                        "fund_code": fund_code,
                        "nav_date": nav_date,
                        "unit_nav": None,
                        "accumulated_nav": self._round_nav(acc_nav, fund_code),
                        "daily_return": None,
                        "daily_change": None,
                    }])
                    count += 1
        return count

    def _persist_holdings(self, df: pd.DataFrame, fund_code: str) -> int:
        """解析并保存持仓数据"""
        # AKShare fund_portfolio_hold_em 常见返回列:
        # 序号, 股票代码, 股票名称, 占净值比例, 持股数, 持仓市值, 季度
        records = []
        for _, row in df.iterrows():
            report_date = self._parse_holding_report_date(row.get("报告期") or row.get("季度"))
            if not report_date:
                continue

            stock_code = str(row.get("股票代码", "")).strip()
            if not stock_code:
                continue

            market = "A"
            if stock_code.startswith(("0", "3", "6")):
                market = "A"
            elif stock_code.startswith(("hk", "HK")):
                market = "HK"

            records.append({
                "fund_code": fund_code,
                "report_date": report_date,
                "stock_code": stock_code,
                "stock_name": str(row.get("股票名称", "")).strip(),
                "stock_market": market,
                "holding_pct": self._safe_float(row.get("占净值比例")),
                "holding_shares": self._safe_float(row.get("持股数(万股)") or row.get("持股数")),
                "holding_amount": self._safe_float(row.get("持仓市值(万元)") or row.get("持仓市值")),
                "rank": self._safe_int(row.get("持仓序号") or row.get("序号") or row.get("rank")),
            })

        return self.repo.save_holdings(records)

    @staticmethod
    def _parse_holding_report_date(value) -> Optional[date]:
        if value is None or value == "":
            return None
        text = str(value).strip()
        quarter_match = re.search(r"(\d{4})年\s*([1-4])季度", text)
        if quarter_match:
            year = int(quarter_match.group(1))
            quarter = int(quarter_match.group(2))
            month_day = {
                1: (3, 31),
                2: (6, 30),
                3: (9, 30),
                4: (12, 31),
            }[quarter]
            return datetime(year, month_day[0], month_day[1]).date()
        try:
            return pd.to_datetime(text).date()
        except Exception:
            return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        try:
            if val is None or val == "" or val == "--":
                return None
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _round_nav(value: Optional[float], fund_code: str) -> Optional[float]:
        if value is None:
            return None
        return round_asset_price(value, symbol=fund_code, asset_category="fund")

    @staticmethod
    def _safe_int(val) -> Optional[int]:
        try:
            if val is None or val == "" or val == "--":
                return None
            return int(val)
        except (ValueError, TypeError):
            return None
