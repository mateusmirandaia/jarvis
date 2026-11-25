"""Teste do microfone da janela de configuracao e reproducao curta de audio.

``TesteMicrofone`` abre o microfone numa thread propria e avisa o volume (0 a 1) umas 20
vezes por segundo, para a barra da tela "Microfone" reagir a voz. So roda durante a
configuracao, antes de o assistente de voz abrir o microfone dele.

O ``pyaudio`` so e importado quando o teste comeca (os testes passam uma fabrica falsa).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from jarvis.assistants.observer import pcm_level

logger = logging.getLogger(__name__)

TAXA = 16_000
BLOCO = 800  # 50 ms a 16 kHz: ~20 avisos por segundo
LIMITE_S = 300.0  # para sozinho depois de 5 minutos (se a janela esquecer de parar)
GANHO = 1.4  # a barra sobe com voz normal; pcm_level ja satura em 1

MSG_SEM_PYAUDIO = (
    "Não encontrei o suporte a microfone neste computador. Reinstale o Jarvis e tente de novo."
)
MSG_SEM_MICROFONE = (
    "Não encontrei um microfone. Confira se ele está conectado e se o Windows permite o uso "
    "(Configurações > Privacidade > Microfone)."
)
MSG_EM_USO = "O Jarvis já está usando o microfone. O teste só funciona durante a configuração."


def _pyaudio_padrao() -> Any:
    import pyaudio

    return pyaudio


class TesteMicrofone:
    """Mede o volume do microfone numa thread e entrega a ``ao_nivel(nivel)``."""

    def __init__(
        self,
        ao_nivel: Callable[[float], None],
        modulo_pyaudio: Callable[[], Any] | None = None,
        limite_s: float = LIMITE_S,
    ) -> None:
        self._ao_nivel = ao_nivel
        self._modulo = modulo_pyaudio or _pyaudio_padrao
        self._limite_s = limite_s
        self._trava = threading.Lock()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def ativo(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def iniciar(self) -> tuple[bool, str]:
        """Abre o microfone e comeca a medir. Ja ativo = nada muda.

        Returns:
            (True, "") se esta medindo; (False, mensagem simples) se nao deu.
        """
        with self._trava:
            if self.ativo:
                return True, ""
            try:
                pyaudio = self._modulo()
            except ImportError:
                logger.warning("pyaudio ausente: teste do microfone indisponivel")
                return False, MSG_SEM_PYAUDIO
            try:
                pa = pyaudio.PyAudio()
            except Exception:  # noqa: BLE001 - PortAudio sem dispositivos
                logger.warning("nao consegui iniciar o PyAudio", exc_info=True)
                return False, MSG_SEM_MICROFONE
            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=TAXA,
                    input=True,
                    frames_per_buffer=BLOCO,
                )
            except Exception:  # noqa: BLE001 - sem microfone ou bloqueado pelo Windows
                logger.warning("nao consegui abrir o microfone para o teste", exc_info=True)
                _fechar(pa, None)
                return False, MSG_SEM_MICROFONE
            # Um sinal de parada por rodada: se a rodada anterior ainda estiver presa num read()
            # lento, ela continua vendo o SEU sinal (ja ligado) e termina, em vez de ficar viva.
            self._parar = threading.Event()
            self._thread = threading.Thread(
                target=self._medir,
                args=(pa, stream, self._parar),
                name="jarvis-teste-mic",
                daemon=True,
            )
            self._thread.start()
            logger.info("teste do microfone iniciado")
            return True, ""

    def parar(self, espera_s: float = 1.0) -> bool:
        """Para de medir e fecha o microfone. Sempre devolve True (parado ou ja estava)."""
        with self._trava:
            self._parar.set()
            thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(espera_s)
        return True

    def _medir(self, pa: Any, stream: Any, parar: threading.Event) -> None:
        inicio = time.monotonic()
        try:
            while not parar.is_set():
                if time.monotonic() - inicio > self._limite_s:
                    logger.info("teste do microfone parou sozinho (tempo maximo)")
                    break
                try:
                    dados = stream.read(BLOCO, exception_on_overflow=False)
                except Exception:  # noqa: BLE001 - microfone desconectado no meio
                    logger.warning("o microfone parou de responder", exc_info=True)
                    break
                self._avisar(min(1.0, pcm_level(dados) * GANHO))
        finally:
            self._avisar(0.0)
            _fechar(pa, stream)
            logger.info("teste do microfone encerrado")

    def _avisar(self, nivel: float) -> None:
        try:
            self._ao_nivel(nivel)
        except Exception:  # noqa: BLE001 - a janela nunca derruba o teste
            logger.debug("falha ao enviar o nivel do microfone", exc_info=True)


def _fechar(pa: Any, stream: Any | None) -> None:
    for acao in (
        (lambda: stream.stop_stream()) if stream is not None else None,
        (lambda: stream.close()) if stream is not None else None,
        pa.terminate,
    ):
        if acao is None:
            continue
        try:
            acao()
        except Exception:  # noqa: BLE001
            logger.debug("falha ao fechar o audio do teste", exc_info=True)


def tocar_pcm(dados: bytes) -> None:
    """Toca audio PCM16 mono 24 kHz pelo alto-falante padrao (bloqueia ate terminar).

    Usa o mesmo ``AudioIO`` do assistente de voz.
    """
    from jarvis.assistants.audio import AudioIO

    audio = AudioIO()
    try:
        audio.open_speaker()
        audio.write_speaker(dados)
    finally:
        audio.close()
