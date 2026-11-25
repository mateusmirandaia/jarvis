"""Registro das ferramentas do Jarvis: a LISTA FECHADA de acoes que a IA pode chamar.

Acao nova = metodo na classe de ferramentas + nome na tupla ``TOOL_NAMES`` dela.
Cada acao passa por ``safe_tool``: erro vira uma frase simples, nunca trava o Jarvis.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jarvis.config import Settings
from jarvis.errors import safe_tool
from jarvis.tools.app_tools import AppTools
from jarvis.tools.file_tools import FileTools
from jarvis.tools.security import PathGuard
from jarvis.tools.system_tools import SystemTools
from jarvis.tools.web_tools import WebTools

logger = logging.getLogger(__name__)

__all__ = ["ToolRegistry", "confirm_timeout_for"]

# Acoes que esperam o senhor clicar numa janela ganham mais tempo.
SLOW_TOOLS = frozenset({"delete_to_trash"})

# A janela de confirmacao fecha sozinha esta folga ANTES de o Jarvis desistir de esperar.
# Assim um clique atrasado em "Sim" nunca apaga nada depois que a IA ja ouviu "falhou".
DIALOG_MARGIN_S = 10.0


def confirm_timeout_for(settings: Settings) -> float:
    """Tempo (segundos) que a janela de apagar fica aberta: sempre menor que delete_timeout_s.

    Args:
        settings: configuracoes com ``delete_timeout_s``.
    """
    total = settings.delete_timeout_s
    return max(total - DIALOG_MARGIN_S, total / 2)


def _pasta_usuario() -> Path:
    from jarvis.armazenamento import pasta_usuario

    return pasta_usuario()


class ToolRegistry:
    """Monta as ferramentas, embrulha cada uma com ``safe_tool`` e entrega a lista fechada."""

    def __init__(
        self, settings: Settings, confirm: Callable[[str, str], bool] | None = None
    ) -> None:
        """Cria o registro.

        Args:
            settings: configuracoes do Jarvis (pasta do projeto e tempos limite).
            confirm: confirmacao manual (titulo, mensagem) -> bool; None usa a janela do Windows.
        """
        self._settings = settings
        # A pasta de dados do usuario guarda as chaves (.env): nenhuma acao mexe nela.
        self._guard = PathGuard(settings.project_root, extra_protected=[_pasta_usuario()])
        self._apps = AppTools()
        files = FileTools(
            self._guard, confirm=confirm, confirm_timeout_s=confirm_timeout_for(settings)
        )
        providers: tuple[Any, ...] = (SystemTools(), self._apps, WebTools(), files)

        self._tools: dict[str, Callable[..., str]] = {}
        for provider in providers:
            for name in provider.TOOL_NAMES:
                if name in self._tools:
                    raise ValueError(f"ferramenta duplicada: {name}")
                self._tools[name] = safe_tool(getattr(provider, name))
        logger.info("ferramentas registradas: %s", ", ".join(self._tools))

    @property
    def functions(self) -> list[Callable[..., str]]:
        """Funcoes embrulhadas, na ordem: system, apps, web, files."""
        return list(self._tools.values())

    @property
    def names(self) -> list[str]:
        """Nomes das ferramentas, na mesma ordem de ``functions``."""
        return list(self._tools)

    def get(self, name: str) -> Callable[..., str] | None:
        """Devolve a ferramenta embrulhada pelo nome, ou None se nao existir.

        Args:
            name: nome da ferramenta (ex.: "create_folder").
        """
        return self._tools.get(name)

    def timeout_for(self, name: str, settings: Settings) -> float:
        """Tempo limite (segundos) para executar a ferramenta.

        Args:
            name: nome da ferramenta.
            settings: configuracoes com ``tool_timeout_s`` e ``delete_timeout_s``.
        """
        return settings.delete_timeout_s if name in SLOW_TOOLS else settings.tool_timeout_s

    @property
    def guard(self) -> PathGuard:
        """Guarda de caminhos compartilhado (pastas do usuario e pastas protegidas)."""
        return self._guard

    @property
    def app_names(self) -> list[str]:
        """Nomes falados dos apps conhecidos (para o prompt de sistema)."""
        return self._apps.app_names
