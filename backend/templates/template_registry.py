"""
Template Registry – defines available document templates for ClipBuilder.

Each template is a dict with metadata (id, name, description, thumbnail hint,
structure sections) that the frontend can display and the export engine can
use to build the final DOCX/PDF.

Two corporate templates based on Wolbito do Brasil standards:
  1. IT  – Instrução de Trabalho (concise, step-by-step with screenshots)
  2. POP – Procedimento Operacional Padrão (full formal document)

Plus the original "pro" template already shipped with ClipBuilder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).resolve().parent
# Pasta centralizada de ícones/logos (ClipBuilder/Icons/)
_ICONS_DIR = Path(__file__).resolve().parent.parent.parent / "Icons"

WOLBITO_LOGO_BLUE = _ICONS_DIR / "wolbito_logo_blue.png"
WOLBITO_LOGO_WHITE = _ICONS_DIR / "wolbito_logo_white.png"
CLIPBUILDER_ICON = _ICONS_DIR / "clipbuilder_icon.png"


# ---------------------------------------------------------------------------
# Template dataclass
# ---------------------------------------------------------------------------


@dataclass
class DocumentTemplate:
    """Describes a document template that users can pick from the UI."""

    id: str
    name: str
    short_name: str  # for UI badges / chips
    description: str
    icon: str  # emoji or icon key for the frontend
    category: str  # "corporate" | "general"

    # Whether this template adds a logo in the header
    has_logo: bool = False
    logo_path: str | None = None

    # Header metadata fields expected by this template
    header_fields: list[str] = field(default_factory=list)

    # Ordered list of section keys that the template produces
    sections: list[str] = field(default_factory=list)

    # Footer info
    footer_fields: list[str] = field(default_factory=list)

    # Extra config hints (font, colours, page size, …)
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the /templates API endpoint."""
        return {
            "id": self.id,
            "name": self.name,
            "short_name": self.short_name,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "has_logo": self.has_logo,
            "header_fields": self.header_fields,
            "sections": self.sections,
            "footer_fields": self.footer_fields,
        }


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

TEMPLATE_CLIPBUILDER_PRO = DocumentTemplate(
    id="clipbuilder_pro",
    name="ClipBuilder Pro",
    short_name="Pro",
    description=(
        "Template padrão do ClipBuilder com capa, sumário, títulos coloridos, "
        "callouts e rodapé com numeração de páginas."
    ),
    icon="✨",
    category="general",
    has_logo=True,
    logo_path=str(CLIPBUILDER_ICON),
    header_fields=[],
    sections=[
        "cover",
        "toc",
        "content",
    ],
    footer_fields=["page_number"],
    config={
        "page_size": "letter",
        "font": "Arial",
        "heading1_color": "1F4E79",
        "heading2_color": "2E75B6",
        "heading3_color": "5B9BD5",
    },
)

TEMPLATE_WOLBITO_IT = DocumentTemplate(
    id="wolbito_it",
    name="Wolbito – Instrução de Trabalho (IT)",
    short_name="IT",
    description=(
        "Instrução de Trabalho padrão Wolbito do Brasil. "
        "Formato conciso com cabeçalho corporativo (logo, código, revisão), "
        "seções de Introdução e Procedimento com capturas de tela, "
        "e rodapé de responsáveis."
    ),
    icon="📋",
    category="corporate",
    has_logo=True,
    logo_path=str(WOLBITO_LOGO_BLUE),
    header_fields=[
        "document_code",
        "revision",
        "expiration_period",
        "elaboration_date",
    ],
    sections=[
        "header_table",
        "introduction",
        "procedure",
        "procedure_requirements",
        "procedure_steps",
        "annexes",
        "reference_documents",
        "records",
    ],
    footer_fields=[
        "responsible_elaboration",
        "responsible_consensus",
        "responsible_approval",
    ],
    config={
        "page_size": "a4",
        "font": "Arial",
        "font_size": 11,
        "heading_font_size": 14,
        "heading_color": "1F4E79",
        "header_bg_color": "1F4E79",
        "header_text_color": "FFFFFF",
        "table_border_color": "1F4E79",
        "section_numbering": True,
        "logo_width_cm": 2.5,
        "logo_height_cm": 2.5,
        # Default metadata values (user can override)
        "defaults": {
            "document_code": "IT-XX-XXX-0000",
            "revision": "00",
            "expiration_period": "1 ano",
            "elaboration_date": "",
            "responsible_elaboration": "",
            "responsible_consensus": "",
            "responsible_approval": "",
        },
    },
)

TEMPLATE_WOLBITO_POP = DocumentTemplate(
    id="wolbito_pop",
    name="Wolbito – Procedimento Operacional Padrão (POP)",
    short_name="POP",
    description=(
        "Procedimento Operacional Padrão completo da Wolbito do Brasil. "
        "Inclui Introdução, Objetivo, Abrangência, Referências, Definições, "
        "Símbolos e Abreviaturas, Responsabilidades, Metodologia, "
        "Desvios e Ações, e Documentos Relacionados. "
        "Cabeçalho corporativo com logo e rodapé de responsáveis."
    ),
    icon="📑",
    category="corporate",
    has_logo=True,
    logo_path=str(WOLBITO_LOGO_BLUE),
    header_fields=[
        "document_code",
        "revision",
        "expiration_period",
        "elaboration_date",
    ],
    sections=[
        "header_table",
        "introduction",
        "objective",
        "scope",
        "references",
        "definitions",
        "symbols_abbreviations",
        "responsibilities",
        "methodology",
        "procedure_steps",
        "deviations_and_actions",
        "related_documents_and_annexes",
    ],
    footer_fields=[
        "responsible_elaboration",
        "responsible_consensus",
        "responsible_approval",
    ],
    config={
        "page_size": "a4",
        "font": "Arial",
        "font_size": 11,
        "heading_font_size": 14,
        "heading_color": "1F4E79",
        "header_bg_color": "1F4E79",
        "header_text_color": "FFFFFF",
        "table_border_color": "1F4E79",
        "section_numbering": True,
        "logo_width_cm": 2.5,
        "logo_height_cm": 2.5,
        "defaults": {
            "document_code": "POP-XX-XXX-0000",
            "revision": "00",
            "expiration_period": "1 ano",
            "elaboration_date": "",
            "responsible_elaboration": "",
            "responsible_consensus": "",
            "responsible_approval": "",
        },
    },
)

# ---------------------------------------------------------------------------
# Registry (ordered – first is default)
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, DocumentTemplate] = {
    TEMPLATE_CLIPBUILDER_PRO.id: TEMPLATE_CLIPBUILDER_PRO,
    TEMPLATE_WOLBITO_IT.id: TEMPLATE_WOLBITO_IT,
    TEMPLATE_WOLBITO_POP.id: TEMPLATE_WOLBITO_POP,
}

DEFAULT_TEMPLATE_ID = TEMPLATE_CLIPBUILDER_PRO.id


def list_templates() -> list[dict[str, Any]]:
    """Return all registered templates as serialisable dicts."""
    return [t.to_dict() for t in _TEMPLATES.values()]


def get_template(template_id: str) -> DocumentTemplate | None:
    """Return a template by id, or None if not found."""
    return _TEMPLATES.get(template_id)


def get_template_or_default(template_id: str | None) -> DocumentTemplate:
    """Return the requested template, falling back to the default."""
    if template_id and template_id in _TEMPLATES:
        return _TEMPLATES[template_id]
    return _TEMPLATES[DEFAULT_TEMPLATE_ID]


def register_template(template: DocumentTemplate) -> None:
    """Register a custom template at runtime (for future extensibility)."""
    _TEMPLATES[template.id] = template
