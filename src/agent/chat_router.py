# -*- coding: utf-8 -*-
"""Rule-based profile router for the Web AI chat entrypoint."""

from __future__ import annotations

from typing import Any, Mapping


AUTO_CHAT_PROFILE_ID = "stock_chat_auto"
DEFAULT_QUICK_CHAT_PROFILE_ID = "stock_chat_quick"


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def select_chat_profile_id(message: str, context: Mapping[str, Any] | None = None) -> str:
    """Select a concrete Agent profile for chat using fast deterministic rules."""
    text = str(message or "").strip().lower()
    asset_type = str((context or {}).get("asset_type") or "").strip().lower()

    if asset_type and asset_type != "stock":
        return DEFAULT_QUICK_CHAT_PROFILE_ID

    specialist_keywords = (
        "专家", "专项", "策略专项", "multi-agent", "多agent", "多 agent",
        "龙头", "缠论", "波浪", "箱体", "金叉", "放量突破", "缩量回踩",
    )
    if _contains_any(text, specialist_keywords):
        return "stock_specialist"

    deep_keywords = (
        "深度", "完整", "全面", "详细", "系统分析", "全方位", "报告", "研报",
        "完整分析", "深度分析", "全面分析",
    )
    risk_keywords = (
        "风险", "暴雷", "减持", "监管", "处罚", "预亏", "亏损", "解禁", "退市",
    )
    if _contains_any(text, deep_keywords) or _contains_any(text, risk_keywords):
        return "stock_full"

    return DEFAULT_QUICK_CHAT_PROFILE_ID


def resolve_chat_profile_id(requested_profile_id: str | None, message: str, context: Mapping[str, Any] | None = None) -> str | None:
    """Resolve auto profile id into the concrete runtime profile id."""
    requested = str(requested_profile_id or "").strip()
    if requested and requested != AUTO_CHAT_PROFILE_ID:
        return requested
    if requested == AUTO_CHAT_PROFILE_ID:
        return select_chat_profile_id(message, context)
    return requested_profile_id
