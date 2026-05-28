# -*- coding: utf-8 -*-
"""
===================================
AKShare 指数分钟线数据获取
===================================

用于获取 A 股指数的分钟线数据（分时图）
接口：index_zh_a_hist_min_em
"""

import logging
from typing import Optional, List, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


def get_index_minute_data_akshare(symbol: str, period: str = '1') -> Optional[List[Dict[str, Any]]]:
    """
    使用 akshare 获取指数分钟线数据
    
    Args:
        symbol: 指数代码（如 sh000001, sz399001）
        period: 周期（1/5/15/30/60 对应分钟）
        
    Returns:
        分钟线数据列表
    """
    try:
        import akshare as ak
        
        # 只取今天的数据
        today = pd.Timestamp.now().strftime('%Y-%m-%d 09:30:00')
        
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
        
        logger.debug(f"[AKShare] 获取 {symbol} 分钟线 {len(result)} 条")
        return result
        
    except Exception as e:
        logger.warning(f"[AKShare] 获取 {symbol} 分钟线失败：{e}")
        return None


def get_stock_minute_data_akshare(stock_code: str, days: int = 1) -> Optional[List[Dict[str, Any]]]:
    """
    获取 AKShare 分钟线数据（兼容接口）
    
    Args:
        stock_code: 股票代码（如 sh000001）
        days: 获取天数（忽略，只返回当天数据）
        
    Returns:
        分钟线数据列表（按时间正序）
    """
    # 只支持 A 股指数
    if not stock_code.startswith(('sh', 'sz')):
        return None
    
    result = get_index_minute_data_akshare(stock_code, period='5')
    
    if not result:
        return None
    
    # 按时间排序确保正序
    sorted_data = sorted(result, key=lambda x: x['date'])
    
    return sorted_data
