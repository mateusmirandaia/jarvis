"""Testes da personalidade (persona.py) e da coerencia com a lista fechada de ferramentas."""

from __future__ import annotations

import re
from pathlib import Path

from jarvis.config import Settings
from jarvis.persona import build_system_prompt
from jarvis.tools import ToolRegistry

FOLDERS = {"area de trabalho": Path("/casa/Desktop")}


def test_persona_generica_sem_nome() -> None:
    texto = build_system_prompt(FOLDERS, ["calculadora"])
    assert "seu assistente pessoal" in texto
    assert "assistente pessoal do" not in texto
    assert '"senhor"' in texto


def test_persona_com_nome() -> None:
    texto = build_system_prompt(FOLDERS, ["calculadora"], user_name="  Carlos   Silva ")
    assert "assistente pessoal do Carlos Silva" in texto
    assert '"senhor"' in texto


def test_persona_nome_so_com_espacos_fica_generica() -> None:
    assert "seu assistente pessoal" in build_system_prompt(FOLDERS, [], user_name="   ")


def test_persona_lista_pastas_e_apps() -> None:
    texto = build_system_prompt(FOLDERS, ["calculadora", "paint"])
    assert "area de trabalho:" in texto
    assert "calculadora, paint" in texto


def test_ferramentas_citadas_existem_no_registry(tmp_path: Path) -> None:
    registry = ToolRegistry(
        Settings(api_key="x", project_root=tmp_path), confirm=lambda t, m: False
    )
    texto = build_system_prompt(registry.guard.user_folders(), registry.app_names)
    citadas = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", texto))
    assert citadas, "a persona deveria citar ferramentas pelo nome"
    assert citadas <= set(registry.names)


def test_persona_exige_portugues_do_brasil(tmp_path) -> None:
    from jarvis.persona import build_system_prompt

    prompt = build_system_prompt({"area de trabalho": tmp_path}, ["calculadora"])
    assert "portugues do BRASIL" in prompt
    assert "vosso" in prompt  # citado como proibido
