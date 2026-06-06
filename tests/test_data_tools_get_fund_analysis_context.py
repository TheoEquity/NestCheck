import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from src.agent.tools.data_tools import _handle_get_fund_analysis_context, _handle_get_similar_funds_by_rank_profile


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

    def test_get_similar_funds_by_rank_profile_matches_same_20_percentile_buckets(self) -> None:
        overview = pd.DataFrame([
            {"基金简称": "测试成长混合", "基金类型": "混合型-偏股"}
        ])
        rank = pd.DataFrame([
            {"基金代码": "000001", "基金简称": "测试成长混合", "日期": "2026-06-05", "单位净值": 1.10, "近3月": 90, "近1年": 90, "近3年": 90, "手续费": "0.15%"},
            {"基金代码": "000002", "基金简称": "相似混合A", "日期": "2026-06-05", "单位净值": 1.20, "近3月": 89, "近1年": 88, "近3年": 87, "手续费": "0.15%"},
            {"基金代码": "000003", "基金简称": "相似混合B", "日期": "2026-06-05", "单位净值": 1.30, "近3月": 88, "近1年": 87, "近3年": 86, "手续费": "0.20%"},
            {"基金代码": "000004", "基金简称": "一年不相似", "日期": "2026-06-05", "单位净值": 1.40, "近3月": 87, "近1年": 10, "近3年": 85, "手续费": "0.20%"},
            {"基金代码": "000005", "基金简称": "三月不相似", "日期": "2026-06-05", "单位净值": 1.50, "近3月": 10, "近1年": 86, "近3年": 84, "手续费": "0.20%"},
            {"基金代码": "000006", "基金简称": "样本6", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 9, "近1年": 9, "近3年": 9, "手续费": "0.20%"},
            {"基金代码": "000007", "基金简称": "样本7", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 8, "近1年": 8, "近3年": 8, "手续费": "0.20%"},
            {"基金代码": "000008", "基金简称": "样本8", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 7, "近1年": 7, "近3年": 7, "手续费": "0.20%"},
            {"基金代码": "000009", "基金简称": "样本9", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 6, "近1年": 6, "近3年": 6, "手续费": "0.20%"},
            {"基金代码": "000010", "基金简称": "样本10", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 5, "近1年": 5, "近3年": 5, "手续费": "0.20%"},
            {"基金代码": "000011", "基金简称": "样本11", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 4, "近1年": 4, "近3年": 4, "手续费": "0.20%"},
            {"基金代码": "000012", "基金简称": "样本12", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 3, "近1年": 3, "近3年": 3, "手续费": "0.20%"},
            {"基金代码": "000013", "基金简称": "样本13", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 2, "近1年": 2, "近3年": 2, "手续费": "0.20%"},
            {"基金代码": "000014", "基金简称": "样本14", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 1, "近1年": 1, "近3年": 1, "手续费": "0.20%"},
            {"基金代码": "000015", "基金简称": "样本15", "日期": "2026-06-05", "单位净值": 1.00, "近3月": 0, "近1年": 0, "近3年": 0, "手续费": "0.20%"},
        ])

        fake_ak = MagicMock()
        fake_ak.fund_overview_em.return_value = overview
        fake_ak.fund_open_fund_rank_em.return_value = rank

        def overview_by_code(symbol):
            if symbol == "000002":
                return pd.DataFrame([{"基金简称": "相似混合A", "份额规模": "2.00亿份", "净资产规模": "2.40亿元"}])
            if symbol == "000003":
                return pd.DataFrame([{"基金简称": "相似混合B", "份额规模": "6.00亿份", "净资产规模": "7.80亿元"}])
            return overview

        fake_ak.fund_overview_em.side_effect = overview_by_code
        fake_ak.fund_individual_analysis_xq.return_value = pd.DataFrame([
            {"周期": "近1年", "最大回撤": "6.10"},
            {"周期": "近3年", "最大回撤": "12.30"},
        ])

        with patch.dict("sys.modules", {"akshare": fake_ak}):
            result = _handle_get_similar_funds_by_rank_profile("1", limit=10)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["fund_code"], "000001")
        self.assertEqual(result["rank_category"], "混合型")
        self.assertEqual(result["bucket_size_pct"], 20)
        self.assertEqual(result["min_scale_yi"], 5.0)
        self.assertEqual(result["rank_profile"]["近3月"]["percentile_bucket"], "0-20%")
        self.assertEqual([item["fund_code"] for item in result["similar_funds"]], ["000003"])
        self.assertEqual(result["filtered_small_scale_count"], 1)
        self.assertEqual(result["similar_funds"][0]["estimated_scale_yi"], 7.8)
        self.assertEqual(result["display_only_fields"], ["max_drawdown_1y_pct"])
        self.assertEqual(result["similar_funds"][0]["max_drawdown_1y_pct"], 6.1)
        self.assertNotIn("max_drawdown_pct", result["similar_funds"][0])


if __name__ == "__main__":
    unittest.main()
