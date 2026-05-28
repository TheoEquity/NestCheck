# -*- coding: utf-8 -*-
"""
===================================
Akshare 分钟线数据获取
===================================

用于获取 A 股和指数的分钟线数据（分时图）
"""

import logging
from typing import Optional, List, Dict, Any
import time

logger = logging.getLogger(__name__)


def get_stock_minute_data_akshare(stock_code: str, days: int = 1) -> Optional[List[Dict[str, Any]]]:
    """
    使用 akshare 获取分钟线数据
    
    Args:
        stock_code: 股票代码（如 sh000001, 600519）
        days: 获取天数（1-5）
        
    Returns:
        分钟线数据列表
    """
    try:
        import akshare as ak
        
        # 转换为 akshare 格式（sh/sz 前缀）
        if stock_code.startswith(('sh', 'sz')):
            symbol = stock_code
        elif stock_code[:6].isdigit():
            # 自动判断市场
            if stock_code.startswith('6'):
                symbol = f"sh{stock_code}"
            else:
                symbol = f"sz{stock_code}"
        else:
            # 其他格式不支持
            logger.debug(f"[Akshare] 不支持的代码格式：{stock_code}")
            return None
        
        # 重试机制
        for attempt in range(3):
            try:
                # 获取分钟线数据
                df = ak.stock_zh_a_hist_min_em(symbol=symbol, period='1', adjust='qfq')
                
                if df is None or df.empty:
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
                
                logger.debug(f"[Akshare] 获取 {symbol} 分钟线 {len(result)} 条")
                return result
                
            except Exception as e:
                logger.warning(f"[Akshare] 尝试 {attempt + 1} 失败：{e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    raise
        
    except Exception as e:
        logger.warning(f"[Akshare] 获取 {stock_code} 分钟线失败：{e}")
        return None
