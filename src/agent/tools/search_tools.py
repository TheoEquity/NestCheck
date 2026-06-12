# -*- coding: utf-8 -*-
"""
Search tools — wraps SearchService methods as agent-callable tools.

Tools:
- search_stock_news: search latest stock news
- search_comprehensive_intel: multi-dimensional intelligence search
"""

import logging
import hashlib
import html
import ipaddress
import json
import re
import socket
from html.parser import HTMLParser
from datetime import datetime
from urllib.parse import urlparse
from typing import Any, Dict, Optional

from src.agent.tools.registry import ToolParameter, ToolDefinition
from src.agent.runtime_context import get_agent_topic_key, is_agent_chat_mode

logger = logging.getLogger(__name__)

_FETCH_TIMEOUT_SECONDS = 12
_MAX_FETCH_BYTES = 1_500_000
_MAX_EXTRACTED_CHARS = 6000
_ALLOWED_FETCH_SCHEMES = {"http", "https"}


class _ReadableTextParser(HTMLParser):
    """Small HTML text extractor for evidence snippets."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe"}
    _BLOCK_TAGS = {"p", "div", "section", "article", "br", "li", "tr", "h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []
        self.title = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self.lasttag == "title" and data.strip():
            self.title += data.strip()
        if data.strip():
            self._parts.append(data)

    def text(self) -> str:
        raw = html.unescape(" ".join(self._parts))
        raw = re.sub(r"[\t\r\f\v]+", " ", raw)
        raw = re.sub(r" *\n *", "\n", raw)
        raw = re.sub(r"[ ]{2,}", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _get_db():
    """Lazy import for DatabaseManager."""
    from src.storage import get_db
    return get_db()


def _get_search_service():
    """Return shared SearchService singleton."""
    from src.search_service import get_search_service
    return get_search_service()


def _safe_fetch_url(url: str) -> Optional[str]:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme.lower() not in _ALLOWED_FETCH_SCHEMES or not parsed.netloc:
        return None
    hostname = (parsed.hostname or "").lower()
    if not hostname or hostname == "localhost":
        return None

    def _is_blocked_addr(addr: ipaddress._BaseAddress) -> bool:
        return any((
            addr.is_loopback,
            addr.is_private,
            addr.is_link_local,
            addr.is_reserved,
            addr.is_multicast,
            addr.is_unspecified,
        ))

    try:
        addr = ipaddress.ip_address(hostname)
        if _is_blocked_addr(addr):
            return None
    except ValueError:
        try:
            infos = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except OSError:
            return None
        for info in infos:
            sockaddr = info[4]
            if not sockaddr:
                return None
            try:
                if _is_blocked_addr(ipaddress.ip_address(sockaddr[0])):
                    return None
            except ValueError:
                return None
    return parsed.geturl()


def _fetch_page_text(url: str, *, max_chars: int = _MAX_EXTRACTED_CHARS) -> dict:
    safe_url = _safe_fetch_url(url)
    if safe_url is None:
        return {"success": False, "error": "URL is not fetchable", "url": url}

    try:
        import requests

        response = requests.get(
            safe_url,
            headers={
                "User-Agent": "NestCheckAgent/1.0 (+https://github.com/TheoEquity/NestCheck)",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
            },
            timeout=_FETCH_TIMEOUT_SECONDS,
            stream=True,
            allow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            return {"success": False, "error": "Redirect responses are not fetchable", "url": safe_url}
        response.raise_for_status()
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=65536, decode_unicode=False):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= _MAX_FETCH_BYTES:
                break
        encoding = response.encoding or response.apparent_encoding or "utf-8"
        body = b"".join(chunks).decode(encoding, errors="replace")
        parser = _ReadableTextParser()
        parser.feed(body)
        text = parser.text()
        return {
            "success": True,
            "url": response.url,
            "status_code": response.status_code,
            "title": parser.title[:160],
            "text": text[:max_chars],
            "text_length": len(text),
            "truncated": len(text) > max_chars or total >= _MAX_FETCH_BYTES,
            "fetched_at": datetime.now().isoformat(),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "url": safe_url}


def _canonical_search_code(stock_code: str) -> str:
    from data_provider.base import canonical_stock_code, normalize_stock_code

    return canonical_stock_code(normalize_stock_code(str(stock_code or "").strip()))


def _agent_cache_key(data_type: str, symbol: str, params: Dict[str, Any]) -> str:
    payload = json.dumps(params or {}, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    topic_key = get_agent_topic_key() or "adhoc"
    return f"{topic_key}:{data_type}:{symbol}:{digest}"


def _persist_agent_search_cache(
    *,
    stock_code: str,
    data_type: str,
    payload: Any,
    params: Optional[Dict[str, Any]] = None,
    provider: Optional[str] = None,
    symbol_override: Optional[str] = None,
) -> None:
    code = symbol_override or _canonical_search_code(stock_code)
    try:
        _get_db().save_agent_data_cache(
            cache_key=_agent_cache_key(data_type, code, params or {}),
            topic_key=get_agent_topic_key(),
            data_type=data_type,
            symbol=code,
            params=params or {},
            payload=payload,
            source=provider,
            as_of=datetime.now().isoformat(),
            ttl_seconds=86400,
        )
    except Exception as exc:
        logger.warning("Agent search cache save failed for %s/%s: %s", data_type, code, exc)


def _get_agent_search_cache(
    *,
    stock_code: str,
    data_type: str,
    params: Optional[Dict[str, Any]] = None,
    symbol_override: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    code = symbol_override or _canonical_search_code(stock_code)
    try:
        return _get_db().get_agent_data_cache(
            _agent_cache_key(data_type, code, params or {})
        )
    except Exception as exc:
        logger.warning("Agent search cache read failed for %s/%s: %s", data_type, code, exc)
        return None


def _persist_news_response(
    *,
    stock_code: str,
    stock_name: str,
    dimension: str,
    response,
) -> None:
    """Best-effort short-lived cache for Agent search tools."""
    if not response or not getattr(response, "success", False) or not getattr(response, "results", None):
        return

    if not is_agent_chat_mode():
        return

    _persist_agent_search_cache(
        stock_code=stock_code,
        data_type=f"news_{dimension}",
        provider=getattr(response, "provider", None),
        params={"stock_code": stock_code, "stock_name": stock_name, "dimension": dimension},
        payload={
            "query": getattr(response, "query", ""),
            "provider": getattr(response, "provider", None),
            "results": [
                {
                    "title": item.title,
                    "snippet": item.snippet,
                    "url": item.url,
                    "source": item.source,
                    "published_date": item.published_date,
                }
                for item in getattr(response, "results", [])
            ],
        },
    )


def _handle_search_stock_news(stock_code: str, stock_name: str) -> dict:
    """Search latest news for a stock."""
    cache_params = {"stock_code": stock_code, "stock_name": stock_name, "dimension": "latest_news"}
    if is_agent_chat_mode():
        cached = _get_agent_search_cache(
            stock_code=stock_code,
            data_type="news_latest_news",
            params=cache_params,
        )
        if cached is not None:
            payload = cached.get("payload") or {}
            results = list(payload.get("results") or [])
            return {
                "query": payload.get("query", ""),
                "provider": payload.get("provider") or cached.get("source") or "agent_data_cache",
                "success": True,
                "cache_hit": True,
                "results_count": len(results),
                "results": results,
            }

    service = _get_search_service()

    response = service.search_stock_news(stock_code, stock_name, max_results=5)

    if not response.success:
        return {
            "query": response.query,
            "success": False,
            "error": response.error_message,
        }

    _persist_news_response(
        stock_code=stock_code,
        stock_name=stock_name,
        dimension="latest_news",
        response=response,
    )

    return {
        "query": response.query,
        "provider": response.provider,
        "success": True,
        "results_count": len(response.results),
        "results": [
            {
                "title": r.title,
                "snippet": r.snippet,
                "url": r.url,
                "source": r.source,
                "published_date": r.published_date,
            }
            for r in response.results
        ],
    }


search_stock_news_tool = ToolDefinition(
    name="search_stock_news",
    description="Search for the latest news articles about a specific stock. "
                "Requires both stock_code and stock_name for accurate search. "
                "Returns news titles, snippets, sources, and URLs.",
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="Stock code, e.g., '600519'",
        ),
        ToolParameter(
            name="stock_name",
            type="string",
            description="Stock name in Chinese, e.g., '贵州茅台'",
        ),
    ],
    handler=_handle_search_stock_news,
    category="search",
)


# ============================================================
# fetch_stock_news_pages
# ============================================================

def _handle_fetch_stock_news_pages(stock_code: str, stock_name: str, max_pages: int = 3) -> dict:
    """Search and fetch readable page text for stock news evidence."""
    try:
        effective_pages = max(1, min(int(max_pages), 5))
    except (TypeError, ValueError):
        effective_pages = 3

    cache_params = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "max_pages": effective_pages,
    }
    if is_agent_chat_mode():
        cached = _get_agent_search_cache(
            stock_code=stock_code,
            data_type="news_pages",
            params=cache_params,
        )
        if cached is not None:
            payload = cached.get("payload") or {}
            return {**payload, "cache_hit": True}

    news = _handle_search_stock_news(stock_code, stock_name)
    if news.get("success") is not True:
        return news

    pages = []
    for item in list(news.get("results") or [])[:effective_pages]:
        url = item.get("url")
        if not url:
            continue
        fetched = _fetch_page_text(url)
        pages.append({
            "source_title": item.get("title"),
            "source": item.get("source"),
            "published_date": item.get("published_date"),
            "url": url,
            **fetched,
        })

    payload = {
        "success": True,
        "query": news.get("query", ""),
        "provider": news.get("provider"),
        "pages_count": len(pages),
        "pages": pages,
    }
    if is_agent_chat_mode():
        _persist_agent_search_cache(
            stock_code=stock_code,
            data_type="news_pages",
            params=cache_params,
            provider=str(news.get("provider") or "web_pages"),
            payload=payload,
        )
    return payload


fetch_stock_news_pages_tool = ToolDefinition(
    name="fetch_stock_news_pages",
    description="Search latest stock news and fetch readable page text as evidence. "
                "Use this when the user asks for news-driven reasons, catalysts, or recent events.",
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="Stock code, e.g., '600519', 'hk00700', or 'AAPL'.",
        ),
        ToolParameter(
            name="stock_name",
            type="string",
            description="Stock name, e.g., '贵州茅台' or 'Apple'.",
        ),
        ToolParameter(
            name="max_pages",
            type="integer",
            description="Maximum pages to fetch, 1 to 5. Default is 3.",
            required=False,
            default=3,
        ),
    ],
    handler=_handle_fetch_stock_news_pages,
    category="search",
)


# ============================================================
# extract_page_content
# ============================================================

def _handle_extract_page_content(url: str, max_chars: int = 6000) -> dict:
    """Fetch one public page and extract readable text."""
    try:
        effective_chars = max(500, min(int(max_chars), 12000))
    except (TypeError, ValueError):
        effective_chars = 6000
    payload = _fetch_page_text(url, max_chars=effective_chars)
    if payload.get("success") and is_agent_chat_mode():
        _persist_agent_search_cache(
            stock_code="page",
            data_type="page_content",
            params={"url": url, "max_chars": effective_chars},
            provider=urlparse(payload.get("url") or url).netloc,
            payload=payload,
            symbol_override="page",
        )
    return payload


extract_page_content_tool = ToolDefinition(
    name="extract_page_content",
    description="Fetch a specific public web page and extract readable text. "
                "Use this for user-provided news, announcement, filing, or research URLs.",
    parameters=[
        ToolParameter(
            name="url",
            type="string",
            description="Public http(s) page URL to fetch.",
        ),
        ToolParameter(
            name="max_chars",
            type="integer",
            description="Maximum extracted characters, 500 to 12000. Default is 6000.",
            required=False,
            default=6000,
        ),
    ],
    handler=_handle_extract_page_content,
    category="search",
)


# ============================================================
# search_comprehensive_intel
# ============================================================

def _handle_search_comprehensive_intel(stock_code: str, stock_name: str) -> dict:
    """Multi-dimensional intelligence search."""
    service = _get_search_service()

    intel_results = service.search_comprehensive_intel(
        stock_code=stock_code,
        stock_name=stock_name,
        max_searches=6,
    )

    if not intel_results:
        return {"error": "Comprehensive intel search returned no results"}

    # Format into readable report
    report = service.format_intel_report(intel_results, stock_name)

    # Also return structured data
    dimensions = {}
    for dim_name, response in intel_results.items():
        if response and response.success:
            _persist_news_response(
                stock_code=stock_code,
                stock_name=stock_name,
                dimension=dim_name,
                response=response,
            )
            dimensions[dim_name] = {
                "query": response.query,
                "results_count": len(response.results),
                "results": [
                    {
                        "title": r.title,
                        "snippet": r.snippet,
                        "source": r.source,
                    }
                    for r in response.results[:3]  # limit to 3 per dimension to save tokens
                ],
            }

    return {
        "report": report,
        "dimensions": dimensions,
    }


search_comprehensive_intel_tool = ToolDefinition(
    name="search_comprehensive_intel",
    description="Multi-dimensional intelligence search: latest news, market analysis, "
                "risk checking, earnings outlook, and industry trends for a stock. "
                "Returns a formatted report and structured results.",
    parameters=[
        ToolParameter(
            name="stock_code",
            type="string",
            description="Stock code, e.g., '600519'",
        ),
        ToolParameter(
            name="stock_name",
            type="string",
            description="Stock name in Chinese, e.g., '贵州茅台'",
        ),
    ],
    handler=_handle_search_comprehensive_intel,
    category="search",
)


ALL_SEARCH_TOOLS = [
    search_stock_news_tool,
    fetch_stock_news_pages_tool,
    extract_page_content_tool,
    search_comprehensive_intel_tool,
]
