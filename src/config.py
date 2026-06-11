# -*- coding: utf-8 -*-
"""
===================================
A股自选股智能分析系统 - 配置管理模块
===================================

职责：
1. 使用单例模式管理全局配置
2. 从 .env 文件加载敏感配置
3. 提供类型安全的配置访问接口
"""

import json
import logging
import os
import re
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import unquote, urlparse
from dotenv import load_dotenv, dotenv_values
from dataclasses import dataclass, field

from src.report_language import (
    is_supported_report_language_value,
    normalize_report_language,
)
from src.llm import generation_params as llm_generation_params

logger = logging.getLogger(__name__)


@dataclass
class ConfigIssue:
    """Structured configuration validation issue with a severity level.

    Attributes:
        severity: One of "error", "warning", or "info".
        message:  Human-readable description of the issue.
        field:    The environment variable / config field name most relevant to
                  this issue (empty string when not applicable).
    """

    severity: Literal["error", "warning", "info"]
    message: str
    field: str = ""

    def __str__(self) -> str:  # noqa: D105
        return self.message


_MANAGED_LITELLM_KEY_PROVIDERS = {"gemini", "vertex_ai", "anthropic", "openai", "deepseek"}
SUPPORTED_LLM_CHANNEL_PROTOCOLS = ("openai", "anthropic", "gemini", "vertex_ai", "deepseek", "ollama")
_FALSEY_ENV_VALUES = {"0", "false", "no", "off"}




AGENT_MAX_STEPS_DEFAULT = 10
FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT = 8.0


@dataclass(frozen=True)
class AgentContextCompressionPreset:
    """Preset values for visible chat history compression."""

    trigger_tokens: int
    protected_turns: int
    summary_target_tokens: int
    # P1 reserves this budget for future prompt-size controls; it is not
    # enforced by the current rolling-summary state table.
    history_budget_tokens: int


AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE = "balanced"
AGENT_CONTEXT_COMPRESSION_PROFILES: Dict[str, AgentContextCompressionPreset] = {
    "cost": AgentContextCompressionPreset(
        trigger_tokens=6000,
        protected_turns=2,
        summary_target_tokens=900,
        history_budget_tokens=4000,
    ),
    "balanced": AgentContextCompressionPreset(
        trigger_tokens=12000,
        protected_turns=4,
        summary_target_tokens=1500,
        history_budget_tokens=8000,
    ),
    "long_context_raw_first": AgentContextCompressionPreset(
        trigger_tokens=24000,
        protected_turns=6,
        summary_target_tokens=2600,
        history_budget_tokens=14000,
    ),
}


def parse_env_bool(value: Optional[str], default: bool = False) -> bool:
    """Parse common truthy/falsey environment-style values."""
    if value is None:
        return default
    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized not in _FALSEY_ENV_VALUES


def parse_env_int(
    value: Optional[str],
    default: int,
    *,
    field_name: str,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """Parse an integer env value with warning + fallback semantics."""
    raw_value = value
    if raw_value is None or not str(raw_value).strip():
        parsed = int(default)
    else:
        try:
            parsed = int(str(raw_value).strip())
        except (TypeError, ValueError):
            logger.warning(
                "%s=%r is not a valid integer; falling back to %s",
                field_name,
                raw_value,
                default,
            )
            parsed = int(default)

    if minimum is not None and parsed < minimum:
        logger.warning(
            "%s=%r is below minimum %s; clamping to %s",
            field_name,
            parsed,
            minimum,
            minimum,
        )
        parsed = minimum
    if maximum is not None and parsed > maximum:
        logger.warning(
            "%s=%r is above maximum %s; clamping to %s",
            field_name,
            parsed,
            maximum,
            maximum,
        )
        parsed = maximum
    return parsed


def parse_env_float(
    value: Optional[str],
    default: float,
    *,
    field_name: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    """Parse a float env value with warning + fallback semantics."""
    raw_value = value
    if raw_value is None or not str(raw_value).strip():
        parsed = float(default)
    else:
        try:
            parsed = float(str(raw_value).strip())
        except (TypeError, ValueError):
            logger.warning(
                "%s=%r is not a valid number; falling back to %s",
                field_name,
                raw_value,
                default,
            )
            parsed = float(default)

    if minimum is not None and parsed < minimum:
        logger.warning(
            "%s=%r is below minimum %s; clamping to %s",
            field_name,
            parsed,
            minimum,
            minimum,
        )
        parsed = minimum
    if maximum is not None and parsed > maximum:
        logger.warning(
            "%s=%r is above maximum %s; clamping to %s",
            field_name,
            parsed,
            maximum,
            maximum,
        )
        parsed = maximum
    return parsed


def normalize_agent_context_compression_profile(value: Optional[str]) -> str:
    """Normalize visible-chat context compression profile values."""
    candidate = (value or AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE).strip().lower()
    if candidate in AGENT_CONTEXT_COMPRESSION_PROFILES:
        return candidate
    logger.warning(
        "Invalid AGENT_CONTEXT_COMPRESSION_PROFILE=%r; falling back to %s",
        value,
        AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE,
    )
    return AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE


def get_agent_context_compression_preset(profile: Optional[str]) -> AgentContextCompressionPreset:
    """Return the preset for a normalized profile, falling back to balanced."""
    normalized = normalize_agent_context_compression_profile(profile)
    return AGENT_CONTEXT_COMPRESSION_PROFILES[normalized]


def parse_agent_context_compression_int(
    value: Optional[str],
    default: int,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    """Parse compression integers; empty/invalid/out-of-range values follow preset defaults."""
    raw_value = value
    if raw_value is None or not str(raw_value).strip():
        return int(default)
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        logger.warning(
            "%s=%r is not a valid integer; falling back to preset default %s",
            field_name,
            raw_value,
            default,
        )
        return int(default)
    if parsed < minimum or parsed > maximum:
        logger.warning(
            "%s=%r is outside supported range [%s, %s]; falling back to preset default %s",
            field_name,
            parsed,
            minimum,
            maximum,
            default,
        )
        return int(default)
    return parsed


def canonicalize_llm_channel_protocol(value: Optional[str]) -> str:
    """Normalize a protocol label into a LiteLLM provider identifier."""
    candidate = (value or "").strip().lower().replace("-", "_")
    aliases = {
        "openai_compatible": "openai",
        "openai_compat": "openai",
        "claude": "anthropic",
        "google": "gemini",
        "vertex": "vertex_ai",
        "vertexai": "vertex_ai",
    }
    return aliases.get(candidate, candidate)


def resolve_llm_channel_protocol(
    protocol: Optional[str],
    *,
    base_url: Optional[str] = None,
    models: Optional[List[str]] = None,
    channel_name: Optional[str] = None,
) -> str:
    """Resolve the effective protocol for a channel."""
    explicit = canonicalize_llm_channel_protocol(protocol)
    if explicit in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
        return explicit

    for model in models or []:
        if "/" not in model:
            continue
        prefix = canonicalize_llm_channel_protocol(model.split("/", 1)[0])
        if prefix in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
            return prefix

    # Infer from channel name (e.g. "deepseek" -> deepseek, "gemini" -> gemini)
    if channel_name:
        name_protocol = canonicalize_llm_channel_protocol(channel_name)
        if name_protocol in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
            return name_protocol

    if base_url:
        parsed = urlparse(base_url)
        if parsed.hostname in {"127.0.0.1", "localhost", "0.0.0.0"}:
            # Default to openai for local servers (vLLM, LM Studio, LocalAI, etc.).
            # Ollama users should set PROTOCOL=ollama explicitly or name the channel "ollama".
            return "openai"
        return "openai"

    return ""


def channel_allows_empty_api_key(protocol: Optional[str], base_url: Optional[str]) -> bool:
    """Return True when a channel can run without an API key."""
    resolved_protocol = resolve_llm_channel_protocol(protocol, base_url=base_url)
    if resolved_protocol == "ollama":
        return True
    parsed = urlparse(base_url or "")
    return parsed.hostname in {"127.0.0.1", "localhost", "0.0.0.0"}


def normalize_llm_channel_model(model: str, protocol: Optional[str], base_url: Optional[str] = None) -> str:
    """Attach a provider prefix when the model omits it."""
    normalized_model = model.strip()
    if not normalized_model:
        return normalized_model

    resolved_protocol = resolve_llm_channel_protocol(protocol, base_url=base_url, models=[normalized_model])

    if "/" in normalized_model:
        # The model already has a slash, e.g. 'deepseek-ai/DeepSeek-V3'.
        # Check if the prefix is a known LiteLLM provider; if so, keep it.
        # Otherwise (e.g. HuggingFace-style IDs on SiliconFlow), prepend
        # the resolved protocol so LiteLLM routes via the correct handler.
        raw_prefix, remainder = normalized_model.split("/", 1)
        prefix = raw_prefix.lower()
        canonical_prefix = canonicalize_llm_channel_protocol(prefix)
        known_providers = _MANAGED_LITELLM_KEY_PROVIDERS | set(SUPPORTED_LLM_CHANNEL_PROTOCOLS) | {
            "minimax",
            "cohere", "huggingface", "bedrock", "sagemaker", "azure",
            "replicate", "together_ai", "palm", "text-completion-openai",
            "command-r", "groq", "cerebras", "fireworks_ai", "friendliai",
        }
        if prefix in known_providers:
            return normalized_model
        if canonical_prefix in known_providers:
            return f"{canonical_prefix}/{remainder}"
        # Not a real provider prefix — add one so LiteLLM routes correctly.
        if resolved_protocol:
            return f"{resolved_protocol}/{normalized_model}"
        return normalized_model

    if not resolved_protocol:
        return normalized_model
    return f"{resolved_protocol}/{normalized_model}"


def get_configured_llm_models(model_list: List[Dict[str, Any]]) -> List[str]:
    """Return non-legacy model names declared in Router model_list order.

    Uses the top-level ``model_name`` (the routing alias that users set in
    LITELLM_MODEL) rather than ``litellm_params.model`` (the wire-level
    model identifier).  For channel-built entries both are identical, but
    YAML configs may define a friendly alias that differs from the
    underlying provider/model path.
    """
    models: List[str] = []
    seen: set = set()
    for entry in model_list or []:
        # Prefer top-level model_name (router routing key); fall back to
        # litellm_params.model for entries that omit it.
        name = str(entry.get("model_name") or "").strip()
        if not name:
            params = entry.get("litellm_params", {}) or {}
            name = str(params.get("model") or "").strip()
        if not name or name.startswith("__legacy_") or name in seen:
            continue
        seen.add(name)
        models.append(name)
    return models


def resolve_litellm_wire_model(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Resolve a router alias to its underlying LiteLLM wire model."""
    return llm_generation_params.resolve_litellm_wire_model(model, model_list)


def resolve_litellm_thinking_enabled(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> Optional[bool]:
    """Resolve whether the outgoing LiteLLM request explicitly enables thinking."""
    return llm_generation_params.resolve_litellm_thinking_enabled(
        model,
        model_list=model_list,
        request_overrides=request_overrides,
    )


def get_fixed_litellm_temperature(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """Return a provider-mandated temperature for known strict models."""
    return llm_generation_params.get_fixed_litellm_temperature(
        model,
        model_list=model_list,
        request_overrides=request_overrides,
    )


def normalize_litellm_temperature(
    model: str,
    temperature: Optional[float],
    *,
    default: float = 0.7,
    model_list: Optional[List[Dict[str, Any]]] = None,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> float:
    """Normalize temperature before sending a LiteLLM request."""
    return llm_generation_params.normalize_litellm_temperature(
        model,
        temperature,
        default=default,
        model_list=model_list,
        request_overrides=request_overrides,
    )


def resolve_unified_llm_temperature(model: str) -> float:
    """Resolve the raw unified LLM temperature with backward-compatible fallbacks."""
    llm_temperature_raw = os.getenv("LLM_TEMPERATURE")
    if llm_temperature_raw and llm_temperature_raw.strip():
        try:
            return float(llm_temperature_raw)
        except (ValueError, TypeError):
            pass

    provider_temperature_env = {
        "gemini": "GEMINI_TEMPERATURE",
        "vertex_ai": "GEMINI_TEMPERATURE",
        "anthropic": "ANTHROPIC_TEMPERATURE",
        "openai": "OPENAI_TEMPERATURE",
        "deepseek": "OPENAI_TEMPERATURE",
    }
    preferred_env = provider_temperature_env.get(_get_litellm_provider(model))
    if preferred_env:
        preferred_value = os.getenv(preferred_env)
        if preferred_value and preferred_value.strip():
            try:
                return float(preferred_value)
            except (ValueError, TypeError):
                pass

    for env_name in ("GEMINI_TEMPERATURE", "ANTHROPIC_TEMPERATURE", "OPENAI_TEMPERATURE"):
        env_value = os.getenv(env_name)
        if env_value and env_value.strip():
            try:
                return float(env_value)
            except (ValueError, TypeError):
                continue

    return 0.7


def _get_litellm_provider(model: str) -> str:
    """Extract the LiteLLM provider prefix from a model string."""
    if not model:
        return ""
    if "/" in model:
        return model.split("/", 1)[0]
    return "openai"


def _uses_direct_env_provider(model: str) -> bool:
    """Whether runtime handles the model via direct litellm env/provider resolution."""
    provider = _get_litellm_provider(model)
    return bool(provider) and provider not in _MANAGED_LITELLM_KEY_PROVIDERS


def normalize_agent_litellm_model(
    model: str,
    configured_models: Optional[set[str]] = None,
) -> str:
    """Normalize AGENT_LITELLM_MODEL while preserving configured router aliases."""
    normalized_model = (model or "").strip()
    if not normalized_model:
        return ""
    if "/" not in normalized_model:
        if configured_models and normalized_model in configured_models:
            return normalized_model
        return f"openai/{normalized_model}"
    return normalized_model


def get_effective_agent_primary_model(config: "Config") -> str:
    """Return the effective Agent primary model with fallback inheritance."""
    configured_router_models = set(
        get_configured_llm_models(getattr(config, "llm_model_list", []) or [])
    )
    configured_agent_model = normalize_agent_litellm_model(
        getattr(config, "agent_litellm_model", ""),
        configured_models=configured_router_models,
    )
    if configured_agent_model:
        if (
            configured_router_models
            and configured_agent_model not in configured_router_models
            and not _uses_direct_env_provider(configured_agent_model)
        ):
            return (getattr(config, "litellm_model", "") or "").strip()
        return configured_agent_model
    return (getattr(config, "litellm_model", "") or "").strip()


def get_effective_agent_models_to_try(config: "Config") -> List[str]:
    """Return Agent model try-order: primary + global fallbacks (deduped)."""
    configured_router_models = set(
        get_configured_llm_models(getattr(config, "llm_model_list", []) or [])
    )
    raw_models = [get_effective_agent_primary_model(config)] + (
        getattr(config, "litellm_fallback_models", []) or []
    )
    seen = set()
    ordered_models: List[str] = []
    for model in raw_models:
        normalized_model = (model or "").strip()
        if not normalized_model:
            continue
        dedupe_key = normalize_agent_litellm_model(
            normalized_model,
            configured_models=configured_router_models,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        ordered_models.append(normalized_model)
    return ordered_models


def setup_env(override: bool = False):
    """
    Initialize environment variables from .env file.

    Args:
        override: If True, overwrite existing environment variables with values
                  from .env file. Set to True when reloading config after updates.
                  Default is False to preserve behavior on initial load where
                  system environment variables take precedence.
    """
    Config._capture_bootstrap_runtime_env_overrides()
    # src/config.py -> src/ -> root
    env_file = os.getenv("ENV_FILE")
    if env_file:
        env_path = Path(env_file)
    else:
        env_path = Path(__file__).parent.parent / '.env'
    load_dotenv(dotenv_path=env_path, override=override)


@dataclass
class Config:
    """
    系统配置类 - 单例模式
    
    设计说明：
    - 使用 dataclass 简化配置属性定义
    - 所有配置项从环境变量读取，支持默认值
    - 类方法 get_instance() 实现单例访问
    """
    
    # === 飞书云文档配置 ===
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    feishu_folder_token: Optional[str] = None  # 目标文件夹 Token

    # === 数据源 API Token ===
    tushare_token: Optional[str] = None
    tickflow_api_key: Optional[str] = None

    # === AI 分析配置 ===
    # LiteLLM unified model config (provider/model format, e.g. gemini/gemini-3.1-pro-preview)
    litellm_model: str = ""  # Primary model; must include provider prefix when set explicitly
    litellm_fallback_models: List[str] = field(default_factory=list)  # Cross-model fallback list

    # Unified temperature for all LLM calls (LLM_TEMPERATURE); legacy per-provider temps are fallback only
    llm_temperature: float = 0.7

    # --- Multi-channel LLM config ---
    # Internal metadata: which config layer actually produced llm_model_list
    llm_models_source: str = "legacy_env"
    # LLM_CHANNELS: list of channel dicts, each with name/base_url/api_keys/models
    llm_channels: List[Dict[str, Any]] = field(default_factory=list)
    # Pre-built LiteLLM Router model_list (populated from channels, YAML, or legacy keys)
    llm_model_list: List[Dict[str, Any]] = field(default_factory=list)

    # Multi-key support: each list is parsed from *_API_KEYS (comma-separated) with single-key fallback
    gemini_api_keys: List[str] = field(default_factory=list)
    anthropic_api_keys: List[str] = field(default_factory=list)
    openai_api_keys: List[str] = field(default_factory=list)
    deepseek_api_keys: List[str] = field(default_factory=list)

    # Legacy single-key fields (kept for backward compatibility; gemini_api_keys[0] when set)
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.1-pro-preview"  # 主模型
    gemini_model_fallback: str = "gemini-3-flash-preview"  # 备选模型
    gemini_temperature: float = 0.7  # 温度参数（0.0-2.0，控制输出随机性，默认0.7）

    # Gemini API 请求配置（防止 429 限流）
    gemini_request_delay: float = 2.0  # 请求间隔（秒）
    gemini_max_retries: int = 5  # 最大重试次数
    gemini_retry_delay: float = 5.0  # 重试基础延时（秒）

    # Anthropic Claude API（备选，当 Gemini 不可用时使用）
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"  # Claude model name
    anthropic_temperature: float = 0.7  # Anthropic temperature (0.0-1.0, default 0.7)
    anthropic_max_tokens: int = 8192  # Max tokens for Anthropic responses

    # OpenAI 兼容 API（备选，当 Gemini/Anthropic 不可用时使用）
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None  # 如: https://api.openai.com/v1
    openai_model: str = "gpt-5.5"  # OpenAI 兼容模型名称
    openai_vision_model: Optional[str] = None  # Deprecated: use VISION_MODEL instead
    openai_temperature: float = 0.7  # OpenAI 温度参数（0.0-2.0，默认0.7）

    # === Vision 配置 ===
    # VISION_MODEL: litellm model string used for image understanding calls.
    # Fallback chain: VISION_MODEL → OPENAI_VISION_MODEL → gemini/gemini-2.0-flash
    vision_model: str = ""
    # VISION_PROVIDER_PRIORITY: comma-separated provider order for Vision fallback.
    vision_provider_priority: str = "gemini,anthropic,openai"

    # === 搜索引擎配置（支持多 Key 负载均衡）===
    anspire_api_keys: List[str] = field(default_factory=list)  # Anspire API Keys (LLM channel fallback only)
    minimax_api_keys: List[str] = field(default_factory=list)  # MiniMax API Keys
    brave_api_keys: List[str] = field(default_factory=list)  # Brave Search API Keys
    serpapi_keys: List[str] = field(default_factory=list)  # SerpAPI Keys
    firecrawl_api_key: Optional[str] = None  # Firecrawl API key for URL content scraping

    # === Social Sentiment (US stocks only, api.adanos.org) ===
    social_sentiment_api_key: Optional[str] = None
    social_sentiment_api_url: str = "https://api.adanos.org"

    # === 新闻与分析筛选配置 ===
    bias_threshold: float = 5.0  # 旧个股分析链路的固定乖离率阈值

    # === Agent 模式配置 ===
    agent_litellm_model: str = ""  # Optional Agent-only primary model; empty inherits LITELLM_MODEL
    agent_mode: bool = False
    _agent_mode_explicit: bool = False  # True when AGENT_MODE was explicitly set in env
    agent_max_steps: int = AGENT_MAX_STEPS_DEFAULT
    agent_skills: List[str] = field(default_factory=list)
    agent_skill_dir: Optional[str] = None
    agent_nl_routing: bool = False  # Enable natural language routing in bot dispatcher
    agent_arch: str = "single"     # Agent architecture: 'single' (legacy) or 'multi' (orchestrator)
    agent_orchestrator_mode: str = "standard"  # Orchestrator mode: quick/standard/full/specialist
    agent_orchestrator_timeout_s: int = 600  # Cooperative timeout budget for the whole multi-agent pipeline
    agent_risk_override: bool = True  # Allow risk agent to veto buy signals
    agent_deep_research_budget: int = 30000  # Max token budget for deep research
    agent_deep_research_timeout: int = 180  # Max seconds for /research command before returning timeout
    agent_memory_enabled: bool = False  # Enable memory & calibration system
    agent_skill_autoweight: bool = True  # Auto-weight skills by backtest performance
    agent_skill_routing: str = "auto"  # Skill routing: 'auto' (regime-based) or 'manual'
    agent_context_compression_enabled: bool = False  # Compress visible chat history before Agent calls
    agent_context_compression_profile: str = AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE
    agent_context_compression_trigger_tokens: int = 12000
    agent_context_protected_turns: int = 4

    # 报告类型：simple(精简) 或 full(完整)
    report_type: str = "simple"
    report_language: str = "zh"

    # 仅分析结果摘要：true 时只推送汇总，不含个股详情（Issue #262）
    report_summary_only: bool = False
    report_show_llm_model: bool = True

    # Report Engine P0: Jinja2 renderer and integrity checks
    report_templates_dir: str = "templates"  # Template directory (relative to project root)
    report_renderer_enabled: bool = False  # Enable Jinja2 rendering (default off for zero regression)
    report_integrity_enabled: bool = True  # Content integrity validation after LLM output
    report_integrity_retry: int = 1  # Retry count when mandatory fields missing (0 = placeholder only)
    report_history_compare_n: int = 0  # History comparison count (0 = disabled)

    # 实时行情预取（Issue #455）：设为 false 可禁用，避免 efinance/akshare_em 全市场拉取
    prefetch_realtime_quotes: bool = True

    # === 数据库配置 ===
    database_path: str = "./data/stock_analysis.db"
    sqlite_wal_enabled: bool = True
    sqlite_busy_timeout_ms: int = 5000
    sqlite_write_retry_max: int = 3
    sqlite_write_retry_base_delay: float = 0.1

    # 是否保存分析上下文快照（用于历史回溯）
    save_context_snapshot: bool = True

    # === 回测配置 ===
    backtest_enabled: bool = True
    backtest_eval_window_days: int = 10
    backtest_min_age_days: int = 14
    backtest_engine_version: str = "v1"
    backtest_neutral_band_pct: float = 2.0
    
    # === 日志配置 ===
    log_dir: str = "./logs"  # 日志文件目录
    log_level: str = "INFO"  # 日志级别
    
    # === 系统配置 ===
    max_workers: int = 3  # 低并发防封禁
    debug: bool = False
    http_proxy: Optional[str] = None  # HTTP 代理 (例如: http://127.0.0.1:10809)
    https_proxy: Optional[str] = None # HTTPS 代理
    
    # === 启动配置 ===
    schedule_enabled: bool = False            # legacy compatibility, scheduler mode has been removed
    schedule_time: str = "18:00"              # legacy compatibility
    # 东财接口补丁开关
    enable_eastmoney_patch: bool = False
    # 实时行情数据源优先级（逗号分隔）
    # 推荐顺序：tencent > akshare_sina > efinance > akshare_em > tushare
    # - tencent: 腾讯财经，有量比/换手率/市盈率等，单股查询稳定（推荐）
    # - akshare_sina: 新浪财经，基本行情稳定，但无量比
    # - efinance/akshare_em: 东财全量接口，数据最全但容易被封
    # - tushare: Tushare Pro，需要 2000 积分，数据全面（付费用户可优先使用）
    realtime_source_priority: str = "tencent,akshare_sina,efinance,akshare_em"
    # Toggle switches for built-in data providers
    tushare: bool = False
    akshare: bool = True
    yfinance: bool = True
    pytdx: bool = True
    efinance: bool = True
    baostock: bool = True
    # 实时行情缓存时间（秒）
    realtime_cache_ttl: int = 600
    # 熔断器冷却时间（秒）
    circuit_breaker_cooldown: int = 300

    # === 基本面聚合开关与降级保护 ===
    # 全局总开关；关闭时返回 not_supported 并保持主流程无变化
    enable_fundamental_pipeline: bool = True
    # 基本面阶段总预算（秒）
    fundamental_stage_timeout_seconds: float = FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT
    # 单能力源调用超时（秒）
    fundamental_fetch_timeout_seconds: float = 3.0
    # 单能力失败重试次数（已包含首次）
    fundamental_retry_max: int = 1
    # 基本面上下文短 TTL（秒）
    fundamental_cache_ttl_seconds: int = 120
    # 基本面缓存最大条目数（避免长时间运行内存增长）
    fundamental_cache_max_entries: int = 256

    # === Portfolio PR2: import/risk/fx settings ===
    portfolio_risk_concentration_alert_pct: float = 35.0
    portfolio_risk_drawdown_alert_pct: float = 15.0
    portfolio_risk_stop_loss_alert_pct: float = 10.0
    portfolio_risk_stop_loss_near_ratio: float = 0.8
    portfolio_risk_lookback_days: int = 180
    portfolio_fx_update_enabled: bool = True

    # Discord 机器人状态
    discord_bot_status: str = "A股智能分析 | /help"

    # === 流控配置（防封禁关键参数）===
    # Akshare 请求间隔范围（秒）
    akshare_sleep_min: float = 2.0
    akshare_sleep_max: float = 5.0
    
    # Tushare 每分钟最大请求数（免费配额）
    tushare_rate_limit_per_minute: int = 80
    
    # 重试配置
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0
    
    # === WebUI 配置 ===
    webui_enabled: bool = False
    webui_host: str = "127.0.0.1"
    webui_port: int = 8000
    
    # === 机器人配置 ===
    bot_enabled: bool = True              # 是否启用机器人功能
    bot_command_prefix: str = "/"         # 命令前缀
    bot_rate_limit_requests: int = 10     # 频率限制：窗口内最大请求数
    bot_rate_limit_window: int = 60       # 频率限制：窗口时间（秒）
    bot_admin_users: List[str] = field(default_factory=list)  # 管理员用户 ID 列表
    
    # 飞书机器人（事件订阅）- 已有 feishu_app_id, feishu_app_secret
    feishu_verification_token: Optional[str] = None  # 事件订阅验证 Token
    feishu_encrypt_key: Optional[str] = None         # 消息加密密钥（可选）
    feishu_stream_enabled: bool = False              # 是否启用 Stream 长连接模式（无需公网IP）
    
    # 钉钉机器人
    dingtalk_app_key: Optional[str] = None      # 应用 AppKey
    dingtalk_app_secret: Optional[str] = None   # 应用 AppSecret
    dingtalk_stream_enabled: bool = False       # 是否启用 Stream 模式（无需公网IP）
    
    # 企业微信机器人（回调模式）
    wecom_corpid: Optional[str] = None              # 企业 ID
    wecom_token: Optional[str] = None               # 回调 Token
    wecom_encoding_aes_key: Optional[str] = None    # 消息加解密密钥
    wecom_agent_id: Optional[str] = None            # 应用 AgentId
    
    # Telegram 机器人 - 已有 telegram_bot_token, telegram_chat_id
    telegram_webhook_secret: Optional[str] = None   # Webhook 密钥

    # === 配置校验模式 ===
    # CONFIG_VALIDATE_MODE=warn (default): log all issues but always continue startup
    # CONFIG_VALIDATE_MODE=strict: exit(1) when any "error" severity issue is found
    config_validate_mode: str = "warn"

    # --- Post-init validation ---------------------------------------------------
    _VALID_AGENT_ARCH = {"single", "multi"}
    _VALID_ORCHESTRATOR_MODES = {"quick", "standard", "full", "specialist"}
    _VALID_SKILL_ROUTING = {"auto", "manual"}
    _WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS = frozenset()
    _BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED = False
    _BOOTSTRAP_RUNTIME_ENV_OVERRIDES = frozenset()
    _BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS = frozenset()

    def __post_init__(self) -> None:
        _log = logging.getLogger(__name__)
        if self.agent_arch not in self._VALID_AGENT_ARCH:
            _log.warning(
                "Invalid AGENT_ARCH=%r, falling back to 'single'. Valid: %s",
                self.agent_arch, self._VALID_AGENT_ARCH,
            )
            object.__setattr__(self, "agent_arch", "single")
        if self.agent_orchestrator_mode in {"strategy", "skill"}:
            _log.info(
                "AGENT_ORCHESTRATOR_MODE=%s is deprecated; normalizing to 'specialist'",
                self.agent_orchestrator_mode,
            )
            object.__setattr__(self, "agent_orchestrator_mode", "specialist")
        if self.agent_orchestrator_mode not in self._VALID_ORCHESTRATOR_MODES:
            _log.warning(
                "Invalid AGENT_ORCHESTRATOR_MODE=%r, falling back to 'standard'. Valid: %s",
                self.agent_orchestrator_mode, self._VALID_ORCHESTRATOR_MODES,
            )
            object.__setattr__(self, "agent_orchestrator_mode", "standard")
        if self.agent_skill_routing not in self._VALID_SKILL_ROUTING:
            _log.warning(
                "Invalid AGENT_SKILL_ROUTING=%r, falling back to 'auto'. Valid: %s",
                self.agent_skill_routing, self._VALID_SKILL_ROUTING,
            )
            object.__setattr__(self, "agent_skill_routing", "auto")
        normalized_profile = normalize_agent_context_compression_profile(
            self.agent_context_compression_profile
        )
        if normalized_profile != self.agent_context_compression_profile:
            object.__setattr__(self, "agent_context_compression_profile", normalized_profile)

    # 单例实例存储
    _instance: Optional['Config'] = None
    
    @classmethod
    def get_instance(cls) -> 'Config':
        """
        获取配置单例实例
        
        单例模式确保：
        1. 全局只有一个配置实例
        2. 配置只从环境变量加载一次
        3. 所有模块共享相同配置
        """
        if cls._instance is None:
            cls._instance = cls._load_from_env()
        return cls._instance
    
    @classmethod
    def _load_from_env(cls) -> 'Config':
        """
        从 .env 文件加载配置
        
        加载优先级：
        1. JSON 配置持久化（config/settings.json）
        2. 显式设置的 process 环境变量
        3. .env 文件
        4. 代码中的默认值
        """
        cls._capture_bootstrap_runtime_env_overrides()
        preexisting_report_language = os.environ.get("REPORT_LANGUAGE")

        # 确保 .env 已加载
        setup_env()

        # 加载 JSON 配置到环境变量（如果 .env 中未设置）
        from src.config_storage import config_storage
        config_storage.initialize()
        config_storage.load_to_env()

        # === 智能代理配置 (关键修复) ===
        # 如果配置了代理，自动设置 NO_PROXY 以排除国内数据源，避免行情获取失败
        http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
        if http_proxy:
            # 国内金融数据源域名列表
            domestic_domains = [
                'eastmoney.com',   # 东方财富 (Efinance/Akshare)
                'sina.com.cn',     # 新浪财经 (Akshare)
                '163.com',         # 网易财经 (Akshare)
                'tushare.pro',     # Tushare
                'baostock.com',    # Baostock
                'sse.com.cn',      # 上交所
                'szse.cn',         # 深交所
                'csindex.com.cn',  # 中证指数
                'cninfo.com.cn',   # 巨潮资讯
                'localhost',
                '127.0.0.1'
            ]

            # 获取现有的 no_proxy
            current_no_proxy = os.getenv('NO_PROXY') or os.getenv('no_proxy') or ''
            existing_domains = current_no_proxy.split(',') if current_no_proxy else []

            # 合并去重
            final_domains = list(set(existing_domains + domestic_domains))
            final_no_proxy = ','.join(filter(None, final_domains))

            # 设置环境变量 (requests/urllib3/aiohttp 都会遵守此设置)
            os.environ['NO_PROXY'] = final_no_proxy
            os.environ['no_proxy'] = final_no_proxy

            # 确保 HTTP_PROXY 也被正确设置（以防仅在 .env 中定义但未导出）
            os.environ['HTTP_PROXY'] = http_proxy
            os.environ['http_proxy'] = http_proxy

            # HTTPS_PROXY 同理
            https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
            if https_proxy:
                os.environ['HTTPS_PROXY'] = https_proxy
                os.environ['https_proxy'] = https_proxy

        # === LiteLLM multi-key parsing ===
        _gemini_keys_raw = os.getenv('GEMINI_API_KEYS', '')
        gemini_api_keys = [k.strip() for k in _gemini_keys_raw.split(',') if k.strip()]
        _single_gemini = os.getenv('GEMINI_API_KEY', '').strip()
        if not gemini_api_keys and _single_gemini:
            gemini_api_keys = [_single_gemini]

        # ANTHROPIC_API_KEYS > ANTHROPIC_API_KEY
        _anthropic_keys_raw = os.getenv('ANTHROPIC_API_KEYS', '')
        anthropic_api_keys = [k.strip() for k in _anthropic_keys_raw.split(',') if k.strip()]
        _single_anthropic = os.getenv('ANTHROPIC_API_KEY', '').strip()
        if not anthropic_api_keys and _single_anthropic:
            anthropic_api_keys = [_single_anthropic]

        # OPENAI_API_KEYS > AIHUBMIX_KEY > OPENAI_API_KEY
        _aihubmix = os.getenv('AIHUBMIX_KEY', '').strip()
        _openai_keys_raw = os.getenv('OPENAI_API_KEYS', '')
        openai_api_keys = [k.strip() for k in _openai_keys_raw.split(',') if k.strip()]
        if not openai_api_keys:
            _single_openai = os.getenv('OPENAI_API_KEY', '').strip()
            _fallback_key = _aihubmix or _single_openai
            if _fallback_key:
                openai_api_keys = [_fallback_key]
        openai_base_url = os.getenv('OPENAI_BASE_URL') or (
            'https://aihubmix.com/v1' if _aihubmix else None
        )

        # DEEPSEEK_API_KEYS > DEEPSEEK_API_KEY (independent from OpenAI-compatible layer)
        _deepseek_keys_raw = os.getenv('DEEPSEEK_API_KEYS', '')
        deepseek_api_keys = [k.strip() for k in _deepseek_keys_raw.split(',') if k.strip()]
        if not deepseek_api_keys:
            _single_deepseek = os.getenv('DEEPSEEK_API_KEY', '').strip()
            if _single_deepseek:
                deepseek_api_keys = [_single_deepseek]

        anspire_keys_str = os.getenv('ANSPIRE_API_KEYS', '')
        anspire_api_keys = [k.strip() for k in anspire_keys_str.split(',') if k.strip()]

        # LITELLM_MODEL: explicit config takes precedence; else infer from available keys
        litellm_model = os.getenv('LITELLM_MODEL', '').strip()
        inferred_legacy_deepseek_model = False
        _openai_model_env = os.getenv('OPENAI_MODEL', '').strip()
        _openai_model_name = _openai_model_env or 'gpt-5.5'
        if not litellm_model:
            _gemini_model_name = os.getenv('GEMINI_MODEL', 'gemini-3.1-pro-preview').strip()
            _anthropic_model_name = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6').strip()
            if gemini_api_keys:
                litellm_model = f'gemini/{_gemini_model_name}'
            elif anthropic_api_keys:
                litellm_model = f'anthropic/{_anthropic_model_name}'
            elif deepseek_api_keys:
                litellm_model = 'deepseek/deepseek-chat'
                inferred_legacy_deepseek_model = True
            elif openai_api_keys:
                # For openai-compatible models, add prefix only if not already prefixed
                if '/' not in _openai_model_name:
                    litellm_model = f'openai/{_openai_model_name}'
                else:
                    litellm_model = _openai_model_name

        # LITELLM_FALLBACK_MODELS: comma-separated list of fallback models
        _fallback_str = os.getenv('LITELLM_FALLBACK_MODELS', '')
        if _fallback_str.strip():
            litellm_fallback_models = [m.strip() for m in _fallback_str.split(',') if m.strip()]
        else:
            # Backward compat: use gemini_model_fallback when primary is gemini
            _gemini_fallback = os.getenv('GEMINI_MODEL_FALLBACK', 'gemini-3-flash-preview').strip()
            if litellm_model.startswith('gemini/') and _gemini_fallback:
                _fb = f'gemini/{_gemini_fallback}' if '/' not in _gemini_fallback else _gemini_fallback
                litellm_fallback_models = [_fb]
            else:
                litellm_fallback_models = []

        # === LLM Channels ===
        llm_models_source = "legacy_env"
        llm_channels: List[Dict[str, Any]] = []
        llm_model_list: List[Dict[str, Any]] = []

        # Priority 1: LLM_CHANNELS (env var based channel config)
        _channels_str = os.getenv('LLM_CHANNELS', '').strip()
        if _channels_str:
            llm_channels = cls._parse_llm_channels(_channels_str)
            llm_model_list = cls._channels_to_model_list(llm_channels)
            if llm_model_list:
                llm_models_source = "llm_channels"

        # Priority 2: Legacy env vars → auto-build model_list (backward compatible)
        if not llm_model_list:
            llm_model_list = cls._legacy_keys_to_model_list(
                gemini_api_keys, anthropic_api_keys, openai_api_keys,
                openai_base_url,
                deepseek_api_keys,
            )
            if llm_model_list:
                llm_models_source = "legacy_env"

        configured_runtime_models = get_configured_llm_models(llm_model_list)
        if (
            litellm_model
            and configured_runtime_models
            and litellm_model not in configured_runtime_models
            and not _uses_direct_env_provider(litellm_model)
        ):
            replacement_model = configured_runtime_models[0]
            logger.warning(
                "Configured LITELLM_MODEL %s is not present in current runtime model list; using %s instead.",
                litellm_model,
                replacement_model,
            )
            litellm_model = replacement_model

        if (
            inferred_legacy_deepseek_model
            and llm_models_source == "legacy_env"
            and litellm_model == 'deepseek/deepseek-chat'
        ):
            logger.warning(
                "Deprecation warning:\n"
                "deepseek-chat will be deprecated on 2026-07-24,\n"
                "please migrate to deepseek-v4-flash."
            )

        # Auto-infer LITELLM_MODEL from channels when not explicitly set
        if not litellm_model and llm_channels:
            for _ch in llm_channels:
                if _ch.get('models'):
                    litellm_model = _ch['models'][0]
                    break

        # Auto-infer LITELLM_FALLBACK_MODELS from channels when not explicitly set
        if not litellm_fallback_models and llm_channels and litellm_model:
            _all_ch_models: List[str] = []
            for _ch in llm_channels:
                _all_ch_models.extend(_ch.get('models', []))
            _seen = {litellm_model}
            litellm_fallback_models = [
                m for m in _all_ch_models
                if m not in _seen and not _seen.add(m)  # type: ignore[func-returns-value]
            ]

        agent_litellm_model = normalize_agent_litellm_model(
            os.getenv('AGENT_LITELLM_MODEL', ''),
            configured_models=set(get_configured_llm_models(llm_model_list)),
        )
        agent_context_compression_profile = normalize_agent_context_compression_profile(
            os.getenv('AGENT_CONTEXT_COMPRESSION_PROFILE')
        )
        agent_context_compression_preset = get_agent_context_compression_preset(
            agent_context_compression_profile
        )
        agent_context_compression_trigger_tokens = parse_agent_context_compression_int(
            os.getenv('AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS'),
            agent_context_compression_preset.trigger_tokens,
            field_name='AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
            minimum=1000,
            maximum=200000,
        )
        agent_context_protected_turns = parse_agent_context_compression_int(
            os.getenv('AGENT_CONTEXT_PROTECTED_TURNS'),
            agent_context_compression_preset.protected_turns,
            field_name='AGENT_CONTEXT_PROTECTED_TURNS',
            minimum=1,
            maximum=20,
        )

        # 解析搜索引擎 API Keys（支持多个 key，逗号分隔）
        minimax_keys_str = os.getenv('MINIMAX_API_KEYS', '')
        minimax_api_keys = [k.strip() for k in minimax_keys_str.split(',') if k.strip()]
        
        serpapi_keys_str = os.getenv('SERPAPI_API_KEYS', '')
        serpapi_keys = [k.strip() for k in serpapi_keys_str.split(',') if k.strip()]

        brave_keys_str = os.getenv('BRAVE_API_KEYS', '')
        brave_api_keys = [k.strip() for k in brave_keys_str.split(',') if k.strip()]

        report_language_raw = cls._resolve_report_language_env_value(
            preexisting_report_language
        )
        report_show_llm_model_raw = os.getenv('REPORT_SHOW_LLM_MODEL')
        report_show_llm_model = parse_env_bool(report_show_llm_model_raw, default=True)
        if report_show_llm_model_raw is not None and not report_show_llm_model_raw.strip():
            report_show_llm_model = False

        return cls(
            feishu_app_id=os.getenv('FEISHU_APP_ID'),
            feishu_app_secret=os.getenv('FEISHU_APP_SECRET'),
            feishu_folder_token=os.getenv('FEISHU_FOLDER_TOKEN'),
            tushare_token=os.getenv('TUSHARE_TOKEN'),
            tickflow_api_key=os.getenv('TICKFLOW_API_KEY'),
            litellm_model=litellm_model,
            litellm_fallback_models=litellm_fallback_models,
            llm_temperature=resolve_unified_llm_temperature(litellm_model),
            llm_models_source=llm_models_source,
            llm_channels=llm_channels,
            llm_model_list=llm_model_list,
            gemini_api_keys=gemini_api_keys,
            anthropic_api_keys=anthropic_api_keys,
            openai_api_keys=openai_api_keys,
            deepseek_api_keys=deepseek_api_keys,
            gemini_api_key=os.getenv('GEMINI_API_KEY'),
            gemini_model=os.getenv('GEMINI_MODEL', 'gemini-3.1-pro-preview'),
            gemini_model_fallback=os.getenv('GEMINI_MODEL_FALLBACK', 'gemini-3-flash-preview'),
            gemini_temperature=parse_env_float(os.getenv('GEMINI_TEMPERATURE'), 0.7, field_name='GEMINI_TEMPERATURE'),
            gemini_request_delay=parse_env_float(os.getenv('GEMINI_REQUEST_DELAY'), 2.0, field_name='GEMINI_REQUEST_DELAY', minimum=0.0),
            gemini_max_retries=parse_env_int(os.getenv('GEMINI_MAX_RETRIES'), 5, field_name='GEMINI_MAX_RETRIES', minimum=0),
            gemini_retry_delay=parse_env_float(os.getenv('GEMINI_RETRY_DELAY'), 5.0, field_name='GEMINI_RETRY_DELAY', minimum=0.0),
            anthropic_api_key=os.getenv('ANTHROPIC_API_KEY'),
            anthropic_model=os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
            anthropic_temperature=parse_env_float(os.getenv('ANTHROPIC_TEMPERATURE'), 0.7, field_name='ANTHROPIC_TEMPERATURE'),
            anthropic_max_tokens=parse_env_int(os.getenv('ANTHROPIC_MAX_TOKENS'), 8192, field_name='ANTHROPIC_MAX_TOKENS', minimum=1),
            # AIHubmix is the preferred OpenAI-compatible provider (one key, all models, no VPN required).
            # Within the OpenAI-compatible layer: AIHUBMIX_KEY takes priority over OPENAI_API_KEY.
            # Overall provider fallback order: Gemini > Anthropic > OpenAI-compatible (incl. AIHubmix).
            # base_url is auto-set to aihubmix.com/v1 when AIHUBMIX_KEY is used and no explicit
            # OPENAI_BASE_URL override is provided.
            # Model names match upstream (e.g. gemini-3.1-pro-preview, gpt-5.5, deepseek-v4-flash).
            openai_api_key=openai_api_keys[0] if openai_api_keys else None,
            openai_base_url=openai_base_url,
            openai_model=_openai_model_name,
            openai_vision_model=os.getenv('OPENAI_VISION_MODEL') or None,
            openai_temperature=parse_env_float(os.getenv('OPENAI_TEMPERATURE'), 0.7, field_name='OPENAI_TEMPERATURE'),
            # Vision model: VISION_MODEL > OPENAI_VISION_MODEL (alias) > default
            vision_model=(
                os.getenv('VISION_MODEL')
                or os.getenv('OPENAI_VISION_MODEL')
                or ""
            ),
            vision_provider_priority=os.getenv('VISION_PROVIDER_PRIORITY', 'gemini,anthropic,openai'),
            anspire_api_keys=anspire_api_keys,
            minimax_api_keys=minimax_api_keys,
            brave_api_keys=brave_api_keys,
            serpapi_keys=serpapi_keys,
            firecrawl_api_key=os.getenv('FIRECRAWL_API_KEY') or None,
            social_sentiment_api_key=os.getenv('SOCIAL_SENTIMENT_API_KEY') or None,
            social_sentiment_api_url=os.getenv('SOCIAL_SENTIMENT_API_URL', 'https://api.adanos.org').rstrip('/'),
            bias_threshold=5.0,
            agent_litellm_model=agent_litellm_model,
            agent_mode=os.getenv('AGENT_MODE', 'false').lower() == 'true',
            _agent_mode_explicit=os.getenv('AGENT_MODE') is not None,
            agent_max_steps=parse_env_int(
                os.getenv('AGENT_MAX_STEPS'),
                AGENT_MAX_STEPS_DEFAULT,
                field_name='AGENT_MAX_STEPS',
                minimum=1,
            ),
            agent_skills=[s.strip() for s in os.getenv('AGENT_SKILLS', '').split(',') if s.strip()],
            agent_skill_dir=os.getenv('AGENT_SKILL_DIR') or os.getenv('AGENT_STRATEGY_DIR'),
            agent_nl_routing=os.getenv('AGENT_NL_ROUTING', 'false').lower() == 'true',
            agent_arch=os.getenv('AGENT_ARCH', 'single').lower(),
            agent_orchestrator_mode=os.getenv('AGENT_ORCHESTRATOR_MODE', 'standard').lower(),
            agent_orchestrator_timeout_s=parse_env_int(
                os.getenv('AGENT_ORCHESTRATOR_TIMEOUT_S'),
                600,
                field_name='AGENT_ORCHESTRATOR_TIMEOUT_S',
                minimum=0,
            ),
            agent_risk_override=os.getenv('AGENT_RISK_OVERRIDE', 'true').lower() == 'true',
            agent_deep_research_budget=parse_env_int(
                os.getenv('AGENT_DEEP_RESEARCH_BUDGET'),
                30000,
                field_name='AGENT_DEEP_RESEARCH_BUDGET',
                minimum=5000,
            ),
            agent_deep_research_timeout=parse_env_int(
                os.getenv('AGENT_DEEP_RESEARCH_TIMEOUT'),
                180,
                field_name='AGENT_DEEP_RESEARCH_TIMEOUT',
                minimum=30,
            ),
            agent_memory_enabled=os.getenv('AGENT_MEMORY_ENABLED', 'false').lower() == 'true',
            agent_skill_autoweight=(
                os.getenv('AGENT_SKILL_AUTOWEIGHT')
                or os.getenv('AGENT_STRATEGY_AUTOWEIGHT', 'true')
            ).lower() == 'true',
            agent_skill_routing=(
                os.getenv('AGENT_SKILL_ROUTING')
                or os.getenv('AGENT_STRATEGY_ROUTING', 'auto')
            ).lower(),
            agent_context_compression_enabled=parse_env_bool(
                os.getenv('AGENT_CONTEXT_COMPRESSION_ENABLED'),
                default=False,
            ),
            agent_context_compression_profile=agent_context_compression_profile,
            agent_context_compression_trigger_tokens=agent_context_compression_trigger_tokens,
            agent_context_protected_turns=agent_context_protected_turns,
            report_type=cls._parse_report_type(os.getenv('REPORT_TYPE', 'simple')),
            report_language=cls._parse_report_language(report_language_raw),
            report_summary_only=os.getenv('REPORT_SUMMARY_ONLY', 'false').lower() == 'true',
            report_show_llm_model=report_show_llm_model,
            report_templates_dir=os.getenv('REPORT_TEMPLATES_DIR', 'templates'),
            report_renderer_enabled=os.getenv('REPORT_RENDERER_ENABLED', 'false').lower() == 'true',
            report_integrity_enabled=os.getenv('REPORT_INTEGRITY_ENABLED', 'true').lower() == 'true',
            report_integrity_retry=parse_env_int(os.getenv('REPORT_INTEGRITY_RETRY'), 1, field_name='REPORT_INTEGRITY_RETRY', minimum=0),
            report_history_compare_n=parse_env_int(os.getenv('REPORT_HISTORY_COMPARE_N'), 0, field_name='REPORT_HISTORY_COMPARE_N', minimum=0),
            prefetch_realtime_quotes=os.getenv('PREFETCH_REALTIME_QUOTES', 'true').lower() == 'true',
            database_path=os.getenv('DATABASE_PATH', './data/stock_analysis.db'),
            sqlite_wal_enabled=os.getenv('SQLITE_WAL_ENABLED', 'true').lower() == 'true',
            sqlite_busy_timeout_ms=parse_env_int(
                os.getenv('SQLITE_BUSY_TIMEOUT_MS'),
                5000,
                field_name='SQLITE_BUSY_TIMEOUT_MS',
                minimum=0,
            ),
            sqlite_write_retry_max=parse_env_int(
                os.getenv('SQLITE_WRITE_RETRY_MAX'),
                3,
                field_name='SQLITE_WRITE_RETRY_MAX',
                minimum=0,
            ),
            sqlite_write_retry_base_delay=parse_env_float(
                os.getenv('SQLITE_WRITE_RETRY_BASE_DELAY'),
                0.1,
                field_name='SQLITE_WRITE_RETRY_BASE_DELAY',
                minimum=0.0,
            ),
            save_context_snapshot=os.getenv('SAVE_CONTEXT_SNAPSHOT', 'true').lower() == 'true',
            backtest_enabled=os.getenv('BACKTEST_ENABLED', 'true').lower() == 'true',
            backtest_eval_window_days=parse_env_int(os.getenv('BACKTEST_EVAL_WINDOW_DAYS'), 10, field_name='BACKTEST_EVAL_WINDOW_DAYS', minimum=1),
            backtest_min_age_days=parse_env_int(os.getenv('BACKTEST_MIN_AGE_DAYS'), 14, field_name='BACKTEST_MIN_AGE_DAYS', minimum=1),
            backtest_engine_version=os.getenv('BACKTEST_ENGINE_VERSION', 'v1'),
            backtest_neutral_band_pct=parse_env_float(
                os.getenv('BACKTEST_NEUTRAL_BAND_PCT'),
                2.0,
                field_name='BACKTEST_NEUTRAL_BAND_PCT',
                minimum=0.0,
            ),
            log_dir=os.getenv('LOG_DIR', './logs'),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            max_workers=parse_env_int(os.getenv('MAX_WORKERS'), 3, field_name='MAX_WORKERS', minimum=1),
            debug=os.getenv('DEBUG', 'false').lower() == 'true',
            config_validate_mode=os.getenv('CONFIG_VALIDATE_MODE', 'warn').lower(),
            http_proxy=os.getenv('HTTP_PROXY'),
            https_proxy=os.getenv('HTTPS_PROXY'),
            schedule_enabled=False,
            schedule_time='18:00',
            webui_enabled=os.getenv('WEBUI_ENABLED', 'false').lower() == 'true',
            webui_host=os.getenv('WEBUI_HOST', '127.0.0.1'),
            webui_port=parse_env_int(os.getenv('WEBUI_PORT'), 8000, field_name='WEBUI_PORT', minimum=1, maximum=65535),
            # 机器人配置
            bot_enabled=os.getenv('BOT_ENABLED', 'true').lower() == 'true',
            bot_command_prefix=os.getenv('BOT_COMMAND_PREFIX', '/'),
            bot_rate_limit_requests=parse_env_int(os.getenv('BOT_RATE_LIMIT_REQUESTS'), 10, field_name='BOT_RATE_LIMIT_REQUESTS', minimum=1),
            bot_rate_limit_window=parse_env_int(os.getenv('BOT_RATE_LIMIT_WINDOW'), 60, field_name='BOT_RATE_LIMIT_WINDOW', minimum=1),
            bot_admin_users=[u.strip() for u in os.getenv('BOT_ADMIN_USERS', '').split(',') if u.strip()],
            # 飞书机器人
            feishu_verification_token=os.getenv('FEISHU_VERIFICATION_TOKEN'),
            feishu_encrypt_key=os.getenv('FEISHU_ENCRYPT_KEY'),
            feishu_stream_enabled=os.getenv('FEISHU_STREAM_ENABLED', 'false').lower() == 'true',
            # 钉钉机器人
            dingtalk_app_key=os.getenv('DINGTALK_APP_KEY'),
            dingtalk_app_secret=os.getenv('DINGTALK_APP_SECRET'),
            dingtalk_stream_enabled=os.getenv('DINGTALK_STREAM_ENABLED', 'false').lower() == 'true',
            # 企业微信机器人
            wecom_corpid=os.getenv('WECOM_CORPID'),
            wecom_token=os.getenv('WECOM_TOKEN'),
            wecom_encoding_aes_key=os.getenv('WECOM_ENCODING_AES_KEY'),
            wecom_agent_id=os.getenv('WECOM_AGENT_ID'),
            # Telegram
            telegram_webhook_secret=os.getenv('TELEGRAM_WEBHOOK_SECRET'),
            # Discord 机器人扩展配置
            discord_bot_status=os.getenv('DISCORD_BOT_STATUS', 'A股智能分析 | /help'),
            # 东财接口补丁开关
            enable_eastmoney_patch=os.getenv('ENABLE_EASTMONEY_PATCH', 'false').lower() == 'true',
            # 实时行情数据源优先级：
            # - tencent: 腾讯财经，有量比/换手率/PE/PB等，单股查询稳定（推荐）
            # - akshare_sina: 新浪财经，基本行情稳定，但无量比
            # - efinance/akshare_em: 东财全量接口，数据最全但容易被封
            # - tushare: Tushare Pro，需要2000积分，数据全面
            realtime_source_priority=cls._resolve_realtime_source_priority(),
            tushare=parse_env_bool(os.getenv('TUSHARE_ENABLED'), False),
            akshare=parse_env_bool(os.getenv('AKSHARE'), True),
            yfinance=parse_env_bool(os.getenv('YFINANCE'), True),
            pytdx=parse_env_bool(os.getenv('PYTDX'), True),
            efinance=parse_env_bool(os.getenv('EFINANCE'), True),
            baostock=parse_env_bool(os.getenv('BAOSTOCK'), True),
            realtime_cache_ttl=parse_env_int(os.getenv('REALTIME_CACHE_TTL'), 600, field_name='REALTIME_CACHE_TTL', minimum=0),
            circuit_breaker_cooldown=parse_env_int(os.getenv('CIRCUIT_BREAKER_COOLDOWN'), 300, field_name='CIRCUIT_BREAKER_COOLDOWN', minimum=0),
            enable_fundamental_pipeline=os.getenv('ENABLE_FUNDAMENTAL_PIPELINE', 'true').lower() == 'true',
            fundamental_stage_timeout_seconds=parse_env_float(
                os.getenv('FUNDAMENTAL_STAGE_TIMEOUT_SECONDS'),
                FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
                field_name='FUNDAMENTAL_STAGE_TIMEOUT_SECONDS',
                minimum=0.0,
            ),
            fundamental_fetch_timeout_seconds=parse_env_float(
                os.getenv('FUNDAMENTAL_FETCH_TIMEOUT_SECONDS'),
                3.0,
                field_name='FUNDAMENTAL_FETCH_TIMEOUT_SECONDS',
                minimum=0.0,
            ),
            fundamental_retry_max=parse_env_int(os.getenv('FUNDAMENTAL_RETRY_MAX'), 1, field_name='FUNDAMENTAL_RETRY_MAX', minimum=0),
            fundamental_cache_ttl_seconds=parse_env_int(
                os.getenv('FUNDAMENTAL_CACHE_TTL_SECONDS'),
                120,
                field_name='FUNDAMENTAL_CACHE_TTL_SECONDS',
                minimum=0,
            ),
            fundamental_cache_max_entries=parse_env_int(
                os.getenv('FUNDAMENTAL_CACHE_MAX_ENTRIES'),
                256,
                field_name='FUNDAMENTAL_CACHE_MAX_ENTRIES',
                minimum=1,
            ),
            portfolio_risk_concentration_alert_pct=parse_env_float(
                os.getenv('PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT'),
                35.0,
                field_name='PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT',
                minimum=0.0,
            ),
            portfolio_risk_drawdown_alert_pct=parse_env_float(
                os.getenv('PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT'),
                15.0,
                field_name='PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT',
                minimum=0.0,
            ),
            portfolio_risk_stop_loss_alert_pct=parse_env_float(
                os.getenv('PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT'),
                10.0,
                field_name='PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT',
                minimum=0.0,
            ),
            portfolio_risk_stop_loss_near_ratio=parse_env_float(
                os.getenv('PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO'),
                0.8,
                field_name='PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO',
                minimum=0.0,
            ),
            portfolio_risk_lookback_days=parse_env_int(
                os.getenv('PORTFOLIO_RISK_LOOKBACK_DAYS'),
                180,
                field_name='PORTFOLIO_RISK_LOOKBACK_DAYS',
                minimum=1,
            ),
            portfolio_fx_update_enabled=os.getenv('PORTFOLIO_FX_UPDATE_ENABLED', 'true').lower() == 'true'
        )
    
    @classmethod
    def _parse_llm_channels(cls, channels_str: str) -> List[Dict[str, Any]]:
        """Parse LLM_CHANNELS env var and per-channel env vars.

        Format:
            LLM_CHANNELS=aihubmix,deepseek,gemini
            LLM_AIHUBMIX_PROTOCOL=openai
            LLM_AIHUBMIX_BASE_URL=https://aihubmix.com/v1
            LLM_AIHUBMIX_API_KEY=sk-xxx           (or LLM_AIHUBMIX_API_KEYS=k1,k2)
            LLM_AIHUBMIX_MODELS=gpt-5.5,claude-sonnet-4-6
            LLM_AIHUBMIX_ENABLED=true
        """
        import logging
        _logger = logging.getLogger(__name__)

        channels: List[Dict[str, Any]] = []
        for raw_name in channels_str.split(','):
            ch_name = raw_name.strip()
            if not ch_name:
                continue
            ch_lower = ch_name.lower()
            ch_upper = ch_name.upper()

            base_url = os.getenv(f'LLM_{ch_upper}_BASE_URL', '').strip() or None
            protocol_raw = os.getenv(f'LLM_{ch_upper}_PROTOCOL', '').strip()
            if ch_lower == "anspire" and not protocol_raw:
                protocol_raw = "openai"
            enabled_raw = os.getenv(f'LLM_{ch_upper}_ENABLED')
            enabled = parse_env_bool(enabled_raw, default=True)

            # API keys: LLM_{NAME}_API_KEYS (multi) > LLM_{NAME}_API_KEY (single)
            api_keys_raw = os.getenv(f'LLM_{ch_upper}_API_KEYS', '')
            api_keys = [k.strip() for k in api_keys_raw.split(',') if k.strip()]
            if not api_keys:
                single_key = os.getenv(f'LLM_{ch_upper}_API_KEY', '').strip()
                if single_key:
                    api_keys = [single_key]
            if not api_keys and ch_lower == "anspire":
                anspire_keys_raw = os.getenv('ANSPIRE_API_KEYS', '')
                api_keys = [k.strip() for k in anspire_keys_raw.split(',') if k.strip()]

            # Models
            models_raw = os.getenv(f'LLM_{ch_upper}_MODELS', '')
            raw_models = [m.strip() for m in models_raw.split(',') if m.strip()]
            protocol = resolve_llm_channel_protocol(protocol_raw, base_url=base_url, models=raw_models, channel_name=ch_name)
            models = [normalize_llm_channel_model(m, protocol, base_url) for m in raw_models]

            # Extra headers (JSON string, optional)
            extra_headers_raw = os.getenv(f'LLM_{ch_upper}_EXTRA_HEADERS', '').strip()
            extra_headers = None
            if extra_headers_raw:
                try:
                    extra_headers = json.loads(extra_headers_raw)
                except json.JSONDecodeError:
                    _logger.warning(f"LLM_{ch_upper}_EXTRA_HEADERS: invalid JSON, ignored")

            if not enabled:
                _logger.info(f"LLM channel '{ch_name}': disabled, skipped")
                continue

            if protocol_raw and canonicalize_llm_channel_protocol(protocol_raw) not in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
                _logger.warning(
                    "LLM_%s_PROTOCOL=%s is unsupported; auto-detected protocol=%s",
                    ch_upper,
                    protocol_raw,
                    protocol or "unknown",
                )

            if not api_keys and channel_allows_empty_api_key(protocol, base_url):
                api_keys = [""]

            if not api_keys:
                _logger.warning(f"LLM channel '{ch_name}': no API key configured, skipped")
                continue
            if not models:
                _logger.warning(f"LLM channel '{ch_name}': no models configured, skipped")
                continue

            channels.append({
                'name': ch_name.lower(),
                'protocol': protocol,
                'enabled': enabled,
                'base_url': base_url,
                'api_keys': api_keys,
                'models': models,
                'extra_headers': extra_headers,
            })
            _logger.info(f"LLM channel '{ch_name}': {len(models)} model(s), {len(api_keys)} key(s)")

        return channels

    @classmethod
    def _channels_to_model_list(cls, channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert parsed LLM channels to LiteLLM Router model_list format."""
        model_list: List[Dict[str, Any]] = []
        for ch in channels:
            for model_name in ch['models']:
                for api_key in ch['api_keys']:
                    litellm_params: Dict[str, Any] = {
                        'model': model_name,
                    }
                    if api_key:
                        litellm_params['api_key'] = api_key
                    if ch['base_url']:
                        litellm_params['api_base'] = ch['base_url']
                    # Auto-inject aihubmix sponsored header
                    headers = dict(ch.get('extra_headers') or {})
                    if ch['base_url'] and 'aihubmix.com' in ch['base_url']:
                        headers.setdefault('APP-Code', 'GPIJ3886')
                    if headers:
                        litellm_params['extra_headers'] = headers

                    model_list.append({
                        'model_name': model_name,
                        'litellm_params': litellm_params,
                    })
        return model_list

    @classmethod
    def _legacy_keys_to_model_list(
        cls,
        gemini_keys: List[str],
        anthropic_keys: List[str],
        openai_keys: List[str],
        openai_base_url: Optional[str],
        deepseek_keys: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build Router model_list from legacy per-provider keys (backward compat).

        Returns a model_list where each provider's keys are expanded into
        deployments, keyed by placeholder model_name tokens.  The analyzer
        resolves actual model_names at call time from LITELLM_MODEL /
        LITELLM_FALLBACK_MODELS.
        """
        model_list: List[Dict[str, Any]] = []

        # Gemini keys
        for k in gemini_keys:
            if k and len(k) >= 8:
                model_list.append({
                    'model_name': '__legacy_gemini__',
                    'litellm_params': {'model': '__legacy_gemini__', 'api_key': k},
                })

        # Anthropic keys
        for k in anthropic_keys:
            if k and len(k) >= 8:
                model_list.append({
                    'model_name': '__legacy_anthropic__',
                    'litellm_params': {'model': '__legacy_anthropic__', 'api_key': k},
                })

        # OpenAI-compatible keys
        for k in openai_keys:
            if k and len(k) >= 8:
                params: Dict[str, Any] = {'model': '__legacy_openai__', 'api_key': k}
                if openai_base_url:
                    params['api_base'] = openai_base_url
                if openai_base_url and 'aihubmix.com' in openai_base_url:
                    params['extra_headers'] = {'APP-Code': 'GPIJ3886'}
                model_list.append({
                    'model_name': '__legacy_openai__',
                    'litellm_params': params,
                })

        # DeepSeek keys (native litellm provider — auto-resolves api_base)
        for k in (deepseek_keys or []):
            if k and len(k) >= 8:
                model_list.append({
                    'model_name': '__legacy_deepseek__',
                    'litellm_params': {
                        'model': '__legacy_deepseek__',
                        'api_key': k,
                    },
                })

        return model_list

    @classmethod
    def _parse_report_type(cls, value: str) -> str:
        """Parse REPORT_TYPE, fallback to simple for invalid values (supports brief)."""
        v = (value or 'simple').strip().lower()
        if v in ('simple', 'full', 'brief'):
            return v
        import logging
        logging.getLogger(__name__).warning(
            f"REPORT_TYPE '{value}' invalid, fallback to 'simple' (valid: simple/full/brief)"
        )
        return 'simple'

    @classmethod
    def _get_env_file_value(cls, key: str) -> Optional[str]:
        """Read one config key directly from the active `.env` file."""
        env_file = os.getenv("ENV_FILE")
        env_path = Path(env_file) if env_file else (Path(__file__).parent.parent / ".env")
        if not env_path.exists():
            return None

        try:
            env_values = dotenv_values(env_path)
        except Exception as exc:  # pragma: no cover - defensive branch
            logging.getLogger(__name__).warning(
                "Failed to read %s while resolving %s: %s",
                env_path,
                key,
                exc,
            )
            return None

        value = env_values.get(key)
        if value is None:
            return None
        return str(value)

    @classmethod
    def _resolve_env_value(
        cls,
        key: str,
        *,
        default: Optional[str] = None,
        prefer_env_file: bool = False,
    ) -> Optional[str]:
        """Resolve one env value, optionally preferring the persisted `.env` copy."""
        env_value = os.getenv(key)
        file_value = cls._get_env_file_value(key)

        should_prefer_file = prefer_env_file or key in cls._WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS
        if should_prefer_file and file_value is not None:
            if env_value is not None and cls._has_bootstrap_runtime_env_override(key):
                return env_value
            return file_value
        if env_value is not None:
            return env_value
        if file_value is not None:
            return file_value
        return default

    @classmethod
    def _capture_bootstrap_runtime_env_overrides(cls) -> None:
        """Remember process-provided runtime env overrides before dotenv mutates os.environ.

        Called by ``setup_env()`` **before** ``load_dotenv()``, so ``os.environ``
        only contains genuine process-level values (Docker ``environment:``,
        Dockerfile ``ENV``, shell exports, etc.).

        A key is treated as an explicit override when it is present in
        ``os.environ`` and either:
        * absent from the persisted ``.env`` file, **or**
        * present with a **different** value.

        When both values are identical, the distinction is irrelevant and we
        do **not** flag the key, so that a later ``.env`` update by WebUI can
        take effect on config reload without requiring a container restart.
        """
        if cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED:
            return

        explicit_overrides = set()
        present_keys = set()
        for key in cls._WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS:
            env_value = os.environ.get(key)
            if env_value is None:
                continue

            present_keys.add(key)
            file_value = cls._get_env_file_value(key)
            if file_value is None or env_value != file_value:
                explicit_overrides.add(key)

        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES = frozenset(explicit_overrides)
        cls._BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS = frozenset(present_keys)
        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED = True

    @classmethod
    def _has_bootstrap_runtime_env_override(cls, key: str) -> bool:
        cls._capture_bootstrap_runtime_env_overrides()
        return key in cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES

    @classmethod
    def _had_bootstrap_runtime_env_key(cls, key: str) -> bool:
        cls._capture_bootstrap_runtime_env_overrides()
        return key in cls._BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS

    @classmethod
    def _resolve_report_language_env_value(
        cls,
        preexisting_env_value: Optional[str],
    ) -> str:
        """Resolve REPORT_LANGUAGE while preserving real process env overrides."""
        file_value = cls._get_env_file_value("REPORT_LANGUAGE")
        env_value = os.getenv("REPORT_LANGUAGE")

        if preexisting_env_value is not None:
            env_text = preexisting_env_value.strip()
            file_text = (file_value or "").strip()
            if file_text and env_text and env_text.lower() != file_text.lower():
                env_file = os.getenv("ENV_FILE") or str(Path(__file__).parent.parent / ".env")
                logging.getLogger(__name__).warning(
                    "REPORT_LANGUAGE environment value '%s' overrides %s ('%s')",
                    preexisting_env_value,
                    env_file,
                    file_value,
                )
            return preexisting_env_value

        if file_value is not None:
            return file_value

        return env_value or "zh"

    @classmethod
    def _parse_report_language(cls, value: Optional[str]) -> str:
        """Parse REPORT_LANGUAGE, fallback to zh for invalid values."""
        normalized = normalize_report_language(value, default="zh")
        raw = (value or "").strip()
        if raw and not is_supported_report_language_value(raw):
            logging.getLogger(__name__).warning(
                "REPORT_LANGUAGE '%s' invalid, fallback to 'zh' (valid: zh/en)",
                value,
            )
        return normalized

    @classmethod
    def _resolve_realtime_source_priority(cls) -> str:
        """
        Resolve realtime source priority with automatic tushare injection.

        When TUSHARE_TOKEN is configured but REALTIME_SOURCE_PRIORITY is not
        explicitly set, automatically prepend 'tushare' to the default priority
        so that the paid data source is utilized for realtime quotes as well.
        """
        explicit = os.getenv('REALTIME_SOURCE_PRIORITY')
        default_priority = 'tencent,akshare_sina,efinance,akshare_em,tushare'

        if explicit:
            return explicit

        tushare_token = os.getenv('TUSHARE_TOKEN', '').strip()
        tushare_enabled = parse_env_bool(os.getenv('TUSHARE_ENABLED'), False)
        if tushare_enabled and tushare_token:
            # Token configured but no explicit priority override
            # Prepend tushare so the paid source is tried first
            import logging
            logger = logging.getLogger(__name__)
            resolved = f'tushare,{default_priority}'
            logger.info(
                f"TUSHARE_TOKEN detected, auto-injecting tushare into realtime priority: {resolved}"
            )
            return resolved

        return default_priority

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（主要用于测试）"""
        cls._instance = None
        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED = False
        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES = frozenset()
        cls._BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS = frozenset()


    def has_search_capability_enabled(self) -> bool:
        """Whether any search provider or local AkShare news fallback is available."""
        return bool(
            self.minimax_api_keys
            or self.brave_api_keys
            or self.serpapi_keys
            or importlib.util.find_spec("akshare") is not None
        )

    def is_agent_available(self) -> bool:
        """Check whether agent capabilities are usable.

        Decision table:

        +-----------------------+----------------------------------+---------+
        | AGENT_MODE env        | effective Agent primary model set| Result  |
        +-----------------------+----------------------------------+---------+
        | ``true``              | any                              | True    |
        | ``false`` (explicit)  | any                              | False   |
        | not set (default)     | yes                              | True    |
        | not set (default)     | no                               | False   |
        +-----------------------+----------------------------------+---------+

        This keeps backward compatibility: users who never touch
        ``AGENT_MODE`` get agent features automatically once they configure an
        Agent-effective model, while ``AGENT_MODE=false`` acts as an explicit
        kill-switch.
        """
        # Explicit AGENT_MODE takes full precedence
        if self._agent_mode_explicit:
            return self.agent_mode
        # Auto-detect: Agent inherits global model when AGENT_LITELLM_MODEL is empty.
        return bool(get_effective_agent_primary_model(self))

    def validate_structured(self) -> List[ConfigIssue]:
        """Return structured validation issues with severity levels.

        Covers the supported LLM configuration tiers:
        - LLM_CHANNELS (env)
        - Legacy per-provider keys

        Returns:
            List of ConfigIssue objects, each carrying a severity
            ("error" | "warning" | "info"), a human-readable message, and the
            primary environment variable / field name it relates to.
        """
        issues: List[ConfigIssue] = []

        # --- Data sources (informational only) ---
        if not self.tushare_token:
            issues.append(ConfigIssue(
                severity="info",
                message="未配置 Tushare Token，将使用其他数据源",
                field="TUSHARE_TOKEN",
            ))

        # --- LLM availability ---
        # llm_model_list is populated for channels / managed legacy keys.
        # Other LiteLLM-native providers (for example cohere/*) run through the
        # direct litellm env path and therefore do not populate llm_model_list.
        has_direct_env_model = bool(self.litellm_model) and _uses_direct_env_provider(self.litellm_model)
        if not self.llm_model_list and not has_direct_env_model:
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "未配置任何可用的 AI 模型接入（渠道 / API Key），"
                    "AI 分析功能将不可用"
                ),
                field="LLM_CHANNELS",
            ))
        elif not self.litellm_model:
            issues.append(ConfigIssue(
                severity="info",
                message=(
                    "尚未明确指定主模型，系统将自动从可用 API Key 推断。"
                    "建议尽早配置主模型（格式如 gemini/gemini-3.1-pro-preview）"
                ),
                field="LITELLM_MODEL",
            ))

        available_router_models = get_configured_llm_models(self.llm_model_list)
        available_router_model_set = set(available_router_models)

        def _has_runtime_source_for_model(model: str) -> bool:
            if not model or _uses_direct_env_provider(model):
                return True
            provider = _get_litellm_provider(model)
            if provider in {"gemini", "vertex_ai"}:
                return any(k and len(k) >= 8 for k in (self.gemini_api_keys or []))
            if provider == "anthropic":
                return any(k and len(k) >= 8 for k in (self.anthropic_api_keys or []))
            if provider == "deepseek":
                return any(k and len(k) >= 8 for k in (self.deepseek_api_keys or []))
            if provider == "openai":
                return any(k and len(k) >= 8 for k in (self.openai_api_keys or []))
            return False

        configured_agent_primary_model = bool((self.agent_litellm_model or "").strip())
        effective_agent_primary_model = get_effective_agent_primary_model(self)

        if available_router_model_set:
            if (
                self.litellm_model
                and not _uses_direct_env_provider(self.litellm_model)
                and self.litellm_model not in available_router_model_set
            ):
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "已配置的主模型未出现在当前渠道配置中。"
                        f" 当前可用模型：{', '.join(available_router_models[:6])}"
                    ),
                    field="LITELLM_MODEL",
                ))

            if (
                configured_agent_primary_model
                and effective_agent_primary_model
                and not _uses_direct_env_provider(effective_agent_primary_model)
                and effective_agent_primary_model not in available_router_model_set
            ):
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "已配置的 Agent 主模型未出现在当前渠道配置中。"
                        f" 当前可用模型：{', '.join(available_router_models[:6])}"
                    ),
                    field="AGENT_LITELLM_MODEL",
                ))

            invalid_fallbacks = [
                model for model in (self.litellm_fallback_models or [])
                if model and model not in available_router_model_set
                and not _uses_direct_env_provider(model)
            ]
            if invalid_fallbacks:
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "备选模型中包含未在当前渠道或高级模型路由配置中声明的模型："
                        f"{', '.join(invalid_fallbacks[:3])}"
                    ),
                    field="LITELLM_FALLBACK_MODELS",
                ))

            if (
                self.vision_model
                and not _uses_direct_env_provider(self.vision_model)
                and self.vision_model not in available_router_model_set
            ):
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "VISION_MODEL 未出现在当前渠道声明中。"
                        f" 当前可用模型：{', '.join(available_router_models[:6])}"
                    ),
                    field="VISION_MODEL",
                ))
        elif (
            configured_agent_primary_model
            and effective_agent_primary_model
            and not _has_runtime_source_for_model(effective_agent_primary_model)
        ):
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "已配置 Agent 主模型，但未找到可用的运行时来源"
                    "（启用渠道或匹配的 API Key）。"
                ),
                field="AGENT_LITELLM_MODEL",
            ))

        # --- Search engine (informational only) ---
        if not self.has_search_capability_enabled():
            issues.append(ConfigIssue(
                severity="info",
                message="未配置搜索引擎能力 (MiniMax/Brave/SerpAPI)，新闻搜索功能将不可用",
                field="MINIMAX_API_KEYS",
            ))

        # --- Deprecated field migration hints ---
        if os.getenv("OPENAI_VISION_MODEL"):
            issues.append(ConfigIssue(
                severity="info",
                message=(
                    "OPENAI_VISION_MODEL 已废弃，请改用 VISION_MODEL。"
                    "当前值已自动迁移，建议更新配置文件以消除此提示。"
                ),
                field="OPENAI_VISION_MODEL",
            ))

        # --- Vision key availability ---
        # Only warn when user explicitly set VISION_MODEL (or OPENAI_VISION_MODEL alias).
        # Skipped when vision_model is empty (Vision not intentionally configured).
        if self.vision_model:
            # Maps provider prefix → the corresponding key list tracked by Config.
            # vertex_ai shares gemini keys; other LiteLLM-native providers are not
            # in this map (their keys come from env vars, which we cannot inspect here).
            _VISION_KEY_MAP = {
                "gemini": self.gemini_api_keys,
                "vertex_ai": self.gemini_api_keys,
                "anthropic": self.anthropic_api_keys,
                "openai": self.openai_api_keys,
                "deepseek": self.deepseek_api_keys,
            }
            # Derive the primary model's provider prefix so that its key is also
            # checked even when the provider is absent from VISION_PROVIDER_PRIORITY.
            _primary_prefix = (
                self.vision_model.split("/")[0]
                if "/" in self.vision_model
                else "openai"
            )
            _priority_providers = [
                p.strip().lower()
                for p in self.vision_provider_priority.split(",")
                if p.strip()
            ]
            # Union: fallback providers + primary model's own provider
            _all_providers = {_primary_prefix} | set(_priority_providers)

            # Align with get_api_keys_for_model: keys must be non-empty and len >= 8
            _has_any_key = any(
                any(k and len(k) >= 8 for k in (_VISION_KEY_MAP.get(p) or []))
                for p in _all_providers
                if p in _VISION_KEY_MAP
            )
            if not _has_any_key:
                _checked = sorted(_all_providers & _VISION_KEY_MAP.keys())
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "VISION_MODEL 已配置，但未找到可用的 Vision API Key "
                        f"（已检查：{', '.join(_checked)}）。"
                        "图片股票代码提取功能将不可用，请配置对应的 API Key。"
                    ),
                    field="VISION_MODEL",
                ))

        return issues

    def validate(self) -> List[str]:
        """Return validation messages as plain strings (backward-compatible).

        Internally delegates to validate_structured().  Callers that only need
        the human-readable strings can continue to use this method unchanged.

        Returns:
            List of message strings, one per ConfigIssue.
        """
        return [issue.message for issue in self.validate_structured()]
    
    def get_db_url(self) -> str:
        """
        获取 SQLAlchemy 数据库连接 URL
        
        自动创建数据库目录（如果不存在）
        """
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.absolute()}"


# === 便捷的配置访问函数 ===
def get_config() -> Config:
    """获取全局配置实例的快捷方式"""
    return Config.get_instance()


# ============================================================
# Shared LLM helpers (used by both analyzer and agent/llm_adapter)
# ============================================================

def get_api_keys_for_model(model: str, config: Config) -> List[str]:
    """Return explicitly managed API keys for a litellm model (legacy path only).

    When llm_model_list is populated (channels / YAML), the Router handles key
    selection, so this function is not needed.  Kept for backward compat when
    no Router is built and a direct litellm.completion() call is needed.
    """
    provider = _get_litellm_provider(model)
    if provider in {"gemini", "vertex_ai"}:
        return [k for k in config.gemini_api_keys if k and len(k) >= 8]
    if provider == "anthropic":
        return [k for k in config.anthropic_api_keys if k and len(k) >= 8]
    if provider == "deepseek":
        return [k for k in config.deepseek_api_keys if k and len(k) >= 8]
    if provider == "openai":
        return [k for k in config.openai_api_keys if k and len(k) >= 8]
    # Other LiteLLM-native providers – API key resolved from env vars
    return []


def extra_litellm_params(model: str, config: Config) -> Dict[str, Any]:
    """Build extra litellm params for a model (legacy path only).

    When llm_model_list is populated, the Router already carries api_base
    and headers per-deployment, so this is not called.
    """
    params: Dict[str, Any] = {}
    # deepseek/ provider: litellm auto-resolves api_base, no manual override needed
    if model.startswith("deepseek/"):
        return params
    if model.startswith("openai/") or "/" not in model:
        if config.openai_base_url:
            params["api_base"] = config.openai_base_url
        if config.openai_base_url and "aihubmix.com" in config.openai_base_url:
            params["extra_headers"] = {"APP-Code": "GPIJ3886"}
    return params


if __name__ == "__main__":
    # 测试配置加载
    config = get_config()
    print("=== 配置加载测试 ===")
    print(f"数据库路径: {config.database_path}")
    print(f"最大并发数: {config.max_workers}")
    print(f"调试模式: {config.debug}")
    
    # 验证配置
    warnings = config.validate()
    if warnings:
        print("\n配置验证结果:")
        for w in warnings:
            print(f"  - {w}")
