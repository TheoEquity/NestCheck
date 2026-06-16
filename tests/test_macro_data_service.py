# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.services import macro_data_service


class _StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class MacroDataServiceTestCase(unittest.TestCase):
    def test_fetch_fred_latest_quote_parses_value_and_change_pct(self) -> None:
        payload = {
            "observations": [
                {"date": "2026-06-10", "value": "7.2000"},
                {"date": "2026-06-11", "value": "7.2360"},
            ]
        }
        with patch("src.services.macro_data_service.requests.get", return_value=_StubResponse(payload)):
            quote = macro_data_service.fetch_fred_latest_quote("USDCNY=X")

        self.assertIsNotNone(quote)
        self.assertEqual(quote["date"], "2026-06-11")
        self.assertAlmostEqual(float(quote["value"]), 7.236, places=6)
        self.assertAlmostEqual(float(quote["change_pct"]), 0.5, places=2)
        self.assertEqual(quote["source"], "fred")

    def test_fetch_fred_latest_quote_supports_us_equity_indices(self) -> None:
        payload = {
            "observations": [
                {"date": "2026-06-10", "value": "5900.00"},
                {"date": "2026-06-11", "value": "5959.00"},
            ]
        }
        with patch("src.services.macro_data_service.requests.get", return_value=_StubResponse(payload)):
            quote = macro_data_service.fetch_fred_latest_quote("^GSPC")

        self.assertIsNotNone(quote)
        self.assertEqual(quote["date"], "2026-06-11")
        self.assertAlmostEqual(float(quote["value"]), 5959.0, places=6)
        self.assertEqual(quote["source"], "fred")

    def test_fetch_fred_daily_dataframe_builds_standard_columns(self) -> None:
        payload = {
            "observations": [
                {"date": "2026-06-09", "value": "."},
                {"date": "2026-06-10", "value": "21.0"},
                {"date": "2026-06-11", "value": "22.05"},
            ]
        }
        with patch("src.services.macro_data_service.requests.get", return_value=_StubResponse(payload)):
            df = macro_data_service.fetch_fred_daily_dataframe("us_vix", days=5)

        self.assertEqual(list(df.columns), ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"])
        self.assertEqual(len(df), 2)
        self.assertAlmostEqual(float(df.iloc[-1]["close"]), 22.05, places=6)
        self.assertAlmostEqual(float(df.iloc[-1]["pct_chg"]), 5.0, places=2)

    def test_fetch_latest_usd_cny_rate_reads_open_er_payload(self) -> None:
        payload = {
            "result": "success",
            "time_last_update_unix": 1781395200,
            "rates": {"CNY": 7.2512},
        }
        with patch("src.services.macro_data_service.requests.get", return_value=_StubResponse(payload)):
            quote = macro_data_service.fetch_latest_usd_cny_rate()

        self.assertIsNotNone(quote)
        self.assertAlmostEqual(float(quote["value"]), 7.2512, places=6)
        self.assertEqual(quote["source"], "open_er_api")


if __name__ == "__main__":
    unittest.main()
