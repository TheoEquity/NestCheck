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
    美元指数：用美元对人民币汇率代表
    
    数据源：currency_boc_safe (中国银行外汇牌价)
    """
    # 先查缓存
    cache = _load_cache("dollar")
    if cache:
        return cache
    
    # 获取新数据
    try:
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
    债市信号：中美 10 年期国债收益率利差
    
    数据源：bond_zh_us_rate
    """
    # 先查缓存
    cache = _load_cache("bond")
    if cache:
        return cache
    
    # 获取新数据
    try:
        df = ak.bond_zh_us_rate()
        latest = df.iloc[-1]
        
        # 直接使用确切列名
        us_10y = float(latest['美国国债收益率10年'])
        cn_10y = float(latest['中国国债收益率10年'])
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
        
        result = {
            "us_10y": round(us_10y, 2),
            "cn_10y": round(cn_10y, 2),
            "spread": round(spread, 2),
            "status": status,
            "badge": badge,
            "description": description,
            "date": str(latest.get('日期', datetime.now().strftime("%Y-%m-%d")))
        }
        _save_cache("bond", result)
        return result
    
    except Exception as e:
        logger.warning(f"获取债市数据失败：{e}")
        return {
            "status": "获取失败",
            "badge": "default",
            "description": "请稍后刷新"
        }


def _stock_market() -> Dict[str, Any]:
    """
    股市：暂用占位数据
    
    注：A 股实时接口不稳定，后续寻找替代数据源
    """
    cache = _load_cache("stock")
    if cache:
        return cache
    
    # 占位数据
    result = {
        "status": "数据维护中",
        "badge": "default",
        "description": "A 股数据接口维护中",
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    _save_cache("stock", result)
    return result


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


def clear_cache():
    """清空所有缓存"""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.glob("*.json"):
            f.unlink()
        logger.info("缓存已清空")
