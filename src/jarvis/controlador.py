"""Controlador do assistente de voz: inicia, para e reinicia sem travar a janela.

O assistente (``LiveAssistant``) roda numa thread com o PROPRIO loop asyncio. A janela (ou a
API do JavaScript) chama ``iniciar``/``parar``/``reiniciar`` de qualquer thread; parar cancela
a tarefa do assistente dentro do loop dele, o que fecha microfone, alto-falante e a conexao
com o Google do jeito normal (os blocos ``finally`` do assistente).

Se o Google recusar a chave ao conectar (``ChaveInvalidaError``), o controlador nao tenta de
novo: avisa o observador com ``on_aviso_chave(mensagem)`` (a janela mostra o botao
"Atualizar chave").
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from jarvis.errors import ChaveInvalidaError, ConfigError

if TYPE_CHECKING:
    from jarvis.config import Settings

logger = logging.getLogger(__name__)

MSG_CHAVE_PAROU = (
    'A chave do Google parou de funcionar. Clique em "Atualizar chave" e cole uma chave nova.'
)
MSG_FALHA = "Senhor, algo deu errado e precisei parar. Os detalhes ficaram no log."
ESPERA_PARAR_S = 5.0


class Assistente(Protocol):
    """O que o controlador precisa do assistente: um ``run()`` assincrono."""

    def run(self) -> Coroutine[Any, Any, None]: ...


FabricaAssistente = Callable[["Settings", Any], Assistente]


def _fabrica_padrao(settings: Settings, observer: Any) -> Assistente:
    from jarvis.assistants.live_assistant import LiveAssistant
    from jarvis.tools import ToolRegistry

    return LiveAssistant(settings, ToolRegistry(settings), observer=observer)


@dataclass
class _Execucao:
    """Uma rodada do assistente (cada reinicio cria outra)."""

    thread: threading.Thread | None = None
    loop: asyncio.AbstractEventLoop | None = None
    tarefa: asyncio.Task[None] | None = None
    parar_pedido: bool = False
    pronto: threading.Event = field(default_factory=threading.Event)


class Controlador:
    """Liga e desliga o assistente de voz em segundo plano."""

    def __init__(
        self,
        observer: Any,
        carregar_settings: Callable[[], Settings],
        fabrica: FabricaAssistente | None = None,
    ) -> None:
        """Cria o controlador.

        Args:
            observer: quem mostra o estado (a ``OrbWindow``); recebe ``on_state``,
                ``on_transcript`` e, se tiver, ``on_aviso_chave``.
            carregar_settings: le as configuracoes atuais (chamado a cada inicio, para pegar
                a chave/voz que acabaram de ser salvas).
            fabrica: cria o assistente a partir das configuracoes (testes passam um falso).
        """
        self._observer = observer
        self._carregar = carregar_settings
        self._fabrica = fabrica or _fabrica_padrao
        # _comando: um comando por vez (iniciar/parar/reiniciar). _estado: trava curta, usada
        # tambem pela thread do assistente (nunca fica presa esperando outra thread).
        self._comando = threading.Lock()
        self._estado = threading.Lock()
        self._atual: _Execucao | None = None

    @property
    def rodando(self) -> bool:
        """True enquanto a thread do assistente estiver viva."""
        atual = self._atual
        return atual is not None and atual.thread is not None and atual.thread.is_alive()

    # ------------------------------------------------------------------ comandos
    def iniciar(self) -> bool:
        """Inicia o assistente se ainda nao estiver rodando.

        Returns:
            True se esta rodando (ja estava ou acabou de iniciar); False sem chave ou se as
            configuracoes nao puderam ser lidas.
        """
        with self._comando:
            return self._iniciar()

    def parar(self, espera_s: float = ESPERA_PARAR_S) -> bool:
        """Para o assistente (cancela a tarefa no loop dele) e espera a thread terminar.

        Returns:
            True se parou (ou nao estava rodando); False se a thread nao terminou a tempo.
        """
        with self._comando:
            return self._parar(espera_s)

    def reiniciar(self) -> bool:
        """Para e inicia de novo com as configuracoes atuais (voz, chave, ElevenLabs)."""
        with self._comando:
            self._parar(ESPERA_PARAR_S)
            return self._iniciar()

    def _iniciar(self) -> bool:
        with self._estado:
            if self.rodando:
                return True
            try:
                settings = self._carregar()
            except ConfigError as erro:
                logger.warning("nao iniciei o assistente: %s", erro)
                return False
            if not settings.api_key:
                logger.info("assistente nao iniciado: falta a chave do Google")
                return False
            execucao = _Execucao()
            execucao.thread = threading.Thread(
                target=self._rodar,
                args=(execucao, settings),
                name="jarvis-assistente",
                daemon=True,
            )
            self._atual = execucao
            execucao.thread.start()
            logger.info("assistente iniciado")
            return True

    def _parar(self, espera_s: float) -> bool:
        with self._estado:
            execucao, self._atual = self._atual, None
            if execucao is None:
                return True
            execucao.parar_pedido = True
            loop, tarefa = execucao.loop, execucao.tarefa
            if loop is not None and tarefa is not None:
                try:
                    loop.call_soon_threadsafe(tarefa.cancel)
                except RuntimeError:  # loop ja fechado
                    pass
        thread = execucao.thread
        if thread is None or thread is threading.current_thread():
            return True
        thread.join(espera_s)
        parou = not thread.is_alive()
        if not parou:
            logger.warning("o assistente demorou para parar")
        else:
            logger.info("assistente parado")
        return parou

    # ------------------------------------------------------------------ thread
    def _rodar(self, execucao: _Execucao, settings: Settings) -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            assistente = self._fabrica(settings, self._observer)
            tarefa = loop.create_task(assistente.run())
            with self._estado:
                execucao.loop, execucao.tarefa = loop, tarefa
                if execucao.parar_pedido:
                    tarefa.cancel()
            execucao.pronto.set()
            loop.run_until_complete(tarefa)
        except asyncio.CancelledError:
            pass  # parado de proposito (parar/reiniciar)
        except ChaveInvalidaError:
            logger.error("o Google recusou a chave: assistente parado ate trocar a chave")
            self._avisar_chave()
        except ConfigError as erro:
            logger.error("assistente parou por configuracao: %s", erro)
            self._avisar("offline", str(erro))
        except Exception:  # noqa: BLE001 - mostra na janela em vez de sumir calado
            logger.exception("o assistente parou")
            self._avisar("offline", MSG_FALHA)
        finally:
            execucao.pronto.set()
            _fechar_loop(loop)

    def _avisar(self, estado: str, mensagem: str) -> None:
        for metodo, argumentos in (
            ("on_state", (estado,)),
            ("on_transcript", ("sistema", mensagem)),
        ):
            _chamar(self._observer, metodo, *argumentos)

    def _avisar_chave(self) -> None:
        _chamar(self._observer, "on_state", "offline")
        if getattr(self._observer, "on_aviso_chave", None) is not None:
            _chamar(self._observer, "on_aviso_chave", MSG_CHAVE_PAROU)
        else:
            _chamar(self._observer, "on_transcript", "sistema", MSG_CHAVE_PAROU)


def _chamar(observer: Any, metodo: str, *argumentos: Any) -> None:
    funcao = getattr(observer, metodo, None)
    if funcao is None:
        return
    try:
        funcao(*argumentos)
    except Exception:  # noqa: BLE001 - a janela nunca derruba o controlador
        logger.debug("observador falhou em %s", metodo, exc_info=True)


def _fechar_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Cancela o que sobrou, espera as threads do to_thread e fecha o loop."""
    try:
        pendentes = [tarefa for tarefa in asyncio.all_tasks(loop) if not tarefa.done()]
        for tarefa in pendentes:
            tarefa.cancel()
        if pendentes:
            loop.run_until_complete(asyncio.gather(*pendentes, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor(timeout=3))
    except Exception:  # noqa: BLE001
        logger.debug("falha ao fechar o loop do assistente", exc_info=True)
    finally:
        asyncio.set_event_loop(None)
        loop.close()
