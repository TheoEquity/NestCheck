# -*- coding: utf-8 -*-

import unittest

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


if __name__ == "__main__":
    unittest.main()
