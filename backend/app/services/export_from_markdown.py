"""
Exporta Markdown (saída do Gemini) para .docx ou .pdf.

Parsing simples: # ## ###, **negrito**, listas e checklist (- [ ]).
Placeholders [Imagem: Nome] e ![alt](path) ou data URL resolvidos via image_map.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Documentos longos com muitas imagens podem passar de 2 minutos.
LIBREOFFICE_TIMEOUT_SECONDS = int(os.getenv("CLIPBUILDER_LIBREOFFICE_TIMEOUT", "240"))


def _escape_html(s: str) -> str:
    """Escapa &, <, > para uso em Paragraph do reportlab."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _parse_inline_bold(text: str) -> list[tuple[str, bool]]:
    """Retorna lista de (fragmento, is_bold). Ex: 'Foo **bar** baz' -> [('Foo ', False), ('bar', True), (' baz', False)]."""
    parts: list[tuple[str, bool]] = []
    rest = text
    while rest:
        i = rest.find("**")
        if i == -1:
            if rest:
                parts.append((rest, False))
            break
        before = rest[:i]
        rest = rest[i + 2 :]
        j = rest.find("**")
        if j == -1:
            parts.append((before + "**" + rest, False))
            break
        if before:
            parts.append((before, False))
        parts.append((rest[:j], True))
        rest = rest[j + 2 :]
    return parts


def _validate_image_bytes(img_bytes: bytes) -> bool:
    """
    Validate image bytes with Pillow (verify integrity).
    Returns True if valid, False otherwise; logs errors.
    """
    try:
        from PIL import Image as PILImage

        pil_img = PILImage.open(io.BytesIO(img_bytes))
        pil_img.verify()
        return True
    except Exception as e:
        logger.error("Imagem inválida (Pillow verify): %s", e)
        return False


def _resolve_image(
    image_map: dict | None, name: str
) -> tuple[bytes | None, str | None]:
    """
    Resolve image bytes from image_map by name.
    name: e.g. "Passo 1".
    Returns (bytes, None) on success, (None, error_msg) on failure.
    Value in map can be: file path (str), data URL, base64 string, bytes, or file-like (e.g. BytesIO).
    """
    if not image_map or not name:
        return (None, "não encontrada")
    name = name.strip()
    if name not in image_map:
        return (None, "não encontrada")
    val = image_map[name]
    # bytes: return as-is
    if isinstance(val, bytes):
        return (val, None)
    # file-like (e.g. BytesIO)
    if hasattr(val, "read") and callable(getattr(val, "read", None)):
        try:
            val.seek(0)
            return (val.read(), None)
        except Exception as e:
            logger.warning("Imagem não legível (file-like) para %s: %s", name, e)
            return (None, str(e))
    if not isinstance(val, str):
        return (None, "valor inválido")
    val = val.strip()
    # data URL
    if val.startswith("data:") and "base64," in val:
        try:
            b64 = val.split("base64,", 1)[1]
            return (base64.b64decode(b64), None)
        except Exception as e:
            logger.warning("Imagem base64 (data URL) inválida para %s: %s", name, e)
            return (None, str(e))
    # raw base64 (no data: prefix)
    if val and not val.startswith("/") and ":" not in val[:2]:
        try:
            return (base64.b64decode(val), None)
        except Exception:
            pass
    # file path
    p = Path(val)
    if p.exists():
        try:
            return (p.read_bytes(), None)
        except Exception as e:
            logger.warning("Imagem não legível %s: %s", val, e)
            return (None, str(e))
    return (None, "path não existe")


def markdown_to_docx(markdown: str, image_map: dict | None = None) -> bytes:
    """
    Converte Markdown em bytes de um documento Word (.docx).

    Suporta: # ## ###, **negrito**, listas -, *, 1., - [ ] (checklist),
    [Imagem: Nome] e ![alt](path) ou data URL; image_map resolve Nome/alt para path ou base64.
    """
    try:
        from docx import Document
        from docx.shared import Inches, RGBColor
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'python-docx' não instalada. Instale no backend."
        ) from exc

    doc = Document()
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Headings
        if stripped.startswith("### "):
            doc.add_heading(stripped[4:].strip(), level=3)
            i += 1
            continue
        if stripped.startswith("## "):
            doc.add_heading(stripped[3:].strip(), level=2)
            i += 1
            continue
        if stripped.startswith("# "):
            doc.add_heading(stripped[2:].strip(), level=1)
            i += 1
            continue

        # Horizontal rule / ---
        if stripped in ("---", "***", "___"):
            i += 1
            continue

        # [Imagem: Nome] (custom placeholder)
        img_placeholder_match = re.match(
            r"^\[Imagem:\s*(.+?)\]$", stripped, re.IGNORECASE
        )
        if img_placeholder_match:
            nome = img_placeholder_match.group(1).strip()
            img_bytes, err = _resolve_image(image_map, nome)
            if img_bytes and _validate_image_bytes(img_bytes):
                try:
                    doc.add_picture(io.BytesIO(img_bytes), width=Inches(5.5))
                    cap = doc.add_paragraph(f"Imagem: {nome}")
                    if cap.runs:
                        cap.runs[0].font.italic = True
                    logger.info("Embutindo imagem: %s", nome)
                except Exception as e:
                    logger.error("Erro embutindo imagem %s: %s", nome, e)
                    p = doc.add_paragraph(f"[Imagem não encontrada: {nome}]")
                    if p.runs:
                        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            else:
                p = doc.add_paragraph(f"[Imagem não encontrada: {nome}]")
                if p.runs:
                    p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
                logger.warning("Imagem não encontrada: %s", nome)
            i += 1
            continue

        # ![alt](url) — data URL, image_map, or file path
        img_md_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if img_md_match:
            alt_text = img_md_match.group(1)
            url = img_md_match.group(2).strip()
            img_bytes = None
            if url.startswith("data:") and "base64," in url:
                try:
                    b64 = url.split("base64,", 1)[1]
                    img_bytes = base64.b64decode(b64)
                except Exception:
                    pass
            if img_bytes is None and image_map and alt_text:
                img_bytes, _ = _resolve_image(image_map, alt_text)
            if img_bytes is None and url and not url.startswith("data:"):
                path = Path(url)
                if path.exists():
                    try:
                        img_bytes = path.read_bytes()
                    except Exception:
                        pass
            if img_bytes and _validate_image_bytes(img_bytes):
                try:
                    doc.add_picture(io.BytesIO(img_bytes), width=Inches(5.5))
                    cap = doc.add_paragraph(f"Imagem: {alt_text or url}")
                    if cap.runs:
                        cap.runs[0].font.italic = True
                    logger.info("Embutindo imagem: %s", alt_text or url)
                except Exception:
                    p = doc.add_paragraph(f"[Imagem não encontrada: {alt_text or url}]")
                    if p.runs:
                        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            else:
                p = doc.add_paragraph(f"[Imagem não encontrada: {alt_text or url}]")
                if p.runs:
                    p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            i += 1
            continue

        # Checklist: - [ ] ou - [x]
        if re.match(r"^[\s]*-\s*\[[\sxX]\]\s*", stripped):
            text = re.sub(r"^[\s]*-\s*\[[\sxX]\]\s*", "☐ ", stripped)
            p = doc.add_paragraph()
            for frag, bold in _parse_inline_bold(text):
                run = p.add_run(frag)
                run.bold = bold
            i += 1
            continue

        # Unordered list: - item or * item
        if re.match(r"^[\s]*[-*]\s+", stripped):
            text = re.sub(r"^[\s]*[-*]\s+", "", stripped, count=1)
            p = doc.add_paragraph(style="List Bullet")
            for frag, bold in _parse_inline_bold(text):
                run = p.add_run(frag)
                run.bold = bold
            i += 1
            continue

        # Numbered list: 1. item
        num_match = re.match(r"^[\s]*(\d+)\.\s+", stripped)
        if num_match:
            text = stripped[num_match.end() :]
            p = doc.add_paragraph(style="List Number")
            for frag, bold in _parse_inline_bold(text):
                run = p.add_run(frag)
                run.bold = bold
            i += 1
            continue

        # Empty line
        if not stripped:
            i += 1
            continue

        # Normal paragraph
        p = doc.add_paragraph()
        for frag, bold in _parse_inline_bold(stripped):
            run = p.add_run(frag)
            run.bold = bold
        i += 1

    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out.read()


def markdown_to_docx_pro(
    markdown: str, title: str = "Documento", image_map: dict | None = None
) -> bytes:
    """
    Converte Markdown em bytes de um documento Word (.docx) com formatação profissional.

    Recursos:
    - Layout: US Letter, margens 1" (2.54cm), fonte Arial
    - Capa centrada na primeira página
    - Sumário automático (TOC) na segunda página
    - H1: Azul Escuro + quebra de página obrigatória
    - H2/H3: Tons de azul mais claros
    - Imagens: Centralizadas, max 15cm; [Imagem: Nome] e ![alt](url) via image_map
    - Callouts: Caixas com shading (NOTE=Azul, TIP=Verde, WARNING=Amarelo, CAUTION=Vermelho)
    - Rodapé: "Página X de Y"
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Cm, Inches, Pt, RGBColor
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'python-docx' não instalada. Instale no backend."
        ) from exc

    doc = Document()

    # -------------------------------------------------------------------------
    # 1. Page Setup: US Letter, 1 inch margins
    # -------------------------------------------------------------------------
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)

    # -------------------------------------------------------------------------
    # 2. Set default font to Arial
    # -------------------------------------------------------------------------
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Arial"
    font.size = Pt(11)

    # Also set Arial for headings
    for heading_level in range(1, 4):
        heading_style = doc.styles[f"Heading {heading_level}"]
        heading_style.font.name = "Arial"

    # -------------------------------------------------------------------------
    # 3. Define heading colors
    # -------------------------------------------------------------------------
    DARK_BLUE = RGBColor(0x1F, 0x4E, 0x79)  # #1F4E79 - H1
    MEDIUM_BLUE = RGBColor(0x2E, 0x75, 0xB6)  # #2E75B6 - H2
    LIGHT_BLUE = RGBColor(0x5B, 0x9B, 0xD5)  # #5B9BD5 - H3

    # Callout shading colors (XML hex format without #)
    CALLOUT_COLORS = {
        "NOTE": "DBEAFE",  # Light blue
        "TIP": "D1FAE5",  # Light green
        "WARNING": "FEF3C7",  # Light yellow
        "CAUTION": "FEE2E2",  # Light red
    }

    # -------------------------------------------------------------------------
    # Helper: Add shading to paragraph
    # -------------------------------------------------------------------------
    def _add_shading(paragraph, color_hex: str):
        """Add background shading to a paragraph."""
        pPr = paragraph._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), color_hex)
        pPr.append(shd)

    # -------------------------------------------------------------------------
    # Helper: Add page break before paragraph
    # -------------------------------------------------------------------------
    def _add_page_break_before(paragraph):
        """Force a page break before this paragraph."""
        pPr = paragraph._p.get_or_add_pPr()
        pb = OxmlElement("w:pageBreakBefore")
        pb.set(qn("w:val"), "true")
        pPr.append(pb)

    # -------------------------------------------------------------------------
    # Helper: Create footer with Page X of Y
    # -------------------------------------------------------------------------
    def _add_page_number_footer(section):
        """Add 'Página X de Y' footer."""
        footer = section.footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # "Página "
        run = p.add_run("Página ")
        run.font.name = "Arial"
        run.font.size = Pt(10)

        # PAGE field
        fldChar1 = OxmlElement("w:fldChar")
        fldChar1.set(qn("w:fldCharType"), "begin")
        instrText = OxmlElement("w:instrText")
        instrText.text = "PAGE"
        fldChar2 = OxmlElement("w:fldChar")
        fldChar2.set(qn("w:fldCharType"), "end")

        run2 = p.add_run()
        run2._r.append(fldChar1)
        run2._r.append(instrText)
        run2._r.append(fldChar2)

        # " de "
        run3 = p.add_run(" de ")
        run3.font.name = "Arial"
        run3.font.size = Pt(10)

        # NUMPAGES field
        fldChar3 = OxmlElement("w:fldChar")
        fldChar3.set(qn("w:fldCharType"), "begin")
        instrText2 = OxmlElement("w:instrText")
        instrText2.text = "NUMPAGES"
        fldChar4 = OxmlElement("w:fldChar")
        fldChar4.set(qn("w:fldCharType"), "end")

        run4 = p.add_run()
        run4._r.append(fldChar3)
        run4._r.append(instrText2)
        run4._r.append(fldChar4)

    # -------------------------------------------------------------------------
    # Helper: Add TOC field
    # -------------------------------------------------------------------------
    def _make_bookmark_id(text: str, used: set) -> str:
        """Generate a unique bookmark name from heading text."""
        import unicodedata

        slug = unicodedata.normalize("NFD", text)
        slug = "".join(ch for ch in slug if unicodedata.category(ch) != "Mn")
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_")[:40]
        slug = f"_bm_{slug}" if slug else "_bm_heading"
        base = slug
        counter = 1
        while slug in used:
            slug = f"{base}_{counter}"
            counter += 1
        used.add(slug)
        return slug

    def _extract_headings(md_text: str) -> list[tuple[int, str, str]]:
        """Pre-scan markdown to extract H1 and H2 headings for TOC.

        Returns list of (level, text, bookmark_id) tuples.
        - Skips the first H1 (document title, already on cover page).
        - Skips H3 and below (sub-sections like Objetivo/Procedimento/Observações
          clutter the TOC without adding navigation value).
        """
        headings: list[tuple[int, str, str]] = []
        used_ids: set[str] = set()
        found_first_h1 = False
        for raw_line in md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            s = raw_line.strip()
            if s.startswith("## "):
                txt = s[3:].strip()
                bm = _make_bookmark_id(txt, used_ids)
                headings.append((2, txt, bm))
            elif s.startswith("# ") and not s.startswith("### "):
                if not found_first_h1:
                    found_first_h1 = True
                    continue  # skip document title
                txt = s[2:].strip()
                bm = _make_bookmark_id(txt, used_ids)
                headings.append((1, txt, bm))
        return headings

    # Mapping from heading text -> bookmark_id, populated by _extract_headings,
    # consumed when rendering headings to insert bookmark anchors.
    _heading_bookmark_map: dict[str, str] = {}

    def _add_bookmark(paragraph, bookmark_name: str):
        """Insert a bookmark anchor (<w:bookmarkStart/End>) into a paragraph."""
        bm_id = str(id(paragraph))[-6:]  # unique-ish numeric id
        start = OxmlElement("w:bookmarkStart")
        start.set(qn("w:id"), bm_id)
        start.set(qn("w:name"), bookmark_name)
        end = OxmlElement("w:bookmarkEnd")
        end.set(qn("w:id"), bm_id)
        paragraph._p.insert(0, start)
        paragraph._p.append(end)

    def _add_hyperlink_run(
        paragraph,
        bookmark_name: str,
        text: str,
        font_name: str,
        font_size,
        font_color,
        bold: bool = False,
    ):
        """Add an internal hyperlink run pointing to a bookmark."""
        hyperlink = OxmlElement("w:hyperlink")
        hyperlink.set(qn("w:anchor"), bookmark_name)

        run_elem = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")

        rFonts = OxmlElement("w:rFonts")
        rFonts.set(qn("w:ascii"), font_name)
        rFonts.set(qn("w:hAnsi"), font_name)
        rPr.append(rFonts)

        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), str(int(font_size.pt * 2)))
        rPr.append(sz)

        color_el = OxmlElement("w:color")
        color_el.set(
            qn("w:val"),
            f"{font_color[0]:02X}{font_color[1]:02X}{font_color[2]:02X}"
            if isinstance(font_color, (tuple, list))
            else str(font_color).replace("#", ""),
        )
        rPr.append(color_el)

        if bold:
            b_el = OxmlElement("w:b")
            rPr.append(b_el)

        # Underline (typical for hyperlinks)
        u_el = OxmlElement("w:u")
        u_el.set(qn("w:val"), "none")
        rPr.append(u_el)

        run_elem.append(rPr)
        t = OxmlElement("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = text
        run_elem.append(t)

        hyperlink.append(run_elem)
        paragraph._p.append(hyperlink)

    def _add_static_toc(doc, headings: list[tuple[int, str, str]]):
        """Build a static (pre-filled) TOC with clickable links to bookmarks."""
        if not headings:
            p = doc.add_paragraph()
            run = p.add_run("(Nenhum título encontrado)")
            run.font.italic = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
            return

        for level, text, bookmark_id in headings:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)

            if level == 1:
                p.paragraph_format.left_indent = Cm(0)
                _add_hyperlink_run(
                    p,
                    bookmark_id,
                    text,
                    font_name="Arial",
                    font_size=Pt(13),
                    font_color=(0x1F, 0x4E, 0x79),
                    bold=True,
                )
            else:
                p.paragraph_format.left_indent = Cm(1)
                _add_hyperlink_run(
                    p,
                    bookmark_id,
                    text,
                    font_name="Arial",
                    font_size=Pt(11),
                    font_color=(0x2E, 0x75, 0xB6),
                    bold=False,
                )

    # -------------------------------------------------------------------------
    # 4. Add footer with page numbers
    # -------------------------------------------------------------------------
    _add_page_number_footer(section)

    # -------------------------------------------------------------------------
    # 5. Cover Page
    # -------------------------------------------------------------------------
    # Add vertical space
    for _ in range(5):
        doc.add_paragraph()

    # ClipBuilder icon centered on cover
    _cover_icon_path = (
        Path(__file__).resolve().parent.parent / "Icons" / "clipbuilder_icon.png"
    )
    if _cover_icon_path.exists():
        try:
            icon_para = doc.add_paragraph()
            icon_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            icon_run = icon_para.add_run()
            icon_run.add_picture(str(_cover_icon_path), width=Cm(4), height=Cm(4))
        except Exception as _icon_err:
            logger.warning("Não foi possível inserir ícone na capa: %s", _icon_err)

    doc.add_paragraph()

    # Title centered
    cover_title = doc.add_paragraph()
    cover_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cover_title.add_run(title)
    run.font.name = "Arial"
    run.font.size = Pt(36)
    run.font.bold = True
    run.font.color.rgb = DARK_BLUE

    # Subtitle/date
    doc.add_paragraph()
    cover_sub = doc.add_paragraph()
    cover_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = cover_sub.add_run("Documentação Técnica")
    run_sub.font.name = "Arial"
    run_sub.font.size = Pt(16)
    run_sub.font.color.rgb = MEDIUM_BLUE

    # Page break after cover
    doc.add_page_break()

    # -------------------------------------------------------------------------
    # 6. Table of Contents Page (static, pre-filled)
    # -------------------------------------------------------------------------
    toc_headings = _extract_headings(markdown)
    # Build lookup: heading text -> bookmark_id for use when rendering headings
    for _lvl, _txt, _bm in toc_headings:
        _heading_bookmark_map[_txt] = _bm

    toc_heading = doc.add_paragraph()
    toc_heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_toc = toc_heading.add_run("Sumário")
    run_toc.font.name = "Arial"
    run_toc.font.size = Pt(24)
    run_toc.font.bold = True
    run_toc.font.color.rgb = DARK_BLUE

    doc.add_paragraph()
    _add_static_toc(doc, toc_headings)
    doc.add_page_break()

    # -------------------------------------------------------------------------
    # 7. Parse and render Markdown content
    # -------------------------------------------------------------------------
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    is_first_h1 = True
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            i += 1
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            # Add a thin line or just skip
            i += 1
            continue

        # -----------------------------------------------------------------
        # Callouts: > [!NOTE], > [!TIP], > [!WARNING], > [!CAUTION]
        # -----------------------------------------------------------------
        callout_match = re.match(
            r"^>\s*\[!(NOTE|TIP|WARNING|CAUTION)\]", stripped, re.IGNORECASE
        )
        if callout_match:
            callout_type = callout_match.group(1).upper()
            callout_color = CALLOUT_COLORS.get(callout_type, "DBEAFE")

            # Collect all callout lines
            callout_lines = []
            # First line might have content after [!TYPE]
            first_line_content = re.sub(
                r"^>\s*\[!(NOTE|TIP|WARNING|CAUTION)\]\s*",
                "",
                stripped,
                flags=re.IGNORECASE,
            )
            if first_line_content:
                callout_lines.append(first_line_content)

            i += 1
            # Continue collecting lines that start with >
            while i < len(lines):
                next_line = lines[i].strip()
                if next_line.startswith(">"):
                    content = next_line[1:].strip()
                    if content:
                        callout_lines.append(content)
                    i += 1
                else:
                    break

            # Add callout box
            callout_text = (
                " ".join(callout_lines) if callout_lines else f"{callout_type}"
            )

            # Add label
            label_p = doc.add_paragraph()
            label_run = label_p.add_run(f"📌 {callout_type}: ")
            label_run.font.bold = True
            label_run.font.name = "Arial"
            label_run.font.size = Pt(11)
            _add_shading(label_p, callout_color)

            # Add content
            content_p = doc.add_paragraph()
            for frag, bold in _parse_inline_bold(callout_text):
                run = content_p.add_run(frag)
                run.bold = bold
                run.font.name = "Arial"
                run.font.size = Pt(11)
            _add_shading(content_p, callout_color)

            doc.add_paragraph()  # spacing after callout
            continue

        # -----------------------------------------------------------------
        # Headings
        # -----------------------------------------------------------------
        if stripped.startswith("### "):
            text = stripped[4:].strip()
            h = doc.add_heading(text, level=3)
            h.runs[0].font.color.rgb = LIGHT_BLUE
            h.runs[0].font.name = "Arial"
            # Add bookmark if this heading is in the TOC map
            if text in _heading_bookmark_map:
                _add_bookmark(h, _heading_bookmark_map[text])
            i += 1
            continue

        if stripped.startswith("## "):
            text = stripped[3:].strip()
            h = doc.add_heading(text, level=2)
            h.runs[0].font.color.rgb = MEDIUM_BLUE
            h.runs[0].font.name = "Arial"
            # Add bookmark anchor so TOC link navigates here
            if text in _heading_bookmark_map:
                _add_bookmark(h, _heading_bookmark_map[text])
            i += 1
            continue

        if stripped.startswith("# "):
            text = stripped[2:].strip()
            h = doc.add_heading(text, level=1)
            h.runs[0].font.color.rgb = DARK_BLUE
            h.runs[0].font.name = "Arial"
            # Add bookmark anchor so TOC link navigates here
            if text in _heading_bookmark_map:
                _add_bookmark(h, _heading_bookmark_map[text])
            # Page break before H1 (except maybe first)
            if not is_first_h1:
                _add_page_break_before(h)
            is_first_h1 = False
            i += 1
            continue

        # -----------------------------------------------------------------
        # [Imagem: Nome] (custom placeholder)
        # -----------------------------------------------------------------
        img_placeholder_match = re.match(
            r"^\[Imagem:\s*(.+?)\]$", stripped, re.IGNORECASE
        )
        if img_placeholder_match:
            nome = img_placeholder_match.group(1).strip()
            img_bytes, err = _resolve_image(image_map, nome)
            if img_bytes and _validate_image_bytes(img_bytes):
                try:
                    doc.add_picture(io.BytesIO(img_bytes), width=Cm(15))
                    last_para = doc.paragraphs[-1]
                    last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap = doc.add_paragraph(f"Imagem: {nome}")
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    if cap.runs:
                        cap.runs[0].font.italic = True
                        cap.runs[0].font.name = "Arial"
                        cap.runs[0].font.size = Pt(11)
                    logger.info("Embutindo imagem: %s", nome)
                except Exception as e:
                    logger.error("Erro embutindo imagem %s: %s", nome, e)
                    p = doc.add_paragraph(f"[Imagem não encontrada: {nome}]")
                    if p.runs:
                        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            else:
                p = doc.add_paragraph(f"[Imagem não encontrada: {nome}]")
                if p.runs:
                    p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
                logger.warning("Imagem não encontrada: %s", nome)
            i += 1
            continue

        # -----------------------------------------------------------------
        # Images: ![alt](path) or data URL or image_map
        # -----------------------------------------------------------------
        img_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", stripped)
        if img_match:
            alt_text = img_match.group(1)
            img_path = img_match.group(2).strip()
            img_bytes = None
            if img_path.startswith("data:") and "base64," in img_path:
                try:
                    b64 = img_path.split("base64,", 1)[1]
                    img_bytes = base64.b64decode(b64)
                except Exception:
                    pass
            if img_bytes is None and image_map and alt_text:
                img_bytes, _ = _resolve_image(image_map, alt_text)
            if img_bytes is None and img_path and not img_path.startswith("data:"):
                img_file = Path(img_path)
                if img_file.exists():
                    try:
                        img_bytes = img_file.read_bytes()
                    except Exception:
                        pass
            if img_bytes and _validate_image_bytes(img_bytes):
                try:
                    doc.add_picture(io.BytesIO(img_bytes), width=Cm(15))
                    last_para = doc.paragraphs[-1]
                    last_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap = doc.add_paragraph(f"Imagem: {alt_text or img_path}")
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    if cap.runs:
                        cap.runs[0].font.italic = True
                        cap.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)
                    logger.info("Embutindo imagem: %s", alt_text or img_path)
                except Exception:
                    p = doc.add_paragraph(
                        f"[Imagem não encontrada: {alt_text or img_path}]"
                    )
                    if p.runs:
                        p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            else:
                p = doc.add_paragraph(
                    f"[Imagem não encontrada: {alt_text or img_path}]"
                )
                if p.runs:
                    p.runs[0].font.color.rgb = RGBColor(255, 0, 0)
            i += 1
            continue

        # -----------------------------------------------------------------
        # Checklist: - [ ] or - [x]
        # -----------------------------------------------------------------
        if re.match(r"^[\s]*-\s*\[[\sxX]\]\s*", stripped):
            checked = re.match(r"^[\s]*-\s*\[[xX]\]", stripped)
            text = re.sub(r"^[\s]*-\s*\[[\sxX]\]\s*", "", stripped)
            symbol = "☑" if checked else "☐"
            p = doc.add_paragraph()
            for frag, bold in _parse_inline_bold(f"{symbol} {text}"):
                run = p.add_run(frag)
                run.bold = bold
                run.font.name = "Arial"
            i += 1
            continue

        # -----------------------------------------------------------------
        # Unordered list: - item or * item
        # -----------------------------------------------------------------
        if re.match(r"^[\s]*[-*]\s+", stripped):
            text = re.sub(r"^[\s]*[-*]\s+", "", stripped, count=1)
            p = doc.add_paragraph(style="List Bullet")
            for frag, bold in _parse_inline_bold(text):
                run = p.add_run(frag)
                run.bold = bold
                run.font.name = "Arial"
            i += 1
            continue

        # -----------------------------------------------------------------
        # Numbered list: 1. item
        # -----------------------------------------------------------------
        num_match = re.match(r"^[\s]*(\d+)\.\s+", stripped)
        if num_match:
            text = stripped[num_match.end() :]
            p = doc.add_paragraph(style="List Number")
            for frag, bold in _parse_inline_bold(text):
                run = p.add_run(frag)
                run.bold = bold
                run.font.name = "Arial"
            i += 1
            continue

        # -----------------------------------------------------------------
        # Table: | col1 | col2 |
        # -----------------------------------------------------------------
        if stripped.startswith("|") and stripped.endswith("|"):
            table_rows = []
            while i < len(lines):
                row_line = lines[i].strip()
                if row_line.startswith("|") and row_line.endswith("|"):
                    # Skip separator rows (|---|---|)
                    if not re.match(r"^\|[-:\s|]+\|$", row_line):
                        cells = [c.strip() for c in row_line.strip("|").split("|")]
                        table_rows.append(cells)
                    i += 1
                else:
                    break

            if table_rows:
                num_cols = max(len(row) for row in table_rows)
                table = doc.add_table(rows=len(table_rows), cols=num_cols)
                table.style = "Table Grid"

                for row_idx, row_data in enumerate(table_rows):
                    for col_idx, cell_text in enumerate(row_data):
                        if col_idx < num_cols:
                            cell = table.rows[row_idx].cells[col_idx]
                            cell.text = cell_text
                            # Bold header row
                            if row_idx == 0:
                                for p in cell.paragraphs:
                                    for run in p.runs:
                                        run.font.bold = True
                                        run.font.name = "Arial"

                doc.add_paragraph()  # spacing after table
            continue

        # -----------------------------------------------------------------
        # Normal paragraph
        # -----------------------------------------------------------------
        p = doc.add_paragraph()
        for frag, bold in _parse_inline_bold(stripped):
            run = p.add_run(frag)
            run.bold = bold
            run.font.name = "Arial"
        i += 1

    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out.read()


def structured_json_to_docx(data: dict, title: str = "Documento") -> bytes:
    """
    Converte JSON estruturado (saída de generate_structured_documentation) em DOCX profissional.

    Estrutura esperada do JSON:
    {
        "visao_geral": str,
        "passos": [{"numero": int, "titulo": str, "objetivo": str, "procedimento": list[str], "imagem": str}],
        "avisos": [{"tipo": "WARNING"|"TIP"|"NOTE", "texto": str}],
        "checklist": list[str],
        "troubleshooting": [{"problema": str, "causa": str, "solucao": str}]
    }
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Cm, Inches, Pt, RGBColor
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'python-docx' não instalada. Instale no backend."
        ) from exc

    doc = Document()

    # -------------------------------------------------------------------------
    # Page Setup: US Letter, 1 inch margins
    # -------------------------------------------------------------------------
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)

    # -------------------------------------------------------------------------
    # Set default font to Arial
    # -------------------------------------------------------------------------
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Arial"
    font.size = Pt(11)

    # Colors
    DARK_BLUE = RGBColor(0x1F, 0x4E, 0x79)
    MEDIUM_BLUE = RGBColor(0x2E, 0x75, 0xB6)

    CALLOUT_COLORS = {
        "NOTE": "DBEAFE",
        "TIP": "D1FAE5",
        "WARNING": "FEF3C7",
        "CAUTION": "FEE2E2",
    }

    def _add_shading(paragraph, color_hex: str):
        pPr = paragraph._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), color_hex)
        pPr.append(shd)

    def _add_page_number_footer(section):
        footer = section.footer
        footer.is_linked_to_previous = False
        p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        run = p.add_run("Página ")
        run.font.name = "Arial"
        run.font.size = Pt(10)

        fldChar1 = OxmlElement("w:fldChar")
        fldChar1.set(qn("w:fldCharType"), "begin")
        instrText = OxmlElement("w:instrText")
        instrText.text = "PAGE"
        fldChar2 = OxmlElement("w:fldChar")
        fldChar2.set(qn("w:fldCharType"), "end")

        run2 = p.add_run()
        run2._r.append(fldChar1)
        run2._r.append(instrText)
        run2._r.append(fldChar2)

        run3 = p.add_run(" de ")
        run3.font.name = "Arial"
        run3.font.size = Pt(10)

        fldChar3 = OxmlElement("w:fldChar")
        fldChar3.set(qn("w:fldCharType"), "begin")
        instrText2 = OxmlElement("w:instrText")
        instrText2.text = "NUMPAGES"
        fldChar4 = OxmlElement("w:fldChar")
        fldChar4.set(qn("w:fldCharType"), "end")

        run4 = p.add_run()
        run4._r.append(fldChar3)
        run4._r.append(instrText2)
        run4._r.append(fldChar4)

    # Add footer
    _add_page_number_footer(section)

    # -------------------------------------------------------------------------
    # Cover Page
    # -------------------------------------------------------------------------
    for _ in range(3):
        doc.add_paragraph()

    # ClipBuilder icon centered on cover
    _cover_icon_path = (
        Path(__file__).resolve().parent.parent / "Icons" / "clipbuilder_icon.png"
    )
    if _cover_icon_path.exists():
        try:
            icon_para = doc.add_paragraph()
            icon_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            icon_run = icon_para.add_run()
            icon_run.add_picture(str(_cover_icon_path), width=Cm(3.5), height=Cm(3.5))
        except Exception as _icon_err:
            logger.warning("Não foi possível inserir ícone na capa: %s", _icon_err)

    doc.add_paragraph()

    cover_title = doc.add_paragraph()
    cover_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = cover_title.add_run(title)
    run.font.name = "Arial"
    run.font.size = Pt(32)
    run.font.bold = True
    run.font.color.rgb = DARK_BLUE

    doc.add_paragraph()
    cover_sub = doc.add_paragraph()
    cover_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = cover_sub.add_run("Documentação Técnica")
    run_sub.font.name = "Arial"
    run_sub.font.size = Pt(14)
    run_sub.font.color.rgb = MEDIUM_BLUE

    doc.add_page_break()

    # -------------------------------------------------------------------------
    # Visão Geral
    # -------------------------------------------------------------------------
    h = doc.add_heading("Visão Geral", level=1)
    h.runs[0].font.color.rgb = DARK_BLUE
    h.runs[0].font.name = "Arial"

    visao_geral = data.get("visao_geral", "")
    if visao_geral:
        p = doc.add_paragraph(visao_geral)
        p.runs[0].font.name = "Arial" if p.runs else None

    doc.add_paragraph()

    # -------------------------------------------------------------------------
    # Passos
    # -------------------------------------------------------------------------
    passos = data.get("passos", [])
    for passo in passos:
        numero = passo.get("numero", 0)
        titulo = passo.get("titulo", f"Passo {numero}")
        objetivo = passo.get("objetivo", "")
        procedimento = passo.get("procedimento", [])
        imagem = passo.get("imagem")

        # Título do passo
        h = doc.add_heading(f"Passo {numero}: {titulo}", level=2)
        h.runs[0].font.color.rgb = MEDIUM_BLUE
        h.runs[0].font.name = "Arial"

        # Objetivo
        obj_label = doc.add_paragraph()
        run_label = obj_label.add_run("Objetivo")
        run_label.font.bold = True
        run_label.font.name = "Arial"
        run_label.font.size = Pt(11)

        if objetivo:
            obj_p = doc.add_paragraph(objetivo)
            for r in obj_p.runs:
                r.font.name = "Arial"

        # Procedimento
        proc_label = doc.add_paragraph()
        run_proc = proc_label.add_run("Procedimento")
        run_proc.font.bold = True
        run_proc.font.name = "Arial"
        run_proc.font.size = Pt(11)

        if isinstance(procedimento, list):
            for step_text in procedimento:
                p = doc.add_paragraph(style="List Number")
                p.add_run(step_text).font.name = "Arial"
        elif procedimento:
            p = doc.add_paragraph(str(procedimento))
            for r in p.runs:
                r.font.name = "Arial"

        # Imagem placeholder
        if imagem:
            img_p = doc.add_paragraph()
            img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run_img = img_p.add_run(f"[Imagem: {imagem}]")
            run_img.font.italic = True
            run_img.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

        doc.add_paragraph()

    # -------------------------------------------------------------------------
    # Avisos
    # -------------------------------------------------------------------------
    avisos = data.get("avisos", [])
    if avisos:
        h = doc.add_heading("Avisos Importantes", level=2)
        h.runs[0].font.color.rgb = MEDIUM_BLUE
        h.runs[0].font.name = "Arial"

        for aviso in avisos:
            tipo = aviso.get("tipo", "NOTE").upper()
            texto = aviso.get("texto", "")
            color_hex = CALLOUT_COLORS.get(tipo, "DBEAFE")

            emoji = {"WARNING": "⚠️", "TIP": "💡", "CAUTION": "🚨", "NOTE": "📝"}.get(
                tipo, "📌"
            )

            p = doc.add_paragraph()
            run = p.add_run(f"{emoji} {tipo}: {texto}")
            run.font.name = "Arial"
            _add_shading(p, color_hex)

        doc.add_paragraph()

    # -------------------------------------------------------------------------
    # Checklist de Verificação Final
    # -------------------------------------------------------------------------
    checklist = data.get("checklist", [])
    if checklist:
        h = doc.add_heading("Checklist de Verificação Final", level=2)
        h.runs[0].font.color.rgb = MEDIUM_BLUE
        h.runs[0].font.name = "Arial"

        intro = doc.add_paragraph(
            "Antes de considerar o procedimento concluído, confirme:"
        )
        for r in intro.runs:
            r.font.name = "Arial"

        for item in checklist:
            p = doc.add_paragraph()
            run = p.add_run(f"☐ {item}")
            run.font.name = "Arial"

        doc.add_paragraph()

    # -------------------------------------------------------------------------
    # Tabela de Troubleshooting
    # -------------------------------------------------------------------------
    troubleshooting = data.get("troubleshooting", [])
    if troubleshooting:
        h = doc.add_heading("Problemas Comuns e Soluções", level=2)
        h.runs[0].font.color.rgb = MEDIUM_BLUE
        h.runs[0].font.name = "Arial"

        # Create table
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"

        # Header row
        header_cells = table.rows[0].cells
        headers = ["Problema", "Causa", "Solução"]
        for i, header_text in enumerate(headers):
            header_cells[i].text = header_text
            for p in header_cells[i].paragraphs:
                for run in p.runs:
                    run.font.bold = True
                    run.font.name = "Arial"

        # Data rows
        for item in troubleshooting:
            row = table.add_row().cells
            row[0].text = item.get("problema", "")
            row[1].text = item.get("causa", "")
            row[2].text = item.get("solucao", "")

            for cell in row:
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.font.name = "Arial"

    # Save to bytes
    out = io.BytesIO()
    doc.save(out)
    out.seek(0)
    return out.read()


def convert_docx_to_pdf(input_docx: str, output_pdf: str) -> None:
    """
    Converte DOCX em PDF usando LibreOffice headless.
    Preserva 100% do layout (estilos, imagens, caixas, tabelas).

    LibreOffice escreve <input_basename>.pdf no --outdir.
    output_pdf deve ser o caminho completo esperado (ex: /tmp/xxx.pdf).
    """
    out_dir = os.path.dirname(output_pdf)

    # Perfil de usuário próprio para cada conversão.  Sem isso, duas instâncias
    # simultâneas do LibreOffice disputam ~/.config/libreoffice e uma delas
    # aborta — cenário real desde que as exportações passaram a rodar em
    # paralelo em worker threads.
    with tempfile.TemporaryDirectory(prefix="lo_profile_") as profile_dir:
        try:
            subprocess.run(
                [
                    "libreoffice",
                    f"-env:UserInstallation=file://{profile_dir}",
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    out_dir,
                    input_docx,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=LIBREOFFICE_TIMEOUT_SECONDS,
            )
            logger.info("Convertido %s para %s", input_docx, output_pdf)
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or "").strip() if e.stderr else ""
            raise ValueError(
                f"LibreOffice falhou ao converter DOCX para PDF: {stderr or str(e)}"
            ) from e
        except subprocess.TimeoutExpired as e:
            raise ValueError(f"LibreOffice expirou (timeout) ao converter: {e}") from e
        except FileNotFoundError as e:
            raise ValueError(
                "LibreOffice não encontrado. Instale libreoffice no container."
            ) from e
        except Exception as e:
            raise ValueError(f"Erro na conversão DOCX→PDF: {e}") from e


def markdown_to_pdf_via_libreoffice(
    markdown: str,
    image_map: dict | None = None,
    use_pro: bool = True,
    title: str = "Documento",
) -> bytes:
    """
    Converte Markdown em PDF via DOCX + LibreOffice.
    Preserva estilos, imagens, callouts (TIP/WARNING), tabelas.
    Fallback para reportlab se LibreOffice falhar.
    """
    docx_bytes = (
        markdown_to_docx_pro(markdown, title=title, image_map=image_map)
        if use_pro
        else markdown_to_docx(markdown, image_map=image_map)
    )
    # Diretório temporário próprio: respeita TMPDIR, evita colisão entre
    # conversões simultâneas e some sozinho — inclusive quando o LibreOffice
    # deixa arquivos auxiliares para trás.
    try:
        with tempfile.TemporaryDirectory(prefix="md2pdf_") as work_dir:
            temp_docx = str(Path(work_dir) / "documento.docx")
            temp_pdf = str(Path(work_dir) / "documento.pdf")

            Path(temp_docx).write_bytes(docx_bytes)
            convert_docx_to_pdf(temp_docx, temp_pdf)

            pdf_path = Path(temp_docx).with_suffix(".pdf")
            if not pdf_path.exists():
                raise ValueError("LibreOffice não criou o arquivo PDF")
            return pdf_path.read_bytes()
    except (ValueError, OSError) as e:
        logger.warning(
            "LibreOffice falhou, usando fallback reportlab: %s",
            e,
        )
        return markdown_to_pdf(markdown, image_map=image_map)


def _image_to_data_url(
    image_map: dict | None,
    name: str,
) -> str | None:
    """
    Resolve image from image_map to data URL (base64).
    image_map values: path (str), data URL (str), base64 (str), or bytes.
    Returns data:image/png;base64,... or None if not found.
    """
    if not image_map or not name or name not in image_map:
        return None
    val = image_map[name]
    if isinstance(val, bytes):
        return f"data:image/png;base64,{base64.b64encode(val).decode('ascii')}"
    if isinstance(val, str):
        img_bytes, _ = _resolve_image(image_map, name)
        if img_bytes:
            return (
                f"data:image/png;base64,{base64.b64encode(img_bytes).decode('ascii')}"
            )
    return None


def _slug_for_heading(text: str, used: set[str]) -> str:
    """Generate a unique slug from heading text for id attributes (ASCII-safe)."""
    slug = re.sub(r"[^a-zA-Z0-9\s_-]", "", text).strip()
    slug = re.sub(r"[-\s]+", "-", slug).lower().strip("-") or "section"
    base = slug
    idx = 0
    while slug in used:
        idx += 1
        slug = f"{base}-{idx}"
    used.add(slug)
    return slug


def markdown_to_html(
    md_content: str,
    image_map: dict | None = None,
    output_path: str | None = None,
    title: str = "Documento",
    subtitle: str = "Documentação Técnica",
) -> str:
    """
    Converte Markdown em HTML standalone com CSS inline.
    Imagens como base64 para portabilidade.
    Suporta: capa, sumário (TOC), callouts (NOTE/TIP/WARNING), tabelas, checklists, [Imagem: Nome].
    """
    try:
        import markdown
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'markdown' (python-markdown) não instalada. Instale: pip install markdown"
        ) from exc

    image_map = image_map or {}
    md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
    lines = md_content.split("\n")

    # Callout class map: NOTE/TIP/WARNING/CAUTION -> .note, .tip, .warning
    _callout_class = {
        "NOTE": "note",
        "TIP": "tip",
        "WARNING": "warning",
        "CAUTION": "warning",
    }

    # Pre-process callouts (multi-line): > [!NOTE], > [!TIP], > [!WARNING], > [!CAUTION]
    processed_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        callout_match = re.match(
            r"^>\s*\[!(NOTE|TIP|WARNING|CAUTION)\](?:\s*(.*))?$",
            stripped,
            re.IGNORECASE,
        )
        if callout_match:
            callout_type = callout_match.group(1).upper()
            first_content = (callout_match.group(2) or "").strip()
            callout_lines = [first_content] if first_content else []
            i += 1
            while i < len(lines) and lines[i].strip().startswith(">"):
                content = lines[i].strip()[1:].strip()
                if content:
                    callout_lines.append(content)
                i += 1
            callout_text = " ".join(callout_lines) or callout_type
            callout_inner = markdown.markdown(callout_text, extensions=[])
            cls = _callout_class.get(callout_type, "note")
            processed_lines.append(f'<div class="{cls}">{callout_inner.strip()}</div>')
            continue
        # Single-line callouts: [!NOTE] Text, [!TIP] Text, etc.
        single_callout = re.match(
            r"^\s*\[!(NOTE|TIP|WARNING|CAUTION)\]\s*(.*)$",
            stripped,
            re.IGNORECASE,
        )
        if single_callout:
            callout_type = single_callout.group(1).upper()
            content = (single_callout.group(2) or "").strip()
            cls = _callout_class.get(callout_type, "note")
            inner = (
                markdown.markdown(content, extensions=[]) if content else callout_type
            )
            processed_lines.append(f'<div class="{cls}">{inner.strip()}</div>')
            i += 1
            continue
        processed_lines.append(line)
        i += 1

    md_processed = "\n".join(processed_lines)

    # Pre-process checklists: - [ ] and - [x] (markdown will convert to list)
    # We'll post-process list items for checkbox
    md_processed = re.sub(
        r"^(\s*)[-*]\s+\[ \]\s+",
        r"\1- ☐ ",
        md_processed,
        flags=re.MULTILINE,
    )
    md_processed = re.sub(
        r"^(\s*)[-*]\s+\[[xX]\]\s+",
        r"\1- ☑ ",
        md_processed,
        flags=re.MULTILINE,
    )

    # Convert Markdown to HTML
    html_body = markdown.markdown(
        md_processed,
        extensions=["tables", "fenced_code", "nl2br"],
    )

    # Post-process checklists: ☐ → checkbox unchecked, ☑ → checkbox checked
    html_body = re.sub(
        r"<li>\s*☐\s+",
        r'<li><input type="checkbox" disabled> ',
        html_body,
    )
    html_body = re.sub(
        r"<li>\s*☑\s+",
        r'<li><input type="checkbox" disabled checked> ',
        html_body,
    )

    # Post-process [Imagem: Nome] placeholders: resolve, validate Pillow, base64 embed
    _img_style = "max-width:80%; height:auto; border:1px solid #ddd; border-radius:4px; display:block; margin:20px auto;"
    _cap_style = "text-align:center; font-style:italic; color:#666;"

    def _replace_imagem_placeholder(match: re.Match[str]) -> str:
        nome = match.group(1).strip()
        if nome not in image_map:
            logger.error("Imagem não encontrada no image_map: %s", nome)
            return f'<p style="color:red; font-weight:bold;">[Imagem não encontrada: {nome}]</p>'
        img_bytes, err = _resolve_image(image_map, nome)
        if not img_bytes:
            logger.error("Erro embutindo imagem %s: %s", nome, err)
            return f'<p style="color:red; font-weight:bold;">[Imagem não encontrada: {nome}]</p>'
        if not _validate_image_bytes(img_bytes):
            logger.error("Erro embutindo imagem (inválida): %s", nome)
            return f'<p style="color:red; font-weight:bold;">[Imagem não encontrada: {nome}]</p>'
        logger.info("Embutindo imagem: %s", nome)
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        return (
            f'<img src="data:image/png;base64,{b64}" alt="{nome}" style="{_img_style}>'
            f'<p style="{_cap_style}">Imagem: {nome}</p>'
        )

    html_body = re.sub(r"\[Imagem:\s*(.+?)\]", _replace_imagem_placeholder, html_body)

    # Post-process <img> from ![alt](url): resolve via image_map, validate Pillow, base64
    def _replace_img(m: re.Match[str]) -> str:
        alt = m.group(1).strip()
        img_bytes, err = (
            _resolve_image(image_map, alt) if image_map and alt else (None, None)
        )
        if not img_bytes:
            logger.error("Imagem não encontrada para alt %s: %s", alt, err)
            return f'<p style="color:red; font-weight:bold;">[Imagem não encontrada: {alt}]</p>'
        if not _validate_image_bytes(img_bytes):
            logger.error("Erro embutindo imagem (inválida): %s", alt)
            return f'<p style="color:red; font-weight:bold;">[Imagem não encontrada: {alt}]</p>'
        logger.info("Embutindo imagem: %s", alt)
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        return (
            f'<img src="data:image/png;base64,{b64}" alt="{alt}" style="{_img_style}">'
            f'<p style="{_cap_style}">Imagem: {alt}</p>'
        )

    html_body = re.sub(
        r'<img\s+[^>]*alt=["\']([^"\']*)["\'][^>]*>', _replace_img, html_body
    )

    # Add table class for styling
    html_body = re.sub(r"<table>", '<table class="doc-table">', html_body)

    # TOC: add ids to h2/h3 and build nav (BeautifulSoup)
    toc_html = ""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_body, "html.parser")
        used_ids: set[str] = set()
        toc_items: list[str] = []
        for tag in soup.find_all(["h2", "h3"]):
            text = tag.get_text(strip=True)
            slug = _slug_for_heading(text, used_ids)
            tag["id"] = slug
            toc_items.append(f'<li><a href="#{slug}">{text}</a></li>')
        if toc_items:
            toc_html = "<nav><h2>Sumário</h2><ul>" + "".join(toc_items) + "</ul></nav>"
        html_body = str(soup)
    except ImportError:
        pass

    # CSS inline (match PDF spec: Arial, #001F3F headings, .note/.tip/.warning, tables)
    css = """
    body { font-family: Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 0 24px; }
    h1, h2 { color: #001F3F; }
    h1 { font-size: 24px; font-weight: bold; margin: 0 0 16px; }
    h2 { font-size: 18px; font-weight: bold; margin: 24px 0 8px; }
    h3 { font-size: 16px; font-weight: bold; margin: 20px 0 6px; color: #001F3F; }
    .note { background: #E0F7FA; border: 1px solid #00BCD4; padding: 10px; border-radius: 4px; margin: 12px 0; }
    .tip { background: #E8F5E9; border: 1px solid #4CAF50; padding: 10px; border-radius: 4px; margin: 12px 0; }
    .warning { background: #FFF3E0; border: 1px solid #FF9800; padding: 10px; border-radius: 4px; margin: 12px 0; }
    table.doc-table { border-collapse: collapse; width: 100%; margin: 16px 0; }
    table.doc-table th, table.doc-table td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    table.doc-table th { background: #f2f2f2; font-weight: bold; }
    ul li input[type="checkbox"] { margin-right: 8px; vertical-align: middle; }
    pre { background: #f6f8fa; padding: 12px; border-radius: 6px; overflow: auto; border: 1px solid #e1e4e8; }
    figure { margin: 1em 0; }
    """

    safe_title = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    safe_subtitle = (
        subtitle.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    # Embed ClipBuilder icon as base64 for HTML cover
    _html_icon_path = (
        Path(__file__).resolve().parent.parent / "Icons" / "clipbuilder_icon.png"
    )
    _icon_img_tag = ""
    if _html_icon_path.exists():
        try:
            _icon_b64 = base64.b64encode(_html_icon_path.read_bytes()).decode("utf-8")
            _icon_img_tag = (
                f'<img src="data:image/png;base64,{_icon_b64}" '
                f'alt="ClipBuilder" '
                f'style="width:80px; height:80px; margin:0 auto 16px; display:block;">'
            )
        except Exception:
            pass

    header_html = (
        '<header style="text-align:center; margin-bottom:40px;">'
        f"{_icon_img_tag}"
        f'<h1 style="color:#001F3F; font-size:36px;">{safe_title}</h1>'
        f'<h2 style="color:#001F3F; font-size:24px;">{safe_subtitle}</h2>'
        "</header>"
    )
    footer_html = (
        '<footer style="text-align:center; color:#999; border-top:1px solid #ddd; margin-top:40px;">'
        "Página simulada</footer>"
    )
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_title}</title>
    <style>{css}</style>
</head>
<body>
{header_html}
{toc_html}
{html_body}
{footer_html}
</body>
</html>"""

    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")

    return html


def markdown_to_pdf(markdown: str, image_map: dict | None = None) -> bytes:
    """
    Converte Markdown em bytes de um PDF.

    Reutiliza padrão do projeto: DejaVu/Helvetica, SimpleDocTemplate, Paragraph.
    image_map: nome -> path ou base64 para [Imagem: Nome] e ![alt](...).
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Image as RLImage
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise RuntimeError(
            "Dependência 'reportlab' não instalada. Instale no backend."
        ) from exc

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
        base_font = "DejaVuSans"
    except Exception:
        base_font = "Helvetica"

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "MdTitle",
        parent=styles["Title"],
        fontName=base_font,
    )
    h2_style = ParagraphStyle(
        "MdH2",
        parent=styles["Heading2"],
        fontName=base_font,
        spaceBefore=12,
        spaceAfter=6,
    )
    h3_style = ParagraphStyle(
        "MdH3",
        parent=styles["Heading3"],
        fontName=base_font,
        spaceBefore=10,
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "MdBody",
        parent=styles["BodyText"],
        fontName=base_font,
        leading=14,
    )
    error_style = ParagraphStyle(
        "MdError",
        parent=body_style,
        textColor=(1, 0, 0),
    )

    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title="Manual",
    )

    story: list[object] = []
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    max_img_width = 5 * inch

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("### "):
            text = _escape_html(stripped[4:].strip())
            story.append(Paragraph(text, h3_style))
            story.append(Spacer(1, 4))
            i += 1
            continue
        if stripped.startswith("## "):
            text = _escape_html(stripped[3:].strip())
            story.append(Paragraph(text, h2_style))
            story.append(Spacer(1, 6))
            i += 1
            continue
        if stripped.startswith("# "):
            text = _escape_html(stripped[2:].strip())
            story.append(Paragraph(text, title_style))
            story.append(Spacer(1, 12))
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            i += 1
            continue

        # [Imagem: Nome]
        img_placeholder_match = re.match(
            r"^\[Imagem:\s*(.+?)\]$", stripped, re.IGNORECASE
        )
        if img_placeholder_match:
            nome = img_placeholder_match.group(1).strip()
            img_bytes, _ = _resolve_image(image_map, nome)
            if img_bytes and _validate_image_bytes(img_bytes):
                try:
                    story.append(
                        RLImage(ImageReader(io.BytesIO(img_bytes)), width=max_img_width)
                    )
                    story.append(Spacer(1, 4))
                    story.append(Paragraph(_escape_html(f"Imagem: {nome}"), body_style))
                    logger.info("Embutindo imagem PDF: %s", nome)
                except Exception as e:
                    logger.error("Erro embutindo imagem PDF %s: %s", nome, e)
                    story.append(
                        Paragraph(
                            _escape_html(f"[Imagem não encontrada: {nome}]"),
                            error_style,
                        )
                    )
            else:
                story.append(
                    Paragraph(
                        _escape_html(f"[Imagem não encontrada: {nome}]"), error_style
                    )
                )
                logger.warning("Imagem não encontrada PDF: %s", nome)
            story.append(Spacer(1, 6))
            i += 1
            continue

        # ![alt](url) — data URL or image_map
        img_md_match = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if img_md_match:
            alt_text = img_md_match.group(1)
            url = img_md_match.group(2).strip()
            img_bytes = None
            if url.startswith("data:") and "base64," in url:
                try:
                    b64 = url.split("base64,", 1)[1]
                    img_bytes = base64.b64decode(b64)
                except Exception:
                    pass
            if img_bytes is None and image_map and alt_text:
                img_bytes, _ = _resolve_image(image_map, alt_text)
            if img_bytes is None and url and not url.startswith("data:"):
                p = Path(url)
                if p.exists():
                    try:
                        img_bytes = p.read_bytes()
                    except Exception:
                        pass
            if img_bytes and _validate_image_bytes(img_bytes):
                try:
                    story.append(
                        RLImage(ImageReader(io.BytesIO(img_bytes)), width=max_img_width)
                    )
                    story.append(Spacer(1, 4))
                    story.append(
                        Paragraph(
                            _escape_html(f"Imagem: {alt_text or url}"), body_style
                        )
                    )
                    logger.info("Embutindo imagem PDF: %s", alt_text or url)
                except Exception:
                    story.append(
                        Paragraph(
                            _escape_html(f"[Imagem não encontrada: {alt_text or url}]"),
                            error_style,
                        )
                    )
            else:
                story.append(
                    Paragraph(
                        _escape_html(f"[Imagem não encontrada: {alt_text or url}]"),
                        error_style,
                    )
                )
            story.append(Spacer(1, 6))
            i += 1
            continue

        # Checklist or list
        if re.match(r"^[\s]*-\s*\[[\sxX]\]\s*", stripped):
            text = re.sub(r"^[\s]*-\s*\[[\sxX]\]\s*", "☐ ", stripped)
            text = _escape_html(text).replace("\n", "<br/>")
            story.append(Paragraph(text, body_style))
            i += 1
            continue
        if re.match(r"^[\s]*[-*]\s+", stripped):
            text = re.sub(r"^[\s]*[-*]\s+", "• ", stripped, count=1)
            text = _escape_html(text).replace("\n", "<br/>")
            story.append(Paragraph(text, body_style))
            i += 1
            continue
        num_match = re.match(r"^[\s]*(\d+)\.\s+", stripped)
        if num_match:
            text = stripped[num_match.end() :]
            text = _escape_html(text).replace("\n", "<br/>")
            story.append(Paragraph(text, body_style))
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        text = _escape_html(stripped).replace("\n", "<br/>")
        story.append(Paragraph(text, body_style))
        story.append(Spacer(1, 6))
        i += 1

    doc.build(story)
    out.seek(0)
    return out.read()
