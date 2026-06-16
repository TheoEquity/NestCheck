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


if __name__ == "__main__":
    unittest.main()
