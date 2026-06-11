# -*- coding: utf-8 -*-
"""
Centralized daily full-sync job execution (8:30 / 20:30 / Startup Catch-up)
"""

import logging
from datetime import datetime, date
from typing import Dict, Any

logger = logging.getLogger(__name__)


def run_daily_market_cache_refresh() -> Dict[str, Any]:
    """Run the full daily market cache and portfolio sync workflow.
    
    This includes:
    - Portfolio position prices refresh
    - VIX (CN/US) and Bond (CN/US 10Y) daily data fetch
    - Sector ETF daily data refresh
    - Watchlist stock & fund signal refresh
    - Market dashboard cache rebuild (trend, risk, radar, etc.)
    """
    import akshare as ak
    import yfinance as yf

    from src.services.portfolio_service import PortfolioService
    from src.storage import get_db, StockDaily
    from src.services.market_cache_service import (
        MARKET_CACHE_BUILDERS,
        refresh_market_cache,
        refresh_trend_realtime_quotes,
    )
    from src.services.sector_etf_service import refresh_sector_etf_daily_data
    from src.services.watchlist_signal_service import WatchlistSignalService

    today = date.today()
    summary: Dict[str, Any] = {"status": "success", "errors": []}

    # 1. Portfolio Prices & FX
    try:
        svc = PortfolioService()
        result = svc.refresh_all_prices(refresh_fx=True)
        summary["portfolio"] = result
        logger.info("Portfolio price refresh: %s", result)
    except Exception as exc:
        logger.warning("Portfolio price refresh failed: %s", exc)
        summary["errors"].append(f"portfolio: {exc}")

    # 2. Market Risk Indices (VIX, Bond)
    try:
        try:
            df = ak.index_option_300etf_qvix()
            if not df.empty:
                with get_db().get_session() as s:
                    s.query(StockDaily).filter_by(code="cn_vix", date=today).delete()
                    s.add(StockDaily(code="cn_vix", date=today, close=float(df.iloc[-1]["qvix"]), data_source="akshare", updated_at=datetime.now()))
                    s.commit()
        except Exception as exc:
            logger.warning("cn_vix failed: %s", exc)
            
        try:
            vix = yf.Ticker("^VIX")
            hist = vix.history(period="2d")
            if not hist.empty:
                with get_db().get_session() as s:
                    s.query(StockDaily).filter_by(code="us_vix", date=today).delete()
                    s.add(StockDaily(code="us_vix", date=today, close=float(hist["Close"].iloc[-1]), data_source="yfinance", updated_at=datetime.now()))
                    s.commit()
        except Exception as exc:
            logger.warning("us_vix failed: %s", exc)
            
        try:
            df = ak.bond_zh_us_rate()
            if not df.empty:
                for i in range(len(df) - 1, max(0, len(df) - 10), -1):
                    row = df.iloc[i]
                    us_val = row.get("美国国债收益率10年")
                    cn_val = row.get("中国国债收益率10年")
                    if str(us_val) != "nan" and us_val is not None and str(cn_val) != "nan" and cn_val is not None:
                        with get_db().get_session() as s:
                            s.query(StockDaily).filter_by(code="bond_us_10y", date=today).delete()
                            s.query(StockDaily).filter_by(code="bond_cn_10y", date=today).delete()
                            s.add(StockDaily(code="bond_cn_10y", date=today, close=float(cn_val), data_source="akshare", updated_at=datetime.now()))
                            s.add(StockDaily(code="bond_us_10y", date=today, close=float(us_val), data_source="akshare", updated_at=datetime.now()))
                            s.commit()
                        break
        except Exception as exc:
            logger.warning("Bond indices failed: %s", exc)
            
    except Exception as exc:
        logger.warning("Market risk indices refresh failed: %s", exc)
        summary["errors"].append(f"risk_indices: {exc}")

    # 3. Sector ETF
    try:
        sector_result = refresh_sector_etf_daily_data()
        summary["sector_etf"] = sector_result
        logger.info("Sector ETF refresh: refreshed=%d, failed=%d", sector_result.get("refreshed", 0), sector_result.get("failed", 0))
    except Exception as exc:
        logger.warning("Sector ETF refresh failed: %s", exc)
        summary["errors"].append(f"sector_etf: {exc}")

    # 4. Watchlist Signals (Stocks)
    try:
        signal_result = WatchlistSignalService().refresh_enabled_stocks()
        summary["watchlist_stocks"] = signal_result
        logger.info("Watchlist signal refresh: success=%d, failed=%d", signal_result.get("success", 0), signal_result.get("failed", 0))
    except Exception as exc:
        logger.warning("Watchlist stock signal refresh failed: %s", exc)
        summary["errors"].append(f"watchlist_stocks: {exc}")

    # 5. Watchlist Signals (Funds)
    try:
        fund_result = WatchlistSignalService().refresh_enabled_funds()
        summary["watchlist_funds"] = fund_result
        logger.info("Watchlist fund signal refresh: success=%d, failed=%d", fund_result.get("success", 0), fund_result.get("failed", 0))
    except Exception as exc:
        logger.warning("Watchlist fund signal refresh failed: %s", exc)
        summary["errors"].append(f"watchlist_funds: {exc}")

    # 6. Market Dashboard Cache (Risk, Trend, Radar, etc.)
    for cache_key in MARKET_CACHE_BUILDERS:
        try:
            if cache_key == "trend":
                refresh_trend_realtime_quotes()
            else:
                refresh_market_cache(cache_key)
            logger.info("Market cache refreshed: %s", cache_key)
        except Exception as exc:
            logger.error("Market cache refresh failed: %s, key=%s", exc, cache_key)
            summary["errors"].append(f"cache_{cache_key}: {exc}")

    return summary