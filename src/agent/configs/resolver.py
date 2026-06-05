# -*- coding: utf-8 -*-
"""Resolve Agent catalog profiles into runtime config overrides."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.agent.configs.loader import load_agent_catalog
from src.agent.configs.models import AgentDefinition, AgentProfile


EXECUTABLE_STOCK_PROFILE_MODES = {"quick", "standard", "full", "specialist"}
EXECUTABLE_SINGLE_AGENT_TYPES = {"single_agent_executor"}


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


def find_agent_definition(agent_id: str) -> AgentDefinition:
    """Return an agent definition from the catalog by id."""
    normalized_id = str(agent_id or "").strip()
    if not normalized_id:
        raise AgentProfileResolveError("agent_id is empty")

    catalog = load_agent_catalog()
    for agent in catalog.agents:
        if agent.id == normalized_id:
            return agent
    raise AgentProfileResolveError(f"Unknown agent definition: {normalized_id}")


def resolve_profile_runtime_config(config: Any, profile_id: str | None) -> Any:
    """Return a per-request config with runtime overrides for a profile.

    This does not mutate the process-wide Config singleton. The first executable
    phase maps stock profiles to the existing AgentOrchestrator modes.
    """
    normalized_id = str(profile_id or "").strip()
    if not normalized_id:
        return config

    profile = find_agent_profile(normalized_id)
    if profile.mode == "chat":
        if not profile.workflow:
            raise AgentProfileResolveError(f"Agent profile '{profile.id}' has no workflow agent")
        agent = find_agent_definition(profile.workflow[0])
        if agent.type not in EXECUTABLE_SINGLE_AGENT_TYPES:
            raise AgentProfileResolveError(
                f"Agent profile '{profile.id}' points to unsupported agent type '{agent.type}'"
            )
        runtime_config = replace(
            config,
            agent_arch="single",
            agent_max_steps=agent.max_steps if agent.max_steps is not None else config.agent_max_steps,
        )
        setattr(runtime_config, "agent_catalog_profile_id", profile.id)
        setattr(runtime_config, "agent_catalog_agent_id", agent.id)
        setattr(runtime_config, "agent_catalog_agent", agent)
        return runtime_config

    if profile.asset_type != "stock" or profile.mode not in EXECUTABLE_STOCK_PROFILE_MODES:
        raise AgentProfileResolveError(
            f"Agent profile '{profile.id}' is configured but not executable yet"
        )

    return replace(
        config,
        agent_arch="multi",
        agent_orchestrator_mode=profile.mode,
    )
