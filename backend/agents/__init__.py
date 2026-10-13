"""PydanticAI agents package for ClipBuilder.

Public re-exports for convenient imports::

    from agents import StepOutput, ActionType, extract_steps

All imports are lazy so that the rest of the backend keeps working even
when ``pydantic-ai`` is not installed.  A missing dependency will only
surface when the symbols are actually *used*.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger("clipbuilder.agents")

# These imports are only visible to static type checkers (mypy, pyright,
# VSCode Pylance). They are NOT executed at runtime, so a missing
# pydantic-ai install never causes an ImportError on startup.
if TYPE_CHECKING:
    from agents.step_extractor import (
        ActionType,
        StepExtractionDeps,
        StepOutput,
        extract_steps,
        step_extractor_agent,
    )

__all__: list[str] = [
    "ActionType",
    "StepExtractionDeps",
    "StepOutput",
    "extract_steps",
    "step_extractor_agent",
]


def __getattr__(name: str):
    """Lazy import: only resolve symbols when actually accessed."""
    if name in __all__:
        try:
            from agents import step_extractor  # noqa: WPS433
            return getattr(step_extractor, name)
        except ImportError as exc:
            raise ImportError(
                f"Cannot import '{name}' from agents.step_extractor. "
                f"Make sure 'pydantic-ai' is installed: "
                f"pip install 'pydantic-ai[google,openai]>=0.2.14'"
            ) from exc
    raise AttributeError(f"module 'agents' has no attribute {name!r}")
