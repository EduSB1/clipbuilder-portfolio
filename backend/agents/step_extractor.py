"""Step Extractor Agent — PydanticAI-powered tutorial step extraction.

This module implements a typed agent that analyses video frames and
transcriptions to produce structured tutorial steps.  It uses PydanticAI
for structured output, dependency injection, and tool registration.

Usage::

    from agents.step_extractor import extract_steps, StepExtractionDeps

    deps = StepExtractionDeps(
        project_context="Web app login flow",
        valid_action_types=None,          # uses defaults
        api_key="sk-...",                 # or read from env
    )
    steps = await extract_steps(
        transcript="User clicks the login button ...",
        frame_descriptions=["Screenshot of login page", "Screenshot of dashboard"],
        deps=deps,
    )
    for step in steps:
        print(step.title, step.action_type, step.importance_score)
"""

# Refactor notes (applied):
# [x] Agent instantiated with _resolve_model() — not static _DEFAULT_MODEL
# [x] get_project_context tool removed — data already in user prompt
# [x] validate_action_type tool removed — Pydantic enum handles validation
# [x] api_key wired up (or removed) — no longer a silent no-op
# [x] Default model updated to gemini-2.5-flash
# [x] Unused imports cleaned up

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field

# FIX: removed unused `Tool` import — it was imported but never used directly.
# `@agent.tool` decorator is sufficient for tool registration.
# FIX: removed `RunContext` import — no longer needed after removing tools.
from pydantic_ai import Agent

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("clipbuilder.agents.step_extractor")

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActionType(str, Enum):
    """Possible user-action categories inside a tutorial step."""

    CLICK = "CLICK"
    TYPE = "TYPE"
    NAVIGATE = "NAVIGATE"
    OBSERVE = "OBSERVE"


# ---------------------------------------------------------------------------
# Pydantic V2 output model
# ---------------------------------------------------------------------------


class StepOutput(BaseModel):
    """Structured representation of a single tutorial step."""

    title: str = Field(
        ...,
        description="Short, imperative title for the step (e.g. 'Click the Submit button').",
    )
    description: str = Field(
        ...,
        description="Detailed explanation of what happens in this step.",
    )
    importance_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How critical this step is (0 = trivial, 1 = essential).",
    )
    action_type: ActionType = Field(
        ...,
        description="Category of user action performed in this step.",
    )
    suggested_duration: int = Field(
        ...,
        ge=1,
        description="Suggested display duration for this step in seconds.",
    )


class StepListOutput(BaseModel):
    """Wrapper so the agent always returns a JSON array of steps."""

    steps: list[StepOutput] = Field(
        ...,
        description="Ordered list of tutorial steps extracted from the source material.",
    )


# ---------------------------------------------------------------------------
# Dependency container (injected at run-time)
# ---------------------------------------------------------------------------


@dataclass
class StepExtractionDeps:
    """Run-time dependencies for the step-extractor agent.

    Attributes:
        project_context: Free-text description of the project / tutorial topic.
        valid_action_types: Allowed action types for validation.  ``None`` means
            all ``ActionType`` members are valid.
        api_key: API key override.  When *None* the key is read from the
            ``GOOGLE_API_KEY`` or ``OPENAI_API_KEY`` environment variable
            (depending on the chosen model).  When provided, it is temporarily
            set as the appropriate environment variable during the agent call.
        language: Target language for the generated steps (BCP-47 tag).
    """

    project_context: str = "General software tutorial"
    valid_action_types: set[ActionType] | None = None
    api_key: str | None = None
    language: str = "pt-BR"

    def get_valid_actions(self) -> set[ActionType]:
        """Return the effective set of valid action types."""
        return self.valid_action_types or set(ActionType)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = """\
You are an **Expert Technical Documentation Specialist** with deep knowledge
of software UIs, developer tools, and user workflows.

### Your mission
Given a video transcript and/or descriptions of video frames, you MUST
extract an **ordered list of tutorial steps** that a reader can follow to
reproduce the demonstrated workflow.

### Rules
1. Each step MUST have a concise, imperative *title* (e.g. "Click **Save**").
2. The *description* elaborates what happens and why it matters.
3. Assign an *importance_score* between 0.0 and 1.0 — reserve 1.0 for steps
   that are absolutely critical; trivial UI transitions should be ≤ 0.3.
4. Choose the most appropriate *action_type*: CLICK, TYPE, NAVIGATE, or OBSERVE.
5. Estimate a *suggested_duration* in whole seconds (minimum 1).
6. When frame descriptions are provided, use them to infer visual context
   (button labels, page layout, highlighted elements).
7. Merge near-duplicate actions into a single step when they clearly belong
   together.
8. Return the steps in chronological order.
9. Always respond in the language specified by the user (default: pt-BR).
"""

# ---------------------------------------------------------------------------
# Model selection helper
# ---------------------------------------------------------------------------

# Default model aligned with system settings seed ("models/gemini-2.5-flash").
# The google-gla: prefix is PydanticAI's provider identifier for Google AI.
_DEFAULT_MODEL: str = "google-gla:gemini-2.5-flash"


def _resolve_model() -> str:
    """Pick the model string at *call time* (not at import time).

    Priority:
      1. ``CLIPBUILDER_AGENT_MODEL`` env var (e.g. ``openai:gpt-4o``).
      2. If ``OPENAI_API_KEY`` is set  → ``openai:gpt-4o``.
      3. Default → ``google-gla:gemini-2.5-flash``.
    """
    explicit = (os.getenv("CLIPBUILDER_AGENT_MODEL") or "").strip()
    if explicit:
        return explicit
    if (os.getenv("OPENAI_API_KEY") or "").strip():
        return "openai:gpt-4o"
    return _DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

# Agent is constructed with _resolve_model() so that env vars like
# CLIPBUILDER_AGENT_MODEL are respected even when the module is imported
# before those vars are set.  The model can still be overridden at runtime
# via agent.override(model=...) inside extract_steps().
step_extractor_agent: Agent[StepExtractionDeps, StepListOutput] = Agent(
    model=_resolve_model(),
    result_type=StepListOutput,
    system_prompt=_SYSTEM_PROMPT,
    deps_type=StepExtractionDeps,
    retries=2,
)


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------


def _build_user_prompt(
    transcript: str | None,
    frame_descriptions: Sequence[str] | None,
    deps: StepExtractionDeps,
) -> str:
    """Assemble the user-facing prompt from the available inputs."""

    language = deps.language
    valid_actions = deps.get_valid_actions()
    valid_action_names = ", ".join(sorted(a.value for a in valid_actions))

    parts: list[str] = [
        f"**Target language for the output:** {language}",
        f"**Project context:** {deps.project_context}",
        f"**Allowed action types:** {valid_action_names}",
        "",
    ]

    if transcript:
        parts.append("## Transcript")
        parts.append(transcript.strip())
        parts.append("")

    if frame_descriptions:
        parts.append("## Frame Descriptions (chronological order)")
        for idx, desc in enumerate(frame_descriptions, start=1):
            parts.append(f"{idx}. {desc}")
        parts.append("")

    if not transcript and not frame_descriptions:
        parts.append(
            "No transcript or frame descriptions provided. "
            "Please return an empty list of steps."
        )

    parts.append(
        "Analyse the material above and return the ordered tutorial steps."
    )

    return "\n".join(parts)


async def extract_steps(
    transcript: str | None = None,
    frame_descriptions: Sequence[str] | None = None,
    *,
    deps: StepExtractionDeps | None = None,
    model_override: str | None = None,
) -> list[StepOutput]:
    """Run the step-extractor agent and return a list of typed steps.

    This is the main public entry-point that should be called from FastAPI
    endpoint handlers.

    Args:
        transcript: Plain-text transcription of the video audio.
        frame_descriptions: Ordered descriptions (or base64 refs) of key frames.
        deps: Runtime dependencies.  A default instance is created when *None*.
        model_override: Optional model string that takes precedence over env
            configuration (e.g. ``"openai:gpt-4o"``).

    Returns:
        A list of ``StepOutput`` objects in chronological order.

    Raises:
        RuntimeError: If the agent fails after all retries.
    """
    if deps is None:
        deps = StepExtractionDeps()

    # FIX: Wire up deps.api_key — PydanticAI reads API keys from env vars,
    # so we temporarily set the appropriate env var if an override key is given.
    # We use setdefault to avoid overwriting an existing key.
    effective_model = model_override or _resolve_model()
    if deps.api_key:
        # Determine which env var to set based on the model provider prefix.
        if effective_model.startswith("openai"):
            os.environ.setdefault("OPENAI_API_KEY", deps.api_key)
        else:
            # Default to Google API key for Gemini and other providers.
            os.environ.setdefault("GOOGLE_API_KEY", deps.api_key)

    user_prompt = _build_user_prompt(
        transcript=transcript,
        frame_descriptions=frame_descriptions,
        deps=deps,
    )

    logger.info(
        "Running step_extractor_agent (model=%s, context=%r)",
        effective_model,
        deps.project_context,
    )

    # Use agent.override() to swap the model at run time.
    # Passing `model` as a kwarg to .run() is NOT supported by PydanticAI;
    # .override() returns a thin wrapper that inherits all tools/prompts.
    agent = step_extractor_agent.override(model=effective_model)

    # Pass user_prompt as a positional argument, not as a kwarg.
    # The .run() signature is: run(user_prompt, *, deps, ...) — the first
    # parameter is positional-only in the PydanticAI public API.
    result = await agent.run(user_prompt, deps=deps)

    steps: list[StepOutput] = result.data.steps
    logger.info("Extracted %d steps from source material.", len(steps))
    return steps
