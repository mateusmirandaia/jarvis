"""Configuracao comum dos testes.

Os testes rodam em qualquer sistema (inclusive Linux), SEM internet e SEM pyaudio:
- coloca a pasta src/ no sys.path (funciona mesmo sem `pip install -e .`);
- se a biblioteca send2trash nao estiver instalada, usa um modulo falso;
- oferece fixtures para simular a Lixeira e o Windows.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:  # pragma: no cover - depende do ambiente
    import send2trash as _send2trash  # noqa: F401
except ImportError:  # pragma: no cover
    _fake = types.ModuleType("send2trash")

    def _fake_send2trash(path: str) -> None:
        raise RuntimeError("send2trash falso: use a fixture fake_trash nos testes")

    _fake.send2trash = _fake_send2trash  # type: ignore[attr-defined]
    sys.modules["send2trash"] = _fake


@pytest.fixture(autouse=True)
def _pasta_do_usuario_isolada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nenhum teste le ou grava a pasta real do usuario (preferencias.json, .env, logs).

    HOME/APPDATA apontam para uma pasta temporaria; as variaveis do Jarvis do ambiente real
    sao removidas para os testes nao dependerem da maquina.
    """
    falso = tmp_path / "_usuario"
    monkeypatch.setenv("HOME", str(falso))
    monkeypatch.setenv("USERPROFILE", str(falso))
    monkeypatch.setenv("APPDATA", str(falso / "AppData" / "Roaming"))
    for nome in (
        "GEMINI_API_KEY",
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_VOICE_ID",
        "ELEVENLABS_MODEL",
        "JARVIS_VOZ",
        "JARVIS_NOME_USUARIO",
        "JARVIS_FONE",
        "JARVIS_VISUAL",
    ):
        monkeypatch.delenv(nome, raising=False)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """Home falso com as pastas Desktop, Documents e Downloads."""
    casa = tmp_path / "home"
    for nome in ("Desktop", "Documents", "Downloads"):
        (casa / nome).mkdir(parents=True)
    return casa


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Pasta falsa do projeto Jarvis (deve ser protegida)."""
    raiz = tmp_path / "projeto_jarvis"
    raiz.mkdir()
    (raiz / ".env").write_text("GEMINI_API_KEY=segredo", encoding="utf-8")
    return raiz


@pytest.fixture
def guard(project_root: Path, home: Path):
    from jarvis.tools.security import PathGuard

    return PathGuard(project_root=project_root, home=home)


@pytest.fixture
def fake_trash(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Substitui o send2trash: registra o caminho e remove o item (como se fosse a Lixeira)."""
    import shutil

    sent: list[str] = []

    def _trash(path: str) -> None:
        sent.append(str(path))
        p = Path(path)
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()

    fake_module = types.ModuleType("send2trash")
    fake_module.send2trash = _trash  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "send2trash", fake_module)

    import jarvis.tools.file_tools as file_tools

    if hasattr(file_tools, "send2trash"):
        monkeypatch.setattr(file_tools, "send2trash", _trash)
    yield sent


@pytest.fixture
def as_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Faz o codigo achar que esta no Windows (sem chamar nenhuma API real do Windows)."""
    import jarvis.os_integration.windows as windows
    import jarvis.tools.file_tools as file_tools

    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    if hasattr(file_tools, "IS_WINDOWS"):
        monkeypatch.setattr(file_tools, "IS_WINDOWS", True)
