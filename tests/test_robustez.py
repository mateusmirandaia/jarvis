"""Bateria de estresse do LiveAssistant (rodada 0.9): sessao Live, audio e ElevenLabs falsos.

Cada cenario roda o ``run()`` de verdade (laco de reconexao, TaskGroup, vigia de resposta)
com uma sessao Live falsa e um tempo maximo (``asyncio.wait_for``): se algo congelar, o
teste estoura o tempo em vez de travar a bateria. Criterio: nada congela, o laco continua,
o estado volta a "listening" depois de reconectar e nenhuma excecao escapa.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
import warnings
import wave
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("google.genai")

import httpx  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402
from google.genai import types  # noqa: E402

from jarvis import avisos  # noqa: E402
from jarvis.assistants import live_assistant as live  # noqa: E402
from jarvis.assistants.elevenlabs_voice import ElevenLabsVoice  # noqa: E402
from jarvis.assistants.observer import NullObserver  # noqa: E402
from jarvis.assistants.voice_output import FALLBACK_NOTICE, VoiceOutput  # noqa: E402
from jarvis.config import Settings  # noqa: E402
from jarvis.errors import ChaveInvalidaError, SemRespostaError  # noqa: E402
from jarvis.tools import ToolRegistry  # noqa: E402

TEMPO_MAX_S = 10.0  # nenhum cenario pode passar disso: passou = congelou
ESPERA_S = 4.0

MARCA_INTERNET = b"\x11\x22"
MARCA_INTERNET_PUCK = b"\x55\x66"
MARCA_ELEVEN = b"\x33\x44"
MARCA_MODELO = b"\x01\x00"


# =================================================================== utilitarios
async def _esperar(condicao: Callable[[], bool], timeout: float = ESPERA_S) -> None:
    limite = time.monotonic() + timeout
    while not condicao():
        if time.monotonic() > limite:
            raise AssertionError("a condicao nao ficou verdadeira a tempo")
        await asyncio.sleep(0.01)


def _rodar(cenario: Callable[[], Any]) -> Any:
    """Roda o cenario com tempo maximo: congelar vira falha, nunca trava a bateria."""
    return asyncio.run(asyncio.wait_for(cenario(), TEMPO_MAX_S))


def _wav(caminho: Path, marca: bytes, quadros: int = 1_200) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24_000)
        w.writeframes(marca * quadros)
    return caminho


@pytest.fixture
def pasta_avisos(tmp_path: Path) -> Path:
    pasta = tmp_path / "avisos"
    _wav(pasta / "internet_Charon.wav", MARCA_INTERNET)
    _wav(pasta / "internet_Puck.wav", MARCA_INTERNET_PUCK)
    _wav(pasta / "elevenlabs_Charon.wav", MARCA_ELEVEN)
    return pasta


class Gravador(NullObserver):
    """Observador que guarda tudo (pode ser chamado de qualquer thread)."""

    def __init__(self) -> None:
        self.estados: list[str] = []
        self.falas: list[tuple[str, str]] = []
        self.acoes: list[tuple[str, bool]] = []

    def on_state(self, state: str) -> None:  # type: ignore[override]
        self.estados.append(state)

    def on_transcript(self, speaker: str, text: str) -> None:  # type: ignore[override]
        self.falas.append((speaker, text))

    def on_tool(self, name: str, ok: bool) -> None:
        self.acoes.append((name, ok))

    def sistema(self) -> list[str]:
        return [texto for quem, texto in self.falas if quem == "sistema"]


class ObservadorQuebrado:
    """Janela com defeito: todo metodo levanta. O assistente tem de seguir mesmo assim."""

    def __getattr__(self, nome: str) -> Callable[..., None]:
        def quebrar(*_args: Any) -> None:
            raise RuntimeError(f"janela quebrada em {nome}")

        return quebrar


class AudioFalso:
    """Microfone e alto-falante falsos (thread-safe). O microfone manda silencio sem parar."""

    def __init__(self) -> None:
        self.trava = threading.Lock()
        self.tocado: list[bytes] = []
        self.eventos: list[str] = []
        self.mic_quebrado = False
        self.falante_quebrado = False
        self.falante_preso = threading.Event()  # set = write_speaker fica preso
        self.soltar = threading.Event()

    def _evento(self, nome: str) -> None:
        with self.trava:
            self.eventos.append(nome)

    def open_mic(self) -> None:
        if self.mic_quebrado:
            raise OSError(-9996, "Invalid input device (no default output device)")
        self._evento("open_mic")

    def read_mic(self) -> bytes:
        time.sleep(0.005)
        if self.mic_quebrado:
            raise OSError(-9999, "Unanticipated host error")
        return bytes(320)

    def close_mic(self) -> None:
        self._evento("close_mic")

    def open_speaker(self) -> None:
        self._evento("open_speaker")

    def write_speaker(self, data: bytes) -> None:
        if self.falante_quebrado:
            raise OSError(-9999, "Unanticipated host error")
        if self.falante_preso.is_set():
            self.soltar.wait(5)
        with self.trava:
            self.tocado.append(data)

    def close_speaker(self) -> None:
        self._evento("close_speaker")

    def close(self) -> None:
        self._evento("close")

    def tocou(self, marca: bytes) -> int:
        """Quantos bytes com a marca foram tocados."""
        with self.trava:
            return sum(len(b) for b in self.tocado if b[:2] == marca)


class SessaoFalsa:
    """Sessao Live falsa: o teste poe mensagens (ou excecoes) na caixa de entrada."""

    def __init__(self) -> None:
        self.caixa: asyncio.Queue[Any] = asyncio.Queue()
        self.textos: list[str] = []
        self.respostas: list[Any] = []
        self.audio_enviado = 0
        self.fechada = False
        self.falha_ao_enviar: BaseException | None = None

    def por(self, *itens: Any) -> None:
        for item in itens:
            self.caixa.put_nowait(item)

    async def send_realtime_input(self, audio: types.Blob) -> None:
        if self.falha_ao_enviar is not None:
            raise self.falha_ao_enviar
        self.audio_enviado += 1

    async def send_client_content(self, turns: Any, turn_complete: bool) -> None:
        self.textos.append(turns.parts[0].text)

    async def send_tool_response(self, function_responses: list[Any]) -> None:
        self.respostas.extend(function_responses)

    async def receive(self) -> AsyncIterator[Any]:
        while True:
            item = await self.caixa.get()
            if isinstance(item, BaseException):
                raise item
            yield item
            if item.server_content and item.server_content.turn_complete:
                return


class ClienteFalso:
    """Substitui o ``genai.Client``: cada ``connect`` entrega a proxima sessao falsa."""

    def __init__(self) -> None:
        self.sessoes: list[SessaoFalsa] = []
        self.falhas_ao_conectar: list[BaseException | str] = []  # "pendurar" = nunca conecta
        self.aio = self
        self.live = self

    @contextlib.asynccontextmanager
    async def connect(self, model: str, config: Any) -> AsyncIterator[SessaoFalsa]:
        if self.falhas_ao_conectar:
            falha = self.falhas_ao_conectar.pop(0)
            if falha == "pendurar":
                await asyncio.Event().wait()
            assert isinstance(falha, BaseException)
            raise falha
        sessao = SessaoFalsa()
        self.sessoes.append(sessao)
        try:
            yield sessao
        finally:
            sessao.fechada = True

    @property
    def atual(self) -> SessaoFalsa:
        return self.sessoes[-1]


def _audio_msg(marca: bytes = MARCA_MODELO, tamanho: int = 480) -> types.LiveServerMessage:
    parte = types.Part(
        inline_data=types.Blob(data=marca * tamanho, mime_type="audio/pcm;rate=24000")
    )
    return types.LiveServerMessage(
        server_content=types.LiveServerContent(model_turn=types.Content(parts=[parte]))
    )


def _conteudo(**campos: Any) -> types.LiveServerMessage:
    return types.LiveServerMessage(server_content=types.LiveServerContent(**campos))


def _fala(texto: str) -> types.LiveServerMessage:
    return _conteudo(input_transcription=types.Transcription(text=texto))


def _texto_jarvis(texto: str) -> types.LiveServerMessage:
    return _conteudo(output_transcription=types.Transcription(text=texto))


def _fim() -> types.LiveServerMessage:
    return _conteudo(turn_complete=True)


def _acao(nome: str, id_: str = "1") -> types.LiveServerMessage:
    chamada = types.FunctionCall(id=id_, name=nome, args={})
    return types.LiveServerMessage(tool_call=types.LiveServerToolCall(function_calls=[chamada]))


def _api_error(codigo: int, mensagem: str) -> genai_errors.APIError:
    return genai_errors.APIError(codigo, {"error": {"message": mensagem}})


class Cena:
    """Monta um LiveAssistant com cliente, audio e avisos falsos e roda o ``run()``."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        pasta_avisos: Path,
        observer: Any = None,
        **ajustes: Any,
    ) -> None:
        monkeypatch.setattr(live, "MAX_BACKOFF_S", 0)
        monkeypatch.setattr(live, "ECHO_GAP_S", 0)
        self.audio = AudioFalso()
        monkeypatch.setattr(live, "AudioIO", lambda: self.audio)
        opcoes: dict[str, Any] = {
            "api_key": "x",
            "project_root": tmp_path,
            "resposta_timeout_s": 0.3,
        }
        opcoes.update(ajustes)
        settings = Settings(**opcoes)
        registry = ToolRegistry(settings, confirm=lambda title, message: False)
        self.observador = observer if observer is not None else Gravador()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.jarvis = live.LiveAssistant(settings, registry, observer=self.observador)
        self.cliente = ClienteFalso()
        self.jarvis.client = self.cliente  # type: ignore[assignment]
        self.jarvis.avisos_dir = pasta_avisos
        self.tarefa: asyncio.Task[None] | None = None

    async def iniciar(self) -> None:
        self.tarefa = asyncio.create_task(self.jarvis.run())
        await self.conectou(1)

    async def conectou(self, n: int) -> SessaoFalsa:
        """Espera a n-esima sessao abrir e o estado voltar a "listening"."""
        await _esperar(lambda: len(self.cliente.sessoes) >= n)
        if isinstance(self.observador, Gravador):
            await _esperar(lambda: self.observador.estados[-1:] == ["listening"])
        return self.cliente.sessoes[n - 1]

    async def parar(self) -> None:
        """Para como o controlador para: cancela a tarefa. Nunca pode levantar outra coisa."""
        assert self.tarefa is not None
        self.tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await self.tarefa
        assert "close" in self.audio.eventos  # o audio sempre fecha


@pytest.fixture
def cena(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pasta_avisos: Path):
    def fabricar(**ajustes: Any) -> Cena:
        return Cena(monkeypatch, tmp_path, pasta_avisos, **ajustes)

    return fabricar


# =================================================================== internet caindo
@pytest.mark.parametrize("momento", ["antes", "durante", "depois"])
def test_internet_cai_e_ele_avisa_e_reconecta(cena: Callable[..., Cena], momento: str) -> None:
    c = cena()

    async def cenario() -> None:
        await c.iniciar()
        s1 = c.cliente.atual
        s1.por(_fala("Que horas são?"))
        if momento in ("durante", "depois"):
            s1.por(_audio_msg(), _texto_jarvis("São dez "))
        if momento == "depois":
            s1.por(_texto_jarvis("horas."), _fim())
            await _esperar(lambda: ("jarvis", "São dez horas.") in c.observador.falas)
        s1.por(_api_error(1006, "abnormal closure"))
        s2 = await c.conectou(2)
        assert s1.fechada
        assert c.audio.tocou(MARCA_INTERNET) == 2_400  # o aviso inteiro, uma vez
        assert avisos.TEXTO_INTERNET in c.observador.sistema()
        assert live.RECONNECT_NOTICE in s2.textos  # ele mesmo diz que voltou
        # a conversa continua normal depois de voltar
        s2.por(_audio_msg(b"\x02\x00"), _fim())
        await _esperar(lambda: c.audio.tocou(b"\x02\x00") > 0)
        await _esperar(lambda: c.observador.estados[-1] == "listening")
        await c.parar()

    _rodar(cenario)


def test_modelo_mudo_estoura_o_tempo_toca_aviso_e_reconecta(cena: Callable[..., Cena]) -> None:
    c = cena(resposta_timeout_s=0.3)

    async def cenario() -> None:
        await c.iniciar()
        inicio = time.monotonic()
        c.cliente.atual.por(_fala("Abre o bloco de notas"))  # e o modelo nunca responde
        await c.conectou(2)
        assert 0.25 <= time.monotonic() - inicio < 3.0
        assert c.audio.tocou(MARCA_INTERNET) > 0
        assert avisos.TEXTO_INTERNET in c.observador.sistema()
        await c.parar()

    _rodar(cenario)


def test_sem_fala_nao_ha_tempo_limite(cena: Callable[..., Cena]) -> None:
    """Ficar em silencio (ninguem falou) nao e problema de internet."""
    c = cena(resposta_timeout_s=0.1)

    async def cenario() -> None:
        await c.iniciar()
        await asyncio.sleep(0.5)
        assert len(c.cliente.sessoes) == 1
        assert c.audio.tocou(MARCA_INTERNET) == 0
        await c.parar()

    _rodar(cenario)


def test_resposta_que_chega_desarma_o_tempo_limite(cena: Callable[..., Cena]) -> None:
    c = cena(resposta_timeout_s=0.2)

    async def cenario() -> None:
        await c.iniciar()
        s1 = c.cliente.atual
        s1.por(_fala("Oi"), _audio_msg(), _texto_jarvis("Olá, senhor."), _fim())
        s1.por(_fala(" atrasada"))  # transcricao atrasada depois do fim do turno? nova fala
        s1.por(_texto_jarvis("Pois não."), _fim())
        await asyncio.sleep(0.6)
        assert len(c.cliente.sessoes) == 1
        assert c.audio.tocou(MARCA_INTERNET) == 0
        await c.parar()

    _rodar(cenario)


def test_transcricao_atrasada_no_meio_da_resposta_nao_rearma(cena: Callable[..., Cena]) -> None:
    c = cena(resposta_timeout_s=0.2)

    async def cenario() -> None:
        await c.iniciar()
        s1 = c.cliente.atual
        s1.por(_fala("Que horas"), _audio_msg(), _fala(" são?"))  # pedaco atrasado
        await asyncio.sleep(0.6)  # resposta longa ainda tocando, sem fim de turno
        assert len(c.cliente.sessoes) == 1
        await c.parar()

    _rodar(cenario)


def test_aviso_de_internet_no_maximo_1_vez_a_cada_30_s(cena: Callable[..., Cena]) -> None:
    c = cena()
    relogio = [1_000.0]
    c.jarvis._clock = lambda: relogio[0]

    async def cenario() -> None:
        await c.iniciar()
        for n in range(2, 5):  # tres quedas seguidas em menos de 30 s
            c.cliente.atual.por(ConnectionResetError("rede caiu"))
            await c.conectou(n)
            relogio[0] += 5
        assert c.audio.tocou(MARCA_INTERNET) == 2_400  # tocou so na primeira
        assert c.observador.sistema().count(avisos.TEXTO_INTERNET) == 1
        relogio[0] += 31
        c.cliente.atual.por(ConnectionResetError("rede caiu de novo"))
        await c.conectou(5)
        assert c.audio.tocou(MARCA_INTERNET) == 4_800  # passou de 30 s: toca de novo
        await c.parar()

    _rodar(cenario)


@pytest.mark.parametrize("codigo", [500, 503])
def test_servidor_5xx_avisa_internet_e_reconecta(cena: Callable[..., Cena], codigo: int) -> None:
    c = cena()

    async def cenario() -> None:
        await c.iniciar()
        c.cliente.atual.por(_fala("oi"), _api_error(codigo, "The service is currently unavailable"))
        await c.conectou(2)
        assert c.audio.tocou(MARCA_INTERNET) > 0
        await c.parar()

    _rodar(cenario)


def test_429_nao_fala_de_internet_mas_reconecta(cena: Callable[..., Cena]) -> None:
    c = cena()

    async def cenario() -> None:
        await c.iniciar()
        c.cliente.atual.por(_api_error(429, "RESOURCE_EXHAUSTED: quota exceeded"))
        await c.conectou(2)
        assert c.audio.tocou(MARCA_INTERNET) == 0
        assert avisos.TEXTO_INTERNET not in c.observador.sistema()
        assert any("limite de uso" in t for t in c.observador.sistema())
        await c.parar()

    _rodar(cenario)


def test_google_fecha_a_sessao_normalmente_sem_aviso_de_internet(
    cena: Callable[..., Cena],
) -> None:
    """Codigo 1000: o Google encerra a conexao (tempo maximo). Reconecta calado."""
    c = cena()

    async def cenario() -> None:
        await c.iniciar()
        c.cliente.atual.por(_api_error(1000, "session ended"))
        await c.conectou(2)
        assert c.audio.tocou(MARCA_INTERNET) == 0
        await c.parar()

    _rodar(cenario)


def test_conectar_pendurado_estoura_o_tempo(
    cena: Callable[..., Cena], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "CONNECT_TIMEOUT_S", 0.2)
    c = cena()
    c.cliente.falhas_ao_conectar = ["pendurar", OSError(11001, "getaddrinfo failed")]

    async def cenario() -> None:
        c.tarefa = asyncio.create_task(c.jarvis.run())
        await c.conectou(1)  # duas tentativas falham, a terceira conecta
        assert c.audio.tocou(MARCA_INTERNET) > 0  # tocou (uma vez) enquanto estava sem rede
        await c.parar()

    _rodar(cenario)


def test_chave_invalida_no_meio_para_sem_travar(cena: Callable[..., Cena]) -> None:
    c = cena()

    async def cenario() -> None:
        await c.iniciar()
        c.cliente.atual.por(_api_error(1008, "API key not valid. Please pass a valid API key."))
        assert c.tarefa is not None
        with pytest.raises(ChaveInvalidaError):
            await c.tarefa
        assert c.observador.estados[-1] == "offline"
        assert "close" in c.audio.eventos
        assert c.audio.tocou(MARCA_INTERNET) == 0  # nao e internet: a janela pede outra chave

    _rodar(cenario)


# =================================================================== audio
def test_microfone_some_avisa_e_tenta_de_novo(cena: Callable[..., Cena]) -> None:
    c = cena()

    async def cenario() -> None:
        await c.iniciar()
        c.audio.mic_quebrado = True  # arrancaram o microfone USB
        await _esperar(lambda: any("microfone" in t for t in c.observador.sistema()))
        await _esperar(lambda: len(c.cliente.sessoes) >= 3)  # continua tentando
        assert c.audio.tocou(MARCA_INTERNET) == 0  # nao e internet
        c.audio.mic_quebrado = False  # ligaram de volta
        await _esperar(lambda: c.audio.eventos.count("open_mic") >= 2)
        await _esperar(lambda: c.observador.estados[-1] == "listening")
        await c.parar()

    _rodar(cenario)


def test_alto_falante_com_erro_avisa_e_tenta_de_novo(cena: Callable[..., Cena]) -> None:
    c = cena()

    async def cenario() -> None:
        await c.iniciar()
        c.audio.falante_quebrado = True
        c.cliente.atual.por(_fala("oi"), _audio_msg())
        await c.conectou(2)
        assert any("som" in t for t in c.observador.sistema())
        c.audio.falante_quebrado = False
        c.cliente.atual.por(_audio_msg(b"\x02\x00"), _fim())
        await _esperar(lambda: c.audio.tocou(b"\x02\x00") > 0)
        await c.parar()

    _rodar(cenario)


def test_alto_falante_preso_no_aviso_nao_trava_a_reconexao(
    cena: Callable[..., Cena], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live, "AVISO_FOLGA_S", 0.1)
    c = cena()

    async def cenario() -> None:
        await c.iniciar()
        c.audio.falante_preso.set()  # o driver de som travou
        c.cliente.atual.por(ConnectionError("caiu"))
        await _esperar(lambda: len(c.cliente.sessoes) >= 2, timeout=3.0)
        c.audio.falante_preso.clear()
        c.audio.soltar.set()
        await c.conectou(2)
        await c.parar()

    _rodar(cenario)


# =================================================================== interrupcoes
def test_interrupcoes_seguidas_nao_deixam_ele_mudo(cena: Callable[..., Cena]) -> None:
    c = cena()

    async def cenario() -> None:
        await c.iniciar()
        s1 = c.cliente.atual
        for _ in range(30):
            s1.por(_fala("espera"), _audio_msg(), _conteudo(interrupted=True))
        s1.por(_audio_msg(b"\x07\x00"), _texto_jarvis("Pois não?"), _fim())
        await _esperar(lambda: c.audio.tocou(b"\x07\x00") > 0)
        await _esperar(lambda: c.observador.estados[-1] == "listening")
        assert len(c.cliente.sessoes) == 1  # interromper nao derruba nada
        await c.parar()

    _rodar(cenario)


# =================================================================== ferramentas
def test_ferramenta_que_trava_vira_frase_e_o_laco_segue(
    cena: Callable[..., Cena], monkeypatch: pytest.MonkeyPatch
) -> None:
    c = cena(resposta_timeout_s=0.2)
    soltar = threading.Event()
    monkeypatch.setattr(c.jarvis.registry, "get", lambda nome: lambda: soltar.wait(3) and "ok")
    monkeypatch.setattr(c.jarvis.registry, "timeout_for", lambda nome, settings: 0.5)

    async def cenario() -> None:
        await c.iniciar()
        s1 = c.cliente.atual
        s1.por(_fala("abre o word"), _acao("open_app"))
        # enquanto a acao roda o senhor fala de novo (novo turno): o silencio nao conta
        await asyncio.sleep(0.05)
        s1.por(_fim(), _fala("e ai?"))
        await _esperar(lambda: bool(s1.respostas), timeout=3.0)
        assert "demorou demais" in s1.respostas[0].response["result"]
        assert len(c.cliente.sessoes) == 1  # 0,5 s de acao > 0,2 s de limite: nao caiu
        s1.por(_texto_jarvis("Demorou, senhor."), _fim())  # o modelo fala o resultado
        await asyncio.sleep(0.4)
        assert len(c.cliente.sessoes) == 1  # acao lenta nao e queda de internet
        assert ("open_app", False) in c.observador.acoes
        soltar.set()
        await c.parar()

    _rodar(cenario)


def test_vigia_espera_acao_lenta_e_depois_cobra_resposta(cena: Callable[..., Cena]) -> None:
    c = cena(resposta_timeout_s=0.15)

    async def cenario() -> None:
        acao = asyncio.create_task(asyncio.sleep(0.5))
        c.jarvis._tool_tasks.add(acao)
        c.jarvis._arm_reply_deadline()
        inicio = time.monotonic()
        with pytest.raises(SemRespostaError):
            await c.jarvis._watch_reply()
        assert time.monotonic() - inicio >= 0.5  # so depois que a acao terminou
        assert acao.done()

    _rodar(cenario)


def test_ferramenta_com_erro_inesperado_sempre_responde(
    cena: Callable[..., Cena], monkeypatch: pytest.MonkeyPatch
) -> None:
    c = cena()

    def quebrado(nome: str) -> Any:
        raise RuntimeError("registro quebrado")

    monkeypatch.setattr(c.jarvis.registry, "get", quebrado)

    async def cenario() -> None:
        await c.iniciar()
        s1 = c.cliente.atual
        s1.por(_acao("current_time"))
        await _esperar(lambda: bool(s1.respostas))
        assert s1.respostas[0].response["result"] == "Ação não permitida."
        await c.parar()

    _rodar(cenario)


# =================================================================== excecoes inesperadas
@pytest.mark.parametrize("onde", ["receive", "voz", "enviar_audio"])
def test_excecao_inesperada_em_qualquer_tarefa_reconecta(
    cena: Callable[..., Cena], monkeypatch: pytest.MonkeyPatch, onde: str
) -> None:
    c = cena()
    chamadas = [0]

    if onde == "voz":
        original = c.jarvis.voice.run

        async def voz_quebrada() -> None:
            chamadas[0] += 1
            if chamadas[0] == 1:
                raise ValueError("bug na voz")
            await original()

        monkeypatch.setattr(c.jarvis.voice, "run", voz_quebrada)

    async def cenario() -> None:
        c.tarefa = asyncio.create_task(c.jarvis.run())
        if onde == "voz":
            await c.conectou(2)
        else:
            await c.conectou(1)
            if onde == "receive":
                c.cliente.atual.por(KeyError("mensagem estranha"))
            else:
                c.cliente.atual.falha_ao_enviar = RuntimeError("bug ao enviar")
            await c.conectou(2)
        assert c.audio.tocou(MARCA_INTERNET) == 0  # bug nao e internet
        assert any("perdi a conexão" in t for t in c.observador.sistema())
        await c.parar()

    _rodar(cenario)


def test_janela_quebrada_nao_derruba_o_assistente(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pasta_avisos: Path
) -> None:
    c = Cena(monkeypatch, tmp_path, pasta_avisos, observer=ObservadorQuebrado())

    async def cenario() -> None:
        c.tarefa = asyncio.create_task(c.jarvis.run())
        await _esperar(lambda: len(c.cliente.sessoes) == 1)
        s1 = c.cliente.atual
        s1.por(_fala("oi"), _audio_msg(), _texto_jarvis("Olá."), _fim(), _acao("current_time"))
        await _esperar(lambda: c.audio.tocou(MARCA_MODELO) > 0 and bool(s1.respostas))
        s1.por(ConnectionError("caiu"))
        await _esperar(lambda: len(c.cliente.sessoes) == 2)
        assert c.audio.tocou(MARCA_INTERNET) > 0
        await c.parar()

    _rodar(cenario)


def test_receive_que_termina_vazio_nao_congela_o_loop(cena: Callable[..., Cena]) -> None:
    """Sessao estranha cujo receive() acaba sem mensagem: o loop precisa continuar girando."""
    c = cena()

    class SessaoVazia(SessaoFalsa):
        async def receive(self) -> AsyncIterator[Any]:
            return
            yield  # pragma: no cover

    async def cenario() -> None:
        sessao = SessaoVazia()
        tarefa = asyncio.create_task(c.jarvis._receive(sessao))
        batidas = 0
        for _ in range(20):
            await asyncio.sleep(0.005)  # se o _receive girasse sem ceder, isto nunca voltaria
            batidas += 1
        assert batidas == 20
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa

    _rodar(cenario)


# =================================================================== ElevenLabs
class _StreamQuebrado(httpx.AsyncByteStream):
    """Corpo da resposta que manda um pedaco de audio e cai no meio."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"\x09\x00" * 600
        raise httpx.ReadError("conexao caiu no meio do audio")


def _transporte(tipo: str) -> httpx.MockTransport:
    def responder(request: httpx.Request) -> httpx.Response:
        if tipo == "sem_credito":
            return httpx.Response(401, json={"detail": {"status": "quota_exceeded"}})
        if tipo == "timeout":
            raise httpx.ReadTimeout("demorou", request=request)
        if tipo == "meio":
            return httpx.Response(200, stream=_StreamQuebrado())
        return httpx.Response(500, text="erro interno")

    return httpx.MockTransport(responder)


@pytest.mark.parametrize("tipo", ["sem_credito", "timeout", "meio", "erro"])
def test_elevenlabs_falha_avisa_uma_vez_e_segue_na_voz_do_google(
    cena: Callable[..., Cena], tipo: str
) -> None:
    c = cena(elevenlabs_api_key="k", elevenlabs_voice_id="v", voice="Puck")

    async def cenario() -> None:
        assert c.jarvis.voice.uses_elevenlabs
        await c.jarvis.voice.close()  # o cliente de verdade nao e usado
        c.jarvis.voice._elevenlabs = ElevenLabsVoice("k", "v", "m", transport=_transporte(tipo))
        await c.iniciar()
        s1 = c.cliente.atual
        s1.por(_fala("Oi"), _audio_msg(), _texto_jarvis("Pois não, senhor. Em que posso"))
        s1.por(_texto_jarvis(" ajudar?"), _fim())
        await _esperar(lambda: not c.jarvis.voice.uses_elevenlabs)
        await _esperar(lambda: c.audio.tocou(MARCA_ELEVEN) == 2_400)
        if tipo != "meio":  # nada foi falado pelo ElevenLabs: toca a reserva do Google
            await _esperar(lambda: c.audio.tocou(MARCA_MODELO) > 0)
        # proximo turno ja sai direto na voz do Google
        s1.por(_fala("e agora?"), _audio_msg(b"\x08\x00"), _texto_jarvis("Agora sim."), _fim())
        await _esperar(lambda: c.audio.tocou(b"\x08\x00") > 0)
        assert c.observador.sistema().count(FALLBACK_NOTICE) == 1
        assert c.audio.tocou(MARCA_ELEVEN) == 2_400  # o aviso tocou UMA vez
        # internet caiu depois: o aviso de internet sai na voz do Google escolhida (Puck)
        s1.por(ConnectionError("caiu"))
        await c.conectou(2)
        assert c.audio.tocou(MARCA_INTERNET_PUCK) == 2_400
        assert c.audio.tocou(MARCA_INTERNET) == 0
        await c.parar()

    _rodar(cenario)


def test_elevenlabs_aviso_gravado_toca_so_uma_vez_mesmo_com_duas_falhas() -> None:
    from jarvis.assistants.elevenlabs_voice import ElevenLabsError

    class VozRuim:
        def __init__(self) -> None:
            self.chamadas = 0

        async def stream(self, text: str) -> AsyncIterator[bytes]:
            self.chamadas += 1
            raise ElevenLabsError("HTTP 401: sem creditos", 401)
            yield b""  # pragma: no cover

        async def close(self) -> None:
            pass

    async def cenario() -> None:
        fila: asyncio.Queue[bytes] = asyncio.Queue()
        observador = Gravador()
        saida = VoiceOutput(
            fila, observador, VozRuim(), aviso_elevenlabs=lambda: b"\x33\x44" * 5000
        )  # type: ignore[arg-type]
        tarefa = asyncio.create_task(saida.run())
        saida.on_model_text("Primeira. ")
        await _esperar(lambda: not saida.uses_elevenlabs)
        saida._elevenlabs = VozRuim()  # type: ignore[assignment]  # religaram e falhou de novo
        saida.on_model_text("Segunda. ")
        await _esperar(lambda: not saida.uses_elevenlabs)
        itens = []
        while not fila.empty():
            itens.append(fila.get_nowait())
        assert sum(len(i) for i in itens) == 10_000  # aviso inteiro, uma vez so
        assert all(len(i) <= 4_800 for i in itens)  # em pedacos: da para interromper
        assert observador.sistema().count(FALLBACK_NOTICE) == 1
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa

    _rodar(cenario)


def test_elevenlabs_sem_aviso_gravado_so_mostra_texto() -> None:
    from jarvis.assistants.elevenlabs_voice import ElevenLabsError

    class VozRuim:
        async def stream(self, text: str) -> AsyncIterator[bytes]:
            raise ElevenLabsError("HTTP 402")
            yield b""  # pragma: no cover

        async def close(self) -> None:
            raise RuntimeError("fechar tambem falha")

    def aviso_quebrado() -> bytes | None:
        raise OSError("disco sumiu")

    async def cenario() -> None:
        fila: asyncio.Queue[bytes] = asyncio.Queue()
        observador = Gravador()
        saida = VoiceOutput(fila, observador, VozRuim(), aviso_elevenlabs=aviso_quebrado)  # type: ignore[arg-type]
        tarefa = asyncio.create_task(saida.run())
        saida.on_model_audio(b"reserva!")
        saida.on_model_text("Olá, senhor. ")
        await _esperar(lambda: not fila.empty())
        assert fila.get_nowait() == b"reserva!"
        assert FALLBACK_NOTICE in observador.sistema()
        tarefa.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarefa

    _rodar(cenario)


# =================================================================== avisos faltando
def test_sem_nenhum_aviso_gravado_so_escreve_na_tela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    c = Cena(monkeypatch, tmp_path, tmp_path / "vazia")

    async def cenario() -> None:
        await c.iniciar()
        c.cliente.atual.por(ConnectionError("caiu"))
        await c.conectou(2)
        assert avisos.TEXTO_INTERNET in c.observador.sistema()
        assert not c.audio.tocado
        await c.parar()

    _rodar(cenario)


def test_voz_sem_aviso_proprio_usa_o_charon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pasta_avisos: Path
) -> None:
    c = Cena(monkeypatch, tmp_path, pasta_avisos, voice="Kore")  # nao tem internet_Kore.wav

    async def cenario() -> None:
        await c.iniciar()
        c.cliente.atual.por(ConnectionError("caiu"))
        await c.conectou(2)
        assert c.audio.tocou(MARCA_INTERNET) == 2_400
        await c.parar()

    _rodar(cenario)


# =================================================================== controlador
def test_controlador_liga_e_desliga_o_live_de_verdade_sem_travar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pasta_avisos: Path
) -> None:
    from jarvis.controlador import Controlador

    c = Cena(monkeypatch, tmp_path, pasta_avisos)
    observador: Gravador = c.observador

    controlador = Controlador(
        observador, lambda: c.jarvis.settings, fabrica=lambda settings, obs: c.jarvis
    )
    assert controlador.iniciar()
    limite = time.monotonic() + ESPERA_S
    while "listening" not in observador.estados:
        assert time.monotonic() < limite, "nao ficou ouvindo"
        time.sleep(0.01)
    inicio = time.monotonic()
    assert controlador.parar(espera_s=5.0)
    assert time.monotonic() - inicio < 3.0
    assert not controlador.rodando
    assert "close" in c.audio.eventos
