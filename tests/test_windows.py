"""Testes da janela de confirmacao (os_integration/windows.py) com um user32 falso."""

from __future__ import annotations

import ctypes
from collections.abc import Callable

import pytest

import jarvis.os_integration.windows as windows


class FakeApi:
    """Imita uma funcao do ctypes: aceita argtypes/restype e anota as chamadas."""

    def __init__(self, name: str, answer: int, calls: list[tuple[str, tuple[object, ...]]]):
        self.name, self.answer, self.calls = name, answer, calls
        self.argtypes: tuple[object, ...] = ()
        self.restype: object = None

    def __call__(self, *args: object) -> int:
        self.calls.append((self.name, args))
        return self.answer


class FakeUser32:
    """Imita o user32 com MessageBoxW e (opcional) MessageBoxTimeoutW."""

    def __init__(self, answer: int, with_timeout_api: bool) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.MessageBoxW = FakeApi("MessageBoxW", answer, self.calls)
        if with_timeout_api:
            self.MessageBoxTimeoutW = FakeApi("MessageBoxTimeoutW", answer, self.calls)


@pytest.fixture
def fake_user32(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeUser32]:
    """Instala um user32 falso e faz o modulo achar que esta no Windows."""

    def install(answer: int, with_timeout_api: bool = True) -> FakeUser32:
        user32 = FakeUser32(answer, with_timeout_api)
        fake_windll = type("FakeWindll", (), {"user32": user32})()
        monkeypatch.setattr(ctypes, "windll", fake_windll, raising=False)
        monkeypatch.setattr(windows, "IS_WINDOWS", True)
        return user32

    return install


def test_fora_do_windows_nega(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows, "IS_WINDOWS", False)
    assert windows.confirm_dialog("t", "m") is False
    assert windows.confirm_dialog("t", "m", timeout_s=5) is False


def test_sem_prazo_usa_messagebox_normal(fake_user32: Callable[..., FakeUser32]) -> None:
    user32 = fake_user32(answer=6)
    assert windows.confirm_dialog("t", "m") is True
    assert [name for name, _ in user32.calls] == ["MessageBoxW"]


def test_com_prazo_usa_messagebox_timeout(fake_user32: Callable[..., FakeUser32]) -> None:
    user32 = fake_user32(answer=6)
    assert windows.confirm_dialog("titulo", "pergunta", timeout_s=110) is True
    name, args = user32.calls[0]
    assert name == "MessageBoxTimeoutW"
    assert args[1:3] == ("pergunta", "titulo")
    assert args[4] == 0  # wLanguageId
    assert args[5] == 110_000  # milissegundos
    assert len(user32.MessageBoxTimeoutW.argtypes) == 6


def test_tempo_esgotado_conta_como_nao(fake_user32: Callable[..., FakeUser32]) -> None:
    fake_user32(answer=32000)
    assert windows.confirm_dialog("t", "m", timeout_s=1) is False


def test_clique_em_nao(fake_user32: Callable[..., FakeUser32]) -> None:
    fake_user32(answer=7)
    assert windows.confirm_dialog("t", "m", timeout_s=1) is False


def test_sem_api_de_prazo_nega_sem_abrir_janela(fake_user32: Callable[..., FakeUser32]) -> None:
    user32 = fake_user32(answer=6, with_timeout_api=False)
    assert windows.confirm_dialog("t", "m", timeout_s=5) is False
    assert user32.calls == []
