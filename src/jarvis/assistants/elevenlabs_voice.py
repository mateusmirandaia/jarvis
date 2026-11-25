"""Voz do ElevenLabs para o Jarvis (opcional e paga).

O Gemini Live continua sendo o ouvido e o cerebro. Quando ``ELEVENLABS_API_KEY`` e
``ELEVENLABS_VOICE_ID`` estao no .env, o texto que o Gemini vai falar e enviado, frase
por frase, ao ElevenLabs, e o audio volta em PCM 24 kHz (o mesmo formato do alto-falante).
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
OUTPUT_FORMAT = "pcm_24000"  # igual a SPEAKER_RATE do AudioIO: toca direto, sem converter
LANGUAGE = "pt"
CHUNK_BYTES = 4_096
TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# Fim de frase forte (. ! ? ...) seguido de espaco ou no fim do texto recebido.
_STRONG_END = re.compile(r"[.!?…]+[\"')\]]*(?:\s|$)")
# Pausa (, ; :) para cortar trechos longos, ou o primeiro trecho de cada resposta.
_SOFT_END = re.compile(r"[,;:](?:\s|$)")
_SOFT_SPLIT_MIN_CHARS = 80
FIRST_PIECE_MIN_CHARS = 12  # a primeira fala sai na primeira virgula: ele comeca mais cedo


class ElevenLabsError(RuntimeError):
    """Falha ao gerar voz no ElevenLabs (chave, cota, rede).

    Attributes:
        status: codigo HTTP da resposta (None quando a falha foi de rede).
        detail: inicio do corpo da resposta de erro (o ElevenLabs nunca devolve a chave nele).
    """

    def __init__(self, message: str, status: int | None = None, detail: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


def split_sentences(buffer: str, first_piece: bool = False) -> tuple[list[str], str]:
    """Separa frases completas do texto que ainda esta chegando.

    Frases curtas saem logo, para o Jarvis comecar a falar antes do Gemini terminar.
    No comeco de cada resposta (``first_piece``), corta ja na primeira virgula, para a
    primeira palavra sair o mais rapido possivel.

    Args:
        buffer: texto acumulado da transcricao do Gemini.
        first_piece: True se nada desta resposta foi enviado para falar ainda.

    Returns:
        (frases prontas para falar, resto que ainda nao fechou uma frase).
    """
    sentences: list[str] = []
    rest = buffer
    while True:
        match = _STRONG_END.search(rest)
        if match is None or (first_piece and not sentences):
            soft_min = FIRST_PIECE_MIN_CHARS if first_piece and not sentences else None
            if soft_min is None and len(rest) >= _SOFT_SPLIT_MIN_CHARS:
                soft_min = _SOFT_SPLIT_MIN_CHARS // 2
            soft = _SOFT_END.search(rest, soft_min) if soft_min is not None else None
            if soft is not None and (match is None or soft.end() < match.end()):
                match = soft
        if match is None:
            break
        sentence, rest = rest[: match.end()].strip(), rest[match.end() :]
        if sentence:
            sentences.append(sentence)
    return sentences, rest


class ElevenLabsVoice:
    """Cliente de streaming de voz do ElevenLabs (Flash v2.5 por padrao: menor atraso)."""

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = API_URL.format(voice_id=voice_id)
        self._model = model
        self._client = httpx.AsyncClient(
            timeout=TIMEOUT,
            headers={"xi-api-key": api_key, "accept": "audio/pcm"},
            transport=transport,  # None = rede de verdade; os testes passam um transporte falso
        )

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        """Gera a fala de ``text`` e devolve o audio PCM 24 kHz em pedacos.

        Args:
            text: frase a ser falada.

        Yields:
            Pedacos de audio PCM16 mono a 24 kHz.

        Raises:
            ElevenLabsError: chave invalida, sem creditos, voz inexistente ou rede fora.
        """
        payload = {"text": text, "model_id": self._model, "language_code": LANGUAGE}
        try:
            async with self._client.stream(
                "POST", self._url, params={"output_format": OUTPUT_FORMAT}, json=payload
            ) as response:
                if response.status_code != 200:
                    detail = (await response.aread()).decode("utf-8", "replace")[:300]
                    raise ElevenLabsError(
                        f"HTTP {response.status_code}: {detail}", response.status_code, detail
                    )
                leftover = b""
                async for chunk in response.aiter_bytes(CHUNK_BYTES):
                    data = leftover + chunk
                    cut = len(data) - (len(data) % 2)  # nunca corta uma amostra ao meio
                    leftover = data[cut:]
                    if cut:
                        yield data[:cut]
        except httpx.HTTPError as error:
            raise ElevenLabsError(f"rede: {error!r}") from error

    async def close(self) -> None:
        """Fecha as conexoes HTTP."""
        await self._client.aclose()
