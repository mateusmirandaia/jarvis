"""Chamadas nativas do Windows (ctypes) isoladas num unico modulo.

Tudo que depende de ``ctypes.windll`` fica dentro das funcoes, para que o modulo
importe normalmente no Linux/macOS (onde os testes rodam). Fora do Windows as
funcoes devolvem valores neutros ou levantam ``NotImplementedError``.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import platform
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

IS_WINDOWS: bool = platform.system() == "Windows"

# Constantes da API Win32.
_GW_OWNER = 4
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x80
_DWMWA_CLOAKED = 14
_WM_CLOSE = 0x0010
_MB_YESNO = 0x4
_MB_ICONWARNING = 0x30
_MB_SETFOREGROUND = 0x10000
_MB_TOPMOST = 0x40000
_IDYES = 6
_IDNO = 7
_MB_TIMEDOUT = 32000  # resposta de MessageBoxTimeoutW quando o tempo acaba


@dataclass(frozen=True)
class Window:
    """Uma janela "de verdade" (das que aparecem no Alt+Tab)."""

    process: str
    title: str
    hwnd: int


def _process_names_by_pid() -> dict[int, str]:
    """Mapeia pid -> nome do processo com uma unica chamada ao ``tasklist``."""
    output = subprocess.run(
        ["tasklist", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        encoding="cp850",
        errors="ignore",
        check=False,
    ).stdout
    return {
        int(row[1]): row[0]
        for row in csv.reader(io.StringIO(output))
        if len(row) > 1 and row[1].isdigit()
    }


def list_windows(excluded_processes: Iterable[str] = ()) -> list[Window]:
    """Lista as janelas visiveis do Alt+Tab, ignorando os processos excluidos.

    Criterios (os mesmos do Alt+Tab): visivel, sem janela dona, nao e janela de
    ferramenta, nao esta "camuflada" (apps UWP escondidos) e tem titulo.

    Args:
        excluded_processes: nomes de processo (ex.: "explorer.exe") que nao entram na lista.

    Returns:
        Lista de ``Window``; vazia fora do Windows.
    """
    if not IS_WINDOWS:
        return []
    import ctypes
    from ctypes import wintypes

    excluded = {name.lower() for name in excluded_processes}
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    dwmapi = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    names = _process_names_by_pid()
    windows: list[Window] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)  # type: ignore[attr-defined]
    def visit(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, _GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, _GWL_EXSTYLE) & _WS_EX_TOOLWINDOW:
            return True
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(
            hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
        )
        if cloaked.value:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process = names.get(pid.value, "?")
        if process.lower() not in excluded and buffer.value != "Program Manager":
            windows.append(Window(process=process, title=buffer.value, hwnd=int(hwnd)))
        return True

    user32.EnumWindows(visit, 0)
    logger.debug("list_windows encontrou %d janelas", len(windows))
    return windows


def close_window(hwnd: int) -> None:
    """Pede para a janela fechar (equivale a clicar no X; o app pode perguntar se quer salvar).

    Args:
        hwnd: identificador da janela.
    """
    if not IS_WINDOWS:
        raise NotImplementedError("close_window so funciona no Windows")
    import ctypes

    ctypes.windll.user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)  # type: ignore[attr-defined]
    logger.info("WM_CLOSE enviado para hwnd=%s", hwnd)


def kill_process(image_name: str) -> bool:
    """Encerra a forca todos os processos com esse nome (``taskkill /IM x /F``).

    Args:
        image_name: nome do executavel, ex.: "notepad.exe".

    Returns:
        True se o taskkill terminou com sucesso; False fora do Windows ou em falha.
    """
    if not IS_WINDOWS:
        return False
    result = subprocess.run(["taskkill", "/IM", image_name, "/F"], capture_output=True, check=False)
    logger.info("taskkill /F %s -> codigo %s", image_name, result.returncode)
    return result.returncode == 0


def confirm_dialog(title: str, message: str, timeout_s: float | None = None) -> bool:
    """Abre uma janela Sim/Nao no topo da tela: SO o clique humano em "Sim" autoriza.

    Com ``timeout_s``, a janela se fecha sozinha depois desse tempo e isso conta como
    "Nao". Assim um clique atrasado nunca apaga nada depois que o Jarvis ja desistiu.

    Args:
        title: titulo da janela.
        message: texto da pergunta.
        timeout_s: segundos ate a janela fechar sozinha; None espera para sempre.

    Returns:
        True somente se o usuario clicou em "Sim" a tempo; False fora do Windows.
    """
    if not IS_WINDOWS:
        logger.warning("confirm_dialog chamado fora do Windows; negando por seguranca")
        return False
    import ctypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    style = _MB_YESNO | _MB_ICONWARNING | _MB_TOPMOST | _MB_SETFOREGROUND
    if timeout_s is None:
        answer = user32.MessageBoxW(0, message, title, style)
    else:
        answer = _message_box_with_timeout(user32, title, message, style, timeout_s)
    logger.info("confirm_dialog '%s' -> resposta %s", title, answer)
    if answer == _MB_TIMEDOUT:
        logger.info("confirm_dialog '%s': tempo esgotado, tratado como Nao", title)
    return answer == _IDYES


def _message_box_with_timeout(
    user32: object, title: str, message: str, style: int, timeout_s: float
) -> int:
    """Chama ``MessageBoxTimeoutW`` (fecha sozinha apos o tempo e devolve 32000).

    Se a funcao nao existir nesta versao do Windows, devolve "Nao" (mais seguro do que
    abrir uma janela sem prazo, que poderia apagar depois que o Jarvis desistiu).
    """
    import ctypes
    from ctypes import wintypes

    func = getattr(user32, "MessageBoxTimeoutW", None)
    if func is None:
        logger.error("MessageBoxTimeoutW indisponivel; negando por seguranca")
        return _IDNO
    func.argtypes = (
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.UINT,
        wintypes.WORD,
        wintypes.DWORD,
    )
    func.restype = ctypes.c_int
    milliseconds = max(1, int(timeout_s * 1000))
    return int(func(None, message, title, style, 0, milliseconds))


def show_message(title: str, message: str) -> None:
    """Mostra um aviso simples (botao OK). Usado quando nao ha terminal (atalho/pythonw).

    Args:
        title: titulo da janela.
        message: texto do aviso.
    """
    if not IS_WINDOWS:
        return
    import ctypes

    _mb_ok, _mb_iconinformation = 0x0, 0x40
    ctypes.windll.user32.MessageBoxW(
        0, message, title, _mb_ok | _mb_iconinformation | _MB_TOPMOST | _MB_SETFOREGROUND
    )


_single_instance_handle: int | None = None  # mantido vivo enquanto o programa roda


def acquire_single_instance(name: str) -> bool:
    """Garante uma unica janela do Jarvis aberta (mutex nomeado do Windows).

    Args:
        name: nome unico do mutex.

    Returns:
        True se esta e a primeira instancia (ou fora do Windows); False se ja ha outra aberta.
    """
    global _single_instance_handle
    if not IS_WINDOWS:
        return True
    import ctypes

    error_already_exists = 183
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, name)
    if kernel32.GetLastError() == error_already_exists:
        kernel32.CloseHandle(handle)
        return False
    _single_instance_handle = handle
    return True


def open_with_shell(target: str | Path) -> None:
    """Abre um arquivo, pasta, programa ou protocolo com o shell do Windows (``os.startfile``).

    Args:
        target: o que abrir (ex.: "calc.exe", "whatsapp:", um caminho).

    Raises:
        NotImplementedError: fora do Windows.
        OSError: se o Windows nao encontrar ou recusar o alvo.
    """
    if not IS_WINDOWS:
        raise NotImplementedError("open_with_shell so funciona no Windows")
    os.startfile(target)  # type: ignore[attr-defined]  # noqa: S606
    logger.info("open_with_shell: %s", target)
