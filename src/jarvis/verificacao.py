"""Testes rapidos das chaves (Google e ElevenLabs) feitos pela janela de configuracao.

Tudo aqui devolve mensagens curtas em portugues para a pessoa leiga e NUNCA coloca a chave em
log, mensagem ou excecao. A rede e injetavel (``transport`` do httpx; cliente do Gemini por
fabrica) para os testes rodarem sem internet.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from jarvis.assistants.elevenlabs_voice import ElevenLabsError, ElevenLabsVoice
from jarvis.errors import _cadeia, _codigo, _texto, erro_de_autenticacao

__all__ = ["erro_de_autenticacao"]

logger = logging.getLogger(__name__)

GEMINI_TIMEOUT_MS = 12_000
ELEVENLABS_VOICES_URL = "https://api.elevenlabs.io/v1/voices"
ELEVENLABS_TIMEOUT = httpx.Timeout(12.0, connect=6.0)
ELEVENLABS_MODELO_PADRAO = "eleven_flash_v2_5"
FRASE_TESTE_ELEVENLABS = "Olá, senhor. Esta é a minha nova voz."
MAX_VOZES = 300
MAX_AUDIO_TESTE_BYTES = 24_000 * 2 * 15  # 15 s de PCM 24 kHz: bem mais que a frase de teste

# Formatos plausiveis. A chave do Google costuma ser "AIza" + 35 caracteres, mas o formato
# pode mudar: aceitamos qualquer texto longo so com letras, numeros, "_" e "-".
_FORMATO_CHAVE_GOOGLE = re.compile(r"[A-Za-z0-9_\-]{20,200}")
_FORMATO_CHAVE_ELEVENLABS = re.compile(r"[A-Za-z0-9_\-]{16,200}")
_FORMATO_VOZ_ELEVENLABS = re.compile(r"[A-Za-z0-9]{8,64}")

MSG_OK = "Chave funcionando."
MSG_FORMATO = "Essa chave não parece completa. Copie de novo a chave inteira e cole aqui."
MSG_INVALIDA = "Chave inválida. Confira se copiou a chave inteira, sem espaços."
MSG_SEM_INTERNET = "Sem internet (ou o Google não respondeu). Confira a conexão e tente de novo."
MSG_LIMITE = "Limite da conta grátis atingido. Espere alguns minutos e tente de novo."
MSG_GOOGLE_INSTAVEL = "O Google está instável agora. Tente de novo em alguns minutos."
MSG_INESPERADO = "Erro inesperado ao testar a chave. Tente de novo; se continuar, veja o log."

EL_MSG_FORMATO = "Essa chave do ElevenLabs não parece completa. Copie de novo a chave inteira."
EL_MSG_VOZ_FORMATO = (
    "Esse ID de voz não parece certo. Ele tem só letras e números (ex.: 21m00Tcm4)."
)
EL_MSG_INVALIDA = "Chave do ElevenLabs inválida. Confira se copiou a chave inteira."
EL_MSG_SEM_PERMISSAO_VOZES = (
    'Sua chave não tem a permissão "Voices: read", então não consigo listar as vozes. '
    'Crie outra chave marcando "Voices: read" (e "Text to Speech"), ou cole o ID da voz à mão.'
)
EL_MSG_SEM_PERMISSAO_FALA = (
    'Sua chave não tem a permissão "Text to Speech". Crie outra chave marcando essa permissão.'
)
EL_MSG_SEM_CREDITOS = "Seus créditos do ElevenLabs acabaram (ou o plano não permite essa voz)."
EL_MSG_VOZ_NAO_ACHADA = "Não achei essa voz na sua conta do ElevenLabs. Confira o ID da voz."
EL_MSG_SEM_INTERNET = "Sem internet (ou o ElevenLabs não respondeu). Confira a conexão."
EL_MSG_LIMITE = "O ElevenLabs pediu para esperar um pouco (muitos pedidos). Tente de novo já já."
EL_MSG_INESPERADO = "Erro inesperado no ElevenLabs. Tente de novo; se continuar, veja o log."
EL_MSG_SEM_VOZES = "Sua conta ainda não tem vozes. Crie ou adicione uma voz no site do ElevenLabs."


@dataclass(frozen=True)
class Resultado:
    """Resultado de um teste: ``ok`` e uma mensagem para mostrar a pessoa."""

    ok: bool
    mensagem: str

    def como_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "mensagem": self.mensagem}


# --------------------------------------------------------------------- formatos
def chave_google_plausivel(chave: object) -> bool:
    """True se ``chave`` tem o formato de uma chave do Google AI Studio."""
    return isinstance(chave, str) and _FORMATO_CHAVE_GOOGLE.fullmatch(chave) is not None


def chave_elevenlabs_plausivel(chave: object) -> bool:
    """True se ``chave`` tem o formato de uma chave do ElevenLabs."""
    return isinstance(chave, str) and _FORMATO_CHAVE_ELEVENLABS.fullmatch(chave) is not None


def voz_elevenlabs_plausivel(voz_id: object) -> bool:
    """True se ``voz_id`` tem o formato de um ID de voz do ElevenLabs (vai na URL)."""
    return isinstance(voz_id, str) and _FORMATO_VOZ_ELEVENLABS.fullmatch(voz_id) is not None


# ------------------------------------------------------------------- erros
def _erro_de_rede(erro: BaseException) -> bool:
    for atual in _cadeia(erro):
        if isinstance(atual, httpx.TransportError | ConnectionError | TimeoutError):
            return True
        nome = type(atual).__name__
        if nome in {"ConnectError", "ConnectTimeout", "ReadTimeout", "TimeoutException"}:
            return True
        if isinstance(atual, OSError) and not isinstance(atual, FileNotFoundError):
            return True
    return False


def _codigo_api(erro: BaseException) -> int | None:
    try:
        from google.genai import errors as genai_errors
    except ImportError:  # pragma: no cover
        return None
    for atual in _cadeia(erro):
        if isinstance(atual, genai_errors.APIError):
            return _codigo(atual)
    return None


def _resumo(erro: BaseException, *segredos: str) -> str:
    """Descricao curta do erro para o log, sem nenhum segredo."""
    from jarvis.logging_setup import redigir

    texto = f"{type(erro).__name__} {_codigo(erro) or ''} {str(erro)[:200]}"
    for segredo in segredos:
        if segredo:
            texto = texto.replace(segredo, "…")
    return redigir(texto)


def mensagem_erro_gemini(erro: BaseException) -> str:
    """Traduz um erro do Google numa frase simples."""
    if erro_de_autenticacao(erro):
        return MSG_INVALIDA
    codigo = _codigo_api(erro)
    if codigo == 429:
        return MSG_LIMITE
    if codigo is not None and 500 <= codigo < 600:
        return MSG_GOOGLE_INSTAVEL
    if codigo == 400:
        return MSG_INVALIDA if "key" in _texto(erro) else MSG_INESPERADO
    if _erro_de_rede(erro):
        return MSG_SEM_INTERNET
    return MSG_INESPERADO


# ------------------------------------------------------------------- Google
def _cliente_gemini_padrao(chave: str) -> Any:
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=chave,
        http_options=types.HttpOptions(
            timeout=GEMINI_TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def testar_chave_gemini(
    chave: object, fabrica_cliente: Callable[[str], Any] | None = None
) -> Resultado:
    """Faz a chamada mais barata possivel (listar 1 modelo) para ver se a chave funciona.

    Args:
        chave: a chave colada pela pessoa.
        fabrica_cliente: cria o cliente do Gemini (os testes passam um falso).

    Returns:
        ``Resultado`` com uma das mensagens simples (chave funcionando, invalida, sem
        internet, limite atingido, erro inesperado).
    """
    if not chave_google_plausivel(chave):
        return Resultado(False, MSG_FORMATO)
    assert isinstance(chave, str)
    try:
        cliente = (fabrica_cliente or _cliente_gemini_padrao)(chave)
        modelos = cliente.models.list(config={"page_size": 1})
        next(iter(modelos), None)
    except Exception as erro:  # noqa: BLE001 - qualquer falha vira frase simples
        mensagem = mensagem_erro_gemini(erro)
        logger.warning("teste da chave do Google falhou: %s", _resumo(erro, chave))
        return Resultado(False, mensagem)
    logger.info("teste da chave do Google: ok")
    return Resultado(True, MSG_OK)


# --------------------------------------------------------------- ElevenLabs
def _status_detalhe(corpo: Any) -> tuple[str, str]:
    """Extrai (status, mensagem) do JSON de erro do ElevenLabs: {"detail": {...}}."""
    detalhe = corpo.get("detail") if isinstance(corpo, dict) else None
    if isinstance(detalhe, dict):
        return str(detalhe.get("status", "")).lower(), str(detalhe.get("message", "")).lower()
    if isinstance(detalhe, str):
        return "", detalhe.lower()
    return "", ""


def _json_seguro(texto: str) -> Any:
    import json

    try:
        return json.loads(texto)
    except ValueError:
        return None


def mensagem_erro_elevenlabs(status: int | None, corpo_texto: str, *, listando: bool) -> str:
    """Traduz uma resposta de erro do ElevenLabs numa frase simples."""
    if status is None:
        return EL_MSG_SEM_INTERNET
    codigo, mensagem = _status_detalhe(_json_seguro(corpo_texto))
    junto = f"{codigo} {mensagem} {corpo_texto[:300].lower()}"
    if "missing_permissions" in junto or "permission" in junto:
        if listando or "voices_read" in junto:
            return EL_MSG_SEM_PERMISSAO_VOZES
        return EL_MSG_SEM_PERMISSAO_FALA
    if "quota" in junto or "credit" in junto or status == 402:
        return EL_MSG_SEM_CREDITOS
    if status == 401 or "invalid_api_key" in junto:
        return EL_MSG_INVALIDA
    if status == 404 or "voice_not_found" in junto:
        return EL_MSG_VOZ_NAO_ACHADA
    if status == 429:
        return EL_MSG_LIMITE
    return EL_MSG_INESPERADO


def _texto_curto(valor: object, limite: int) -> str:
    if not isinstance(valor, str):
        return ""
    limpo = "".join(c for c in valor if c.isprintable())
    return limpo.strip()[:limite]


def listar_vozes_elevenlabs(
    chave: object, transport: httpx.BaseTransport | None = None
) -> dict[str, Any]:
    """Lista as vozes da conta (``GET /v1/voices``; precisa da permissao "Voices: read").

    Returns:
        ``{"ok": True, "vozes": [{"id", "nome"}], "mensagem": ""}`` ou
        ``{"ok": False, "vozes": [], "mensagem": "..."}``.
    """
    if not chave_elevenlabs_plausivel(chave):
        return {"ok": False, "vozes": [], "mensagem": EL_MSG_FORMATO}
    assert isinstance(chave, str)
    try:
        with httpx.Client(timeout=ELEVENLABS_TIMEOUT, transport=transport) as cliente:
            resposta = cliente.get(
                ELEVENLABS_VOICES_URL,
                headers={"xi-api-key": chave, "accept": "application/json"},
            )
            texto = resposta.text
            status = resposta.status_code
    except httpx.HTTPError as erro:
        logger.warning("ElevenLabs (listar vozes) sem resposta: %s", _resumo(erro, chave))
        return {"ok": False, "vozes": [], "mensagem": EL_MSG_SEM_INTERNET}
    if status != 200:
        logger.warning("ElevenLabs (listar vozes) respondeu HTTP %s", status)
        mensagem = mensagem_erro_elevenlabs(status, texto, listando=True)
        return {"ok": False, "vozes": [], "mensagem": mensagem}
    corpo = _json_seguro(texto)
    brutas = corpo.get("voices") if isinstance(corpo, dict) else None
    vozes: list[dict[str, str]] = []
    for item in brutas if isinstance(brutas, list) else []:
        if not isinstance(item, dict):
            continue
        voz_id = item.get("voice_id")
        if not voz_elevenlabs_plausivel(voz_id):
            continue
        nome = _texto_curto(item.get("name"), 60) or str(voz_id)
        vozes.append({"id": str(voz_id), "nome": nome})
        if len(vozes) >= MAX_VOZES:
            break
    logger.info("ElevenLabs: %d voz(es) na conta", len(vozes))
    if not vozes:
        return {"ok": False, "vozes": [], "mensagem": EL_MSG_SEM_VOZES}
    return {"ok": True, "vozes": vozes, "mensagem": ""}


def sintetizar_elevenlabs(
    chave: str,
    voz_id: str,
    texto: str = FRASE_TESTE_ELEVENLABS,
    modelo: str = ELEVENLABS_MODELO_PADRAO,
    transport: httpx.AsyncBaseTransport | None = None,
) -> bytes:
    """Gera a fala de ``texto`` com o mesmo cliente usado pelo assistente (PCM 24 kHz).

    Raises:
        ElevenLabsError: chave, permissao, creditos, voz ou rede (``status`` None = rede).
    """

    async def _baixar() -> bytes:
        voz = ElevenLabsVoice(chave, voz_id, modelo, transport=transport)
        partes: list[bytes] = []
        total = 0
        try:
            async for pedaco in voz.stream(texto):
                partes.append(pedaco)
                total += len(pedaco)
                if total >= MAX_AUDIO_TESTE_BYTES:
                    break
        finally:
            await voz.close()
        return b"".join(partes)

    return asyncio.run(_baixar())


def testar_voz_elevenlabs(
    chave: object,
    voz_id: object,
    tocar: Callable[[bytes], None],
    modelo: str = ELEVENLABS_MODELO_PADRAO,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Resultado:
    """Fala uma frase curta com a voz (gasta creditos) e toca pelos alto-falantes."""
    if not chave_elevenlabs_plausivel(chave):
        return Resultado(False, EL_MSG_FORMATO)
    if not voz_elevenlabs_plausivel(voz_id):
        return Resultado(False, EL_MSG_VOZ_FORMATO)
    assert isinstance(chave, str) and isinstance(voz_id, str)
    try:
        audio = sintetizar_elevenlabs(chave, voz_id, modelo=modelo, transport=transport)
    except ElevenLabsError as erro:
        logger.warning("ElevenLabs (teste de voz) falhou: HTTP %s", erro.status)
        return Resultado(False, mensagem_erro_elevenlabs(erro.status, erro.detail, listando=False))
    except Exception as erro:  # noqa: BLE001
        logger.warning("ElevenLabs (teste de voz) falhou: %s", _resumo(erro, chave))
        return Resultado(False, EL_MSG_INESPERADO)
    if not audio:
        return Resultado(False, EL_MSG_INESPERADO)
    try:
        tocar(audio)
    except Exception as erro:  # noqa: BLE001
        logger.warning("nao consegui tocar o teste de voz: %s", _resumo(erro, chave))
        return Resultado(False, "Gerei a voz, mas não consegui tocar no alto-falante.")
    return Resultado(True, "Pronto! Essa é a voz escolhida.")
