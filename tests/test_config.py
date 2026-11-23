"""Testes do Settings.from_env (config.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.config import Settings
from jarvis.errors import ConfigError

ENV_VARS = (
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_MODEL_RESERVA",
    "GEMINI_LIVE_MODEL",
    "JARVIS_VOZ",
    "JARVIS_NOME_USUARIO",
)


@pytest.fixture(autouse=True)
def _limpa_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _env_file(tmp_path: Path, text: str) -> Path:
    arquivo = tmp_path / ".env"
    arquivo.write_text(text, encoding="utf-8")
    return arquivo


def test_sem_chave_da_erro_amigavel(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        Settings.from_env(_env_file(tmp_path, "GEMINI_MODEL=x\n"))


def test_chave_de_exemplo_da_erro(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(_env_file(tmp_path, "GEMINI_API_KEY=cole_sua_chave_aqui\n"))


def test_padroes(tmp_path: Path) -> None:
    settings = Settings.from_env(_env_file(tmp_path, "GEMINI_API_KEY=abc123\n"))
    assert settings.api_key == "abc123"
    assert settings.voice == "Charon"
    assert settings.user_name == ""
    assert "abc123" not in repr(settings)


def test_nome_do_usuario(tmp_path: Path) -> None:
    env = "GEMINI_API_KEY=abc123\nJARVIS_NOME_USUARIO=Carlos\nJARVIS_VOZ=Puck\n"
    settings = Settings.from_env(_env_file(tmp_path, env))
    assert settings.user_name == "Carlos"
    assert settings.voice == "Puck"


def test_nome_vazio_no_env_fica_vazio(tmp_path: Path) -> None:
    settings = Settings.from_env(_env_file(tmp_path, "GEMINI_API_KEY=abc\nJARVIS_NOME_USUARIO=\n"))
    assert settings.user_name == ""
