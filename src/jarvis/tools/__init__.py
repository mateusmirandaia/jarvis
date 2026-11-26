"""Registro das ferramentas do Jarvis: a LISTA FECHADA de acoes que a IA pode chamar.

Acao nova = metodo na classe de ferramentas + nome na tupla ``TOOL_NAMES`` dela + uma linha
no mapa ``EXIGENCIAS`` de ``tools/permissoes.py`` (sem isso ela fica sempre bloqueada).
Cada acao passa por ``safe_tool``: erro vira uma frase simples, nunca trava o Jarvis.
Antes de rodar, cada acao confere as permissoes ATUAIS (lidas na hora da chamada).
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from jarvis.config import Settings
from jarvis.errors import safe_tool
from jarvis.logging_setup import registrar_segredos
from jarvis.tools import permissoes
from jarvis.tools.app_tools import AppTools
from jarvis.tools.file_tools import FileTools
from jarvis.tools.office_tools import OfficeTools
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


def _permissoes_salvas() -> Mapping[str, Any]:
    """Padrao: le o preferencias.json a cada chamada (mudar no painel vale na hora)."""
    from jarvis.ui import preferencias

    return preferencias.carregar_permissoes()


def _ler_permissoes(fonte: Callable[[], Mapping[str, Any]]) -> dict[str, Any]:
    """Permissoes atuais; qualquer erro (ou valor estranho) vira tudo desligado."""
    try:
        return permissoes.normalizar(fonte())
    except Exception:  # noqa: BLE001 - ler permissao nunca derruba o Jarvis
        logger.warning("nao consegui ler as permissoes; tudo desligado", exc_info=True)
        return permissoes.normalizar(None)


def _com_permissao(
    nome: str, func: Callable[..., str], fonte: Callable[[], Mapping[str, Any]]
) -> Callable[..., str]:
    """Embrulha a ferramenta: bloqueada devolve a frase do contrato SEM executar.

    Mantem nome, docstring e assinatura (a SDK do Gemini monta o schema com eles).
    """

    @functools.wraps(func)
    def checar(*args: Any, **kwargs: Any) -> str:
        if not permissoes.permitido(nome, _ler_permissoes(fonte)):
            logger.info("ferramenta bloqueada pelas permissoes: %s", nome)
            return permissoes.mensagem_bloqueio(nome)
        return func(*args, **kwargs)

    return checar


class ToolRegistry:
    """Monta as ferramentas, embrulha cada uma com ``safe_tool`` e entrega a lista fechada."""

    def __init__(
        self,
        settings: Settings,
        confirm: Callable[[str, str], bool] | None = None,
        permissoes_atuais: Callable[[], Mapping[str, Any]] | None = None,
    ) -> None:
        """Cria o registro.

        Args:
            settings: configuracoes do Jarvis (pasta do projeto e tempos limite).
            confirm: confirmacao manual (titulo, mensagem) -> bool; None usa a janela do Windows.
            permissoes_atuais: funcao que devolve as permissoes de AGORA (chamada a cada
                ferramenta); None le o preferencias.json. Erro = tudo desligado.
        """
        self._settings = settings
        self._permissoes_atuais = permissoes_atuais or _permissoes_salvas
        # O log apaga o valor exato das chaves em uso, qualquer que seja o formato delas.
        registrar_segredos(settings.api_key, settings.elevenlabs_api_key)
        # A pasta de dados do usuario guarda as chaves (.env): nenhuma acao mexe nela.
        # "Outros discos" e conferido no PathGuard a cada caminho: as ferramentas de arquivo
        # (de hoje e as novas) herdam a regra sem mudar nada nelas.
        self._guard = PathGuard(
            settings.project_root,
            extra_protected=[_pasta_usuario()],
            outros_drives=self._outros_drives,
        )
        self._apps = AppTools()
        files = FileTools(
            self._guard, confirm=confirm, confirm_timeout_s=confirm_timeout_for(settings)
        )
        providers: tuple[Any, ...] = (
            SystemTools(),
            self._apps,
            WebTools(),
            files,
            OfficeTools(self._guard),
        )

        self._tools: dict[str, Callable[..., str]] = {}
        for provider in providers:
            for name in provider.TOOL_NAMES:
                if name in self._tools:
                    raise ValueError(f"ferramenta duplicada: {name}")
                self._tools[name] = _com_permissao(
                    name, safe_tool(getattr(provider, name)), self._permissoes_atuais
                )
        logger.info("ferramentas registradas: %s", ", ".join(self._tools))

    def _outros_drives(self) -> bool:
        return permissoes.outros_drives(_ler_permissoes(self._permissoes_atuais))

    def permissoes(self) -> dict[str, Any]:
        """Permissoes valendo agora (completas; erro = tudo desligado)."""
        return _ler_permissoes(self._permissoes_atuais)

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
