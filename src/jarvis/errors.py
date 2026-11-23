"""Erros do Jarvis e o embrulho que transforma qualquer falha de ferramenta em frase simples."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 700
_CUT_SUFFIX = " ...(cortado)"


class JarvisError(Exception):
    """Erro base do Jarvis."""


class ConfigError(JarvisError):
    """Configuracao ausente ou invalida (ex.: falta a GEMINI_API_KEY no .env)."""


def friendly_message(error: BaseException) -> str:
    """Traduz uma excecao em uma instrucao curta e sem termos tecnicos para a IA.

    Args:
        error: excecao capturada durante a execucao de uma ferramenta.

    Returns:
        Texto iniciado por "ERRO:" que orienta a IA a avisar o senhor em uma frase simples.
    """
    # A ordem importa: PermissionError, FileNotFoundError e TimeoutError sao subclasses de OSError.
    if isinstance(error, PermissionError):
        reason = "o Windows nao me deu permissao para isso"
    elif isinstance(error, FileNotFoundError):
        reason = "nao encontrei o arquivo ou o programa"
    elif isinstance(error, TimeoutError | asyncio.TimeoutError):
        reason = "a acao demorou demais e eu desisti"
    elif isinstance(error, OSError):
        reason = "o Windows recusou a acao"
    else:
        reason = "algo inesperado deu errado nessa acao"
    return f"ERRO: {reason}. Avise o senhor em uma frase simples, sem termos tecnicos."


def safe_tool(func: Callable[..., Any]) -> Callable[..., str]:
    """Embrulha uma ferramenta: o resultado vira texto curto e erro vira frase, nunca trava.

    Usa functools.wraps para preservar __name__, __doc__ e a assinatura; a SDK do Gemini
    le essas informacoes (inspect.signature) para montar o schema da ferramenta.

    Args:
        func: metodo ou funcao exposta para a IA.

    Returns:
        Funcao com a mesma assinatura que sempre devolve str.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            result = str(func(*args, **kwargs))
        except Exception as exc:
            logger.exception("Falha na ferramenta %s", getattr(func, "__name__", func))
            return friendly_message(exc)
        if len(result) > MAX_RESULT_CHARS:
            result = result[:MAX_RESULT_CHARS] + _CUT_SUFFIX
        return result

    return wrapper
