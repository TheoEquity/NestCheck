"""Macro data helpers for stable free daily feeds."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

logger = logging.getLogger(__name__)

FRED_SERIES_BY_CODE: Dict[str, str] = {
    "^DJI": "DJIA",
    "^IXIC": "NASDAQCOM",
    "^GSPC": "SP500",
    "USDCNY=X": "DEXCHUS",
    "^TNX": "DGS10",
    "us_vix": "VIXCLS",
    "^VIX": "VIXCLS",
}

FRED_GRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
OPEN_ER_LATEST_USD_URL = "https://open.er-api.com/v6/latest/USD"
REQUEST_TIMEOUT_SECONDS = 10
REQUEST_ATTEMPTS = 3


def _request_with_retries(url: str, *, params: Optional[Dict[str, object]] = None) -> requests.Response:
    last_error: Optional[Exception] = None
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        timeout = REQUEST_TIMEOUT_SECONDS + (attempt - 1) * 5
        try:
            return requests.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "Request failed for %s on attempt %s/%s: %s",
                url,
                attempt,
                REQUEST_ATTEMPTS,
                exc,
            )
            if attempt < REQUEST_ATTEMPTS:
                time.sleep(0.5 * attempt)
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request failed without exception: {url}")


def supports_fred_code(code: str) -> bool:
    return code in FRED_SERIES_BY_CODE


def _normalize_provider_name(provider: object) -> str:
    raw = str(provider or "").strip()
    lowered = raw.lower()
    if lowered.endswith("fetcher"):
        lowered = lowered[:-7]
    return lowered or "network_fallback"


def _fetch_manager_daily_dataframe(code: str, *, days: int) -> pd.DataFrame:
    from data_provider.base import DataFetcherManager

    manager = DataFetcherManager()
    df, source = manager.get_daily_data(code, days=days)
    if df is None or df.empty:
        return pd.DataFrame()
    df.attrs["source"] = _normalize_provider_name(source)
    return df


def _fetch_manager_latest_quote(code: str) -> Optional[Dict[str, object]]:
    from data_provider.base import DataFetcherManager

    manager = DataFetcherManager()
    quote = manager.get_realtime_quote(code, log_final_failure=False)
    if quote is None:
        return None
    price = getattr(quote, "price", None)
    if price in (None, ""):
        return None
    change_pct = getattr(quote, "change_pct", None)
    source = getattr(quote, "source", None)
    return {
        "value": float(price),
        "date": date.today().isoformat(),
        "change_pct": float(change_pct) if change_pct is not None else None,
        "source": _normalize_provider_name(getattr(source, "value", source)),
    }


def _parse_fred_csv(code: str, csv_text: str) -> List[Tuple[date, float]]:
    observations: List[Tuple[date, float]] = []
    series_id = FRED_SERIES_BY_CODE.get(code)
    if not series_id:
        return observations
    frame = pd.read_csv(StringIO(csv_text))
    if frame.empty or "observation_date" not in frame.columns or series_id not in frame.columns:
        return observations
    for item in frame.to_dict(orient="records"):
        raw_value = str(item.get(series_id, "")).strip()
        if not raw_value or raw_value == ".":
            continue
        raw_date = str(item.get("observation_date", "")).strip()
        try:
            obs_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            obs_value = float(raw_value)
        except (TypeError, ValueError):
            continue
        observations.append((obs_date, obs_value))
    return observations


def fetch_fred_observations(code: str, *, start_date: Optional[date] = None) -> List[Tuple[date, float]]:
    series_id = FRED_SERIES_BY_CODE.get(code)
    if not series_id:
        return []
    params = {"id": series_id}
    if start_date is not None:
        params["cosd"] = start_date.isoformat()
    response = _request_with_retries(FRED_GRAPH_CSV_URL, params=params)
    response.raise_for_status()
    return _parse_fred_csv(code, response.text)


def build_daily_dataframe(code: str, observations: List[Tuple[date, float]]) -> pd.DataFrame:
    if not observations:
        return pd.DataFrame()
    df = pd.DataFrame(observations, columns=["date", "close"])
    df["open"] = df["close"]
    df["high"] = df["close"]
    df["low"] = df["close"]
    df["volume"] = 0
    df["amount"] = 0
    df["pct_chg"] = df["close"].pct_change() * 100.0
    return df[["date", "open", "high", "low", "close", "volume", "amount", "pct_chg"]]


def fetch_fred_daily_dataframe(code: str, *, days: int) -> pd.DataFrame:
    lookback_days = max(days * 3, 45)
    observations = fetch_fred_observations(code, start_date=date.today() - timedelta(days=lookback_days))
    if not observations:
        return pd.DataFrame()
    df = build_daily_dataframe(code, observations)
    df.attrs["source"] = "fred"
    return df.tail(days + 10).reset_index(drop=True)


def fetch_fred_latest_quote(code: str) -> Optional[Dict[str, object]]:
    observations = fetch_fred_observations(code, start_date=date.today() - timedelta(days=20))
    if not observations:
        return None
    current_date, current_value = observations[-1]
    previous_value = observations[-2][1] if len(observations) >= 2 else None
    change_pct = None
    if previous_value not in (None, 0):
        change_pct = (current_value - previous_value) / previous_value * 100.0
    return {
        "value": float(current_value),
        "date": current_date.isoformat(),
        "change_pct": round(float(change_pct), 2) if change_pct is not None else None,
        "source": "fred",
    }


def fetch_latest_usd_cny_rate() -> Optional[Dict[str, object]]:
    response = _request_with_retries(OPEN_ER_LATEST_USD_URL)
    response.raise_for_status()
    payload = response.json()
    rates = payload.get("rates") or {}
    value = rates.get("CNY")
    if value in (None, ""):
        return None
    updated_at = payload.get("time_last_update_unix")
    if updated_at is not None:
        try:
            updated_date = datetime.fromtimestamp(int(updated_at), tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError, OSError):
            updated_date = date.today().isoformat()
    else:
        updated_date = date.today().isoformat()
    return {
        "value": float(value),
        "date": updated_date,
        "source": "open_er_api",
    }


def fetch_supported_daily_dataframe(code: str, *, days: int) -> pd.DataFrame:
    if supports_fred_code(code):
        try:
            df = fetch_fred_daily_dataframe(code, days=days)
        except Exception as exc:
            logger.warning("FRED daily fetch failed for %s: %s", code, exc)
            df = pd.DataFrame()
        if df is not None and not df.empty:
            return df
        try:
            return _fetch_manager_daily_dataframe(code, days=days)
        except Exception as exc:
            logger.warning("Manager daily fallback failed for %s: %s", code, exc)
            return pd.DataFrame()
    return pd.DataFrame()


def fetch_supported_latest_quote(code: str) -> Optional[Dict[str, object]]:
    if supports_fred_code(code):
        try:
            quote = fetch_fred_latest_quote(code)
        except Exception as exc:
            logger.warning("FRED latest quote failed for %s: %s", code, exc)
            quote = None
        if quote is not None:
            return quote
        try:
            return _fetch_manager_latest_quote(code)
        except Exception as exc:
            logger.warning("Manager realtime fallback failed for %s: %s", code, exc)
            return None
    return None
