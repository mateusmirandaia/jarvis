"""Ferramentas de aplicativos: listar, abrir e fechar apps do Windows."""

from __future__ import annotations

import logging
import webbrowser
from pathlib import Path

from jarvis.os_integration import windows
from jarvis.tools.security import EXECUTABLE_EXTENSIONS, PROTECTED_PROCESSES, normalize

logger = logging.getLogger(__name__)

# nome falado -> (comando para abrir, processos que representam o app)
APPS: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "calculadora": ("calc.exe", ("calculatorapp.exe", "calc.exe")),
    "bloco de notas": ("notepad.exe", ("notepad.exe",)),
    "paint": ("mspaint.exe", ("mspaint.exe",)),
    "explorador de arquivos": ("explorer.exe", ()),
    "navegador": (None, ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe")),
    "chrome": ("chrome", ("chrome.exe",)),
    "edge": ("msedge", ("msedge.exe",)),
    "word": ("winword", ("winword.exe",)),
    "excel": ("excel", ("excel.exe",)),
    "powerpoint": ("powerpnt", ("powerpnt.exe",)),
    "vs code": ("code", ("code.exe",)),
    "spotify": ("spotify", ("spotify.exe",)),
    "whatsapp": ("whatsapp:", ("whatsapp.exe", "whatsapp.root.exe")),
}
APP_NAMES: tuple[str, ...] = tuple(APPS)

BROWSERS: frozenset[str] = frozenset(
    {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
)

ONLY_WINDOWS = "Esta acao so funciona no Windows."


class AppTools:
    """Abre e fecha aplicativos pelo nome, nunca por caminho, nunca processos do sistema."""

    TOOL_NAMES: tuple[str, ...] = ("list_open_apps", "open_app", "close_app")

    @property
    def app_names(self) -> list[str]:
        """Nomes de apps conhecidos (usados no prompt do sistema)."""
        return list(APP_NAMES)

    def _windows(self) -> list[windows.Window]:
        return windows.list_windows(PROTECTED_PROCESSES)

    def list_open_apps(self) -> str:
        """Lista os aplicativos abertos na tela (processo e titulo da janela)."""
        apps = self._windows()
        if not apps:
            return "Nao encontrei janelas abertas (ou nao estou no Windows)."
        return " | ".join(f"{w.process}: {w.title[:60]}" for w in apps[:25])

    def open_app(self, nome: str) -> str:
        """Abre um aplicativo pelo nome (ex.: calculadora, chrome, word, excel, spotify, vs code).

        Args:
            nome: nome do app.
        """
        if not windows.IS_WINDOWS:
            return ONLY_WINDOWS
        key = normalize(nome)
        if key == "navegador":
            webbrowser.open("about:blank")
            return "Navegador aberto."
        command = APPS.get(key, (None, ()))[0]
        if command is None:
            looks_like_path = any(sep in nome for sep in ("\\", "/", ":"))
            if looks_like_path or Path(nome.strip()).suffix.lower() in EXECUTABLE_EXTENSIONS:
                logger.warning("abertura por caminho recusada: %s", nome)
                return "Por seguranca, abro apps pelo nome, nao por caminho."
            command = nome.strip()
        try:
            windows.open_with_shell(command)
        except OSError:
            try:
                windows.open_with_shell(command + ".exe")
            except OSError:
                return f"Nao encontrei o app '{nome}' instalado."
        return f"{nome} aberto."

    def close_app(self, nome: str, forcar: bool = False) -> str:
        """Fecha um aplicativo aberto (pelo nome do app ou pelo titulo da janela).
        Fecha a janela do jeito normal (o app pode perguntar se quer salvar).

        Args:
            nome: ex.: "navegador", "calculadora", "firefox", ou parte do titulo da janela.
            forcar: True so se o senhor pedir para fechar a forca (perde o que nao foi salvo).
        """
        if not windows.IS_WINDOWS:
            return ONLY_WINDOWS
        key = normalize(nome)
        open_windows = self._windows()
        known = {p.lower() for p in APPS.get(key, (None, ()))[1]}
        targets = [w for w in open_windows if w.process.lower() in known]
        if not targets and (known & BROWSERS or "naveg" in key):
            targets = [w for w in open_windows if w.process.lower() in BROWSERS]
        if not targets:
            compact = key.replace(" ", "")
            targets = [
                w
                for w in open_windows
                if compact in normalize(w.process).replace(" ", "") or key in normalize(w.title)
            ]
        # Defesa extra: list_windows ja exclui, mas nunca toca em processo protegido.
        targets = [w for w in targets if w.process.lower() not in PROTECTED_PROCESSES]
        if not targets:
            return f"Nao achei '{nome}' aberto. Abertos agora: {self.list_open_apps()}"
        if forcar:
            processes = sorted({w.process for w in targets})
            for process in processes:
                windows.kill_process(process)
            return "Fechado a forca: " + ", ".join(processes)
        for w in targets:
            windows.close_window(w.hwnd)
        return "Fechei: " + " | ".join(f"{w.process} ({w.title[:40]})" for w in targets)
