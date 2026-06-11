# -*- coding: utf-8 -*-
"""Configuration field metadata registry.

This module is the single source of truth for configuration UI metadata,
validation hints, and category grouping.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from src.config import AGENT_CONTEXT_COMPRESSION_PROFILES, AGENT_MAX_STEPS_DEFAULT

SCHEMA_VERSION = "2026-05-25"

_CATEGORY_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "category": "ai_model",
        "title": "AI Model",
        "description": "Model providers, model names, and inference parameters.",
        "display_order": 20,
    },
    {
        "category": "data_source",
        "title": "Data Source",
        "description": "Market data provider credentials and priority settings.",
        "display_order": 30,
    },
    {
        "category": "system",
        "title": "System",
        "description": "Runtime and scheduling controls.",
        "display_order": 50,
    },
    {
        "category": "agent",
        "title": "Agent",
        "description": "Agent mode and strategy-skill settings.",
        "display_order": 55,
    },
    {
        "category": "backtest",
        "title": "Backtest",
        "description": "Backtest engine behavior and evaluation parameters.",
        "display_order": 60,
    },
    {
        "category": "uncategorized",
        "title": "Uncategorized",
        "description": "Keys not mapped in the field registry.",
        "display_order": 99,
    },
]

_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # ------------------------------------------------------------------
    # AI Model – LiteLLM unified config
    # ------------------------------------------------------------------
    "LITELLM_MODEL": {
        "title": "Primary Model",
        "description": "Primary model in provider/model format (e.g. gemini/gemini-3.1-pro-preview, deepseek/deepseek-v4-flash, anthropic/claude-sonnet-4-6). If empty, it is auto-inferred from available API keys or channel declarations.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 1,
        "help_key": "settings.ai_model.LITELLM_MODEL",
        "examples": [
            "LITELLM_MODEL=deepseek/deepseek-v4-flash",
            "LITELLM_MODEL=gemini/gemini-3.1-pro-preview",
            "LITELLM_MODEL=ollama/qwen3:8b",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
            {
                "label": "完整指南：AI 模型配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#ai-模型配置",
            },
        ],
        "warning_codes": ["provider_prefix_required"],
    },
    "AGENT_LITELLM_MODEL": {
        "title": "Agent Primary Model",
        "description": "Optional Agent-only primary model in provider/model format. When empty, Agent inherits the primary model. Bare model names are normalized to openai/<model>.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 2,
        "help_key": "settings.ai_model.AGENT_LITELLM_MODEL",
        "examples": [
            "AGENT_LITELLM_MODEL=deepseek/deepseek-v4-pro",
            "AGENT_LITELLM_MODEL=gemini/gemini-3.1-pro-preview",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
            {
                "label": "完整指南：AI 模型配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#ai-模型配置",
            },
        ],
        "warning_codes": ["inherits_primary_when_empty"],
    },
    "LITELLM_FALLBACK_MODELS": {
        "title": "Fallback Models",
        "description": "Comma-separated fallback models tried when the primary model fails (e.g. anthropic/claude-sonnet-4-6,openai/gpt-5.4-mini). Useful for cross-provider redundancy.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 2,
        "help_key": "settings.ai_model.LITELLM_FALLBACK_MODELS",
        "examples": [
            "LITELLM_FALLBACK_MODELS=deepseek/deepseek-v4-pro,gemini/gemini-3-flash-preview",
            "LITELLM_FALLBACK_MODELS=openai/gpt-5.4-mini",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
            {
                "label": "完整指南：AI 模型配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#ai-模型配置",
            },
        ],
        "warning_codes": ["fallback_models_must_be_available"],
    },
    # ------------------------------------------------------------------
    # AI Model – Multi-channel LLM configuration
    # ------------------------------------------------------------------
    "LLM_CHANNELS": {
        "title": "LLM Channels",
        "description": "Channel names (comma-separated). Managed by the channel editor above.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 4,
        "help_key": "settings.ai_model.LLM_CHANNELS",
        "examples": [
            "LLM_CHANNELS=deepseek,aihubmix",
            "LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY=sk-xxxx",
            "LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro",
        ],
        "docs": [
            {
                "label": "LLM 配置指南：渠道模式",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md#方式二渠道channels模式配置适合进阶多模型",
            },
            {
                "label": "LLM 服务商配置速查",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/llm-providers.md",
            },
        ],
        "warning_codes": ["channels_override_legacy_keys"],
    },
    "LLM_TEMPERATURE": {
        "title": "Temperature",
        "description": "Unified sampling temperature for all LLM calls. Range [0.0, 2.0], default 0.7.",
        "category": "ai_model",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0.7",
        "options": [],
        "validation": {"min": 0.0, "max": 2.0},
        "display_order": 5,
        "help_key": "settings.ai_model.LLM_TEMPERATURE",
        "examples": [
            "LLM_TEMPERATURE=0.2",
            "LLM_TEMPERATURE=0.7",
        ],
        "docs": [
            {
                "label": "完整指南：AI 模型配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#ai-模型配置",
            },
        ],
        "warning_codes": [],
    },
    "AIHUBMIX_KEY": {
        "title": "AIHubmix Key",
        "description": "AIHubmix one-stop API key – access all mainstream models with a single key, no VPN required. Auto-sets base URL to aihubmix.com/v1. Get key: https://aihubmix.com/?aff=CfMq",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 5,
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "AIHUBMIX_KEY=sk-xxxx",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
            {
                "label": "LLM 服务商配置速查",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/llm-providers.md",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    # ------------------------------------------------------------------
    # AI Model – DeepSeek official (independent from OpenAI-compatible)
    # ------------------------------------------------------------------
    "DEEPSEEK_API_KEY": {
        "title": "DeepSeek API Key",
        "description": "Official DeepSeek API key (from https://platform.deepseek.com). For compatibility, a key set alone still auto-infers deepseek/deepseek-chat and logs a deprecation warning; new configs should migrate to deepseek/deepseek-v4-flash. Also works in multi-channel mode.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 6,
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "DEEPSEEK_API_KEY=sk-xxxx",
            "LITELLM_MODEL=deepseek/deepseek-v4-flash",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
            {
                "label": "LLM 服务商配置速查",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/llm-providers.md",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "DEEPSEEK_API_KEYS": {
        "title": "DeepSeek API Keys (Multi)",
        "description": "Comma-separated DeepSeek API keys for load balancing. Takes priority over DEEPSEEK_API_KEY.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 7,
    },
    "TUSHARE_TOKEN": {
        "title": "Tushare Token",
        "description": "Token for Tushare Pro API. Must be provided to enable Tushare data source.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 21,
        "help_key": "settings.data_source.TUSHARE_TOKEN",
        "examples": [
            "TUSHARE_TOKEN=your_tushare_token",
        ],
        "docs": [
            {
                "label": "Tushare 股票列表指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/TUSHARE_STOCK_LIST_GUIDE.md",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "REALTIME_SOURCE_PRIORITY": {
        "title": "实时数据源优先级",
        "description": "按逗号分隔填写数据源调用顺序。系统默认顺序为：tencent、akshare_sina、efinance、akshare_em、tushare。",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "tencent,akshare_sina,efinance,akshare_em,tushare",
        "options": [],
        "validation": {},
        "display_order": 30,
        "help_key": "settings.data_source.REALTIME_SOURCE_PRIORITY",
        "examples": [
            "REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em",
        ],
        "docs": [
            {
                "label": "完整指南：数据源配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#数据源配置",
            },
        ],
        "warning_codes": ["provider_priority_order"],
    },
    "FIRECRAWL_API_KEY": {
        "help_key": "settings.data_source.search_api_keys",
        "examples": [
            "FIRECRAWL_API_KEY=fc-your_key_here",
        ],
        "docs": [
            {
                "label": "Firecrawl 文档",
                "href": "https://docs.firecrawl.dev/",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "TUSHARE": {
        "title": "Tushare",
        "description": "是否启用 Tushare 数据源（需填写 Token）。用于获取 A 股/指数的高频行情、财务数据与资金流向。",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 24,
    },
    "AKSHARE": {
        "title": "AkShare",
        "description": "是否启用 AkShare 数据源（提供 A 股/港股/美股历史行情与部分实时数据）。",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 25,
    },
    "YFINANCE": {
        "title": "YFinance",
        "description": "是否启用 Yahoo Finance 数据源（提供美股/港股/全球指数历史与实时行情）。",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 26,
    },
    "PYTDX": {
        "title": "Pytdx",
        "description": "是否启用 Pytdx（通达信）数据源（支持部分 A 股实时行情与历史数据）。",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 27,
    },
    "EFINANCE": {
        "title": "EFinance",
        "description": "是否启用 EFinance 数据源（东方财富接口，数据最全但高频调用易被封）。",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 28,
    },
    "BAOSTOCK": {
        "title": "BaoStock",
        "description": "是否启用 BaoStock 数据源（提供稳定的 A 股历史日线数据）。",
        "category": "data_source",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 29,
    },
    "FIRECRAWL_API_KEY": {
        "title": "Firecrawl API Key",
        "description": "Firecrawl API key used to scrape article URLs after a news URL is discovered.",
        "category": "data_source",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 54,
        "help_key": "settings.data_source.search_api_keys",
        "examples": [
            "FIRECRAWL_API_KEY=fc-your_key_here",
        ],
        "docs": [
            {
                "label": "Firecrawl 文档",
                "href": "https://docs.firecrawl.dev/",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "GEMINI_API_KEY": {
        "title": "Gemini API Key",
        "description": "Single API key for Gemini service (from https://aistudio.google.com).",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 10,
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "GEMINI_API_KEY=your_gemini_api_key",
            "LITELLM_MODEL=gemini/gemini-3.1-pro-preview",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
            {
                "label": "LLM 服务商配置速查",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/llm-providers.md",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "GEMINI_API_KEYS": {
        "title": "Gemini API Keys (Multi)",
        "description": "Comma-separated Gemini API keys for load balancing. Takes priority over GEMINI_API_KEY.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 11,
    },
    "GEMINI_MODEL": {
        "title": "Gemini Model",
        "description": "Gemini model name.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "gemini-3.1-pro-preview",
        "options": [],
        "validation": {},
        "display_order": 20,
    },
    "GEMINI_MODEL_FALLBACK": {
        "title": "Gemini Fallback Model",
        "description": "Fallback Gemini model name (used when LITELLM_FALLBACK_MODELS is not set and primary is Gemini).",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "gemini-3-flash-preview",
        "options": [],
        "validation": {},
        "display_order": 21,
    },
    "GEMINI_TEMPERATURE": {
        "title": "Gemini Temperature",
        "description": "Temperature in range [0.0, 2.0].",
        "category": "ai_model",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0.7",
        "options": [],
        "validation": {"min": 0.0, "max": 2.0},
        "display_order": 30,
    },
    "OPENAI_API_KEY": {
        "title": "OpenAI API Key",
        "description": "API key for OpenAI-compatible service.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 40,
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "OPENAI_API_KEY=sk-xxxx",
            "OPENAI_BASE_URL=https://api.example.com/v1",
            "LITELLM_MODEL=openai/gpt-5.5",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
            {
                "label": "LLM 服务商配置速查",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/llm-providers.md",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "OPENAI_API_KEYS": {
        "title": "OpenAI API Keys (Multi)",
        "description": "Comma-separated OpenAI-compatible API keys for load balancing. Takes priority over AIHUBMIX_KEY and OPENAI_API_KEY.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 41,
    },
    "OPENAI_BASE_URL": {
        "title": "OpenAI Base URL",
        "description": "Base URL for OpenAI-compatible endpoint.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 50,
        "help_key": "settings.ai_model.OPENAI_BASE_URL",
        "examples": [
            "OPENAI_BASE_URL=https://api.openai.com/v1",
            "OPENAI_BASE_URL=https://api.example.com/v1",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
            {
                "label": "LLM 服务商配置速查",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/llm-providers.md",
            },
        ],
        "warning_codes": ["base_url_must_match_provider"],
    },
    "OPENAI_MODEL": {
        "title": "OpenAI Model",
        "description": "Model name for OpenAI-compatible endpoint.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "gpt-5.5",
        "options": [],
        "validation": {},
        "display_order": 60,
    },
    "OPENAI_VISION_MODEL": {
        "title": "OpenAI Vision Model",
        "description": "Model for image extraction (some APIs e.g. DeepSeek lack vision). Leave empty to use OPENAI_MODEL.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 61,
    },
    "OPENAI_TEMPERATURE": {
        "title": "OpenAI Temperature",
        "description": "Temperature for OpenAI-compatible models in range [0.0, 2.0].",
        "category": "ai_model",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0.7",
        "options": [],
        "validation": {"min": 0.0, "max": 2.0},
        "display_order": 62,
    },
    "ANTHROPIC_API_KEY": {
        "title": "Anthropic API Key",
        "description": "Anthropic Claude API key (from https://console.anthropic.com).",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 35,
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "ANTHROPIC_API_KEY=sk-ant-xxxx",
            "LITELLM_MODEL=anthropic/claude-sonnet-4-6",
        ],
        "docs": [
            {
                "label": "LLM 配置指南",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
            },
            {
                "label": "LLM 服务商配置速查",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/llm-providers.md",
            },
        ],
        "warning_codes": ["secret_value"],
    },
    "ANTHROPIC_API_KEYS": {
        "title": "Anthropic API Keys (Multi)",
        "description": "Comma-separated Anthropic API keys for load balancing. Takes priority over ANTHROPIC_API_KEY.",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {"multi_value": True, "delimiter": ","},
        "display_order": 35,
    },
    "ANTHROPIC_MODEL": {
        "title": "Anthropic Model",
        "description": "Claude 模型名称（如 claude-sonnet-4-6）。",
        "category": "ai_model",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "claude-sonnet-4-6",
        "options": [],
        "validation": {},
        "display_order": 36,
    },
    "ANTHROPIC_TEMPERATURE": {
        "title": "Anthropic Temperature",
        "description": "温度参数，范围 [0.0, 1.0]。",
        "category": "ai_model",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "0.7",
        "options": [],
        "validation": {"min": 0.0, "max": 1.0},
        "display_order": 37,
    },
    "ANTHROPIC_MAX_TOKENS": {
        "title": "Anthropic Max Tokens",
        "description": "Anthropic API 响应最大 token 数（默认 8192）。",
        "category": "ai_model",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "8192",
        "options": [],
        "validation": {"min": 256, "max": 8192},
        "display_order": 38,
    },
    "HTTP_PROXY": {
        "title": "HTTP Proxy",
        "description": "Optional HTTP proxy endpoint.",
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 20,
        "help_key": "settings.system.HTTP_PROXY",
        "examples": [
            "HTTP_PROXY=http://127.0.0.1:7890",
            "HTTPS_PROXY=http://127.0.0.1:7890",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["network_scope"],
    },
    "LOG_LEVEL": {
        "title": "Log Level",
        "description": "Application log level.",
        "category": "system",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "INFO",
        "options": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        "validation": {"enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]},
        "display_order": 30,
        "help_key": "settings.system.LOG_LEVEL",
        "examples": [
            "LOG_LEVEL=INFO",
            "LOG_LEVEL=DEBUG",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": ["restart_required"],
    },
    "WEBUI_HOST": {
        "title": "Web UI Host",
        "description": "Host address for Web UI service binding.",
        "category": "system",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "127.0.0.1",
        "options": [],
        "validation": {},
        "display_order": 39,
        "help_key": "settings.system.WEBUI_HOST",
        "examples": [
            "WEBUI_HOST=127.0.0.1",
            "WEBUI_HOST=0.0.0.0",
        ],
        "docs": [
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/deploy-webui-cloud.md",
            },
            {
                "label": "完整指南：WebUI 与 API",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#webui-与-api-服务",
            },
        ],
        "warning_codes": ["public_bind_requires_auth", "restart_required"],
    },
    "WEBUI_PORT": {
        "title": "Web UI Port",
        "description": "Port for Web UI service.",
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "8000",
        "options": [],
        "validation": {"min": 1, "max": 65535},
        "display_order": 40,
        "help_key": "settings.system.WEBUI_PORT",
        "examples": [
            "WEBUI_PORT=8000",
            "WEBUI_PORT=18000",
        ],
        "docs": [
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/deploy-webui-cloud.md",
            },
            {
                "label": "完整指南：WebUI 与 API",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#webui-与-api-服务",
            },
        ],
        "warning_codes": ["port_mapping_required", "restart_required"],
    },
    "ADMIN_AUTH_ENABLED": {
        "title": "Admin Auth Enabled",
        "description": "Enable password protection for Web UI. The first visit initializes the admin password.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": False,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 41,
        "help_key": "settings.system.ADMIN_AUTH_ENABLED",
        "examples": [
            "ADMIN_AUTH_ENABLED=true",
            "python -m src.auth reset_password",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#其他配置",
            },
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/deploy-webui-cloud.md",
            },
        ],
        "warning_codes": ["public_webui_requires_auth", "auth_settings_endpoint_required"],
    },
    "TRUST_X_FORWARDED_FOR": {
        "title": "Trust X-Forwarded-For",
        "description": "Use X-Forwarded-For as the client IP behind one trusted reverse proxy.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 42,
        "help_key": "settings.system.TRUST_X_FORWARDED_FOR",
        "examples": [
            "TRUST_X_FORWARDED_FOR=false",
            "TRUST_X_FORWARDED_FOR=true",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#其他配置",
            },
            {
                "label": "云服务器访问 WebUI",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/deploy-webui-cloud.md",
            },
        ],
        "warning_codes": ["trusted_proxy_only"],
    },
    "TRADING_DAY_CHECK_ENABLED": {
        "title": "Trading Day Check",
        "description": "Skip analysis on non-trading days. Set to false or use --force-run to override.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 12,
        "help_key": "settings.system.TRADING_DAY_CHECK_ENABLED",
        "examples": [
            "TRADING_DAY_CHECK_ENABLED=true",
            "TRADING_DAY_CHECK_ENABLED=false",
        ],
        "docs": [
            {
                "label": "完整指南：其他配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#其他配置",
            },
        ],
        "warning_codes": ["force_run_override"],
    },
    "MAX_WORKERS": {
        "title": "Max Workers",
        "description": "Maximum concurrent analysis threads. Keep low to avoid API rate limits.",
        "category": "system",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "3",
        "options": [],
        "validation": {"min": 1, "max": 20},
        "display_order": 50,
        "help_key": "settings.system.MAX_WORKERS",
        "examples": [
            "MAX_WORKERS=3",
            "MAX_WORKERS=5",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "DEBUG": {
        "title": "Debug Mode",
        "description": "Enable debug mode with verbose logging.",
        "category": "system",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 55,
        "help_key": "settings.system.DEBUG",
        "examples": [
            "DEBUG=true",
            "DEBUG=false",
        ],
        "docs": [
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "BACKTEST_ENABLED": {
        "title": "Backtest Enabled",
        "description": "Whether backtest is enabled.",
        "category": "backtest",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 10,
        "help_key": "settings.backtest.BACKTEST_ENABLED",
        "examples": [
            "BACKTEST_ENABLED=true",
            "BACKTEST_ENABLED=false",
        ],
        "docs": [
            {
                "label": "完整指南：回测配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#回测功能",
            },
        ],
        "warning_codes": [],
    },
    "BACKTEST_EVAL_WINDOW_DAYS": {
        "title": "Backtest Eval Window Days",
        "description": "Backtest evaluation window in trading days.",
        "category": "backtest",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "10",
        "options": [],
        "validation": {"min": 1, "max": 365},
        "display_order": 20,
        "help_key": "settings.backtest.eval_params",
        "examples": [
            "BACKTEST_EVAL_WINDOW_DAYS=10",
            "BACKTEST_MIN_AGE_DAYS=14",
            "BACKTEST_NEUTRAL_BAND_PCT=2.0",
        ],
        "docs": [
            {
                "label": "完整指南：回测配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#回测功能",
            },
        ],
        "warning_codes": [],
    },
    "BACKTEST_MIN_AGE_DAYS": {
        "title": "Backtest Min Age Days",
        "description": "Only evaluate analysis records older than this threshold.",
        "category": "backtest",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "14",
        "options": [],
        "validation": {"min": 0, "max": 3650},
        "display_order": 30,
        "help_key": "settings.backtest.eval_params",
        "examples": [
            "BACKTEST_MIN_AGE_DAYS=14",
            "BACKTEST_EVAL_WINDOW_DAYS=10",
        ],
        "docs": [
            {
                "label": "完整指南：回测配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#回测功能",
            },
        ],
        "warning_codes": [],
    },
    "BACKTEST_ENGINE_VERSION": {
        "title": "Backtest Engine Version",
        "description": "Backtest engine version label.",
        "category": "backtest",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "v1",
        "options": [],
        "validation": {},
        "display_order": 40,
        "help_key": "settings.backtest.BACKTEST_ENGINE_VERSION",
        "examples": [
            "BACKTEST_ENGINE_VERSION=v1",
        ],
        "docs": [
            {
                "label": "完整指南：回测配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#回测功能",
            },
        ],
        "warning_codes": [],
    },
    "BACKTEST_NEUTRAL_BAND_PCT": {
        "title": "Backtest Neutral Band Pct",
        "description": "Neutral return band percentage for outcome labeling.",
        "category": "backtest",
        "data_type": "number",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "2.0",
        "options": [],
        "validation": {"min": 0.0, "max": 100.0},
        "display_order": 50,
        "help_key": "settings.backtest.eval_params",
        "examples": [
            "BACKTEST_NEUTRAL_BAND_PCT=2.0",
            "BACKTEST_EVAL_WINDOW_DAYS=10",
        ],
        "docs": [
            {
                "label": "完整指南：回测配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#回测功能",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_MODE": {
        "title": "Agent Mode",
        "description": "Enable ReAct Agent for stock analysis.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 10,
        "help_key": "settings.agent.AGENT_MODE",
        "examples": [
            "AGENT_MODE=true",
            "AGENT_MODE=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_MAX_STEPS": {
        "title": "Agent Max Steps",
        "description": f"Maximum reasoning-step limit for Agent mode. At the default ({AGENT_MAX_STEPS_DEFAULT}), each sub-agent keeps its own preset. When raised above {AGENT_MAX_STEPS_DEFAULT}, all sub-agents adopt this value. When lowered below a sub-agent's preset, that sub-agent is capped at this value.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(AGENT_MAX_STEPS_DEFAULT),
        "options": [],
        "validation": {"min": 1, "max": 50},
        "display_order": 20,
        "help_key": "settings.agent.AGENT_MAX_STEPS",
        "examples": [
            f"AGENT_MAX_STEPS={AGENT_MAX_STEPS_DEFAULT}",
            "AGENT_MAX_STEPS=25",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_SKILLS": {
        "title": "Agent Strategies",
        "description": "Comma-separated list of active agent strategy skills. Leave empty to use the primary default strategy skill declared in metadata (built-in default: bull_trend). When set to specific skills (not 'all'), scheduled tasks will automatically use the Agent pipeline.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {},
        "display_order": 30,
        "help_key": "settings.agent.AGENT_SKILLS",
        "examples": [
            "AGENT_SKILLS=",
            "AGENT_SKILLS=bull_trend,mean_reversion",
            "AGENT_SKILLS=all",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_SKILL_DIR": {
        "title": "Agent Strategy Dir",
        "description": "Directory containing agent strategy-skill definition files (YAML or SKILL.md bundles).",
        "category": "agent",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "strategies",
        "options": [],
        "validation": {},
        "display_order": 40,
        "help_key": "settings.agent.AGENT_SKILL_DIR",
        "examples": [
            "AGENT_SKILL_DIR=strategies",
            "AGENT_SKILL_DIR=my_strategies",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_NL_ROUTING": {
        "title": "Agent NL Routing",
        "description": "Enable natural-language routing in bot dispatcher. When on, high-confidence stock queries in private chat (or @mentions) are routed to the agent even without an explicit command.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 50,
        "help_key": "settings.agent.AGENT_NL_ROUTING",
        "examples": [
            "AGENT_NL_ROUTING=true",
            "AGENT_NL_ROUTING=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_ARCH": {
        "title": "Agent Architecture",
        "description": "Agent execution architecture. 'single' uses the classic ReAct executor; 'multi' uses the orchestrator pipeline with specialised sub-agents.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "single",
        "options": [
            {"label": "Single Agent", "value": "single"},
            {"label": "Multi Agent (Orchestrator)", "value": "multi"},
        ],
        "validation": {},
        "display_order": 60,
        "help_key": "settings.agent.AGENT_ARCH",
        "examples": [
            "AGENT_ARCH=single",
            "AGENT_ARCH=multi",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_ORCHESTRATOR_MODE": {
        "title": "Orchestrator Mode",
        "description": "Pipeline mode when AGENT_ARCH=multi. 'quick' (tech→decision), 'standard' (tech→intel→decision), 'full' (tech→intel→risk→decision), 'specialist' (full + per-strategy specialist agents).",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "standard",
        "options": [
            {"label": "Quick", "value": "quick"},
            {"label": "Standard", "value": "standard"},
            {"label": "Full", "value": "full"},
            {"label": "Specialist", "value": "specialist"},
        ],
        "validation": {"enum": ["quick", "standard", "full", "specialist", "strategy", "skill"]},
        "display_order": 61,
        "help_key": "settings.agent.AGENT_ORCHESTRATOR_MODE",
        "examples": [
            "AGENT_ORCHESTRATOR_MODE=standard",
            "AGENT_ORCHESTRATOR_MODE=full",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_ORCHESTRATOR_TIMEOUT_S": {
        "title": "Agent Timeout",
        "description": "Shared timeout budget in seconds for Agent execution. Single-agent runs use it as the overall ReAct loop budget; multi-agent mode uses it as the cooperative pipeline budget. Set to 0 to disable.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "600",
        "options": [],
        "validation": {"min": 0, "max": 3600},
        "display_order": 62,
        "help_key": "settings.agent.AGENT_ORCHESTRATOR_TIMEOUT_S",
        "examples": [
            "AGENT_ORCHESTRATOR_TIMEOUT_S=600",
            "AGENT_ORCHESTRATOR_TIMEOUT_S=0",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_RISK_OVERRIDE": {
        "title": "Risk Agent Override",
        "description": "Allow the risk agent to veto buy signals when critical risk flags are detected.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 63,
        "help_key": "settings.agent.AGENT_RISK_OVERRIDE",
        "examples": [
            "AGENT_RISK_OVERRIDE=true",
            "AGENT_RISK_OVERRIDE=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_DEEP_RESEARCH_BUDGET": {
        "title": "Deep Research Token Budget",
        "description": "Maximum token budget for Deep Research planning, follow-up research, and final synthesis.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "30000",
        "options": [],
        "validation": {"min": 5000, "max": 100000},
        "display_order": 64,
        "help_key": "settings.agent.DEEP_RESEARCH",
        "examples": [
            "AGENT_DEEP_RESEARCH_BUDGET=30000",
            "AGENT_DEEP_RESEARCH_BUDGET=50000",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_DEEP_RESEARCH_TIMEOUT": {
        "title": "Deep Research Timeout",
        "description": "Maximum seconds allowed for a Deep Research request before returning a timeout response.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "180",
        "options": [],
        "validation": {"min": 30, "max": 600},
        "display_order": 65,
        "help_key": "settings.agent.DEEP_RESEARCH",
        "examples": [
            "AGENT_DEEP_RESEARCH_TIMEOUT=180",
            "AGENT_DEEP_RESEARCH_TIMEOUT=300",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_MEMORY_ENABLED": {
        "title": "Agent Memory",
        "description": "Enable the memory & calibration system. Tracks prediction accuracy and adjusts agent confidence over time.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 66,
        "help_key": "settings.agent.AGENT_MEMORY_ENABLED",
        "examples": [
            "AGENT_MEMORY_ENABLED=true",
            "AGENT_MEMORY_ENABLED=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_SKILL_AUTOWEIGHT": {
        "title": "Auto-Weight Strategies",
        "description": "Automatically weight strategy-skill opinions by their historical backtest performance.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "true",
        "options": [],
        "validation": {},
        "display_order": 67,
        "help_key": "settings.agent.AGENT_SKILL_AUTOWEIGHT",
        "examples": [
            "AGENT_SKILL_AUTOWEIGHT=true",
            "AGENT_SKILL_AUTOWEIGHT=false",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_SKILL_ROUTING": {
        "title": "Strategy Routing",
        "description": "Strategy-skill selection mode. 'auto' detects market regime and picks relevant skills; 'manual' uses AGENT_SKILLS list only.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "auto",
        "options": [
            {"label": "Auto (Regime-based)", "value": "auto"},
            {"label": "Manual (Use AGENT_SKILLS)", "value": "manual"},
        ],
        "validation": {},
        "display_order": 68,
        "help_key": "settings.agent.AGENT_SKILL_ROUTING",
        "examples": [
            "AGENT_SKILL_ROUTING=auto",
            "AGENT_SKILL_ROUTING=manual",
        ],
        "docs": [
            {
                "label": "完整指南：Agent 配置",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_CONTEXT_COMPRESSION_ENABLED": {
        "title": "Agent Context Compression",
        "description": "Enable rolling compression of visible Agent chat history. Default is off to preserve existing behavior.",
        "category": "agent",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 72,
        "help_key": "settings.agent.context_compression",
        "examples": [
            "AGENT_CONTEXT_COMPRESSION_ENABLED=false",
            "AGENT_CONTEXT_COMPRESSION_ENABLED=true",
        ],
        "docs": [
            {
                "label": "LLM 配置指南：问股可见对话上下文压缩",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md#问股可见对话上下文压缩",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_CONTEXT_COMPRESSION_PROFILE": {
        "title": "Context Compression Profile",
        "description": "Preset for visible chat history compression. Trigger/protected-turn fields can be left empty to follow the selected profile.",
        "category": "agent",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "balanced",
        "options": [
            {"label": "成本优先", "value": "cost"},
            {"label": "均衡推荐", "value": "balanced"},
            {"label": "长上下文原文优先", "value": "long_context_raw_first"},
        ],
        "validation": {"enum": list(AGENT_CONTEXT_COMPRESSION_PROFILES.keys())},
        "display_order": 73,
        "help_key": "settings.agent.context_compression",
        "examples": [
            "AGENT_CONTEXT_COMPRESSION_PROFILE=balanced",
            "AGENT_CONTEXT_COMPRESSION_PROFILE=cost",
            "AGENT_CONTEXT_COMPRESSION_PROFILE=long_context_raw_first",
        ],
        "docs": [
            {
                "label": "LLM 配置指南：问股可见对话上下文压缩",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md#问股可见对话上下文压缩",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS": {
        "title": "Context Compression Trigger Tokens",
        "description": "Token threshold for visible chat history compression. Leave empty to follow the selected compression profile preset.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"min": 1000, "max": 200000},
        "display_order": 74,
        "help_key": "settings.agent.context_compression",
        "examples": [
            "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS=",
            "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS=12000",
        ],
        "docs": [
            {
                "label": "LLM 配置指南：问股可见对话上下文压缩",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md#问股可见对话上下文压缩",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
    "AGENT_CONTEXT_PROTECTED_TURNS": {
        "title": "Context Protected Turns",
        "description": "Recent user turns preserved verbatim during visible chat history compression. Leave empty to follow the selected compression profile preset.",
        "category": "agent",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"min": 1, "max": 20},
        "display_order": 75,
        "help_key": "settings.agent.context_compression",
        "examples": [
            "AGENT_CONTEXT_PROTECTED_TURNS=",
            "AGENT_CONTEXT_PROTECTED_TURNS=4",
        ],
        "docs": [
            {
                "label": "LLM 配置指南：问股可见对话上下文压缩",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md#问股可见对话上下文压缩",
            },
            {
                "label": "完整指南：环境变量完整列表",
                "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
            },
        ],
        "warning_codes": [],
    },
}

_DOC_FULL_GUIDE_ENV = [
    {
        "label": "完整指南：环境变量完整列表",
        "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#环境变量完整列表",
    },
]

_DOC_FULL_GUIDE_SEARCH = [
    {
        "label": "完整指南：搜索服务配置",
        "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#搜索服务配置",
    },
]

_DOC_FULL_GUIDE_DATA_SOURCE = [
    {
        "label": "完整指南：数据源配置",
        "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/full-guide.md#数据源配置",
    },
]

_DOC_LLM_CONFIG = [
    {
        "label": "LLM 配置指南",
        "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md",
    },
    {
        "label": "LLM 服务商配置速查",
        "href": "https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/llm-providers.md",
    },
]

_FIELD_HELP_METADATA: Dict[str, Dict[str, Any]] = {
    "DEEPSEEK_API_KEYS": {
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "DEEPSEEK_API_KEYS=sk-xxxx,sk-yyyy",
            "LITELLM_MODEL=deepseek/deepseek-v4-flash",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "GEMINI_API_KEYS": {
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "GEMINI_API_KEYS=your_gemini_key_1,your_gemini_key_2",
            "LITELLM_MODEL=gemini/gemini-3.1-pro-preview",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "GEMINI_MODEL": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "GEMINI_MODEL=gemini-3.1-pro-preview",
            "LITELLM_MODEL=gemini/gemini-3.1-pro-preview",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "GEMINI_MODEL_FALLBACK": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "GEMINI_MODEL_FALLBACK=gemini-3-flash-preview",
            "LITELLM_FALLBACK_MODELS=gemini/gemini-3-flash-preview",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "GEMINI_TEMPERATURE": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "GEMINI_TEMPERATURE=0.7",
            "LLM_TEMPERATURE=0.7",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "OPENAI_API_KEYS": {
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "OPENAI_API_KEYS=sk-xxxx,sk-yyyy",
            "OPENAI_BASE_URL=https://api.example.com/v1",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "OPENAI_MODEL": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "OPENAI_MODEL=gpt-5.5",
            "LITELLM_MODEL=openai/gpt-5.5",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "OPENAI_VISION_MODEL": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "OPENAI_VISION_MODEL=gpt-5.5",
            "VISION_MODEL=openai/gpt-5.5",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "OPENAI_TEMPERATURE": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "OPENAI_TEMPERATURE=0.7",
            "LLM_TEMPERATURE=0.7",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "ANTHROPIC_API_KEYS": {
        "help_key": "settings.ai_model.provider_keys",
        "examples": [
            "ANTHROPIC_API_KEYS=sk-ant-xxxx,sk-ant-yyyy",
            "LITELLM_MODEL=anthropic/claude-sonnet-4-6",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["secret_value", "comma_separated_keys"],
    },
    "ANTHROPIC_MODEL": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "ANTHROPIC_MODEL=claude-sonnet-4-6",
            "LITELLM_MODEL=anthropic/claude-sonnet-4-6",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "ANTHROPIC_TEMPERATURE": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "ANTHROPIC_TEMPERATURE=0.7",
            "LLM_TEMPERATURE=0.7",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
    "ANTHROPIC_MAX_TOKENS": {
        "help_key": "settings.ai_model.legacy_provider_params",
        "examples": [
            "ANTHROPIC_MAX_TOKENS=8192",
        ],
        "docs": _DOC_LLM_CONFIG,
        "warning_codes": ["legacy_provider_setting"],
    },
}


def get_category_definitions() -> List[Dict[str, Any]]:
    """Return deep-copied category metadata."""
    return deepcopy(_CATEGORY_DEFINITIONS)


def get_registered_field_keys() -> List[str]:
    """Return all explicitly registered keys."""
    return list(_FIELD_DEFINITIONS.keys())


def _extract_option_values(options: List[Any]) -> List[str]:
    """Extract canonical option values from string/object style select options."""
    values: List[str] = []
    for option in options:
        if isinstance(option, str):
            values.append(option)
            continue
        if isinstance(option, dict):
            value = option.get("value")
            if isinstance(value, str) and value:
                values.append(value)
    return values


def get_field_definition(key: str, value_hint: Optional[str] = None) -> Dict[str, Any]:
    """Return field definition for key, including inferred fallback metadata."""
    key_upper = key.upper()
    if key_upper in _FIELD_DEFINITIONS:
        field = deepcopy(_FIELD_DEFINITIONS[key_upper])
        if key_upper in _FIELD_HELP_METADATA:
            field.update(deepcopy(_FIELD_HELP_METADATA[key_upper]))
        field["key"] = key_upper
        validation = deepcopy(field.get("validation") or {})
        option_values = _extract_option_values(field.get("options", []))
        if field.get("ui_control") == "select" and option_values and "enum" not in validation:
            validation["enum"] = option_values
        field["validation"] = validation
        return field

    category = _infer_category(key_upper)
    data_type = _infer_data_type(key_upper, value_hint)
    field = {
        "key": key_upper,
        "title": key_upper.replace("_", " ").title(),
        "description": "Auto-inferred field metadata.",
        "category": category,
        "data_type": data_type,
        "ui_control": _infer_ui_control(data_type, key_upper),
        "is_sensitive": _is_sensitive_key(key_upper),
        "is_required": False,
        "is_editable": True,
        "default_value": None,
        "options": [],
        "validation": {},
        "display_order": 9000,
    }
    return field


def build_schema_response() -> Dict[str, Any]:
    """Build schema payload grouped by category."""
    category_map: Dict[str, Dict[str, Any]] = {}
    for category in get_category_definitions():
        category_map[category["category"]] = {**category, "fields": []}

    for key in sorted(_FIELD_DEFINITIONS.keys()):
        field = get_field_definition(key)
        category_map[field["category"]]["fields"].append(field)

    categories = sorted(category_map.values(), key=lambda item: item["display_order"])
    for category in categories:
        category["fields"] = sorted(
            category["fields"],
            key=lambda item: (item.get("display_order", 9999), item["key"]),
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "categories": categories,
    }


def _is_sensitive_key(key: str) -> bool:
    markers = ("KEY", "TOKEN", "SECRET", "PASSWORD")
    return any(marker in key for marker in markers)


def _infer_category(key: str) -> str:
    if key.startswith("BACKTEST_"):
        return "backtest"
    if key.startswith(("GEMINI_", "OPENAI_", "ANTHROPIC_", "LITELLM_", "AIHUBMIX_", "DEEPSEEK_", "LLM_")):
        return "ai_model"
    if key.endswith("_PRIORITY") or key.startswith(
        (
            "TUSHARE",
            "TICKFLOW",
            "AKSHARE",
            "EFINANCE",
            "PYTDX",
            "BAOSTOCK",
            "YFINANCE",
            "SERPAPI",
            "BRAVE",
            "BIAS_",
        )
    ):
        return "data_source"
    if key.startswith(("LOG_", "SCHEDULE_", "WEBUI_", "HTTP_", "HTTPS_", "MAX_", "DEBUG", "MARKET_REVIEW_", "TRADING_DAY_")):
        return "system"
    return "uncategorized"


def _infer_data_type(key: str, value_hint: Optional[str]) -> str:
    if key.endswith("_TIME"):
        return "time"
    if value_hint is None:
        return "string"

    lowered = value_hint.strip().lower()
    if lowered in {"true", "false"}:
        return "boolean"

    try:
        int(value_hint)
        return "integer"
    except (TypeError, ValueError):
        pass

    try:
        float(value_hint)
        return "number"
    except (TypeError, ValueError):
        pass

    return "string"


def _infer_ui_control(data_type: str, key: str) -> str:
    if _is_sensitive_key(key):
        return "password"
    if data_type == "boolean":
        return "switch"
    if data_type in {"integer", "number"}:
        return "number"
    if data_type == "time":
        return "time"
    if data_type == "array":
        return "textarea"
    return "text"
