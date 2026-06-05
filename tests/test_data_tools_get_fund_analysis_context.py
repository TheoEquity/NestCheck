import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.agent.tools.data_tools import _handle_get_fund_analysis_context


class FundAnalysisContextToolTestCase(unittest.TestCase):
    def test_get_fund_analysis_context_aggregates_core_blocks(self) -> None:
        overview = pd.DataFrame([
            {
                "基金全称": "测试成长混合型证券投资基金",
                "基金简称": "测试成长混合",
                "基金代码": "000001",
                "基金类型": "混合型-灵活",
                "成立日期/规模": "2020年01月01日 / 10.00亿份",
                "净资产规模": "20.00亿元（截止至：2026年03月31日）",
                "基金管理人": "测试基金",
                "基金经理人": "张三",
                "管理费率": "1.20%（每年）",
                "托管费率": "0.20%（每年）",
                "业绩比较基准": "沪深300指数收益率*60%+中债指数收益率*40%",
            }
        ])
        purchase = pd.DataFrame([
            {
                "基金代码": "000001",
                "最新净值/万份收益": "1.20",
                "最新净值/万份收益-报告时间": "06-05",
                "申购状态": "开放申购",
                "赎回状态": "开放赎回",
                "购买起点": "10.0",
                "手续费": "0.15",
            }
        ])
        nav = pd.DataFrame([
            {"净值日期": "2025-06-05", "单位净值": 1.0, "日增长率": 0.0},
            {"净值日期": "2025-12-05", "单位净值": 1.1, "日增长率": 1.0},
            {"净值日期": "2026-06-05", "单位净值": 1.2, "日增长率": 2.0},
        ])
        risk = pd.DataFrame([
            {
                "周期": "近1年",
                "较同类风险收益比": "70",
                "较同类抗风险波动": "65",
                "年化波动率": "18.5",
                "年化夏普比率": "1.2",
                "最大回撤": "10.0",
            }
        ])
        achievement = pd.DataFrame([
            {
                "业绩类型": "年度业绩",
                "周期": "今年以来",
                "本产品区间收益": "12.3",
                "本产品最大回撒": "8.0",
                "周期收益同类排名": "100/1000",
            }
        ])
        probability = pd.DataFrame([
            {"持有时长": "满1年", "盈利概率": "60", "平均收益": "12.0"}
        ])
        stock_hold = pd.DataFrame([
            {
                "股票代码": "600519",
                "股票名称": "贵州茅台",
                "占净值比例": "5.00",
                "持股数": "10.0",
                "持仓市值": "1000.0",
                "季度": "2026年1季度股票投资明细",
            }
        ])
        industry = pd.DataFrame([
            {"行业类别": "制造业", "占净值比例": "40.0", "市值": "8000", "截止时间": "2026-03-31"}
        ])
        bond_hold = pd.DataFrame([
            {"债券代码": "240001", "债券名称": "测试债", "占净值比例": "3.0", "持仓市值": "600", "季度": "2026年1季度债券投资明细"}
        ])
        rating = pd.DataFrame([
            {"代码": "000001", "简称": "测试成长混合", "基金经理": "张三", "基金公司": "测试基金", "上海证券": "5", "招商证券": "4", "济安金信": "5", "晨星评级": "4", "类型": "混合型"}
        ])

        fake_ak = MagicMock()
        fake_ak.fund_overview_em.return_value = overview
        fake_ak.fund_purchase_em.return_value = purchase
        fake_ak.fund_open_fund_info_em.return_value = nav
        fake_ak.fund_individual_analysis_xq.return_value = risk
        fake_ak.fund_individual_achievement_xq.return_value = achievement
        fake_ak.fund_individual_profit_probability_xq.return_value = probability
        fake_ak.fund_portfolio_hold_em.return_value = stock_hold
        fake_ak.fund_portfolio_industry_allocation_em.return_value = industry
        fake_ak.fund_portfolio_bond_hold_em.return_value = bond_hold
        fake_ak.fund_rating_all.return_value = rating

        with patch.dict("sys.modules", {"akshare": fake_ak}):
            result = _handle_get_fund_analysis_context("1", report_year="2026")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["fund_code"], "000001")
        self.assertEqual(result["profile"]["fund_short_name"], "测试成长混合")
        self.assertEqual(result["trading"]["subscription_status"], "开放申购")
        self.assertEqual(result["performance"]["latest_nav"], 1.2)
        self.assertEqual(result["risk_metrics"]["periods"][0]["年化夏普比率"], "1.2")
        self.assertEqual(result["holding_experience"]["periods"][0]["盈利概率"], "60")
        self.assertEqual(result["holdings"]["top_stocks"][0]["股票名称"], "贵州茅台")
        self.assertEqual(result["holdings"]["top_stock_weight_pct"], 5.0)
        self.assertNotIn("rating", result)


if __name__ == "__main__":
    unittest.main()
