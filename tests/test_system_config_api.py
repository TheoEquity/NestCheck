# -*- coding: utf-8 -*-
"""Integration tests for system configuration API endpoints."""

import asyncio
import os
import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException, Request

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from api.middlewares.auth import add_auth_middleware
from api.middlewares.error_handler import add_error_handlers
from api.v1.endpoints import system_config
from api.v1.schemas.system_config import (
    DiscoverLLMChannelModelsRequest,
    ImportSystemConfigRequest,
    TestLLMChannelRequest,
    UpdateSystemConfigRequest,
)
import src.auth as auth
from src.config import Config
from src.core.config_manager import ConfigManager
from src.services.system_config_service import SystemConfigService
from src.agent.tools import search_tools


class SystemConfigApiTestCase(unittest.TestCase):
    """System config API tests in isolation without loading the full app."""

    def setUp(self) -> None:
        auth._auth_enabled = None
        auth._session_secret = None
        auth._password_hash_salt = None
        auth._password_hash_stored = None
        auth._rate_limit = {}

        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.env_path.write_text(
            "\n".join(
                [
                    "CUSTOM_NOTE=desktop sample",
                    "GEMINI_API_KEY=secret-key-value",
                    "RUN_IMMEDIATELY=true",
                    "LOG_LEVEL=INFO",
                    "ADMIN_AUTH_ENABLED=true",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self._orig_dsa_desktop_mode = os.environ.get("DSA_DESKTOP_MODE")
        self._orig_database_path = os.environ.get("DATABASE_PATH")
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(Path(self.temp_dir.name) / "system_config_api_test.db")
        Config.reset_instance()

        self.manager = ConfigManager(env_path=self.env_path)
        self.service = SystemConfigService(manager=self.manager)
        self._verify_session_patch = patch.object(system_config, "verify_session", return_value=True)
        self._verify_session_patch.start()

    def tearDown(self) -> None:
        Config.reset_instance()
        self._verify_session_patch.stop()
        os.environ.pop("ENV_FILE", None)
        if self._orig_dsa_desktop_mode is None:
            os.environ.pop("DSA_DESKTOP_MODE", None)
        else:
            os.environ["DSA_DESKTOP_MODE"] = self._orig_dsa_desktop_mode
        if self._orig_database_path is None:
            os.environ.pop("DATABASE_PATH", None)
        else:
            os.environ["DATABASE_PATH"] = self._orig_database_path
        self.temp_dir.cleanup()

    @staticmethod
    def _build_request(cookies: dict[str, str] | None = None) -> SimpleNamespace:
        return SimpleNamespace(
            cookies=cookies if cookies is not None else {system_config.COOKIE_NAME: "valid-session-token"}
        )

    def _build_client_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/api/v1/system/config/export")
        async def export_config(request: Request):
            return system_config.export_system_config(request=request, service=self.service)

        add_error_handlers(app)
        add_auth_middleware(app)
        return app

    def test_get_config_masks_secret_value(self) -> None:
        payload = system_config.get_system_config(include_schema=True, service=self.service).model_dump(by_alias=True)
        item_map = {item["key"]: item for item in payload["items"]}
        self.assertEqual(item_map["GEMINI_API_KEY"]["value"], "******")
        self.assertTrue(item_map["GEMINI_API_KEY"]["raw_value_exists"])
        self.assertTrue(item_map["GEMINI_API_KEY"]["is_masked"])

    def test_get_config_schema_includes_help_metadata(self) -> None:
        payload = system_config.get_system_config(include_schema=True, service=self.service).model_dump(by_alias=True)
        item_map = {item["key"]: item for item in payload["items"]}
        api_key_schema = item_map["GEMINI_API_KEY"]["schema"]

        self.assertEqual(api_key_schema["help_key"], "settings.ai_model.provider_keys")
        self.assertTrue(api_key_schema["examples"])
        self.assertTrue(api_key_schema["docs"])

    def test_get_config_includes_dynamic_llm_channel_fields(self) -> None:
        self.env_path.write_text(
            "\n".join(
                [
                    "LLM_CHANNELS=dashscope",
                    "LLM_DASHSCOPE_PROTOCOL=openai",
                    "LLM_DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "LLM_DASHSCOPE_ENABLED=true",
                    "LLM_DASHSCOPE_API_KEY=sk-dashscope-test",
                    "LLM_DASHSCOPE_MODELS=glm-5",
                    "AGENT_LITELLM_MODEL=openai/glm-5",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        payload = system_config.get_system_config(include_schema=True, service=self.service).model_dump(by_alias=True)
        item_map = {item["key"]: item for item in payload["items"]}

        self.assertEqual(item_map["LLM_DASHSCOPE_PROTOCOL"]["value"], "openai")
        self.assertEqual(item_map["LLM_DASHSCOPE_BASE_URL"]["value"], "https://dashscope.aliyuncs.com/compatible-mode/v1")
        self.assertEqual(item_map["LLM_DASHSCOPE_ENABLED"]["value"], "true")
        self.assertEqual(item_map["LLM_DASHSCOPE_API_KEY"]["value"], "******")
        self.assertTrue(item_map["LLM_DASHSCOPE_API_KEY"]["is_masked"])
        self.assertEqual(item_map["LLM_DASHSCOPE_MODELS"]["value"], "glm-5")
        self.assertEqual(item_map["LLM_DASHSCOPE_API_KEY"]["schema"]["category"], "ai_model")
        self.assertTrue(item_map["LLM_DASHSCOPE_API_KEY"]["schema"]["is_sensitive"])

    def test_llm_base_url_guard_blocks_internal_targets(self) -> None:
        blocked_urls = [
            "http://localhost:11434/v1",
            "http://127.0.0.1:11434/v1",
            "http://10.0.0.1/v1",
            "http://192.168.0.1/v1",
            "http://169.254.169.254/latest/meta-data",
            "http://metadata.google.internal/computeMetadata/v1",
        ]

        for url in blocked_urls:
            with self.subTest(url=url):
                self.assertFalse(SystemConfigService._is_safe_base_url(url))

    def test_llm_base_url_guard_allows_private_targets_with_escape_hatch(self) -> None:
        with patch.dict(os.environ, {"DSA_ALLOW_PRIVATE_LLM_BASE_URLS": "true"}, clear=False):
            self.assertTrue(SystemConfigService._is_safe_base_url("http://127.0.0.1:11434/v1"))

    def test_llm_base_url_guard_blocks_dns_to_private_address(self) -> None:
        private_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]

        with patch("src.services.system_config_service.socket.getaddrinfo", return_value=private_info):
            self.assertFalse(SystemConfigService._is_safe_base_url("https://llm.internal.example/v1"))

    def test_agent_fetch_url_guard_blocks_internal_targets(self) -> None:
        self.assertIsNone(search_tools._safe_fetch_url("http://localhost/page"))
        self.assertIsNone(search_tools._safe_fetch_url("http://127.0.0.1/page"))
        self.assertIsNone(search_tools._safe_fetch_url("http://169.254.169.254/latest/meta-data"))

    def test_agent_fetch_url_guard_blocks_dns_to_private_address(self) -> None:
        private_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]

        with patch("src.agent.tools.search_tools.socket.getaddrinfo", return_value=private_info):
            self.assertIsNone(search_tools._safe_fetch_url("https://news.internal.example/article"))

    def test_get_config_schema_excludes_removed_notification_fields(self) -> None:
        payload = system_config.get_system_config(include_schema=True, service=self.service).model_dump(by_alias=True)
        item_map = {item["key"]: item for item in payload["items"]}

        self.assertNotIn("NOTIFICATION_DEDUP_TTL_SECONDS", item_map)
        self.assertNotIn("NOTIFICATION_COOLDOWN_SECONDS", item_map)
        self.assertNotIn("NOTIFICATION_DAILY_DIGEST_ENABLED", item_map)
        self.assertNotIn("NOTIFICATION_MIN_SEVERITY", item_map)

    def test_get_setup_status_returns_readiness_payload(self) -> None:
        self.env_path.write_text(
            "\n".join(
                [
                    "LITELLM_MODEL=gemini/gemini-3-flash-preview",
                    "GEMINI_API_KEY=secret-key-value",
                    "CUSTOM_NOTE=sample",
                    "ADMIN_AUTH_ENABLED=false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {}, clear=True):
            payload = system_config.get_setup_status(service=self.service).model_dump()

        self.assertTrue(payload["is_complete"])
        self.assertTrue(payload["ready_for_smoke"])
        self.assertEqual(payload["required_missing_keys"], [])
        check_map = {check["key"]: check for check in payload["checks"]}
        self.assertEqual(check_map["llm_primary"]["status"], "configured")
        self.assertEqual(check_map["llm_agent"]["status"], "inherited")

    def test_put_config_updates_secret_and_plain_field(self) -> None:
        current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()
        payload = system_config.update_system_config(
            request=UpdateSystemConfigRequest(
                config_version=current["config_version"],
                mask_token="******",
                reload_now=False,
                items=[
                    {"key": "GEMINI_API_KEY", "value": "new-secret-value"},
                    {"key": "CUSTOM_NOTE", "value": "updated sample"},
                ],
            ),
            service=self.service,
        ).model_dump()

        self.assertEqual(payload["applied_count"], 2)
        self.assertEqual(payload["skipped_masked_count"], 0)

        env_content = self.env_path.read_text(encoding="utf-8")
        self.assertIn("CUSTOM_NOTE=updated sample", env_content)
        self.assertIn("GEMINI_API_KEY=new-secret-value", env_content)

    def test_put_config_returns_conflict_when_version_is_stale(self) -> None:
        with self.assertRaises(HTTPException) as context:
            system_config.update_system_config(
                request=UpdateSystemConfigRequest(
                    config_version="stale-version",
                    items=[{"key": "CUSTOM_NOTE", "value": "updated sample"}],
                ),
                service=self.service,
            )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(context.exception.detail["error"], "config_version_conflict")

    def test_put_config_preserves_comments_and_blank_lines(self) -> None:
        self.env_path.write_text(
            "\n".join(
                [
                    "# Base settings",
                    "CUSTOM_NOTE=desktop sample",
                    "",
                    "# Secrets",
                    "GEMINI_API_KEY=secret-key-value",
                    "ADMIN_AUTH_ENABLED=false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()
        payload = system_config.update_system_config(
            request=UpdateSystemConfigRequest(
                config_version=current["config_version"],
                mask_token="******",
                reload_now=False,
                items=[{"key": "CUSTOM_NOTE", "value": "updated sample"}],
            ),
            service=self.service,
        ).model_dump()

        self.assertTrue(payload["success"])
        env_content = self.env_path.read_text(encoding="utf-8")
        self.assertIn("# Base settings\n", env_content)
        self.assertIn("\n\n# Secrets\n", env_content)
        self.assertIn("CUSTOM_NOTE=updated sample\n", env_content)

    def test_put_config_returns_startup_only_bind_warning(self) -> None:
        current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()
        payload = system_config.update_system_config(
            request=UpdateSystemConfigRequest(
                config_version=current["config_version"],
                reload_now=True,
                items=[
                    {"key": "WEBUI_PORT", "value": "8502"},
                ],
            ),
            service=self.service,
        ).model_dump()

        self.assertTrue(payload["success"])
        bind_warning = next(
            warning
            for warning in payload["warnings"]
            if "WEBUI_PORT 已写入 .env" in warning
        )
        self.assertIn("启动期监听配置", bind_warning)
        self.assertIn("不会因为本次保存重新绑定监听地址或端口", bind_warning)

    def test_export_system_config_returns_raw_env_content(self) -> None:
        self.env_path.write_text(
            "# Web config\nCUSTOM_NOTE=desktop sample\nGEMINI_API_KEY=secret-key-value\nADMIN_AUTH_ENABLED=true\n",
            encoding="utf-8",
        )
        self.manager = ConfigManager(env_path=self.env_path)
        self.service = SystemConfigService(manager=self.manager)
        Config.reset_instance()

        payload = system_config.export_system_config(
            request=self._build_request(),
            service=self.service,
        ).model_dump()

        self.assertEqual(
            payload["content"],
            "# Web config\nCUSTOM_NOTE=desktop sample\nGEMINI_API_KEY=secret-key-value\nADMIN_AUTH_ENABLED=true\n",
        )
        self.assertEqual(payload["config_version"], self.manager.get_config_version())

    def test_import_system_config_merges_updates(self) -> None:
        current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()

        payload = system_config.import_system_config(
            request_obj=self._build_request(),
            request=ImportSystemConfigRequest(
                config_version=current["config_version"],
                content="CUSTOM_NOTE=config backup\n",
                reload_now=False,
            ),
            service=self.service,
        ).model_dump()

        self.assertTrue(payload["success"])
        env_content = self.env_path.read_text(encoding="utf-8")
        self.assertIn("CUSTOM_NOTE=config backup\n", env_content)
        self.assertIn("GEMINI_API_KEY=secret-key-value\n", env_content)

    def test_import_system_config_returns_conflict_when_version_is_stale(self) -> None:
        with self.assertRaises(HTTPException) as context:
            system_config.import_system_config(
                request_obj=self._build_request(),
                request=ImportSystemConfigRequest(
                    config_version="stale-version",
                    content="CUSTOM_NOTE=config backup\n",
                    reload_now=False,
                ),
                service=self.service,
            )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(context.exception.detail["error"], "config_version_conflict")

    def test_import_system_config_returns_bad_request_for_invalid_content(self) -> None:
        current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()

        with self.assertRaises(HTTPException) as context:
            system_config.import_system_config(
                request_obj=self._build_request(),
                request=ImportSystemConfigRequest(
                    config_version=current["config_version"],
                    content="# comments only\n\n",
                    reload_now=False,
                ),
                service=self.service,
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.detail["error"], "invalid_import_file")

    def test_import_system_config_returns_bad_request_for_empty_content(self) -> None:
        current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()

        with self.assertRaises(HTTPException) as context:
            system_config.import_system_config(
                request_obj=self._build_request(),
                request=ImportSystemConfigRequest(
                    config_version=current["config_version"],
                    content="",
                    reload_now=False,
                ),
                service=self.service,
            )

        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.detail["error"], "invalid_import_file")

    def test_config_env_endpoints_work_outside_desktop_mode(self) -> None:
        with patch.dict(os.environ, {"DSA_DESKTOP_MODE": "false"}, clear=False):
            current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()

            export_payload = system_config.export_system_config(
                request=self._build_request(),
                service=self.service,
            ).model_dump()
            import_payload = system_config.import_system_config(
                request_obj=self._build_request(),
                request=ImportSystemConfigRequest(
                    config_version=current["config_version"],
                    content="CUSTOM_NOTE=config backup\n",
                    reload_now=False,
                ),
                service=self.service,
            ).model_dump()

            self.assertIn("CUSTOM_NOTE=desktop sample", export_payload["content"])
            self.assertTrue(import_payload["success"])
            self.assertEqual(self.manager.read_config_map()["CUSTOM_NOTE"], "config backup")

    def test_config_env_endpoints_reject_without_backup_access(self) -> None:
        with patch.dict(
            os.environ,
            {"DSA_DESKTOP_MODE": "false"},
            clear=False,
        ):
            self.env_path.write_text(
                "\n".join(
                    [
                        "CUSTOM_NOTE=desktop sample",
                        "GEMINI_API_KEY=secret-key-value",
                        "RUN_IMMEDIATELY=true",
                        "LOG_LEVEL=INFO",
                        "ADMIN_AUTH_ENABLED=false",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            self.manager = ConfigManager(env_path=self.env_path)
            self.service = SystemConfigService(manager=self.manager)
            Config.reset_instance()

            current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()

            with self.assertRaises(HTTPException) as export_ctx:
                system_config.export_system_config(
                    request=self._build_request(),
                    service=self.service,
                )
            self.assertEqual(export_ctx.exception.status_code, 403)
            self.assertEqual(export_ctx.exception.detail["error"], "env_backup_access_denied")

            with self.assertRaises(HTTPException) as import_ctx:
                system_config.import_system_config(
                    request_obj=self._build_request(),
                    request=ImportSystemConfigRequest(
                        config_version=current["config_version"],
                        content="CUSTOM_NOTE=config backup\n",
                        reload_now=False,
                    ),
                    service=self.service,
                )
            self.assertEqual(import_ctx.exception.status_code, 403)
            self.assertEqual(import_ctx.exception.detail["error"], "env_backup_access_denied")

    def test_config_env_endpoints_require_valid_admin_session(self) -> None:
        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "false"}, clear=False),
            patch.object(system_config, "verify_session", return_value=False),
        ):
            current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()
            invalid_request = self._build_request({system_config.COOKIE_NAME: "invalid-session"})

            with self.assertRaises(HTTPException) as export_ctx:
                system_config.export_system_config(request=invalid_request, service=self.service)
            self.assertEqual(export_ctx.exception.status_code, 401)
            self.assertEqual(export_ctx.exception.detail["error"], "env_backup_access_denied")

            with self.assertRaises(HTTPException) as import_ctx:
                system_config.import_system_config(
                    request_obj=invalid_request,
                    request=ImportSystemConfigRequest(
                        config_version=current["config_version"],
                        content="CUSTOM_NOTE=config backup\n",
                        reload_now=False,
                    ),
                    service=self.service,
                )
            self.assertEqual(import_ctx.exception.status_code, 401)
            self.assertEqual(import_ctx.exception.detail["error"], "env_backup_access_denied")

    def test_config_env_endpoints_require_explicit_true_for_desktop_bypass(self) -> None:
        with patch.dict(
            os.environ,
            {"DSA_DESKTOP_MODE": "desktop"},
            clear=False,
        ):
            self.env_path.write_text(
                "\n".join(
                    [
                        "CUSTOM_NOTE=desktop sample",
                        "GEMINI_API_KEY=secret-key-value",
                        "RUN_IMMEDIATELY=true",
                        "LOG_LEVEL=INFO",
                        "ADMIN_AUTH_ENABLED=false",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            self.manager = ConfigManager(env_path=self.env_path)
            self.service = SystemConfigService(manager=self.manager)
            Config.reset_instance()

            with self.assertRaises(HTTPException) as export_ctx:
                system_config.export_system_config(
                    request=self._build_request(),
                    service=self.service,
                )

            self.assertEqual(export_ctx.exception.status_code, 403)
            self.assertEqual(export_ctx.exception.detail["error"], "env_backup_access_denied")

    def test_config_env_endpoints_return_server_error_for_storage_permission_error(self) -> None:
        current = system_config.get_system_config(include_schema=False, service=self.service).model_dump()

        with patch.object(self.service, "export_env", side_effect=PermissionError("read denied")):
            with self.assertRaises(HTTPException) as export_ctx:
                system_config.export_system_config(
                    request=self._build_request(),
                    service=self.service,
                )

        self.assertEqual(export_ctx.exception.status_code, 500)
        self.assertEqual(export_ctx.exception.detail["error"], "internal_error")

        with patch.object(self.service, "import_env", side_effect=PermissionError("write denied")):
            with self.assertRaises(HTTPException) as import_ctx:
                system_config.import_system_config(
                    request_obj=self._build_request(),
                    request=ImportSystemConfigRequest(
                        config_version=current["config_version"],
                        content="CUSTOM_NOTE=config backup\n",
                        reload_now=False,
                    ),
                    service=self.service,
                )

        self.assertEqual(import_ctx.exception.status_code, 500)
        self.assertEqual(import_ctx.exception.detail["error"], "internal_error")

    def test_config_env_endpoints_reject_without_session_after_auth_toggle(self) -> None:
        self.env_path.write_text(
            "\n".join(
                [
                    "CUSTOM_NOTE=desktop sample",
                    "GEMINI_API_KEY=secret-key-value",
                    "RUN_IMMEDIATELY=true",
                    "LOG_LEVEL=INFO",
                    "ADMIN_AUTH_ENABLED=false",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.manager = ConfigManager(env_path=self.env_path)
        self.service = SystemConfigService(manager=self.manager)
        Config.reset_instance()

        self.env_path.write_text(
            "\n".join(
                [
                    "CUSTOM_NOTE=desktop sample",
                    "GEMINI_API_KEY=secret-key-value",
                    "RUN_IMMEDIATELY=true",
                    "LOG_LEVEL=INFO",
                    "ADMIN_AUTH_ENABLED=true",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        auth._auth_enabled = False

        async def request_export() -> httpx.Response:
            transport = httpx.ASGITransport(app=self._build_client_app())
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.get("/api/v1/system/config/export")

        response = asyncio.run(request_export())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "env_backup_access_denied")

    def test_test_llm_channel_endpoint_returns_service_payload(self) -> None:
        with patch.object(
            self.service,
            "test_llm_channel",
            return_value={
                "success": True,
                "message": "LLM channel test succeeded",
                "error": None,
                "error_code": None,
                "stage": "chat_completion",
                "retryable": False,
                "details": {},
                "resolved_protocol": "openai",
                "resolved_model": "openai/gpt-4o-mini",
                "latency_ms": 123,
            },
        ) as mock_test:
            payload = system_config.test_llm_channel(
                request=TestLLMChannelRequest(
                    name="primary",
                    protocol="openai",
                    base_url="https://api.example.com/v1",
                    api_key="sk-test",
                    models=["gpt-4o-mini"],
                    capability_checks=["json", "stream"],
                ),
                service=self.service,
            ).model_dump()

        self.assertTrue(payload["success"])
        self.assertEqual(payload["resolved_model"], "openai/gpt-4o-mini")
        self.assertEqual(payload["stage"], "chat_completion")
        self.assertEqual(payload["capability_results"], {})
        mock_test.assert_called_once()
        self.assertEqual(mock_test.call_args.kwargs["capability_checks"], ["json", "stream"])

    def test_validate_returns_user_facing_model_message_without_internal_env_key_name(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LITELLM_MODEL", "value": "openai/gpt-4o"},
            ]
        )

        self.assertFalse(validation["valid"])
        issue = next(issue for issue in validation["issues"] if issue["key"] == "LITELLM_MODEL")
        self.assertEqual(issue["code"], "unknown_model")
        self.assertNotIn("LITELLM_MODEL", issue["message"])
        self.assertIn("primary model", issue["message"].lower())

    def test_discover_llm_channel_models_endpoint_returns_service_payload(self) -> None:
        with patch.object(
            self.service,
            "discover_llm_channel_models",
            return_value={
                "success": True,
                "message": "LLM channel model discovery succeeded",
                "error": None,
                "error_code": None,
                "stage": "model_discovery",
                "retryable": False,
                "details": {"model_count": 2},
                "resolved_protocol": "openai",
                "models": ["qwen-plus", "qwen-turbo"],
                "latency_ms": 88,
            },
        ) as mock_discover:
            payload = system_config.discover_llm_channel_models(
                request=DiscoverLLMChannelModelsRequest(
                    name="dashscope",
                    protocol="openai",
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    api_key="sk-test",
                ),
                service=self.service,
            ).model_dump()

        self.assertTrue(payload["success"])
        self.assertEqual(payload["models"], ["qwen-plus", "qwen-turbo"])
        self.assertEqual(payload["stage"], "model_discovery")
        mock_discover.assert_called_once()


if __name__ == "__main__":
    unittest.main()
