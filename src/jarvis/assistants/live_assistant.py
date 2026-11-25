"""Jarvis por voz em tempo real: Gemini Live (ouvido + cerebro + boca numa conexao so).

Use fone de ouvido de preferencia. Ctrl+C encerra.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from google import genai
from google.genai import types

from jarvis.assistants.audio import MIC_MIME_TYPE, AudioIO
from jarvis.assistants.elevenlabs_voice import ElevenLabsVoice
from jarvis.assistants.observer import AssistantObserver, NullObserver, pcm_level
from jarvis.assistants.voice_output import VoiceOutput
from jarvis.errors import ChaveInvalidaError, erro_de_autenticacao, friendly_message
from jarvis.persona import build_system_prompt

if TYPE_CHECKING:
    from jarvis.config import Settings
    from jarvis.tools import ToolRegistry

logger = logging.getLogger(__name__)

MAX_BACKOFF_S = 15
ECHO_GAP_S = 0.2  # folga apos a fala para o eco morrer antes de reabrir o microfone
PLAYBACK_SLICE_BYTES = 2_048  # ~42 ms de audio a 24 kHz: o orb pulsa no ritmo da fala
MIC_LEVEL_FACTOR = 0.6  # ao ouvir, o orb reage ao microfone de forma mais discreta
INVALID_KEY_MESSAGE = (
    "O Google recusou a chave (GEMINI_API_KEY): ela está errada, foi apagada ou bloqueada. "
    "Abra o Jarvis pela janela e troque a chave na engrenagem (aba Chave do Google)."
)
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
        self.voice = VoiceOutput(self.audio_queue, self.observer, self._build_elevenlabs())
        self.speaking = False  # enquanto ele fala, o microfone nao envia (evita eco)
        self.failures = 0  # quedas seguidas da conexao
        self._tool_tasks: set[asyncio.Task[None]] = set()  # acoes rodando em segundo plano
        self._heard_at: float | None = None  # ultima vez que ouviu o senhor (para medir atraso)
        self._answer_logged = False
        self.audio: AudioIO | None = None

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
                        self.observer.on_state("offline")
                        raise ChaveInvalidaError(INVALID_KEY_MESSAGE) from None
                    await self._handle_disconnect(error)
        finally:
            self.audio.close()
            await self.voice.close()

    async def _handle_disconnect(self, error: Exception) -> None:
        """Registra a queda, avisa no terminal, limpa o estado e espera o backoff."""
        cause = getattr(error, "exceptions", [error])[0]
        logger.error("sessao caiu: %r", cause)
        self.failures += 1
        wait = min(2**self.failures, MAX_BACKOFF_S)
        notice = f"Senhor, perdi a conexão. Tento de novo em {wait} s…"
        print(f"(Jarvis: {notice})")
        self.observer.on_state("offline")
        self.observer.on_transcript("sistema", notice)
        self._reset_playback()
        self.voice.on_interrupted()
        await asyncio.sleep(wait)

    def _reset_playback(self) -> None:
        """Esvazia a fila de audio e libera o microfone."""
        self.speaking = False
        self._clear_queue()
        self.observer.on_level(0.0)

    def _clear_queue(self) -> None:
        while not self.audio_queue.empty():
            self.audio_queue.get_nowait()

    async def _session(self) -> None:
        """Uma sessao Live: conecta, avisa se voltou de queda e roda as tarefas."""
        async with self.client.aio.live.connect(
            model=self.settings.live_model, config=self.config
        ) as session:
            if self.failures:  # voltou de uma queda: ele mesmo avisa, em voz
                await session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part(text=RECONNECT_NOTICE)]),
                    turn_complete=True,
                )
                logger.info("reconectado apos %d queda(s)", self.failures)
            else:
                print(
                    f"Jarvis ouvindo ({self.settings.live_model}, voz {self.voice_label}). "
                    "Fale! Ctrl+C para sair."
                )
                logger.info("sessao iniciada, voz: %s", self.voice_label)
            self.failures = 0
            self.observer.on_state("listening")
            try:
                await self._run_tasks(session)
            finally:
                for task in list(self._tool_tasks):  # acoes da sessao que caiu
                    task.cancel()

    async def _run_tasks(self, session: Any) -> None:
        """Roda ouvir, receber, falar e a voz em paralelo ate a sessao cair."""
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self._listen(session))
            tasks.create_task(self._receive(session))
            tasks.create_task(self._speak())
            tasks.create_task(self.voice.run())

    # --------------------------------------------------------------------- tarefas
    async def _listen(self, session: Any) -> None:
        """Le o microfone e envia ao modelo, exceto enquanto o Jarvis fala (anti-eco)."""
        assert self.audio is not None
        await asyncio.to_thread(self.audio.open_mic)
        try:
            while True:
                data = await asyncio.to_thread(self.audio.read_mic)
                # Sem fone, enquanto ele fala o microfone manda SILENCIO no lugar da sua voz
                # (senao ele ouve a si mesmo). O fluxo nunca para: o detector de fala do
                # Gemini continua acompanhando e reconhece quando o senhor volta a falar.
                if self.settings.headphones or not self.speaking:
                    self.observer.on_level(pcm_level(data) * MIC_LEVEL_FACTOR)
                else:
                    data = bytes(len(data))
                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type=MIC_MIME_TYPE)
                )
        finally:
            self.audio.close_mic()

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
                if message.data:
                    self.voice.on_model_audio(message.data)
                if message.tool_call:
                    self.observer.on_state("thinking")
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
                    logger.info("interrompido pelo senhor")
                    self._clear_queue()
                    self.voice.on_interrupted()
                if content.turn_complete:
                    logger.info("turno completo (fila de audio: %d)", self.audio_queue.qsize())
                    self.voice.on_turn_complete()
                    self._print_turn(user_text, jarvis_text)
                    self._notify_turn(user_text, jarvis_text)
                    user_text, jarvis_text = "", ""

    async def _speak(self) -> None:
        """Toca o audio da fila; mantem o microfone mudo ate a folga do eco passar."""
        assert self.audio is not None
        await asyncio.to_thread(self.audio.open_speaker)
        try:
            while True:
                data = await self.audio_queue.get()
                if not self.speaking:
                    self.speaking = True
                    self.observer.on_state("speaking")
                    self._log_latency()
                await self._play(data)
                if self.audio_queue.empty():
                    await asyncio.sleep(ECHO_GAP_S)
                    self.speaking = not self.audio_queue.empty()
                    if not self.speaking:
                        logger.info("terminou de falar: microfone liberado")
                        self.observer.on_level(0.0)
                        self.observer.on_state("listening")
        finally:
            self.audio.close_speaker()

    async def _play(self, data: bytes) -> None:
        """Toca um bloco em fatias pequenas, avisando o volume de cada fatia ao observador."""
        assert self.audio is not None
        for start in range(0, len(data), PLAYBACK_SLICE_BYTES):
            piece = data[start : start + PLAYBACK_SLICE_BYTES]
            self.observer.on_level(pcm_level(piece))
            await asyncio.to_thread(self.audio.write_speaker, piece)

    # ---------------------------------------------------------------- ferramentas
    async def _handle_tool_call(self, session: Any, tool_call: types.LiveServerToolCall) -> None:
        """Executa cada acao pedida (em outra thread) e devolve o resultado ao modelo.

        Roda em segundo plano: o modelo ja disse "Um instante, senhor" e, quando o
        resultado chega (WHEN_IDLE), ele fala o resultado assim que terminar a frase atual.
        """
        responses: list[types.FunctionResponse] = []
        for call in tool_call.function_calls or []:
            name = call.name or ""
            result = await self._execute(name, call.args or {})
            print(f"  [ação] {name}({call.args or ''}) -> {result}")
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
        func = self.registry.get(name)
        if func is None:
            logger.warning("acao nao permitida pedida pelo modelo: %s", name)
            self._notify_tool(name, ok=False)
            return "Ação não permitida."
        try:
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
        self._notify_tool(name, ok=not str(result).startswith("ERRO:"))
        return result

    # ------------------------------------------------------------------- terminal
    @staticmethod
    def _print_turn(user_text: str, jarvis_text: str) -> None:
        if user_text.strip():
            print("Você:", user_text.strip())
        if jarvis_text.strip():
            print("Jarvis:", jarvis_text.strip())

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
            self.observer.on_transcript("voce", user_text.strip())
        if jarvis_text.strip():
            self.observer.on_transcript("jarvis", jarvis_text.strip())
