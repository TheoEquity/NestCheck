# -*- coding: utf-8 -*-
"""
===================================
市场实时快照服务 (Market Snapshot)
===================================
负责获取 12 个核心指数的最新价格及涨跌幅。

策略：
1. 优先读取 5 分钟缓存（/tmp/nestcheck_market_snapshot）。
2. 缓存过期或被强制刷新时，从网络拉取。
3. 网络失败时，降级读取 SQLite 昨日收盘价。
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
import yfinance as yf
import akshare as ak
import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/tmp/nestcheck_market_snapshot")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_EXPIRY_MINUTES = 5
CACHE_FILE = CACHE_DIR / "snapshot.json"

MARKET_INDICES = [
    {"key": "a500", "label": "A500", "code": "sh000510", "source": "akshare"},
    {"key": "hs300", "label": "沪深300", "code": "sh000300", "source": "akshare"},
    {"key": "zz500", "label": "中证500", "code": "sh000905", "source": "akshare"},
    {"key": "sh", "label": "上证指数", "code": "sh000001", "source": "akshare"},
    {"key": "sz", "label": "深圳成指", "code": "sz399001", "source": "akshare"},
    {"key": "cyb", "label": "创业板指", "code": "sz399006", "source": "akshare"},
    {"key": "dji", "label": "道琼斯", "code": "^DJI", "source": "yfinance"},
    {"key": "ixic", "label": "纳斯达克", "code": "^IXIC", "source": "yfinance"},
    {"key": "gspc", "label": "标普500", "code": "^GSPC", "source": "yfinance"},
    {"key": "dxy", "label": "美元指数", "code": "DX-Y.NYB", "source": "yfinance"},
    {"key": "usdcny", "label": "美元兑人民币", "code": "USDCNY=X", "source": "yfinance"},
    {"key": "tnx", "label": "10年期美债", "code": "^TNX", "source": "yfinance"},
]

def _load_cache() -> Optional[Dict[str, Any]]:
    try:
        if not CACHE_FILE.exists():
            return None
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cached_at = datetime.fromisoformat(data.get("_cached_at", "1970-01-01"))
        if datetime.now() - cached_at > timedelta(minutes=CACHE_EXPIRY_MINUTES):
            return None
        return data
    except Exception:
        return None

def _save_cache(data: Dict[str, Any]):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({**data, "_cached_at": datetime.now().isoformat()}, f, ensure_ascii=False)
    except Exception:
        pass

def _get_fallback_from_db() -> Dict[str, Any]:
    """降级方案：从数据库读取昨日收盘价"""
    from src.storage import StorageManager
    manager = StorageManager()
    engine = manager._engine
    from sqlalchemy import text
    result = {}
    for item in MARKET_INDICES:
        code = item["code"]
        db_code = code[2:] if code.startswith(("sh", "sz")) else code
        
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    text('SELECT close, pct_chg FROM stock_daily WHERE code = :code ORDER BY date DESC LIMIT 1'),
                    {"code": db_code}
                ).fetchone()
                if row:
                    result[code] = {"close": row[0], "pct_chg": row[1] or 0, "source": "sqlite"}
                else:
                    result[code] = {"close": 0, "pct_chg": 0, "source": "offline"}
        except Exception as e:
            logger.warning(f"Fallback DB query failed for {code}: {e}")
            result[code] = {"close": 0, "pct_chg": 0, "source": "offline"}
    return result

def _fetch_network_snapshot() -> Dict[str, Any]:
    result = {}
    for item in MARKET_INDICES:
        try:
            if item["source"] == "yfinance":
                ticker = yf.Ticker(item["code"])
                hist = ticker.history(period="2d")
                if not hist.empty:
                    close = round(float(hist["Close"].iloc[-1]), 2)
                    pct = 0.0
                    if len(hist) >= 2:
                        prev = hist["Close"].iloc[-2]
                        pct = round((close - prev) / prev * 100, 2)
                    result[item["code"]] = {"close": close, "pct_chg": pct, "source": "yfinance"}
            elif item["source"] == "akshare":
                raw_code = item["code"][2:] if item["code"].startswith(("sh", "sz")) else item["code"]
                try:
                    df = ak.index_zh_a_hist(
                        symbol=raw_code,
                        start_date=(datetime.now() - timedelta(days=5)).strftime("%Y%m%d"),
                        end_date=datetime.now().strftime("%Y%m%d")
                    )
                    if not df.empty:
                        latest = df.iloc[-1]
                        result[item["code"]] = {"close": float(latest.get("收盘")), "pct_chg": float(latest.get("涨跌幅")), "source": "akshare"}
                except Exception as e:
                    logger.warning(f"Snapshot akshare fetch failed for {item['code']}, will fallback to DB")
            time.sleep(0.2)
        except Exception as e:
            logger.warning(f"Snapshot fetch failed for {item['code']}: {e}")
    
    return result

def get_market_snapshot(force_refresh: bool = False) -> Dict[str, Any]:
    if not force_refresh:
        cached = _load_cache()
        if cached:
            return cached

    net_data = _fetch_network_snapshot()
    is_network_good = len(net_data) >= 5
    
    if not is_network_good:
        logger.info("[Snapshot] 网络数据不佳，降级使用数据库")
        net_data = _get_fallback_from_db()

    final_result = {"items": {}, "updated_at": datetime.now().isoformat()}
    for item in MARKET_INDICES:
        code = item["code"]
        if code in net_data:
            final_result["items"][code] = net_data[code]
        else:
            # Per-index fallback: try DB when network fails for this specific index
            db_code = code[2:] if code.startswith(("sh", "sz")) else code
            try:
                from src.storage import StorageManager
                manager = StorageManager()
                engine = manager._engine
                from sqlalchemy import text
                with engine.connect() as conn:
                    row = conn.execute(
                        text('SELECT close, pct_chg FROM stock_daily WHERE code = :code ORDER BY date DESC LIMIT 1'),
                        {"code": db_code}
                    ).fetchone()
                    if row:
                        final_result["items"][code] = {"close": row[0], "pct_chg": row[1] or 0, "source": "sqlite"}
                    else:
                        final_result["items"][code] = {"close": 0, "pct_chg": 0, "source": "offline"}
            except Exception as e:
                logger.warning(f"DB fallback failed for {code}: {e}")
                final_result["items"][code] = {"close": 0, "pct_chg": 0, "source": "offline"}
    
    _save_cache(final_result)
    return final_result
