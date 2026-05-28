# -*- coding: utf-8 -*-
"""
===================================
市场风险指标服务
===================================

参考：/workspace/Code_01.py
"""

import akshare as ak
from datetime import datetime
from typing import Dict, Any
import logging
import signal

logger = logging.getLogger(__name__)


def _fetch_with_timeout(func, timeout=10, default=None):
    """带超时的数据获取"""
    def handler(signum, frame):
        raise TimeoutError("Data fetch timeout")
    
    old_handler = signal.signal(signal.SIGALRM, handler)
    signal.alarm(timeout)
    
    try:
        result = func()
        signal.alarm(0)
        return result
    except (TimeoutError, Exception) as e:
        signal.alarm(0)
        logger.warning(f"获取数据超时或失败：{e}")
        return default if default is not None else {"error": "timeout"}
    finally:
        signal.signal(signal.SIGALRM, old_handler)


def _dollar_index() -> Dict[str, Any]:
    """
    美元指数：用美元对人民币汇率代表
    
    数据源：currency_boc_safe (中国银行外汇牌价)
    """
    def _fetch():
        df = ak.currency_boc_safe()
        latest = df.iloc[-1]
        
        # 获取美元汇率（中行汇率是 100 外币兑人民币）
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
        
        return {
            "value": round(usd_cny, 4),
            "status": status,
            "badge": badge,
            "description": description
        }
    
    return _fetch_with_timeout(_fetch, timeout=10, default={
        "status": "获取失败",
        "badge": "default",
        "description": "请稍后刷新"
    })


def _bond_spread() -> Dict[str, Any]:
    """
    债市信号：中美 10 年期国债收益率利差
    
    数据源：bond_zh_us_rate
    """
    def _fetch():
        df = ak.bond_zh_us_rate()
        latest = df.iloc[-1]
        
        us_10y = float(latest['美国国债收益率 10 年'])
        cn_10y = float(latest['中国国债收益率 10 年'])
        spread = us_10y - cn_10y
        
        # 根据利差判断
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
        
        return {
            "us_10y": round(us_10y, 2),
            "cn_10y": round(cn_10y, 2),
            "spread": round(spread, 2),
            "status": status,
            "badge": badge,
            "description": description
        }
    
    return _fetch_with_timeout(_fetch, timeout=10, default={
        "status": "获取失败",
        "badge": "default",
        "description": "请稍后刷新"
    })


def _stock_market() -> Dict[str, Any]:
    """
    股市：用美元汇率预判反映市场情绪
    
    注：A 股实时接口不稳定，暂用汇率替代
    """
    # 简化：暂无合适数据源
    return {
        "status": "数据维护中",
        "badge": "default",
        "description": "A 股数据接口维护中"
    }


def _vix_index() -> Dict[str, Any]:
    """
    VIX 恐慌指数
    
    注：index_vix 接口已失效，后续寻找替代数据源
    """
    return {
        "status": "暂无数据",
        "badge": "default",
        "description": "VIX 数据源接口暂不可用"
    }


def calculate_market_risk() -> Dict[str, Any]:
    """
    计算综合市场风险指标
    """
    stock = _stock_market()
    bond = _bond_spread()
    dollar = _dollar_index()
    vix = _vix_index()
    
    score = 0
    if stock.get("badge") in ["warning", "danger"]: score += 1
    if bond.get("badge") in ["warning", "danger"]: score += 1
    if dollar.get("badge") in ["warning", "danger"]: score += 1
    if vix.get("badge") in ["warning", "danger"]: score += 1
    
    if score <= 1:
        temperature = "温和"
        badge = "success"
        advice = "市场情绪平稳，适合按计划执行配置。"
    elif score == 2:
        temperature = "中性偏热"
        badge = "warning"
        advice = "建议维持现有仓位，暂缓激进加仓。"
    else:
        temperature = "警报"
        badge = "danger"
        advice = "多项指标亮红灯，优先防守，保留现金。"
    
    llm_prompt = f"""
【NestCheck 市场风险快照】
- 日期：{datetime.now().strftime("%Y-%m-%d")}
- 股市：{stock.get("status", "N/A")}（{stock.get("description", "N/A")}）
- 债市：{bond.get("status", "N/A")}（{bond.get("description", "N/A")}）
- 美元：{dollar.get("status", "N/A")}（{dollar.get("description", "N/A")}）
- VIX: {vix.get("status", "N/A")}
- 综合体温：{temperature}

请以 NestCheck（稳巢）的理性口吻，写一段 100 字以内的市场点评。
"""
    
    return {
        "snapshot_date": datetime.now().strftime("%Y-%m-%d"),
        "stock_valuation": stock,
        "bond_signal": bond,
        "dollar_strength": dollar,
        "vix": vix,
        "temperature": temperature,
        "badge": badge,
        "score": score,
        "advice": advice,
        "llm_prompt": llm_prompt
    }
