"""Quem fala: a voz nativa do Gemini ou a voz do ElevenLabs.

Sem ElevenLabs configurado, o audio do Gemini vai direto para o alto-falante.
Com ElevenLabs, o audio do Gemini fica guardado como reserva e o texto da resposta e
falado pelo ElevenLabs, frase por frase. Cada frase e pedida ao ElevenLabs assim que
fica pronta (em paralelo), e o audio toca na ordem certa: sem pausa entre as frases.
Se o ElevenLabs falhar (sem creditos, chave errada, rede), o Jarvis avisa uma vez
(texto na tela + o aviso gravado ``avisos/elevenlabs_Charon.wav``, se existir) e volta para a
voz do Gemini, sem travar.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from jarvis.assistants.elevenlabs_voice import ElevenLabsError, ElevenLabsVoice, split_sentences
from jarvis.assistants.observer import AssistantObserver

logger = logging.getLogger(__name__)

_END: Final = object()  # marca o fim do audio de uma frase
FALLBACK_NOTICE = "Senhor, a voz do ElevenLabs falhou. Vou usar a voz do Google por enquanto."
AVISO_PEDACO_BYTES = 4_800  # ~100 ms: o aviso gravado entra na fila em pedacos (interrompivel)


def _fecha_fila(chunks: asyncio.Queue[object]) -> Callable[[asyncio.Task[None]], None]:
    """Callback que poe ``_END`` na fila da frase quando a tarefa termina (de qualquer jeito)."""

    def fechar(_task: asyncio.Task[None]) -> None:
        chunks.put_nowait(_END)

    return fechar


def _print_seguro(texto: str) -> None:
    """``print`` que nunca levanta (console sem UTF-8, sem console no programa instalado)."""
    try:
        print(texto)
    except Exception:  # noqa: BLE001
        logger.debug("nao consegui escrever no terminal", exc_info=True)


@dataclass(frozen=True)
class _Sentence:
    epoch: int  # muda quando o senhor interrompe: frases antigas sao descartadas
    turn: int  # numero do turno, para achar o audio reserva do Gemini
    text: str | None  # None marca o fim do turno


class VoiceOutput:
    """Roteia a fala do Jarvis para o alto-falante (fila de audio PCM 24 kHz)."""

    def __init__(
        self,
        audio_queue: asyncio.Queue[bytes],
        observer: AssistantObserver,
        elevenlabs: ElevenLabsVoice | None = None,
        aviso_elevenlabs: Callable[[], bytes | None] | None = None,
    ) -> None:
        self._audio_queue = audio_queue
        self._observer = observer
        self._elevenlabs = elevenlabs
        # Devolve o PCM do aviso gravado "minha voz personalizada esta com problemas" (ou None).
        self._aviso_elevenlabs = aviso_elevenlabs
        self._avisou_falha = False  # o aviso de falha toca UMA vez
        self._sentences: asyncio.Queue[_Sentence] = asyncio.Queue()
        self._buffer = ""
        self._epoch = 0
        self._turn = 0
        self._reserve: dict[int, list[bytes]] = {}
        self._spoken_turns: set[int] = set()
        self._started_turns: set[int] = set()  # turnos que ja mandaram a primeira fala
        # frases ja pedidas ao ElevenLabs, na ordem de fala: (frase, fila com o audio dela)
        self._ordered: asyncio.Queue[tuple[_Sentence, asyncio.Queue[object] | None]] = (
            asyncio.Queue()
        )
        self._fetches: set[asyncio.Task[None]] = set()

    @property
    def uses_elevenlabs(self) -> bool:
        """True enquanto o ElevenLabs estiver ativo (vira False se ele falhar)."""
        return self._elevenlabs is not None

    # ----------------------------------------------------------- eventos do Gemini
    def on_model_audio(self, data: bytes) -> None:
        """Audio nativo do Gemini: toca direto ou guarda como reserva."""
        if self.uses_elevenlabs:
            self._reserve.setdefault(self._turn, []).append(data)
        else:
            self._audio_queue.put_nowait(data)

    def on_model_text(self, text: str) -> None:
        """Texto da fala do Gemini: vira frases para o ElevenLabs."""
        if not self.uses_elevenlabs:
            return
        self._buffer += text
        first_piece = self._turn not in self._started_turns
        sentences, self._buffer = split_sentences(self._buffer, first_piece=first_piece)
        if sentences:
            self._started_turns.add(self._turn)
        for sentence in sentences:
            self._sentences.put_nowait(_Sentence(self._epoch, self._turn, sentence))

    def on_turn_complete(self) -> None:
        """Fim da resposta: fala o que sobrou e fecha o turno."""
        if self.uses_elevenlabs:
            rest, self._buffer = self._buffer.strip(), ""
            if rest:
                self._sentences.put_nowait(_Sentence(self._epoch, self._turn, rest))
            self._sentences.put_nowait(_Sentence(self._epoch, self._turn, None))
        self._turn += 1

    def on_interrupted(self) -> None:
        """O senhor falou por cima (ou a conexao caiu): descarta tudo o que estava pendente."""
        self._epoch += 1
        self._buffer = ""
        self._reserve.clear()
        self._drop_pending()

    def _drop_pending(self) -> None:
        """Esvazia as filas internas e cancela pedidos ao ElevenLabs em andamento."""
        for pending in (self._sentences, self._ordered):
            while not pending.empty():
                pending.get_nowait()
        for task in list(self._fetches):
            task.cancel()

    # ------------------------------------------------------------------- execucao
    async def run(self) -> None:
        """Pede cada frase ao ElevenLabs assim que chega e toca na ordem (sem pausas)."""
        forwarder = asyncio.create_task(self._forward())
        try:
            while True:
                item = await self._sentences.get()
                if item.epoch != self._epoch:
                    continue  # frase de antes de uma interrupcao
                if item.text is None or self._elevenlabs is None:
                    self._ordered.put_nowait((item, None))
                    continue
                chunks: asyncio.Queue[object] = asyncio.Queue()
                task = asyncio.create_task(self._fetch(self._elevenlabs, item.text, chunks))
                self._fetches.add(task)
                task.add_done_callback(self._fetches.discard)
                # cancelada antes de comecar, a corrotina nem roda o ``finally`` do _fetch:
                # este callback garante o _END mesmo assim (um _END a mais e inofensivo).
                task.add_done_callback(_fecha_fila(chunks))
                self._ordered.put_nowait((item, chunks))
        finally:
            forwarder.cancel()
            for task in list(self._fetches):
                task.cancel()

    @staticmethod
    async def _fetch(voice: ElevenLabsVoice, text: str, chunks: asyncio.Queue[object]) -> None:
        """Baixa o audio de uma frase para a fila dela (ou a excecao, se falhar).

        A fila SEMPRE termina com ``_END`` (tambem quando a tarefa e cancelada por uma
        interrupcao): sem isso o ``_forward`` ficaria esperando para sempre e o Jarvis mudo.
        """
        try:
            async for chunk in voice.stream(text):
                chunks.put_nowait(chunk)
        except asyncio.CancelledError:
            raise
        except ElevenLabsError as error:
            chunks.put_nowait(error)
        except Exception as error:  # noqa: BLE001 - erro inesperado: cai para a voz do Gemini
            logger.exception("erro inesperado no ElevenLabs")
            chunks.put_nowait(ElevenLabsError(f"erro inesperado: {error!r}"))
        finally:
            chunks.put_nowait(_END)

    async def _forward(self) -> None:
        """Entrega o audio das frases ao alto-falante, uma frase de cada vez, na ordem."""
        while True:
            item, chunks = await self._ordered.get()
            if item.epoch != self._epoch:
                continue
            if item.text is None:  # fim do turno
                self._reserve.pop(item.turn, None)
                self._spoken_turns.discard(item.turn)
                self._started_turns.discard(item.turn)
                continue
            if chunks is None:
                continue
            while True:
                chunk = await chunks.get()
                if chunk is _END or item.epoch != self._epoch:
                    break
                if isinstance(chunk, ElevenLabsError):
                    await self._fall_back(item, chunk)
                    break
                assert isinstance(chunk, bytes)
                self._audio_queue.put_nowait(chunk)
                self._spoken_turns.add(item.turn)

    async def _fall_back(self, item: _Sentence, error: Exception) -> None:
        """Desliga o ElevenLabs nesta sessao e toca o audio reserva do Gemini."""
        logger.error("ElevenLabs falhou, usando a voz do Gemini: %s", error)
        voice, self._elevenlabs = self._elevenlabs, None
        if not self._avisou_falha:
            self._avisou_falha = True
            try:
                self._observer.on_transcript("sistema", FALLBACK_NOTICE)
            except Exception:  # noqa: BLE001 - a interface nunca derruba a voz
                logger.debug("observador falhou no aviso do ElevenLabs", exc_info=True)
            _print_seguro(f"(Jarvis: {FALLBACK_NOTICE})")
            self._tocar_aviso_gravado()
        if item.turn not in self._spoken_turns:  # nada foi falado ainda: toca a reserva
            for data in self._reserve.pop(item.turn, []):
                self._audio_queue.put_nowait(data)
        self._reserve.clear()
        self._drop_pending()
        if voice is not None:
            try:
                await voice.close()
            except Exception:  # noqa: BLE001 - fechar nunca derruba a voz do Google
                logger.debug("falha ao fechar o ElevenLabs", exc_info=True)

    def _tocar_aviso_gravado(self) -> None:
        """Poe o aviso gravado na fila do alto-falante (antes da reserva). Sem arquivo: nada."""
        if self._aviso_elevenlabs is None:
            return
        try:
            pcm = self._aviso_elevenlabs()
        except Exception:  # noqa: BLE001 - aviso nunca derruba a voz
            logger.warning("nao consegui carregar o aviso do ElevenLabs", exc_info=True)
            return
        if not pcm:
            logger.warning("aviso do ElevenLabs sem audio gravado: so texto na tela")
            return
        for inicio in range(0, len(pcm), AVISO_PEDACO_BYTES):
            self._audio_queue.put_nowait(pcm[inicio : inicio + AVISO_PEDACO_BYTES])

    async def close(self) -> None:
        """Fecha a conexao com o ElevenLabs, se houver."""
        if self._elevenlabs is not None:
            try:
                await self._elevenlabs.close()
            except Exception:  # noqa: BLE001 - fechar nunca quebra o encerramento
                logger.debug("falha ao fechar o ElevenLabs", exc_info=True)
