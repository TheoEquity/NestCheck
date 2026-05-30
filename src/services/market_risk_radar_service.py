# -*- coding: utf-8 -*-
"""风险雷达图：6 维度风险体检 (按照最新严格算法重构)"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import logging
import warnings

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", message="Mean of empty slice") # Suppress pandas warnings

from .market_trend_service import _get_manager, _load_cache, _save_cache, CACHE_EXPIRY_HOURS


def _linear_interpolate(val: float, keys: list, values: list) -> float:
    """分段线性插值 (线性映射)"""
    if val <= keys[0]: return values[0]
    if val >= keys[-1]: return values[-1]
    
    for i in range(len(keys) - 1):
        if keys[i] <= val < keys[i+1]:
            ratio = (val - keys[i]) / (keys[i+1] - keys[i])
            return values[i] + ratio * (values[i+1] - values[i])
    return values[-1]

def _to_weekly_returns(s: pd.Series) -> pd.Series:
    """将日线序列转换为周收益序列 (周五收盘)"""
    s = s.copy()
    s.index = pd.to_datetime(s.index)
    weekly = s.resample("W-FRI").last().ffill(limit=1).dropna()
    return weekly.pct_change().dropna()

# =========================================================
# 1. 波动率 RV (0-100)
# 规则: 20D std * sqrt(252)
# 映射: <12->10, <16->30, <22->55, <30->80, >=30->100
# =========================================================
def calc_rv_score(close_daily: pd.Series) -> float:
    ret = close_daily.pct_change()
    rv_annual = ret.rolling(20).std().iloc[-1] * np.sqrt(252) * 100 # %
    # 映射
    if rv_annual < 12: return 10.0
    elif rv_annual < 16: return _linear_interpolate(rv_annual, [12, 16], [10, 30])
    elif rv_annual < 22: return _linear_interpolate(rv_annual, [16, 22], [30, 55])
    elif rv_annual < 30: return _linear_interpolate(rv_annual, [22, 30], [55, 80])
    else: return 100.0

# =========================================================
# 2. 回撤 DD (0-100)
# 规则: 60D 相对当前价位的最低回撤
# 映射: <5%->10, <10%->35, <15%->60, <25%->85, >=25%->100
# =========================================================
def calc_dd_score(close_daily: pd.Series) -> float:
    roll_max = close_daily.rolling(window=60, min_periods=20).max()
    dd = (close_daily.iloc[-1] / roll_max.iloc[-1] - 1) 
    dd_abs = abs(min(dd, 0)) * 100 # 转换为 %
    
    if dd_abs < 5: return 10.0
    elif dd_abs < 10: return _linear_interpolate(dd_abs, [5, 10], [10, 35])
    elif dd_abs < 15: return _linear_interpolate(dd_abs, [10, 15], [35, 60])
    elif dd_abs < 25: return _linear_interpolate(dd_abs, [15, 25], [60, 85])
    else: return 100.0

# =========================================================
# 3. 股债相关性 Corr (0-100)
# 规则: HS300 周收益 vs 债端周代理 (-delta y10y) -> 52W corr
# 映射: <-0.2->10, <0.0->25, <0.4->50, <0.7->75, >=0.7->100
# =========================================================
def calc_corr_score(stock_daily: pd.Series, bond_y10y_daily: pd.Series) -> float:
    r_stock = _to_weekly_returns(stock_daily)
    r_bond_proxy = (-bond_y10y_daily).pct_change().dropna()
    r_bond_weekly = _to_weekly_returns(bond_y10y_daily * -1) # * -1 让收益率变动像价格变动? 
    # 修正：代理逻辑是 bond_return ≈ -delta_y
    # 所以 bond_proxy 序列应该是 [-delta_y] 的周度变化? 不，直接用 -delta_y 作为周度收益的近似
    # 即 y10y_diff = y10y_t - y10y_{t-1} (周度变化). bond_ret_proxy = -y10y_diff
    
    b_weekly = bond_y10y_daily.resample("W-FRI").last().ffill(limit=1).diff() * -1
    merged = pd.concat([r_stock, b_weekly], axis=1).dropna()
    merged.columns = ['s', 'b']
    
    if len(merged) < 20: return 50.0
    
    corr_val = merged['s'].rolling(52).corr(merged['b']).dropna().iloc[-1]
    if np.isnan(corr_val): return 50.0
    
    if corr_val < -0.2: return 10.0
    elif corr_val < 0.0: return _linear_interpolate(corr_val, [-0.2, 0.0], [10, 25])
    elif corr_val < 0.4: return _linear_interpolate(corr_val, [0.0, 0.4], [25, 50])
    elif corr_val < 0.7: return _linear_interpolate(corr_val, [0.4, 0.7], [50, 75])
    else: return 100.0

# =========================================================
# 4. 信用利差 Spread (0-100)
# 新逻辑: 使用 ICE BofA 7-10Y 总回报指数的 60D 最大回撤作为利差风险代理
# 逻辑: 指数回撤越大，说明信用利差走阔越快，市场承受压力大，风险分越高
# =========================================================
def calc_spread_score() -> float:
    """信用利差风险分 (0-100)
    
    使用 ICE BofA 7-10Y 总回报指数的 60D 最大回撤作为利差风险代理。
    指数回撤越大 → 信用利差走阔越快 → 风险分越高。
    
    若网络无法获取，返回中性分 50（不对国债收益率做错误代理）。
    """
    try:
        from financetoolkit import FixedIncome
        fi = FixedIncome(start_date=(datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"))
        df = fi.get_ice_bofa_total_return(maturity=True)
        
        if df is None or df.empty:
            logger.warning("ICE BofA 数据为空，使用默认分 50")
            return 50.0

        if isinstance(df, pd.DataFrame):
            cols = [c for c in df.columns if '7 to 10' in str(c).lower()]
            if not cols: cols = [df.columns[0]]
            series = df[cols[0]].dropna()
        else:
            series = df.dropna()

        if len(series) < 60:
            return 50.0

        recent = series.tail(60)
        roll_max = recent.cummax()
        dd = (recent.iloc[-1] / roll_max.iloc[-1] - 1)
        dd_pct = abs(dd) * 100

        if dd_pct < 0.5: return 10.0
        elif dd_pct < 1.5: return _linear_interpolate(dd_pct, [0.5, 1.5], [10, 40])
        elif dd_pct < 3.0: return _linear_interpolate(dd_pct, [1.5, 3.0], [40, 70])
        else: return 100.0
    except Exception as e:
        logger.warning(f"计算 ICE BofA 利差失败: {e}")
        return 50.0

# =========================================================
# 5. 汇率压力 FX (0-100)
# 规则: USDCNY 近 20 日累计升幅 %
# 映射: <0.3->10, <1.0->30, <2.0->55, <3.5->80
# =========================================================
def calc_fx_score(usdcny_daily: pd.Series) -> float:
    if len(usdcny_daily) < 20: return 50.0
    chg = (usdcny_daily.iloc[-1] / usdcny_daily.iloc[-20] - 1) * 100
    if chg < 0.3: return 10.0
    elif chg < 1.0: return _linear_interpolate(chg, [0.3, 1.0], [10, 30])
    elif chg < 2.0: return _linear_interpolate(chg, [1.0, 2.0], [30, 55])
    elif chg < 3.5: return _linear_interpolate(chg, [2.0, 3.5], [55, 80])
    else: return 100.0

# =========================================================
# 6. 估值分位 Valuation (0-100)
# 降级策略: HS300 点位 5 年分位 (近似 PE 分位)
# =========================================================
def calc_valuation_score(price_daily: pd.Series) -> float:
    lookback = price_daily.tail(1825) # ~5 years
    if len(lookback) < 250: return 50.0
    rank_pct = (lookback < price_daily.iloc[-1]).sum() / len(lookback) * 100
    return rank_pct

def _get_bond_data() -> Tuple[pd.Series, float]:
    """获取国债数据: 返回 (日线序列, 最新值) - 优先读库"""
    try:
        from src.storage import get_db
        
        # 优先从数据库读取
        df = get_db().get_daily_history_df("bond_cn_10y", days=1500)
        
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            s = df.set_index('date')['close'].dropna()
            if len(s) > 50:
                return s, float(s.iloc[-1])
        
        # 降级：数据库无数据，从网络现拉
        import akshare as ak
        logger.info("[Radar] 债券数据降级现拉...")
        df_raw = ak.bond_zh_us_rate(start_date='2020-01-01')
        if df_raw is None or df_raw.empty:
            return pd.Series(dtype='float64'), 2.0
        
        df_raw['date'] = pd.to_datetime(df_raw['日期'])
        df_raw = df_raw.set_index('date')['中国国债收益率10年'].dropna()
        
        # 补充入库
        try:
            insert_df = pd.DataFrame({
                'date': df_raw.index.date,
                'close': df_raw.values,
                'open': df_raw.values,
                'high': df_raw.values,
                'low': df_raw.values,
                'volume': 0,
                'amount': 0,
                'pct_chg': 0,
            })
            get_db().save_daily_data(insert_df, "bond_cn_10y", "network_fallback")
        except Exception as e:
            logger.warning(f"[Radar] 债券 fallback 入库失败: {e}")
        
        return df_raw, float(df_raw.iloc[-1])
    except Exception as e:
        logger.warning(f"获取国债数据失败: {e}")
        return pd.Series(dtype='float64'), 2.0

def _get_usdcny_data() -> pd.Series:
    """获取 USDCNY 日线 - 优先读库"""
    try:
        from src.storage import get_db
        
        # 优先从数据库读取
        df = get_db().get_daily_history_df("USDCNY=X", days=200)
        
        if not df.empty:
            return df.set_index(pd.to_datetime(df['date']))['close']
        
        # 降级：从网络现拉
        manager = _get_manager()
        if not manager: return pd.Series()
        
        logger.info("[Radar] USDCNY 降级现拉...")
        df, _ = manager.get_daily_data("USDCNY=X", days=200)
        if df is None or df.empty: return pd.Series()
        
        # 补充入库
        try:
            get_db().save_daily_data(df, "USDCNY=X", "network_fallback")
        except Exception as e:
            pass
        
        return df.set_index(pd.to_datetime(df['date']))['close']
    except Exception as e:
        logger.warning(f"获取汇率数据失败: {e}")
        return pd.Series()

def get_risk_radar_data() -> Dict[str, Any]:
    """主入口：计算 6 维风险分数 - 直接读库即时计算"""
    scores = {
        "volatility": 50.0,
        "drawdown": 50.0,
        "correlation": 50.0,
        "spread": 50.0,
        "fx": 50.0,
        "valuation": 50.0,
        "details": {},
        "error": None,
    }

    try:
        from src.storage import get_db
        
        # 1. 核心资产：HS300 - 优先读库
        hs300_df = get_db().get_daily_history_df("sh000300", days=1600)
        
        if hs300_df.empty:
            # 降级：从网络现拉
            manager = _get_manager()
            if manager is None:
                scores["error"] = "数据源未初始化"
                return scores
            
            logger.info("[Radar] HS300 降级现拉...")
            hs300_df, source = manager.get_daily_data("000300", days=1500)
            if hs300_df is None or hs300_df.empty:
                scores["error"] = "沪深 300 数据不足"
                return scores
            
            # 补充入库
            try:
                get_db().save_daily_data(hs300_df, "sh000300", source or "network_fallback")
            except Exception as e:
                pass
            
        s_hs300_close = hs300_df.set_index(pd.to_datetime(hs300_df['date']))['close']

        # 2. 债端代理：中国 10Y 国债
        s_bond_y10y, latest_y10y = _get_bond_data()
        
        # 3. 汇率：USDCNY
        s_usdcny = _get_usdcny_data()

        # ======== Calculate Scores ======== #
        
        # RV
        scores["volatility"] = round(calc_rv_score(s_hs300_close), 1)
        rv_val = s_hs300_close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252) * 100
        scores["details"]["volatility_raw"] = round(rv_val, 2)

        # DD
        scores["drawdown"] = round(calc_dd_score(s_hs300_close), 1)
        roll_max = s_hs300_close.rolling(60).max()
        dd_val = (s_hs300_close.iloc[-1] / roll_max.iloc[-1] - 1) * 100
        scores["details"]["drawdown_raw"] = round(dd_val, 2)

        # Corr (requires both)
        if latest_y10y > 0 and len(s_bond_y10y) > 100:
            scores["correlation"] = round(calc_corr_score(s_hs300_close, s_bond_y10y), 1)
            
        # Spread (升级: ICE BofA 7-10Y 总回报 60D 回撤)
        spread_val = calc_spread_score()
        scores["spread"] = round(spread_val, 1)
        
        # 重新获取回撤数值以记录到 details
        try:
            from financetoolkit import FixedIncome
            fi = FixedIncome(start_date=(datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"))
            df = fi.get_ice_bofa_total_return(maturity=True)
            if isinstance(df, pd.DataFrame):
                cols = [c for c in df.columns if '7 to 10' in str(c).lower()]
                if not cols: cols = [df.columns[0]]
                series = df[cols[0]].dropna().tail(60)
            else:
                series = df.dropna().tail(60)
            
            roll_max = series.cummax()
            dd_pct = abs((series.iloc[-1] / roll_max.iloc[-1] - 1)) * 100
            scores["details"]["spread_raw"] = f"{dd_pct:.2f}%"
        except:
            scores["details"]["spread_raw"] = "N/A" 

        # FX
        scores["fx"] = round(calc_fx_score(s_usdcny), 1)
        scores["details"]["fx_raw"] = round((s_usdcny.iloc[-1] / s_usdcny.iloc[-20] - 1) * 100, 2) if len(s_usdcny) >= 20 else 0

        # Valuation (Price Percentile)
        scores["valuation"] = round(calc_valuation_score(s_hs300_close), 1)
        scores["details"]["valuation_raw"] = round((s_hs300_close.iloc[-1] / s_hs300_close.tail(1825).min()), 2) # 5-year multiple

    except Exception as e:
        logger.error(f"雷达计算崩溃: {e}", exc_info=True)
        scores["error"] = str(e)

    scores["label"] = _get_label(scores)
    return scores

def _get_label(scores: Dict[str, Any]) -> str:
    keys = ["volatility", "drawdown", "correlation", "spread", "fx", "valuation"]
    values = [scores.get(k, 50) for k in keys]
    avg = sum(values) / len(values)
    if avg < 30: return "green"
    elif avg < 60: return "yellow"
    else: return "red"
