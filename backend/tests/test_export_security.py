"""Segurança da exportação: imagens só vêm do request, e o HTML sai sanitizado.

Antes: um valor de image_map (ou a url de ![alt](url)) que fosse caminho de
arquivo era lido do disco do servidor e embutido no documento; e o export HTML
deixava passar HTML cru, nomes de imagem e títulos sem escape.
"""

from __future__ import annotations

import base64
import io
import os
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.services.export_from_markdown import (
    markdown_to_docx,
    markdown_to_docx_pro,
    markdown_to_html,
    markdown_to_pdf,
)
from templates.corporate_docx import corporate_markdown_to_docx
from templates.template_registry import get_template_or_default


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def server_image(tmp_path: Path) -> Path:
    """Uma imagem válida no disco do servidor: não pode entrar no documento."""
    # Ruído não comprime: embutida, a imagem faz o documento crescer dezenas de KB.
    noise = Image.frombytes("RGB", (128, 128), os.urandom(128 * 128 * 3))
    path = tmp_path / "segredo.png"
    noise.save(path, format="PNG")
    return path


def _docx_media(docx: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        return [name for name in archive.namelist() if name.startswith("word/media/")]


class TestServerFilesAreNeverRead:
    def test_html_ignores_path_in_image_map(self, server_image: Path) -> None:
        out = markdown_to_html("[Imagem: Passo 1]", image_map={"Passo 1": str(server_image)})
        assert base64.b64encode(server_image.read_bytes()).decode() not in out
        assert "Imagem não encontrada" in out

    @pytest.mark.parametrize("builder", [markdown_to_docx, markdown_to_docx_pro])
    def test_docx_ignores_path_in_markdown_image(self, builder, server_image: Path) -> None:
        assert _docx_media(builder(f"![foto]({server_image})")) == []

    @pytest.mark.parametrize("builder", [markdown_to_docx, markdown_to_docx_pro])
    def test_docx_ignores_path_in_image_map(self, builder, server_image: Path) -> None:
        docx = builder("[Imagem: Passo 1]", image_map={"Passo 1": str(server_image)})
        assert _docx_media(docx) == []

    def test_corporate_docx_ignores_path(self, server_image: Path) -> None:
        template = get_template_or_default(None)
        with_path = corporate_markdown_to_docx(
            f"![foto]({server_image})\n\n[Imagem: Passo 1]",
            template,
            image_map={"Passo 1": str(server_image)},
        )
        baseline = corporate_markdown_to_docx("![foto](nada)\n\n[Imagem: Passo 1]", template)
        # Só a mídia do próprio template (logo), nenhuma vinda do disco.
        assert _docx_media(with_path) == _docx_media(baseline)

    def test_pdf_never_reads_path_in_markdown_image(
        self, server_image: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No PDF a imagem lida nem sempre chega a ser embutida, então o que se
        # verifica é a leitura em si.
        read: list[Path] = []
        original = Path.read_bytes

        def spy(self: Path) -> bytes:
            read.append(self)
            return original(self)

        monkeypatch.setattr(Path, "read_bytes", spy)
        markdown_to_pdf(f"![foto]({server_image})\n\n[Imagem: Passo 1]", {"Passo 1": str(server_image)})
        assert server_image not in read

    def test_dev_zero_is_not_read(self) -> None:
        # Antes isso lia /dev/zero até estourar a memória.
        out = markdown_to_html("[Imagem: x]", image_map={"x": "/dev/zero"})
        assert "Imagem não encontrada" in out

    def test_base64_images_still_work(self) -> None:
        png = _png_bytes()
        data_url = "data:image/png;base64," + base64.b64encode(png).decode()
        assert _docx_media(markdown_to_docx_pro("[Imagem: Passo 1]", image_map={"Passo 1": data_url}))
        assert "data:image/png;base64," in markdown_to_html(
            "[Imagem: Passo 1]", image_map={"Passo 1": data_url}
        )


class TestHtmlExportIsSanitized:
    def test_raw_html_and_handlers_are_removed(self) -> None:
        out = markdown_to_html(
            "Texto\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>\n\n"
            '<a href="javascript:alert(3)">link</a>\n\n<iframe src="https://evil.example"></iframe>'
        )
        body = out.split("<body", 1)[1]
        assert "<script>alert" not in body
        assert "onerror" not in body
        assert "javascript:" not in body
        assert "<iframe" not in body

    def test_heading_text_is_escaped_in_table_of_contents(self) -> None:
        out = markdown_to_html("## Título &lt;img src=x onerror=alert(1)&gt;\n\ntexto")
        assert "onerror=alert(1)>" not in out
        assert "&lt;img src=x onerror=alert(1)&gt;" in out

    def test_image_name_cannot_break_out_of_attribute(self) -> None:
        name = 'x" onload="alert(1)'
        png = "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()
        out = markdown_to_html(f"[Imagem: {name}]", image_map={name: png})
        assert 'onload="alert(1)"' not in out
        assert "data:image/png;base64," in out

    def test_callouts_keep_their_class(self) -> None:
        out = markdown_to_html("> [!NOTE]\n> Leia antes.\n\n> [!WARNING]\n> Cuidado.")
        assert 'class="note"' in out
        assert 'class="warning"' in out

    def test_regular_markdown_survives(self) -> None:
        out = markdown_to_html(
            "# Guia\n\n## Passo 1\n\n**negrito** e [site](https://example.com)\n\n"
            "| a | b |\n|---|---|\n| 1 | 2 |\n\n```\ncodigo\n```"
        )
        assert "<strong>negrito</strong>" in out
        assert 'href="https://example.com"' in out
        assert "<table" in out
        assert "<code>" in out
