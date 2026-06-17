# -*- coding: utf-8 -*-

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.services import market_risk_service


class MarketRiskServiceTestCase(unittest.TestCase):
    def test_bond_spread_prefers_tnx_record(self) -> None:
        def _load_record(*codes):
            if codes == ("bond_cn_10y",):
                return {"code": "bond_cn_10y", "value": 1.73, "date": "2026-06-17", "source": "akshare"}
            if codes == ("^TNX", "bond_us_10y"):
                return {"code": "^TNX", "value": 4.43, "date": "2026-06-17", "source": "fred"}
            raise AssertionError(f"unexpected lookup: {codes}")

        with patch("src.services.market_risk_service._load_latest_stock_daily_record", side_effect=_load_record), patch(
            "src.services.market_risk_service._save_cache"
        ):
            result = market_risk_service._bond_spread()

        self.assertEqual(result["source"], "fred")
        self.assertAlmostEqual(result["us_10y"], 4.43, places=2)
        self.assertAlmostEqual(result["cn_10y"], 1.73, places=2)
        self.assertAlmostEqual(result["spread"], 2.7, places=2)

    def test_bond_spread_uses_tnx_network_quote_before_akshare(self) -> None:
        def _load_record(*codes):
            if codes == ("bond_cn_10y",):
                return {"code": "bond_cn_10y", "value": 1.73, "date": "2026-06-17", "source": "akshare"}
            if codes == ("^TNX", "bond_us_10y"):
                return None
            raise AssertionError(f"unexpected lookup: {codes}")

        quote = {"value": 4.47, "date": "2026-06-17", "source": "fred", "change_pct": 0.1}
        with patch("src.services.market_risk_service._load_latest_stock_daily_record", side_effect=_load_record), patch(
            "src.services.market_risk_service.fetch_supported_latest_quote",
            return_value=quote,
        ) as mocked_quote, patch("src.services.market_risk_service.ak.bond_zh_us_rate") as mocked_ak, patch(
            "src.services.market_risk_service._save_cache"
        ):
            result = market_risk_service._bond_spread()

        mocked_quote.assert_called_once_with("^TNX")
        mocked_ak.assert_not_called()
        self.assertEqual(result["source"], "fred")
        self.assertAlmostEqual(result["us_10y"], 4.47, places=2)


if __name__ == "__main__":
    unittest.main()
