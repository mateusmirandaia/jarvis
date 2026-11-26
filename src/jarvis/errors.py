"""Erros do Jarvis e o embrulho que transforma qualquer falha de ferramenta em frase simples."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable, Iterator
from typing import Any, Literal

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


class SemRespostaError(JarvisError):
    """O modelo ficou mudo depois da fala do senhor (nem audio, nem texto, nem acao).

    O ``LiveAssistant`` trata como problema de internet: toca o aviso, derruba a sessao e
    reconecta.
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
        reason = (
            "a acao demorou demais e eu desisti de esperar, mas ela pode ter terminado "
            "mesmo assim; confira antes de repetir"
        )
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

    # Ferramenta que devolve texto longo (read_file) declara o proprio limite.
    limite = int(getattr(func, "max_result_chars", MAX_RESULT_CHARS))

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            result = str(func(*args, **kwargs))
        except Exception as exc:
            logger.exception("Falha na ferramenta %s", getattr(func, "__name__", func))
            return friendly_message(exc)
        if len(result) > limite:
            result = result[:limite] + _CUT_SUFFIX
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


# ------------------------------------------------------------- tipo da queda da sessao
TipoQueda = Literal["chave", "audio", "cota", "rede", "encerrada", "outro"]

_ATRIBUTO_DISPOSITIVO = "jarvis_dispositivo"
# Codigos de fechamento do WebSocket que indicam rede ruim ou servidor com problema.
_CODIGOS_WS_REDE = frozenset({1006, 1011, 1012, 1013, 1014, 1015})
# Fechamento normal (o Google encerra a sessao, ex.: tempo maximo de conexao).
_CODIGOS_WS_FIM = frozenset({1000, 1001})
_TEXTOS_COTA = ("resource_exhausted", "quota", "rate limit", "too many requests")


def marcar_dispositivo(erro: BaseException, dispositivo: str) -> None:
    """Marca o erro como vindo do audio ("microfone" ou "alto-falante"), sem trocar o tipo."""
    try:
        if getattr(erro, _ATRIBUTO_DISPOSITIVO, None) is None:
            setattr(erro, _ATRIBUTO_DISPOSITIVO, dispositivo)
    except Exception:  # noqa: BLE001 - excecao que nao aceita atributo: so nao marca
        logger.debug("nao consegui marcar o erro de audio", exc_info=True)


def dispositivo_do_erro(erro: BaseException) -> str | None:
    """ "microfone"/"alto-falante" se o erro (ou uma causa dele) veio do audio; senao None."""
    for atual in _cadeia(erro):
        dispositivo = getattr(atual, _ATRIBUTO_DISPOSITIVO, None)
        if isinstance(dispositivo, str):
            return dispositivo
    return None


def _erro_de_rede(atual: BaseException) -> bool:
    if isinstance(atual, SemRespostaError | ConnectionError | TimeoutError | asyncio.TimeoutError):
        return True
    try:
        import httpx

        if isinstance(atual, httpx.TransportError):
            return True
    except ImportError:  # pragma: no cover - depende do ambiente
        pass
    try:
        from websockets import exceptions as ws_errors

        if isinstance(atual, ws_errors.WebSocketException):
            return True
    except ImportError:  # pragma: no cover - depende do ambiente
        pass
    # gaierror, SSL, "rede inalcancavel"...: OSError que nao veio do audio
    return isinstance(atual, OSError)


def tipo_de_queda(erro: BaseException) -> TipoQueda:
    """Classifica por que a sessao Live caiu (para escolher o aviso certo).

    Ordem: chave recusada > audio (microfone/alto-falante) > cota (429) > rede (queda,
    timeout, 5xx, modelo mudo) > outro. "encerrada" e o Google fechando a sessao do jeito
    normal (codigo 1000/1001, ex.: tempo maximo da conexao): reconecta sem aviso de internet.
    """
    if erro_de_autenticacao(erro):
        return "chave"
    if dispositivo_do_erro(erro) is not None:
        return "audio"
    cadeia = list(_cadeia(erro))
    try:
        from google.genai import errors as genai_errors
    except ImportError:  # pragma: no cover - depende do ambiente
        genai_errors = None  # type: ignore[assignment]
    apis = [a for a in cadeia if genai_errors is not None and isinstance(a, genai_errors.APIError)]
    for atual in apis:
        if _codigo(atual) == 429 or any(t in _texto(atual) for t in _TEXTOS_COTA):
            return "cota"
    for atual in apis:
        codigo = _codigo(atual)
        if codigo is not None and (500 <= codigo < 600 or codigo in _CODIGOS_WS_REDE):
            return "rede"
    # Antes da rede generica: o APIError 1000 carrega o ConnectionClosedOK como contexto.
    for atual in apis:
        if _codigo(atual) in _CODIGOS_WS_FIM:
            return "encerrada"
    if any(_erro_de_rede(atual) for atual in cadeia):
        return "rede"
    return "outro"
