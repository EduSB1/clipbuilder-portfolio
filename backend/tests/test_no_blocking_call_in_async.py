"""Impede que trabalho bloqueante volte para dentro do event loop.

A API roda com um único worker uvicorn.  Chamar LibreOffice, python-docx ou uma
request síncrona ao Gemini direto de um handler `async def` congela o servidor
inteiro para todos os usuários enquanto a operação durar.

O caminho correto é `await _run_blocking(func, ...)` ou `await _run_export(...)`,
que empurram a chamada para uma worker thread.  Passada como *referência*, a
função não é um `ast.Call` — por isso este teste só acusa a chamada direta.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Funções cujo custo é medido em segundos.
BLOCKING_FUNCTIONS = {
    "convert_docx_to_pdf",
    "corporate_markdown_to_docx",
    "corporate_structured_to_docx",
    "enhance_document_with_gemini",
    "format_document_like_template",
    "format_document_like_template_with_gemini",
    "markdown_to_docx",
    "markdown_to_docx_pro",
    "markdown_to_html",
    "markdown_to_pdf",
    "markdown_to_pdf_via_libreoffice",
    "structured_json_to_docx",
    # Mídia: cada uma dispara ffmpeg/ffprobe ou uma chamada de rede.
    "_describe_at_timestamp",
    "_describe_gif_with_gemini",
    "_download_youtube_video",
    "_extract_audio_clip",
    "_extract_frames_from_gif",
    "_extract_frames_from_video",
    "_make_gemini_clip",
    "_upload_video_to_gemini",
}

# Chamadas de biblioteca que bloqueiam o processo inteiro.
BLOCKING_ATTRIBUTES = {
    ("subprocess", "run"),
    ("subprocess", "check_output"),
    ("subprocess", "call"),
    ("time", "sleep"),
}


class _BlockingCallVisitor(ast.NodeVisitor):
    """Percorre a árvore rastreando o escopo de função mais próximo."""

    def __init__(self) -> None:
        self.scope: list[bool] = []  # True = escopo async
        self.violations: list[tuple[int, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Um `def` aninhado dentro de um `async def` roda em worker thread
        # (é o padrão usado com anyio.to_thread) — não é violação.
        self.scope.append(False)
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.scope.append(True)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if self.scope and self.scope[-1]:
            name = None
            if isinstance(node.func, ast.Name):
                if node.func.id in BLOCKING_FUNCTIONS:
                    name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(
                node.func.value, ast.Name
            ):
                pair = (node.func.value.id, node.func.attr)
                if pair in BLOCKING_ATTRIBUTES:
                    name = f"{pair[0]}.{pair[1]}"
            if name:
                self.visit_Call_violation(node, name)
        self.generic_visit(node)

    def visit_Call_violation(self, node: ast.Call, name: str) -> None:
        self.violations.append((node.lineno, name))


def _scan(path: Path) -> list[tuple[int, str]]:
    visitor = _BlockingCallVisitor()
    visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
    return visitor.violations


def test_main_has_no_blocking_call_inside_async_handler() -> None:
    violations = _scan(BACKEND_ROOT / "main.py")
    assert not violations, "Chamadas bloqueantes dentro de handler async em main.py:\n" + "\n".join(
        f"  main.py:{line} → {name}() — use `await _run_blocking(...)` ou `await _run_export(...)`"
        for line, name in violations
    )


def test_routers_have_no_blocking_call_inside_async_handler() -> None:
    offenders: dict[str, list[tuple[int, str]]] = {}
    for path in sorted((BACKEND_ROOT / "app").rglob("*.py")):
        found = _scan(path)
        if found:
            offenders[str(path.relative_to(BACKEND_ROOT))] = found

    assert not offenders, "Chamadas bloqueantes dentro de handler async:\n" + "\n".join(
        f"  {file}:{line} → {name}()"
        for file, items in offenders.items()
        for line, name in items
    )
