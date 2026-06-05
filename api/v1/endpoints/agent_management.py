# -*- coding: utf-8 -*-
"""
Read-only Agent management overview API.

This endpoint exposes the current lightweight Agent runtime assets without
changing any execution behavior.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from src.agent.configs import load_agent_catalog, read_agent_catalog_text, validate_agent_catalog_yaml, write_agent_catalog_text
from src.agent.factory import get_skill_manager, get_tool_registry, invalidate_skill_manager_cache
from src.agent.skills.base import load_skill_from_markdown, load_skill_from_yaml
from src.config import get_config, get_effective_agent_primary_model


router = APIRouter()


class AgentCatalogTextResponse(BaseModel):
    content: str
    source_path: str


class AgentCatalogUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class AgentCatalogUpdateResponse(BaseModel):
    success: bool
    message: str
    overview: Dict[str, Any]


class AgentSkillTextResponse(BaseModel):
    id: str
    content: str
    source_path: str


class AgentSkillUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class AgentSkillUpdateResponse(BaseModel):
    success: bool
    message: str
    overview: Dict[str, Any]


PROJECT_ROOT = Path(__file__).resolve().parents[3]
EDITABLE_SKILL_SUFFIXES = {".yaml", ".yml"}


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _resolve_editable_skill_path(skill_id: str) -> Path:
    config = get_config()
    manager = get_skill_manager(config)
    skill = manager.get(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_id}")

    raw_path = _safe_text(getattr(skill, "entrypoint", ""))
    if not raw_path:
        raise HTTPException(status_code=400, detail="Skill has no editable entrypoint")

    path = Path(raw_path).resolve()
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Skill entrypoint is outside the project") from exc

    is_markdown_skill = path.name == "SKILL.md"
    if path.suffix not in EDITABLE_SKILL_SUFFIXES and not is_markdown_skill:
        raise HTTPException(status_code=400, detail="Skill entrypoint type is not editable")
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Skill entrypoint not found: {path}")
    return path


def _validate_skill_content(path: Path, content: str) -> None:
    suffix = ".md" if path.name == "SKILL.md" else path.suffix
    with NamedTemporaryFile("w", encoding="utf-8", suffix=suffix) as temp_file:
        temp_file.write(content)
        temp_file.flush()
        temp_path = Path(temp_file.name)
        if path.name == "SKILL.md":
            load_skill_from_markdown(temp_path)
        else:
            load_skill_from_yaml(temp_path)


def _read_skill_text(skill_id: str) -> AgentSkillTextResponse:
    path = _resolve_editable_skill_path(skill_id)
    return AgentSkillTextResponse(
        id=skill_id,
        content=path.read_text(encoding="utf-8"),
        source_path=str(path),
    )


def _serialize_skills(config: Any) -> List[Dict[str, Any]]:
    manager = get_skill_manager(config)
    skills = []
    for skill in manager.list_skills():
        skills.append(
            {
                "id": _safe_text(getattr(skill, "name", "")),
                "name": _safe_text(getattr(skill, "display_name", "")) or _safe_text(getattr(skill, "name", "")),
                "description": _safe_text(getattr(skill, "description", "")),
                "category": _safe_text(getattr(skill, "category", "trend")) or "trend",
                "source": _safe_text(getattr(skill, "source", "builtin")) or "builtin",
                "source_path": _safe_text(getattr(skill, "entrypoint", "")),
                "default_active": bool(getattr(skill, "default_active", False)),
                "default_router": bool(getattr(skill, "default_router", False)),
                "user_invocable": bool(getattr(skill, "user_invocable", True)),
                "required_tools": list(getattr(skill, "required_tools", []) or []),
                "allowed_tools": list(getattr(skill, "allowed_tools", []) or []),
            }
        )
    return sorted(skills, key=lambda item: (item["category"], item["name"], item["id"]))


def _serialize_tools() -> List[Dict[str, Any]]:
    registry = get_tool_registry()
    tools = []
    for tool in registry.list_tools():
        tools.append(
            {
                "id": tool.name,
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "parameters": [
                    {
                        "name": parameter.name,
                        "type": parameter.type,
                        "description": parameter.description,
                        "required": parameter.required,
                    }
                    for parameter in tool.parameters
                ],
            }
        )
    return sorted(tools, key=lambda item: (item["category"], item["name"]))


@router.get("/overview")
def get_agent_management_overview() -> Dict[str, Any]:
    """Return current Agent runtime assets and YAML-defined management catalog."""
    config = get_config()
    catalog = load_agent_catalog()
    profiles = [profile.to_dict() for profile in catalog.profiles]
    agents = [agent.to_dict() for agent in catalog.agents]
    skills = _serialize_skills(config)
    tools = _serialize_tools()
    tool_category_counts = Counter(tool["category"] for tool in tools)
    skill_category_counts = Counter(skill["category"] for skill in skills)
    effective_model = get_effective_agent_primary_model(config)

    return {
        "runtime": {
            "agent_mode": bool(config.agent_mode),
            "agent_mode_explicit": bool(getattr(config, "_agent_mode_explicit", False)),
            "agent_available": bool(config.is_agent_available()),
            "agent_arch": config.agent_arch,
            "orchestrator_mode": config.agent_orchestrator_mode,
            "max_steps": config.agent_max_steps,
            "skill_routing": config.agent_skill_routing,
            "configured_skills": config.agent_skills,
            "skill_dir": config.agent_skill_dir,
            "effective_model": effective_model,
            "chat_entrypoint": "/api/v1/agent/chat/stream",
            "analysis_entrypoint": "/api/v1/analysis/analyze",
        },
        "profiles": profiles,
        "agents": agents,
        "skills": skills,
        "tools": tools,
        "catalog": {
            "version": catalog.version,
            "source_path": catalog.source_path,
        },
        "summary": {
            "profile_count": len(profiles),
            "agent_count": len(agents),
            "skill_count": len(skills),
            "tool_count": len(tools),
            "skill_category_counts": dict(skill_category_counts),
            "tool_category_counts": dict(tool_category_counts),
        },
    }


@router.get("/catalog", response_model=AgentCatalogTextResponse)
def get_agent_catalog_text() -> AgentCatalogTextResponse:
    """Return raw Agent catalog YAML for editing."""
    catalog = load_agent_catalog()
    return AgentCatalogTextResponse(
        content=read_agent_catalog_text(),
        source_path=catalog.source_path,
    )


@router.post("/catalog/validate")
def validate_agent_catalog(payload: AgentCatalogUpdateRequest) -> Dict[str, Any]:
    """Validate raw Agent catalog YAML without persisting changes."""
    try:
        catalog = validate_agent_catalog_yaml(payload.content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Agent catalog validation failed: {exc}") from exc
    return {
        "success": True,
        "message": "Agent catalog validation passed",
        "profile_count": len(catalog.profiles),
        "agent_count": len(catalog.agents),
    }


@router.put("/catalog", response_model=AgentCatalogUpdateResponse)
def update_agent_catalog(payload: AgentCatalogUpdateRequest) -> AgentCatalogUpdateResponse:
    """Validate and persist raw Agent catalog YAML."""
    try:
        write_agent_catalog_text(payload.content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Agent catalog save failed: {exc}") from exc
    return AgentCatalogUpdateResponse(
        success=True,
        message="Agent catalog saved",
        overview=get_agent_management_overview(),
    )


@router.get("/skills/{skill_id}", response_model=AgentSkillTextResponse)
def get_agent_skill_text(skill_id: str) -> AgentSkillTextResponse:
    """Return raw skill definition text for editing."""
    return _read_skill_text(skill_id)


@router.put("/skills/{skill_id}", response_model=AgentSkillUpdateResponse)
def update_agent_skill_text(skill_id: str, payload: AgentSkillUpdateRequest) -> AgentSkillUpdateResponse:
    """Validate and persist raw skill definition text."""
    path = _resolve_editable_skill_path(skill_id)
    try:
        _validate_skill_content(path, payload.content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Skill validation failed: {exc}") from exc

    try:
        path.write_text(payload.content, encoding="utf-8")
        invalidate_skill_manager_cache()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Skill save failed: {exc}") from exc

    return AgentSkillUpdateResponse(
        success=True,
        message="Skill saved",
        overview=get_agent_management_overview(),
    )
