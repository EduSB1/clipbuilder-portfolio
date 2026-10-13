"""
Extração de texto de documentos para o pipeline format-and-export.

Suporta: Markdown (string ou .md), DOCX e PDF.

Melhorado para preservar:
- Estrutura de cabeçalhos (H1, H2, H3...)
- Tabelas (convertidas para Markdown)
- Listas
- Formatação básica
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import UploadFile

logger = logging.getLogger("clipbuilder.document_loader")

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = (".md", ".docx", ".pdf", ".html", ".htm")


async def extract_text_from_document(
    file: UploadFile | None = None,
    markdown_text: str | None = None,
) -> str:
    """
    Extrai texto a partir de markdown (string), ou de um ficheiro .md, .docx ou .pdf.

    Args:
        file: Ficheiro enviado (opcional).
        markdown_text: Texto Markdown já em string (opcional).

    Returns:
        Texto bruto para envio ao Gemini.

    Raises:
        ValueError: Se nem file nem markdown_text forem fornecidos, ou se o ficheiro
                    for inválido (extensão ou tamanho).
    """
    if markdown_text is not None and markdown_text.strip():
        return markdown_text.strip()

    if file is None or not file.filename:
        raise ValueError(
            "É necessário fornecer 'markdown' (texto) ou enviar um ficheiro .md, .docx ou .pdf."
        )

    filename = file.filename
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Formato de ficheiro não suportado: {ext}. Use .md, .docx ou .pdf."
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_FILE_BYTES:
        raise ValueError(
            f"Ficheiro demasiado grande (máx. {MAX_FILE_BYTES // (1024 * 1024)} MB)."
        )
    if len(raw_bytes) == 0:
        raise ValueError("O ficheiro está vazio.")

    if ext == ".md":
        try:
            return raw_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            try:
                return raw_bytes.decode("latin-1").strip()
            except Exception as e:
                raise ValueError(f"Falha ao ler ficheiro .md: {e}") from e

    if ext == ".docx":
        return _extract_text_from_docx(raw_bytes)

    if ext == ".pdf":
        return _extract_text_from_pdf(raw_bytes)

    if ext in (".html", ".htm"):
        return _extract_text_from_html(raw_bytes)

    raise ValueError(f"Formato não implementado: {ext}")


def _extract_text_from_docx(raw_bytes: bytes) -> str:
    """Extrai texto de um DOCX usando python-docx.

    Preserva:
    - Cabeçalhos (convertidos para Markdown #)
    - Tabelas (convertidas para Markdown)
    - Listas
    - Parágrafos com formatação
    """
    try:
        from docx import Document
        from docx.table import Table  # noqa: F401 - used for type hints
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'python-docx' não instalada. Instale no backend."
        ) from exc

    doc = Document(io.BytesIO(raw_bytes))
    parts = []

    def _get_heading_level(para) -> int | None:
        """Retorna nível do heading (1-9) ou None se não for heading."""
        style_name = para.style.name if para.style else ""
        if style_name.startswith("Heading"):
            try:
                return int(style_name.replace("Heading", "").strip())
            except ValueError:
                return 1
        if style_name == "Title":
            return 1
        if style_name == "Subtitle":
            return 2
        return None

    def _table_to_markdown(table: Table) -> str:
        """Converte tabela DOCX para Markdown."""
        rows = []
        for i, row in enumerate(table.rows):
            cells = [cell.text.strip().replace("|", "\\|") for cell in row.cells]
            rows.append("| " + " | ".join(cells) + " |")
            # Adiciona linha separadora após o header
            if i == 0:
                rows.append("|" + "|".join(["---"] * len(cells)) + "|")
        return "\n".join(rows)

    def _is_list_item(para) -> tuple[bool, str]:
        """Verifica se é item de lista e retorna prefixo."""
        style_name = para.style.name if para.style else ""
        if "List" in style_name or "Bullet" in style_name:
            return True, "- "
        if "Number" in style_name:
            return True, "1. "
        return False, ""

    # Iterar sobre todos os elementos do documento na ordem
    # (parágrafos e tabelas intercalados)
    for element in doc.element.body:
        # Verifica se é parágrafo
        if element.tag.endswith("}p"):
            for para in doc.paragraphs:
                if para._element == element:
                    text = para.text.strip()
                    if not text:
                        continue

                    # Verificar se é heading
                    heading_level = _get_heading_level(para)
                    if heading_level:
                        parts.append(f"{'#' * heading_level} {text}")
                        continue

                    # Verificar se é item de lista
                    is_list, prefix = _is_list_item(para)
                    if is_list:
                        parts.append(f"{prefix}{text}")
                        continue

                    # Parágrafo normal
                    parts.append(text)
                    break

        # Verifica se é tabela
        elif element.tag.endswith("}tbl"):
            for table in doc.tables:
                if table._element == element:
                    table_md = _table_to_markdown(table)
                    if table_md:
                        parts.append("\n" + table_md + "\n")
                    break

    # Fallback: se não conseguiu extrair via elementos, usa método simples
    if not parts:
        for para in doc.paragraphs:
            if para.text.strip():
                heading_level = _get_heading_level(para)
                if heading_level:
                    parts.append(f"{'#' * heading_level} {para.text.strip()}")
                else:
                    parts.append(para.text.strip())

        # Adiciona tabelas ao final
        for table in doc.tables:
            table_md = _table_to_markdown(table)
            if table_md:
                parts.append("\n" + table_md + "\n")

    return "\n\n".join(parts).strip() if parts else ""


def _extract_text_from_pdf(raw_bytes: bytes) -> str:
    """Extrai texto de um PDF usando pypdf.

    Tenta preservar estrutura básica do documento.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'pypdf' não instalada. Execute: pip install pypdf"
        ) from exc

    reader = PdfReader(io.BytesIO(raw_bytes))
    parts = []

    for page_num, page in enumerate(reader.pages, 1):
        text = page.extract_text()
        if text and text.strip():
            # Adiciona separador de página para contexto
            if page_num > 1:
                parts.append(f"\n--- Página {page_num} ---\n")
            parts.append(text.strip())

    result = "\n\n".join(parts).strip()

    # Se o PDF não teve texto extraído (pode ser escaneado/imagem)
    if not result:
        logger.warning("PDF sem texto extraível - pode ser documento escaneado")
        return "(Documento PDF sem texto extraível - possivelmente escaneado/imagem)"

    return result


def _extract_text_from_html(raw_bytes: bytes) -> str:
    """Extrai texto de um HTML preservando estrutura.

    Converte:
    - Headings (h1-h6) para Markdown #
    - Tabelas para Markdown
    - Listas para Markdown
    - Parágrafos e divs para texto
    - Remove scripts, styles e elementos não-textuais
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'beautifulsoup4' não instalada. Execute: pip install beautifulsoup4"
        ) from exc

    # Tentar decodificar HTML
    try:
        html_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            html_content = raw_bytes.decode("latin-1")
        except Exception:
            html_content = raw_bytes.decode("utf-8", errors="ignore")

    soup = BeautifulSoup(html_content, "html.parser")

    # Remover elementos não-textuais
    for element in soup(["script", "style", "meta", "link", "noscript", "iframe"]):
        element.decompose()

    def _process_element(element, depth=0):
        """Processa elemento HTML recursivamente."""
        if element.name is None:
            # Texto puro
            text = str(element).strip()
            if text:
                return text
            return ""

        result_parts = []

        # Headings
        if element.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(element.name[1])
            text = element.get_text(strip=True)
            if text:
                result_parts.append(f"{'#' * level} {text}")

        # Parágrafos
        elif element.name == "p":
            text = element.get_text(strip=True)
            if text:
                result_parts.append(text)

        # Listas não ordenadas
        elif element.name == "ul":
            for li in element.find_all("li", recursive=False):
                text = li.get_text(strip=True)
                if text:
                    result_parts.append(f"- {text}")

        # Listas ordenadas
        elif element.name == "ol":
            for i, li in enumerate(element.find_all("li", recursive=False), 1):
                text = li.get_text(strip=True)
                if text:
                    result_parts.append(f"{i}. {text}")

        # Tabelas
        elif element.name == "table":
            rows = []
            for tr in element.find_all("tr"):
                cells = []
                for cell in tr.find_all(["th", "td"]):
                    cell_text = cell.get_text(strip=True).replace("|", "\\|")
                    cells.append(cell_text)
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")

            if rows:
                # Inserir linha de separação após o header
                if len(rows) > 0:
                    header_row = rows[0]
                    num_cols = header_row.count("|") - 1
                    separator = "|" + "|".join(["---"] * num_cols) + "|"
                    rows.insert(1, separator)
                result_parts.append("\n".join(rows))

        # Divs e sections - processar filhos
        elif element.name in (
            "div",
            "section",
            "article",
            "main",
            "body",
            "header",
            "footer",
            "nav",
        ):
            for child in element.children:
                if hasattr(child, "name"):
                    child_result = _process_element(child, depth + 1)
                    if child_result:
                        result_parts.append(child_result)
                elif str(child).strip():
                    result_parts.append(str(child).strip())

        # Blockquotes
        elif element.name == "blockquote":
            text = element.get_text(strip=True)
            if text:
                result_parts.append(f"> {text}")

        # Pre/Code
        elif element.name in ("pre", "code"):
            text = element.get_text(strip=True)
            if text:
                result_parts.append(f"```\n{text}\n```")

        # Strong/Bold
        elif element.name in ("strong", "b"):
            text = element.get_text(strip=True)
            if text:
                result_parts.append(f"**{text}**")

        # Emphasis/Italic
        elif element.name in ("em", "i"):
            text = element.get_text(strip=True)
            if text:
                result_parts.append(f"*{text}*")

        # Imagens - preservar referência
        elif element.name == "img":
            alt = element.get("alt", "Imagem")
            src = element.get("src", "")
            if src:
                result_parts.append(f"![{alt}]({src})")

        # Links
        elif element.name == "a":
            text = element.get_text(strip=True)
            href = element.get("href", "")
            if text and href:
                result_parts.append(f"[{text}]({href})")
            elif text:
                result_parts.append(text)

        # Outros elementos - extrair texto
        else:
            text = element.get_text(strip=True)
            if text and len(text) > 2:  # Ignorar textos muito curtos
                result_parts.append(text)

        return "\n\n".join(result_parts)

    # Processar body ou documento inteiro
    body = soup.find("body")
    content = _process_element(body) if body else _process_element(soup)

    # Limpar resultado
    if content:
        # Remover linhas em branco excessivas
        lines = content.split("\n")
        cleaned_lines = []
        prev_blank = False
        for line in lines:
            is_blank = not line.strip()
            if is_blank and prev_blank:
                continue
            cleaned_lines.append(line)
            prev_blank = is_blank

        return "\n".join(cleaned_lines).strip()

    # Fallback: extrair todo o texto
    fallback_text = soup.get_text(separator="\n", strip=True)
    if fallback_text:
        return fallback_text

    logger.warning("HTML sem texto extraível")
    return "(Documento HTML sem conteúdo textual extraível)"
