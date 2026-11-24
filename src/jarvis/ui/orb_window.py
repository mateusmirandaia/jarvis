"""Janela do orb: mostra o Jarvis com um dos visuais animados, reagindo ao estado e a voz.

Usa o ``pywebview`` (no Windows, o WebView2 do Edge, que ja vem no Windows 10/11).
O ``pywebview`` so e importado quando a janela e criada, para que testes e o modo
terminal funcionem sem ele.

O pywebview recebe o HTML como texto (sem arquivos relativos), entao ``montar_html()``
injeta no ``orb.html`` a configuracao inicial (``window.JARVIS_CONFIG``) e o codigo de cada
visual de ``ui/visuais/*.js``.
"""

from __future__ import annotations

import html
import json
import logging
import math
import queue
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jarvis.assistants.observer import Speaker, State
from jarvis.errors import ConfigError
from jarvis.ui import preferencias

if TYPE_CHECKING:
    from jarvis.config import Settings

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent
ORB_HTML = UI_DIR / "orb.html"
VISUAIS_DIR = UI_DIR / "visuais"
ICON_FILE = UI_DIR / "jarvis.ico"

WINDOW_SIZE = (1280, 760)
MIN_SIZE = (900, 600)
BACKGROUND = "#030605"
LEVEL_INTERVAL_S = 1 / 30  # no maximo 30 atualizacoes de volume por segundo
LEVEL_MIN_CHANGE = 0.02

MARCADOR_CONFIG = "/*JARVIS_CONFIG*/"
MARCADOR_VISUAIS = "<!--JARVIS_VISUAIS-->"
_FIM_DE_SCRIPT = re.compile(r"</(script)", re.IGNORECASE)


def montar_config(settings: Settings | None = None) -> dict[str, Any]:
    """Monta o ``window.JARVIS_CONFIG`` que o orb.html le ao abrir.

    Args:
        settings: configuracoes do Jarvis; None usa so a preferencia salva e ``info`` vazio.

    Returns:
        ``{"visual": id | None, "primeiraVez": bool, "info": {...}}``. ``primeiraVez`` e True
        quando ainda nao ha visual escolhido (a janela abre a tela de escolha).
    """
    forcado = settings.visual if settings is not None else ""
    visual = preferencias.visual_inicial(forcado)
    info: dict[str, Any] = {}
    if settings is not None:
        info = {
            "voz": "ElevenLabs" if settings.uses_elevenlabs else settings.voice,
            "modelo": settings.live_model,
            "fone": settings.headphones,
            "nome": settings.user_name,
        }
    return {"visual": visual, "primeiraVez": visual is None, "info": info}


def _json_para_script(valor: Any) -> str:
    """Serializa em JSON seguro para ficar dentro de um ``<script>`` (sem ``</`` nem ``<!--``)."""
    texto = json.dumps(valor, ensure_ascii=False)
    return texto.replace("</", "<\\/").replace("<!--", "<\\u0021--")


def _scripts_dos_visuais(pasta: Path) -> str:
    """Um ``<script>`` por ``visuais/*.js``, em ordem alfabetica do nome do arquivo."""
    try:
        arquivos = sorted(pasta.glob("*.js"), key=lambda caminho: caminho.name)
    except OSError:
        logger.warning("nao consegui listar a pasta de visuais %s", pasta, exc_info=True)
        return ""
    blocos: list[str] = []
    for arquivo in arquivos:
        try:
            codigo = arquivo.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning("nao consegui ler o visual %s", arquivo.name, exc_info=True)
            continue
        # Um "</script" dentro do codigo fecharia a tag antes da hora.
        codigo = _FIM_DE_SCRIPT.sub(r"<\\/\1", codigo)
        nome = html.escape(arquivo.stem, quote=True)
        blocos.append(f'<script data-visual="{nome}">\n{codigo}\n</script>')
    return "\n".join(blocos)


def montar_html(
    config: dict[str, Any],
    *,
    html_path: Path | None = None,
    visuais_dir: Path | None = None,
) -> str:
    """Le o orb.html e injeta a configuracao e os visuais nos marcadores.

    Substitui ``/*JARVIS_CONFIG*/`` por ``window.JARVIS_CONFIG = {...};`` e
    ``<!--JARVIS_VISUAIS-->`` por um ``<script>`` para cada visual. Se um marcador nao existir,
    o HTML segue sem aquela parte (e fica um aviso no log).

    Args:
        config: o objeto ``JARVIS_CONFIG`` (veja ``montar_config``).
        html_path: arquivo HTML; None usa ``ORB_HTML``.
        visuais_dir: pasta dos .js; None usa ``VISUAIS_DIR``.

    Returns:
        O HTML pronto para o ``webview.create_window(html=...)``.
    """
    pagina = (html_path or ORB_HTML).read_text(encoding="utf-8")
    if MARCADOR_CONFIG in pagina:
        injecao = f"window.JARVIS_CONFIG = {_json_para_script(config)};"
        pagina = pagina.replace(MARCADOR_CONFIG, injecao, 1)
    else:
        logger.warning("orb.html sem o marcador %s: configuracao nao injetada", MARCADOR_CONFIG)
    if MARCADOR_VISUAIS in pagina:
        scripts = _scripts_dos_visuais(visuais_dir or VISUAIS_DIR)
        pagina = pagina.replace(MARCADOR_VISUAIS, scripts, 1)
    else:
        logger.warning("orb.html sem o marcador %s: visuais nao injetados", MARCADOR_VISUAIS)
    return pagina


class _ApiJs:
    """Objeto exposto ao JavaScript como ``window.pywebview.api``.

    O pywebview expoe todo metodo e atributo publico deste objeto. Por isso ele tem um unico
    metodo publico e nenhum atributo: nada alem de salvar o visual fica ao alcance da pagina.
    """

    def salvar_visual(self, id_visual: object) -> bool:
        """Salva o visual escolhido na tela de escolha; devolve True se gravou."""
        try:
            return preferencias.salvar_visual(id_visual)
        except Exception:  # noqa: BLE001 - nunca levanta para o JavaScript
            logger.debug("falha ao salvar o visual", exc_info=True)
            return False


class OrbWindow:
    """Janela do orb (1280x760, minimo 900x600). Implementa o ``AssistantObserver``.

    Todos os metodos ``on_*`` podem ser chamados de qualquer thread, nunca levantam e
    nunca bloqueiam: eles so enfileiram o comando. Uma thread propria envia o JavaScript
    para a janela. Assim a animacao nunca atrasa o audio (o ``evaluate_js`` espera a
    janela responder, e isso nao pode acontecer no loop de voz).
    Se a janela ainda nao carregou, o ultimo estado fica guardado e e aplicado depois.
    """

    def __init__(self, settings: Settings | None = None, title: str = "Jarvis") -> None:
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
        self._commands: queue.Queue[str] = queue.Queue()  # estado, legendas e acoes, em ordem
        self._pending_level: str | None = None  # volume: so o mais recente importa
        self._wake = threading.Event()
        threading.Thread(target=self._dispatch_loop, name="orb-js", daemon=True).start()
        self._window: Any = webview.create_window(
            title,
            html=montar_html(montar_config(settings)),
            js_api=_ApiJs(),
            width=WINDOW_SIZE[0],
            height=WINDOW_SIZE[1],
            min_size=MIN_SIZE,
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

    def on_tool(self, name: str, ok: bool) -> None:
        """Mostra a acao executada no log "Atividade" do HUD."""
        try:
            code = f"window.jarvis.addTool({json.dumps(str(name))}, {json.dumps(bool(ok))})"
        except Exception:  # noqa: BLE001 - nunca levanta para o assistente
            logger.debug("acao invalida para o orb: %r", name, exc_info=True)
            return
        self._enqueue(code)

    def on_latency(self, seconds: float) -> None:
        """Mostra o atraso ate a resposta (grafico e numero de latencia do HUD)."""
        try:
            value = float(seconds)
        except (TypeError, ValueError):
            return
        if not math.isfinite(value) or value < 0:
            return
        self._enqueue(f"window.jarvis.setLatency({json.dumps(round(value, 3))})")

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
