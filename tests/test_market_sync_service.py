# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src.services import market_sync_service


class _StubStorageManager:
    def __init__(self) -> None:
        self.saved = []

    def save_daily_data(self, df, code, source) -> None:
        self.saved.append((df.copy(), code, source))


class _ForbiddenFetcherManager:
    def get_daily_data(self, code, days=30):
        raise AssertionError(f"unexpected unified fetch for {code}")


class _StubFetcherManager:
    def __init__(self, df: pd.DataFrame, source: str = "yfinance") -> None:
        self.df = df
        self.source = source
        self.calls = []

    def get_daily_data(self, code, days=30):
        self.calls.append((code, days))
        return self.df.copy(), self.source


class MarketSyncServiceTestCase(unittest.TestCase):
    def test_sync_market_data_uses_fred_for_supported_macro_codes(self) -> None:
        saved_manager = _StubStorageManager()
        fred_df = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-06-15").date(),
                    "open": 7.21,
                    "high": 7.21,
                    "low": 7.21,
                    "close": 7.21,
                    "volume": 0,
                    "amount": 0,
                    "pct_chg": 0.1,
                }
            ]
        )
        fred_df.attrs["source"] = "fred"

        with patch.object(
            market_sync_service,
            "MARKET_INDICES",
            [{"code": "USDCNY=X", "source": "fred", "name": "美元兑人民币"}],
        ), patch("src.services.market_sync_service.StorageManager", return_value=saved_manager), patch(
            "src.services.market_sync_service.DataFetcherManager"
        ) as mock_fetcher_manager, patch(
            "src.services.market_sync_service.fetch_supported_daily_dataframe",
            return_value=fred_df,
        ):
            stats = market_sync_service.sync_market_data(days=30)

        mock_fetcher_manager.assert_called_once()
        self.assertEqual(stats["success"], 1)
        self.assertEqual(len(saved_manager.saved), 1)
        self.assertEqual(saved_manager.saved[0][1], "USDCNY=X")
        self.assertEqual(saved_manager.saved[0][2], "fred")

    def test_sync_market_data_uses_fred_for_us_equity_indices(self) -> None:
        saved_manager = _StubStorageManager()
        fred_df = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-06-15").date(),
                    "open": 42850.0,
                    "high": 42850.0,
                    "low": 42850.0,
                    "close": 42850.0,
                    "volume": 0,
                    "amount": 0,
                    "pct_chg": 0.3,
                }
            ]
        )
        fred_df.attrs["source"] = "fred"

        with patch.object(
            market_sync_service,
            "MARKET_INDICES",
            [{"code": "^DJI", "source": "fred", "name": "道琼斯"}],
        ), patch("src.services.market_sync_service.StorageManager", return_value=saved_manager), patch(
            "src.services.market_sync_service.DataFetcherManager"
        ) as mock_fetcher_manager, patch(
            "src.services.market_sync_service.fetch_supported_daily_dataframe",
            return_value=fred_df,
        ):
            stats = market_sync_service.sync_market_data(days=30)

        mock_fetcher_manager.assert_called_once()
        self.assertEqual(stats["success"], 1)
        self.assertEqual(len(saved_manager.saved), 1)
        self.assertEqual(saved_manager.saved[0][1], "^DJI")
        self.assertEqual(saved_manager.saved[0][2], "fred")

    def test_sync_market_data_persists_fallback_source_for_supported_macro_codes(self) -> None:
        saved_manager = _StubStorageManager()
        fallback_df = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-06-15").date(),
                    "open": 42850.0,
                    "high": 42850.0,
                    "low": 42850.0,
                    "close": 42850.0,
                    "volume": 0,
                    "amount": 0,
                    "pct_chg": 0.3,
                }
            ]
        )
        fallback_df.attrs["source"] = "yfinance"

        with patch.object(
            market_sync_service,
            "MARKET_INDICES",
            [{"code": "^DJI", "source": "fred", "name": "道琼斯"}],
        ), patch("src.services.market_sync_service.StorageManager", return_value=saved_manager), patch(
            "src.services.market_sync_service.DataFetcherManager"
        ) as mock_fetcher_manager, patch(
            "src.services.market_sync_service.fetch_supported_daily_dataframe",
            return_value=fallback_df,
        ):
            stats = market_sync_service.sync_market_data(days=30)

        mock_fetcher_manager.assert_called_once()
        self.assertEqual(stats["success"], 1)
        self.assertEqual(len(saved_manager.saved), 1)
        self.assertEqual(saved_manager.saved[0][2], "yfinance")

    def test_sync_market_data_keeps_prefixed_code_for_a_share_indices(self) -> None:
        saved_manager = _StubStorageManager()
        ak_df = pd.DataFrame(
            [
                {
                    "日期": pd.Timestamp("2026-06-15").date(),
                    "开盘": 3500.0,
                    "最高": 3510.0,
                    "最低": 3490.0,
                    "收盘": 3505.0,
                    "成交量": 100,
                    "成交额": 1000,
                    "涨跌幅": 0.2,
                }
            ]
        )

        with patch.object(
            market_sync_service,
            "MARKET_INDICES",
            [{"code": "sh000001", "source": "akshare", "name": "上证指数", "func": "index_zh_a_hist", "period": "daily"}],
        ), patch("src.services.market_sync_service.StorageManager", return_value=saved_manager), patch(
            "src.services.market_sync_service.DataFetcherManager",
            return_value=_ForbiddenFetcherManager(),
        ), patch(
            "src.services.market_sync_service.ak.index_zh_a_hist",
            return_value=ak_df,
        ):
            stats = market_sync_service.sync_market_data(days=30)

        self.assertEqual(stats["success"], 1)
        self.assertEqual(len(saved_manager.saved), 1)
        self.assertEqual(saved_manager.saved[0][1], "sh000001")
        self.assertEqual(saved_manager.saved[0][2], "akshare")

    def test_sync_market_data_routes_dxy_through_yfinance_manager(self) -> None:
        saved_manager = _StubStorageManager()
        yf_df = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-06-15").date(),
                    "open": 98.1,
                    "high": 98.8,
                    "low": 97.9,
                    "close": 98.4,
                    "volume": 1,
                    "amount": 0,
                    "pct_chg": 0.2,
                }
            ]
        )
        fetcher_manager = _StubFetcherManager(yf_df, "yfinance")

        with patch.object(
            market_sync_service,
            "MARKET_INDICES",
            [{"code": "DX-Y.NYB", "source": "yfinance", "name": "美元指数"}],
        ), patch("src.services.market_sync_service.StorageManager", return_value=saved_manager), patch(
            "src.services.market_sync_service.DataFetcherManager",
            return_value=fetcher_manager,
        ):
            stats = market_sync_service.sync_market_data(days=30)

        self.assertEqual(stats["success"], 1)
        self.assertEqual(fetcher_manager.calls, [("DX-Y.NYB", 30)])
        self.assertEqual(len(saved_manager.saved), 1)
        self.assertEqual(saved_manager.saved[0][1], "DX-Y.NYB")
        self.assertEqual(saved_manager.saved[0][2], "yfinance")


if __name__ == "__main__":
    unittest.main()
