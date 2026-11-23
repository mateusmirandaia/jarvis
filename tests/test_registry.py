"""Testes do ToolRegistry (tools/__init__.py): a LISTA FECHADA de ferramentas."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from jarvis.config import Settings
from jarvis.tools import ToolRegistry, confirm_timeout_for
from jarvis.tools.security import PathGuard

EXPECTED_NAMES = [
    # system
    "current_time",
    # apps
    "list_open_apps",
    "open_app",
    "close_app",
    # web
    "open_website",
    "web_search",
    # files
    "create_folder",
    "list_folder",
    "find_file",
    "open_file",
    "move_or_rename",
    "copy_item",
    "create_text_file",
    "delete_to_trash",
]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(api_key="x", project_root=tmp_path)


@pytest.fixture
def registry(settings: Settings) -> ToolRegistry:
    return ToolRegistry(settings, confirm=lambda title, message: False)


def test_nomes_esperados_na_ordem(registry: ToolRegistry) -> None:
    assert registry.names == EXPECTED_NAMES


def test_functions_batem_com_os_nomes(registry: ToolRegistry) -> None:
    funcs = registry.functions
    assert [f.__name__ for f in funcs] == EXPECTED_NAMES
    assert all(callable(f) for f in funcs)


def test_ferramentas_tem_docstring_e_assinatura(registry: ToolRegistry) -> None:
    for func in registry.functions:
        assert func.__doc__ and func.__doc__.strip(), func.__name__
        params = inspect.signature(func).parameters
        assert "self" not in params, func.__name__


def test_parametros_em_portugues(registry: ToolRegistry) -> None:
    assert list(inspect.signature(registry.get("open_app")).parameters) == ["nome"]
    assert list(inspect.signature(registry.get("close_app")).parameters) == ["nome", "forcar"]
    assert list(inspect.signature(registry.get("move_or_rename")).parameters) == [
        "origem",
        "destino",
    ]


def test_get_nome_valido(registry: ToolRegistry) -> None:
    func = registry.get("current_time")
    assert func is not None
    assert isinstance(func(), str)


@pytest.mark.parametrize("nome", ["rm_rf", "run_command", "", "CURRENT_TIME", "__init__"])
def test_get_nome_invalido_retorna_none(registry: ToolRegistry, nome: str) -> None:
    assert registry.get(nome) is None


def test_ferramentas_embrulhadas_nunca_levantam(registry: ToolRegistry) -> None:
    resultado = registry.get("list_folder")("/caminho/que/nao/existe/mesmo")
    assert isinstance(resultado, str)


def test_timeout_for(registry: ToolRegistry, settings: Settings) -> None:
    assert registry.timeout_for("delete_to_trash", settings) == settings.delete_timeout_s
    assert registry.timeout_for("current_time", settings) == settings.tool_timeout_s
    assert registry.timeout_for("open_app", settings) == settings.tool_timeout_s


def test_guard_protege_project_root(registry: ToolRegistry, settings: Settings) -> None:
    assert isinstance(registry.guard, PathGuard)
    assert registry.guard.is_protected(settings.project_root)


def test_app_names(registry: ToolRegistry) -> None:
    nomes = registry.app_names
    assert isinstance(nomes, list)
    assert "calculadora" in nomes


@pytest.mark.parametrize("total", [120.0, 30.0, 12.0, 5.0])
def test_janela_fecha_antes_do_limite_da_ferramenta(tmp_path: Path, total: float) -> None:
    settings = Settings(api_key="x", project_root=tmp_path, delete_timeout_s=total)
    prazo = confirm_timeout_for(settings)
    assert 0 < prazo < total


def test_prazo_padrao_da_janela(settings: Settings) -> None:
    assert confirm_timeout_for(settings) == settings.delete_timeout_s - 10


def test_registry_sem_confirm_usa_janela_com_prazo(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import jarvis.os_integration.windows as windows

    chamadas: list[float | None] = []

    def janela_falsa(title: str, message: str, timeout_s: float | None = None) -> bool:
        chamadas.append(timeout_s)
        return False

    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "confirm_dialog", janela_falsa)
    alvo = tmp_path.parent / f"{tmp_path.name}_livre" / "a.txt"
    alvo.parent.mkdir()
    alvo.write_text("x", encoding="utf-8")
    resultado = ToolRegistry(settings).get("delete_to_trash")(str(alvo))
    assert chamadas == [confirm_timeout_for(settings)]
    assert alvo.exists()
    assert "Nada foi apagado" in resultado
