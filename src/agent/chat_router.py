# -*- coding: utf-8 -*-
"""Rule-based profile router for the Web AI chat entrypoint."""

from __future__ import annotations

from typing import Any, Mapping


AUTO_CHAT_PROFILE_ID = "stock_chat_auto"
DEFAULT_QUICK_CHAT_PROFILE_ID = "stock_chat_quick"
TECHNICAL_PROFILE_ID = "stock_quick"
INTEL_PROFILE_ID = "stock_intel"
RISK_PROFILE_ID = "stock_risk"


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def select_chat_profile_id(message: str, context: Mapping[str, Any] | None = None) -> str:
    """Select a concrete Agent profile for chat using fast deterministic rules."""
    text = str(message or "").strip().lower()
    asset_type = str((context or {}).get("asset_type") or "").strip().lower()

    if asset_type and asset_type != "stock":
        return DEFAULT_QUICK_CHAT_PROFILE_ID

    risk_keywords = (
        "风险", "利空", "暴雷", "减持", "监管", "处罚", "预亏", "亏损", "解禁", "退市",
    )
    if _contains_any(text, risk_keywords):
        return RISK_PROFILE_ID

    intel_keywords = (
        "新闻", "消息", "资讯", "公告", "舆情", "事件", "传闻", "题材", "催化",
    )
    if _contains_any(text, intel_keywords):
        return INTEL_PROFILE_ID

    technical_keywords = (
        "技术面", "走势", "趋势", "形态", "k线", "k 线", "均线", "支撑", "压力",
        "量能", "成交量", "macd", "rsi", "kdj", "金叉", "死叉", "突破", "回踩",
    )
    if _contains_any(text, technical_keywords):
        return TECHNICAL_PROFILE_ID

    return DEFAULT_QUICK_CHAT_PROFILE_ID


def resolve_chat_profile_id(requested_profile_id: str | None, message: str, context: Mapping[str, Any] | None = None) -> str | None:
    """Resolve auto profile id into the concrete runtime profile id."""
    requested = str(requested_profile_id or "").strip()
    if requested and requested != AUTO_CHAT_PROFILE_ID:
        return requested
    if requested == AUTO_CHAT_PROFILE_ID:
        return select_chat_profile_id(message, context)
    return requested_profile_id
