"""Jarvis por voz em tempo real: Gemini Live (ouvido + cerebro + boca numa conexao so).

Use fone de ouvido de preferencia. Ctrl+C encerra.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from google import genai
from google.genai import types

from jarvis import avisos
from jarvis.assistants.audio import MIC_MIME_TYPE, AudioIO
from jarvis.assistants.elevenlabs_voice import ElevenLabsVoice
from jarvis.assistants.observer import AssistantObserver, NullObserver, pcm_level
from jarvis.assistants.voice_output import VoiceOutput
from jarvis.errors import (
    ChaveInvalidaError,
    SemRespostaError,
    dispositivo_do_erro,
    erro_de_autenticacao,
    friendly_message,
    marcar_dispositivo,
    tipo_de_queda,
)
from jarvis.persona import build_system_prompt

if TYPE_CHECKING:
    from jarvis.config import Settings
    from jarvis.tools import ToolRegistry

logger = logging.getLogger(__name__)

MAX_BACKOFF_S = 15
# Sessao que durou menos que isso nao conta como "voltou": a espera entre tentativas continua
# crescendo (conectar e cair na hora, sem parar, nao pode virar um laco de 2 em 2 s).
SESSAO_ESTAVEL_S = 30.0
# Um pedido do modelo com acoes demais de uma vez (texto injetado num PDF pode pedir 100
# sites ou 100 e-mails) so executa as primeiras; as outras recebem esta resposta.
MAX_ACOES_POR_PEDIDO = 8
MSG_ACOES_DEMAIS = (
    "Ação não executada: foram pedidas ações demais de uma vez. Faça uma de cada vez e só o "
    "que o senhor pediu."
)
TERMINAL_MAX_CHARS = 300  # o terminal mostra so o comeco da acao (read_file traz 20 mil)
ECHO_GAP_S = 0.2  # folga apos a fala para o eco morrer antes de reabrir o microfone
PLAYBACK_SLICE_BYTES = 2_048  # ~42 ms de audio a 24 kHz: o orb pulsa no ritmo da fala
MIC_LEVEL_FACTOR = 0.6  # ao ouvir, o orb reage ao microfone de forma mais discreta
INVALID_KEY_MESSAGE = (
    "O Google recusou a chave (GEMINI_API_KEY): ela está errada, foi apagada ou bloqueada. "
    "Abra o Jarvis pela janela e troque a chave na engrenagem (aba Chave do Google)."
)
CONNECT_TIMEOUT_S = 15.0  # conectar ao Google nunca espera mais que isso
WATCHDOG_STEP_S = 0.25  # de quanto em quanto tempo o vigia confere o silencio do modelo
AVISO_FOLGA_S = 2.0  # tempo extra, alem da duracao do aviso, antes de desistir de toca-lo
DISCONNECT_NOTICE = "Senhor, perdi a conexão. Tento de novo em {wait} s…"
QUOTA_NOTICE = (
    "Senhor, o Google pediu para esperar um pouco (limite de uso). Tento de novo em {wait} s…"
)
MIC_NOTICE = "Senhor, perdi o acesso ao microfone. Tento de novo em {wait} s…"
SPEAKER_NOTICE = "Senhor, tive um problema com o som. Tento de novo em {wait} s…"
RECONNECT_NOTICE = (
    "(Aviso do sistema: a conexão caiu e voltou. Diga ao senhor em uma frase curta que "
    "teve um problema de conexão, mas já está de volta.)"
)


class LiveAssistant:
    """Conversa por voz com o Gemini Live, executando ferramentas da lista fechada."""

    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry,
        observer: AssistantObserver | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.observer: AssistantObserver = observer or NullObserver()
        # O Live (preview) fica na API v1beta; a SDK 3.x usa v1 por padrao e da HTTP 404.
        self.client = genai.Client(
            api_key=settings.api_key,
            http_options=types.HttpOptions(api_version="v1beta"),
        )
        self.config = self._build_config()
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.voice = VoiceOutput(
            self.audio_queue,
            self.observer,
            self._build_elevenlabs(),
            aviso_elevenlabs=lambda: avisos.pcm_aviso(
                "elevenlabs", avisos.VOZ_RESERVA, self.avisos_dir
            ),
        )
        self.speaking = False  # enquanto ele fala, o microfone nao envia (evita eco)
        self.failures = 0  # quedas seguidas da conexao
        self._conectou_em: float | None = None  # relogio da ultima conexao (sessao estavel?)
        self._tool_tasks: set[asyncio.Task[None]] = set()  # acoes rodando em segundo plano
        self._heard_at: float | None = None  # ultima vez que ouviu o senhor (para medir atraso)
        self._answer_logged = False
        self.audio: AudioIO | None = None
        # Tempo limite de resposta: hora (relogio monotonic) em que o silencio do modelo vira
        # queda. None = nao esta esperando resposta. ``_turn_answered``: o modelo ja mandou
        # algo neste turno (transcricao atrasada do senhor nao arma o prazo de novo).
        self._clock = time.monotonic
        self._reply_deadline: float | None = None
        self._turn_answered = False
        self._internet_notice = avisos.LimiteDeAviso(
            avisos.INTERVALO_INTERNET_S, lambda: self._clock()
        )
        self.avisos_dir: Path | None = None  # None = pasta do pacote (testes trocam)

    # -------------------------------------------------------------- configuracao
    def _build_elevenlabs(self) -> ElevenLabsVoice | None:
        """Cria a voz do ElevenLabs se a chave e a voz estiverem no .env."""
        if not self.settings.uses_elevenlabs:
            return None
        return ElevenLabsVoice(
            self.settings.elevenlabs_api_key,
            self.settings.elevenlabs_voice_id,
            self.settings.elevenlabs_model,
        )

    @property
    def voice_label(self) -> str:
        """Descricao curta da voz em uso (para o terminal e o log)."""
        if self.voice.uses_elevenlabs:
            return f"ElevenLabs {self.settings.elevenlabs_model}"
        return f"Google {self.settings.voice}"

    def _build_config(self) -> types.LiveConnectConfig:
        """Monta a configuracao da sessao Live (audio, persona, ferramentas, voz)."""
        system_prompt = build_system_prompt(
            self.registry.guard.user_folders(), self.registry.app_names, self.settings.user_name
        )
        declarations = [
            types.FunctionDeclaration.from_callable(client=self.client, callable=func)
            for func in self.registry.functions
        ]
        for declaration in declarations:
            # Assincrono: enquanto a acao roda, ele continua falando ("Um instante, senhor...").
            declaration.behavior = types.Behavior.NON_BLOCKING
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=system_prompt,
            tools=[types.Tool(function_declarations=declarations)],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.settings.voice)
                )
            ),
            # Fim da fala: sensibilidade alta + silencio curto = ele responde mais rapido.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                    silence_duration_ms=self.settings.silence_ms,
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # conversa longa sem estourar o contexto
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
        )

    # ------------------------------------------------------------------ execucao
    async def run(self) -> None:
        """Loop principal: abre a sessao e reconecta sozinho com backoff se cair.

        Raises:
            ChaveInvalidaError: o Google recusou a chave. Reconectar nao resolve, entao o
                loop para e quem chamou avisa a pessoa (a janela mostra "Atualizar chave").
        """
        self.audio = AudioIO()
        try:
            while True:
                try:
                    await self._session()
                except Exception as error:  # noqa: BLE001 - inclui ExceptionGroup do TaskGroup
                    if erro_de_autenticacao(error):
                        logger.error("o Google recusou a chave; nao vou reconectar")
                        self._notify_optional("on_state", "offline")
                        raise ChaveInvalidaError(INVALID_KEY_MESSAGE) from None
                    try:
                        await self._handle_disconnect(error)
                    except Exception:  # noqa: BLE001 - tratar a queda nunca para o laco
                        logger.exception("falha ao tratar a queda; tento de novo")
                        await asyncio.sleep(1)
        finally:
            try:
                self.audio.close()
            except Exception:  # noqa: BLE001 - fechar nunca quebra o encerramento
                logger.exception("falha ao fechar o audio")
            await self.voice.close()

    async def _handle_disconnect(self, error: BaseException) -> None:
        """Registra a queda, avisa (texto e, se for internet, o aviso gravado) e espera o backoff.

        O aviso de internet toca no maximo 1 vez a cada ``avisos.INTERVALO_INTERNET_S``; o
        tempo tocando conta como parte da espera.
        """
        kind = tipo_de_queda(error)
        cause = getattr(error, "exceptions", [error])[0]
        logger.error("sessao caiu (%s): %r", kind, cause)
        conectou, self._conectou_em = self._conectou_em, None
        if conectou is not None and self._clock() - conectou >= SESSAO_ESTAVEL_S:
            self.failures = 0  # a sessao estava boa: recomeca a espera curta
        self.failures += 1
        wait = min(2**self.failures, MAX_BACKOFF_S)
        self._reply_deadline = None
        self._notify_optional("on_state", "offline")
        self._reset_playback()
        self.voice.on_interrupted()
        spent = 0.0
        if kind == "rede":
            spent = await self._warn_internet()
        notice = self._disconnect_notice(kind, error).format(wait=wait)
        _print_safe(f"(Jarvis: {notice})")
        self._notify_optional("on_transcript", "sistema", notice)
        await asyncio.sleep(max(0.0, wait - spent))

    @staticmethod
    def _disconnect_notice(kind: str, error: BaseException) -> str:
        if kind == "cota":
            return QUOTA_NOTICE
        if kind == "audio":
            return MIC_NOTICE if dispositivo_do_erro(error) == "microfone" else SPEAKER_NOTICE
        return DISCONNECT_NOTICE

    async def _warn_internet(self) -> float:
        """Mostra e toca o aviso de internet (se ja pode de novo). Devolve os segundos gastos."""
        if not self._internet_notice.pode():
            logger.info("aviso de internet ja tocou ha pouco: so reconecto")
            return 0.0
        _print_safe(f"(Jarvis: {avisos.TEXTO_INTERNET})")
        self._notify_optional("on_transcript", "sistema", avisos.TEXTO_INTERNET)
        pcm = avisos.pcm_aviso("internet", self.settings.voice, self.avisos_dir)
        if pcm is None or self.audio is None:
            return 0.0
        started = self._clock()
        stop = threading.Event()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._play_blocking, pcm, stop),
                timeout=avisos.duracao_s(pcm) + AVISO_FOLGA_S,
            )
        except TimeoutError:
            logger.warning("o alto-falante nao tocou o aviso a tempo; sigo reconectando")
        except Exception:  # noqa: BLE001 - sem som: o texto ja esta na tela
            logger.warning("nao consegui tocar o aviso de internet", exc_info=True)
        finally:
            stop.set()  # se a thread ainda estiver tocando, para na proxima fatia
            self._notify_optional("on_level", 0.0)
        return max(0.0, self._clock() - started)

    def _play_blocking(self, pcm: bytes, stop: threading.Event) -> None:
        """Toca um audio inteiro direto no alto-falante (em thread; a sessao esta fora)."""
        audio = self.audio
        if audio is None:
            return
        audio.open_speaker()
        try:
            for start in range(0, len(pcm), PLAYBACK_SLICE_BYTES):
                if stop.is_set():
                    break
                piece = pcm[start : start + PLAYBACK_SLICE_BYTES]
                self._notify_optional("on_level", pcm_level(piece))
                audio.write_speaker(piece)
        finally:
            # Desistimos de esperar (alto-falante preso): a sessao nova pode ja ter reaberto o
            # som; fechar agora tiraria o alto-falante dela. Quem reabre fecha o antigo.
            if not stop.is_set():
                audio.close_speaker()

    def _reset_playback(self) -> None:
        """Esvazia a fila de audio e libera o microfone."""
        self.speaking = False
        self._clear_queue()
        self._notify_optional("on_level", 0.0)

    def _clear_queue(self) -> None:
        while not self.audio_queue.empty():
            self.audio_queue.get_nowait()

    async def _session(self) -> None:
        """Uma sessao Live: conecta (com tempo maximo), avisa se voltou de queda e roda tudo."""
        self._reply_deadline, self._turn_answered = None, False
        async with contextlib.AsyncExitStack() as stack:
            session = await asyncio.wait_for(
                stack.enter_async_context(
                    self.client.aio.live.connect(model=self.settings.live_model, config=self.config)
                ),
                timeout=CONNECT_TIMEOUT_S,
            )
            if self.failures:  # voltou de uma queda: ele mesmo avisa, em voz
                await session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part(text=RECONNECT_NOTICE)]),
                    turn_complete=True,
                )
                self._arm_reply_deadline()  # texto enviado: espera a resposta dele
                logger.info("reconectado apos %d queda(s)", self.failures)
            else:
                _print_safe(
                    f"Jarvis ouvindo ({self.settings.live_model}, voz {self.voice_label}). "
                    "Fale! Ctrl+C para sair."
                )
                logger.info("sessao iniciada, voz: %s", self.voice_label)
            self._marcar_conectado()
            self._notify_optional("on_state", "listening")
            try:
                await self._run_tasks(session)
            finally:
                for task in list(self._tool_tasks):  # acoes da sessao que caiu
                    task.cancel()

    def _marcar_conectado(self) -> None:
        """Conectou. O contador de quedas so zera quando a sessao se firma (veja a queda)."""
        self._conectou_em = self._clock()

    async def _run_tasks(self, session: Any) -> None:
        """Roda ouvir, receber, falar e a voz em paralelo ate a sessao cair."""
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self._listen(session))
            tasks.create_task(self._receive(session))
            tasks.create_task(self._speak())
            tasks.create_task(self.voice.run())
            tasks.create_task(self._watch_reply())

    # ------------------------------------------------------- tempo limite de resposta
    def _arm_reply_deadline(self) -> None:
        """O senhor falou (ou mandamos texto): o modelo tem ``resposta_timeout_s`` para reagir."""
        self._reply_deadline = self._clock() + self.settings.resposta_timeout_s

    def _model_replied(self) -> None:
        """Chegou algo do modelo (audio, texto, acao, fim de turno): nao e silencio."""
        self._reply_deadline = None
        self._turn_answered = True

    def _tools_running(self) -> bool:
        return any(not task.done() for task in self._tool_tasks)

    async def _watch_reply(self) -> None:
        """Derruba a sessao (SemRespostaError) se o modelo ficar mudo depois da fala.

        Acao em andamento nao conta como silencio: enquanto ela roda, o prazo e empurrado.
        """
        step = max(0.01, min(WATCHDOG_STEP_S, self.settings.resposta_timeout_s / 4))
        while True:
            await asyncio.sleep(step)
            deadline = self._reply_deadline
            if deadline is None:
                continue
            now = self._clock()
            if self._tools_running():
                self._reply_deadline = now + self.settings.resposta_timeout_s
                continue
            if now >= deadline:
                logger.warning(
                    "o modelo nao respondeu em %.1f s: reconectando",
                    self.settings.resposta_timeout_s,
                )
                raise SemRespostaError("o modelo nao respondeu a tempo")

    # --------------------------------------------------------------------- tarefas
    async def _listen(self, session: Any) -> None:
        """Le o microfone e envia ao modelo, exceto enquanto o Jarvis fala (anti-eco)."""
        assert self.audio is not None
        await self._mic_call(self.audio.open_mic)
        try:
            while True:
                data = await self._mic_call(self.audio.read_mic)
                # Sem fone, enquanto ele fala o microfone manda SILENCIO no lugar da sua voz
                # (senao ele ouve a si mesmo). O fluxo nunca para: o detector de fala do
                # Gemini continua acompanhando e reconhece quando o senhor volta a falar.
                if self.settings.headphones or not self.speaking:
                    self._notify_optional("on_level", pcm_level(data) * MIC_LEVEL_FACTOR)
                else:
                    data = bytes(len(data))
                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type=MIC_MIME_TYPE)
                )
        finally:
            try:
                self.audio.close_mic()
            except Exception:  # noqa: BLE001 - fechar nunca esconde o erro de verdade
                logger.debug("falha ao fechar o microfone", exc_info=True)

    @staticmethod
    async def _mic_call(func: Any) -> Any:
        """Roda uma chamada do microfone numa thread; erro sai marcado como "microfone"."""
        try:
            return await asyncio.to_thread(func)
        except Exception as error:
            marcar_dispositivo(error, "microfone")
            raise

    async def _receive(self, session: Any) -> None:
        """Recebe audio, transcricoes e pedidos de ferramenta do modelo."""
        user_text, jarvis_text = "", ""
        while True:
            async for message in session.receive():
                # Cede a vez ao loop: sem isso, mensagens que chegam em rajada seguram a voz
                # (ElevenLabs) e o alto-falante ate o Gemini terminar a resposta inteira.
                await asyncio.sleep(0)
                content = message.server_content
                if content and content.input_transcription and content.input_transcription.text:
                    user_text += content.input_transcription.text
                    self._heard_at, self._answer_logged = time.monotonic(), False
                    if content.input_transcription.text.strip() and not self._turn_answered:
                        self._arm_reply_deadline()  # o senhor falou: conta o tempo de resposta
                if self._from_model(message):
                    self._model_replied()
                if message.data:
                    self.voice.on_model_audio(message.data)
                if message.tool_call:
                    self._notify_optional("on_state", "thinking")
                    # Nao espera a acao terminar: ele segue ouvindo e falando enquanto ela roda.
                    task = asyncio.create_task(self._handle_tool_call(session, message.tool_call))
                    self._tool_tasks.add(task)
                    task.add_done_callback(self._tool_tasks.discard)
                if not content:
                    continue
                if content.output_transcription and content.output_transcription.text:
                    jarvis_text += content.output_transcription.text
                    self.voice.on_model_text(content.output_transcription.text)
                if content.interrupted:  # o senhor falou por cima: para de tocar
                    logger.info(
                        "interrompido pelo senhor (ouvido ate agora: %r)", _curto(user_text)
                    )
                    self._turn_answered = False  # a fala nova dele espera uma resposta nova
                    self._clear_queue()
                    self.voice.on_interrupted()
                if content.turn_complete:
                    logger.info("turno completo (fila de audio: %d)", self.audio_queue.qsize())
                    if self._detalhado:
                        logger.info("voce disse: %r", _curto(user_text))
                        logger.info("jarvis disse: %r", _curto(jarvis_text))
                    self._turn_answered = False
                    self.voice.on_turn_complete()
                    self._print_turn(user_text, jarvis_text)
                    self._notify_turn(user_text, jarvis_text)
                    user_text, jarvis_text = "", ""
            # Uma sessao estranha que termina o receive() sem mensagem nao pode girar sem
            # ceder a vez (congelaria o loop inteiro: microfone, voz e janela).
            await asyncio.sleep(0)

    @staticmethod
    def _from_model(message: Any) -> bool:
        """True se a mensagem e uma reacao do modelo (nao so a transcricao do senhor)."""
        if getattr(message, "tool_call", None) or getattr(message, "tool_call_cancellation", None):
            return True
        content = getattr(message, "server_content", None)
        if content is None:
            return False
        return bool(
            content.model_turn
            or content.output_transcription
            or content.turn_complete
            or content.interrupted
            or content.generation_complete
        )

    async def _speak(self) -> None:
        """Toca o audio da fila; mantem o microfone mudo ate a folga do eco passar."""
        assert self.audio is not None
        await self._speaker_call(self.audio.open_speaker)
        try:
            while True:
                data = await self.audio_queue.get()
                if not self.speaking:
                    self.speaking = True
                    self._notify_optional("on_state", "speaking")
                    self._log_latency()
                await self._play(data)
                if self.audio_queue.empty():
                    await asyncio.sleep(ECHO_GAP_S)
                    self.speaking = not self.audio_queue.empty()
                    if not self.speaking:
                        logger.info("terminou de falar: microfone liberado")
                        self._notify_optional("on_level", 0.0)
                        self._notify_optional("on_state", "listening")
        finally:
            try:
                self.audio.close_speaker()
            except Exception:  # noqa: BLE001 - fechar nunca esconde o erro de verdade
                logger.debug("falha ao fechar o alto-falante", exc_info=True)

    @staticmethod
    async def _speaker_call(func: Any, *args: Any) -> Any:
        """Roda uma chamada do alto-falante numa thread; erro sai marcado como "alto-falante"."""
        try:
            return await asyncio.to_thread(func, *args)
        except Exception as error:
            marcar_dispositivo(error, "alto-falante")
            raise

    async def _play(self, data: bytes) -> None:
        """Toca um bloco em fatias pequenas, avisando o volume de cada fatia ao observador."""
        assert self.audio is not None
        for start in range(0, len(data), PLAYBACK_SLICE_BYTES):
            piece = data[start : start + PLAYBACK_SLICE_BYTES]
            self._notify_optional("on_level", pcm_level(piece))
            await self._speaker_call(self.audio.write_speaker, piece)

    # ---------------------------------------------------------------- ferramentas
    async def _handle_tool_call(self, session: Any, tool_call: types.LiveServerToolCall) -> None:
        """Executa cada acao pedida (em outra thread) e devolve o resultado ao modelo.

        Roda em segundo plano: o modelo ja disse "Um instante, senhor" e, quando o
        resultado chega (WHEN_IDLE), ele fala o resultado assim que terminar a frase atual.
        """
        responses: list[types.FunctionResponse] = []
        for indice, call in enumerate(tool_call.function_calls or []):
            name = call.name or ""
            if indice >= MAX_ACOES_POR_PEDIDO:
                logger.warning("acao %s ignorada: acoes demais no mesmo pedido", name)
                self._notify_tool(name, ok=False)
                result = MSG_ACOES_DEMAIS
            else:
                try:
                    result = await self._execute(name, call.args or {})
                except Exception as error:  # noqa: BLE001 - toda acao pedida recebe resposta
                    logger.exception("falha inesperada ao executar %s", name)
                    result = friendly_message(error)
            _print_safe(_linha_de_acao(name, call.args, result))
            responses.append(
                types.FunctionResponse(
                    id=call.id,
                    name=name,
                    response={"result": result},
                    scheduling=types.FunctionResponseScheduling.WHEN_IDLE,
                )
            )
        try:
            await session.send_tool_response(function_responses=responses)
        except Exception:  # noqa: BLE001 - sessao caiu no meio da acao: so registra
            logger.exception("nao consegui devolver o resultado da acao")

    async def _execute(self, name: str, args: dict[str, Any]) -> str:
        """Executa uma acao da lista fechada numa thread, com tempo maximo. Nunca trava.

        Depois de cada execucao avisa o observador (``on_tool``): ``ok`` e False quando a
        acao nao e permitida, estoura o tempo, levanta erro ou devolve um "ERRO:".
        """
        try:
            func = self.registry.get(name)
        except Exception:  # noqa: BLE001 - registro com problema = acao recusada
            logger.exception("falha ao procurar a acao %s", name)
            func = None
        if func is None:
            logger.warning("acao nao permitida pedida pelo modelo: %s", name)
            self._notify_tool(name, ok=False)
            return "Ação não permitida."
        inicio = time.monotonic()
        try:
            args = dict(args)
            if self._detalhado:
                logger.info("acao pedida: %s %s", name, _curto(repr(args), 200))
            result = await asyncio.wait_for(
                asyncio.to_thread(func, **args),
                timeout=self.registry.timeout_for(name, self.settings),
            )
        except TimeoutError:
            logger.error("acao %s passou do tempo maximo", name)
            self._notify_tool(name, ok=False)
            return friendly_message(TimeoutError())
        except Exception as error:  # noqa: BLE001 - erro vira frase simples para a IA
            logger.exception("acao %s falhou", name)
            self._notify_tool(name, ok=False)
            return friendly_message(error)
        # O safe_tool transforma excecao das ferramentas em texto "ERRO: ...".
        if self._detalhado:
            logger.info(
                "acao %s terminou em %.2f s: %r",
                name,
                time.monotonic() - inicio,
                _curto(str(result)),
            )
        self._notify_tool(name, ok=not str(result).startswith("ERRO:"))
        return result

    @property
    def _detalhado(self) -> bool:
        return bool(getattr(self.settings, "log_detalhado", False))

    # ------------------------------------------------------------------- terminal
    @staticmethod
    def _print_turn(user_text: str, jarvis_text: str) -> None:
        if user_text.strip():
            _print_safe(f"Você: {user_text.strip()}")
        if jarvis_text.strip():
            _print_safe(f"Jarvis: {jarvis_text.strip()}")

    def _log_latency(self) -> None:
        """Registra no log quanto tempo levou da sua fala ate a primeira palavra dele."""
        if self._heard_at is None or self._answer_logged:
            return
        self._answer_logged = True
        delay = time.monotonic() - self._heard_at
        logger.info("atraso ate a resposta: %.2f s (voz: %s)", delay, self.voice_label)
        self._notify_optional("on_latency", delay)

    # ------------------------------------------------------------------ observador
    def _notify_tool(self, name: str, ok: bool) -> None:
        """Avisa o observador que uma acao terminou (com ou sem sucesso)."""
        self._notify_optional("on_tool", name, ok)

    def _notify_optional(self, method: str, *args: Any) -> None:
        """Chama um metodo opcional do observador sem nunca derrubar o assistente.

        Observadores antigos podem nao ter ``on_tool``/``on_latency``: nesse caso nada
        acontece. Se o observador levantar erro, ele so vai para o log.
        """
        callback = getattr(self.observer, method, None)
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:  # noqa: BLE001 - a interface nunca pode derrubar o assistente
            logger.debug("observador falhou em %s", method, exc_info=True)

    def _notify_turn(self, user_text: str, jarvis_text: str) -> None:
        """Envia as falas do turno ao observador (ex.: legenda no orb)."""
        if user_text.strip():
            self._notify_optional("on_transcript", "voce", user_text.strip())
        if jarvis_text.strip():
            self._notify_optional("on_transcript", "jarvis", jarvis_text.strip())


def _linha_de_acao(name: str, args: Any, result: Any) -> str:
    """Linha curta da acao para o terminal (o texto inteiro de um arquivo lido nao vai)."""
    linha = f"  [ação] {name}({args or ''}) -> {result}"
    if len(linha) > TERMINAL_MAX_CHARS:
        linha = linha[:TERMINAL_MAX_CHARS] + " …(cortado)"
    return linha


def _print_safe(text: str) -> None:
    """``print`` que nunca levanta: console sem UTF-8 (emoji numa fala) ou sem console."""
    try:
        print(text)
    except Exception:  # noqa: BLE001 - o terminal nunca derruba o assistente
        logger.debug("nao consegui escrever no terminal", exc_info=True)


def _curto(texto: str, limite: int = 300) -> str:
    """Encurta um texto para o log (o log detalhado nunca guarda textos enormes)."""
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= limite else texto[:limite] + "…"
