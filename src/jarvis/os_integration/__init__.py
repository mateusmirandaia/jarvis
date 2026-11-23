"""Integracao com o sistema operacional (Windows) usada pelas ferramentas do Jarvis."""

from __future__ import annotations

from jarvis.os_integration.windows import (
    IS_WINDOWS,
    Window,
    close_window,
    confirm_dialog,
    kill_process,
    list_windows,
    open_with_shell,
    show_message,
)

__all__ = [
    "IS_WINDOWS",
    "Window",
    "close_window",
    "confirm_dialog",
    "kill_process",
    "list_windows",
    "open_with_shell",
    "show_message",
]
