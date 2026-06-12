# -*- coding: utf-8 -*-
"""Integration tests for market API endpoints."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.storage import DatabaseManager, StockDaily


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


class MarketApiTestCase(unittest.TestCase):
    """Market API contract tests for V1.0 dashboard consumers."""

    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "market_api_test.db"
        self.env_path.write_text(
            "\n".join(
                [
                    "CUSTOM_NOTE=sample",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        app = create_app(static_dir=self.data_dir / "empty-static")
        self.client = TestClient(app)
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()
        _reset_auth_globals()

    def _seed_index_history(self, code: str, start: date, closes: list[float]) -> None:
        with self.db.get_session() as session:
            for offset, close in enumerate(closes):
                session.add(
                    StockDaily(
                        code=code,
                        date=start + timedelta(days=offset),
                        open=close,
                        high=close,
                        low=close,
                        close=close,
                        volume=1.0,
                        amount=close,
                        pct_chg=offset * 0.5,
                        data_source="market-api-test",
                    )
                )
            session.commit()

    def test_index_history_returns_limited_ascending_daily_bars(self) -> None:
        start = date(2026, 1, 1)
        self._seed_index_history("sh000300", start, [100.0, 101.0, 102.0])
        self._seed_index_history("511260.SH", start, [1.0, 1.1, 1.2])

        resp = self.client.get("/api/v1/market/index-history", params={"code": "sh000300", "limit": 2})

        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["code"], "sh000300")
        self.assertEqual(
            payload["items"],
            [
                {"date": "2026-01-02", "close": 101.0, "pct_chg": 0.5},
                {"date": "2026-01-03", "close": 102.0, "pct_chg": 1.0},
            ],
        )

    def test_index_history_returns_empty_items_for_unknown_code(self) -> None:
        resp = self.client.get("/api/v1/market/index-history", params={"code": "missing", "limit": 5})

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json(), {"code": "missing", "items": []})


if __name__ == "__main__":
    unittest.main()
