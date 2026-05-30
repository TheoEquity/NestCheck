# -*- coding: utf-8 -*-
"""
===================================
市场趋势数据服务
===================================
为 12 个核心指标计算周线数据 + 均线系统 (MA10/MA20/MA50)
并为每个指标输出环境标签 (趋势位 + 波动态 + 支撑距离)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
import logging
import json
from pathlib import Path
import time

logger = logging.getLogger(__name__)

MANAGER = None

def _get_manager():
    global MANAGER
    if MANAGER is None:
        try:
            from data_provider.base import DataFetcherManager
            MANAGER = DataFetcherManager()
        except Exception as e:
            logger.error(f"初始化 DataFetcherManager 失败: {e}")
    return MANAGER

# 缓存配置
CACHE_DIR = Path("/tmp/nestcheck_market_trend")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_EXPIRY_HOURS = 6  # 周线数据缓存 6 小时（周末不更新，工作日更新频率低）


def _load_cache(name: str) -> Optional[Dict[str, Any]]:
    """加载缓存数据"""
    cache_file = CACHE_DIR / f"{name}.json"
    if not cache_file.exists():
        return None
    
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        cached_at = datetime.fromisoformat(data.get("_cached_at", "1970-01-01"))
        if datetime.now() - cached_at > timedelta(hours=CACHE_EXPIRY_HOURS):
            return None
        
        return data
    except Exception:
        return None


def _save_cache(name: str, data: Dict[str, Any]):
    """保存缓存数据"""
    cache_file = CACHE_DIR / f"{name}.json"
    data_with_timestamp = {**data, "_cached_at": datetime.now().isoformat()}
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data_with_timestamp, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


MARKET_INDICES = [
    {"key": "a500", "label": "A500", "code": "sh000510"},
    {"key": "hs300", "label": "沪深300", "code": "sh000300"},
    {"key": "zz500", "label": "中证500", "code": "sh000905"},
    {"key": "sh", "label": "上证指数", "code": "sh000001"},
    {"key": "sz", "label": "深圳成指", "code": "sz399001"},
    {"key": "cyb", "label": "创业板指", "code": "sz399006"},
    {"key": "dji", "label": "道琼斯", "code": "^DJI"},
    {"key": "ixic", "label": "纳斯达克", "code": "^IXIC"},
    {"key": "gspc", "label": "标普500", "code": "^GSPC"},
    {"key": "dxy", "label": "美元指数", "code": "DX-Y.NYB"},
    {"key": "usdcny", "label": "美元兑人民币", "code": "USDCNY=X"},
    {"key": "tnx", "label": "10年期美债", "code": "^TNX"},
]


def _weekly_resample(df: pd.DataFrame) -> pd.DataFrame:
    """日线数据重采样为周线"""
    if df is None or df.empty or "date" not in df.columns:
        return pd.DataFrame()
    
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df = df.set_index("date")
    
    weekly = df.resample("W-FRI").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    
    return weekly.reset_index()


def _calc_ma(series: pd.Series, window: int) -> pd.Series:
    """计算移动平均线"""
    return series.rolling(window=window, min_periods=1).mean()


def _assess_environment(
    weekly_df: pd.DataFrame, 
    close: float, 
    ma10: float, 
    ma20: float, 
    ma50: float
) -> Dict[str, Any]:
    """
    评估当前市场环境
    
    趋势位：
      ✓ 周K 在 MA20 上方，MA20 斜率向上 → 多头环境
      ✗ 周K 在 MA20 下方，MA10下穿MA20 → 弱势环境
    
    波动态：
      ✓ 近4周振幅收敛 / 正常 → 可控
      ✗ 近2-3周出现 -5%+ 大周阴 → 高压
    
    支撑距离：
      ✓ 离最近周线支撑带 > 5% → 还有缓冲
      ✗ 正在测试/刚跌破关键支撑 → 脆弱
    """
    if len(weekly_df) < 4:
        return {
            "trend": "unknown",
            "volatility": "unknown",
            "support_pct": None,
            "support_status": "unknown",
            "label": "数据不足",
            "color": "gray",
        }
    
    # === 趋势位 ===
    ma20_slope = "unknown"
    if len(weekly_df) >= 2:
        prev_ma20 = weekly_df["ma20"].iloc[-2] if "ma20" in weekly_df.columns else ma20
        if ma20 > prev_ma20:
            ma20_slope = "up"
        else:
            ma20_slope = "down"
    
    if ma20_slope == "up" and close > ma20:
        trend = "bullish"  # 多头环境
    elif close < ma20 and ma10 < ma20:
        trend = "bearish"  # 弱势环境
    else:
        trend = "neutral"  # 中性/震荡
    
    # === 波动态 ===
    last_4 = weekly_df.tail(4)
    large_drop = any(
        (row["close"] - row["open"]) / row["open"] < -0.05 
        for _, row in last_4.iterrows()
    )
    volatility = "high_pressure" if large_drop else "controlled"
    
    # === 支撑距离 ===
    # 最近 10 周的最低点作为支撑参考
    recent_support = weekly_df.tail(10)["low"].min()
    if recent_support > 0:
        support_pct = round((close - recent_support) / close * 100, 2)
        support_status = "safe" if support_pct > 5.0 else "testing"
    else:
        support_pct = None
        support_status = "unknown"
    
    # === 综合标签 & 颜色 ===
    trend_label = {"bullish": "多头", "bearish": "弱势", "neutral": "震荡", "unknown": "未知"}.get(trend, "未知")
    vol_label = {"controlled": "可控", "high_pressure": "高压"}.get(volatility, "未知")
    sup_label = {"safe": "有缓冲", "testing": "脆弱", "unknown": "未知"}.get(support_status, "未知")
    
    label = f"{trend_label} · {vol_label} · {sup_label}"
    
    # 红黄绿评分逻辑
    if trend == "bullish" and volatility == "controlled" and support_status == "safe":
        color = "green"
    elif trend == "bearish" or volatility == "high_pressure" or (support_status == "testing" and support_pct is not None):
        if trend == "bearish" or volatility == "high_pressure":
            color = "red"
        else:
            color = "yellow"
    else:
        color = "yellow"
    
    return {
        "trend": trend,
        "volatility": volatility,
        "support_pct": support_pct,
        "support_status": support_status,
        "label": label,
        "color": color,
    }


def _normalize_code_for_fetch(code: str) -> str:
    """将前端代码格式 (sh000001) 转为数据源格式 (000001)"""
    if code.startswith(('sh', 'sz', 'SH', 'SZ')):
        return code[2:]
    return code


def _fetch_weekly_for_code(code: str) -> Optional[Tuple[pd.DataFrame, pd.DataFrame, Optional[Dict[str, Any]]]]:
    """获取指定代码的日线数据并转为周线，计算均线
    
    返回: (weekly_with_ma, raw_weekly, daily_latest)
      weekly_with_ma: 周线 + 均线
      raw_weekly: 原始周线
      daily_latest: 最新日线快照 {close, pct_chg} 或 None
    """
    start_time = time.time()
    
    try:
        manager = _get_manager()
        
        raw_code = code
        # Note: do NOT strip sh/sz prefix - codes are stored with prefix in stock_daily
        # The DB stores codes as sh000001, sz399001, ^DJI, etc.
        
        days_needed = 500
        
        # 优先从数据库读取
        from src.storage import get_db
        df = get_db().get_daily_history_df(raw_code, days=days_needed + 100)
        
        if df.empty:
            # 降级：数据库无数据，从网络现拉
            if manager is None:
                return None
            logger.info(f"[Trend] {code} 数据库无历史，降级现拉...")
            df, _ = manager.get_daily_data(raw_code, days=days_needed)
            if df is not None and not df.empty:
                # 补充入库以供下次使用
                try:
                    from src.storage import get_db
                    get_db().save_daily_data(df, raw_code, "network_fallback")
                except Exception as e:
                    logger.warning(f"[Trend] {code} fallback 入库失败: {e}")
        
        if df is None or df.empty:
            return None
        
        # 提取最新日线快照
        daily_latest = None
        if len(df) > 0:
            close_val = df["close"].iloc[-1]
            pct_val = df["pct_chg"].iloc[-1] if "pct_chg" in df.columns else 0.0
            daily_latest = {"close": round(float(close_val), 2), "pct_chg": round(float(pct_val), 2)}
        
        weekly = _weekly_resample(df)
        if "close" not in weekly.columns:
            return None
            
        weekly["ma10"] = _calc_ma(weekly["close"], 10)
        weekly["ma20"] = _calc_ma(weekly["close"], 20)
        weekly["ma50"] = _calc_ma(weekly["close"], 50)
        
        logger.info(f"获取周线 {code} 成功: {len(weekly)} 周, 耗时 {time.time()-start_time:.1f}s")
        
        return weekly, weekly[["date", "open", "high", "low", "close", "volume"]], daily_latest
        
    except Exception as e:
        logger.error(f"获取周线数据失败 {code}: {e}", exc_info=True)
        return None


def get_market_trend_data() -> Dict[str, Any]:
    """直接从 SQLite 读取历史底稿并即时计算趋势数据及环境评估"""
    
    result_data = {}
    
    for index in MARKET_INDICES:
        key = index["key"]
        code = index["code"]
        label = index["label"]
        
        fetched = _fetch_weekly_for_code(code)
        if fetched is None:
            result_data[key] = {
                "label": label,
                "code": code,
                "error": "数据加载失败",
                "weekly_data": [],
                "environment": {"label": "数据不足", "color": "gray"},
                "daily_close": None,
                "daily_pct_chg": None,
            }
            continue
        
        weekly_with_ma, raw_weekly, daily_latest = fetched
        
        daily_close = daily_latest["close"] if daily_latest else None
        daily_pct_chg = daily_latest["pct_chg"] if daily_latest else None
        
        close = float(raw_weekly["close"].iloc[-1]) if len(raw_weekly) > 0 else 0
        ma10 = float(weekly_with_ma["ma10"].iloc[-1]) if len(weekly_with_ma) > 0 else 0
        ma20 = float(weekly_with_ma["ma20"].iloc[-1]) if len(weekly_with_ma) > 0 else 0
        ma50 = float(weekly_with_ma["ma50"].iloc[-1]) if len(weekly_with_ma) > 0 else 0
        
        env = _assess_environment(weekly_with_ma, close, ma10, ma20, ma50)
        
        display_weeks = weekly_with_ma.tail(60)
        
        weekly_data_list = []
        for _, row in display_weeks.iterrows():
            date_val = row["date"]
            date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)
            weekly_data_list.append({
                "date": date_str,
                "open": round(float(row.get("open", 0)), 2),
                "high": round(float(row.get("high", 0)), 2),
                "low": round(float(row.get("low", 0)), 2),
                "close": round(float(row.get("close", 0)), 2),
                "volume": float(row.get("volume", 0)),
                "ma10": round(float(row.get("ma10", 0)), 2) if pd.notna(row.get("ma10")) else None,
                "ma20": round(float(row.get("ma20", 0)), 2) if pd.notna(row.get("ma20")) else None,
                "ma50": round(float(row.get("ma50", 0)), 2) if pd.notna(row.get("ma50")) else None,
            })
        
        result_data[key] = {
            "label": label,
            "code": code,
            "close": close,
            "daily_close": daily_close,
            "daily_pct_chg": daily_pct_chg,
            "ma10": ma10,
            "ma20": ma20,
            "ma50": ma50,
            "weekly_data": weekly_data_list,
            "environment": env,
        }
    
    return {
        "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
        "data": result_data,
    }
    
def get_monthly_seasonality(use_file_cache: bool = True) -> Dict[str, Any]:
    """统计沪深300近10年的月度涨跌幅（季节性规律）
    
    返回:
    {
        "months": ["1月", "2月", ..., "12月"],
        "avg_returns": [1.2, 3.5, ..., 2.0],
        "win_rates": [60, 80, ..., 70]
    }
    """
    cache = _load_cache("seasonality_csi300") if use_file_cache else None
    if cache:
        return cache
    
    try:
        # 优先从数据库读取
        from src.storage import get_db
        df = get_db().get_daily_history_df("sh000300", days=3650)
        
        if df.empty:
            # 降级：从网络获取
            manager = _get_manager()
            if manager is None:
                raise RuntimeError("DataFetcherManager 未初始化")
            
            df_raw, _ = manager.get_daily_data("000300", days=3650)
            if df_raw is not None and not df_raw.empty:
                try:
                    get_db().save_daily_data(df_raw, "sh000300", "network_fallback")
                    df = df_raw
                except Exception as e:
                    logger.warning(f"[Seasonality] fallback 入库失败: {e}")
                    df = df_raw
            else:
                df = df_raw
        
        if df is None or df.empty or len(df) < 365:
            raise RuntimeError("沪深300数据不足")
        
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        df = df.set_index("date")
        
        # 计算月度收益率
        monthly = df["close"].resample("ME").last()
        monthly_returns = monthly.pct_change().dropna() * 100  # 转为百分比
        
        stats = {}
        for month_num in range(1, 13):
            subset = monthly_returns[monthly_returns.index.month == month_num]
            avg = float(subset.mean()) if len(subset) > 0 else 0
            win_rate = float((subset > 0).sum() / len(subset) * 100) if len(subset) > 0 else 0
            stats[month_num] = {"avg": round(avg, 2), "win_rate": round(win_rate, 1)}
        
        months = [f"{m}月" for m in range(1, 13)]
        avg_returns = [stats[m]["avg"] for m in range(1, 13)]
        win_rates = [stats[m]["win_rate"] for m in range(1, 13)]
        
        result = {
            "months": months,
            "avg_returns": avg_returns,
            "win_rates": win_rates,
            "years_stat": len(monthly_returns) // 12,
            "index": "沪深300",
        }
        
        _save_cache("seasonality_csi300", result)
        return result
        
    except Exception as e:
        logger.error(f"获取月度季节性数据失败: {e}", exc_info=True)
        return {"months": [f"{m}月" for m in range(1, 13)], "avg_returns": [0]*12, "win_rates": [0]*12, "error": str(e)}
