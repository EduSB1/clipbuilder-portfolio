"""Parallel execution engine for AI tools.

Runs multiple tools concurrently using asyncio.gather, with support for
cancellation, logging, and SSE streaming callbacks.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

import anyio
from sqlalchemy.orm import Session

from app.admin.models import AiTool
from app.tools.service import get_tools_by_trigger, save_tool_log

logger = logging.getLogger("clipbuilder")


class ToolsEngine:
    """Executes AI tools in parallel with support for cancellation and SSE streaming."""

    def __init__(self, max_workers: int = 5):
        self._max_workers = max_workers
        self._active_tasks: dict[str, asyncio.Task] = {}  # execution_id -> Task
        self._semaphore = asyncio.Semaphore(max_workers)

    async def run_tools_for_trigger(
        self,
        trigger: str,
        context: dict[str, Any],
        gemini_key: str | None,
        db: Session,
        stream_callback: Callable[[str, str], Coroutine] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Find all active tools for *trigger* and execute them in parallel.

        Args:
            trigger: The trigger point (e.g. "on_frame_capture", "on_export").
            context: Dict with keys like "image_bytes", "previous_steps",
                     "full_document", "project_id".
            gemini_key: Gemini API key (may be None).
            db: SQLAlchemy session.
            stream_callback: Optional async callable(tool_id, chunk) for SSE.

        Returns:
            Dict mapping tool_id -> {"output": ..., "output_target": ..., "status": ...,
                                      "tool_name": ..., "error": ..., "duration_ms": ...}
        """
        tools = get_tools_by_trigger(db, trigger, context.get("project_id"))
        active_tools = [t for t in tools if t.is_active]

        if not active_tools:
            return {}

        # Check which providers have keys available
        available_tools = []
        for tool in active_tools:
            if tool.model_provider == "gemini" and not gemini_key:
                logger.debug("Skipping tool '%s' — no Gemini key available", tool.name)
                continue
            available_tools.append(tool)

        if not available_tools:
            return {}

        tasks = [
            self._run_single_tool(
                tool, trigger, context, gemini_key, db, stream_callback
            )
            for tool in available_tools
        ]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, dict[str, Any]] = {}
        # asyncio.gather preserva a ordem, então as listas têm o mesmo tamanho.
        for tool, result in zip(available_tools, results_list, strict=True):
            if isinstance(result, Exception):
                results[tool.id] = {
                    "output": None,
                    "output_target": tool.output_target,
                    "status": "error",
                    "tool_name": tool.name,
                    "error": str(result),
                    "duration_ms": None,
                }
            else:
                results[tool.id] = result

        return results

    async def _run_single_tool(
        self,
        tool: AiTool,
        trigger: str,
        context: dict[str, Any],
        gemini_key: str | None,
        db: Session,
        stream_callback: Callable[[str, str], Coroutine] | None,
    ) -> dict[str, Any]:
        """Execute a single tool, save its log, and return the result."""
        async with self._semaphore:
            start = time.monotonic()
            try:
                output = await self._call_ai(tool, context, gemini_key)
                duration_ms = int((time.monotonic() - start) * 1000)

                save_tool_log(
                    db,
                    tool_id=tool.id,
                    trigger=trigger,
                    status="success",
                    input_summary=self._build_input_summary(context),
                    output=output,
                    duration_ms=duration_ms,
                )

                if stream_callback:
                    try:
                        await stream_callback(tool.id, output)
                    except Exception as cb_err:
                        logger.warning(
                            "Stream callback failed for tool %s: %s",
                            tool.id,
                            cb_err,
                        )

                return {
                    "output": output,
                    "output_target": tool.output_target,
                    "status": "success",
                    "tool_name": tool.name,
                    "error": None,
                    "duration_ms": duration_ms,
                }

            except asyncio.CancelledError:
                duration_ms = int((time.monotonic() - start) * 1000)
                save_tool_log(
                    db,
                    tool_id=tool.id,
                    trigger=trigger,
                    status="cancelled",
                    duration_ms=duration_ms,
                )
                raise

            except Exception as exc:
                duration_ms = int((time.monotonic() - start) * 1000)
                error_msg = str(exc)[:2000]
                logger.error(
                    "Tool '%s' (id=%s) failed: %s",
                    tool.name,
                    tool.id,
                    error_msg,
                    exc_info=True,
                )
                save_tool_log(
                    db,
                    tool_id=tool.id,
                    trigger=trigger,
                    status="error",
                    input_summary=self._build_input_summary(context),
                    error=error_msg,
                    duration_ms=duration_ms,
                )
                return {
                    "output": None,
                    "output_target": tool.output_target,
                    "status": "error",
                    "tool_name": tool.name,
                    "error": error_msg,
                    "duration_ms": duration_ms,
                }

    async def _call_ai(
        self,
        tool: AiTool,
        context: dict[str, Any],
        gemini_key: str | None,
    ) -> str:
        """Call the appropriate AI provider for the tool, replacing prompt variables."""
        prompt = self._render_prompt(tool.prompt, context)

        if tool.model_provider == "gemini":
            if not gemini_key:
                raise ValueError("Chave Gemini não disponível para esta tool.")
            return await self._call_gemini(
                prompt, context.get("image_bytes"), context.get("audio_bytes"), gemini_key, tool.model_name
            )
        else:
            raise ValueError(f"Provider desconhecido: {tool.model_provider}")

    @staticmethod
    def _render_prompt(prompt_template: str, context: dict[str, Any]) -> str:
        """Replace template variables in the prompt."""
        prompt = prompt_template

        if "{previous_steps}" in prompt:
            previous = context.get("previous_steps") or []
            if previous:
                steps_text = "\n".join(
                    [f"Passo {i + 1}: {s}" for i, s in enumerate(previous)]
                )
            else:
                steps_text = "Nenhum passo anterior."
            prompt = prompt.replace("{previous_steps}", steps_text)

        if "{full_document}" in prompt:
            doc = context.get("full_document") or ""
            prompt = prompt.replace("{full_document}", doc)

        return prompt

    @staticmethod
    def _build_input_summary(context: dict[str, Any]) -> str | None:
        """Create a brief summary of the context (never includes raw image bytes)."""
        parts: list[str] = []
        if context.get("image_bytes"):
            parts.append("image: yes")
        if context.get("audio_bytes"):
            parts.append("audio: yes")
        prev = context.get("previous_steps")
        if prev:
            parts.append(f"previous_steps: {len(prev)}")
        if context.get("full_document"):
            doc = context["full_document"]
            parts.append(f"full_document: {len(doc)} chars")
        if context.get("project_id"):
            parts.append(f"project_id: {context['project_id']}")
        return "; ".join(parts) if parts else None

    @staticmethod
    async def _call_gemini(
        prompt: str,
        image_bytes: bytes | None,
        audio_bytes: bytes | None,
        api_key: str,
        model_name: str,
    ) -> str:
        """Call Google Gemini (vision or text) in a thread."""

        def _sync_call() -> str:
            try:
                import google.generativeai as genai
            except ImportError as exc:
                raise RuntimeError(
                    "Dependência 'google-generativeai' não instalada no backend."
                ) from exc

            genai.configure(api_key=api_key)

            from app.core.config import settings

            normalized = (model_name or "").strip()
            if normalized and not normalized.startswith("models/"):
                normalized = f"models/{normalized}"

            model = genai.GenerativeModel(normalized or settings.gemini_model or "models/gemini-2.5-flash")

            content_parts: list[Any] = []

            if image_bytes:
                content_parts.append({"mime_type": "image/png", "data": image_bytes})

            if audio_bytes:
                content_parts.append({"mime_type": "audio/wav", "data": audio_bytes})

            content_parts.append(prompt)

            response = model.generate_content(content_parts)
            text = getattr(response, "text", None)
            return str(text).strip() if text else ""

        return await anyio.to_thread.run_sync(_sync_call)



    def cancel_all(self) -> int:
        """Cancel all currently active tasks. Returns number of tasks cancelled."""
        count = 0
        for _eid, task in list(self._active_tasks.items()):
            if not task.done():
                task.cancel()
                count += 1
        self._active_tasks.clear()
        return count


# Singleton instance used by the application
tools_engine = ToolsEngine()
