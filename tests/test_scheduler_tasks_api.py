# -*- coding: utf-8 -*-
"""Unit tests for scheduler task endpoints."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from api.v1.endpoints import scheduler_tasks


class _ImmediateThread:
    def __init__(self, target=None, args=(), kwargs=None, **_unused):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


class SchedulerTasksApiTestCase(unittest.TestCase):
    def test_init_market_data_rebuilds_trend_cache_after_sync(self) -> None:
        with patch.object(scheduler_tasks.threading, "Thread", _ImmediateThread), \
             patch("src.services.market_sync_service.sync_market_data") as mock_sync, \
             patch("src.services.market_cache_service.refresh_market_cache") as mock_refresh:
            resp = scheduler_tasks.init_market_data()

        self.assertEqual(resp["status"], "running")
        mock_sync.assert_called_once_with(days=1825)
        mock_refresh.assert_called_once_with("trend")


if __name__ == "__main__":
    unittest.main()
