# -*- coding: utf-8 -*-
"""
===================================
AKShare 指数分钟线数据获取
===================================

用于获取 A 股指数的分钟线数据（分时图）
接口：index_zh_a_hist_min_em（东财数据源）
"""

import logging
from typing import Optional, List, Dict, Any
import pandas as pd
import time

logger = logging.getLogger(__name__)


def get_index_minute_data_akshare(symbol: str, period: str = '5', max_retries: int = 5) -> Optional[List[Dict[str, Any]]]:
    """
    使用 akshare 获取指数分钟线数据（带重试机制）
    
    Args:
        symbol: 指数代码（如 sh000001, sz399001）
        period: 周期（1/5/15/30/60 对应分钟）
        max_retries: 最大重试次数
        
    Returns:
        分钟线数据列表
    """
    import akshare as ak
    
    # 只取今天的数据
    today = pd.Timestamp.now().strftime('%Y-%m-%d 09:30:00')
    
    for attempt in range(max_retries):
        try:
            df = ak.index_zh_a_hist_min_em(
                symbol=symbol,
                period=period,
                start_date=today,
                end_date='2222-01-01 09:32:00'
            )
            
            if df is None or df.empty:
                logger.debug(f"[AKShare] 指数 {symbol} 无分钟线数据")
                return None
            
            result = []
            for _, row in df.iterrows():
                result.append({
                    "date": str(row.get('时间', '')),
                    "open": float(row.get('开盘', 0)),
                    "high": float(row.get('最高', 0)),
                    "low": float(row.get('最低', 0)),
                    "close": float(row.get('收盘', 0)),
                    "volume": int(row.get('成交量', 0)) if row.get('成交量') is not None else None,
                    "amount": float(row.get('成交额', 0)) if row.get('成交额') is not None else None,
                    "change_percent": None,
                })
            
            logger.info(f"[AKShare] 获取 {symbol} 分钟线 {len(result)} 条 (尝试 {attempt + 1}/{max_retries})")
            return result
            
        except Exception as e:
            error_msg = str(e)
            # 网络错误时重试
            if 'Connection' in error_msg or 'timeout' in error_msg.lower() or 'RemoteDisconnected' in error_msg:
                wait_time = (attempt + 1) * 2  # 2s, 4s, 6s, 8s, 10s
                logger.warning(f"[AKShare] 网络错误，{wait_time}秒后重试 ({attempt + 1}/{max_retries}): {symbol}")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
            else:
                # 其他错误（如参数错误）直接返回
                logger.warning(f"[AKShare] {symbol} 获取失败：{error_msg}")
                return None
    
    logger.error(f"[AKShare] {symbol} 重试{max_retries}次均失败")
    return None


def get_stock_minute_data_akshare(stock_code: str, days: int = 1, max_retries: int = 5) -> Optional[List[Dict[str, Any]]]:
    """
    获取 AKShare 分钟线数据（兼容接口）
    
    Args:
        stock_code: 股票代码（如 sh000001）
        days: 获取天数（忽略，只返回当天数据）
        max_retries: 最大重试次数
        
    Returns:
        分钟线数据列表（按时间正序），网络不好时会重试
    """
    # 只支持 A 股指数
    if not stock_code.startswith(('sh', 'sz')):
        return None
    
    result = get_index_minute_data_akshare(stock_code, period='5', max_retries=max_retries)
    
    if not result:
        return None
    
    # 按时间排序确保正序
    sorted_data = sorted(result, key=lambda x: x['date'])
    
    return sorted_data
