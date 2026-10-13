"""
Corporate DOCX Builder – generates Word documents that follow the Wolbito do Brasil
corporate templates (IT – Instrução de Trabalho and POP – Procedimento Operacional Padrão).

Reference layout (from real Wolbito documents):
  ┌────────────┬─────────────────────────────────────────────────────┐
  │            │              TÍTULO DO DOCUMENTO                    │
  │   [Logo]   ├─────────────────────────────┬──────────────────────┤
  │            │ Código do documento: XXX    │ Revisão: 00          │
  │            ├─────────────────────────────┼──────────────────────┤
  │            │ Período de expiração: 1 ano │ Data de elab.: DD/MM │
  ├────────────┴─────────────────────────────┴──────────────────────┤
  │                                                                  │
  │  1.   INTRODUÇÃO                                                 │
  │       Texto com indentação na primeira linha, justificado.       │
  │                                                                  │
  │  2.   OBJETIVO                                                   │
  │       ...                                                        │
  │                                                                  │
  ├──────────────────┬──────────────────┬───────────────────────────┤
  │ Resp. Elaboração │ Resp. Consenso   │ Resp. Aprovação           │
  │ Nome             │ Nome             │ Nome                      │
  └──────────────────┴──────────────────┴───────────────────────────┘

Key characteristics:
  - Header: white background, light grey borders, logo vertically merged on left
  - Section headings: black bold, number separated with tab, ALL CAPS
  - Body text: justified, first-line indent ~1.25cm, font Arial 11pt
  - Sub-headings (## Passo N): bold, slightly smaller, also with indent
  - Footer: 3-column table with responsáveis, light grey borders
  - Page: A4, margins ~2cm

This module exposes:
  - corporate_markdown_to_docx(markdown, template, metadata, image_map) -> bytes
  - corporate_structured_to_docx(data, template, metadata) -> bytes
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy imports (python-docx may not be installed everywhere)
# ---------------------------------------------------------------------------


def _import_docx():
    try:
        from docx import Document
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Cm, Emu, Inches, Pt, RGBColor

        return {
            "Document": Document,
            "WD_ALIGN_PARAGRAPH": WD_ALIGN_PARAGRAPH,
            "WD_TABLE_ALIGNMENT": WD_TABLE_ALIGNMENT,
            "OxmlElement": OxmlElement,
            "qn": qn,
            "Cm": Cm,
            "Emu": Emu,
            "Inches": Inches,
            "Pt": Pt,
            "RGBColor": RGBColor,
        }
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'python-docx' não instalada. Instale no backend."
        ) from exc


# ---------------------------------------------------------------------------
# Inline bold/italic parser
# ---------------------------------------------------------------------------


def _parse_inline_bold(text: str) -> list[tuple[str, bool]]:
    """Split text into (fragment, is_bold) tuples around **bold** markers."""
    parts: list[tuple[str, bool]] = []
    segments = text.split("**")
    for i, seg in enumerate(segments):
        if seg:
            parts.append((seg, i % 2 == 1))
    return parts or [("", False)]


# ---------------------------------------------------------------------------
# Image resolver
# ---------------------------------------------------------------------------


def _validate_image_bytes(data: bytes) -> bool:
    if not data or len(data) < 8:
        return False
    png = data[:4] == b"\x89PNG"
    jpg = data[:2] == b"\xff\xd8"
    gif = data[:4] == b"GIF8"
    bmp = data[:2] == b"BM"
    webp = data[:4] == b"RIFF" and data[8:12] == b"WEBP" if len(data) >= 12 else False
    return png or jpg or gif or bmp or webp


def _resolve_image(image_map: dict | None, key: str) -> tuple[bytes | None, str | None]:
    if not image_map or not key:
        return None, "no image_map or key"
    value = image_map.get(key)
    if value is None:
        for k, v in image_map.items():
            if k.lower().strip() == key.lower().strip():
                value = v
                break
    if value is None:
        return None, f"key '{key}' not found"
    if isinstance(value, bytes):
        return value, None
    if isinstance(value, str):
        if value.startswith("data:") and "base64," in value:
            try:
                b64 = value.split("base64,", 1)[1]
                return base64.b64decode(b64), None
            except Exception:
                return None, "bad base64"
        try:
            return base64.b64decode(value), None
        except Exception:
            pass
        p = Path(value)
        if p.exists():
            return p.read_bytes(), None
    return None, "unresolvable"


# ---------------------------------------------------------------------------
# FIX 1: Robust logo finder — searches multiple candidate paths
# ---------------------------------------------------------------------------


def _find_logo(logo_path: str | None) -> Path | None:
    """
    Try to resolve the logo file from multiple candidate locations.

    The template registry builds paths relative to its own file at import time,
    but the working directory at runtime may differ. This function tries:
      1. The path exactly as stored in the template
      2. The same filename relative to this module's directory
      3. A few common project-root patterns (Icons/, assets/, static/)
      4. An environment variable CLIPBUILDER_ICONS_DIR
    """
    if not logo_path:
        return None

    candidates: list[Path] = []

    # 1. Exact path as stored
    candidates.append(Path(logo_path))

    # 2. Relative to this module's directory
    this_dir = Path(__file__).resolve().parent
    filename = Path(logo_path).name
    candidates.append(this_dir / filename)

    # 3. Common project layouts
    for ancestor in [this_dir, this_dir.parent, this_dir.parent.parent]:
        for sub in ("Icons", "icons", "assets", "static", "images"):
            candidates.append(ancestor / sub / filename)

    # 4. Environment variable override
    env_dir = os.environ.get("CLIPBUILDER_ICONS_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / filename)

    for candidate in candidates:
        try:
            if candidate.exists() and candidate.stat().st_size > 0:
                logger.debug("Logo encontrado em: %s", candidate)
                return candidate
        except Exception:
            continue

    logger.warning(
        "Logo não encontrado. Tentativas: %s",
        [str(c) for c in candidates[:6]],
    )
    return None


# ---------------------------------------------------------------------------
# Colour / cell helpers
# ---------------------------------------------------------------------------

# FIX 3: Light grey borders instead of black, consistent across all cells
_BORDER_COLOR = "BFBFBF"  # Cinza claro (was "000000" black)
_BORDER_SIZE = "6"  # Slightly heavier to be visible at grey tone (was "4")


def _hex_to_rgb(hex_str: str):
    d = _import_docx()
    h = hex_str.lstrip("#")
    return d["RGBColor"](int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _set_cell_shading(cell, color_hex: str):
    d = _import_docx()
    qn = d["qn"]
    OxmlElement = d["OxmlElement"]
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color_hex)
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    cell._tc.get_or_add_tcPr().append(shading)


def _set_cell_borders(cell, color_hex: str = _BORDER_COLOR, size: str = _BORDER_SIZE):
    d = _import_docx()
    qn = d["qn"]
    OxmlElement = d["OxmlElement"]
    tc_pr = cell._tc.get_or_add_tcPr()

    # Remove existing tcBorders to avoid duplicates
    for existing in tc_pr.findall(qn("w:tcBorders")):
        tc_pr.remove(existing)

    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color_hex)
        borders.append(el)
    tc_pr.append(borders)


# FIX 3: Table-level borders eliminate gaps at cell junctions
def _set_table_borders(table, color_hex: str = _BORDER_COLOR, size: str = _BORDER_SIZE):
    """
    Apply borders at the table level (w:tblBorders).

    This is essential: cell-level borders alone can leave hairline gaps at
    the corners/junctions where cells meet. Setting tblBorders fills those
    gaps and gives a clean, uniform grid.
    """
    d = _import_docx()
    OxmlElement = d["OxmlElement"]
    qn = d["qn"]

    tbl = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)

    # Remove existing tblBorders
    for existing in tblPr.findall(qn("w:tblBorders")):
        tblPr.remove(existing)

    tblBorders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), size)
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color_hex)
        tblBorders.append(el)
    tblPr.append(tblBorders)


def _set_cell_vertical_alignment(cell, val: str = "center"):
    d = _import_docx()
    qn = d["qn"]
    OxmlElement = d["OxmlElement"]
    tc_pr = cell._tc.get_or_add_tcPr()
    va = OxmlElement("w:vAlign")
    va.set(qn("w:val"), val)
    tc_pr.append(va)


def _set_cell_width(cell, width_cm: float):
    d = _import_docx()
    qn = d["qn"]
    OxmlElement = d["OxmlElement"]
    Cm = d["Cm"]
    tc_pr = cell._tc.get_or_add_tcPr()
    tw = OxmlElement("w:tcW")
    tw.set(qn("w:w"), str(int(Cm(width_cm))))
    tw.set(qn("w:type"), "dxa")
    tc_pr.append(tw)


def _set_paragraph_justified(paragraph):
    """Set paragraph alignment to justified."""
    d = _import_docx()
    paragraph.alignment = d["WD_ALIGN_PARAGRAPH"].JUSTIFY


def _set_paragraph_first_line_indent(paragraph, cm: float = 1.25):
    """Set a first-line indent on the paragraph (like the reference doc)."""
    d = _import_docx()
    Cm = d["Cm"]
    paragraph.paragraph_format.first_line_indent = Cm(cm)


def _set_paragraph_spacing(
    paragraph,
    before_pt: float = 0,
    after_pt: float = 6,
    line_spacing: float | None = None,
):
    """Configure paragraph spacing."""
    d = _import_docx()
    Pt = d["Pt"]
    paragraph.paragraph_format.space_before = Pt(before_pt)
    paragraph.paragraph_format.space_after = Pt(after_pt)
    if line_spacing is not None:
        paragraph.paragraph_format.line_spacing = line_spacing


# ---------------------------------------------------------------------------
# Corporate header table builder (matches reference layout)
# ---------------------------------------------------------------------------


def _add_text_logo_fallback(paragraph, font_name: str = "Arial"):
    """Fallback quando o logo não é encontrado."""
    d = _import_docx()
    Pt = d["Pt"]
    RGBColor = d["RGBColor"]

    run = paragraph.add_run("Wolbito\ndo Brasil")
    run.font.name = font_name
    run.font.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0, 0, 0)


def _fill_meta_cell(cell, text: str, font_name: str = "Arial", size_pt: int = 10):
    """Preenche célula de metadados."""
    d = _import_docx()
    Pt = d["Pt"]
    RGBColor = d["RGBColor"]
    WD_ALIGN_PARAGRAPH = d["WD_ALIGN_PARAGRAPH"]

    _set_cell_vertical_alignment(cell, "center")

    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)

    # Clear existing content
    p.text = ""

    run = p.add_run(text)
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.font.color.rgb = RGBColor(0, 0, 0)


def _build_header_table_for_header_footer(
    container,
    template,
    metadata: dict[str, str],
    is_header: bool = True,
    table_width=None,
):
    """Versão que funciona tanto no body quanto dentro de Header/Footer.

    Nota (python-docx): Header/Footer exigem `add_table(..., width=...)`, enquanto
    no body (`Document`) o método aceita apenas (rows, cols).
    """
    d = _import_docx()
    Cm = d["Cm"]
    Pt = d["Pt"]
    WD_ALIGN_PARAGRAPH = d["WD_ALIGN_PARAGRAPH"]

    cfg = template.config
    font_name = cfg.get("font", "Arial")
    defaults = cfg.get("defaults", {})

    title_text = metadata.get("title", "Instrução de Trabalho")
    doc_code = (
        metadata.get("document_code")
        or defaults.get("document_code")
        or "IT-XX-XXX-0000"
    )
    revision = metadata.get("revision") or defaults.get("revision") or "00"
    exp_period = (
        metadata.get("expiration_period")
        or defaults.get("expiration_period")
        or "1 ano"
    )
    elab_date = metadata.get("elaboration_date") or defaults.get("elaboration_date")
    if not elab_date:
        elab_date = date.today().strftime("%d/%m/%Y")

    # Tabela 3 linhas x 3 colunas
    # Header/Footer precisam de `width`; Document(body) não.
    try:
        if table_width is None:
            table = container.add_table(rows=3, cols=3)
        else:
            table = container.add_table(rows=3, cols=3, width=table_width)
    except TypeError:
        # Fallback (compat): tenta sem width
        table = container.add_table(rows=3, cols=3)

    table.alignment = d["WD_TABLE_ALIGNMENT"].CENTER
    table.autofit = True

    _set_table_borders(table, _BORDER_COLOR, _BORDER_SIZE)

    # Merge logo (vertical)
    logo_cell = table.cell(0, 0).merge(table.cell(2, 0))
    title_cell = table.cell(0, 1).merge(table.cell(0, 2))

    # Logo
    _set_cell_vertical_alignment(logo_cell, "center")
    p_logo = logo_cell.paragraphs[0]
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_logo.paragraph_format.left_indent = 0
    p_logo.paragraph_format.right_indent = 0
    p_logo.paragraph_format.space_before = 0
    p_logo.paragraph_format.space_after = 0

    logo_path = None
    if getattr(template, "has_logo", False):
        logo_path = _find_logo(getattr(template, "logo_path", None))

    if logo_path and logo_path.exists():
        try:
            run = p_logo.add_run()
            run.add_picture(str(logo_path), width=Cm(3.2))
            logger.info(
                "Logo inserido com sucesso no %s: %s",
                "header" if is_header else "footer",
                logo_path,
            )
        except Exception as e:
            logger.error("Erro ao inserir logo: %s", e)
            _add_text_logo_fallback(p_logo, font_name=font_name)
    else:
        _add_text_logo_fallback(p_logo, font_name=font_name)

    # Título
    _set_cell_vertical_alignment(title_cell, "center")
    p_title = title_cell.paragraphs[0]
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(6)
    p_title.paragraph_format.space_after = Pt(6)
    p_title.text = ""
    run = p_title.add_run(title_text or "")
    run.font.name = font_name
    run.font.size = Pt(12)
    run.font.bold = True

    # Linha 1: Código e Revisão
    row1 = table.rows[1]
    _fill_meta_cell(
        row1.cells[1],
        f"Código do documento: {doc_code}",
        font_name=font_name,
        size_pt=10,
    )
    _fill_meta_cell(
        row1.cells[2],
        f"Revisão: {revision}",
        font_name=font_name,
        size_pt=10,
    )

    # Linha 2: Expiração e Data
    row2 = table.rows[2]
    _fill_meta_cell(
        row2.cells[1],
        f"Período de expiração: {exp_period}",
        font_name=font_name,
        size_pt=10,
    )
    _fill_meta_cell(
        row2.cells[2],
        f"Data de elaboração: {elab_date}",
        font_name=font_name,
        size_pt=10,
    )

    return table


def _build_header_table(doc, template, metadata: dict[str, str]):
    """Compat wrapper: build header table in the document body (legacy)."""
    table = _build_header_table_for_header_footer(
        doc, template, metadata, is_header=True
    )

    # Preserve a small gap after header when used in-body
    try:
        d = _import_docx()
        Pt = d["Pt"]
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_before = Pt(0)
        spacer.paragraph_format.space_after = Pt(0)
    except Exception:
        pass

    return table


# ---------------------------------------------------------------------------
# Corporate footer table builder (matches reference layout)
# ---------------------------------------------------------------------------


def _build_footer_table_for_header_footer(
    container, template, metadata: dict[str, str], table_width=None
):
    """Versão que funciona tanto no body quanto dentro de Header/Footer.

    Nota (python-docx): Header/Footer exigem `add_table(..., width=...)`.
    """
    d = _import_docx()
    Pt = d["Pt"]
    WD_ALIGN_PARAGRAPH = d["WD_ALIGN_PARAGRAPH"]

    cfg = template.config
    font_name = cfg.get("font", "Arial")

    defaults = cfg.get("defaults", {})
    elab = metadata.get(
        "responsible_elaboration", defaults.get("responsible_elaboration", "")
    )
    consensus = metadata.get(
        "responsible_consensus", defaults.get("responsible_consensus", "")
    )
    approval = metadata.get(
        "responsible_approval", defaults.get("responsible_approval", "")
    )

    try:
        if table_width is None:
            table = container.add_table(rows=1, cols=3)
        else:
            table = container.add_table(rows=1, cols=3, width=table_width)
    except TypeError:
        table = container.add_table(rows=1, cols=3)

    table.alignment = d["WD_TABLE_ALIGNMENT"].CENTER

    _set_table_borders(table, _BORDER_COLOR, _BORDER_SIZE)

    footer_items = [
        ("Responsável pela elaboração:", elab),
        ("Responsável(eis) pelo consenso:", consensus),
        ("Responsável(eis) pela aprovação:", approval),
    ]

    for col_idx, (label, name) in enumerate(footer_items):
        cell = table.cell(0, col_idx)
        _set_cell_borders(cell, _BORDER_COLOR, _BORDER_SIZE)
        _set_cell_vertical_alignment(cell, "center")

        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(4)

        run_l = p.add_run(label + "\n")
        run_l.font.name = font_name
        run_l.font.size = Pt(8)
        run_l.font.color.rgb = _hex_to_rgb("000000")

        run_n = p.add_run(name)
        run_n.font.name = font_name
        run_n.font.size = Pt(9)
        run_n.font.color.rgb = _hex_to_rgb("000000")

    return table


def _build_footer_table(doc, template, metadata: dict[str, str]):
    """Compat wrapper: build footer table in the document body (legacy)."""
    try:
        d = _import_docx()
        Pt = d["Pt"]
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_before = Pt(12)
    except Exception:
        pass

    return _build_footer_table_for_header_footer(doc, template, metadata)


def _clear_header_footer_container(container) -> None:
    """Remove todo o conteúdo (parágrafos/tabelas) de um Header/Footer."""
    try:
        el = container._element  # Header/Footer XML element
        for child in list(el):
            el.remove(child)
        return
    except Exception:
        pass

    # Fallback: try removing paragraphs
    for p in list(getattr(container, "paragraphs", []) or []):
        try:
            p._element.getparent().remove(p._element)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CONFIGURAÇÃO DE HEADER E FOOTER CORPORATIVOS (em TODAS as páginas)
# ---------------------------------------------------------------------------


def _setup_corporate_header_footer(doc, template, metadata: dict[str, str]):
    """Configura header e footer que se repetem em todas as páginas."""
    # Apply to all sections (future-proof)
    for section in doc.sections:
        usable_width = None
        try:
            usable_width = (
                section.page_width - section.left_margin - section.right_margin
            )
        except Exception:
            usable_width = None

        # === HEADER ===
        header = section.header
        header.is_linked_to_previous = False
        _clear_header_footer_container(header)
        _build_header_table_for_header_footer(
            header,
            template,
            metadata,
            is_header=True,
            table_width=usable_width,
        )

        # === FOOTER ===
        footer = section.footer
        footer.is_linked_to_previous = False
        _clear_header_footer_container(footer)
        _build_footer_table_for_header_footer(
            footer,
            template,
            metadata,
            table_width=usable_width,
        )

    return doc.sections[0].header, doc.sections[0].footer


# ---------------------------------------------------------------------------
# Section heading helper (matches reference: "1.    INTRODUÇÃO")
# ---------------------------------------------------------------------------


def _add_section_heading(
    doc, text: str, level: int, template, section_number: str | None = None
):
    """
    Add a section heading matching the Wolbito reference style:
    - Level 1: bold, black, ~13pt, number + tab + text (e.g. "1.\tINTRODUÇÃO")
    - Level 2: bold, black, ~11pt
    - Level 3: bold, black, ~11pt, italic
    """
    d = _import_docx()
    Pt = d["Pt"]
    Cm = d["Cm"]
    RGBColor = d["RGBColor"]
    WD_ALIGN_PARAGRAPH = d["WD_ALIGN_PARAGRAPH"]

    cfg = template.config
    font_name = cfg.get("font", "Arial")

    if level == 1:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(6)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

        if section_number:
            p.paragraph_format.left_indent = Cm(1.5)
            p.paragraph_format.first_line_indent = Cm(-1.5)

            run_num = p.add_run(f"{section_number}.")
            run_num.font.name = font_name
            run_num.font.size = Pt(13)
            run_num.font.bold = True
            run_num.font.color.rgb = RGBColor(0, 0, 0)

            run_tab = p.add_run("\t")
            run_tab.font.name = font_name

            run_text = p.add_run(text)
            run_text.font.name = font_name
            run_text.font.size = Pt(13)
            run_text.font.bold = True
            run_text.font.color.rgb = RGBColor(0, 0, 0)
        else:
            run_text = p.add_run(text)
            run_text.font.name = font_name
            run_text.font.size = Pt(13)
            run_text.font.bold = True
            run_text.font.color.rgb = RGBColor(0, 0, 0)

        return p

    elif level == 2:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.left_indent = Cm(1.5)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

        run_text = p.add_run(text)
        run_text.font.name = font_name
        run_text.font.size = Pt(11)
        run_text.font.bold = True
        run_text.font.color.rgb = RGBColor(0, 0, 0)

        return p

    else:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Cm(1.5)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

        run_text = p.add_run(text)
        run_text.font.name = font_name
        run_text.font.size = Pt(11)
        run_text.font.bold = True
        run_text.font.color.rgb = RGBColor(0, 0, 0)

        return p


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------


def _setup_page(doc, template):
    """Configure page size, margins, and default styles to match reference."""
    d = _import_docx()
    Cm = d["Cm"]
    Inches = d["Inches"]
    Pt = d["Pt"]

    cfg = template.config
    section = doc.sections[0]

    page_size = cfg.get("page_size", "a4")
    if page_size == "a4":
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
    else:
        section.page_width = Inches(8.5)
        section.page_height = Inches(11)

    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(5.0)
    section.bottom_margin = Cm(2.5)
    section.header_distance = Cm(1.25)
    section.footer_distance = Cm(1.25)

    font_name = cfg.get("font", "Arial")
    font_size = cfg.get("font_size", 11)
    style = doc.styles["Normal"]
    style.font.name = font_name
    style.font.size = Pt(font_size)

    style.paragraph_format.alignment = d["WD_ALIGN_PARAGRAPH"].JUSTIFY
    style.paragraph_format.space_after = Pt(4)

    for lvl in range(1, 4):
        try:
            hs = doc.styles[f"Heading {lvl}"]
            hs.font.name = font_name
            hs.font.color.rgb = d["RGBColor"](0, 0, 0)
        except KeyError:
            pass

    return section


# ---------------------------------------------------------------------------
# Body paragraph helper (justified + first-line indent like reference)
# ---------------------------------------------------------------------------


def _add_body_paragraph(
    doc,
    text: str,
    font_name: str = "Arial",
    font_size_pt: float = 11,
    indent: bool = True,
    left_indent_cm: float = 1.5,
):
    """Add a justified body paragraph with optional first-line indent."""
    d = _import_docx()
    Pt = d["Pt"]
    Cm = d["Cm"]
    WD_ALIGN_PARAGRAPH = d["WD_ALIGN_PARAGRAPH"]

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent = Cm(left_indent_cm)

    if indent:
        p.paragraph_format.first_line_indent = Cm(1.0)

    for frag, bold in _parse_inline_bold(text):
        run = p.add_run(frag)
        run.bold = bold
        run.font.name = font_name
        run.font.size = Pt(font_size_pt)
        run.font.color.rgb = d["RGBColor"](0, 0, 0)

    return p


# ===========================================================================
# MAIN: corporate_markdown_to_docx
# ===========================================================================


def corporate_markdown_to_docx(
    markdown: str,
    template,
    metadata: dict[str, str] | None = None,
    image_map: dict | None = None,
    title: str = "Documento",
) -> bytes:
    """
    Convert markdown text into a DOCX file using the Wolbito corporate template.
    """
    d = _import_docx()
    Document = d["Document"]
    Cm = d["Cm"]
    Pt = d["Pt"]
    RGBColor = d["RGBColor"]
    WD_ALIGN_PARAGRAPH = d["WD_ALIGN_PARAGRAPH"]
    OxmlElement = d["OxmlElement"]
    qn = d["qn"]

    meta = metadata or {}
    meta.setdefault("title", title)

    doc = Document()
    _setup_page(doc, template)

    cfg = template.config
    font_name = cfg.get("font", "Arial")

    # ── Corporate header/footer (real, repeats on all pages) ──
    _setup_corporate_header_footer(doc, template, meta)

    # ── Parse and render markdown body ──
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    section_counter = 0
    is_first_h1 = True
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            i += 1
            continue

        # ── Callouts ──
        callout_match = re.match(
            r"^>\s*\[!(NOTE|TIP|WARNING|CAUTION)\]", stripped, re.IGNORECASE
        )
        if callout_match:
            callout_type = callout_match.group(1).upper()
            callout_colors = {
                "NOTE": "DBEAFE",
                "TIP": "D1FAE5",
                "WARNING": "FEF3C7",
                "CAUTION": "FEE2E2",
            }
            color_hex = callout_colors.get(callout_type, "DBEAFE")

            callout_lines = []
            first_content = re.sub(
                r"^>\s*\[!(NOTE|TIP|WARNING|CAUTION)\]\s*",
                "",
                stripped,
                flags=re.IGNORECASE,
            )
            if first_content:
                callout_lines.append(first_content)
            i += 1
            while i < len(lines):
                nl = lines[i].strip()
                if nl.startswith(">"):
                    content = nl[1:].strip()
                    if content:
                        callout_lines.append(content)
                    i += 1
                else:
                    break

            callout_text = " ".join(callout_lines) if callout_lines else callout_type

            emoji_map = {"WARNING": "⚠️", "TIP": "💡", "CAUTION": "🚨", "NOTE": "📝"}
            emoji = emoji_map.get(callout_type, "📌")

            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(1.5)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(f"{emoji} {callout_type}: {callout_text}")
            run.font.name = font_name
            run.font.size = Pt(10)
            pPr = p._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), color_hex)
            pPr.append(shd)
            continue

        # ── Headings ──
        if stripped.startswith("### "):
            text = stripped[4:].strip()
            _add_section_heading(doc, text, 3, template)
            i += 1
            continue

        if stripped.startswith("## "):
            text = stripped[3:].strip()
            _add_section_heading(doc, text, 2, template)
            i += 1
            continue

        if stripped.startswith("# "):
            text = stripped[2:].strip()
            if is_first_h1:
                is_first_h1 = False
                i += 1
                continue
            section_counter += 1
            numbering = cfg.get("section_numbering", True)
            num_str = str(section_counter) if numbering else None
            _add_section_heading(doc, text, 1, template, num_str)
            i += 1
            continue

        # ── [Imagem: Nome] placeholder ──
        img_placeholder = re.match(r"^\[Imagem:\s*(.+?)\]$", stripped, re.IGNORECASE)
        if img_placeholder:
            nome = img_placeholder.group(1).strip()
            img_bytes, err = _resolve_image(image_map, nome)
            if img_bytes and _validate_image_bytes(img_bytes):
                try:
                    doc.add_picture(io.BytesIO(img_bytes), width=Cm(14))
                    last_para = doc.paragraphs[-1]
                    last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap = doc.add_paragraph(f"Imagem: {nome}")
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    if cap.runs:
                        cap.runs[0].font.italic = True
                        cap.runs[0].font.name = font_name
                        cap.runs[0].font.size = Pt(9)
                        cap.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)
                except Exception as e:
                    logger.error("Erro ao inserir imagem %s: %s", nome, e)
                    p = doc.add_paragraph(f"[Imagem não encontrada: {nome}]")
                    if p.runs:
                        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            else:
                p = doc.add_paragraph(f"[Imagem não encontrada: {nome}]")
                if p.runs:
                    p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            i += 1
            continue

        # ── ![alt](url) — markdown images ──
        img_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if img_match:
            alt_text = img_match.group(1)
            img_url = img_match.group(2).strip()
            img_bytes = None

            if img_url.startswith("data:") and "base64," in img_url:
                try:
                    b64 = img_url.split("base64,", 1)[1]
                    img_bytes = base64.b64decode(b64)
                except Exception:
                    pass

            if img_bytes is None and image_map and alt_text:
                img_bytes, _ = _resolve_image(image_map, alt_text)

            if img_bytes is None and img_url and not img_url.startswith("data:"):
                path = Path(img_url)
                if path.exists():
                    try:
                        img_bytes = path.read_bytes()
                    except Exception:
                        pass

            if img_bytes and _validate_image_bytes(img_bytes):
                try:
                    doc.add_picture(io.BytesIO(img_bytes), width=Cm(14))
                    last_para = doc.paragraphs[-1]
                    last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap = doc.add_paragraph(f"Imagem: {alt_text or img_url}")
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    if cap.runs:
                        cap.runs[0].font.italic = True
                        cap.runs[0].font.size = Pt(9)
                        cap.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)
                except Exception:
                    p = doc.add_paragraph(
                        f"[Imagem não encontrada: {alt_text or img_url}]"
                    )
                    if p.runs:
                        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            else:
                p = doc.add_paragraph(f"[Imagem não encontrada: {alt_text or img_url}]")
                if p.runs:
                    p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            i += 1
            continue

        # ── Checklist ──
        if re.match(r"^[\s]*-\s*\[[\sxX]\]\s*", stripped):
            checked = bool(re.match(r"^[\s]*-\s*\[[xX]\]", stripped))
            text = re.sub(r"^[\s]*-\s*\[[\sxX]\]\s*", "", stripped)
            symbol = "☑" if checked else "☐"
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(1.5)
            for frag, bold in _parse_inline_bold(f"{symbol} {text}"):
                run = p.add_run(frag)
                run.bold = bold
                run.font.name = font_name
                run.font.size = Pt(11)
            i += 1
            continue

        # ── Unordered list ──
        if re.match(r"^[\s]*[-*]\s+", stripped):
            text = re.sub(r"^[\s]*[-*]\s+", "", stripped, count=1)
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.left_indent = Cm(2.0)
            for frag, bold in _parse_inline_bold(text):
                run = p.add_run(frag)
                run.bold = bold
                run.font.name = font_name
                run.font.size = Pt(11)
            i += 1
            continue

        # ── Numbered list ──
        num_match = re.match(r"^[\s]*(\d+)\.\s+", stripped)
        if num_match:
            text = stripped[num_match.end() :]
            p = doc.add_paragraph(style="List Number")
            p.paragraph_format.left_indent = Cm(2.5)
            for frag, bold in _parse_inline_bold(text):
                run = p.add_run(frag)
                run.bold = bold
                run.font.name = font_name
                run.font.size = Pt(11)
            i += 1
            continue

        # ── Markdown table ──
        if stripped.startswith("|") and stripped.endswith("|"):
            table_rows = []
            while i < len(lines):
                row_line = lines[i].strip()
                if row_line.startswith("|") and row_line.endswith("|"):
                    if not re.match(r"^\|[-:\s|]+\|$", row_line):
                        cells = [c.strip() for c in row_line.strip("|").split("|")]
                        table_rows.append(cells)
                    i += 1
                else:
                    break

            if table_rows:
                num_cols = max(len(row) for row in table_rows)
                tbl = doc.add_table(rows=len(table_rows), cols=num_cols)
                tbl.style = "Table Grid"

                for row_idx, row_data in enumerate(table_rows):
                    for col_idx, cell_text in enumerate(row_data):
                        if col_idx < num_cols:
                            cell = tbl.rows[row_idx].cells[col_idx]
                            cell.text = cell_text
                            for p in cell.paragraphs:
                                for run in p.runs:
                                    run.font.name = font_name
                                    run.font.size = Pt(10)
                                    if row_idx == 0:
                                        run.font.bold = True

                doc.add_paragraph()
            continue

        # ── OBS / NOTA / Observação ──
        obs_match = re.match(
            r"^(OBS|NOTA|Observação)\s*:?\s*(.*)", stripped, re.IGNORECASE
        )
        if obs_match:
            label = obs_match.group(1).upper()
            content = obs_match.group(2).strip()
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(1.5)
            run_label = p.add_run(f"{label}: ")
            run_label.font.bold = True
            run_label.font.name = font_name
            run_label.font.size = Pt(11)
            run_content = p.add_run(content)
            run_content.font.name = font_name
            run_content.font.size = Pt(11)
            pPr = p._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "FEF3C7")
            pPr.append(shd)
            i += 1
            continue

        # ── Normal paragraph ──
        _add_body_paragraph(doc, stripped, font_name=font_name)
        i += 1

    # (footer is configured in the document section and repeats on all pages)

    # ── Save to bytes ──
    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out.read()


# ===========================================================================
# STRUCTURED JSON → DOCX (corporate template)
# ===========================================================================


def corporate_structured_to_docx(
    data: dict,
    template,
    metadata: dict[str, str] | None = None,
    title: str = "Documento",
) -> bytes:
    """
    Convert structured JSON documentation into a DOCX file using the
    Wolbito corporate template layout.
    """
    d = _import_docx()
    Document = d["Document"]
    Cm = d["Cm"]
    Pt = d["Pt"]
    RGBColor = d["RGBColor"]
    WD_ALIGN_PARAGRAPH = d["WD_ALIGN_PARAGRAPH"]
    OxmlElement = d["OxmlElement"]
    qn = d["qn"]

    meta = metadata or {}
    meta.setdefault("title", title)

    doc = Document()
    _setup_page(doc, template)

    cfg = template.config
    font_name = cfg.get("font", "Arial")
    numbering = cfg.get("section_numbering", True)

    # ── Corporate header/footer (real, repeats on all pages) ──
    _setup_corporate_header_footer(doc, template, meta)

    section_num = 0

    # ── INTRODUCTION ──
    visao_geral = data.get("visao_geral", "")

    if template.id == "wolbito_pop":
        if visao_geral:
            section_num += 1
            _add_section_heading(
                doc, "INTRODUÇÃO", 1, template, str(section_num) if numbering else None
            )
            _add_body_paragraph(doc, visao_geral, font_name=font_name)

        objetivo_geral = meta.get("objective", "")
        if objetivo_geral:
            section_num += 1
            _add_section_heading(
                doc, "OBJETIVO", 1, template, str(section_num) if numbering else None
            )
            _add_body_paragraph(doc, objetivo_geral, font_name=font_name)

        abrangencia = meta.get("scope", "")
        if abrangencia:
            section_num += 1
            _add_section_heading(
                doc, "ABRANGÊNCIA", 1, template, str(section_num) if numbering else None
            )
            _add_body_paragraph(doc, abrangencia, font_name=font_name)

        referencias = meta.get("references", "")
        if referencias:
            section_num += 1
            _add_section_heading(
                doc, "REFERÊNCIAS", 1, template, str(section_num) if numbering else None
            )
            _add_body_paragraph(doc, referencias, font_name=font_name)

    else:
        if visao_geral:
            section_num += 1
            _add_section_heading(
                doc, "INTRODUÇÃO", 1, template, str(section_num) if numbering else None
            )
            _add_body_paragraph(doc, visao_geral, font_name=font_name)

    # ── PROCEDIMENTO / METODOLOGIA ──
    passos = data.get("passos", [])
    if passos:
        section_num += 1
        proc_num = section_num
        proc_title = "METODOLOGIA" if template.id == "wolbito_pop" else "PROCEDIMENTO"
        _add_section_heading(
            doc, proc_title, 1, template, str(proc_num) if numbering else None
        )

        for passo in passos:
            numero = passo.get("numero", 0)
            titulo = passo.get("titulo", f"Passo {numero}")
            objetivo = passo.get("objetivo", "")
            procedimento = passo.get("procedimento", [])
            imagem = passo.get("imagem")

            _add_section_heading(doc, f"Passo {numero}: {titulo}", 2, template)

            if objetivo:
                p_obj = doc.add_paragraph()
                p_obj.paragraph_format.left_indent = Cm(1.5)
                run_ol = p_obj.add_run("Objetivo: ")
                run_ol.font.bold = True
                run_ol.font.name = font_name
                run_ol.font.size = Pt(11)
                run_ov = p_obj.add_run(objetivo)
                run_ov.font.name = font_name
                run_ov.font.size = Pt(11)

            if isinstance(procedimento, list):
                for step_text in procedimento:
                    p = doc.add_paragraph(style="List Number")
                    p.paragraph_format.left_indent = Cm(2.5)
                    run_s = p.add_run(step_text)
                    run_s.font.name = font_name
                    run_s.font.size = Pt(11)
            elif procedimento:
                _add_body_paragraph(doc, str(procedimento), font_name=font_name)

            if imagem:
                img_p = doc.add_paragraph()
                img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run_img = img_p.add_run(f"[Imagem: {imagem}]")
                run_img.font.italic = True
                run_img.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    # ── DESVIOS E AÇÕES (POP only) ──
    if template.id == "wolbito_pop":
        section_num += 1
        _add_section_heading(
            doc, "DESVIOS E AÇÕES", 1, template, str(section_num) if numbering else None
        )
        desvios = meta.get("deviations", "")
        if desvios:
            _add_body_paragraph(doc, desvios, font_name=font_name)
        else:
            _add_body_paragraph(doc, "N/A", font_name=font_name, indent=False)

    # ── AVISOS ──
    avisos = data.get("avisos", [])
    if avisos:
        section_num += 1
        _add_section_heading(
            doc,
            "AVISOS IMPORTANTES",
            1,
            template,
            str(section_num) if numbering else None,
        )

        callout_colors = {
            "NOTE": "DBEAFE",
            "TIP": "D1FAE5",
            "WARNING": "FEF3C7",
            "CAUTION": "FEE2E2",
        }
        emoji_map = {"WARNING": "⚠️", "TIP": "💡", "CAUTION": "🚨", "NOTE": "📝"}

        for aviso in avisos:
            tipo = aviso.get("tipo", "NOTE").upper()
            texto = aviso.get("texto", "")
            color_hex = callout_colors.get(tipo, "DBEAFE")
            emoji = emoji_map.get(tipo, "📌")

            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(1.5)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(f"{emoji} {tipo}: {texto}")
            run.font.name = font_name
            run.font.size = Pt(10)
            pPr = p._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), color_hex)
            pPr.append(shd)

    # ── CHECKLIST ──
    checklist = data.get("checklist", [])
    if checklist:
        section_num += 1
        _add_section_heading(
            doc,
            "CHECKLIST DE VERIFICAÇÃO FINAL",
            1,
            template,
            str(section_num) if numbering else None,
        )

        intro = doc.add_paragraph()
        intro.paragraph_format.left_indent = Cm(1.5)
        run_intro = intro.add_run(
            "Antes de considerar o procedimento concluído, confirme:"
        )
        run_intro.font.name = font_name
        run_intro.font.size = Pt(11)

        for item in checklist:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(1.5)
            run = p.add_run(f"☐ {item}")
            run.font.name = font_name
            run.font.size = Pt(11)

    # ── TROUBLESHOOTING ──
    troubleshooting = data.get("troubleshooting", [])
    if troubleshooting:
        section_num += 1
        _add_section_heading(
            doc,
            "PROBLEMAS COMUNS E SOLUÇÕES",
            1,
            template,
            str(section_num) if numbering else None,
        )

        tbl = doc.add_table(rows=1, cols=3)
        tbl.style = "Table Grid"

        header_cells = tbl.rows[0].cells
        for idx, h_text in enumerate(["Problema", "Causa", "Solução"]):
            header_cells[idx].text = h_text
            for p in header_cells[idx].paragraphs:
                for run in p.runs:
                    run.font.bold = True
                    run.font.name = font_name
                    run.font.size = Pt(10)

        for item in troubleshooting:
            row = tbl.add_row().cells
            row[0].text = item.get("problema", "")
            row[1].text = item.get("causa", "")
            row[2].text = item.get("solucao", "")
            for cell in row:
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.font.name = font_name
                        run.font.size = Pt(10)

    # ── ANEXOS / DOCUMENTOS RELACIONADOS ──
    if template.id == "wolbito_pop":
        section_num += 1
        _add_section_heading(
            doc,
            "DOCUMENTOS RELACIONADOS E ANEXOS",
            1,
            template,
            str(section_num) if numbering else None,
        )
        _add_body_paragraph(doc, "N/A", font_name=font_name, indent=False)
    else:
        section_num += 1
        _add_section_heading(
            doc,
            "ANEXOS",
            1,
            template,
            str(section_num) if numbering else None,
        )
        _add_body_paragraph(doc, "N/A", font_name=font_name, indent=False)

        section_num += 1
        _add_section_heading(
            doc,
            "DOCUMENTOS DE REFERÊNCIAS",
            1,
            template,
            str(section_num) if numbering else None,
        )
        _add_body_paragraph(doc, "N/A", font_name=font_name, indent=False)

        section_num += 1
        _add_section_heading(
            doc,
            "REGISTROS",
            1,
            template,
            str(section_num) if numbering else None,
        )
        _add_body_paragraph(doc, "N/A", font_name=font_name, indent=False)

    # (footer is configured in the document section and repeats on all pages)

    # ── Save ──
    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out.read()
