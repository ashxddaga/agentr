"""
agentr.adapters: Adapter registry for terminal coding agents.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from .base import BaseAgentAdapter
from .agy import AgyAdapter
from .opencode import OpenCodeAdapter
from .freebuff import FreebuffAdapter
from .grok import GrokAdapter
from .kimi import KimiAdapter
from .claude import ClaudeAdapter

ADAPTERS: Dict[str, BaseAgentAdapter] = {
    "agy": AgyAdapter(),
    "opencode": OpenCodeAdapter(),
    "freebuff": FreebuffAdapter(),
    "grok": GrokAdapter(),
    "kimi": KimiAdapter(),
    "claude": ClaudeAdapter(),
}


def get_adapter(name: str) -> Optional[BaseAgentAdapter]:
    """Retrieve an agent adapter by name."""
    return ADAPTERS.get(name.lower())


def get_active_adapters(include_experimental: bool = False) -> List[BaseAgentAdapter]:
    """Return all available adapters detected on this system."""
    active = []
    for adapter in ADAPTERS.values():
        if not include_experimental and adapter.is_experimental:
            continue
        if adapter.detect():
            active.append(adapter)
    return active


def get_all_adapters() -> List[BaseAgentAdapter]:
    """Return all registered adapters."""
    return list(ADAPTERS.values())
