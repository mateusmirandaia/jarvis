"""Entrada e saida de audio (microfone e alto-falante) via PyAudio.

O ``pyaudio`` so e importado quando ``AudioIO`` e criado, para que o resto do pacote
(modo texto, testes) funcione mesmo sem ele instalado.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from jarvis.errors import ConfigError

logger = logging.getLogger(__name__)

CHANNELS = 1
CHUNK = 512  # chunk menor = menos atraso
MIC_RATE = 16_000
SPEAKER_RATE = 24_000
MIC_MIME_TYPE = f"audio/pcm;rate={MIC_RATE}"
# Fechar espera a leitura/escrita em andamento no maximo isso. Um driver travado (microfone
# arrancado no meio da leitura) nao pode congelar o laco do assistente nem o "parar".
CLOSE_WAIT_S = 1.0


class AudioIO:
    """Encapsula o PyAudio: microfone 16 kHz e saida 24 kHz, PCM 16 bits mono."""

    def __init__(self) -> None:
        try:
            import pyaudio
        except ImportError as error:  # pragma: no cover - depende do ambiente
            raise ConfigError(
                "O modo voz precisa do PyAudio. Instale com: python -m pip install pyaudio "
                "(ou use jarvis --modo texto)."
            ) from error
        self._pyaudio = pyaudio
        self._pa = pyaudio.PyAudio()
        self._mic: Any | None = None
        self._speaker: Any | None = None
        # Fechar um stream enquanto outra thread le/escreve nele pode derrubar o PortAudio.
        # Com as travas, fechar espera a leitura/escrita em andamento (no maximo ~40 ms).
        self._mic_lock = threading.Lock()
        self._speaker_lock = threading.Lock()

    # ----------------------------------------------------------------- microfone
    def open_mic(self) -> None:
        """Abre o microfone (16 kHz, mono, PCM16); fecha antes um que tenha ficado aberto."""
        self.close_mic()
        stream = self._pa.open(
            format=self._pyaudio.paInt16,
            channels=CHANNELS,
            rate=MIC_RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        with self._mic_lock:
            self._mic = stream

    def read_mic(self) -> bytes:
        """Le um bloco de CHUNK amostras do microfone (bloqueante)."""
        with self._mic_lock:
            if self._mic is None:
                raise RuntimeError("microfone nao foi aberto")
            return self._mic.read(CHUNK, exception_on_overflow=False)

    def close_mic(self) -> None:
        """Fecha o microfone, se aberto (espera a leitura atual no maximo ``CLOSE_WAIT_S``)."""
        if not self._mic_lock.acquire(timeout=CLOSE_WAIT_S):
            logger.warning("microfone preso numa leitura: deixei de fechar para nao travar")
            return
        try:
            if self._mic is not None:
                self._close_stream(self._mic)
                self._mic = None
        finally:
            self._mic_lock.release()

    # -------------------------------------------------------------- alto-falante
    def open_speaker(self) -> None:
        """Abre a saida de audio (24 kHz, mono, PCM16); fecha antes uma que tenha ficado aberta."""
        self.close_speaker()
        stream = self._pa.open(
            format=self._pyaudio.paInt16,
            channels=CHANNELS,
            rate=SPEAKER_RATE,
            output=True,
        )
        with self._speaker_lock:
            self._speaker = stream

    def write_speaker(self, data: bytes) -> None:
        """Toca um bloco de audio PCM16 (bloqueante)."""
        with self._speaker_lock:
            if self._speaker is None:
                raise RuntimeError("alto-falante nao foi aberto")
            self._speaker.write(data)

    def close_speaker(self) -> None:
        """Fecha a saida de audio, se aberta (espera a escrita atual no maximo ``CLOSE_WAIT_S``)."""
        if not self._speaker_lock.acquire(timeout=CLOSE_WAIT_S):
            logger.warning("alto-falante preso numa escrita: deixei de fechar para nao travar")
            return
        try:
            if self._speaker is not None:
                self._close_stream(self._speaker)
                self._speaker = None
        finally:
            self._speaker_lock.release()

    # --------------------------------------------------------------------- geral
    def close(self) -> None:
        """Fecha tudo e libera o PyAudio."""
        self.close_mic()
        self.close_speaker()
        try:
            self._pa.terminate()
        except Exception:  # noqa: BLE001 - fechar nunca deve quebrar o encerramento
            logger.exception("falha ao encerrar o PyAudio")

    @staticmethod
    def _close_stream(stream: Any) -> None:
        try:
            stream.close()
        except Exception:  # noqa: BLE001
            logger.exception("falha ao fechar stream de audio")
