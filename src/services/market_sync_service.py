"""
市场数据同步服务
- 负责 12 个大盘指数 + 4 个情绪指标的抓取与入库
- 统一落库到 stock_daily 表
"""

import akshare as ak
import pandas as pd
import logging
from typing import List, Dict, Any
from src.storage import StorageManager
from datetime import datetime, timedelta
import time
import random
from data_provider.base import DataFetcherManager

logger = logging.getLogger(__name__)

AKSHARE_MAX_RETRIES = 3
AKSHARE_RETRY_DELAY = 2  # seconds

# 定义需要同步的指标列表
# code: 存入 stock_daily 的标识
# source: akshare / yfinance
# fetch_func: 对应的抓取函数名
# days: 增量默认 30 天，初始化可设为大数值

MARKET_INDICES = [
    # A 股指数 (akshare: index_zh_a_hist)
    {"code": "sh000510", "source": "akshare", "name": "中证A500", "func": "index_zh_a_hist", "period": "daily"},
    {"code": "sh000300", "source": "akshare", "name": "沪深300", "func": "index_zh_a_hist", "period": "daily"},
    {"code": "sh000905", "source": "akshare", "name": "中证500", "func": "index_zh_a_hist", "period": "daily"},
    {"code": "sh000001", "source": "akshare", "name": "上证指数", "func": "index_zh_a_hist", "period": "daily"},
    {"code": "sz399001", "source": "akshare", "name": "深证成指", "func": "index_zh_a_hist", "period": "daily"},
    {"code": "sz399006", "source": "akshare", "name": "创业板指", "func": "index_zh_a_hist", "period": "daily"},

    # 美股/外汇/美债 (yfinance)
    {"code": "^DJI", "source": "yfinance", "name": "道琼斯"},
    {"code": "^IXIC", "source": "yfinance", "name": "纳斯达克"},
    {"code": "^GSPC", "source": "yfinance", "name": "标普500"},
    {"code": "DX-Y.NYB", "source": "yfinance", "name": "美元指数"},
    {"code": "USDCNY=X", "source": "yfinance", "name": "美元兑人民币"},
    {"code": "^TNX", "source": "yfinance", "name": "10年期美债"},

    # 情绪指标 (特殊处理)
    {"code": "cn_vix", "source": "akshare", "name": "A股恐慌(QVIX)", "func": "index_option_300etf_qvix"},
    {"code": "us_vix", "source": "yfinance", "name": "美股恐慌(VIX)", "yfinance_symbol": "^VIX"},
    {"code": "bond_cn_10y", "source": "akshare", "name": "中国10年国债", "func": "bond_zh_us_rate"},
    {"code": "bond_us_10y", "source": "akshare", "name": "美国10年国债", "func": "bond_zh_us_rate"},
]

def _normalize_yfinance(df, code, days):
    """标准化 YFinance 数据到入库格式"""
    df = df.copy()
    if df.empty:
        return pd.DataFrame()
    df.index.name = 'date'
    df = df.reset_index()
    df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
    
    # YFinance 可能没有 amount 和 pct_chg，计算 pct_chg
    df['pct_chg'] = df['close'].pct_change() * 100
    df['amount'] = 0
    
    # 确保列顺序
    cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
    df = df[[c for c in cols if c in df.columns]]
    df['date'] = pd.to_datetime(df['date']).dt.date
    df = df.tail(days + 10) # 多取一点兜底
    return df

def _normalize_akshare_index(df, code, days):
    """标准化 AkShare 指数数据"""
    df = df.copy()
    if df.empty:
        return pd.DataFrame()
    df = df.rename(columns={
        '日期': 'date', '开盘': 'open', '最高': 'high', '最低': 'low', 
        '收盘': 'close', '成交量': 'volume', '成交额': 'amount', '涨跌幅': 'pct_chg'
    })
    df['date'] = pd.to_datetime(df['date']).dt.date
    df = df.tail(days + 10)
    return df

def _fetch_cn_vix(days):
    """抓取 A 股恐慌指数 QVIX"""
    last_err = None
    for attempt in range(AKSHARE_MAX_RETRIES):
        try:
            df = ak.index_option_300etf_qvix()
            df = df.rename(columns={'date': 'date', 'qvix': 'close'})
            df['open'] = df['close']
            df['high'] = df['close']
            df['low'] = df['close']
            df['volume'] = 0
            df['amount'] = 0
            df['pct_chg'] = df['close'].pct_change() * 100
            df['date'] = pd.to_datetime(df['date']).dt.date
            return df.tail(days + 10)
        except Exception as e:
            last_err = e
            if attempt < AKSHARE_MAX_RETRIES - 1:
                wait = AKSHARE_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"QVIX fetch failed (attempt {attempt+1}/{AKSHARE_MAX_RETRIES}), retrying in {wait:.1f}s")
                time.sleep(wait)
    logger.warning(f"Failed to fetch QVIX after retries: {last_err}")
    return pd.DataFrame()

def _fetch_bond_data(days):
    """抓取中美 10 年国债收益率"""
    last_err = None
    for attempt in range(AKSHARE_MAX_RETRIES):
        try:
            df = ak.bond_zh_us_rate()
            df_cn = df[['日期', '中国国债收益率10年']].dropna()
            df_cn = df_cn.rename(columns={'日期': 'date', '中国国债收益率10年': 'close'})
            df_cn['code'] = 'bond_cn_10y'
            
            df_us = df[['日期', '美国国债收益率10年']].dropna()
            df_us = df_us.rename(columns={'日期': 'date', '美国国债收益率10年': 'close'})
            df_us['code'] = 'bond_us_10y'

            result = []
            for tmp in [df_cn, df_us]:
                tmp['open'] = tmp['close']
                tmp['high'] = tmp['close']
                tmp['low'] = tmp['close']
                tmp['volume'] = 0
                tmp['amount'] = 0
                tmp['pct_chg'] = 0
                tmp['date'] = pd.to_datetime(tmp['date']).dt.date
                result.append(tmp.tail(days + 10))
            return result
        except Exception as e:
            last_err = e
            if attempt < AKSHARE_MAX_RETRIES - 1:
                wait = AKSHARE_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"Bond data fetch failed (attempt {attempt+1}/{AKSHARE_MAX_RETRIES}), retrying in {wait:.1f}s")
                time.sleep(wait)
    logger.warning(f"Failed to fetch bond rates after retries: {last_err}")
    return [pd.DataFrame(), pd.DataFrame()]

def sync_market_data(days=30):
    """执行市场指标同步"""
    manager = StorageManager()
    fetcher_manager = DataFetcherManager()
    stats = {"success": 0, "total": 16}
    
    logger.info(f"开始同步大盘/情绪数据，目标 {days} 天...")

    for item in MARKET_INDICES:
        code = item['code']
        source = item['source']
        name = item.get('name', code)
        
        # 根据 days 参数动态计算起始日期
        if days > 365:
            # 初始化模式：拉取指定天数
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        else:
            # 增量模式：固定拉取最近 100 天兜底
            start_date = (datetime.now() - timedelta(days=100)).strftime("%Y%m%d")
        
        try:
            if code == 'cn_vix':
                df = _fetch_cn_vix(days)
                if not df.empty:
                    manager.save_daily_data(df, code, 'akshare')
                    stats["success"] += 1
            
            elif code in ['bond_cn_10y', 'bond_us_10y']:
                # 债券数据一起抓，分别存
                dfs = _fetch_bond_data(days)
                for df in dfs:
                    if not df.empty:
                        c = df.iloc[0]['code']
                        manager.save_daily_data(df.drop(columns=['code']), c, 'akshare')
                        stats["success"] += 1
                continue # Skip standard logic below as we handled it here

            elif source == 'yfinance':
                fetch_code = item.get('yfinance_symbol', code)
                df_std, source_name = fetcher_manager.get_daily_data(fetch_code, days=days)
                if df_std is not None and not df_std.empty:
                    manager.save_daily_data(df_std, code, source_name or 'network_fallback')
                    stats["success"] += 1

            elif source == 'akshare':
                # A 股指数优先走统一数据源管理器，保留 AkShare 直连作为兜底。
                raw_code = code.replace('sz', '').replace('sh', '')
                try:
                    df_std, source_name = fetcher_manager.get_daily_data(raw_code, days=days)
                    if df_std is not None and not df_std.empty:
                        manager.save_daily_data(df_std, code, source_name or 'network_fallback')
                        stats["success"] += 1
                        time.sleep(0.5)
                        continue
                except Exception as e:
                    logger.warning(f"Unified fetcher failed for {name}({code}), fallback to direct AkShare: {e}")

                df_raw = None
                last_err = None
                for attempt in range(AKSHARE_MAX_RETRIES):
                    try:
                        df_raw = ak.index_zh_a_hist(
                            symbol=raw_code,
                            period=item['period'],
                            start_date=start_date,
                            end_date=datetime.now().strftime("%Y%m%d")
                        )
                        break
                    except Exception as e:
                        last_err = e
                        if attempt < AKSHARE_MAX_RETRIES - 1:
                            wait = AKSHARE_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1)
                            logger.warning(f"AkShare fetch failed for {name} (attempt {attempt+1}/{AKSHARE_MAX_RETRIES}): {e}, retrying in {wait:.1f}s")
                            time.sleep(wait)
                
                if df_raw is not None and not df_raw.empty:
                    df_std = _normalize_akshare_index(df_raw, code, days)
                    if not df_std.empty:
                        manager.save_daily_data(df_std, code, 'akshare')
                        stats["success"] += 1
                elif last_err:
                    logger.error(f"AkShare exhausted retries for {name}({code}): {last_err}")
            
            # 短暂休眠防爆
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Sync failed for {name}({code}): {e}")

    logger.info(f"同步完成: {stats['success']}/{stats['total']}")
    return stats
