# -*- coding: utf-8 -*-
"""Typed config objects for Agent platform definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _string_list(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_safe_text(item) for item in value if _safe_text(item)]
    text = _safe_text(value)
    return [text] if text else []


@dataclass(frozen=True)
class AgentProfile:
    id: str
    name: str
    asset_type: str
    status: str
    mode: str
    workflow: List[str]
    description: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentProfile":
        profile_id = _safe_text(data.get("id"))
        name = _safe_text(data.get("name"))
        if not profile_id or not name:
            raise ValueError("Agent profile requires non-empty id and name")
        return cls(
            id=profile_id,
            name=name,
            asset_type=_safe_text(data.get("asset_type")) or "stock",
            status=_safe_text(data.get("status")) or "planned",
            mode=_safe_text(data.get("mode")) or profile_id,
            workflow=_string_list(data.get("workflow")),
            description=_safe_text(data.get("description")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "asset_type": self.asset_type,
            "status": self.status,
            "mode": self.mode,
            "workflow": list(self.workflow),
            "description": self.description,
        }


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    display_name: str
    description: str
    type: str = "llm_agent"
    max_steps: Optional[int] = None
    tools: List[str] = field(default_factory=list)
    skills: Dict[str, Any] = field(default_factory=dict)
    prompt: Dict[str, str] = field(default_factory=dict)
    model: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentDefinition":
        agent_id = _safe_text(data.get("id"))
        name = _safe_text(data.get("name"))
        if not agent_id or not name:
            raise ValueError("Agent definition requires non-empty id and name")

        raw_max_steps = data.get("max_steps")
        max_steps = None
        if raw_max_steps is not None:
            try:
                max_steps = int(raw_max_steps)
            except (TypeError, ValueError):
                raise ValueError(f"Agent {agent_id} max_steps must be an integer or null") from None

        skills = data.get("skills") if isinstance(data.get("skills"), dict) else {}
        raw_prompt = data.get("prompt") if isinstance(data.get("prompt"), dict) else {}
        prompt = {str(key): _safe_text(value) for key, value in raw_prompt.items()}

        return cls(
            id=agent_id,
            name=name,
            display_name=_safe_text(data.get("display_name")) or name,
            description=_safe_text(data.get("description")),
            type=_safe_text(data.get("type")) or "llm_agent",
            max_steps=max_steps,
            tools=_string_list(data.get("tools")),
            skills=dict(skills),
            prompt=prompt,
            model=_safe_text(data.get("model")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "type": self.type,
            "max_steps": self.max_steps,
            "tools": list(self.tools),
            "skills": dict(self.skills),
            "prompt": dict(self.prompt),
            "model": self.model,
        }


@dataclass(frozen=True)
class AgentCatalog:
    version: int
    profiles: List[AgentProfile]
    agents: List[AgentDefinition]
    source_path: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any], *, source_path: str) -> "AgentCatalog":
        if not isinstance(data, dict):
            raise ValueError("Agent catalog must be a YAML mapping")
        profiles_raw = data.get("profiles") or []
        agents_raw = data.get("agents") or []
        if not isinstance(profiles_raw, list):
            raise ValueError("Agent catalog profiles must be a list")
        if not isinstance(agents_raw, list):
            raise ValueError("Agent catalog agents must be a list")

        profiles = [AgentProfile.from_dict(item) for item in profiles_raw if isinstance(item, dict)]
        agents = [AgentDefinition.from_dict(item) for item in agents_raw if isinstance(item, dict)]
        return cls(
            version=int(data.get("version") or 1),
            profiles=profiles,
            agents=agents,
            source_path=source_path,
        )
