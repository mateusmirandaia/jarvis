"""Cria o atalho "Jarvis" na Area de Trabalho do Windows.

O atalho abre o Jarvis no modo orb usando o ``pythonw.exe`` do ambiente virtual
(sem janela de terminal). Nunca sobrescreve um atalho que ja existe.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from jarvis.os_integration.windows import IS_WINDOWS

logger = logging.getLogger(__name__)

SHORTCUT_NAME = "Jarvis.lnk"
SHORTCUT_ARGS = "-m jarvis --modo orb"

# O PowerShell le os valores de variaveis de ambiente: sem problema com aspas ou acentos.
_PS_SCRIPT = r"""
$desktop = [Environment]::GetFolderPath('Desktop')
$path = Join-Path $desktop $env:JARVIS_LNK_NAME
if (Test-Path -LiteralPath $path) { Write-Output "EXISTE|$path"; exit 0 }
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($path)
$lnk.TargetPath = $env:JARVIS_LNK_TARGET
$lnk.Arguments = $env:JARVIS_LNK_ARGS
$lnk.WorkingDirectory = $env:JARVIS_LNK_DIR
if ($env:JARVIS_LNK_ICON) { $lnk.IconLocation = $env:JARVIS_LNK_ICON }
$lnk.Description = 'Jarvis - assistente de voz'
$lnk.Save()
Write-Output "CRIADO|$path"
"""


def gui_python() -> Path:
    """Devolve o ``pythonw.exe`` do ambiente atual (ou o ``python.exe``, se nao houver)."""
    current = Path(sys.executable)
    windowless = current.with_name("pythonw.exe")
    return windowless if windowless.exists() else current


def create_desktop_shortcut(project_root: Path, icon: Path | None = None) -> str:
    """Cria o atalho na Area de Trabalho e devolve uma mensagem para o usuario.

    Args:
        project_root: pasta do projeto (vira a pasta de trabalho do atalho, onde fica o .env).
        icon: arquivo .ico do atalho (opcional).

    Returns:
        Mensagem em portugues dizendo onde o atalho ficou ou por que nao foi criado.
    """
    if not IS_WINDOWS:
        return "O atalho na Área de Trabalho só pode ser criado no Windows."
    env = os.environ | {
        "JARVIS_LNK_NAME": SHORTCUT_NAME,
        "JARVIS_LNK_TARGET": str(gui_python()),
        "JARVIS_LNK_ARGS": SHORTCUT_ARGS,
        "JARVIS_LNK_DIR": str(project_root),
        "JARVIS_LNK_ICON": str(icon) if icon and icon.exists() else "",
    }
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    status, _, where = result.stdout.strip().partition("|")
    if status == "CRIADO":
        logger.info("atalho criado em %s", where)
        return f"Atalho criado: {where}. Dê dois cliques nele para abrir o Jarvis."
    if status == "EXISTE":
        return (
            f"Já existe um atalho em {where}. Não sobrescrevi. "
            "Se quiser recriar, apague o antigo e rode o comando de novo."
        )
    logger.error("falha ao criar atalho: %s %s", result.stdout, result.stderr)
    return "Não consegui criar o atalho. Os detalhes ficaram no log do Jarvis."
