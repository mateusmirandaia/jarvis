"""Testes do orb, do observador e do atalho (sem janela, sem microfone, sem Windows)."""

from __future__ import annotations

import array
import asyncio
import re
import warnings
from pathlib import Path

import pytest

from jarvis.__main__ import _build_parser
from jarvis.assistants.observer import NullObserver, pcm_level
from jarvis.config import Settings
from jarvis.os_integration import shortcut, windows
from jarvis.tools import ToolRegistry
from jarvis.ui import preferencias
from jarvis.ui.orb_window import ICON_FILE, ORB_HTML, VISUAIS_DIR


class FakeObserver:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def on_state(self, state: str) -> None:
        self.events.append(("state", state))

    def on_level(self, level: float) -> None:
        self.events.append(("level", level))

    def on_transcript(self, speaker: str, text: str) -> None:
        self.events.append(("transcript", (speaker, text)))


def _pcm(value: int, samples: int = 256) -> bytes:
    return array.array("h", [value, -value] * (samples // 2)).tobytes()


def test_pcm_level_silencio_e_zero() -> None:
    assert pcm_level(b"") == 0.0
    assert pcm_level(_pcm(0)) == 0.0


def test_pcm_level_cresce_com_o_volume_e_satura_em_1() -> None:
    baixo, alto = pcm_level(_pcm(500)), pcm_level(_pcm(4000))
    assert 0.0 < baixo < alto <= 1.0
    assert pcm_level(_pcm(32000)) == 1.0


def test_pcm_level_ignora_byte_sobrando() -> None:
    assert pcm_level(_pcm(1000) + b"\x01") == pytest.approx(pcm_level(_pcm(1000)))


def test_null_observer_nao_faz_nada() -> None:
    observer = NullObserver()
    observer.on_state("speaking")
    observer.on_level(0.5)
    observer.on_transcript("jarvis", "oi")


def test_html_do_orb_expoe_a_api_usada_pelo_python() -> None:
    html = ORB_HTML.read_text(encoding="utf-8")
    for trecho in ("window.jarvis", "setState", "setLevel", "addLine", "addTool", "setLatency"):
        assert trecho in html
    for estado in ("idle", "listening", "thinking", "speaking", "offline"):
        assert estado in html
    # Nada carregado da internet: nenhuma URL (o "http-equiv" da CSP nao conta).
    assert not re.search(r"https?://", html, re.IGNORECASE)
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)
    assert csp and not re.search(r"https?:|//", csp.group(1)), "a CSP nao pode liberar URL"
    for visual in sorted(VISUAIS_DIR.glob("*.js")):
        texto = visual.read_text(encoding="utf-8")
        assert not re.search(r"https?://", texto, re.IGNORECASE), visual.name


def test_icone_existe() -> None:
    assert ICON_FILE.exists() and ICON_FILE.stat().st_size > 0


def test_cli_padrao_e_orb_e_aceita_atalho() -> None:
    parser = _build_parser()
    assert parser.parse_args([]).modo == "orb"
    assert parser.parse_args(["--modo", "voz"]).modo == "voz"
    assert parser.parse_args(["--criar-atalho"]).criar_atalho is True


def test_atalho_fora_do_windows_so_avisa(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(shortcut, "IS_WINDOWS", False)
    assert "Windows" in shortcut.create_desktop_shortcut(tmp_path)


def test_instancia_unica_fora_do_windows_libera(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows, "IS_WINDOWS", False)
    assert windows.acquire_single_instance("teste") is True


@pytest.fixture
def live(tmp_path: Path):
    pytest.importorskip("google.genai")
    from jarvis.assistants.live_assistant import LiveAssistant

    settings = Settings(api_key="x", project_root=tmp_path)
    registry = ToolRegistry(settings, confirm=lambda title, message: False)
    observer = FakeObserver()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assistant = LiveAssistant(settings, registry, observer=observer)
    return assistant, observer


def test_live_envia_falas_do_turno_ao_observador(live) -> None:
    assistant, observer = live
    assistant._notify_turn("  que horas sao  ", "Sao dez, senhor.")
    assert ("transcript", ("voce", "que horas sao")) in observer.events
    assert ("transcript", ("jarvis", "Sao dez, senhor.")) in observer.events


def test_live_queda_avisa_o_orb(live, monkeypatch: pytest.MonkeyPatch) -> None:
    assistant, observer = live

    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    asyncio.run(assistant._handle_disconnect(RuntimeError("rede caiu")))
    assert ("state", "offline") in observer.events
    assert any(kind == "transcript" and value[0] == "sistema" for kind, value in observer.events)
    assert ("level", 0.0) in observer.events


def test_live_ao_tocar_audio_informa_volume(live) -> None:
    assistant, observer = live

    class FakeAudio:
        def __init__(self) -> None:
            self.written: list[bytes] = []

        def write_speaker(self, data: bytes) -> None:
            self.written.append(data)

    assistant.audio = FakeAudio()
    data = _pcm(3000, samples=3000)  # 6000 bytes -> 3 fatias
    asyncio.run(assistant._play(data))
    assert b"".join(assistant.audio.written) == data
    levels = [value for kind, value in observer.events if kind == "level"]
    assert len(levels) == 3 and all(level > 0 for level in levels)


class _FakeEvent:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _FakeWindow:
    def __init__(self) -> None:
        self.events = type("Events", (), {})()
        self.events.loaded = _FakeEvent()
        self.js: list[str] = []

    def evaluate_js(self, code: str) -> None:
        self.js.append(code)


class _FakeWebview:
    def __init__(self) -> None:
        self.window = _FakeWindow()
        self.started_with = None
        self.created_with: dict = {}

    def create_window(self, *args, **kwargs):
        self.created_with = kwargs
        return self.window

    def start(self, func, icon=None):
        self.started_with = (func, icon)


@pytest.fixture
def orb(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import sys

    from jarvis.ui.orb_window import OrbWindow

    fake = _FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(
        preferencias, "caminho_preferencias", lambda: tmp_path / "preferencias.json"
    )
    return OrbWindow(), fake


def _load(fake: _FakeWebview) -> None:
    for handler in fake.window.events.loaded.handlers:
        handler()


def _wait_js(fake: _FakeWebview, predicate, timeout: float = 1.0) -> bool:
    """O envio de JS roda numa thread propria: espera ate a condicao valer."""
    import time

    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate(fake.window.js):
            return True
        time.sleep(0.01)
    return False


def test_orb_so_manda_js_depois_de_carregar(orb) -> None:
    window, fake = orb
    window.on_state("listening")
    assert not _wait_js(fake, lambda js: js, timeout=0.1)  # ainda nao carregou
    _load(fake)
    assert _wait_js(fake, lambda js: js and js[-1] == 'window.jarvis.setState("listening")')


def test_orb_escapa_texto_da_legenda(orb) -> None:
    window, fake = orb
    _load(fake)
    window.on_transcript("jarvis", 'Diga "ola" </script>')
    assert _wait_js(fake, lambda js: any('\\"ola\\"' in code for code in js))


def test_orb_limita_frequencia_do_volume(orb) -> None:
    window, fake = orb
    _load(fake)
    assert _wait_js(fake, lambda js: len(js) >= 1)
    for _ in range(50):
        window.on_level(0.5)  # mesmo valor repetido: nao reenvia
    assert _wait_js(fake, lambda js: "window.jarvis.setLevel(0.500)" in js)
    assert sum(code.startswith("window.jarvis.setLevel") for code in fake.window.js) == 1
    window.on_level(0.0)  # silencio sempre passa (o orb precisa "desligar")
    assert _wait_js(fake, lambda js: js[-1] == "window.jarvis.setLevel(0.000)")


def test_orb_on_nunca_bloqueia_quem_chama(orb) -> None:
    import time

    window, fake = orb
    _load(fake)

    def slow(code: str) -> None:
        time.sleep(0.2)  # janela lenta para responder

    fake.window.evaluate_js = slow
    start = time.monotonic()
    for i in range(20):
        window.on_level(i / 20)
        window.on_state("speaking" if i % 2 else "listening")
    assert time.monotonic() - start < 0.1  # o loop de voz nao espera a janela


def test_orb_nunca_quebra_se_a_janela_falhar(orb) -> None:
    window, fake = orb
    for handler in fake.window.events.loaded.handlers:
        handler()

    def explode(code: str) -> None:
        raise RuntimeError("janela fechada")

    fake.window.evaluate_js = explode
    window.on_state("speaking")
    window.on_transcript("sistema", "teste")


def test_orb_start_roda_o_assistente_em_thread(orb) -> None:
    window, fake = orb
    window.start(lambda: None)
    func, icon = fake.started_with
    assert callable(func)
    assert icon is None or icon.endswith("jarvis.ico")


def test_orb_janela_grande_com_api_do_visual(orb) -> None:
    _window, fake = orb
    kwargs = fake.created_with
    assert (kwargs["width"], kwargs["height"]) == (1280, 760)
    assert kwargs["min_size"] == (900, 600)
    from jarvis.ui.api_config import METODOS_PUBLICOS

    publicos = [n for n in dir(kwargs["js_api"]) if not n.startswith("_")]
    assert publicos == sorted(METODOS_PUBLICOS)
    assert "/*JARVIS_CONFIG*/" not in kwargs["html"]


def test_orb_envia_acoes_e_latencia(orb) -> None:
    window, fake = orb
    _load(fake)
    window.on_tool('abre "isso"', True)
    window.on_tool("delete_to_trash", False)
    window.on_latency(0.91234)
    window.on_latency(float("nan"))  # ignorado
    window.on_latency("lixo")  # type: ignore[arg-type]  # ignorado, sem levantar
    assert _wait_js(fake, lambda js: "window.jarvis.setLatency(0.912)" in js)
    assert 'window.jarvis.addTool("abre \\"isso\\"", true)' in fake.window.js
    assert 'window.jarvis.addTool("delete_to_trash", false)' in fake.window.js
    assert sum(code.startswith("window.jarvis.setLatency") for code in fake.window.js) == 1
