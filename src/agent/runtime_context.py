"""Runtime context for Agent tool execution."""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional


_agent_runtime_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "agent_runtime_context",
    default={},
)


def get_agent_runtime_context() -> Dict[str, Any]:
    """Return the current Agent runtime context."""
    return dict(_agent_runtime_context.get() or {})


def is_agent_chat_mode() -> bool:
    """Return True when tools run for the interactive AI chat page."""
    return get_agent_runtime_context().get("mode") == "chat"


def get_agent_topic_key() -> Optional[str]:
    """Return the normalized AI chat topic key, if available."""
    value = get_agent_runtime_context().get("topic_key")
    return str(value) if value else None


@contextmanager
def agent_runtime_context(**values: Any) -> Iterator[None]:
    """Temporarily set runtime values for Agent tool calls."""
    current = dict(_agent_runtime_context.get() or {})
    current.update({key: value for key, value in values.items() if value is not None})
    token = _agent_runtime_context.set(current)
    try:
        yield
    finally:
        _agent_runtime_context.reset(token)
