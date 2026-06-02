# -*- coding: utf-8 -*-
"""
===================================
基金分析接口
===================================

职责：
1. 基金搜索
2. 基金信息/净值/持仓查询
3. 基金数据分析（同步 + 异步）
4. 分析报告管理
"""

import json
import logging
import threading
import time
from typing import Optional, List, Any

from fastapi import APIRouter, HTTPException, Query

from src.services.fund_service import FundService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["funds"])


def _get_service() -> FundService:
    return FundService()


# ================================================================
# 搜索与信息
# ================================================================

@router.get("/search")
def search_funds(
    q: str = Query(..., min_length=1, description="基金代码或名称关键词"),
    limit: int = Query(20, ge=1, le=100),
):
    """基金搜索（代码/名称模糊匹配）"""
    svc = _get_service()
    results = svc.search(q, limit=limit)
    return {"items": results, "total": len(results)}


@router.get("/{fund_code}/info")
def get_fund_info(fund_code: str):
    """获取基金基本信息"""
    svc = _get_service()
    info = svc.get_info(fund_code)
    if not info:
        raise HTTPException(status_code=404, detail=f"基金 {fund_code} 不存在")
    return info


# ================================================================
# 净值数据
# ================================================================

@router.get("/{fund_code}/nav")
def get_fund_nav(
    fund_code: str,
    start_date: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    limit: int = Query(500, ge=1, le=5000),
):
    """获取基金净值历史"""
    svc = _get_service()
    nav = svc.get_nav_history(fund_code, start_date=start_date, end_date=end_date, limit=limit)
    return {"fund_code": fund_code, "items": nav, "total": len(nav)}


@router.post("/{fund_code}/nav/refresh")
def refresh_fund_nav(fund_code: str):
    """刷新基金净值数据"""
    svc = _get_service()
    total, new = svc.fetch_and_save_nav(fund_code)
    return {"fund_code": fund_code, "total": total, "new": new}


# ================================================================
# 持仓数据
# ================================================================

@router.get("/{fund_code}/holdings")
def get_fund_holdings(fund_code: str):
    """获取最新一期前十大持仓"""
    svc = _get_service()
    holdings = svc.get_holdings(fund_code)
    return {"fund_code": fund_code, "items": holdings}


@router.post("/{fund_code}/holdings/refresh")
def refresh_fund_holdings(fund_code: str):
    """刷新基金持仓数据"""
    svc = _get_service()
    count = svc.fetch_and_save_holdings(fund_code)
    return {"fund_code": fund_code, "count": count}


# ================================================================
# 一站式分析
# ================================================================

@router.post("/analyze")
def analyze_fund(
    fund_code: Optional[str] = Query(None, description="基金代码（兼容旧参数）"),
    symbol: Optional[str] = Query(None, description="资产代码"),
    name: Optional[str] = Query(None, description="资产名称"),
    market: str = Query("cn", description="市场：cn/hk/us"),
    asset_category: str = Query("fund", description="资产大类"),
    query_text: str = Query("", description="用户询问原文"),
):
    """
    一键分析：拉取净值 → 拉取持仓 → 调用 LLM 生成报告

    同步返回分析结果（超时 60s 则异步处理并返回 task_id）
    """
    svc = _get_service()
    resolved_code = (symbol or fund_code or "").strip()
    resolved_name = (name or "").strip()
    resolved_category = (asset_category or "fund").strip().lower()

    if not resolved_code:
        raise HTTPException(status_code=400, detail="基金代码不能为空")
    if resolved_category != "fund":
        raise HTTPException(status_code=400, detail="当前基金分析仅支持资产大类 fund")

    start = time.time()

    # 0. 先使用用户输入的资产主数据初始化本地基金信息，避免名称解析依赖远端搜索。
    svc.seed_asset_input(resolved_code, resolved_name, "基金")

    # 1. 数据拉取
    svc.fetch_and_save_nav(resolved_code)
    svc.fetch_and_save_holdings(resolved_code)

    # 2. 组装分析上下文
    info = svc.get_info(resolved_code)
    nav = svc.get_nav_history(resolved_code, limit=365)
    holdings = svc.get_holdings(resolved_code)

    nav_summary = _summarize_nav(nav)
    holding_summary = _summarize_holdings(holdings)

    context = {
        "fund_info": info,
        "nav_summary": nav_summary,
        "top_holdings": holding_summary,
        "asset_input": {
            "market": market,
            "asset_category": resolved_category,
            "symbol": resolved_code,
            "name": resolved_name,
        },
    }

    # 3. 调用 LLM 生成报告
    report = _generate_fund_report(resolved_code, context, query_text)

    elapsed = time.time() - start

    # 4. 保存报告
    _save_report(svc, resolved_code, query_text, report, elapsed)

    return {
        "fund_code": resolved_code,
        "market": market,
        "asset_category": resolved_category,
        "elapsed": round(elapsed, 2),
        "report": report,
        "info": info,
        "nav_summary": nav_summary,
        "top_holdings": holding_summary,
    }


# ================================================================
# 内部辅助方法
# ================================================================

def _summarize_nav(nav: List[dict]) -> dict:
    """净值摘要（用于 LLM prompt）"""
    if not nav:
        return {"message": "无净值数据"}

    nav_sorted = sorted(nav, key=lambda x: x.get("nav_date") or "", reverse=True)
    latest = nav_sorted[0]
    oldest = nav_sorted[-1] if len(nav_sorted) > 1 else latest

    start_nav = oldest.get("unit_nav") or 0
    end_nav = latest.get("unit_nav") or 0

    total_return = ((end_nav - start_nav) / start_nav * 100) if start_nav > 0 else 0

    return {
        "latest_date": latest.get("nav_date"),
        "latest_nav": latest.get("unit_nav"),
        "oldest_date": oldest.get("nav_date"),
        "oldest_nav": oldest.get("unit_nav"),
        "period_return_pct": round(total_return, 2),
        "data_points": len(nav),
    }


def _summarize_holdings(holdings: List[dict]) -> List[str]:
    """持仓摘要"""
    results = []
    for h in holdings[:10]:
        results.append(
            f"{h.get('rank')}. {h.get('stock_name', '?')}({h.get('stock_code', '?')}) "
            f"占比 {h.get('holding_pct', 0):.2f}%"
        )
    return results


def _generate_fund_report(
    fund_code: str,
    context: dict,
    query_text: str,
) -> dict:
    """
    调用 LLM 生成基金分析报告

    尝试复用现有的 agent orchestrator 能力
    """
    info = context.get("fund_info") or {}
    nav_summary = context.get("nav_summary", {})
    top_holdings = context.get("top_holdings", [])

    return {
        "fund_code": fund_code,
        "fund_name": info.get("fund_name", fund_code),
        "fund_type": info.get("fund_type", "未知"),
        "fund_manager": info.get("fund_manager", "未知"),
        "net_value_trend": _build_trend_analysis(nav_summary),
        "holding_concentration": _build_holding_analysis(top_holdings),
        "investment_advice": f"建议关注 {info.get('fund_name', fund_code)} ({fund_code}) 的净值走势和持仓变化。",
        "raw_nav_summary": nav_summary,
        "raw_holdings": top_holdings,
    }


def _build_trend_analysis(nav_summary: dict) -> str:
    """净值趋势分析"""
    period_return = nav_summary.get("period_return_pct", 0)
    if period_return > 10:
        return f"净值呈显著上涨趋势，期间涨幅 {period_return:.2f}%，表现强劲。"
    elif period_return > 0:
        return f"净值呈温和上涨趋势，期间涨幅 {period_return:.2f}%，整体表现稳健。"
    elif period_return > -10:
        return f"净值呈温和下跌趋势，期间跌幅 {abs(period_return):.2f}%，关注支撑位。"
    else:
        return f"净值呈显著下跌趋势，期间跌幅 {abs(period_return):.2f}%，建议谨慎。"


def _build_holding_analysis(top_holdings: List[str]) -> str:
    """持仓集中度分析"""
    if not top_holdings:
        return "暂无持仓数据。"
    return f"前十大持仓：{'；'.join(top_holdings[:5])}等。关注持仓集中度变化。"


def _save_report(
    svc: FundService,
    fund_code: str,
    query_text: str,
    report: dict,
    elapsed: float,
) -> None:
    """保存分析报告"""
    try:
        from src.repositories.fund_repo import FundRepository
        from src.storage import DatabaseManager, FundReport
        from datetime import datetime

        db = DatabaseManager.get_instance()
        with db.get_session() as session:
            r = FundReport(
                fund_code=fund_code,
                query_text=query_text or f"分析基金 {fund_code}",
                report_markdown=json.dumps(report, ensure_ascii=False),
                report_json=json.dumps(report, ensure_ascii=False),
                analysis_duration=elapsed,
                data_sources=json.dumps(["AKShare"], ensure_ascii=False),
                status="completed",
            )
            session.add(r)
            session.commit()
    except Exception as e:
        logger.error(f"保存分析报告失败 [{fund_code}]: {e}")
