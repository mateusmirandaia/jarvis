"""Rodada 0.9 (robustez): avisos gravados, classificacao das quedas, tempo limite no config,
gerador dos avisos, empacotamento, fechamento do audio e a janela que nunca bloqueia.

Sem rede, sem microfone, sem janela de verdade. Tudo com tempo maximo.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
import time
import types
import wave
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from jarvis import avisos
from jarvis.config import Settings, pasta_pacote

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "gerar_avisos_voz.py"
SPEC = RAIZ / "packaging" / "jarvis.spec"
VOZES = ("Charon", "Puck", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr")
CHAVE_FALSA = "AIzaFALSAfalsaFALSAfalsaFALSA12345"


def _wav(
    caminho: Path, quadros: bytes = b"\x01\x02" * 100, taxa: int = 24_000, canais: int = 1
) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(quadros)
    return caminho


# =================================================================== jarvis/avisos.py
def test_textos_dos_avisos_com_acento() -> None:
    assert avisos.TEXTO_INTERNET == (
        "Desculpe, estou tendo problemas com a sua internet. "
        "Aguarde um momento ou tente daqui a pouco."
    )
    assert avisos.TEXTO_ELEVENLABS == (
        "Minha voz personalizada está com problemas. Vou continuar com a voz padrão."
    )


def test_pasta_dos_avisos_e_a_do_pacote_e_existe_no_repo() -> None:
    assert avisos.pasta_avisos() == pasta_pacote() / "avisos"
    assert avisos.pasta_avisos().is_dir()
    assert (avisos.pasta_avisos() / "LEIA.md").is_file()


def test_pasta_dos_avisos_congelado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No instalador (PyInstaller) os avisos ficam em sys._MEIPASS/jarvis/avisos."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert avisos.pasta_avisos() == tmp_path / "jarvis" / "avisos"
    _wav(tmp_path / "jarvis" / "avisos" / "internet_Charon.wav")
    assert avisos.pcm_aviso("internet", "Charon") == b"\x01\x02" * 100


def test_modulo_avisos_nao_e_confundido_com_a_pasta() -> None:
    """``jarvis/avisos.py`` e a pasta ``jarvis/avisos/`` convivem: o import pega o modulo."""
    assert Path(avisos.__file__).name == "avisos.py"


def test_voz_pedida_depois_charon_depois_nada(tmp_path: Path) -> None:
    _wav(tmp_path / "internet_Charon.wav", b"\x0c\x00" * 10)
    _wav(tmp_path / "internet_Puck.wav", b"\x0d\x00" * 10)
    assert avisos.pcm_aviso("internet", "Puck", tmp_path) == b"\x0d\x00" * 10
    assert avisos.pcm_aviso("internet", "Kore", tmp_path) == b"\x0c\x00" * 10  # falta: Charon
    for ruim in ("../Puck", "puck", "", None, 7, "Puck.wav"):  # voz desconhecida: Charon
        assert avisos.pcm_aviso("internet", ruim, tmp_path) == b"\x0c\x00" * 10
    assert avisos.pcm_aviso("elevenlabs", "Charon", tmp_path) is None  # nada: so texto
    assert avisos.pcm_aviso("internet", "Puck", tmp_path / "nao_existe") is None


def test_candidatos_nao_sai_da_pasta(tmp_path: Path) -> None:
    nomes = [c.name for c in avisos.candidatos("internet", "../../x", tmp_path)]
    assert nomes == ["internet_Charon.wav"]
    assert all(c.parent == tmp_path for c in avisos.candidatos("internet", "Zephyr", tmp_path))


@pytest.mark.parametrize(
    "estrago",
    ["taxa_errada", "estereo", "nao_e_wav", "vazio", "pasta", "grande"],
)
def test_aviso_estragado_cai_para_o_charon(tmp_path: Path, estrago: str) -> None:
    _wav(tmp_path / "internet_Charon.wav", b"\x0c\x00" * 10)
    ruim = tmp_path / "internet_Leda.wav"
    if estrago == "taxa_errada":
        _wav(ruim, taxa=16_000)
    elif estrago == "estereo":
        _wav(ruim, canais=2)
    elif estrago == "nao_e_wav":
        ruim.write_bytes(b"isto nao e um wav")
    elif estrago == "vazio":
        _wav(ruim, quadros=b"")
    elif estrago == "pasta":
        ruim.mkdir()
    else:
        ruim.write_bytes(b"RIFF" + bytes(avisos.MAX_BYTES + 1))
    assert avisos.pcm_aviso("internet", "Leda", tmp_path) == b"\x0c\x00" * 10


def test_aviso_trocado_no_disco_e_relido(tmp_path: Path) -> None:
    arquivo = _wav(tmp_path / "internet_Orus.wav", b"\x01\x00" * 10)
    assert avisos.pcm_aviso("internet", "Orus", tmp_path) == b"\x01\x00" * 10
    time.sleep(0.01)
    _wav(arquivo, b"\x02\x00" * 20)
    assert avisos.pcm_aviso("internet", "Orus", tmp_path) == b"\x02\x00" * 20


def test_duracao_do_aviso() -> None:
    assert avisos.duracao_s(bytes(48_000)) == pytest.approx(1.0)


def test_limite_de_aviso_30_s() -> None:
    agora = [100.0]
    limite = avisos.LimiteDeAviso(30.0, lambda: agora[0])
    assert limite.pode()
    agora[0] += 29.9
    assert not limite.pode()
    agora[0] += 0.2
    assert limite.pode()
    assert not limite.pode()


def test_padrao_do_limite_e_30_s() -> None:
    assert avisos.INTERVALO_INTERNET_S == 30.0


# =================================================================== tipo da queda
@pytest.fixture
def genai_errors() -> ModuleType:
    return pytest.importorskip("google.genai.errors")


def _api(genai_errors: ModuleType, codigo: int, mensagem: str = "x") -> Exception:
    return genai_errors.APIError(codigo, {"error": {"message": mensagem}})


def test_tipo_de_queda(genai_errors: ModuleType) -> None:
    import socket

    import httpx
    from websockets.exceptions import ConnectionClosedError

    from jarvis.errors import SemRespostaError, marcar_dispositivo, tipo_de_queda

    assert tipo_de_queda(_api(genai_errors, 1008, "API key not valid")) == "chave"
    assert tipo_de_queda(_api(genai_errors, 401)) == "chave"
    assert tipo_de_queda(_api(genai_errors, 429, "RESOURCE_EXHAUSTED")) == "cota"
    assert tipo_de_queda(_api(genai_errors, 1011, "Quota exceeded for model")) == "cota"
    for codigo in (500, 503, 1006, 1011, 1013):
        assert tipo_de_queda(_api(genai_errors, codigo, "internal")) == "rede", codigo
    assert tipo_de_queda(_api(genai_errors, 1000, "bye")) == "encerrada"
    for erro in (
        ConnectionResetError("reset"),
        TimeoutError(),
        socket.gaierror(11001, "getaddrinfo failed"),
        OSError(10065, "host inalcancavel"),
        SemRespostaError("mudo"),
        httpx.ConnectError("sem rede"),
        ConnectionClosedError(None, None),
    ):
        assert tipo_de_queda(erro) == "rede", erro
    assert tipo_de_queda(ValueError("bug")) == "outro"
    assert tipo_de_queda(KeyError("bug")) == "outro"
    mic = OSError(-9999, "Unanticipated host error")
    marcar_dispositivo(mic, "microfone")
    assert tipo_de_queda(mic) == "audio"


def test_tipo_de_queda_dentro_do_taskgroup(genai_errors: ModuleType) -> None:
    from jarvis.errors import (
        SemRespostaError,
        dispositivo_do_erro,
        marcar_dispositivo,
        tipo_de_queda,
    )

    assert tipo_de_queda(ExceptionGroup("tg", [SemRespostaError("mudo")])) == "rede"
    falante = RuntimeError("alto-falante nao foi aberto")
    marcar_dispositivo(falante, "alto-falante")
    grupo = ExceptionGroup("tg", [falante])
    assert tipo_de_queda(grupo) == "audio"
    assert dispositivo_do_erro(grupo) == "alto-falante"
    # 1000 do Google vem com o ConnectionClosedOK como contexto: continua "encerrada"
    try:
        try:
            raise ConnectionError("fechou")
        except ConnectionError:
            raise _api(genai_errors, 1000, "bye") from None
    except Exception as erro:  # noqa: BLE001
        erro.__context__ = ConnectionError("fechou")
        assert tipo_de_queda(erro) == "encerrada"


def test_marcar_dispositivo_nunca_levanta() -> None:
    from jarvis.errors import dispositivo_do_erro, marcar_dispositivo

    class SemAtributo(Exception):
        __slots__ = ()

        def __setattr__(self, nome: str, valor: Any) -> None:
            raise AttributeError("nao aceita")

    erro = SemAtributo()
    marcar_dispositivo(erro, "microfone")  # nao levanta
    assert dispositivo_do_erro(erro) is None
    ok = OSError("x")
    marcar_dispositivo(ok, "microfone")
    marcar_dispositivo(ok, "alto-falante")  # a primeira marca vale
    assert dispositivo_do_erro(ok) == "microfone"


# =================================================================== config
def test_tempo_limite_padrao_12_s() -> None:
    assert Settings(api_key="x").resposta_timeout_s == 12.0


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("8", 8.0), ("7,5", 7.5), ("0", 3.0), ("999", 120.0), ("abc", 12.0), ("nan", 12.0)],
)
def test_tempo_limite_pelo_ambiente(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, valor: str, esperado: float
) -> None:
    monkeypatch.setenv("JARVIS_RESPOSTA_TIMEOUT_S", valor)
    settings = Settings.from_env(
        tmp_path / "nao.env",
        exigir_chave=False,
        env_usuario=tmp_path / "nao_usuario.env",
        preferencias_arquivo=tmp_path / "p.json",
    )
    assert settings.resposta_timeout_s == esperado


# =================================================================== gerar_avisos_voz.py
@pytest.fixture
def gerador() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("gerar_avisos_voz", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gerar_avisos_voz"] = modulo
    spec.loader.exec_module(modulo)
    yield modulo
    sys.modules.pop("gerar_avisos_voz", None)
    sys.modules.pop("gerar_amostras_voz", None)


@pytest.fixture
def sem_chave(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, gerador: ModuleType) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(gerador.amostras, "pasta_usuario", lambda: tmp_path / "sem_usuario")
    monkeypatch.setattr(gerador, "RAIZ_PROJETO", tmp_path / "sem_projeto")


class _ClienteFalso:
    """Cliente do Gemini falso: devolve um WAV 24 kHz e guarda os pedidos."""

    def __init__(self, taxa: int = 24_000) -> None:
        self.chamadas: list[dict[str, Any]] = []
        self.models = self
        self.taxa = taxa

    def generate_content(self, model: str, contents: Any, config: Any) -> Any:
        self.chamadas.append({"model": model, "contents": contents, "config": config})
        import io

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.taxa)
            w.writeframes(b"\x01\x00" * 2400)
        inline = types.SimpleNamespace(data=buffer.getvalue(), mime_type="audio/wav")
        parte = types.SimpleNamespace(inline_data=inline)
        return types.SimpleNamespace(
            candidates=[types.SimpleNamespace(content=types.SimpleNamespace(parts=[parte]))]
        )


def _texto_pedido(chamada: dict[str, Any]) -> str:
    return chamada["contents"][0].parts[0].text


def test_gerador_reaproveita_as_amostras_e_textos_batem(gerador: ModuleType) -> None:
    assert gerador.VOZES == VOZES
    assert gerador.TEXTO_INTERNET == avisos.TEXTO_INTERNET
    assert gerador.TEXTO_ELEVENLABS == avisos.TEXTO_ELEVENLABS
    assert gerador.MODELO_PADRAO == gerador.amostras.MODELO_PADRAO
    assert gerador.PASTA_AVISOS == RAIZ / "src" / "jarvis" / "avisos"
    ajuda = gerador._parser().format_help()
    for opcao in ("--forcar", "--vozes", "--modelo", "--saida", "--pausa"):
        assert opcao in ajuda


def test_gerador_faz_os_9_avisos_e_pula_os_prontos(
    gerador: ModuleType,
    sem_chave: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", CHAVE_FALSA)
    cliente = _ClienteFalso()
    monkeypatch.setattr(gerador.amostras, "_criar_cliente", lambda chave: cliente)
    saida = tmp_path / "avisos"
    assert gerador.main(["--saida", str(saida), "--pausa", "0"]) == 0
    esperados = {f"internet_{v}.wav" for v in VOZES} | {"elevenlabs_Charon.wav"}
    assert {p.name for p in saida.glob("*.wav")} == esperados
    for arquivo in saida.glob("*.wav"):
        assert avisos.ler_pcm(arquivo) is not None  # o Jarvis consegue tocar
    textos = [_texto_pedido(c) for c in cliente.chamadas]
    assert textos.count(avisos.TEXTO_INTERNET) == 8
    assert textos.count(avisos.TEXTO_ELEVENLABS) == 1
    saida_texto = capsys.readouterr()
    assert CHAVE_FALSA not in saida_texto.out + saida_texto.err
    # de novo: tudo pronto, nenhum pedido ao Google
    assert gerador.main(["--saida", str(saida), "--pausa", "0"]) == 0
    assert len(cliente.chamadas) == 9


def test_gerador_so_algumas_vozes(gerador: ModuleType, tmp_path: Path) -> None:
    cliente = _ClienteFalso()
    saida = tmp_path / "avisos"
    assert gerador.main(["--vozes", "puck", "--saida", str(saida), "--pausa", "0"], cliente) == 0
    assert [p.name for p in saida.glob("*.wav")] == ["internet_Puck.wav"]
    assert gerador.main(["--vozes", "Jarvisson", "--saida", str(saida)], cliente) == 2


def test_gerador_sem_chave(
    gerador: ModuleType, sem_chave: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gerador.main(["--saida", str(tmp_path / "a"), "--pausa", "0"]) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_gerador_recusa_formato_errado_e_nao_mostra_a_chave(
    gerador: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    saida = tmp_path / "avisos"
    codigo = gerador.main(
        ["--vozes", "Kore", "--saida", str(saida), "--pausa", "0"], _ClienteFalso(taxa=16_000)
    )
    assert codigo == 1
    assert not list(saida.glob("*.wav"))  # nada no formato errado fica na pasta

    class ClienteQueVaza(_ClienteFalso):
        def generate_content(self, model: str, contents: Any, config: Any) -> Any:
            raise RuntimeError(f"falhou com a chave {CHAVE_FALSA}")

    capsys.readouterr()
    assert (
        gerador.main(["--vozes", "Kore", "--saida", str(saida), "--pausa", "0"], ClienteQueVaza())
        == 1
    )
    assert CHAVE_FALSA not in capsys.readouterr().err


# =================================================================== empacotamento
def test_spec_leva_os_avisos() -> None:
    import ast

    texto = SPEC.read_text(encoding="utf-8")
    ast.parse(texto)
    assert '"avisos"' in texto
    assert '"jarvis/avisos"' in texto
    assert 'AVISOS.glob("*.wav")' in texto


def test_gitignore_versiona_os_avisos() -> None:
    texto = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    assert "!src/jarvis/avisos/*.wav" in texto


# =================================================================== AudioIO
class _FluxoPreso:
    """Stream do PyAudio cujo read fica preso (microfone arrancado no meio da leitura)."""

    def __init__(self) -> None:
        self.soltar = threading.Event()
        self.fechado = False

    def read(self, n: int, exception_on_overflow: bool = False) -> bytes:
        self.soltar.wait(5)
        return bytes(n * 2)

    def write(self, data: bytes) -> None:
        self.soltar.wait(5)

    def close(self) -> None:
        self.fechado = True


@pytest.fixture
def audio_io(monkeypatch: pytest.MonkeyPatch):
    fluxos: list[_FluxoPreso] = []

    class _PA:
        def open(self, **kwargs: Any) -> _FluxoPreso:
            fluxo = _FluxoPreso()
            fluxos.append(fluxo)
            return fluxo

        def terminate(self) -> None:
            pass

    falso = types.ModuleType("pyaudio")
    falso.PyAudio = _PA  # type: ignore[attr-defined]
    falso.paInt16 = 8  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyaudio", falso)
    from jarvis.assistants import audio

    monkeypatch.setattr(audio, "CLOSE_WAIT_S", 0.2)
    return audio.AudioIO(), fluxos


def test_fechar_microfone_preso_nao_trava(audio_io) -> None:
    io_, fluxos = audio_io
    io_.open_mic()
    leitor = threading.Thread(target=io_.read_mic, daemon=True)
    leitor.start()
    time.sleep(0.05)  # a leitura esta presa segurando a trava
    inicio = time.monotonic()
    io_.close()  # o que o run() faz ao parar
    assert time.monotonic() - inicio < 1.0
    fluxos[0].soltar.set()
    leitor.join(2)
    io_.close_mic()
    assert fluxos[0].fechado


def test_reabrir_fecha_o_anterior(audio_io) -> None:
    io_, fluxos = audio_io
    io_.open_speaker()
    io_.open_speaker()
    assert fluxos[0].fechado and not fluxos[1].fechado
    io_.open_mic()
    io_.open_mic()
    assert fluxos[2].fechado and not fluxos[3].fechado
    io_.close()
    assert all(f.fechado for f in fluxos)


# =================================================================== janela
class _Eventos:
    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, handler: Any) -> _Eventos:
        self.handlers.append(handler)
        return self


class _JanelaFalsa:
    def __init__(self) -> None:
        self.events = types.SimpleNamespace(loaded=_Eventos())
        self.js: list[str] = []
        self.modo = "ok"  # "presa" = evaluate_js nunca volta; "fechada" = levanta
        self.soltar = threading.Event()

    def evaluate_js(self, code: str) -> None:
        if self.modo == "presa":
            self.soltar.wait(5)
        if self.modo == "fechada":
            raise RuntimeError("a janela foi fechada")
        self.js.append(code)


@pytest.fixture
def janela(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from jarvis.ui import preferencias
    from jarvis.ui.orb_window import OrbWindow

    falsa = _JanelaFalsa()
    webview = types.ModuleType("webview")
    webview.create_window = lambda *a, **k: falsa  # type: ignore[attr-defined]
    webview.start = lambda *a, **k: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(preferencias, "caminho_preferencias", lambda: tmp_path / "p.json")
    orb = OrbWindow()
    for handler in falsa.events.loaded.handlers:
        handler()
    yield orb, falsa
    falsa.soltar.set()


def _rajada(orb: Any) -> float:
    """Tudo o que o assistente manda para a janela numa conversa agitada; devolve o tempo."""
    inicio = time.monotonic()
    for i in range(2_000):
        orb.on_state(("listening", "thinking", "speaking", "offline")[i % 4])
        orb.on_level((i % 10) / 10)
        orb.on_transcript("sistema", avisos.TEXTO_INTERNET)
        orb.on_tool("open_app", i % 2 == 0)
        orb.on_latency(0.4)
    orb.on_aviso_chave("A chave parou")
    return time.monotonic() - inicio


def test_janela_presa_nao_bloqueia_o_assistente(janela) -> None:
    orb, falsa = janela
    falsa.modo = "presa"  # WebView2 travado: evaluate_js nunca volta
    assert _rajada(orb) < 2.0


def test_janela_fechada_e_ignorada(janela) -> None:
    orb, falsa = janela
    falsa.modo = "fechada"
    assert _rajada(orb) < 2.0
    time.sleep(0.2)  # a thread da janela engole os erros e continua viva
    falsa.modo = "ok"
    orb.on_transcript("jarvis", "voltei")
    limite = time.monotonic() + 3
    while not any("voltei" in c for c in falsa.js):
        assert time.monotonic() < limite, "a thread da janela morreu"
        time.sleep(0.01)


def test_chamadas_da_janela_vindas_de_varias_threads(janela) -> None:
    orb, _falsa = janela
    erros: list[BaseException] = []

    def martelar() -> None:
        try:
            _rajada(orb)
        except BaseException as erro:  # noqa: BLE001
            erros.append(erro)

    threads = [threading.Thread(target=martelar) for _ in range(4)]
    inicio = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not erros
    assert time.monotonic() - inicio < 8.0
