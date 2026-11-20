"""Leitura das configurações a partir das variáveis de ambiente."""

from __future__ import annotations

import pytest

from app.core.config import Settings


class TestAllowedOrigins:
    # O .env.example usa lista separada por vírgula. Antes do NoDecode, o
    # pydantic-settings tentava ler o valor como JSON e o backend não subia.
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("http://a.com,http://b.com", ["http://a.com", "http://b.com"]),
            ('["http://a.com", "http://b.com"]', ["http://a.com", "http://b.com"]),
            (" http://a.com , ", ["http://a.com"]),
        ],
    )
    def test_accepts_csv_and_json(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, expected: list[str]
    ) -> None:
        monkeypatch.setenv("ALLOWED_ORIGINS", raw)
        assert Settings().allowed_origins == expected

    def test_empty_value_falls_back_to_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOWED_ORIGINS", "")
        assert Settings().allowed_origins
