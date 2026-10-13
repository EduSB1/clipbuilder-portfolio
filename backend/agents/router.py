"""FastAPI router for the PydanticAI step-extractor agent.

Exposes a POST ``/agents/extract-steps`` endpoint that accepts a video
transcript and/or frame descriptions and returns structured tutorial steps
via the :pymod:`agents.step_extractor` agent.

Integration
-----------
Import and include this router in the main FastAPI application::

    from agents.router import router as agents_router
    app.include_router(agents_router)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.step_extractor import (
    ActionType,
    StepExtractionDeps,
    StepOutput,
    extract_steps,
)

logger = logging.getLogger("clipbuilder.agents.router")

router = APIRouter(prefix="/agents", tags=["agents"])

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ExtractStepsRequest(BaseModel):
    """Payload accepted by the ``/agents/extract-steps`` endpoint."""

    transcript: str | None = Field(
        default=None,
        description="Plain-text transcription of the video audio.",
    )
    frame_descriptions: list[str] | None = Field(
        default=None,
        description="Ordered descriptions (or base64 refs) of key video frames.",
    )
    project_context: str = Field(
        default="General software tutorial",
        description="Free-text description of the project or tutorial topic.",
    )
    valid_action_types: list[ActionType] | None = Field(
        default=None,
        description=(
            "Restrict which action types the agent may assign. "
            "When null every ActionType is allowed."
        ),
    )
    language: str = Field(
        default="pt-BR",
        description="BCP-47 language tag for the generated output.",
    )
    model_override: str | None = Field(
        default=None,
        description=(
            "Optional model identifier that overrides the default "
            "(e.g. 'openai:gpt-4o' or 'google-gla:gemini-1.5-flash')."
        ),
    )


class ExtractStepsResponse(BaseModel):
    """Structured response returned by the extraction endpoint."""

    steps: list[StepOutput] = Field(
        ...,
        description="Ordered list of extracted tutorial steps.",
    )
    count: int = Field(
        ...,
        description="Total number of steps returned.",
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/extract-steps",
    response_model=ExtractStepsResponse,
    summary="Extract tutorial steps from video material",
    description=(
        "Sends transcript and/or frame descriptions to the PydanticAI "
        "step-extractor agent and returns structured, typed tutorial steps."
    ),
)
async def extract_steps_endpoint(
    body: ExtractStepsRequest,
) -> ExtractStepsResponse:
    """Run the step-extractor agent and return structured steps.

    Raises:
        HTTPException 422: When neither transcript nor frame_descriptions
            are provided.
        HTTPException 502: When the upstream LLM call fails.
    """
    # Validate that at least one input source is provided
    if not body.transcript and not body.frame_descriptions:
        raise HTTPException(
            status_code=422,
            detail=(
                "At least one of 'transcript' or 'frame_descriptions' "
                "must be provided."
            ),
        )

    # Build the dependency container from the request payload
    deps = StepExtractionDeps(
        project_context=body.project_context,
        valid_action_types=(
            set(body.valid_action_types) if body.valid_action_types else None
        ),
        language=body.language,
    )

    # NOTE: model_override flows through to extract_steps() → agent.override(),
    # which is the correct PydanticAI pattern for per-request model switching.
    try:
        steps: list[StepOutput] = await extract_steps(
            transcript=body.transcript,
            frame_descriptions=body.frame_descriptions,
            deps=deps,
            model_override=body.model_override,
        )
    except Exception as exc:
        logger.exception("Step extraction failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Step extraction failed: {exc}",
        ) from exc

    return ExtractStepsResponse(steps=steps, count=len(steps))
