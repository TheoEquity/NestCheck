# -*- coding: utf-8 -*-
"""
===================================
市场风险指标服务
===================================

职责：
1. 计算股市、债市、汇市的风险指标
2. 生成市场综合体温和配置建议
3. 为 LLM 评论提供数据基础
"""

import akshare as ak
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def _stock_valuation_percentile(symbol: str = "沪深300") -> Dict[str, Any]:
    """
    计算 A 股市场估值分位数
    
    数据源：乐咕乐股 - 指数市盈率
    """
    try:
        df = ak.stock_index_pe_lg(symbol=symbol)
        if df.empty:
            return {"error": "数据为空"}
        
        current_pe = df.iloc[-1]["滚动市盈率"]
        
        hist_5y = df.tail(1250)
        percentile = (hist_5y["滚动市盈率"] < current_pe).mean()
        
        if percentile < 0.3:
            status = "偏低"
            badge = "success"
        elif percentile < 0.7:
            status = "合理"
            badge = "default"
        else:
            status = "偏高"
            badge = "danger"
        
        return {
            "value": round(float(current_pe), 2),
            "percentile": round(float(percentile * 100), 1),
            "status": status,
            "badge": badge,
            "description": f"当前市盈率处于历史 {round(percentile * 100)}% 分位"
        }
    except Exception as e:
        logger.error(f"获取股市估值失败：{e}")
        return {"error": str(e)}


def _bond_market_signal() -> Dict[str, Any]:
    """
    债市信号：10 年 -2 年期国债收益率差
    
    数据源：中美债券收益率
    """
    try:
        df = ak.bond_zh_us_rate()
        latest = df.iloc[-1]
        
        cn_10y = latest["中国10年期国债收益率"]
        cn_2y = latest["中国2年期国债收益率"]
        spread = cn_10y - cn_2y
        
        if spread < 0:
            status = "倒挂"
            badge = "danger"
            description = "收益率曲线倒挂，经济预期偏弱"
        elif spread < 0.3:
            status = "偏平"
            badge = "warning"
            description = "收益率曲线偏平，增长预期谨慎"
        else:
            status = "正常"
            badge = "success"
            description = "利率环境稳定"
        
        return {
            "spread": round(float(spread), 2),
            "cn_10y": round(float(cn_10y), 2),
            "cn_2y": round(float(cn_2y), 2),
            "status": status,
            "badge": badge,
            "description": description
        }
    except Exception as e:
        logger.error(f"获取债市信号失败：{e}")
        return {"error": str(e)}


def _dollar_index() -> Dict[str, Any]:
    """
    美元指数强弱
    
    数据源：外汇实时行情
    """
    try:
        df = ak.forex_spot_em()
        dxy = df[df["代码"] == "DXY"]["最新价"].values[0]
        
        if dxy < 100:
            status = "偏弱"
            badge = "success"
            description = "美元走弱，利好新兴市场资产"
        elif dxy < 105:
            status = "中性"
            badge = "default"
            description = "美元指数中性震荡"
        else:
            status = "偏强"
            badge = "warning"
            description = "留意人民币资产波动"
        
        return {
            "value": round(float(dxy), 2),
            "status": status,
            "badge": badge,
            "description": description
        }
    except Exception as e:
        logger.error(f"获取美元指数失败：{e}")
        return {"error": str(e)}


def _vix_index() -> Dict[str, Any]:
    """
    VIX 恐慌指数
    
    数据源：index_vix
    """
    try:
        df = ak.index_vix()
        df["date"] = pd.to_datetime(df["date"])
        latest = df.iloc[-1]
        
        current = latest["close"]
        hist_5y = df.tail(1250)
        percentile = (hist_5y["close"] < current).mean()
        
        if current < 20:
            status = "温和"
            badge = "success"
        elif current < 30:
            status = "警惕"
            badge = "warning"
        else:
            status = "恐慌"
            badge = "danger"
        
        return {
            "value": round(float(current), 2),
            "percentile": round(float(percentile * 100), 1),
            "status": status,
            "badge": badge
        }
    except Exception as e:
        logger.error(f"获取 VIX 指数失败：{e}")
        return {"error": str(e)}


def calculate_market_risk() -> Dict[str, Any]:
    """
    计算综合市场风险指标
    
    返回：
    {
        "snapshot_date": str,
        "stock_valuation": {...},
        "bond_signal": {...},
        "dollar_strength": {...},
        "vix": {...},
        "temperature": str,
        "badge": str,
        "advice": str,
        "llm_prompt": str
    }
    """
    stock = _stock_valuation_percentile("沪深 300")
    bond = _bond_market_signal()
    dollar = _dollar_index()
    vix = _vix_index()
    
    score = 0
    if stock.get("badge") == "danger": score += 1
    if bond.get("badge") == "danger": score += 1
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
- 股市估值：{stock.get("percentile", "N/A")}% 分位（{stock.get("status", "N/A")}）
- 债市信号：{bond.get("status", "N/A")}（{bond.get("description", "N/A")}）
- 美元指数：{dollar.get("value", "N/A")}（{dollar.get("status", "N/A")}）
- VIX 恐慌：{vix.get("value", "N/A")}（{vix.get("status", "N/A")}）
- 综合体温：{temperature}

请以 NestCheck（稳巢）的理性口吻，写一段 100 字以内的市场点评。
要求：不预测涨跌，重点提示风险管理和资产配置建议。
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
