# -*- coding: utf-8 -*-
"""Loader for lightweight Agent platform YAML definitions."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from src.agent.configs.models import AgentCatalog


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_AGENT_CATALOG_PATH = PROJECT_ROOT / "agent_configs" / "catalog.yaml"


@lru_cache(maxsize=8)
def _load_agent_catalog_cached(path_text: str) -> AgentCatalog:
    path = Path(path_text)
    if not path.is_file():
        raise FileNotFoundError(f"Agent catalog not found: {path}")
    with path.open("r", encoding="utf-8") as file_obj:
        data = yaml.safe_load(file_obj) or {}
    return AgentCatalog.from_dict(data, source_path=str(path))


def load_agent_catalog(path: str | Path | None = None) -> AgentCatalog:
    """Load the Agent catalog from YAML with a small process-local cache."""
    catalog_path = Path(path) if path else DEFAULT_AGENT_CATALOG_PATH
    return _load_agent_catalog_cached(str(catalog_path.resolve()))


def validate_agent_catalog_yaml(content: str, *, source_path: str = "<inline>") -> AgentCatalog:
    """Validate catalog YAML content and return parsed catalog definitions."""
    data = yaml.safe_load(content) or {}
    return AgentCatalog.from_dict(data, source_path=source_path)


def read_agent_catalog_text(path: str | Path | None = None) -> str:
    """Read raw catalog YAML text."""
    catalog_path = Path(path) if path else DEFAULT_AGENT_CATALOG_PATH
    return catalog_path.read_text(encoding="utf-8")


def write_agent_catalog_text(content: str, path: str | Path | None = None) -> AgentCatalog:
    """Validate and persist raw catalog YAML text, then clear cached catalog."""
    catalog_path = Path(path) if path else DEFAULT_AGENT_CATALOG_PATH
    catalog = validate_agent_catalog_yaml(content, source_path=str(catalog_path))
    catalog_path.write_text(content, encoding="utf-8")
    clear_agent_catalog_cache()
    return catalog


def clear_agent_catalog_cache() -> None:
    """Clear cached catalog definitions after future edit operations."""
    _load_agent_catalog_cached.cache_clear()
