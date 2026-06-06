# -*- coding: utf-8 -*-
"""Agent chat history API regressions."""

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import create_app
from api.v1.endpoints.agent import ChatRequest, _prepare_chat_session
from src.config import Config
from src.storage import DatabaseManager


def teardown_function() -> None:
    DatabaseManager.reset_instance()
    Config.reset_instance()


def test_chat_session_messages_api_does_not_expose_provider_trace(tmp_path: Path) -> None:
    DatabaseManager.reset_instance()
    Config.reset_instance()
    db = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'trace.db'}")
    session_id = "api-trace-hidden"
    user_id = db.save_conversation_message(session_id, "user", "visible question")
    assistant_id = db.save_conversation_message(session_id, "assistant", "visible answer")
    db.save_agent_provider_turn(
        session_id=session_id,
        run_id="run-hidden",
        provider="deepseek",
        model="deepseek/deepseek-chat",
        anchor_user_message_id=user_id,
        anchor_assistant_message_id=assistant_id,
        messages=[
            {
                "role": "assistant",
                "content": "checking",
                "reasoning_content": "SECRET_REASONING",
                "tool_calls": [{"id": "call_1", "name": "echo", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "SECRET_TOOL_RESULT"},
        ],
        contains_reasoning=True,
        contains_tool_calls=True,
        contains_thinking_blocks=False,
        must_roundtrip=True,
        estimated_tokens=10,
    )

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        client = TestClient(create_app(static_dir=tmp_path / "static"))
        response = client.get(f"/api/v1/agent/chat/sessions/{session_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert [(msg["role"], msg["content"]) for msg in payload["messages"]] == [
        ("user", "visible question"),
        ("assistant", "visible answer"),
    ]
    assert "SECRET_REASONING" not in response.text
    assert "SECRET_TOOL_RESULT" not in response.text
    assert "tool_calls" not in response.text


def test_resolve_chat_topic_overwrites_fund_name_from_code(tmp_path: Path) -> None:
    DatabaseManager.reset_instance()
    Config.reset_instance()
    DatabaseManager(db_url=f"sqlite:///{tmp_path / 'fund-topic.db'}")

    with (
        patch("api.middlewares.auth.is_auth_enabled", return_value=False),
        patch("api.v1.endpoints.agent._resolve_fund_name_by_code", return_value="华夏成长混合") as resolver,
    ):
        client = TestClient(create_app(static_dir=tmp_path / "static"))
        response = client.get(
            "/api/v1/agent/chat/topics/resolve",
            params={
                "stock_code": "470018",
                "stock_name": "用户手填名称",
                "market": "cn",
                "asset_type": "fund",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert payload["asset_type"] == "fund"
    assert payload["code"] == "470018"
    assert payload["name"] == "华夏成长混合"
    assert payload["title"] == "470018 华夏成长混合"
    resolver.assert_called_once_with("470018")


def test_prepare_chat_session_accepts_fund_context(tmp_path: Path) -> None:
    DatabaseManager.reset_instance()
    Config.reset_instance()
    DatabaseManager(db_url=f"sqlite:///{tmp_path / 'prepare-fund.db'}")

    with patch("api.v1.endpoints.agent._resolve_fund_name_by_code", return_value="兴业收益增强债券A"):
        prepared = _prepare_chat_session(ChatRequest(
            message="基金经理还有其他持仓吗、业绩如何？",
            context={
                "agent_chat_mode": True,
                "market": "cn",
                "asset_type": "fund",
                "asset_code": "001258",
                "fund_code": "001258",
                "fund_name": "用户手填名称",
            },
        ))

    assert prepared.reject_message is None
    assert prepared.session_id.startswith("topic:")
    assert prepared.context["asset_type"] == "fund"
    assert prepared.context["asset_code"] == "001258"
    assert prepared.context["asset_name"] == "兴业收益增强债券A"
    assert prepared.context["fund_code"] == "001258"
    assert prepared.context["fund_name"] == "兴业收益增强债券A"


def test_resolve_chat_topic_accepts_market_without_code(tmp_path: Path) -> None:
    DatabaseManager.reset_instance()
    Config.reset_instance()
    DatabaseManager(db_url=f"sqlite:///{tmp_path / 'market-topic.db'}")

    with patch("api.middlewares.auth.is_auth_enabled", return_value=False):
        client = TestClient(create_app(static_dir=tmp_path / "static"))
        response = client.get(
            "/api/v1/agent/chat/topics/resolve",
            params={"market": "cn", "asset_type": "market"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert payload["market"] == "cn"
    assert payload["asset_type"] == "market"
    assert payload["code"] == "overview"
    assert payload["name"] == "A股市场"
    assert payload["title"] == "A股市场"


def test_prepare_chat_session_accepts_market_context(tmp_path: Path) -> None:
    DatabaseManager.reset_instance()
    Config.reset_instance()
    DatabaseManager(db_url=f"sqlite:///{tmp_path / 'prepare-market.db'}")

    prepared = _prepare_chat_session(ChatRequest(
        message="现在大盘环境怎么样？",
        context={
            "agent_chat_mode": True,
            "market": "cn",
            "asset_type": "market",
            "asset_code": "overview",
            "asset_name": "A股市场",
        },
    ))

    assert prepared.reject_message is None
    assert prepared.session_id.startswith("topic:")
    assert prepared.context["market"] == "cn"
    assert prepared.context["asset_type"] == "market"
    assert prepared.context["asset_code"] == "overview"
    assert prepared.context["asset_name"] == "A股市场"
    assert "stock_code" not in prepared.context
    assert "fund_code" not in prepared.context
