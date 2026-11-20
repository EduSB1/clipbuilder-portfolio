"""Templates corporativos sem marca de terceiro e dados de pagamento do próprio cliente.

Antes: os templates IT e POP carregavam nome, descrição, prompts e logo de
uma empresa específica; o DOCX escrevia o nome dela quando o logo faltava; e
o Pix usava um e-mail fixo de um domínio de terceiros quando a conta não
tinha e-mail.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest

from app.services.enhance import build_doc_pro_prompt
from templates.corporate_docx import corporate_markdown_to_docx
from templates.template_registry import CLIPBUILDER_ICON, get_template, list_templates
from tests.conftest import auth_header

CORPORATE_IDS = ("corporate_it", "corporate_pop")


def test_builtin_templates_are_neutral() -> None:
    ids = {t["id"] for t in list_templates()}
    assert ids == {"clipbuilder_pro", *CORPORATE_IDS}
    for template in list_templates():
        # O texto removido identificava a empresa como "... do Brasil".
        assert "Brasil" not in str(template)


def test_builtin_logo_ships_with_the_backend() -> None:
    assert CLIPBUILDER_ICON.is_file()


@pytest.mark.parametrize("template_id", CORPORATE_IDS)
def test_corporate_docx_has_the_logo_and_no_third_party_name(template_id: str) -> None:
    docx = corporate_markdown_to_docx("## Passo 1\n\nAbrir o sistema.", get_template(template_id))
    with zipfile.ZipFile(io.BytesIO(docx)) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())
        text = b"".join(archive.read(n) for n in archive.namelist() if n.endswith(".xml"))
    # Sem logo, o gerador escrevia o nome da empresa ("... do Brasil").
    assert b"Brasil" not in text


@pytest.mark.parametrize("template_id", CORPORATE_IDS)
def test_corporate_prompts_have_no_third_party_name(template_id: str) -> None:
    prompt = build_doc_pro_prompt("Guia", [{"description": "Abrir", "has_image": False}], template_id)
    assert "Padrão Corporativo" in prompt
    assert "Brasil" not in prompt


def test_pix_requires_the_buyer_email(
    client: Any, db: Any, make_user: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.billing import router as billing_router

    calls: list[Any] = []

    class FakeSDK:
        def payment(self) -> Any:
            calls.append("payment")
            raise AssertionError("não deveria chegar ao Mercado Pago")

    monkeypatch.setattr(billing_router, "_get_mp", FakeSDK)
    user = make_user()
    user.email = ""
    db.commit()
    response = client.post("/billing/checkout/pix", json={"package_id": "starter"}, headers=auth_header(user))
    assert response.status_code == 400
    assert calls == []
