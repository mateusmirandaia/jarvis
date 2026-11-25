"""Testes das correcoes de qualidade da 0.8.x (sem rede, sem microfone, sem sleeps fixos).

- voz do ElevenLabs nunca deixa o Jarvis mudo (interrupcao no meio do stream, erro generico);
- o controlador fecha o loop tambem no Python 3.11 (sem ``shutdown_default_executor(timeout)``);
- os lacos do ``LiveAssistant`` (_listen, _receive, _speak, run) com sessao e audio falsos;
- mensagens que a pessoa ve, com acento.
"""

from __future__ import annotations

import asyncio
import threading
import time
import warnings
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from jarvis.assistants.observer import NullObserver
from jarvis.assistants.voice_output import _END, FALLBACK_NOTICE, VoiceOutput, _fecha_fila

ESPERA_MAX_S = 3.0


async def _esperar(condicao: Callable[[], bool], timeout: float = ESPERA_MAX_S) -> None:
    """Espera a condicao ficar verdadeira (checa a cada ~10 ms); falha depois de ``timeout``."""
    limite = time.monotonic() + timeout
    while not condicao():
        if time.monotonic() > limite:
            raise AssertionError("a condicao nao ficou verdadeira a tempo")
        await asyncio.sleep(0.01)


def _drenar(fila: asyncio.Queue[bytes]) -> list[bytes]:
    itens = []
    while not fila.empty():
        itens.append(fila.get_nowait())
    return itens


class Gravador(NullObserver):
    """Observador que guarda tudo o que recebeu."""

    def __init__(self) -> None:
        self.estados: list[str] = []
        self.falas: list[tuple[str, str]] = []
        self.niveis: list[float] = []

    def on_state(self, state: str) -> None:  # type: ignore[override]
        self.estados.append(state)

    def on_transcript(self, speaker: str, text: str) -> None:  # type: ignore[override]
        self.falas.append((speaker, text))

    def on_level(self, level: float) -> None:
        self.niveis.append(level)


# =================================================================== voz do ElevenLabs
class VozPresa:
    """ElevenLabs falso: a 1a frase manda um pedaco e fica presa (frase longa chegando)."""

    def __init__(self) -> None:
        self.liberar = asyncio.Event()
        self.chamadas = 0

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        self.chamadas += 1
        if self.chamadas == 1:
            yield b"\x01\x00" * 10
            await self.liberar.wait()  # so continua se alguem liberar (ninguem libera)
            yield b"\x02\x00" * 10
        else:
            yield f"<{text}>".encode()

    async def close(self) -> None:
        pass


class VozQuebrada:
    """ElevenLabs falso que falha com um erro que NAO e ElevenLabsError."""

    def __init__(self) -> None:
        self.fechada = False

    async def stream(self, text: str) -> AsyncIterator[bytes]:
        raise RuntimeError("bug inesperado no cliente")
        yield b""  # pragma: no cover - so para ser um gerador assincrono

    async def close(self) -> None:
        self.fechada = True


def test_interrupcao_no_meio_do_stream_nao_deixa_o_jarvis_mudo() -> None:
    """Bug grave da 0.8.0: cancelar o _fetch no meio nao punha _END e o _forward travava."""

    async def cenario() -> None:
        fila: asyncio.Queue[bytes] = asyncio.Queue()
        voz = VozPresa()
        saida = VoiceOutput(fila, NullObserver(), voz)  # type: ignore[arg-type]
        rodando = asyncio.create_task(saida.run())
        try:
            saida.on_model_text("Primeira frase bem longa aqui. ")
            await _esperar(lambda: not fila.empty())  # o 1o pedaco ja tocou
            _drenar(fila)
            saida.on_interrupted()  # o senhor fala por cima no meio do stream
            saida.on_turn_complete()
            saida.on_model_text("Segunda resposta depois da interrupcao. ")
            saida.on_turn_complete()
            await _esperar(lambda: not fila.empty())  # travado = estoura o tempo aqui
            assert _drenar(fila) == [b"<Segunda resposta depois da interrupcao.>"]
            assert saida.uses_elevenlabs  # interrupcao nao e falha: continua no ElevenLabs
        finally:
            rodando.cancel()
            with pytest.raises(asyncio.CancelledError):
                await rodando

    asyncio.run(asyncio.wait_for(cenario(), 10))


def test_erro_generico_no_elevenlabs_cai_para_a_voz_do_google() -> None:
    async def cenario() -> None:
        fila: asyncio.Queue[bytes] = asyncio.Queue()
        observador = Gravador()
        voz = VozQuebrada()
        saida = VoiceOutput(fila, observador, voz)  # type: ignore[arg-type]
        rodando = asyncio.create_task(saida.run())
        try:
            saida.on_model_audio(b"reserva-do-gemini")
            saida.on_model_text("Pois não, senhor. ")
            await _esperar(lambda: not fila.empty())
            assert _drenar(fila) == [b"reserva-do-gemini"]
            assert ("sistema", FALLBACK_NOTICE) in observador.falas
            assert not saida.uses_elevenlabs
            await _esperar(lambda: voz.fechada)
            # o turno seguinte ja sai direto pela voz do Gemini
            saida.on_turn_complete()
            saida.on_model_audio(b"gemini-direto")
            assert fila.get_nowait() == b"gemini-direto"
        finally:
            rodando.cancel()
            with pytest.raises(asyncio.CancelledError):
                await rodando

    asyncio.run(asyncio.wait_for(cenario(), 10))


def test_fetch_cancelado_antes_de_comecar_ainda_fecha_a_fila() -> None:
    """Tarefa cancelada antes do 1o passo nem roda o ``finally``: o callback garante o _END."""

    async def cenario() -> list[object]:
        chunks: asyncio.Queue[object] = asyncio.Queue()
        tarefa = asyncio.create_task(VoiceOutput._fetch(VozPresa(), "oi", chunks))  # type: ignore[arg-type]
        tarefa.add_done_callback(_fecha_fila(chunks))
        tarefa.cancel()
        await asyncio.gather(tarefa, return_exceptions=True)
        await asyncio.sleep(0)  # callbacks de "done" rodam no proximo giro do loop
        return [chunks.get_nowait() for _ in range(chunks.qsize())]

    itens = asyncio.run(cenario())
    assert itens and itens[-1] is _END


def test_fetch_cancelado_no_meio_repassa_o_cancelamento() -> None:
    async def cenario() -> tuple[bool, list[object]]:
        chunks: asyncio.Queue[object] = asyncio.Queue()
        tarefa = asyncio.create_task(VoiceOutput._fetch(VozPresa(), "oi", chunks))  # type: ignore[arg-type]
        await _esperar(lambda: not chunks.empty())
        tarefa.cancel()
        resultado = await asyncio.gather(tarefa, return_exceptions=True)
        return isinstance(resultado[0], asyncio.CancelledError), [
            chunks.get_nowait() for _ in range(chunks.qsize())
        ]

    cancelada, itens = asyncio.run(cenario())
    assert cancelada
    assert isinstance(itens[0], bytes) and itens[-1] is _END


def test_aviso_de_voz_reserva_tem_acento_e_fala_do_google() -> None:
    assert FALLBACK_NOTICE == (
        "Senhor, a voz do ElevenLabs falhou. Vou usar a voz do Google por enquanto."
    )


# =================================================================== controlador
def test_fechar_loop_funciona_sem_timeout_do_python_312(monkeypatch: pytest.MonkeyPatch) -> None:
    """No 3.11 ``shutdown_default_executor`` nao aceita ``timeout`` (e espera para sempre)."""
    from jarvis import controlador

    class Loop311(asyncio.SelectorEventLoop):
        async def shutdown_default_executor(self) -> None:  # type: ignore[override]
            raise AssertionError("no 3.11 nao pode ser chamado: trava com thread presa")

    monkeypatch.setattr(controlador, "sys", SimpleNamespace(version_info=(3, 11, 9)))
    loop = Loop311()
    soltar = threading.Event()
    try:
        loop.run_until_complete(asyncio.to_thread(lambda: None))
        loop.run_in_executor(None, soltar.wait)  # thread presa (ex.: lendo o microfone)
        inicio = time.monotonic()
        controlador._desligar_executor(loop, 0.2)  # nao pode levantar TypeError nem travar
        assert time.monotonic() - inicio < 2.0
    finally:
        soltar.set()
        loop.close()


def test_fechar_loop_espera_threads_que_terminam(monkeypatch: pytest.MonkeyPatch) -> None:
    from jarvis import controlador

    monkeypatch.setattr(controlador, "sys", SimpleNamespace(version_info=(3, 11, 9)))
    loop = asyncio.new_event_loop()
    feito = threading.Event()
    try:
        loop.run_until_complete(asyncio.to_thread(lambda: None))
        loop.run_in_executor(None, feito.set)
        controlador._desligar_executor(loop, 2.0)
        assert feito.is_set()
    finally:
        loop.close()


def test_fechar_loop_inteiro_nao_levanta() -> None:
    from jarvis import controlador

    loop = asyncio.new_event_loop()
    loop.run_until_complete(asyncio.to_thread(lambda: None))
    controlador._fechar_loop(loop)
    assert loop.is_closed()


# =================================================================== LiveAssistant
pytest.importorskip("google.genai")

from google.genai import types  # noqa: E402

from jarvis.assistants import live_assistant as live  # noqa: E402
from jarvis.config import Settings  # noqa: E402
from jarvis.tools import ToolRegistry  # noqa: E402


class AudioFalso:
    """AudioIO falso: o microfone devolve blocos da lista e depois para com um erro."""

    def __init__(self, blocos: list[bytes] | None = None) -> None:
        self.blocos = list(blocos or [])
        self.tocado: list[bytes] = []
        self.eventos: list[str] = []

    def open_mic(self) -> None:
        self.eventos.append("open_mic")

    def read_mic(self) -> bytes:
        if not self.blocos:
            raise ConnectionError("fim do teste")
        return self.blocos.pop(0)

    def close_mic(self) -> None:
        self.eventos.append("close_mic")

    def open_speaker(self) -> None:
        self.eventos.append("open_speaker")

    def write_speaker(self, data: bytes) -> None:
        self.tocado.append(data)

    def close_speaker(self) -> None:
        self.eventos.append("close_speaker")

    def close(self) -> None:
        self.eventos.append("close")


class SessaoFalsa:
    """Sessao Live falsa: entrega as mensagens uma vez; o 2o ``receive`` derruba a conexao."""

    def __init__(self, mensagens: list[Any] | None = None) -> None:
        self.mensagens = list(mensagens or [])
        self.enviados: list[bytes] = []
        self.recebimentos = 0

    async def send_realtime_input(self, audio: types.Blob) -> None:
        self.enviados.append(audio.data or b"")

    async def send_tool_response(self, function_responses: list[Any]) -> None:
        pass

    async def receive(self) -> AsyncIterator[Any]:
        self.recebimentos += 1
        if self.recebimentos > 1:
            raise ConnectionError("conexao caiu")
        for mensagem in self.mensagens:
            yield mensagem


@pytest.fixture
def assistente(tmp_path: Path) -> live.LiveAssistant:
    settings = Settings(api_key="x", project_root=tmp_path)
    registry = ToolRegistry(settings, confirm=lambda title, message: False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        jarvis = live.LiveAssistant(settings, registry, observer=Gravador())
    return jarvis


def _audio(data: bytes) -> types.LiveServerMessage:
    parte = types.Part(inline_data=types.Blob(data=data, mime_type="audio/pcm;rate=24000"))
    return types.LiveServerMessage(
        server_content=types.LiveServerContent(model_turn=types.Content(parts=[parte]))
    )


def _conteudo(**campos: Any) -> types.LiveServerMessage:
    return types.LiveServerMessage(server_content=types.LiveServerContent(**campos))


def test_receive_toca_audio_e_mostra_as_falas_do_turno(assistente: live.LiveAssistant) -> None:
    sessao = SessaoFalsa(
        [
            _conteudo(input_transcription=types.Transcription(text="Que horas ")),
            _conteudo(input_transcription=types.Transcription(text="são?")),
            _audio(b"\x10\x00" * 8),
            _conteudo(output_transcription=types.Transcription(text="São dez horas, senhor.")),
            _conteudo(turn_complete=True),
        ]
    )
    with pytest.raises(ConnectionError):
        asyncio.run(assistente._receive(sessao))
    assert assistente.audio_queue.get_nowait() == b"\x10\x00" * 8
    falas = assistente.observer.falas  # type: ignore[attr-defined]
    assert ("voce", "Que horas são?") in falas
    assert ("jarvis", "São dez horas, senhor.") in falas


def test_receive_interrompido_esvazia_o_audio(assistente: live.LiveAssistant) -> None:
    sessao = SessaoFalsa([_audio(b"a" * 4), _audio(b"b" * 4), _conteudo(interrupted=True)])
    with pytest.raises(ConnectionError):
        asyncio.run(assistente._receive(sessao))
    assert assistente.audio_queue.empty()


def test_receive_pedido_de_acao_roda_em_segundo_plano(assistente: live.LiveAssistant) -> None:
    chamada = types.FunctionCall(id="1", name="current_time", args={})
    sessao = SessaoFalsa(
        [types.LiveServerMessage(tool_call=types.LiveServerToolCall(function_calls=[chamada]))]
    )
    respostas: list[Any] = []

    async def guardar(function_responses: list[Any]) -> None:
        respostas.extend(function_responses)

    sessao.send_tool_response = guardar  # type: ignore[method-assign]

    async def cenario() -> None:
        with pytest.raises(ConnectionError):
            await assistente._receive(sessao)
        await _esperar(lambda: bool(respostas))

    asyncio.run(cenario())
    assert "thinking" in assistente.observer.estados  # type: ignore[attr-defined]
    assert respostas[0].id == "1"


def test_listen_manda_silencio_enquanto_ele_fala(assistente: live.LiveAssistant) -> None:
    audio = AudioFalso([b"\x05\x05" * 4, b"\x06\x06" * 4])
    assistente.audio = audio  # type: ignore[assignment]
    sessao = SessaoFalsa()
    original = sessao.send_realtime_input

    async def enviar(audio: types.Blob) -> None:
        await original(audio)
        assistente.speaking = True  # depois do 1o bloco ele comeca a falar

    sessao.send_realtime_input = enviar  # type: ignore[method-assign]
    assistente.speaking = False
    with pytest.raises(ConnectionError):
        asyncio.run(assistente._listen(sessao))
    assert sessao.enviados == [b"\x05\x05" * 4, bytes(8)]  # 2o bloco: falando = silencio
    assert audio.eventos == ["open_mic", "close_mic"]


def test_listen_com_fone_nao_silencia(assistente: live.LiveAssistant) -> None:
    assistente.settings = Settings(api_key="x", headphones=True)
    audio = AudioFalso([b"\x07\x07" * 4])
    assistente.audio = audio  # type: ignore[assignment]
    assistente.speaking = True
    sessao = SessaoFalsa()
    with pytest.raises(ConnectionError):
        asyncio.run(assistente._listen(sessao))
    assert sessao.enviados == [b"\x07\x07" * 4]


def test_speak_toca_e_libera_o_microfone(
    assistente: live.LiveAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "ECHO_GAP_S", 0)
    audio = AudioFalso()
    assistente.audio = audio  # type: ignore[assignment]
    bloco = b"\x00\x10" * (live.PLAYBACK_SLICE_BYTES // 2 + 10)  # vira 2 fatias
    observador: Gravador = assistente.observer  # type: ignore[assignment]

    async def cenario() -> None:
        tarefa = asyncio.create_task(assistente._speak())
        assistente.audio_queue.put_nowait(bloco)
        await _esperar(lambda: observador.estados[-2:] == ["speaking", "listening"])
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa

    asyncio.run(cenario())
    assert b"".join(audio.tocado) == bloco and len(audio.tocado) == 2
    assert not assistente.speaking
    assert audio.eventos == ["open_speaker", "close_speaker"]


def test_queda_avisa_com_acento_e_reconecta(
    assistente: live.LiveAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    from google.genai import errors as genai_errors

    monkeypatch.setattr(live, "MAX_BACKOFF_S", 0)
    audio = AudioFalso()
    monkeypatch.setattr(live, "AudioIO", lambda: audio)
    tentativas: list[int] = []

    async def sessao() -> None:
        tentativas.append(assistente.failures)
        if len(tentativas) == 1:
            raise ConnectionError("rede caiu")
        raise genai_errors.APIError(401, {"error": {"message": "API key not valid"}})

    monkeypatch.setattr(assistente, "_session", sessao)
    with pytest.raises(live.ChaveInvalidaError):
        asyncio.run(assistente.run())
    assert tentativas == [0, 1]
    falas = assistente.observer.falas  # type: ignore[attr-defined]
    assert ("sistema", "Senhor, perdi a conexão. Tento de novo em 0 s…") in falas
    assert "close" in audio.eventos  # o audio fecha mesmo parando por chave invalida


# =================================================================== mensagens
def test_mensagens_visiveis_tem_acento() -> None:
    from jarvis import config
    from jarvis.os_integration import shortcut

    assert "Não encontrei" in config._MISSING_KEY_MESSAGE
    assert "está errada" in live.INVALID_KEY_MESSAGE
    if not shortcut.sys.platform.startswith("win"):
        assert shortcut.create_desktop_shortcut(Path("."), None) == (
            "O atalho na Área de Trabalho só pode ser criado no Windows."
        )


def test_jarvis_ja_aberto_explica_onde_esta(monkeypatch: pytest.MonkeyPatch) -> None:

    from jarvis import __main__ as cli
    from jarvis.os_integration import windows

    avisos: list[str] = []
    monkeypatch.setattr(cli, "_tell_user", avisos.append)
    monkeypatch.setattr(windows, "acquire_single_instance", lambda nome: False)
    cli._run_orb(Settings(api_key=""))
    assert avisos == ["O Jarvis já está aberto, senhor. Procure a janela dele na barra de tarefas."]


def test_pasta_usuario_tem_uma_so_implementacao(monkeypatch: pytest.MonkeyPatch) -> None:
    from jarvis import armazenamento, config

    monkeypatch.setattr(armazenamento, "pasta_usuario", lambda: Path("/tmp/jarvis-teste"))
    assert config.pasta_usuario() == Path("/tmp/jarvis-teste")


def test_vozes_dizem_o_genero() -> None:
    from jarvis import vozes

    for id_voz, descricao in vozes.VOZES:
        assert descricao.startswith(("Masculina", "Feminina")), id_voz
    assert vozes.DESCRICOES["Zephyr"] == "Feminina, clara"
