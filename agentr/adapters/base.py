"""
agentr.adapters.base: Abstract base class for coding agent integrations.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, List, Tuple
from ..core import SessionInfo, SearchResult


class BaseAgentAdapter(ABC):
    """Protocol for integrating a terminal AI coding agent into agentr."""

    name: str
    display_name: str
    tag: str
    is_experimental: bool = False

    @abstractmethod
    def detect(self) -> bool:
        """Return True if the agent is installed or has local storage."""
        pass

    @abstractmethod
    def list_sessions(self) -> List[SessionInfo]:
        """Return list of recent sessions sorted by timestamp descending."""
        pass

    @abstractmethod
    def search(self, query: str) -> List[SearchResult]:
        """Deep search agent transcripts and sessions for query."""
        pass

    @abstractmethod
    def preview(self, cid: str, query: Optional[str] = None) -> None:
        """Print colored transcript preview of a session."""
        pass

    @abstractmethod
    def resume(self, cid: str, workdir: str) -> None:
        """Execute native CLI command to resume the session in workdir."""
        pass

    @abstractmethod
    def extract_briefing_context(
        self, cid: str, workdir: str
    ) -> Tuple[str, str, List[str], List[str]]:
        """Return (title, workdir, user_prompts, assistant_messages) for handoff."""
        pass

    @abstractmethod
    def receive_handoff(self, briefing: str, title: str, workdir: str, non_interactive: bool = False, **kwargs) -> None:
        """Launch the agent with handoff briefing context."""
        pass
