"""Janela do orb: mostra o Jarvis como uma esfera animada que reage ao estado e a voz.

Usa o ``pywebview`` (no Windows, o WebView2 do Edge, que ja vem no Windows 10/11).
O ``pywebview`` so e importado quando a janela e criada, para que testes e o modo
terminal funcionem sem ele.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jarvis.assistants.observer import Speaker, State
from jarvis.errors import ConfigError

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent
ORB_HTML = UI_DIR / "orb.html"
ICON_FILE = UI_DIR / "jarvis.ico"

WINDOW_SIZE = (420, 540)
BACKGROUND = "#030605"
LEVEL_INTERVAL_S = 1 / 30  # no maximo 30 atualizacoes de volume por segundo
LEVEL_MIN_CHANGE = 0.02


class OrbWindow:
    """Janela do orb. Implementa o ``AssistantObserver`` do LiveAssistant.

    Todos os metodos ``on_*`` podem ser chamados de qualquer thread, nunca levantam e
    nunca bloqueiam: eles so enfileiram o comando. Uma thread propria envia o JavaScript
    para a janela. Assim a animacao nunca atrasa o audio (o ``evaluate_js`` espera a
    janela responder, e isso nao pode acontecer no loop de voz).
    Se a janela ainda nao carregou, o ultimo estado fica guardado e e aplicado depois.
    """

    def __init__(self, title: str = "Jarvis") -> None:
        try:
            import webview
        except ImportError as error:  # pragma: no cover - depende do ambiente
            raise ConfigError(
                "O modo orb precisa do pywebview. Instale com: python -m pip install pywebview "
                "(ou use jarvis --modo voz)."
            ) from error
        self._webview = webview
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._state: State = "idle"
        self._last_level = 0.0
        self._last_level_at = 0.0
        self._commands: queue.Queue[str] = queue.Queue()  # estado e legendas, em ordem
        self._pending_level: str | None = None  # volume: so o mais recente importa
        self._wake = threading.Event()
        threading.Thread(target=self._dispatch_loop, name="orb-js", daemon=True).start()
        self._window: Any = webview.create_window(
            title,
            html=ORB_HTML.read_text(encoding="utf-8"),
            width=WINDOW_SIZE[0],
            height=WINDOW_SIZE[1],
            min_size=(320, 400),
            background_color=BACKGROUND,
        )
        self._window.events.loaded += self._on_loaded

    # ------------------------------------------------------------------ ciclo de vida
    def start(self, worker: Callable[[], None]) -> None:
        """Abre a janela (bloqueia ate ela ser fechada) e roda ``worker`` numa thread.

        Args:
            worker: funcao que roda o assistente (ex.: o loop do LiveAssistant).
        """
        thread = threading.Thread(target=worker, name="jarvis-assistente", daemon=True)
        icon = str(ICON_FILE) if ICON_FILE.exists() else None
        self._webview.start(thread.start, icon=icon)

    def _on_loaded(self) -> None:
        self._ready.set()
        self._enqueue(f"window.jarvis.setState({json.dumps(self._state)})")

    # ------------------------------------------------------------ AssistantObserver
    def on_state(self, state: State) -> None:
        """Muda a animacao do orb (em espera, ouvindo, pensando, falando, sem conexao)."""
        with self._lock:
            if state == self._state:
                return
            self._state = state
        self._enqueue(f"window.jarvis.setState({json.dumps(state)})")

    def on_level(self, level: float) -> None:
        """Atualiza o volume (0 a 1), com limite de frequencia para nao pesar."""
        now = time.monotonic()
        with self._lock:
            changed = abs(level - self._last_level) >= LEVEL_MIN_CHANGE or level == 0.0
            if not changed or (now - self._last_level_at < LEVEL_INTERVAL_S and level != 0.0):
                return
            self._last_level, self._last_level_at = level, now
            self._pending_level = f"window.jarvis.setLevel({level:.3f})"
        self._wake.set()

    def on_transcript(self, speaker: Speaker, text: str) -> None:
        """Mostra a ultima fala como legenda embaixo do orb."""
        self._enqueue(f"window.jarvis.addLine({json.dumps(speaker)}, {json.dumps(text)})")

    # ------------------------------------------------------------------ utilitario
    def _enqueue(self, code: str) -> None:
        """Agenda um comando para a janela (nao bloqueia quem chamou)."""
        self._commands.put(code)
        self._wake.set()

    def _dispatch_loop(self) -> None:
        """Thread que envia os comandos a janela: estados/legendas em ordem, volume mais recente."""
        while True:
            self._wake.wait()
            self._wake.clear()
            while not self._commands.empty():
                self._run_js(self._commands.get_nowait())
            with self._lock:
                level, self._pending_level = self._pending_level, None
            if level is not None:
                self._run_js(level)

    def _run_js(self, code: str) -> None:
        """Executa JavaScript na janela; ignora erros (janela fechando, ainda carregando)."""
        if not self._ready.is_set():
            return
        try:
            self._window.evaluate_js(code)
        except Exception:  # noqa: BLE001 - a interface nunca pode derrubar o assistente
            logger.debug("falha ao atualizar o orb", exc_info=True)
