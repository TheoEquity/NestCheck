# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from src.config import Config
from src.config_storage import ConfigStorage


class TushareCompatTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        Config.reset_instance()

    def test_legacy_tushare_env_enables_runtime_config(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TUSHARE": "true",
                "TUSHARE_TOKEN": "demo-token",
            },
            clear=False,
        ):
            os.environ.pop("TUSHARE_ENABLED", None)
            Config.reset_instance()
            config = Config._load_from_env()

        self.assertTrue(config.tushare)
        self.assertEqual(config.realtime_source_priority, "tushare,tencent,akshare_sina,efinance,akshare_em")

    def test_data_sources_reflect_runtime_enabled_tushare(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            storage = ConfigStorage(config_dir=tempdir)
            with patch("src.config.get_config") as mock_get_config:
                mock_get_config.return_value = type(
                    "RuntimeConfig",
                    (),
                    {"tushare": True, "tushare_token": "demo-token"},
                )()
                sources = storage.get_data_sources()

        tushare = next(source for source in sources if source.get("type") == "tushare")
        self.assertTrue(tushare["enabled"])
        self.assertEqual(tushare["priority"], -1)


if __name__ == "__main__":
    unittest.main()
