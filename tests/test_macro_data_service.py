# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src.services import macro_data_service


class _StubResponse:
    def __init__(self, text: str = "", payload=None):
        self.text = text
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class MacroDataServiceTestCase(unittest.TestCase):
    def test_fetch_fred_latest_quote_parses_value_and_change_pct(self) -> None:
        csv_text = "observation_date,DEXCHUS\n2026-06-10,7.2000\n2026-06-11,7.2360\n"
        with patch("src.services.macro_data_service.requests.get", return_value=_StubResponse(text=csv_text)):
            quote = macro_data_service.fetch_fred_latest_quote("USDCNY=X")

        self.assertIsNotNone(quote)
        self.assertEqual(quote["date"], "2026-06-11")
        self.assertAlmostEqual(float(quote["value"]), 7.236, places=6)
        self.assertAlmostEqual(float(quote["change_pct"]), 0.5, places=2)
        self.assertEqual(quote["source"], "fred")

    def test_fetch_fred_latest_quote_supports_us_equity_indices(self) -> None:
        csv_text = "observation_date,SP500\n2026-06-10,5900.00\n2026-06-11,5959.00\n"
        with patch("src.services.macro_data_service.requests.get", return_value=_StubResponse(text=csv_text)):
            quote = macro_data_service.fetch_fred_latest_quote("^GSPC")

        self.assertIsNotNone(quote)
        self.assertEqual(quote["date"], "2026-06-11")
        self.assertAlmostEqual(float(quote["value"]), 5959.0, places=6)
        self.assertEqual(quote["source"], "fred")

    def test_fetch_fred_daily_dataframe_builds_standard_columns(self) -> None:
        csv_text = "observation_date,VIXCLS\n2026-06-09,.\n2026-06-10,21.0\n2026-06-11,22.05\n"
        with patch("src.services.macro_data_service.requests.get", return_value=_StubResponse(text=csv_text)):
            df = macro_data_service.fetch_fred_daily_dataframe("us_vix", days=5)

        self.assertEqual(list(df.columns), ["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"])
        self.assertEqual(len(df), 2)
        self.assertAlmostEqual(float(df.iloc[-1]["close"]), 22.05, places=6)
        self.assertAlmostEqual(float(df.iloc[-1]["pct_chg"]), 5.0, places=2)

    def test_parse_fred_csv_uses_fredgraph_columns(self) -> None:
        csv_text = "observation_date,DJIA\n2026-06-10,42000.1\n2026-06-11,42100.2\n"

        observations = macro_data_service._parse_fred_csv("^DJI", csv_text)

        self.assertEqual(len(observations), 2)
        self.assertEqual(observations[-1][0].isoformat(), "2026-06-11")
        self.assertAlmostEqual(observations[-1][1], 42100.2, places=6)

    def test_fetch_fred_observations_uses_fredgraph_endpoint_without_api_key(self) -> None:
        with patch(
            "src.services.macro_data_service.requests.get",
            return_value=_StubResponse(text="observation_date,SP500\n2026-06-10,5900.00\n"),
        ) as mocked_get:
            macro_data_service.fetch_fred_observations("^GSPC", start_date=macro_data_service.date(2026, 6, 10))

        _, kwargs = mocked_get.call_args
        self.assertEqual(kwargs["params"]["id"], "SP500")
        self.assertEqual(kwargs["params"]["cosd"], "2026-06-10")
        self.assertNotIn("api_key", kwargs["params"])

    def test_fetch_latest_usd_cny_rate_reads_open_er_payload(self) -> None:
        payload = {
            "result": "success",
            "time_last_update_unix": 1781395200,
            "rates": {"CNY": 7.2512},
        }
        with patch("src.services.macro_data_service.requests.get", return_value=_StubResponse(payload=payload)):
            quote = macro_data_service.fetch_latest_usd_cny_rate()

        self.assertIsNotNone(quote)
        self.assertAlmostEqual(float(quote["value"]), 7.2512, places=6)
        self.assertEqual(quote["source"], "open_er_api")

    def test_fetch_supported_daily_dataframe_falls_back_to_manager_on_fred_timeout(self) -> None:
        fallback_df = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-06-15").date(),
                    "open": 42000.0,
                    "high": 42100.0,
                    "low": 41900.0,
                    "close": 42050.0,
                    "volume": 1,
                    "amount": 1,
                    "pct_chg": 0.2,
                }
            ]
        )
        with patch(
            "src.services.macro_data_service.fetch_fred_daily_dataframe",
            side_effect=macro_data_service.requests.ReadTimeout("timeout"),
        ), patch(
            "src.services.macro_data_service._fetch_manager_daily_dataframe",
            return_value=fallback_df,
        ) as mocked_fallback:
            df = macro_data_service.fetch_supported_daily_dataframe("^DJI", days=30)

        mocked_fallback.assert_called_once_with("^DJI", days=30)
        self.assertFalse(df.empty)

    def test_fetch_supported_latest_quote_falls_back_to_manager_on_fred_timeout(self) -> None:
        fallback_quote = {
            "value": 5959.0,
            "date": "2026-06-15",
            "change_pct": 0.3,
            "source": "yfinance",
        }
        with patch(
            "src.services.macro_data_service.fetch_fred_latest_quote",
            side_effect=macro_data_service.requests.ReadTimeout("timeout"),
        ), patch(
            "src.services.macro_data_service._fetch_manager_latest_quote",
            return_value=fallback_quote,
        ) as mocked_fallback:
            quote = macro_data_service.fetch_supported_latest_quote("^GSPC")

        mocked_fallback.assert_called_once_with("^GSPC")
        self.assertEqual(quote, fallback_quote)


if __name__ == "__main__":
    unittest.main()
