"""Observador do assistente: quem quiser mostrar o estado do Jarvis (ex.: o orb) implementa isto.

O ``LiveAssistant`` avisa o observador quando muda de estado, quando o volume muda
(microfone ou voz do Jarvis), quando um turno de conversa termina, quando uma acao
(ferramenta) termina e quanto tempo levou para ele comecar a responder. O padrao e o
``NullObserver``, que nao faz nada (modo terminal).

``on_tool`` e ``on_latency`` chegaram depois (v0.6.0): o ``LiveAssistant`` os chama de forma
segura, entao observadores antigos que nao os implementam continuam funcionando.
"""

from __future__ import annotations

import array
import math
import sys
from typing import Literal, Protocol

State = Literal["idle", "listening", "thinking", "speaking", "offline"]
Speaker = Literal["voce", "jarvis", "sistema"]

_FULL_SCALE = 6_000  # RMS de PCM16 que consideramos "volume maximo" para a animacao


class AssistantObserver(Protocol):
    """Recebe eventos do assistente. Todos os metodos devem ser rapidos e nunca levantar."""

    def on_state(self, state: State) -> None:
        """O assistente mudou de estado."""

    def on_level(self, level: float) -> None:
        """Volume atual entre 0.0 e 1.0 (microfone ao ouvir, voz do Jarvis ao falar)."""

    def on_transcript(self, speaker: Speaker, text: str) -> None:
        """Uma fala terminou (do senhor, do Jarvis ou um aviso do sistema)."""

    def on_tool(self, name: str, ok: bool) -> None:
        """Uma acao terminou: ``name`` e o nome tecnico da ferramenta; ``ok`` False se falhou."""

    def on_latency(self, seconds: float) -> None:
        """Atraso, em segundos, entre o fim da fala do senhor e o inicio da resposta."""


class NullObserver:
    """Observador vazio: usado no modo terminal."""

    def on_state(self, state: State) -> None:
        """Nao faz nada."""

    def on_level(self, level: float) -> None:
        """Nao faz nada."""

    def on_transcript(self, speaker: Speaker, text: str) -> None:
        """Nao faz nada."""

    def on_tool(self, name: str, ok: bool) -> None:
        """Nao faz nada."""

    def on_latency(self, seconds: float) -> None:
        """Nao faz nada."""


def pcm_level(data: bytes) -> float:
    """Calcula o volume (0.0 a 1.0) de um bloco de audio PCM 16 bits mono.

    Args:
        data: bytes de audio PCM16 little-endian.

    Returns:
        Volume normalizado, ja limitado entre 0.0 e 1.0.
    """
    usable = len(data) - (len(data) % 2)
    if usable <= 0:
        return 0.0
    samples = array.array("h")
    samples.frombytes(data[:usable])
    if sys.byteorder == "big":  # pragma: no cover - so em maquinas big-endian
        samples.byteswap()
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return min(rms / _FULL_SCALE, 1.0)
