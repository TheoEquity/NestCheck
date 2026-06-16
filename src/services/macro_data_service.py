"""Macro data helpers for stable free daily feeds."""

from __future__ import annotations

import logging
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
    "DX-Y.NYB": "DTWEXBGS",
    "USDCNY=X": "DEXCHUS",
    "^TNX": "DGS10",
    "us_vix": "VIXCLS",
    "^VIX": "VIXCLS",
}

FRED_GRAPH_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
OPEN_ER_LATEST_USD_URL = "https://open.er-api.com/v6/latest/USD"
REQUEST_TIMEOUT_SECONDS = 10


def supports_fred_code(code: str) -> bool:
    return code in FRED_SERIES_BY_CODE


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
    response = requests.get(FRED_GRAPH_CSV_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
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
    response = requests.get(OPEN_ER_LATEST_USD_URL, timeout=REQUEST_TIMEOUT_SECONDS)
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
        return fetch_fred_daily_dataframe(code, days=days)
    return pd.DataFrame()


def fetch_supported_latest_quote(code: str) -> Optional[Dict[str, object]]:
    if supports_fred_code(code):
        return fetch_fred_latest_quote(code)
    return None
