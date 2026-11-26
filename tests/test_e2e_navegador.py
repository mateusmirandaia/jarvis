"""Testes de ponta a ponta da janela num Chrome de verdade (sem pywebview, sem rede, sem audio).

A pagina e a de ``montar_html(montar_config(...))``, a mesma que o Jarvis entrega ao WebView2.
``window.pywebview.api`` chama a ``ApiJs`` REAL (Python) por ``expose_binding``; a ``OrbWindow``
REAL (com um ``webview`` falso) manda o JavaScript de volta para a pagina. O Google, o
ElevenLabs, o microfone e o assistente de voz sao falsos.

So roda onde houver Playwright e Chrome (senao, os testes sao pulados). Para rodar aqui:
``PYTHONPATH=<site-packages do venv> python3 -m pytest tests/test_e2e_navegador.py``.
Chrome em outro lugar: variavel ``JARVIS_CHROME``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
httpx = pytest.importorskip("httpx")

CHROME = Path(os.environ.get("JARVIS_CHROME", "/usr/bin/google-chrome"))
if not CHROME.exists():  # pragma: no cover - depende da maquina
    pytest.skip("Chrome nao encontrado (defina JARVIS_CHROME)", allow_module_level=True)

from jarvis import config  # noqa: E402
from jarvis.config import Settings  # noqa: E402
from jarvis.controlador import Controlador  # noqa: E402
from jarvis.errors import ChaveInvalidaError  # noqa: E402
from jarvis.ui import preferencias  # noqa: E402
from jarvis.ui.api_config import METODOS_PUBLICOS, ApiJs  # noqa: E402

CHAVE_BOA = "AIzaSyBOABOABOABOABOABOABOABOABOABOA"
CHAVE_RUIM = "AIzaSyRUIMRUIMRUIMRUIMRUIMRUIMRUIMRUIM"
EL_BOA = "sk_" + "a" * 40
EL_PROJETO = "sk_" + "p" * 40
VOZ_A = "21m00Tcm4TlvDq8ikWAM"
VOZ_PROJETO = "VozDoProjeto12345"


# ------------------------------------------------------------------ falsos
class _Eventos:
    def __init__(self) -> None:
        self.handlers: list[Any] = []

    def __iadd__(self, funcao: Any) -> _Eventos:
        self.handlers.append(funcao)
        return self


class _JanelaFalsa:
    def __init__(self) -> None:
        self.events = types.SimpleNamespace(loaded=_Eventos())
        self.html = ""
        self.fila: list[str] = []
        self.trava = threading.Lock()

    def evaluate_js(self, codigo: str) -> None:
        with self.trava:
            self.fila.append(codigo)


class _Gemini:
    def __init__(self, chave: str) -> None:
        self.models = self
        self.chave = chave

    def list(self, config: Any = None) -> Any:
        if self.chave == CHAVE_BOA:
            return iter(["models/x"])
        from google.genai import errors

        raise errors.ClientError(
            400, {"error": {"message": "API key not valid.", "status": "INVALID_ARGUMENT"}}
        )


def _eleven(req: Any) -> Any:
    chave = req.headers.get("xi-api-key", "")
    if chave in (EL_BOA, EL_PROJETO):
        vozes = [{"voice_id": VOZ_A, "name": "Rachel"}, {"voice_id": "pNInz6obpgDQGcFmaJgB"}]
        return httpx.Response(200, json={"voices": vozes})
    if chave.startswith("sk_semperm"):
        detalhe = {"status": "missing_permissions", "message": "missing voices_read"}
        return httpx.Response(401, json={"detail": detalhe})
    return httpx.Response(401, json={"detail": {"status": "invalid_api_key"}})


async def _eleven_async(req: Any) -> Any:
    return httpx.Response(200, content=b"\x00\x01" * 4800)


class _Microfone:
    """``pyaudio`` falso: conta quantos microfones estao abertos."""

    def __init__(self) -> None:
        self.abertos = 0
        self.paInt16 = 8
        self.PyAudio = lambda: self

    def open(self, **kwargs: Any) -> Any:
        self.abertos += 1
        dono = self

        class _Fluxo:
            def read(self, n: int, exception_on_overflow: bool = False) -> bytes:
                time.sleep(0.05)
                return (6000).to_bytes(2, "little", signed=True) * n

            def stop_stream(self) -> None:
                pass

            def close(self) -> None:
                dono.abertos -= 1

        return _Fluxo()

    def terminate(self) -> None:
        pass


class _Assistente:
    """Assistente de voz falso: diz que esta ouvindo e espera ser parado."""

    log: list[tuple[str, bool, int]] = []
    recusar_chave = False
    microfone: _Microfone | None = None

    def __init__(self, settings: Settings, observer: Any) -> None:
        self.settings = settings
        self.observer = observer

    async def run(self) -> None:
        abertos = self.microfone.abertos if self.microfone else 0
        _Assistente.log.append((self.settings.voice, self.settings.uses_elevenlabs, abertos))
        if _Assistente.recusar_chave:
            raise ChaveInvalidaError("recusada")
        self.observer.on_state("listening")
        self.observer.on_transcript("jarvis", f"Pronto, voz {self.settings.voice}.")
        await asyncio.sleep(3600)


# ------------------------------------------------------------------ mesa de teste
class Mesa:
    """Uma abertura do Jarvis: ApiJs + OrbWindow + Controlador reais e uma aba do Chrome."""

    def __init__(self, navegador: Any, pastas: dict[str, Path], largura: int, altura: int) -> None:
        from jarvis.ui.orb_window import OrbWindow

        self.pastas = pastas
        self.erros: list[str] = []
        self.links: list[str] = []
        self.tocados: list[int] = []
        self.chamadas: list[str] = []
        self.microfone = _Microfone()
        _Assistente.microfone = self.microfone
        self.janela_falsa = _JanelaFalsa()
        falso = types.ModuleType("webview")

        def criar(titulo: str, html: str = "", **kwargs: Any) -> _JanelaFalsa:
            self.janela_falsa.html = html
            return self.janela_falsa

        falso.create_window = criar  # type: ignore[attr-defined]
        falso.start = lambda *a, **k: None  # type: ignore[attr-defined]
        self._webview_antes = sys.modules.get("webview")
        sys.modules["webview"] = falso
        self.api = ApiJs(
            carregar_settings=self.carregar,
            fabrica_gemini=_Gemini,
            transporte_http=httpx.MockTransport(_eleven),
            transporte_http_async=httpx.MockTransport(_eleven_async),
            tocar=lambda dados: self.tocados.append(len(dados)),
            modulo_pyaudio=lambda: self.microfone,
            abrir_url=lambda url: self.links.append(url) or True,
            abrir_pasta=lambda pasta: self.links.append(str(pasta)) or True,
        )
        self.janela = OrbWindow(self.carregar(), api=self.api)
        self.ctrl = Controlador(self.janela, self.carregar, fabrica=_Assistente)
        self.api._ligar(controlador=self.ctrl)
        if self.carregar().has_api_key:
            self.ctrl.iniciar()
        arquivo = pastas["raiz"] / f"pagina_{largura}x{altura}_{time.monotonic_ns()}.html"
        arquivo.write_text(self.janela_falsa.html, encoding="utf-8")
        self.pg = navegador.new_page(viewport={"width": largura, "height": altura})
        self.pg.set_default_timeout(8000)
        self.pg.on(
            "console",
            lambda m: m.type in ("error", "warning") and self.erros.append(f"{m.type}: {m.text}"),
        )
        self.pg.on("pageerror", lambda e: self.erros.append(f"pageerror: {e}"))
        self.pg.expose_binding("__py", lambda fonte, nome, args: self._chamar(nome, args))
        nomes = json.dumps(list(METODOS_PUBLICOS))
        self.pg.add_init_script(
            "window.pywebview = {api: {}};"
            f"for (const n of {nomes}) window.pywebview.api[n] = (...a) => window.__py(n, a);"
        )
        self.pg.goto(arquivo.as_uri())
        for funcao in self.janela_falsa.events.loaded.handlers:
            funcao()
        self.bombear(400)

    def carregar(self) -> Settings:
        return Settings.from_env(exigir_chave=False)

    def _chamar(self, nome: str, args: list[Any]) -> Any:
        """Como o pywebview: cada chamada do JS roda numa thread nova."""
        self.chamadas.append(nome)
        caixa: dict[str, Any] = {}
        thread = threading.Thread(target=lambda: caixa.update(r=getattr(self.api, nome)(*args)))
        thread.start()
        thread.join(30)
        resposta = caixa.get("r")
        texto = json.dumps(resposta, ensure_ascii=False)
        for segredo in (CHAVE_BOA, EL_BOA, EL_PROJETO):
            assert segredo not in texto, f"segredo no retorno de {nome}"
        return resposta

    def bombear(self, ms: int) -> None:
        """Entrega a pagina o JavaScript que a OrbWindow mandou (setState, avisoChave...)."""
        fim = time.monotonic() + ms / 1000
        while True:
            with self.janela_falsa.trava:
                fila, self.janela_falsa.fila = self.janela_falsa.fila, []
            for codigo in fila:
                self.pg.evaluate(codigo)
            if time.monotonic() >= fim:
                break
            self.pg.wait_for_timeout(30)

    def ate(self, condicao_js: str, ms: int = 4000) -> bool:
        fim = time.monotonic() + ms / 1000
        while time.monotonic() < fim:
            self.bombear(60)
            if self.pg.evaluate(condicao_js):
                return True
        return False

    def texto(self, id_: str) -> str:
        return self.pg.evaluate(f"document.getElementById('{id_}').textContent")

    def visivel(self, seletor: str) -> bool:
        return self.pg.is_visible(seletor)

    def fechar(self) -> None:
        self.ctrl.parar(3)
        self.api._encerrar()
        self.pg.close()
        if self._webview_antes is not None:
            sys.modules["webview"] = self._webview_antes
        else:
            sys.modules.pop("webview", None)


@pytest.fixture(scope="module")
def navegador() -> Iterator[Any]:
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=str(CHROME),
            args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"],
        )
        yield b
        b.close()


@pytest.fixture
def pastas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Pasta do usuario com acento e espaco (como C:\\Users\\Joao Silva) e projeto sem .env."""
    raiz = tmp_path / "João Silva"
    usuario = raiz / "AppData" / "Roaming" / "Jarvis"
    projeto = raiz / "projeto"
    projeto.mkdir(parents=True)
    monkeypatch.setattr(preferencias, "caminho_preferencias", lambda: usuario / "preferencias.json")
    monkeypatch.setattr(config, "raiz_projeto", lambda: projeto)
    _Assistente.log = []
    _Assistente.recusar_chave = False
    return {"raiz": raiz, "usuario": usuario, "projeto": projeto}


@pytest.fixture
def abrir(navegador: Any, pastas: dict[str, Path]) -> Iterator[Any]:
    mesas: list[Mesa] = []

    def _abrir(largura: int = 1280, altura: int = 760) -> Mesa:
        mesa = Mesa(navegador, pastas, largura, altura)
        mesas.append(mesa)
        return mesa

    yield _abrir
    for mesa in mesas:
        mesa.fechar()


def _sem_erros(mesa: Mesa) -> None:
    # O teste de "Ouvir" no Chrome sem placa de som pode avisar; o resto tem de estar limpo.
    erros = [e for e in mesa.erros if "não consegui tocar a amostra" not in e]
    assert not erros, erros


# ------------------------------------------------------------------ fluxos
@pytest.mark.parametrize(("largura", "altura"), [(900, 600), (1280, 760), (1920, 1080)])
def test_primeira_vez_completa_e_segunda_abertura(
    abrir: Any, pastas: dict[str, Path], largura: int, altura: int
) -> None:
    m = abrir(largura, altura)
    assert m.visivel("#assistente") and not m.ctrl.rodando
    m.pg.click("#assist-avancar")  # 1 -> 2
    m.pg.click("#assist-criar-chave")
    assert m.ate("true", 100) and m.links == ["https://aistudio.google.com/apikey"]
    m.pg.click("#assist-avancar", force=True)  # aria-disabled: sem chave testada nao avanca
    assert m.pg.evaluate("document.getElementById('assistente').dataset.passo") == "2"
    m.pg.fill("#assist-chave", CHAVE_RUIM)
    m.pg.click("#assist-testar")
    assert m.ate("document.getElementById('assist-chave-res').classList.contains('erro')")
    assert "inválida" in m.texto("assist-chave-res")
    m.pg.fill("#assist-chave", CHAVE_BOA)
    m.pg.click("#assist-testar")
    assert m.ate("document.getElementById('assist-chave-res').classList.contains('ok')")
    m.pg.click("#assist-avancar")  # 2 -> 3: microfone
    assert m.ate("document.getElementById('assist-mic-res').textContent.includes('ouvindo')")
    assert m.microfone.abertos == 1
    m.pg.check("#assist-fone")
    m.pg.click("#assist-avancar")  # 3 -> 4: o microfone do teste fecha
    assert m.ate("true", 300) and m.microfone.abertos == 0
    m.pg.fill("#assist-nome", "João 🇧🇷")
    m.pg.click("#assist-vozes .cartao-voz:nth-child(3) label")  # Kore
    m.pg.click("#assist-avancar")  # 4 -> 5: permissoes (tudo desligado)
    assert m.texto("assist-passo") == "Passo 5 de 6"
    assert m.pg.is_checked("#assist-perm-arquivos-nenhum")
    assert m.visivel("#assist-pular")
    m.pg.click("#assist-pular")  # 5 -> 6: pular mantem tudo desligado
    assert not m.visivel("#assist-pular")
    assert "João 🇧🇷" in m.texto("assist-pronto-nome")
    m.pg.click("#assist-avancar")  # Comecar a usar
    assert m.ate("document.getElementById('assistente').hidden", 6000)
    assert m.ctrl.rodando and _Assistente.log[-1] == ("Kore", False, 0)
    assert m.pg.evaluate("document.getElementById('assist-chave').value") == ""
    assert CHAVE_BOA not in m.pg.content()
    prefs = preferencias.carregar()
    assert prefs["configurado"] is True and prefs["voz"] == "Kore" and prefs["fone"] is True
    assert prefs["nome"] == "João 🇧🇷"
    assert prefs["permissoes"] == {
        "arquivos": "nenhum",
        "apps": False,
        "internet": False,
        "email": False,
        "outros_drives": False,
    }
    _sem_erros(m)
    m.fechar()

    # segunda abertura: pula o assistente e ja inicia
    m2 = abrir(largura, altura)
    assert not m2.visivel("#assistente")
    assert m2.ate("document.getElementById('pilula-texto').textContent !== ''")
    assert m2.ctrl.rodando
    assert m2.ate("document.body.textContent.includes('Pronto, voz Kore.')")
    _sem_erros(m2)


def test_amostras_de_voz_tocam_na_pagina(abrir: Any) -> None:
    m = abrir()
    m.pg.click("#assist-avancar")
    m.pg.fill("#assist-chave", CHAVE_BOA)
    m.pg.click("#assist-testar")
    assert m.ate("document.getElementById('assist-chave-res').classList.contains('ok')")
    m.pg.click("#assist-avancar")  # 2 -> 3
    m.pg.click("#assist-avancar")  # 3 -> 4: vozes
    botoes = m.pg.locator("#assist-vozes .cartao-voz .botao")
    assert botoes.count() == 8  # todas as amostras existem
    for i in range(8):
        botoes.nth(i).click()
        assert m.ate(
            f"document.querySelectorAll('#assist-vozes .cartao-voz .botao')[{i}]"
            ".getAttribute('aria-pressed') === 'true'"
        ), f"amostra {i} nao tocou"
    duracao = m.pg.evaluate(
        "new Promise(r => { const a = new Audio(); a.onloadedmetadata = () => r(a.duration);"
        " a.onerror = () => r(-1); window.pywebview.api.amostra_voz('Charon')"
        ".then(x => { a.src = x.dados; }); })"
    )
    assert 1.0 < duracao < 15.0
    _sem_erros(m)


def _configurar(pastas: dict[str, Path], **prefs: Any) -> None:
    from jarvis import armazenamento

    assert armazenamento.salvar_segredos({armazenamento.GEMINI_API_KEY: CHAVE_BOA})
    assert preferencias.atualizar({"configurado": True, **prefs})


def test_troca_dos_9_visuais_persiste_e_sem_erros(abrir: Any, pastas: dict[str, Path]) -> None:
    _configurar(pastas)
    m = abrir()
    for id_visual in preferencias.VISUAIS:
        m.pg.click("#btn-trocar")
        assert m.visivel("#escolha")
        assert m.pg.locator("#grade .cartao").count() == len(preferencias.VISUAIS)
        m.pg.click(f'#grade .cartao[data-id="{id_visual}"]')
        assert m.ate("document.getElementById('escolha').hidden")
        m.bombear(450)  # fade da troca
        assert preferencias.carregar()["visual"] == id_visual
        for estado in ("listening", "thinking", "speaking", "offline", "idle"):
            m.pg.evaluate(f"window.jarvis.setState('{estado}'); window.jarvis.setLevel(0.7)")
            m.pg.wait_for_timeout(60)
    # Voltar e Esc nao mudam nada
    m.pg.click("#btn-trocar")
    m.pg.keyboard.press("Escape")
    assert m.ate("document.getElementById('escolha').hidden")
    assert preferencias.carregar()["visual"] == preferencias.VISUAIS[-1]
    _sem_erros(m)
    m.fechar()
    m2 = abrir()
    nome = m2.texto("nome-visual")
    assert nome and nome != "—"
    assert m2.pg.evaluate("document.body.dataset.paleta") in ("petroleo", "aurora", "aura")
    _sem_erros(m2)


def test_visual_salvo_que_nao_existe_mais_abre_o_padrao(
    abrir: Any, pastas: dict[str, Path]
) -> None:
    _configurar(pastas, visual="antigo_removido")
    m = abrir()
    assert m.texto("nome-visual") == "Galáxia Neural"
    _sem_erros(m)


def test_engrenagem_abas_salvar_e_aplicar(abrir: Any, pastas: dict[str, Path]) -> None:
    _configurar(pastas)
    m = abrir()
    assert m.ate("window.document.getElementById('pilula-texto').textContent !== ''")
    inicios = len(_Assistente.log)
    m.pg.click("#btn-config")
    for aba in ("geral", "permissoes", "chave", "elevenlabs", "sobre"):
        m.pg.click(f"#cfg-aba-{aba}")
        assert m.visivel(f"#cfg-painel-{aba}")
    m.pg.click("#cfg-aba-geral")
    m.pg.fill("#cfg-nome", "Ana")
    m.pg.click("#cfg-vozes .cartao-voz:nth-child(2) label")  # Puck
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('ok')", 8000)
    assert len(_Assistente.log) == inicios + 1 and _Assistente.log[-1][0] == "Puck"
    assert preferencias.carregar()["nome"] == "Ana"
    # nada mudou
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').textContent === 'Nada mudou.'")
    # aba Chave: so os 4 ultimos caracteres; trocar por uma chave ruim nao salva
    m.pg.click("#cfg-aba-chave")
    assert m.texto("cfg-chave-final") == "…" + CHAVE_BOA[-4:]
    m.pg.fill("#cfg-chave", CHAVE_RUIM)
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('erro')", 6000)
    assert m.carregar().api_key == CHAVE_BOA
    # Sobre: links da lista fechada
    m.pg.click("#cfg-aba-sobre")
    for botao in ("#cfg-abrir-repo", "#cfg-abrir-config", "#cfg-abrir-logs"):
        m.pg.click(botao)
    assert m.ate("true", 200)
    assert m.links[0] == "https://github.com/mateusmirandaia/jarvis"
    assert "João Silva" in m.links[1]
    # fechar com mudanca pendente pede confirmacao
    m.pg.click("#cfg-aba-geral")
    m.pg.fill("#cfg-nome", "Outra")
    m.pg.click("#config-fechar")
    assert m.visivel("#config")
    m.pg.click("#config-fechar")
    assert not m.visivel("#config")
    _sem_erros(m)


def test_elevenlabs_ligar_testar_e_desligar(abrir: Any, pastas: dict[str, Path]) -> None:
    _configurar(pastas)
    m = abrir()
    m.pg.click("#btn-config")
    m.pg.click("#cfg-aba-elevenlabs")
    m.pg.fill("#cfg-el-chave", "sk_sempermXXXXXXXXXXXXXXXX")
    m.pg.click("#cfg-el-buscar")
    assert m.ate("document.getElementById('cfg-el-buscar-res').textContent.includes('Voices')")
    assert m.visivel("#cfg-el-manual")
    m.pg.fill("#cfg-el-chave", EL_BOA)
    m.pg.click("#cfg-el-buscar")
    assert m.ate("document.querySelectorAll('#cfg-el-lista label').length === 2")
    m.pg.click("#cfg-el-lista label:nth-child(1)")
    m.pg.click("#cfg-el-testar")
    assert m.visivel("#cfg-el-confirmar")  # avisa que gasta creditos antes
    m.pg.click("#cfg-el-confirmar-sim")
    assert m.ate("document.getElementById('cfg-el-res').classList.contains('ok')")
    assert m.tocados == [9600]
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('ok')", 8000)
    assert _Assistente.log[-1][1] is True  # reiniciou com o ElevenLabs
    assert m.carregar().elevenlabs_voice_id == VOZ_A
    # Geral: volta para a voz do Google sem apagar a chave
    m.pg.click("#cfg-aba-geral")
    m.pg.check("#cfg-fonte-google")
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('ok')", 8000)
    assert _Assistente.log[-1][1] is False and m.carregar().elevenlabs_configurado
    m.pg.check("#cfg-fonte-eleven")
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('ok')", 8000)
    assert _Assistente.log[-1][1] is True
    # desligar de vez
    m.pg.click("#cfg-aba-elevenlabs")
    m.pg.click("#cfg-el-desligar")
    assert m.ate("document.getElementById('cfg-el-res').classList.contains('ok')", 8000)
    assert _Assistente.log[-1][1] is False and not m.carregar().elevenlabs_configurado
    _sem_erros(m)


def test_elevenlabs_no_env_do_projeto_cenario_do_mateus(
    abrir: Any, pastas: dict[str, Path]
) -> None:
    (pastas["projeto"] / ".env").write_text(
        f"GEMINI_API_KEY={CHAVE_BOA}\nELEVENLABS_API_KEY={EL_PROJETO}\n"
        f"ELEVENLABS_VOICE_ID={VOZ_PROJETO}\n",
        encoding="utf-8",
    )
    m = abrir()
    assert not m.visivel("#assistente")
    assert m.ate("document.body.textContent.includes('Pronto, voz')")
    assert _Assistente.log[-1][1] is True
    m.pg.click("#btn-config")
    m.pg.click("#cfg-aba-chave")
    assert m.visivel("#cfg-chave-projeto")  # avisa que a chave vem do .env do projeto
    # desligar: fica guardada no projeto, mas passa a usar a voz do Google
    m.pg.click("#cfg-aba-elevenlabs")
    m.pg.click("#cfg-el-desligar")
    assert m.ate("document.getElementById('cfg-el-res').classList.contains('ok')", 8000)
    assert "projeto" in m.texto("cfg-el-res")
    assert _Assistente.log[-1][1] is False
    # religar pela aba Geral
    m.pg.click("#cfg-aba-geral")
    m.pg.check("#cfg-fonte-eleven")
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('ok')", 8000)
    assert _Assistente.log[-1][1] is True
    # escolher OUTRA voz na janela: o .env do projeto continua mandando, e a janela avisa
    m.pg.click("#cfg-aba-elevenlabs")
    m.pg.fill("#cfg-el-chave", EL_BOA)
    m.pg.click("#cfg-el-buscar")
    assert m.ate("document.querySelectorAll('#cfg-el-lista label').length === 2")
    m.pg.click("#cfg-el-lista label:nth-child(1)")
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('ok')", 8000)
    assert ".env da pasta do projeto" in m.texto("config-status")
    _sem_erros(m)


def test_chave_recusada_mostra_aviso_e_atualizar(abrir: Any, pastas: dict[str, Path]) -> None:
    _configurar(pastas)
    _Assistente.recusar_chave = True
    m = abrir()
    assert m.ate("!document.getElementById('aviso-chave').hidden")
    assert "Atualizar chave" in m.texto("aviso-chave-texto")
    m.pg.click("#btn-aviso-atualizar")
    assert m.ate("document.querySelector('[role=tab][aria-selected=true]').id === 'cfg-aba-chave'")
    _Assistente.recusar_chave = False
    m.pg.fill("#cfg-chave", CHAVE_BOA)
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('ok')", 8000)
    assert m.ctrl.rodando and m.visivel("#aviso-chave") is False
    _sem_erros(m)


def test_hud_com_centenas_de_falas_e_rajadas(abrir: Any, pastas: dict[str, Path]) -> None:
    _configurar(pastas, visual="cortex")
    m = abrir()
    for i in range(400):
        m.janela.on_transcript("voce" if i % 2 else "jarvis", f"fala {i} " + "palavra " * (i % 30))
        m.janela.on_tool(f"ferramenta_{i % 17}", i % 5 != 0)
        m.janela.on_latency(0.3 + (i % 10) / 10)
        m.janela.on_level((i % 100) / 100)
        m.janela.on_state(("listening", "thinking", "speaking")[i % 3])
    m.bombear(1500)
    tamanho = m.pg.evaluate(
        "({conversa: document.querySelectorAll('#lista-conversa li').length,"
        " atividade: document.querySelectorAll('#lista-atividade li').length,"
        " nos: document.getElementsByTagName('*').length})"
    )
    assert tamanho["conversa"] <= 6 and tamanho["atividade"] <= 12
    assert tamanho["nos"] < 2500
    assert "fala 399" in m.texto("legenda-grande") or "fala 398" in m.texto("legenda-grande")
    # rajada direta de setLevel/setState: nada quebra e o quadro continua andando
    m.pg.evaluate(
        "for (let i = 0; i < 20000; i++) { window.jarvis.setLevel(Math.random());"
        " window.jarvis.setState(['idle','listening','thinking','speaking'][i % 4]); }"
    )
    quadros = m.pg.evaluate(
        "new Promise(r => { let n = 0; const f = () => { n++; if (n < 30) requestAnimationFrame(f);"
        " else r(n); }; requestAnimationFrame(f); })"
    )
    assert quadros == 30
    _sem_erros(m)


def test_pagina_fora_do_app_nao_quebra(navegador: Any, pastas: dict[str, Path]) -> None:
    """Abrindo o orb.html cru no navegador (sem pywebview e sem os marcadores substituidos)."""
    from jarvis.ui.orb_window import ORB_HTML

    pg = navegador.new_page(viewport={"width": 900, "height": 600})
    erros: list[str] = []
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and erros.append(m.text))
    pg.goto(ORB_HTML.as_uri())
    pg.wait_for_timeout(500)
    assert pg.is_hidden("#assistente")  # sem JARVIS_CONFIG: abre direto no visual
    pg.click("#btn-config")
    pg.click("#cfg-aba-chave")
    pg.fill("#cfg-chave", CHAVE_BOA)
    pg.click("#cfg-testar")
    pg.wait_for_timeout(200)
    assert "fora do app" in pg.evaluate("document.getElementById('cfg-chave-res').textContent")
    pg.close()
    assert not erros, erros
