# -*- coding: utf-8 -*-
"""
===================================
腾讯财经分钟线数据获取
===================================

用于获取 A 股指数的分钟线数据（分时图）
接口：http://data.gtimg.cn/flashdata/hushen/minute/{code}.js
"""

import logging
import re
from typing import Optional, List, Dict, Any
import time

logger = logging.getLogger(__name__)


def parse_tencent_minute_data(stock_code: str) -> Optional[List[Dict[str, Any]]]:
    """
    解析腾讯财经分钟线数据
    
    Args:
        stock_code: 股票代码（如 sh000001）
        
    Returns:
        分钟线数据列表
    """
    import requests
    
    try:
        # 腾讯分钟线接口
        symbol = stock_code.lower() if stock_code.startswith(('sh', 'sz')) else f'sh{stock_code}'
        url = f'http://data.gtimg.cn/flashdata/hushen/minute/{symbol}.js'
        
        headers = {
            'Referer': 'http://stockapp.finance.qq.com/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            logger.debug(f"[Tencent] HTTP {resp.status_code}: {stock_code}")
            return None
        
        text = resp.text
        
        # 提取 min_data 内容
        match = re.search(r'min_data="(.*?)"', text, re.DOTALL)
        if not match:
            logger.debug(f"[Tencent] 未找到 min_data: {stock_code}")
            return None
        
        lines = match.group(1).strip().split('\\n\\')
        
        result = []
        current_date = ""
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('\\'):
                continue
            
            # 解析日期行：date:211008
            if line.startswith('date:'):
                current_date = line.replace('date:', '')
                # 转换日期格式：211008 -> 2021-10-08
                if len(current_date) == 6:
                    current_date = f"20{current_date[:2]}-{current_date[2:4]}-{current_date[4:]}"
                continue
            
            # 解析数据行：0930 3609.09 20976544
            parts = line.split()
            if len(parts) >= 3:
                time_str = parts[0]  # 0930
                price_str = parts[1]  # 3609.09
                volume_str = parts[2]  # 20976544
                
                try:
                    # 格式化时间：0930 -> 09:30
                    time_formatted = f"{time_str[:2]}:{time_str[2:]}"
                    date_time = f"{current_date} {time_formatted}:00"
                    
                    price = float(price_str)
                    volume = int(volume_str)
                    
                    result.append({
                        "date": date_time,
                        "open": price,
                        "high": price,
                        "low": price,
                        "close": price,
                        "volume": volume,
                        "amount": None,  # 腾讯接口不提供成交额
                        "change_percent": None,
                    })
                except (ValueError, IndexError):
                    continue
        
        if result:
            logger.debug(f"[Tencent] 获取 {stock_code} 分钟线 {len(result)} 条")
        
        return result
        
    except Exception as e:
        logger.warning(f"[Tencent] 获取 {stock_code} 分钟线失败：{e}")
        return None


def get_stock_minute_data_tencent(stock_code: str, days: int = 1) -> Optional[List[Dict[str, Any]]]:
    """
    获取腾讯财经分钟线数据（兼容接口）
    
    Args:
        stock_code: 股票代码
        days: 获取天数（当前只支持 1 天）
        
    Returns:
        分钟线数据列表（正序排列）
    """
    # 只支持 A 股
    if not stock_code.startswith(('sh', 'sz')):
        return None
    
    data = parse_tencent_minute_data(stock_code)
    
    if not data:
        return None
    
    # 按时间排序确保正序
    sorted_data = sorted(data, key=lambda x: x['date'])
    
    return sorted_data
