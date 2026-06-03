# -*- coding: utf-8 -*-
"""Sector ETF configuration, data refresh, and hard-indicator ranking."""

from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import desc

from src.storage import SectorEtf, StockDaily, get_db

logger = logging.getLogger(__name__)

BENCHMARK_CODE = "sh000300"
_TS_CODE_PATTERN = re.compile(r"^(?:\d{6}\.(?:SH|SZ)|sh\d{6}|sz\d{6})$", re.IGNORECASE)


def list_sector_etf_configs() -> List[Dict[str, Any]]:
    db = get_db()
    with db.get_session() as session:
        rows = session.query(SectorEtf).order_by(SectorEtf.sort_order.asc(), SectorEtf.id.asc()).all()
        configs = [_sector_to_dict(row) for row in rows]
    if configs or not hasattr(db, "_init_sector_etfs"):
        return configs
    db._init_sector_etfs()
    with db.get_session() as session:
        rows = session.query(SectorEtf).order_by(SectorEtf.sort_order.asc(), SectorEtf.id.asc()).all()
        return [_sector_to_dict(row) for row in rows]


def update_sector_etf_config(sector: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    sector = (sector or "").strip()
    if not sector:
        raise ValueError("sector is required")

    db = get_db()
    with db.get_session() as session:
        row = session.query(SectorEtf).filter_by(sector=sector).one_or_none()
        if row is None:
            raise KeyError(sector)

        if "ts_code" in payload:
            ts_code = _normalize_ts_code(payload.get("ts_code"))
            if not _TS_CODE_PATTERN.fullmatch(ts_code):
                raise ValueError("Invalid ETF code format, expected 515220.SH or 159928.SZ")
            row.ts_code = ts_code
        if "name" in payload:
            row.name = str(payload.get("name") or "").strip() or row.name
        if "weight" in payload:
            weight = float(payload.get("weight"))
            if weight <= 0:
                raise ValueError("weight must be greater than 0")
            row.weight = weight
        if "is_core" in payload:
            row.is_core = bool(payload.get("is_core"))

        row.updated_at = datetime.now()
        session.commit()
        session.refresh(row)
        return _sector_to_dict(row)


def get_sector_etf_dashboard(force_refresh: bool = False) -> Dict[str, Any]:
    if force_refresh:
        refresh_sector_etf_daily_data()

    configs = list_sector_etf_configs()
    benchmark_month_ret = _get_month_return(BENCHMARK_CODE)
    items = [_build_sector_item(config, benchmark_month_ret) for config in configs]
    items = [item for item in items if item is not None]

    top_gainers = sorted(
        items,
        key=lambda item: item["daily_pct_chg"] if item["daily_pct_chg"] is not None else -9999,
        reverse=True,
    )[:5]
    top_losers = sorted(
        items,
        key=lambda item: item["daily_pct_chg"] if item["daily_pct_chg"] is not None else 9999,
    )[:5]
    monthly_rankings = sorted(
        items,
        key=lambda item: item["month_pct_chg"] if item["month_pct_chg"] is not None else -9999,
        reverse=True,
    )

    return {
        "snapshot_date": _latest_snapshot_date(items),
        "benchmark": {"code": BENCHMARK_CODE, "month_pct_chg": _pct(benchmark_month_ret)},
        "items": items,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "monthly_rankings": monthly_rankings,
        "configs": configs,
        "updated_at": datetime.now().isoformat(),
    }


def refresh_sector_etf_daily_data(days: int = 90) -> Dict[str, Any]:
    configs = list_sector_etf_configs()
    token = (os.getenv("TUSHARE_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is required for sector ETF daily refresh")

    try:
        import tushare as ts
    except ImportError as exc:
        raise RuntimeError("tushare package is required for sector ETF daily refresh") from exc

    pro = ts.pro_api(token)
    end_date = date.today().strftime("%Y%m%d")
    start_date = (date.today() - timedelta(days=days * 2)).strftime("%Y%m%d")
    refreshed = 0
    failed = 0
    failures: List[str] = []

    for config in configs:
        ts_code = config["ts_code"]
        try:
            df = pro.fund_daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields="trade_date,open,high,low,close,vol,amount,pct_chg",
            )
            if df is None or df.empty:
                raise ValueError("empty fund_daily response")
            _upsert_stock_daily(ts_code, df)
            refreshed += 1
        except Exception as exc:
            failed += 1
            failures.append(f"{ts_code}: {exc}")
            logger.warning("Sector ETF refresh failed: %s, code=%s", exc, ts_code)

    return {"refreshed": refreshed, "failed": failed, "failures": failures[:20]}


def _sector_to_dict(row: SectorEtf) -> Dict[str, Any]:
    return {
        "id": row.id,
        "sector": row.sector,
        "ts_code": row.ts_code,
        "name": row.name,
        "weight": row.weight,
        "is_core": bool(row.is_core),
        "sort_order": row.sort_order,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _normalize_ts_code(value: Any) -> str:
    text = str(value or "").strip()
    if "." in text:
        left, right = text.split(".", 1)
        return f"{left.zfill(6)}.{right.upper()}"
    return text


def _upsert_stock_daily(code: str, df) -> None:
    records = []
    for _, row in df.iterrows():
        trade_date = datetime.strptime(str(row.get("trade_date")), "%Y%m%d").date()
        records.append({
            "code": code,
            "date": trade_date,
            "open": _float_or_none(row.get("open")),
            "high": _float_or_none(row.get("high")),
            "low": _float_or_none(row.get("low")),
            "close": _float_or_none(row.get("close")),
            "volume": _float_or_none(row.get("vol")),
            "amount": _float_or_none(row.get("amount")),
            "pct_chg": _float_or_none(row.get("pct_chg")),
            "data_source": "tushare_fund_daily",
            "updated_at": datetime.now(),
        })
    if not records:
        return

    db = get_db()

    def _op(session):
        for record in records:
            row = session.query(StockDaily).filter_by(code=record["code"], date=record["date"]).one_or_none()
            if row is None:
                session.add(StockDaily(**record))
                continue
            for key, value in record.items():
                setattr(row, key, value)

    db._run_write_transaction(f"sector_etf:{code}", _op)


def _build_sector_item(config: Dict[str, Any], benchmark_month_ret: Optional[float]) -> Optional[Dict[str, Any]]:
    bars = _load_latest_bars(config["ts_code"], limit=25)
    if not bars:
        return {
            **config,
            "date": None,
            "close": None,
            "daily_pct_chg": None,
            "month_pct_chg": None,
            "rs": None,
            "status": "missing",
        }

    latest = bars[0]
    month_ret = _calc_month_return_from_bars(bars)
    rs = None
    if month_ret is not None and benchmark_month_ret is not None:
        rs = month_ret - benchmark_month_ret

    return {
        **config,
        "date": latest.date.isoformat() if latest.date else None,
        "close": _round(latest.close),
        "daily_pct_chg": _round(latest.pct_chg),
        "month_pct_chg": _pct(month_ret),
        "rs": _pct(rs),
        "status": "ok",
    }


def _load_latest_bars(code: str, limit: int) -> List[StockDaily]:
    db = get_db()
    with db.get_session() as session:
        return (
            session.query(StockDaily)
            .filter(StockDaily.code == code)
            .order_by(desc(StockDaily.date))
            .limit(limit)
            .all()
        )


def _get_month_return(code: str) -> Optional[float]:
    return _calc_month_return_from_bars(_load_latest_bars(code, limit=25))


def _calc_month_return_from_bars(bars: Iterable[StockDaily]) -> Optional[float]:
    rows = list(bars)
    if len(rows) < 21:
        return None
    result = 1.0
    for row in rows[:20]:
        if row.pct_chg is None:
            return None
        result *= 1 + float(row.pct_chg) / 100
    return result - 1


def _latest_snapshot_date(items: List[Dict[str, Any]]) -> str:
    dates = [item.get("date") for item in items if item.get("date")]
    return max(dates) if dates else ""


def _float_or_none(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def _pct(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value) * 100, 2)
