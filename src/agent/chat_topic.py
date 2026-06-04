"""Topic normalization for AI chat sessions."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChatTopic:
    topic_key: str
    session_id: str
    market: str
    asset_type: str
    code: str
    title: str


_HK_RE = re.compile(r"(?<![A-Z0-9])(?:HK)?(0\d{4}|[1-9]\d{4})(?!\d)", re.IGNORECASE)
_CN_RE = re.compile(r"(?<!\d)(?:SH|SZ)?([036]\d{5}|[159]\d{5})(?!\d)", re.IGNORECASE)
_US_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{1,5}(?:[.-][A-Z])?)(?![A-Z0-9])")


def _normalize_code(message: str, *, allow_us_without_hint: bool = False) -> Optional[tuple[str, str]]:
    text = message or ""
    lower = text.lower()

    cn = _CN_RE.search(lower)
    if cn:
        return "cn", cn.group(1)

    hk_hint = "港股" in text or "hk" in lower
    if hk_hint:
        hk = _HK_RE.search(text)
        if hk:
            return "hk", hk.group(1).zfill(5)

    us_hint = allow_us_without_hint or "美股" in text or "us" in lower or "nasdaq" in lower or "nyse" in lower
    if us_hint:
        for match in _US_RE.finditer(text.upper()):
            token = match.group(1)
            if token in {"A", "AI", "ETF", "US", "HK"}:
                continue
            return "us", token

    return None


def _normalize_asset_type(message: str, code: str) -> str:
    text = message or ""
    lower = text.lower()
    if "index" in lower:
        return "index"
    if "fund" in lower:
        return "fund"
    if "bond" in lower:
        return "bond"
    if "stock" in lower:
        return "stock"
    if any(word in text for word in ("基金", "ETF", "etf", "指数基金", "货基", "固收")):
        return "fund"
    if any(word in text for word in ("指数", "大盘", "沪深300", "上证", "创业板")):
        return "index"
    if code.startswith(("1", "5")) and len(code) == 6:
        return "fund"
    return "stock"


def resolve_chat_topic(
    message: str,
    *,
    stock_code: Optional[str] = None,
    stock_name: Optional[str] = None,
    allow_us_without_hint: bool = False,
) -> Optional[ChatTopic]:
    """Resolve a stable topic for stock/fund/index chat messages."""
    source_text = " ".join(part for part in (stock_code, stock_name, message) if part)
    resolved = _normalize_code(source_text, allow_us_without_hint=allow_us_without_hint)
    if resolved is None:
        return None
    market, code = resolved
    asset_type = _normalize_asset_type(source_text, code)
    topic_key = f"{market}:{asset_type}:{code.upper()}"
    digest = hashlib.sha1(topic_key.encode("utf-8")).hexdigest()[:16]
    session_id = f"topic:{digest}"
    title = f"{market.upper()} {asset_type} {code.upper()}"
    return ChatTopic(
        topic_key=topic_key,
        session_id=session_id,
        market=market,
        asset_type=asset_type,
        code=code.upper(),
        title=title,
    )
