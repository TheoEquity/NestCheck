# -*- coding: utf-8 -*-
"""Watchlist-only hard-rule traffic light refresh service."""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from sqlalchemy import and_, desc, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from data_provider.base import DataFetcherManager, normalize_stock_code
from data_provider.tushare_fetcher import TushareFetcher
from src.storage import (
    DatabaseManager,
    StockDaily,
    WatchlistIndicatorSnapshot,
    WatchlistItem,
    WatchlistSignalSnapshot,
)

logger = logging.getLogger(__name__)

LIGHT_LABELS = {
    "L_VAL": "估值温度",
    "L_QUAL": "利润质量",
    "L_SOLV": "偿债韧性",
    "L_PAY": "兑现力",
    "L_TECH": "周线节奏",
}

SECTOR_TAGS = {"stable", "cyclical", "financial"}
CYCLICAL_HINTS = ("煤", "钢", "有色", "矿", "化工", "石油", "油", "航运", "资源")
FINANCIAL_HINTS = ("银行", "保险", "证券", "券商", "金融", "信托")
TARGET_DAILY_ROWS_FOR_INIT = 520


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _first_float(row: Any, keys: Iterable[str]) -> Optional[float]:
    for key in keys:
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _light(code: str, status: str, reason: str, value: Optional[float] = None) -> Dict[str, Any]:
    return {
        "code": code,
        "label": LIGHT_LABELS[code],
        "status": status,
        "reason": reason,
        "value": value,
    }


def _compound_pct(values: List[float]) -> Optional[float]:
    if not values:
        return None
    factor = 1.0
    for value in values:
        factor *= 1.0 + value / 100.0
    return (factor - 1.0) * 100.0


def _ts_code(symbol: str) -> str:
    code = normalize_stock_code(symbol).upper()
    if code.endswith(".SH") or code.endswith(".SZ") or code.endswith(".BJ"):
        return code
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return code


def _sector_tag_from_text(*parts: Any) -> str:
    source = " ".join(str(part or "") for part in parts)
    if any(token in source for token in FINANCIAL_HINTS):
        return "financial"
    if any(token in source for token in CYCLICAL_HINTS):
        return "cyclical"
    return "stable"


def _sector_tag(item: WatchlistItem) -> str:
    return _sector_tag_from_text(item.asset_subcategory, item.asset_risk_class, item.watch_tags, item.watch_reason, item.notes, item.name)


class WatchlistSignalService:
    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self.db = db or DatabaseManager.get_instance()

    def refresh_enabled_stocks(self) -> Dict[str, Any]:
        items = self._list_enabled_stock_items()
        results = []
        for item in items:
            try:
                results.append(self.refresh_item(item))
            except Exception as exc:
                logger.warning("Watchlist signal refresh failed for %s: %s", item.symbol, exc, exc_info=True)
                results.append({"item_id": item.id, "symbol": item.symbol, "status": "failed", "error": str(exc)})
        return {
            "status": "success",
            "total": len(items),
            "success": sum(1 for item in results if item.get("status") == "success"),
            "failed": sum(1 for item in results if item.get("status") == "failed"),
            "items": results,
        }

    def refresh_item_by_id(self, item_id: int) -> Dict[str, Any]:
        with self.db.get_session() as session:
            item = session.execute(select(WatchlistItem).where(WatchlistItem.id == item_id)).scalar_one_or_none()
            if item is None:
                raise ValueError(f"关注标的不存在: {item_id}")
            if item.asset_category != "stock":
                raise ValueError("当前只支持股票关注标的红绿灯刷新")
            session.expunge(item)
        return self.refresh_item(item)

    def refresh_item(self, item: WatchlistItem) -> Dict[str, Any]:
        self._backfill_daily_data(item.symbol)
        indicator, flags = self._build_indicator(item)
        signal = self._calculate_signal(indicator, flags)
        self._save_indicator_and_signal(item, indicator, signal)
        return {
            "item_id": item.id,
            "symbol": item.symbol,
            "status": "success",
            "verdict_code": signal["verdict_code"],
            "reason": signal["reason"],
            "flags": signal["data_quality_flags"],
        }

    def latest_signals_for_items(self, item_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        if not item_ids:
            return {}
        result: Dict[int, Dict[str, Any]] = {}
        with self.db.get_session() as session:
            for item_id in item_ids:
                row = session.execute(
                    select(WatchlistSignalSnapshot)
                    .where(WatchlistSignalSnapshot.watchlist_item_id == item_id)
                    .order_by(desc(WatchlistSignalSnapshot.as_of_date), desc(WatchlistSignalSnapshot.id))
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    continue
                result[item_id] = {
                    "as_of_date": row.as_of_date.isoformat() if row.as_of_date else None,
                    "verdict_code": row.verdict_code,
                    "reason": row.reason,
                    "lights": self._loads(row.lights_json, []),
                    "data_quality_flags": self._loads(row.data_quality_flags, []),
                }
        return result

    def _list_enabled_stock_items(self) -> List[WatchlistItem]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(WatchlistItem)
                .where(WatchlistItem.watch_enabled == True, WatchlistItem.asset_category == "stock")
                .order_by(WatchlistItem.id.asc())
            ).scalars().all()
            for row in rows:
                session.expunge(row)
            return list(rows)

    def _backfill_daily_data(self, symbol: str) -> None:
        code = normalize_stock_code(symbol)
        manager = DataFetcherManager()
        df, source = manager.get_daily_data(code, days=TARGET_DAILY_ROWS_FOR_INIT)
        if df is not None and not df.empty:
            self.db.save_daily_data(df, code, f"watchlist_{source}")

    def _build_indicator(self, item: WatchlistItem) -> Tuple[Dict[str, Any], List[str]]:
        flags: List[str] = []
        symbol = normalize_stock_code(item.symbol)
        ts_code = _ts_code(symbol)
        today = date.today()
        payload: Dict[str, Any] = {"symbol": symbol, "as_of_date": today, "sector_tag": _sector_tag(item)}
        payload.update(self._latest_price(symbol, flags))
        payload.update(self._weekly_metrics(symbol, flags))
        payload.update(self._tushare_fundamentals(ts_code, flags))
        if payload.get("industry"):
            payload["sector_tag"] = _sector_tag_from_text(payload.get("industry"), item.asset_subcategory, item.name)
        return payload, flags

    def _latest_price(self, symbol: str, flags: List[str]) -> Dict[str, Any]:
        with self.db.get_session() as session:
            row = session.execute(
                select(StockDaily).where(StockDaily.code == symbol).order_by(desc(StockDaily.date)).limit(1)
            ).scalar_one_or_none()
        if row is None:
            flags.append("missing_price")
            return {"price": None, "as_of_date": date.today()}
        return {"price": row.close, "as_of_date": row.date}

    def _weekly_metrics(self, symbol: str, flags: List[str]) -> Dict[str, Any]:
        with self.db.get_session() as session:
            rows = session.execute(
                select(StockDaily).where(StockDaily.code == symbol).order_by(StockDaily.date.asc())
            ).scalars().all()
        if len(rows) < 10 * 5:
            flags.append("weekly_history_short")
        if not rows:
            return {"ma10w": None, "ma30w": None, "prev_ma10w": None, "prev_ma30w": None}
        df = pd.DataFrame([{"date": row.date, "close": row.close} for row in rows if row.close is not None])
        if df.empty:
            return {"ma10w": None, "ma30w": None, "prev_ma10w": None, "prev_ma30w": None}
        df["date"] = pd.to_datetime(df["date"])
        weekly = df.set_index("date").resample("W-FRI").last().dropna().reset_index()
        weekly["ma10w"] = weekly["close"].rolling(5, min_periods=5).mean()
        weekly["ma30w"] = weekly["close"].rolling(10, min_periods=10).mean()
        latest = weekly.iloc[-1] if len(weekly) else None
        prev = weekly.iloc[-2] if len(weekly) >= 2 else None
        return {
            "ma10w": _safe_float(latest.get("ma10w")) if latest is not None else None,
            "ma30w": _safe_float(latest.get("ma30w")) if latest is not None else None,
            "prev_ma10w": _safe_float(prev.get("ma10w")) if prev is not None else None,
            "prev_ma30w": _safe_float(prev.get("ma30w")) if prev is not None else None,
        }

    def _tushare_fundamentals(self, ts_code: str, flags: List[str]) -> Dict[str, Any]:
        fetcher = TushareFetcher()
        api = getattr(fetcher, "_api", None)
        if api is None:
            flags.append("tushare_unavailable")
            return {}
        result: Dict[str, Any] = {}
        raw: Dict[str, Any] = {}
        stock_basic = self._ts_query(api, "stock_basic", flags, ts_code=ts_code, fields="ts_code,name,industry,area,market")
        if stock_basic is not None and not stock_basic.empty:
            basic_info = stock_basic.iloc[0]
            raw["stock_basic"] = basic_info.to_dict()
            result["industry"] = str(basic_info.get("industry") or "").strip() or None
        end = date.today().strftime("%Y%m%d")
        start = (date.today() - timedelta(days=540)).strftime("%Y%m%d")
        basic = self._ts_query(api, "daily_basic", flags, ts_code=ts_code, start_date=start, end_date=end)
        if basic is not None and not basic.empty:
            raw["daily_basic"] = basic.head(80).to_dict("records")
            latest = basic.sort_values("trade_date", ascending=False).iloc[0]
            result["mktcap"] = _first_float(latest, ["total_mv"])
            if result.get("mktcap") is not None:
                result["mktcap"] *= 10000.0
            result["pb"] = _first_float(latest, ["pb"])
            result["pe_ttm"] = _first_float(latest, ["pe_ttm", "pe"])
            pb_values = [_safe_float(v) for v in basic.get("pb", [])] if "pb" in basic else []
            pe_values = [_safe_float(v) for v in basic.get("pe_ttm", [])] if "pe_ttm" in basic else []
            result["pb_history"] = [v for v in pb_values if v is not None and v > 0]
            result["pe_history"] = [v for v in pe_values if v is not None and v > 0]
        else:
            flags.append("missing_daily_basic")

        indicator = self._ts_latest(api, "fina_indicator", flags, ts_code=ts_code)
        if indicator is not None:
            raw["fina_indicator"] = indicator.to_dict()
            result["eps_ttm"] = _first_float(indicator, ["eps", "basic_eps", "dt_eps"])
            result["bvps"] = _first_float(indicator, ["bps", "bvps"])
            result["roe_ttm"] = _first_float(indicator, ["roe_yearly", "roe_waa", "roe_dt", "roe"])
            result["ebitda_ttm"] = _first_float(indicator, ["ebitda"])
            result["netprofit_yoy"] = _first_float(indicator, ["netprofit_yoy", "dt_netprofit_yoy"])
            result["debt_to_assets"] = _first_float(indicator, ["debt_to_assets"])
            result["assets_to_eqt"] = _first_float(indicator, ["assets_to_eqt"])
        else:
            flags.append("missing_fina_indicator")

        income = self._ts_latest(api, "income", flags, ts_code=ts_code)
        if income is not None:
            raw["income"] = income.to_dict()
            result["ni_ttm"] = _first_float(income, ["n_income_attr_p", "n_income", "net_profit"])
            if result.get("ebitda_ttm") is None:
                result["ebitda_ttm"] = _first_float(income, ["operate_profit", "ebit"])
        else:
            flags.append("missing_income")

        cashflow = self._ts_latest(api, "cashflow", flags, ts_code=ts_code)
        if cashflow is not None:
            raw["cashflow"] = cashflow.to_dict()
            ocf = _first_float(cashflow, ["n_cashflow_act", "net_cash_flows_oper_act"])
            capex = _first_float(cashflow, ["c_pay_acq_const_fiolta", "c_pay_acq_const_faolta"])
            result["ocf_ttm"] = ocf
            result["fcf_ttm"] = ocf - capex if ocf is not None and capex is not None else None
            result["div_paid_ttm"] = _first_float(cashflow, ["c_pay_dist_dpcp_int_exp", "c_pay_dist_dpcp_int_exp"])
        else:
            flags.append("missing_cashflow")

        balance = self._ts_latest(api, "balancesheet", flags, ts_code=ts_code)
        if balance is not None:
            raw["balancesheet"] = balance.to_dict()
            debt = _first_float(balance, ["total_liab", "lt_borr", "st_borr", "total_cur_liab"])
            cash = _first_float(balance, ["money_cap", "cash_cash_equ_end_period"])
            result["net_debt"] = debt - cash if debt is not None and cash is not None else None
        else:
            flags.append("missing_balancesheet")

        result["raw_payload"] = raw
        return result

    def _ts_query(self, api: Any, api_name: str, flags: List[str], **params: Any) -> Optional[pd.DataFrame]:
        try:
            df = api.query(api_name, **params)
            return df if isinstance(df, pd.DataFrame) and not df.empty else None
        except Exception as exc:
            flags.append(f"{api_name}_failed")
            logger.debug("Tushare %s failed: %s", api_name, exc)
            return None

    def _ts_latest(self, api: Any, api_name: str, flags: List[str], **params: Any) -> Optional[Any]:
        df = self._ts_query(api, api_name, flags, **params)
        if df is None or df.empty:
            return None
        sort_col = "end_date" if "end_date" in df.columns else df.columns[0]
        return df.sort_values(sort_col, ascending=False).iloc[0]

    def _calculate_signal(self, indicator: Dict[str, Any], flags: List[str]) -> Dict[str, Any]:
        lights = [
            self._calc_val_light(indicator, flags),
            self._calc_quality_light(indicator),
            self._calc_solvency_light(indicator),
            self._calc_pay_light(indicator),
            self._calc_tech_light(indicator, flags),
        ]
        red = sum(1 for light in lights if light["status"] == "R")
        green = sum(1 for light in lights if light["status"] == "G")
        if red >= 2:
            verdict = "RISK"
        elif red == 1 or green < 3:
            verdict = "WATCH"
        else:
            verdict = "OK"
        reason = "；".join(light["reason"] for light in lights if light["status"] != "G") or "硬规则状态健康"
        return {"verdict_code": verdict, "reason": reason, "lights": lights, "data_quality_flags": flags}

    def _calc_val_light(self, indicator: Dict[str, Any], flags: List[str]) -> Dict[str, Any]:
        sector = indicator.get("sector_tag") or "stable"
        metric = "pb" if sector in {"cyclical", "financial"} else "pe_ttm"
        history = indicator.get("pb_history") if metric == "pb" else indicator.get("pe_history")
        current = _safe_float(indicator.get(metric))
        history = [float(v) for v in (history or []) if _safe_float(v) is not None and float(v) > 0]
        if current is None or current <= 0:
            return _light("L_VAL", "Y", "估值数据缺失")
        if len(history) < 60:
            flags.append("valuation_history_short")
            return _light("L_VAL", "Y", "估值历史样本不足", current)
        percentile = sum(1 for value in history if value <= current) / len(history)
        if percentile < 0.30:
            return _light("L_VAL", "G", "估值处于历史低位", percentile)
        if percentile < 0.70:
            return _light("L_VAL", "Y", "估值处于历史中位区", percentile)
        return _light("L_VAL", "R", "估值处于历史高位", percentile)

    def _calc_quality_light(self, indicator: Dict[str, Any]) -> Dict[str, Any]:
        if indicator.get("sector_tag") == "financial":
            roe = _safe_float(indicator.get("roe_ttm"))
            profit_yoy = _safe_float(indicator.get("netprofit_yoy"))
            if roe is None or profit_yoy is None:
                return _light("L_QUAL", "Y", "金融利润质量数据缺失")
            if roe >= 10 and profit_yoy >= 0:
                return _light("L_QUAL", "G", "金融利润质量健康", profit_yoy)
            if roe >= 7 and profit_yoy >= -10:
                return _light("L_QUAL", "Y", "金融利润质量可观察", profit_yoy)
            return _light("L_QUAL", "R", "金融利润质量偏弱", profit_yoy)
        ocf = _safe_float(indicator.get("ocf_ttm"))
        ni = _safe_float(indicator.get("ni_ttm"))
        fcf = _safe_float(indicator.get("fcf_ttm"))
        if ocf is None or ni is None:
            return _light("L_QUAL", "Y", "现金流或净利润数据缺失")
        cash_conv = ocf / max(abs(ni), 1.0)
        if cash_conv >= 0.85 and (fcf is not None and fcf >= 0):
            return _light("L_QUAL", "G", "利润现金含量健康", cash_conv)
        if cash_conv >= 0.65:
            return _light("L_QUAL", "Y", "利润现金含量一般", cash_conv)
        return _light("L_QUAL", "R", "利润现金含量偏弱", cash_conv)

    def _calc_solvency_light(self, indicator: Dict[str, Any]) -> Dict[str, Any]:
        if indicator.get("sector_tag") == "financial":
            debt_to_assets = _safe_float(indicator.get("debt_to_assets"))
            assets_to_eqt = _safe_float(indicator.get("assets_to_eqt"))
            if debt_to_assets is None and assets_to_eqt is None:
                return _light("L_SOLV", "Y", "金融杠杆数据缺失")
            if (debt_to_assets is not None and debt_to_assets <= 92) and (assets_to_eqt is None or assets_to_eqt <= 13):
                return _light("L_SOLV", "G", "金融杠杆韧性健康", debt_to_assets)
            if (debt_to_assets is None or debt_to_assets <= 94) and (assets_to_eqt is None or assets_to_eqt <= 16):
                return _light("L_SOLV", "Y", "金融杠杆韧性可观察", debt_to_assets)
            return _light("L_SOLV", "R", "金融杠杆压力高", debt_to_assets)
        net_debt = _safe_float(indicator.get("net_debt"))
        ebitda = _safe_float(indicator.get("ebitda_ttm"))
        if net_debt is None or ebitda is None:
            return _light("L_SOLV", "Y", "偿债数据缺失")
        ratio = net_debt / max(ebitda, 1.0)
        if ratio <= 2.5:
            return _light("L_SOLV", "G", "债务压力低", ratio)
        if ratio <= 4.5:
            return _light("L_SOLV", "Y", "债务压力中等", ratio)
        return _light("L_SOLV", "R", "债务压力高", ratio)

    def _calc_pay_light(self, indicator: Dict[str, Any]) -> Dict[str, Any]:
        roe = _safe_float(indicator.get("roe_ttm"))
        div_paid = _safe_float(indicator.get("div_paid_ttm"))
        fcf = _safe_float(indicator.get("fcf_ttm"))
        if roe is None:
            return _light("L_PAY", "Y", "ROE 数据缺失")
        pay_ok = fcf is not None and div_paid is not None and fcf >= max(div_paid, 0)
        if roe >= 10 and pay_ok:
            return _light("L_PAY", "G", "ROE 与分红覆盖健康", roe)
        if roe >= 7:
            return _light("L_PAY", "Y", "ROE 处于可观察区", roe)
        return _light("L_PAY", "R", "ROE 偏弱", roe)

    def _calc_tech_light(self, indicator: Dict[str, Any], flags: List[str]) -> Dict[str, Any]:
        ma10 = _safe_float(indicator.get("ma10w"))
        ma30 = _safe_float(indicator.get("ma30w"))
        prev10 = _safe_float(indicator.get("prev_ma10w"))
        prev30 = _safe_float(indicator.get("prev_ma30w"))
        if None in (ma10, ma30, prev10, prev30):
            flags.append("weekly_ma_missing")
            return _light("L_TECH", "Y", "周线均线数据不足")
        if ma10 >= ma30:
            reason = "周线 MA5 在 MA10 上方" if prev10 > prev30 else "周线 MA5 上穿 MA10"
            return _light("L_TECH", "G", reason)
        reason = "周线 MA5 在 MA10 下方" if prev10 < prev30 else "周线 MA5 下穿 MA10"
        return _light("L_TECH", "R", reason)

    def _save_indicator_and_signal(self, item: WatchlistItem, indicator: Dict[str, Any], signal: Dict[str, Any]) -> None:
        as_of_date = indicator.get("as_of_date") or date.today()
        raw_payload = indicator.get("raw_payload") or {}
        indicator_record = {
            "watchlist_item_id": item.id,
            "symbol": normalize_stock_code(item.symbol),
            "as_of_date": as_of_date,
            "price": indicator.get("price"),
            "eps_ttm": indicator.get("eps_ttm"),
            "ni_ttm": indicator.get("ni_ttm"),
            "bvps": indicator.get("bvps"),
            "ocf_ttm": indicator.get("ocf_ttm"),
            "fcf_ttm": indicator.get("fcf_ttm"),
            "mktcap": indicator.get("mktcap"),
            "net_debt": indicator.get("net_debt"),
            "ebitda_ttm": indicator.get("ebitda_ttm"),
            "div_paid_ttm": indicator.get("div_paid_ttm"),
            "roe_ttm": indicator.get("roe_ttm"),
            "ma10w": indicator.get("ma10w"),
            "ma30w": indicator.get("ma30w"),
            "prev_ma10w": indicator.get("prev_ma10w"),
            "prev_ma30w": indicator.get("prev_ma30w"),
            "sector_tag": indicator.get("sector_tag") if indicator.get("sector_tag") in SECTOR_TAGS else "stable",
            "source": "watchlist_signal_service",
            "raw_payload": json.dumps(raw_payload, ensure_ascii=False, default=str),
            "updated_at": datetime.now(),
        }
        signal_record = {
            "watchlist_item_id": item.id,
            "symbol": normalize_stock_code(item.symbol),
            "as_of_date": as_of_date,
            "verdict_code": signal["verdict_code"],
            "reason": signal["reason"],
            "lights_json": json.dumps(signal["lights"], ensure_ascii=False, default=str),
            "data_quality_flags": json.dumps(signal["data_quality_flags"], ensure_ascii=False),
            "updated_at": datetime.now(),
        }
        with self.db.get_session() as session:
            stmt = sqlite_insert(WatchlistIndicatorSnapshot).values(indicator_record)
            session.execute(stmt.on_conflict_do_update(
                index_elements=["watchlist_item_id", "as_of_date"],
                set_={key: getattr(stmt.excluded, key) for key in indicator_record if key not in {"watchlist_item_id", "as_of_date"}},
            ))
            stmt2 = sqlite_insert(WatchlistSignalSnapshot).values(signal_record)
            session.execute(stmt2.on_conflict_do_update(
                index_elements=["watchlist_item_id", "as_of_date"],
                set_={key: getattr(stmt2.excluded, key) for key in signal_record if key not in {"watchlist_item_id", "as_of_date"}},
            ))
            session.commit()

    @staticmethod
    def _loads(raw: Optional[str], fallback: Any) -> Any:
        if not raw:
            return fallback
        try:
            return json.loads(raw)
        except Exception:
            return fallback
