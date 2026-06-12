# -*- coding: utf-8 -*-

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from src.services.watchlist_signal_service import WatchlistSignalService


class WatchlistSignalServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WatchlistSignalService(db=object())

    def _drawdown_light(self, risk_class, max_drawdown_1y):
        lights = self.service._calc_fund_lights(
            {
                "risk_class": risk_class,
                "rank_1m_pct": 0.8,
                "rank_3m_pct": 0.8,
                "rank_1y_pct": 0.8,
                "mgr_years": 4,
                "max_drawdown_1y": max_drawdown_1y,
            },
            [],
        )
        return next(light for light in lights if light["code"] == "F_DRAWDOWN")

    def test_fund_drawdown_light_thresholds_by_risk_class(self) -> None:
        cases = [
            ("R2", 0.9, "G"),
            ("R2", 1.0, "Y"),
            ("R2", 2.0, "Y"),
            ("R2", 2.1, "R"),
            ("R3", 2.9, "G"),
            ("R3", 3.0, "Y"),
            ("R3", 5.0, "Y"),
            ("R3", 5.1, "R"),
            ("R4", 4.9, "G"),
            ("R4", 5.0, "Y"),
            ("R4", 10.0, "Y"),
            ("R4", 10.1, "R"),
            ("R5", 9.9, "G"),
            ("R5", 10.0, "Y"),
            ("R5", 20.0, "Y"),
            ("R5", 20.1, "R"),
        ]
        for risk_class, drawdown, expected_status in cases:
            with self.subTest(risk_class=risk_class, drawdown=drawdown):
                light = self._drawdown_light(risk_class, drawdown)
                self.assertEqual(light["status"], expected_status)
                self.assertEqual(light["value"], drawdown)

    def test_fund_drawdown_missing_uses_gray_light(self) -> None:
        light = self._drawdown_light("R3", None)

        self.assertEqual(light["status"], "N")
        self.assertEqual(light["reason"], "近1年回撤数据缺失")

    def test_fund_rank_uses_each_period_return_column(self) -> None:
        fake_ak = SimpleNamespace(
            fund_open_fund_info_em=lambda symbol, indicator: pd.DataFrame(
                [["2026-06-10", 1.0, 0.0], ["2026-06-11", 1.01, 1.0]],
                columns=["净值日期", "单位净值", "日增长率"],
            ),
            fund_individual_basic_info_xq=lambda symbol: pd.DataFrame(
                [["基金类型", "债券型-混合二级"]],
                columns=["item", "value"],
            ),
            fund_name_em=lambda: pd.DataFrame(
                [
                    ["000001", "债券型-普通债券"],
                    ["001258", "债券型-混合二级"],
                    ["000003", "债券型-混合二级"],
                    ["000004", "债券型-普通债券"],
                ],
                columns=["基金代码", "基金类型"],
            ),
            fund_open_fund_rank_em=lambda symbol: pd.DataFrame(
                [
                    [1, "000001", 2.0, 0.0, 7.0],
                    [2, "001258", 1.0, 5.0, 8.0],
                    [3, "000003", -1.0, 6.0, 9.0],
                    [4, "000004", 1.0, 7.0, None],
                ],
                columns=["序号", "基金代码", "近1月", "近3月", "近1年"],
            ),
            fund_individual_analysis_xq=lambda symbol: pd.DataFrame(),
        )
        fake_ts = SimpleNamespace(pro_api=lambda: SimpleNamespace(fund_manager=lambda **kwargs: pd.DataFrame()))

        with patch.dict("sys.modules", {"akshare": fake_ak, "tushare": fake_ts}):
            indicator = self.service._build_fund_indicator(SimpleNamespace(symbol="001258"), [])

        self.assertEqual(indicator["rank_1m"], 1)
        self.assertEqual(indicator["rank_1m_total"], 2)
        self.assertEqual(indicator["rank_3m"], 2)
        self.assertEqual(indicator["rank_3m_total"], 2)
        self.assertEqual(indicator["rank_1y"], 2)
        self.assertEqual(indicator["rank_1y_total"], 2)
        self.assertEqual(indicator["rank_1m_pct"], 1.0)
        self.assertEqual(indicator["rank_3m_pct"], 0.5)
        self.assertEqual(indicator["rank_1y_pct"], 0.5)
        self.assertEqual(indicator["raw_payload"]["fund_rank"]["fund_type"], "债券型")
        self.assertEqual(indicator["raw_payload"]["fund_rank"]["fund_sub_type"], "债券型-混合二级")
        self.assertEqual(indicator["raw_payload"]["fund_rank"]["rank_scope"], "sub_type")


if __name__ == "__main__":
    unittest.main()
