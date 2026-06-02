# -*- coding: utf-8 -*-
"""Resolve Agent catalog profiles into runtime config overrides."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.agent.configs.loader import load_agent_catalog
from src.agent.configs.models import AgentProfile


EXECUTABLE_STOCK_PROFILE_MODES = {"quick", "standard", "full", "specialist"}


class AgentProfileResolveError(ValueError):
    """Raised when a requested Agent profile cannot be mapped to runtime."""


def find_agent_profile(profile_id: str) -> AgentProfile:
    """Return a profile from the catalog by id."""
    normalized_id = str(profile_id or "").strip()
    if not normalized_id:
        raise AgentProfileResolveError("profile_id is empty")

    catalog = load_agent_catalog()
    for profile in catalog.profiles:
        if profile.id == normalized_id:
            return profile
    raise AgentProfileResolveError(f"Unknown agent profile: {normalized_id}")


def resolve_profile_runtime_config(config: Any, profile_id: str | None) -> Any:
    """Return a per-request config with runtime overrides for a profile.

    This does not mutate the process-wide Config singleton. The first executable
    phase maps stock profiles to the existing AgentOrchestrator modes.
    """
    normalized_id = str(profile_id or "").strip()
    if not normalized_id:
        return config

    profile = find_agent_profile(normalized_id)
    if profile.asset_type != "stock" or profile.mode not in EXECUTABLE_STOCK_PROFILE_MODES:
        raise AgentProfileResolveError(
            f"Agent profile '{profile.id}' is configured but not executable yet"
        )

    return replace(
        config,
        agent_arch="multi",
        agent_orchestrator_mode=profile.mode,
    )
