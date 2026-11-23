"""Testes do FileTools (tools/file_tools.py) em pastas temporarias.

A confirmacao manual e injetada (confirm falso/verdadeiro), entao nenhuma janela abre.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.tools.file_tools import FileTools
from jarvis.tools.security import PathGuard


class ConfirmSpy:
    """Confirmacao falsa que responde sempre a mesma coisa e anota as chamadas."""

    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str]] = []

    def __call__(self, title: str, message: str) -> bool:
        self.calls.append((title, message))
        return self.answer


@pytest.fixture
def desktop(home: Path) -> Path:
    return home / "Desktop"


def make_tools(guard: PathGuard, answer: bool = False) -> tuple[FileTools, ConfirmSpy]:
    spy = ConfirmSpy(answer)
    return FileTools(guard=guard, confirm=spy), spy


def test_tool_names() -> None:
    assert FileTools.TOOL_NAMES == (
        "create_folder",
        "list_folder",
        "find_file",
        "open_file",
        "move_or_rename",
        "copy_item",
        "create_text_file",
        "delete_to_trash",
    )


# ------------------------------------------------------------------ criar pasta
def test_cria_pasta_com_intermediarias(guard: PathGuard, tmp_path: Path) -> None:
    tools, _ = make_tools(guard)
    alvo = tmp_path / "livre" / "a" / "b"
    resultado = tools.create_folder(str(alvo))
    assert isinstance(resultado, str)
    assert alvo.is_dir()


def test_cria_pasta_pelo_atalho(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    tools.create_folder("area de trabalho\\Fotos")
    assert (desktop / "Fotos").is_dir()


def test_criar_pasta_que_ja_existe_nao_quebra(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    (desktop / "Fotos").mkdir()
    (desktop / "Fotos" / "foto.jpg").write_bytes(b"x")
    resultado = tools.create_folder(str(desktop / "Fotos"))
    assert isinstance(resultado, str)
    assert (desktop / "Fotos" / "foto.jpg").exists()


def test_recusa_criar_pasta_protegida(guard: PathGuard, project_root: Path) -> None:
    tools, _ = make_tools(guard)
    alvo = project_root / "invasao"
    tools.create_folder(str(alvo))
    assert not alvo.exists()


# ------------------------------------------------------------------ listar / localizar
def test_lista_pasta(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    (desktop / "relatorio.txt").write_text("x", encoding="utf-8")
    (desktop / "Projetos").mkdir()
    resultado = tools.list_folder("area de trabalho")
    assert "relatorio.txt" in resultado
    assert "Projetos" in resultado


def test_localiza_arquivo_ignorando_acento(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    (desktop / "sub").mkdir()
    (desktop / "sub" / "Relatório Vendas.docx").write_bytes(b"x")
    resultado = tools.find_file("relatorio vendas", onde="area de trabalho")
    assert "Relatório Vendas.docx" in resultado


# ------------------------------------------------------------------ arquivo de texto
def test_cria_arquivo_de_texto(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    tools.create_text_file(str(desktop / "lista.txt"), "arroz, feijao")
    assert (desktop / "lista.txt").read_text(encoding="utf-8") == "arroz, feijao"


def test_arquivo_de_texto_sempre_txt_ou_md(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    tools.create_text_file(str(desktop / "script.bat"), "del *.*")
    assert not (desktop / "script.bat").exists()
    assert (desktop / "script.txt").exists()


def test_arquivo_de_texto_nao_sobrescreve(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    alvo = desktop / "notas.txt"
    alvo.write_text("original", encoding="utf-8")
    tools.create_text_file(str(alvo), "novo")
    assert alvo.read_text(encoding="utf-8") == "original"


def test_recusa_arquivo_de_texto_protegido(guard: PathGuard, project_root: Path) -> None:
    tools, _ = make_tools(guard)
    tools.create_text_file(str(project_root / "x.txt"), "oi")
    assert not (project_root / "x.txt").exists()


# ------------------------------------------------------------------ mover / copiar
def test_move_arquivo(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    origem = desktop / "foto.jpg"
    origem.write_bytes(b"img")
    destino = desktop / "Fotos"
    destino.mkdir()
    tools.move_or_rename(str(origem), str(destino))
    assert not origem.exists()
    assert (destino / "foto.jpg").read_bytes() == b"img"


def test_renomeia_arquivo(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    origem = desktop / "velho.txt"
    origem.write_text("x", encoding="utf-8")
    tools.move_or_rename(str(origem), str(desktop / "novo.txt"))
    assert not origem.exists()
    assert (desktop / "novo.txt").exists()


def test_mover_nao_sobrescreve(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    origem = desktop / "a.txt"
    origem.write_text("A", encoding="utf-8")
    destino = desktop / "b.txt"
    destino.write_text("B", encoding="utf-8")
    tools.move_or_rename(str(origem), str(destino))
    assert origem.read_text(encoding="utf-8") == "A"
    assert destino.read_text(encoding="utf-8") == "B"


def test_recusa_mover_para_protegido(guard: PathGuard, desktop: Path, project_root: Path) -> None:
    tools, _ = make_tools(guard)
    origem = desktop / "a.txt"
    origem.write_text("A", encoding="utf-8")
    tools.move_or_rename(str(origem), str(project_root))
    assert origem.exists()
    assert not (project_root / "a.txt").exists()


def test_recusa_mover_de_protegido(guard: PathGuard, desktop: Path, project_root: Path) -> None:
    tools, _ = make_tools(guard)
    tools.move_or_rename(str(project_root / ".env"), str(desktop))
    assert (project_root / ".env").exists()
    assert not (desktop / ".env").exists()


def test_copia_arquivo(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    origem = desktop / "a.txt"
    origem.write_text("A", encoding="utf-8")
    tools.copy_item(str(origem), str(desktop / "c.txt"))
    assert origem.read_text(encoding="utf-8") == "A"
    assert (desktop / "c.txt").read_text(encoding="utf-8") == "A"


def test_copia_pasta(guard: PathGuard, desktop: Path, home: Path) -> None:
    tools, _ = make_tools(guard)
    pasta = desktop / "Projeto"
    pasta.mkdir()
    (pasta / "x.txt").write_text("x", encoding="utf-8")
    tools.copy_item(str(pasta), str(home / "Documents"))
    assert (home / "Documents" / "Projeto" / "x.txt").exists()
    assert (pasta / "x.txt").exists()


def test_copiar_nao_sobrescreve(guard: PathGuard, desktop: Path) -> None:
    tools, _ = make_tools(guard)
    (desktop / "a.txt").write_text("A", encoding="utf-8")
    (desktop / "b.txt").write_text("B", encoding="utf-8")
    tools.copy_item(str(desktop / "a.txt"), str(desktop / "b.txt"))
    assert (desktop / "b.txt").read_text(encoding="utf-8") == "B"


def test_recusa_copiar_para_protegido(guard: PathGuard, desktop: Path, project_root: Path) -> None:
    tools, _ = make_tools(guard)
    (desktop / "a.txt").write_text("A", encoding="utf-8")
    tools.copy_item(str(desktop / "a.txt"), str(project_root))
    assert not (project_root / "a.txt").exists()


# ------------------------------------------------------------------ abrir
def test_nao_abre_executavel(guard: PathGuard, desktop: Path, monkeypatch, as_windows) -> None:
    import jarvis.os_integration.windows as windows

    chamadas: list[object] = []
    monkeypatch.setattr(windows, "open_with_shell", lambda alvo: chamadas.append(alvo))
    exe = desktop / "virus.exe"
    exe.write_bytes(b"MZ")
    resultado = FileTools(guard=guard, confirm=ConfirmSpy(True)).open_file(str(exe))
    assert isinstance(resultado, str)
    assert chamadas == []


# ------------------------------------------------------------------ apagar (Lixeira)
def test_apagar_sem_confirmacao_nao_apaga(
    guard: PathGuard, desktop: Path, fake_trash: list[str], as_windows: None
) -> None:
    tools, spy = make_tools(guard, answer=False)
    alvo = desktop / "rascunho.txt"
    alvo.write_text("x", encoding="utf-8")
    tools.delete_to_trash(str(alvo))
    assert alvo.exists()
    assert fake_trash == []
    assert len(spy.calls) == 1


def test_apagar_com_confirmacao_vai_para_lixeira(
    guard: PathGuard, desktop: Path, fake_trash: list[str], as_windows: None
) -> None:
    tools, spy = make_tools(guard, answer=True)
    alvo = desktop / "rascunho.txt"
    alvo.write_text("x", encoding="utf-8")
    resultado = tools.delete_to_trash(str(alvo))
    assert isinstance(resultado, str)
    assert len(spy.calls) == 1
    assert fake_trash == [str(alvo)]
    assert not alvo.exists()


def test_apagar_protegido_nem_pergunta(
    guard: PathGuard, project_root: Path, fake_trash: list[str], as_windows: None
) -> None:
    tools, spy = make_tools(guard, answer=True)
    tools.delete_to_trash(str(project_root / ".env"))
    assert (project_root / ".env").exists()
    assert spy.calls == []
    assert fake_trash == []


def test_apagar_inexistente_nem_pergunta(
    guard: PathGuard, desktop: Path, fake_trash: list[str], as_windows: None
) -> None:
    tools, spy = make_tools(guard, answer=True)
    resultado = tools.delete_to_trash(str(desktop / "nao_existe.txt"))
    assert isinstance(resultado, str)
    assert spy.calls == []
    assert fake_trash == []


def test_apagar_com_janela_real_passa_o_prazo(
    guard: PathGuard,
    desktop: Path,
    fake_trash: list[str],
    as_windows: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import jarvis.os_integration.windows as windows

    chamadas: list[float | None] = []

    def janela_falsa(title: str, message: str, timeout_s: float | None = None) -> bool:
        chamadas.append(timeout_s)
        return False  # o tempo acabou / clicou em "Nao"

    monkeypatch.setattr(windows, "confirm_dialog", janela_falsa)
    alvo = desktop / "rascunho.txt"
    alvo.write_text("x", encoding="utf-8")
    resultado = FileTools(guard=guard, confirm_timeout_s=50).delete_to_trash(str(alvo))
    assert chamadas == [50]
    assert "Nada foi apagado" in resultado
    assert alvo.exists()
    assert fake_trash == []


def test_apagar_fora_do_windows_sem_confirm_injetado_recusa(
    guard: PathGuard, desktop: Path, fake_trash: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import jarvis.os_integration.windows as windows

    monkeypatch.setattr(windows, "IS_WINDOWS", False)
    alvo = desktop / "rascunho.txt"
    alvo.write_text("x", encoding="utf-8")
    resultado = FileTools(guard=guard).delete_to_trash(str(alvo))
    assert "Windows" in resultado
    assert alvo.exists()
    assert fake_trash == []
