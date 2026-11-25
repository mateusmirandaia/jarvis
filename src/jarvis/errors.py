"""Erros do Jarvis e o embrulho que transforma qualquer falha de ferramenta em frase simples."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable, Iterator
from typing import Any

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 700
_CUT_SUFFIX = " ...(cortado)"


class JarvisError(Exception):
    """Erro base do Jarvis."""


class ConfigError(JarvisError):
    """Configuracao ausente ou invalida (ex.: falta a GEMINI_API_KEY no .env)."""


class ChaveInvalidaError(ConfigError):
    """O Google recusou a GEMINI_API_KEY ao conectar (chave errada, apagada ou bloqueada).

    O ``LiveAssistant`` levanta este erro em vez de ficar reconectando: sem chave valida,
    tentar de novo nunca resolve.
    """


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


def _cadeia(erro: BaseException) -> Iterator[BaseException]:
    """O erro, as causas dele e, em ExceptionGroup, os erros de dentro (sem repetir)."""
    vistos: set[int] = set()
    pilha: list[BaseException] = [erro]
    while pilha:
        atual = pilha.pop()
        if id(atual) in vistos:
            continue
        vistos.add(id(atual))
        yield atual
        pilha.extend(getattr(atual, "exceptions", ()) or ())
        for ligado in (atual.__cause__, atual.__context__):
            if ligado is not None:
                pilha.append(ligado)


def _codigo(erro: BaseException) -> int | None:
    codigo = getattr(erro, "code", None)
    if isinstance(codigo, int):
        return codigo
    status = getattr(erro, "status_code", None)
    return status if isinstance(status, int) else None


def _texto(erro: BaseException) -> str:
    partes = [str(erro), str(getattr(erro, "status", "") or ""), str(getattr(erro, "message", ""))]
    return " ".join(partes).lower()


_TEXTOS_CHAVE_RUIM = (
    "api key not valid",
    "api_key_invalid",
    "invalid api key",
    "api key expired",
    "api_key_expired",
    "api key was reported as leaked",
    "unauthenticated",
    "permission_denied",
)


def erro_de_autenticacao(erro: BaseException) -> bool:
    """True se o erro (ou uma causa dele) e o Google recusando a chave.

    Cobre a API REST (HTTP 400 API_KEY_INVALID, 401, 403) e o Gemini Live, que fecha o
    WebSocket com codigo 1007/1008 e o motivo "API key not valid".
    """
    try:
        from google.genai import errors as genai_errors
    except ImportError:  # pragma: no cover - depende do ambiente
        return False
    for atual in _cadeia(erro):
        if not isinstance(atual, genai_errors.APIError):
            continue
        codigo = _codigo(atual)
        if codigo in {401, 403}:
            return True
        texto = _texto(atual)
        if any(trecho in texto for trecho in _TEXTOS_CHAVE_RUIM):
            return True
    return False
