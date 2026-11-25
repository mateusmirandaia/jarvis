"""Regras de seguranca compartilhadas pelas ferramentas do Jarvis.

- Processos do sistema e o proprio terminal do Jarvis nunca sao fechados.
- Programas e scripts nunca sao executados por caminho (so apps pelo nome).
- Pastas do sistema, a raiz do disco e a pasta do projeto (onde fica a chave .env)
  sao protegidas: nada e criado, movido ou apagado nelas.
"""

from __future__ import annotations

import logging
import os
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

# Nomes de imagem como o tasklist mostra, sempre em minusculo e com ".exe".
PROTECTED_PROCESSES: frozenset[str] = frozenset(
    {
        "explorer.exe",
        "svchost.exe",
        "csrss.exe",
        "winlogon.exe",
        "lsass.exe",
        "services.exe",
        "smss.exe",
        "wininit.exe",
        "dwm.exe",
        "msmpeng.exe",
        "python.exe",
        "pythonw.exe",
        "py.exe",
        "powershell.exe",
        "pwsh.exe",
        "cmd.exe",
        "windowsterminal.exe",
        "conhost.exe",
        "openconsole.exe",
    }
)

EXECUTABLE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".ps1",
        ".vbs",
        ".js",
        ".msi",
        ".scr",
        ".com",
        ".reg",
        ".jar",
        ".hta",
        ".wsf",
    }
)


def normalize(text: str) -> str:
    """Deixa o texto em minusculo, sem acentos e sem espacos nas pontas."""
    decomposed = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _system_folders() -> list[Path]:
    """Pastas do Windows que nunca podem ser alteradas."""
    return [
        Path(os.environ.get("SystemRoot", r"C:\Windows")),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("ProgramData", r"C:\ProgramData")),
    ]


class PathGuard:
    """Traduz caminhos falados em ``Path`` e diz se um caminho e protegido.

    Args:
        project_root: pasta do projeto Jarvis (protegida, pois guarda a chave).
        home: pasta do usuario; padrao ``Path.home()`` (injetavel para testes).
        extra_protected: outras pastas protegidas (ex.: ``%APPDATA%\\Jarvis``, com as chaves).
    """

    def __init__(
        self,
        project_root: Path,
        home: Path | None = None,
        extra_protected: list[Path] | None = None,
    ) -> None:
        self._project_root = Path(project_root)
        self._home = Path(home) if home is not None else Path.home()
        extras = [Path(pasta) for pasta in extra_protected or []]
        self._protected = [*_system_folders(), self._project_root, *extras]

    @property
    def project_root(self) -> Path:
        """Pasta do projeto Jarvis."""
        return self._project_root

    @property
    def home(self) -> Path:
        """Pasta do usuario usada para os atalhos."""
        return self._home

    def user_folders(self) -> dict[str, Path]:
        """Atalhos falados -> pasta real (OneDrive primeiro, como o Windows costuma usar)."""
        home = self._home
        options: dict[str, list[Path]] = {
            "area de trabalho": [
                home / "OneDrive" / "Área de Trabalho",
                home / "OneDrive" / "Desktop",
                home / "Desktop",
                home / "Área de Trabalho",
            ],
            "documentos": [
                home / "OneDrive" / "Documentos",
                home / "OneDrive" / "Documents",
                home / "Documents",
            ],
            "downloads": [home / "Downloads"],
        }
        return {
            name: next((p for p in candidates if p.is_dir()), candidates[-1])
            for name, candidates in options.items()
        }

    def resolve(self, text: str) -> Path:
        """Aceita caminho completo, "C:" (vira "C:\\") ou atalhos como "area de trabalho\\x".

        Args:
            text: caminho dito pelo usuario ou escolhido pela IA.
        """
        raw = text.strip().strip('"')
        norm = normalize(raw).replace("\\", "/")
        for alias, folder in self.user_folders().items():
            if norm == alias or norm.startswith(alias + "/"):
                rest = raw[len(alias) :].lstrip("\\/")
                return folder / rest if rest else folder
        if len(raw) == 2 and raw[1] == ":":
            raw += "\\"
        return Path(os.path.expandvars(os.path.expanduser(raw)))

    def is_protected(self, path: Path) -> bool:
        """True para a raiz do disco, pastas do sistema e a pasta do projeto (e o que ha dentro).

        Args:
            path: caminho a verificar (nao precisa existir).
        """
        resolved = Path(path).resolve()
        if resolved == Path(resolved.anchor):
            return True
        for folder in self._protected:
            base = folder.resolve()
            if resolved == base or resolved.is_relative_to(base):
                logger.info("caminho protegido bloqueado: %s", resolved)
                return True
        return False
