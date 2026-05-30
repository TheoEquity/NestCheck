# -*- coding: utf-8 -*-
"""相关性热力图：5 个核心资产的滚动周收益相关性分析"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

from .market_trend_service import _get_manager, _load_cache, _save_cache


def _get_bond_ice_bofa_series() -> Optional[pd.Series]:
    """获取 ICE BofA 7-10Y 总回报指数的周收益率 (代表机构债市真实表现)
    
    逻辑：相比用 -ΔY10Y 近似，Total Return 包含了票息和资本利得，是真实的债券回报。
    """
    try:
        from financetoolkit import FixedIncome
        
        # 获取过去 3 年数据以确保 rolling 52 周计算稳健
        fi = FixedIncome(start_date=(datetime.now() - timedelta(days=1095)).strftime("%Y-%m-%d"))
        df = fi.get_ice_bofa_total_return(maturity=True)
        
        if df is None or df.empty:
            return None

        # 适配不同版本的 financetookit 返回格式 (Series 或 DataFrame)
        if isinstance(df, pd.DataFrame):
            # 寻找包含 '7 to 10' 的列名
            cols = [c for c in df.columns if '7 to 10' in str(c).lower()]
            if not cols: cols = [df.columns[0]] # Fallback
            series = df[cols[0]]
        else:
            series = df
            
        s = series.dropna()
        # 转为周收益率
        return s.pct_change().dropna()
        
    except Exception as e:
        logger.warning(f"获取 ICE BofA 总回报数据失败: {e}")
        return None


def _get_weekly_returns(df: pd.DataFrame, inverse_label: bool = False) -> pd.Series:
    """将日线转为周收益率"""
    if df is None or df.empty or "close" not in df.columns or len(df) < 30:
        return pd.Series()
    
    temp_df = df.copy()
    temp_df["date"] = pd.to_datetime(temp_df["date"])
    temp_df = temp_df.set_index("date")
    
    weekly = temp_df["close"].resample("W-FRI").last()
    
    if inverse_label:
        # 利率端：用收益率下降（-Δy）近似债券收益率 (保留此逻辑作为 Fallback)
        # 利率上升 = 债券跌 = 负收益
        weekly_ret = -weekly.diff()
    else:
        weekly_ret = weekly.pct_change()
    
    return weekly_ret.dropna()


def get_correlation_heatmap_data() -> Dict[str, Any]:
    """计算 5 个核心资产的滚动 52 周相关性矩阵 - 直接读库即时计算"""
    manager = _get_manager()
    if manager is None:
        return {"labels": [], "data": [], "error": "数据源未初始化"}
    
    assets_config = [
        {"key": "csi300", "label": "沪深300", "code": "sh000001"},
        {"key": "bond", "label": "债券(中债)", "is_bond": True},
        {"key": "dxy", "label": "美元(DXY)", "code": "DX-Y.NYB"},
        {"key": "spx", "label": "美股(SPX)", "code": "^GSPC"},
        {"key": "cyb", "label": "创业板(创)", "code": "sz399006"},
    ]
    
    returns_dict = {}
    
    for asset in assets_config:
        try:
            if asset.get("is_bond"):
                # 债券特殊处理：使用 ICE BofA 7-10Y 总回报指数
                bond_ret_weekly = _get_bond_ice_bofa_series()
                if bond_ret_weekly is not None and len(bond_ret_weekly) > 10:
                    bond_ret_weekly.index = pd.to_datetime(bond_ret_weekly.index)
                    returns_dict[asset["key"]] = bond_ret_weekly.tail(52)
                else:
                    logger.warning("资产 债券(中债) 周收益数据不足 (ICE BofA)")
            else:
                # 优先从数据库读取
                from src.storage import get_db
                code = asset["code"]
                df = get_db().get_daily_history_df(code, days=900)
                
                if df.empty:
                    # 降级：从网络现拉
                    logger.info(f"[Correlation] {code} 降级现拉...")
                    df, source = manager.get_daily_data(code, days=800)
                    if df is not None and not df.empty:
                        try:
                            get_db().save_daily_data(df, code, source or "network_fallback")
                        except Exception as e:
                            pass
                    else:
                        logger.warning(f"资产 {asset['label']} 现拉失败")
                        continue
                
                ret = _get_weekly_returns(df)
                if len(ret) > 10:
                    returns_dict[asset["key"]] = ret.tail(52)
                else:
                    logger.warning(f"资产 {asset['label']} 周收益数据不足")
        except Exception as e:
            logger.warning(f"获取相关性资产 {asset['label']} 失败: {e}")
    
    if len(returns_dict) < 2:
        return {"labels": [], "data": [], "error": "有效资产数据不足"}
    
    labels = []
    assets_series = []
    
    for asset in assets_config:
        key = asset["key"]
        if key in returns_dict:
            labels.append(asset["label"])
            assets_series.append(returns_dict[key])
    
    returns_df = pd.concat(assets_series, axis=1).dropna()
    
    if len(returns_df) < 10:
        return {"labels": labels, "data": [], "error": "重叠数据不足"}
    
    corr = returns_df.corr()
    
    data = []
    for i in range(len(labels)):
        for j in range(len(labels)):
            val = corr.iloc[i, j]
            data.append([i, j, round(float(val), 2)])
    
    return {"labels": labels, "data": data, "error": None}
