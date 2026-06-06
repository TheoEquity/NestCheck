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
_FUND_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_US_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{1,5}(?:[.-][A-Z])?)(?![A-Z0-9])")

_INDEX_NAME_MAP = {
    "中证A500": "sh000510",
    "A500": "sh000510",
    "沪深300": "sh000300",
    "中证500": "sh000905",
    "上证指数": "sh000001",
    "上证": "sh000001",
    "深证成指": "sz399001",
    "深证": "sz399001",
    "创业板指": "sz399006",
    "创业板": "sz399006",
}


def _normalize_code(message: str, *, allow_us_without_hint: bool = False) -> Optional[tuple[str, str]]:
    text = message or ""
    lower = text.lower()

    for name, code in _INDEX_NAME_MAP.items():
        if name in text:
            return "cn", code

    fund_hint = "fund" in lower or any(word in text for word in ("基金", "ETF", "etf", "货基", "固收"))
    if fund_hint:
        fund = _FUND_RE.search(text)
        if fund:
            return "cn", fund.group(1)

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
    if any(word in text for word in (
        "指数", "大盘", "沪深300", "中证500", "中证A500", "A500", "上证", "深证", "创业板",
    )):
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
    lower_source = source_text.lower()
    if "bond" in lower_source or "债券" in source_text or "债市" in source_text:
        topic_key = "cn:bond:overview"
        digest = hashlib.sha1(topic_key.encode("utf-8")).hexdigest()[:16]
        return ChatTopic(
            topic_key=topic_key,
            session_id=f"topic:{digest}",
            market="cn",
            asset_type="bond",
            code="overview",
            title="中国债市",
        )
    if "market" in lower_source or any(word in source_text for word in ("市场", "大盘")):
        market = "cn"
        if "hk" in lower_source or "港股" in source_text:
            market = "hk"
        elif "us" in lower_source or "美股" in source_text:
            market = "us"
        topic_key = f"{market}:market:overview"
        digest = hashlib.sha1(topic_key.encode("utf-8")).hexdigest()[:16]
        return ChatTopic(
            topic_key=topic_key,
            session_id=f"topic:{digest}",
            market=market,
            asset_type="market",
            code="overview",
            title=f"{market.upper()} market overview",
        )
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
