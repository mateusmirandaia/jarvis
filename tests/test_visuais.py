"""Testes dos visuais escolhiveis (v0.6.0): preferencias, injecao no HTML e eventos novos.

Tudo sem janela e sem rede: so funcoes puras e o LiveAssistant com observadores falsos.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import warnings
from pathlib import Path

import pytest

from jarvis.assistants.observer import NullObserver
from jarvis.config import Settings
from jarvis.tools import ToolRegistry
from jarvis.ui import orb_window, preferencias
from jarvis.ui.orb_window import ORB_HTML, VISUAIS_DIR, montar_config, montar_html
from jarvis.ui.preferencias import VISUAIS

# --------------------------------------------------------------------------- preferencias


@pytest.fixture
def pref(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Aponta o arquivo de preferencias para uma pasta temporaria (que ainda nao existe)."""
    arquivo = tmp_path / "config" / "jarvis" / "preferencias.json"
    monkeypatch.setattr(preferencias, "caminho_preferencias", lambda: arquivo)
    return arquivo


def test_visuais_tem_os_nove_ids() -> None:
    assert VISUAIS == (
        "galaxia",
        "globo",
        "cortex",
        "reator",
        "holograma",
        "mapa",
        "esfera",
        "aura",
        "cerebro",
    )
    assert preferencias.VISUAL_PADRAO == "galaxia"
    assert VISUAIS[0] == preferencias.VISUAL_PADRAO  # primeiro cartao da tela de escolha


def test_caminho_fica_fora_do_projeto(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(preferencias.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert preferencias.caminho_preferencias() == (
        tmp_path / "Roaming" / "Jarvis" / "preferencias.json"
    )
    monkeypatch.setattr(preferencias.sys, "platform", "linux")
    caminho = preferencias.caminho_preferencias()
    assert caminho.parts[-3:] == (".config", "jarvis", "preferencias.json")


def test_sem_arquivo_carrega_vazio(pref: Path) -> None:
    assert preferencias.carregar() == {}


def test_salvar_e_carregar_ida_e_volta(pref: Path) -> None:
    assert preferencias.salvar_visual("reator") is True
    assert pref.exists()
    assert preferencias.carregar() == {"visual": "reator"}
    assert preferencias.salvar_visual("aura") is True
    assert preferencias.carregar()["visual"] == "aura"
    # escrita atomica: nenhum temporario esquecido na pasta
    assert [p.name for p in pref.parent.iterdir()] == ["preferencias.json"]


@pytest.mark.parametrize("invalido", ["", "Reator", "inexistente", "../globo", None, 3])
def test_id_invalido_nao_grava(pref: Path, invalido: object) -> None:
    assert preferencias.salvar_visual(invalido) is False
    assert not pref.exists()


def test_arquivo_corrompido_carrega_vazio_e_salvar_recupera(pref: Path) -> None:
    pref.parent.mkdir(parents=True)
    pref.write_text("{isto nao e json", encoding="utf-8")
    assert preferencias.carregar() == {}
    assert preferencias.salvar_visual("mapa") is True
    assert json.loads(pref.read_text(encoding="utf-8")) == {"visual": "mapa"}


def test_json_que_nao_e_objeto_carrega_vazio(pref: Path) -> None:
    pref.parent.mkdir(parents=True)
    pref.write_text("[1, 2, 3]", encoding="utf-8")
    assert preferencias.carregar() == {}


def test_salvar_preserva_outras_chaves(pref: Path) -> None:
    pref.parent.mkdir(parents=True)
    pref.write_text(json.dumps({"tema": "escuro", "visual": "globo"}), encoding="utf-8")
    assert preferencias.salvar_visual("esfera") is True
    assert preferencias.carregar() == {"tema": "escuro", "visual": "esfera"}


def test_falha_de_escrita_devolve_false(pref: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pref.parent.mkdir(parents=True)
    pref.write_text(json.dumps({"visual": "globo"}), encoding="utf-8")

    def disco_cheio(origem: str, destino: object) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(preferencias.os, "replace", disco_cheio)
    assert preferencias.salvar_visual("cortex") is False
    assert preferencias.carregar() == {"visual": "globo"}  # o arquivo antigo ficou inteiro
    assert [p.name for p in pref.parent.iterdir()] == ["preferencias.json"]


def test_pasta_bloqueada_devolve_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bloqueio = tmp_path / "arquivo"
    bloqueio.write_text("x", encoding="utf-8")  # um arquivo no lugar da pasta
    monkeypatch.setattr(
        preferencias, "caminho_preferencias", lambda: bloqueio / "jarvis" / "preferencias.json"
    )
    assert preferencias.salvar_visual("globo") is False
    assert preferencias.carregar() == {}


# ------------------------------------------------------------------ visual inicial


def test_visual_inicial_sem_nada_e_none(pref: Path) -> None:
    assert preferencias.visual_inicial("") is None


def test_visual_inicial_usa_o_salvo(pref: Path) -> None:
    preferencias.salvar_visual("holograma")
    assert preferencias.visual_inicial("") == "holograma"


def test_visual_inicial_env_tem_prioridade(pref: Path) -> None:
    preferencias.salvar_visual("holograma")
    assert preferencias.visual_inicial("aura") == "aura"


def test_visual_inicial_env_invalido_e_ignorado(pref: Path) -> None:
    assert preferencias.visual_inicial("matrix") is None
    preferencias.salvar_visual("mapa")
    assert preferencias.visual_inicial("matrix") == "mapa"


def test_visual_inicial_salvo_invalido_e_ignorado(pref: Path) -> None:
    pref.parent.mkdir(parents=True)
    pref.write_text(json.dumps({"visual": "matrix"}), encoding="utf-8")
    assert preferencias.visual_inicial("") is None


def test_settings_le_jarvis_visual(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv (e nao o .env) para o monkeypatch restaurar o ambiente depois do teste
    monkeypatch.setenv("GEMINI_API_KEY", "abc123")
    monkeypatch.setenv("JARVIS_VISUAL", " Reator ")
    vazio = tmp_path / ".env"
    vazio.write_text("", encoding="utf-8")
    assert Settings.from_env(vazio).visual == "reator"
    monkeypatch.setenv("JARVIS_VISUAL", "")
    assert Settings.from_env(vazio).visual == ""


def test_settings_visual_padrao_vazio() -> None:
    assert Settings(api_key="x").visual == ""


def test_montar_config_primeira_vez_abre_na_galaxia(pref: Path) -> None:
    settings = Settings(api_key="x", user_name="Carlos", headphones=True)
    config = montar_config(settings)
    assert config["visual"] == "galaxia" and config["primeiraVez"] is True
    assert config["info"] == {
        "voz": "Charon",
        "modelo": settings.live_model,
        "fone": True,
        "nome": "Carlos",
    }
    assert "api_key" not in json.dumps(config)  # a chave nunca vai para a pagina


def test_montar_config_com_preferencia_e_env(pref: Path) -> None:
    preferencias.salvar_visual("esfera")
    assert montar_config(Settings(api_key="x"))["visual"] == "esfera"
    config = montar_config(Settings(api_key="x", visual="cortex"))
    assert config["visual"] == "cortex" and config["primeiraVez"] is False
    assert montar_config(None)["info"] == {}


def test_montar_config_env_invalido_cai_no_padrao(pref: Path) -> None:
    config = montar_config(Settings(api_key="x", visual="matrix"))
    assert config["visual"] == "galaxia" and config["primeiraVez"] is True


# ------------------------------------------------------------------ montar_html

_MODELO = (
    "<!doctype html><html><head><script>/*JARVIS_CONFIG*/</script></head>"
    "<body><script>window.JarvisVisuais = {registrar() {}};</script>"
    "<!--JARVIS_VISUAIS--><script>/* shell */</script></body></html>"
)


def _modelo(tmp_path: Path) -> Path:
    arquivo = tmp_path / "orb.html"
    arquivo.write_text(_MODELO, encoding="utf-8")
    return arquivo


def _config_injetada(pagina: str) -> dict:
    achado = re.search(r"window\.JARVIS_CONFIG = (.*?);</script>", pagina)
    assert achado, "JARVIS_CONFIG nao foi injetado"
    return json.loads(achado.group(1))


def test_montar_html_injeta_config_parseavel(tmp_path: Path) -> None:
    config = {"visual": "reator", "primeiraVez": False, "info": {"nome": "Zé </script> <!--"}}
    pagina = montar_html(config, html_path=_modelo(tmp_path), visuais_dir=tmp_path / "vazia")
    assert "/*JARVIS_CONFIG*/" not in pagina and "<!--JARVIS_VISUAIS-->" not in pagina
    assert _config_injetada(pagina) == config
    assert pagina.lower().count("</script") == 3  # o texto do nome nao fechou a tag


def test_montar_html_injeta_todos_os_visuais_em_ordem(tmp_path: Path) -> None:
    arquivos = sorted(VISUAIS_DIR.glob("*.js"))
    assert arquivos, "a pasta ui/visuais precisa ter ao menos um .js"
    pagina = montar_html({}, html_path=_modelo(tmp_path))
    posicoes = []
    for arquivo in arquivos:
        marca = f'<script data-visual="{arquivo.stem}">'
        assert marca in pagina
        posicoes.append(pagina.index(marca))
    assert posicoes == sorted(posicoes)
    # os visuais entram depois do registro e antes do script do shell
    assert pagina.index("window.JarvisVisuais") < posicoes[0]
    assert posicoes[-1] < pagina.index("/* shell */")


def test_montar_html_escapa_fim_de_script_dos_visuais(tmp_path: Path) -> None:
    pasta = tmp_path / "visuais"
    pasta.mkdir()
    (pasta / "b.js").write_text('const s = "</SCRIPT><b>oi</b>";', encoding="utf-8")
    (pasta / "a.js").write_text("const a = 1;", encoding="utf-8")
    (pasta / "leia-me.txt").write_text("nao e js", encoding="utf-8")
    pagina = montar_html({}, html_path=_modelo(tmp_path), visuais_dir=pasta)
    assert "<\\/SCRIPT><b>oi</b>" in pagina
    assert pagina.index('data-visual="a"') < pagina.index('data-visual="b"')
    assert "nao e js" not in pagina


def test_montar_html_sem_marcadores_ainda_funciona(tmp_path: Path) -> None:
    simples = tmp_path / "simples.html"
    simples.write_text("<html><body>orb</body></html>", encoding="utf-8")
    assert montar_html({"visual": None}, html_path=simples) == "<html><body>orb</body></html>"


def test_montar_html_real_sem_internet() -> None:
    pagina = montar_html({"visual": "globo", "primeiraVez": False, "info": {}})
    assert "http" not in pagina.lower()


def test_orb_html_tem_os_dois_marcadores() -> None:
    html = ORB_HTML.read_text(encoding="utf-8")
    assert "/*JARVIS_CONFIG*/" in html
    assert "<!--JARVIS_VISUAIS-->" in html


def test_cada_visual_tem_arquivo_e_registra_o_proprio_id() -> None:
    """Cada id de VISUAIS tem visuais/<id>.js e vice-versa; cada arquivo registra o proprio id."""
    arquivos = {arquivo.stem for arquivo in VISUAIS_DIR.glob("*.js")}
    assert arquivos == set(VISUAIS), (
        f"faltando: {sorted(set(VISUAIS) - arquivos)}; sobrando: {sorted(arquivos - set(VISUAIS))}"
    )
    for id_visual in VISUAIS:
        codigo = (VISUAIS_DIR / f"{id_visual}.js").read_text(encoding="utf-8")
        padrao = rf"registrar\(\s*\{{[\s\S]*?\bid\s*:\s*[\"']{id_visual}[\"']"
        assert re.search(padrao, codigo), f'{id_visual}.js nao registra id: "{id_visual}"'
        assert "http" not in codigo.lower(), f"{id_visual}.js carrega algo da internet"


# ------------------------------------------------------------------ API do JavaScript


def test_api_js_so_expoe_a_lista_do_contrato(pref: Path) -> None:
    from jarvis.ui.api_config import METODOS_PUBLICOS

    api = orb_window._ApiJs()
    publicos = [nome for nome in dir(api) if not nome.startswith("_")]
    assert publicos == sorted(METODOS_PUBLICOS)
    assert all(nome.startswith("_") for nome in vars(api))  # nenhum atributo publico
    assert api.salvar_visual("globo") is True
    assert api.salvar_visual("nada") is False
    assert api.salvar_visual({"id": "globo"}) is False


def test_api_js_nunca_levanta(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(id_visual: object) -> bool:
        raise RuntimeError("inesperado")

    monkeypatch.setattr(preferencias, "salvar_visual", explode)
    assert orb_window._ApiJs().salvar_visual("globo") is False


# ------------------------------------------------------------------ observador / LiveAssistant


def test_null_observer_aceita_eventos_novos() -> None:
    observer = NullObserver()
    observer.on_tool("current_time", True)
    observer.on_latency(0.9)


class _ObservadorNovo:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def on_state(self, state: str) -> None:
        self.events.append(("state", state))

    def on_level(self, level: float) -> None:
        self.events.append(("level", level))

    def on_transcript(self, speaker: str, text: str) -> None:
        self.events.append(("transcript", (speaker, text)))

    def on_tool(self, name: str, ok: bool) -> None:
        self.events.append(("tool", (name, ok)))

    def on_latency(self, seconds: float) -> None:
        self.events.append(("latency", seconds))


class _ObservadorAntigo:
    """Observador de antes da v0.6.0: sem on_tool nem on_latency."""

    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def on_state(self, state: str) -> None:
        self.events.append(("state", state))

    def on_level(self, level: float) -> None:
        self.events.append(("level", level))

    def on_transcript(self, speaker: str, text: str) -> None:
        self.events.append(("transcript", (speaker, text)))


class _ObservadorQueExplode(_ObservadorNovo):
    def on_tool(self, name: str, ok: bool) -> None:
        raise RuntimeError("janela fechada")

    def on_latency(self, seconds: float) -> None:
        raise RuntimeError("janela fechada")


def _live(tmp_path: Path, observer: object):
    pytest.importorskip("google.genai")
    from jarvis.assistants.live_assistant import LiveAssistant

    settings = Settings(api_key="x", project_root=tmp_path)
    registry = ToolRegistry(settings, confirm=lambda title, message: False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return LiveAssistant(settings, registry, observer=observer)


def _tools(observer: _ObservadorNovo) -> list[object]:
    return [value for kind, value in observer.events if kind == "tool"]


def test_live_emite_on_tool_com_sucesso(tmp_path: Path) -> None:
    observer = _ObservadorNovo()
    assistant = _live(tmp_path, observer)
    asyncio.run(assistant._execute("current_time", {}))
    assert _tools(observer) == [("current_time", True)]


def test_live_emite_on_tool_false_quando_falha(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observer = _ObservadorNovo()
    assistant = _live(tmp_path, observer)
    asyncio.run(assistant._execute("run_command", {"cmd": "del"}))  # nao permitida
    asyncio.run(assistant._execute("current_time", {"inventado": 1}))  # vira "ERRO:"
    monkeypatch.setattr(assistant.registry, "timeout_for", lambda name, settings: 0.05)
    monkeypatch.setattr(assistant.registry, "get", lambda name: lambda: time.sleep(0.5) or "ok")
    asyncio.run(assistant._execute("lenta", {}))  # estourou o tempo

    def quebra() -> str:
        raise ValueError("bug")

    monkeypatch.setattr(assistant.registry, "get", lambda name: quebra)
    asyncio.run(assistant._execute("quebrada", {}))  # excecao fora do safe_tool
    assert _tools(observer) == [
        ("run_command", False),
        ("current_time", False),
        ("lenta", False),
        ("quebrada", False),
    ]


def test_live_emite_on_latency_uma_vez_por_resposta(tmp_path: Path) -> None:
    observer = _ObservadorNovo()
    assistant = _live(tmp_path, observer)
    assistant._log_latency()  # ainda nao ouviu nada: nao mede
    assistant._heard_at, assistant._answer_logged = time.monotonic() - 0.5, False
    assistant._log_latency()
    assistant._log_latency()  # o mesmo turno nao conta duas vezes
    latencias = [value for kind, value in observer.events if kind == "latency"]
    assert len(latencias) == 1 and 0.5 <= latencias[0] < 5


def test_live_funciona_com_observador_antigo(tmp_path: Path) -> None:
    observer = _ObservadorAntigo()
    assistant = _live(tmp_path, observer)
    assert asyncio.run(assistant._execute("current_time", {})) != ""
    assistant._heard_at, assistant._answer_logged = time.monotonic(), False
    assistant._log_latency()
    assistant._notify_turn("oi", "Ola, senhor.")
    assert ("transcript", ("jarvis", "Ola, senhor.")) in observer.events


def test_live_observador_que_explode_nao_derruba(tmp_path: Path) -> None:
    observer = _ObservadorQueExplode()
    assistant = _live(tmp_path, observer)
    resultado = asyncio.run(assistant._execute("current_time", {}))
    assert not resultado.startswith("ERRO:")
    assistant._heard_at, assistant._answer_logged = time.monotonic(), False
    assistant._log_latency()


def test_orb_html_ordem_dos_cartoes_igual_a_visuais() -> None:
    html = ORB_HTML.read_text(encoding="utf-8")
    achado = re.search(r"const ORDEM = \[([^\]]*)\]", html)
    assert achado, "orb.html sem a lista ORDEM"
    assert tuple(re.findall(r'"([a-z]+)"', achado.group(1))) == VISUAIS


def test_orb_html_tem_a_paleta_nuvem_completa() -> None:
    html = ORB_HTML.read_text(encoding="utf-8")
    assert 'body[data-paleta="nuvem"]' in html
    bloco = re.search(r"nuvem: \{([^}]*)\}", html)
    assert bloco, "PALETAS.nuvem nao encontrado"
    cores = dict(re.findall(r'(\w+): "(#[0-9A-Fa-f]{6})"', bloco.group(1)))
    esperado = {
        "fundo": "#041012",
        "superficie": "#08201F",
        "linha": "#12403D",
        "texto": "#F0EEE9",
        "texto2": "#8FB8B2",
        "primaria": "#2BA79B",
        "escura": "#1E7F7A",
        "clara": "#9FE3DA",
        "destaque": "#F0EEE9",
        "erro": "#FF6B6B",
        "ouvindo": "#5FC8BE",
        "pensando": "#9FE3DA",
        "falando": "#F0EEE9",
    }
    assert cores == esperado
