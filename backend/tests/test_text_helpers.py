"""Testes das funções puras de main.py usadas na montagem de nomes e timestamps."""

from __future__ import annotations

import pytest

import main


class TestSafeFilename:
    def test_removes_path_separators(self) -> None:
        # Nome de arquivo vem do título digitado pelo usuário: precisa ser inerte.
        assert "/" not in main._safe_filename("relatorio/2026")
        assert "\\" not in main._safe_filename("relatorio\\2026")

    def test_does_not_allow_directory_traversal(self) -> None:
        assert main._safe_filename("../../etc/passwd").strip(".") not in ("", "/")
        assert "/" not in main._safe_filename("../../etc/passwd")

    def test_falls_back_when_title_is_empty(self) -> None:
        assert main._safe_filename("", fallback="documento") == "documento"
        assert main._safe_filename("   ", fallback="documento") == "documento"

    def test_keeps_readable_accented_title(self) -> None:
        assert main._safe_filename("Manual de Instalação")


class TestTimestamp:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [(0, "00:00:00"), (61, "00:01:01"), (3661, "01:01:01")],
    )
    def test_format(self, seconds: float, expected: str) -> None:
        assert main._format_timestamp(seconds) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("00:00:00", 0), ("00:01:01", 61), ("01:01:01", 3661)],
    )
    def test_parse(self, value: str, expected: float) -> None:
        assert main._parse_timestamp_to_seconds(value) == expected

    def test_roundtrip(self) -> None:
        assert main._parse_timestamp_to_seconds(main._format_timestamp(7325)) == 7325

    def test_rejects_garbage(self) -> None:
        with pytest.raises(ValueError):
            main._parse_timestamp_to_seconds("ontem à tarde")


class TestYoutubeUrlValidation:
    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
        ],
    )
    def test_accepts_youtube(self, url: str) -> None:
        assert main._is_supported_youtube_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.com/watch?v=x",
            "file:///etc/passwd",
            "http://127.0.0.1:8000/videos",
            "not a url",
            "",
        ],
    )
    def test_rejects_everything_else(self, url: str) -> None:
        # O valor vai parar numa linha de comando do yt-dlp: só domínios
        # conhecidos podem passar.
        assert not main._is_supported_youtube_url(url)


class TestMaskKey:
    def test_does_not_leak_the_secret(self) -> None:
        secret = "AIzaSyD-ExemploDeChaveSecreta1234567890"
        masked = main._mask_key(secret)
        assert secret not in masked
        assert len(masked) < len(secret) or "*" in masked or "…" in masked

    def test_handles_empty(self) -> None:
        assert main._mask_key("") is not None
