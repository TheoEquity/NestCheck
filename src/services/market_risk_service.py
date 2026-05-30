# -*- coding: utf-8 -*-
"""
===================================
市场风险指标服务
===================================

参考：/workspace/Code_01.py
特点：
1. 本地 JSON 缓存，避免频繁调用 AkShare
2. 缓存过期时间可配置
3. 失败时返回缓存数据
"""

import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# 缓存配置
CACHE_DIR = Path("/tmp/nestcheck_market_risk")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_EXPIRY_HOURS = 12  # 缓存过期时间（小时）


def _load_cache(name: str) -> Optional[Dict[str, Any]]:
    """加载缓存数据"""
    cache_file = CACHE_DIR / f"{name}.json"
    if not cache_file.exists():
        return None
    
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 检查缓存是否过期
        cached_at = datetime.fromisoformat(data.get("_cached_at", "1970-01-01"))
        if datetime.now() - cached_at > timedelta(hours=CACHE_EXPIRY_HOURS):
            logger.info(f"缓存 {name} 已过期")
            return None
        
        return data
    except Exception as e:
        logger.warning(f"读取缓存失败 {name}: {e}")
        return None


def _save_cache(name: str, data: Dict[str, Any]):
    """保存缓存数据"""
    cache_file = CACHE_DIR / f"{name}.json"
    data_with_timestamp = {
        **data,
        "_cached_at": datetime.now().isoformat()
    }
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data_with_timestamp, f, ensure_ascii=False, indent=2)
        logger.info(f"缓存已保存 {name}")
    except Exception as e:
        logger.error(f"保存缓存失败 {name}: {e}")


def _dollar_index() -> Dict[str, Any]:
    """
    美元指数：用美元对人民币汇率代表 - 优先读库
    
    数据源：数据库优先，降级 currency_boc_safe
    """
    # 先查缓存
    cache = _load_cache("dollar")
    if cache:
        return cache
    
    # 优先从数据库读取
    try:
        from src.storage import get_db
        df = get_db().get_daily_history_df("USDCNY=X", days=10)
        if not df.empty:
            latest = df.iloc[-1]
            usd_cny = float(latest['close'])
            
            if usd_cny > 7.3:
                status = "偏强"
                badge = "warning"
                description = "留意人民币资产波动"
            elif usd_cny > 7.5:
                status = "强势"
                badge = "danger"
                description = "美元强势，注意风险"
            elif usd_cny < 7.0:
                status = "偏弱"
                badge = "success"
                description = "美元走弱，利好新兴市场"
            else:
                status = "中性"
                badge = "default"
                description = "汇率正常波动"
            
            result = {
                "value": round(usd_cny, 4),
                "status": status,
                "badge": badge,
                "description": description,
                "date": str(latest.get('date', datetime.now().strftime("%Y-%m-%d")))
            }
            _save_cache("dollar", result)
            return result
    except Exception as e:
        logger.warning(f"读取数据库汇率失败: {e}")
    
    # 降级：从网络现拉
    try:
        df = ak.currency_boc_safe()
        latest = df.iloc[-1]
        
        usd_cny = float(latest['美元']) / 100.0
        
        if usd_cny > 7.3:
            status = "偏强"
            badge = "warning"
            description = "留意人民币资产波动"
        elif usd_cny > 7.5:
            status = "强势"
            badge = "danger"
            description = "美元强势，注意风险"
        elif usd_cny < 7.0:
            status = "偏弱"
            badge = "success"
            description = "美元走弱，利好新兴市场"
        else:
            status = "中性"
            badge = "default"
            description = "汇率正常波动"
        
        result = {
            "value": round(usd_cny, 4),
            "status": status,
            "badge": badge,
            "description": description,
            "date": str(latest.get('日期', datetime.now().strftime("%Y-%m-%d")))
        }
        _save_cache("dollar", result)
        return result
    
    except Exception as e:
        logger.warning(f"获取美元汇率失败：{e}")
        return {
            "status": "获取失败",
            "badge": "default",
            "description": "请稍后刷新"
        }


def _bond_spread() -> Dict[str, Any]:
    """
    债市信号：中美 10 年期国债收益率利差 - 优先读库
    
    数据源：数据库 bond_cn_10y / bond_us_10y，降级 bond_zh_us_rate
    """
    cache = _load_cache("bond")
    if cache:
        return cache
    
    us_10y = None
    cn_10y = None
    date = None
    
    # 优先从数据库读取
    try:
        from src.storage import get_db
        
        df_cn = get_db().get_daily_history_df("bond_cn_10y", days=10)
        df_us = get_db().get_daily_history_df("bond_us_10y", days=10)
        
        if not df_cn.empty and not df_us.empty:
            cn_10y = float(df_cn.iloc[-1]['close'])
            us_10y = float(df_us.iloc[-1]['close'])
            date = str(df_cn.iloc[-1].get('date', datetime.now().strftime("%Y-%m-%d")))
    except Exception as e:
        logger.warning(f"读取数据库债券数据失败: {e}")
    
    # 降级：从网络现拉
    if us_10y is None:
        try:
            logger.info("[Risk] 利差降级现拉...")
            df = ak.bond_zh_us_rate()
            
            for i in range(len(df)-1, max(0, len(df)-10), -1):
                row = df.iloc[i]
                val = row.get('美国国债收益率10年')
                if str(val) != 'nan' and val is not None:
                    us_10y = float(val)
                    cn_10y = float(row['中国国债收益率10年'])
                    date = str(row.get('日期', datetime.now().strftime("%Y-%m-%d")))
                    break
        except Exception as e:
            logger.warning(f"网络拉取债券数据失败: {e}")
    
    if us_10y is None:
        return {"status": "数据缺失", "badge": "default", "description": "美国国债数据暂缺"}
    
    spread = us_10y - cn_10y
    
    if spread > 3:
        status = "倒挂扩大"
        badge = "danger"
        description = "中美利差高位，人民币贬值压力大"
    elif spread > 2:
        status = "偏高水平"
        badge = "warning"
        description = "中美利差偏高，关注汇率波动"
    else:
        status = "正常"
        badge = "success"
        description = "利率环境稳定"
    
    result = {
        "us_10y": round(us_10y, 2),
        "cn_10y": round(cn_10y, 2),
        "spread": round(spread, 2),
        "status": status,
        "badge": badge,
        "description": description,
        "date": date
    }
    _save_cache("bond", result)
    return result


def _chinese_vix() -> Dict[str, Any]:
    """
    A 股恐慌指数（中国波指）- 优先读库
    
    数据源：数据库 cn_vix，降级 index_option_300etf_qvix
    """
    cache = _load_cache("chinese_vix")
    if cache:
        return cache
    
    try:
        from src.storage import get_db
        
        df = get_db().get_daily_history_df("cn_vix", days=1300)
        
        if df.empty:
            # 降级：从网络现拉
            logger.info("[Risk] A股VIX 降级现拉...")
            df = ak.index_option_300etf_qvix()
            if df.empty:
                return {"error": "数据为空"}
            
            # 补充入库
            try:
                insert_df = df.rename(columns={'date': 'date', 'qvix': 'close'})
                insert_df['open'] = insert_df['close']
                insert_df['high'] = insert_df['close']
                insert_df['low'] = insert_df['close']
                insert_df['volume'] = 0
                insert_df['amount'] = 0
                insert_df['date'] = pd.to_datetime(insert_df['date']).dt.date
                get_db().save_daily_data(insert_df, "cn_vix", "network_fallback")
            except Exception as e:
                pass
        else:
            df = df.rename(columns={'close': 'close', 'date': 'date'})
        
        current = float(df.iloc[-1]['close'])
        hist_5y = df.tail(1250)
        percentile = (hist_5y['close'] < current).mean()
        
        if current < 20:
            status = "温和"
            badge = "success"
            description = f"市场情绪平稳 (历史{round(percentile*100)}% 分位)"
        elif current < 30:
            status = "警惕"
            badge = "warning"
            description = f"波动率上升 (历史{round(percentile*100)}% 分位)"
        else:
            status = "恐慌"
            badge = "danger"
            description = f"市场恐慌 (历史{round(percentile*100)}% 分位)"
        
        result = {
            "value": round(current, 2),
            "percentile": round(float(percentile * 100), 1),
            "status": status,
            "badge": badge,
            "description": description,
            "date": str(df.iloc[-1].get('date', datetime.now().strftime("%Y-%m-%d")))
        }
        _save_cache("chinese_vix", result)
        return result
    
    except Exception as e:
        logger.warning(f"获取 A 股 VIX 失败：{e}")
        return {
            "status": "获取失败",
            "badge": "default",
            "description": "请稍后刷新"
        }


def _us_vix() -> Dict[str, Any]:
    """
    美股恐慌指数（VIX）- 优先读库
    
    数据源：数据库 us_vix，降级 yfinance ^VIX
    """
    cache = _load_cache("us_vix")
    if cache:
        return cache
    
    try:
        from src.storage import get_db
        
        df = get_db().get_daily_history_df("us_vix", days=10)
        
        if df.empty:
            import yfinance as yf
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="10d")
            if hist.empty:
                return {"error": "数据为空"}
            
            # 补充入库
            import pandas as pd
            try:
                insert_df = pd.DataFrame({
                    'date': hist.index.date,
                    'close': hist['Close'].values,
                    'open': hist['Open'].values,
                    'high': hist['High'].values,
                    'low': hist['Low'].values,
                    'volume': 0,
                    'amount': 0,
                })
                get_db().save_daily_data(insert_df, "us_vix", "network_fallback")
                df = insert_df
            except Exception as e:
                pass
        else:
            df = df.rename(columns={'close': 'close', 'date': 'date'})
        
        current = float(df.iloc[-1]['close'])
        
        if current < 20:
            status = "温和"
            badge = "success"
            description = "美股市场情绪平稳"
        elif current < 30:
            status = "警惕"
            badge = "warning"
            description = "美股波动率上升"
        else:
            status = "恐慌"
            badge = "danger"
            description = "美股恐慌情绪蔓延"
        
        result = {
            "value": round(current, 2),
            "status": status,
            "badge": badge,
            "description": description,
            "date": str(df.iloc[-1].get('date', datetime.now().strftime("%Y-%m-%d")))
        }
        _save_cache("us_vix", result)
        return result
    
    except Exception as e:
        logger.warning(f"获取美股 VIX 失败：{e}")
        return {
            "status": "获取失败",
            "badge": "default",
            "description": "请稍后刷新"
        }


def _vix_index() -> Dict[str, Any]:
    """
    VIX 恐慌指数（中国波指）
    
    数据源：index_option_300etf_qvix (沪深 300ETF 波动率指数)
    """
    # 先查缓存
    cache = _load_cache("vix")
    if cache:
        return cache
    
    # 获取新数据
    try:
        df = ak.index_option_300etf_qvix()
        if df.empty:
            return {"error": "数据为空"}
        
        current = float(df.iloc[-1]['close'])
        hist_5y = df.tail(1250)
        percentile = (hist_5y['close'] < current).mean()
        
        if current < 20:
            status = "温和"
            badge = "success"
        elif current < 30:
            status = "警惕"
            badge = "warning"
        else:
            status = "恐慌"
            badge = "danger"
        
        result = {
            "value": round(current, 2),
            "percentile": round(float(percentile * 100), 1),
            "status": status,
            "badge": badge,
            "description": f"中国波指 {round(current, 2)} (历史{round(percentile*100)}% 分位)",
            "date": df.iloc[-1]['date'].strftime("%Y-%m-%d") if hasattr(df.iloc[-1]['date'], 'strftime') else str(df.iloc[-1]['date'])
        }
        _save_cache("vix", result)
        return result
    
    except Exception as e:
        logger.warning(f"获取 VIX 失败：{e}")
        return {
            "status": "获取失败",
            "badge": "default",
            "description": "请稍后刷新"
        }


def calculate_market_risk() -> Dict[str, Any]:
    """
    计算综合市场风险指标
    
    返回 4 个仪表盘指标：
    1. A 股恐慌指数 (0-50)
    2. 美股恐慌指数 (0-50)
    3. 美元强弱 (6.5-7.8)
    4. 中美利差 (-2% - 4%)
    """
    chinese_vix = _chinese_vix()
    us_vix = _us_vix()
    dollar = _dollar_index()
    bond = _bond_spread()
    
    return {
        "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
        "chinese_vix": chinese_vix,
        "us_vix": us_vix,
        "dollar_strength": dollar,
        "bond_spread": bond,
    }


def clear_cache():
    """清空所有缓存"""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
        logger.info("缓存已清空")
