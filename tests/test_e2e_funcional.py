"""Testes funcionais de ponta a ponta e de borda do Jarvis 0.8.0 (lado Python).

Cobrem o caminho que a pessoa faz (primeira vez, segunda abertura, engrenagem, ElevenLabs,
chave recusada) e o que costuma quebrar no Windows de verdade: .env com BOM/CRLF/UTF-16/ANSI,
preferencias.json estragado, pasta com acento e espaco, APPDATA ausente, nome com emoji,
corridas no controlador e no teste do microfone, comandos para a janela antes de ela carregar.
Sem rede, sem janela e sem microfone (tudo falso). A pagina no Chrome fica em
``test_e2e_navegador.py``.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import threading
import time
import types
import wave
from pathlib import Path
from typing import Any

import pytest

from jarvis import armazenamento, config, vozes
from jarvis.config import Settings
from jarvis.controlador import Controlador
from jarvis.errors import ChaveInvalidaError
from jarvis.microfone import TesteMicrofone as _MedidorMic
from jarvis.ui import preferencias
from jarvis.ui.api_config import METODOS_PUBLICOS, ApiJs, ponte_js

CHAVE = "AIzaSyE2E_chave_de_teste_000000000000000"
CHAVE_PROJETO = "AIzaSyE2E_chave_do_projeto_11111111111"
EL = "sk_" + "e" * 40
EL_PROJETO = "sk_" + "p" * 40
VOZ_EL = "21m00Tcm4TlvDq8ikWAM"
VOZ_PROJETO = "VozDoProjeto12345"


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def pastas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Pasta do usuario com acento e espaco (como C:\\Users\\Joao Silva\\AppData\\Roaming)."""
    usuario = tmp_path / "João Silva" / "AppData" / "Roaming" / "Jarvis"
    projeto = tmp_path / "Meus Projetos" / "jarvis"
    projeto.mkdir(parents=True)
    monkeypatch.setattr(preferencias, "caminho_preferencias", lambda: usuario / "preferencias.json")
    monkeypatch.setattr(config, "raiz_projeto", lambda: projeto)
    return {"usuario": usuario, "projeto": projeto, "env": usuario / ".env"}


def _settings() -> Settings:
    return Settings.from_env(exigir_chave=False)


class _Gemini:
    def __init__(self, chave: str) -> None:
        self.models = self
        self.chave = chave

    def list(self, config: Any = None) -> Any:
        if self.chave in (CHAVE, CHAVE_PROJETO):
            return iter(["models/x"])
        from google.genai import errors

        raise errors.ClientError(400, {"error": {"message": "API key not valid."}})


class _Controlador:
    def __init__(self) -> None:
        self.rodando = False
        self.chamadas: list[str] = []

    def iniciar(self) -> bool:
        self.chamadas.append("iniciar")
        self.rodando = True
        return True

    def reiniciar(self) -> bool:
        self.chamadas.append("reiniciar")
        self.rodando = True
        return True


def _api(**kwargs: Any) -> ApiJs:
    kwargs.setdefault("carregar_settings", _settings)
    kwargs.setdefault("fabrica_gemini", _Gemini)
    kwargs.setdefault("abrir_url", lambda url: True)
    kwargs.setdefault("abrir_pasta", lambda pasta: True)
    return ApiJs(**kwargs)


def _esperar(condicao: Any, tempo: float = 3.0) -> bool:
    fim = time.monotonic() + tempo
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.01)
    return condicao()


# ------------------------------------------------------------------ fluxo completo
def test_primeira_vez_ate_segunda_abertura(pastas: dict[str, Path]) -> None:
    """Assistente da primeira vez pela API do JS, como a pagina faz, e depois reabrir."""
    from jarvis.ui.orb_window import montar_config

    inicio = montar_config(_settings())
    assert inicio["precisaConfigurar"] is True and inicio["config"]["tem_chave"] is False
    assert inicio["visual"] == preferencias.VISUAL_PADRAO

    ctrl = _Controlador()
    api = _api(controlador=ctrl)
    assert api.testar_chave("AIzaSyERRADA_errada_errada_errada_000")["ok"] is False
    assert api.testar_chave(f"  {CHAVE}\r\n") == {"ok": True, "mensagem": "Chave funcionando."}
    assert api.salvar_chave(CHAVE)["ok"] is True
    assert api.salvar_preferencias({"nome": "Ana Clara", "voz": "Kore", "fone": True})["ok"]
    assert api.salvar_visual("aura") is True
    assert api.concluir_configuracao() == {"ok": True, "mensagem": ""}
    assert ctrl.chamadas == ["iniciar"]

    # segunda abertura: nada para configurar, visual e voz lembrados
    depois = montar_config(_settings())
    assert depois["precisaConfigurar"] is False
    assert depois["visual"] == "aura" and depois["primeiraVez"] is False
    estado = depois["config"]
    assert estado["configurado"] is True and estado["voz"] == "Kore" and estado["fone"] is True
    assert estado["nome"] == "Ana Clara" and estado["chave_final"] == "…" + CHAVE[-4:]
    assert CHAVE not in json.dumps(depois, ensure_ascii=False)
    assert "João Silva" in estado["pasta_config"]


def test_engrenagem_troca_voz_e_chave_e_aplica(pastas: dict[str, Path]) -> None:
    armazenamento.salvar_segredos({armazenamento.GEMINI_API_KEY: CHAVE})
    ctrl = _Controlador()
    api = _api(controlador=ctrl)
    assert api.salvar_preferencias({"voz": "Puck", "fone": False, "nome": ""})["ok"]
    nova = "AIzaSyE2E_chave_nova_22222222222222222"
    assert api.salvar_chave(nova)["ok"] is True
    assert api.aplicar_configuracao()["ok"] is True
    assert ctrl.chamadas == ["reiniciar"]
    s = _settings()
    assert s.api_key == nova and s.voice == "Puck"
    linhas = pastas["env"].read_text(encoding="utf-8").splitlines()
    assert sum(linha.startswith("GEMINI_API_KEY=") for linha in linhas) == 1


# ------------------------------------------------------------------ .env do Windows
@pytest.mark.parametrize(
    ("nome", "bruto"),
    [
        ("bom_crlf", ("\ufeffGEMINI_API_KEY=" + CHAVE + "\r\nJARVIS_VOZ=Kore\r\n").encode()),
        ("utf16", ("GEMINI_API_KEY=" + CHAVE + "\r\nJARVIS_VOZ=Kore\r\n").encode("utf-16")),
        (
            "ansi",
            ("# comentário\r\nGEMINI_API_KEY=" + CHAVE + "\r\nJARVIS_VOZ=Kore\r\n").encode(
                "cp1252"
            ),
        ),
        ("lixo", ("lixo sem igual\n=\nGEMINI_API_KEY=" + CHAVE + "\nJARVIS_VOZ=Kore").encode()),
        ("aspas_espacos", ('  GEMINI_API_KEY = "' + CHAVE + '"  \nJARVIS_VOZ=Kore\n').encode()),
    ],
)
def test_env_do_projeto_editado_no_windows(
    pastas: dict[str, Path], nome: str, bruto: bytes
) -> None:
    """O .env do projeto (Bloco de Notas/PowerShell) continua dando a chave."""
    (pastas["projeto"] / ".env").write_bytes(bruto)
    s = _settings()
    assert s.api_key == CHAVE, nome
    assert s.api_key_source == "projeto" and s.voice == "Kore"


@pytest.mark.parametrize(
    "bruto",
    [
        ("\ufeffGEMINI_API_KEY=" + CHAVE + "\r\nOUTRA=1\r\n").encode(),
        ("GEMINI_API_KEY=" + CHAVE + "\r\nOUTRA=1\r\n").encode("utf-16"),
        ("# coração\r\nGEMINI_API_KEY=" + CHAVE + "\r\nOUTRA=1\r\n").encode("cp1252"),
        (b"GEMINI_API_KEY=velha_velha_velha_velha\nOUTRA=1\nGEMINI_API_KEY=repetida_aaaaaaa\n"),
    ],
)
def test_env_do_usuario_estranho_ainda_salva(pastas: dict[str, Path], bruto: bytes) -> None:
    """Trocar a chave pela janela funciona mesmo com o .env do usuario mexido a mao."""
    pastas["env"].parent.mkdir(parents=True)
    pastas["env"].write_bytes(bruto)
    nova = "AIzaSyE2E_chave_nova_33333333333333333"
    assert armazenamento.salvar_segredos({armazenamento.GEMINI_API_KEY: nova})
    texto = pastas["env"].read_text(encoding="utf-8")
    assert not texto.startswith("\ufeff")
    assert texto.count("GEMINI_API_KEY=") == 1 and "OUTRA=1" in texto
    assert _settings().api_key == nova


# ------------------------------------------------------------------ preferencias estragadas
@pytest.mark.parametrize(
    "bruto",
    [b"", b"{", b"[]", b"null", b"\xff\xfe{", b'{"visual": 42, "voz": ["x"], "fone": "sim"}'],
)
def test_preferencias_estragadas_nao_derrubam(pastas: dict[str, Path], bruto: bytes) -> None:
    arquivo = pastas["usuario"] / "preferencias.json"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_bytes(bruto)
    s = _settings()
    assert s.voice == vozes.VOZ_PADRAO and s.headphones is False
    from jarvis.ui.orb_window import montar_config

    assert montar_config(s)["visual"] == preferencias.VISUAL_PADRAO
    assert preferencias.salvar_visual("reator") is True
    assert preferencias.carregar()["visual"] == "reator"


def test_preferencias_com_bom_nao_perdem_o_resto(pastas: dict[str, Path]) -> None:
    arquivo = pastas["usuario"] / "preferencias.json"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_bytes('\ufeff{"visual": "aura", "nome": "Zé", "configurado": true}'.encode())
    assert preferencias.salvar_visual("mapa")
    assert preferencias.carregar() == {"visual": "mapa", "nome": "Zé", "configurado": True}


def test_preferencias_virou_pasta(pastas: dict[str, Path]) -> None:
    (pastas["usuario"] / "preferencias.json").mkdir(parents=True)
    assert preferencias.carregar() == {}
    assert preferencias.salvar_visual("aura") is False
    api = _api()
    assert api.salvar_preferencias({"voz": "Kore"})["ok"] is False
    assert api.estado_config()["visual"] == preferencias.VISUAL_PADRAO


def test_visual_salvo_que_nao_existe_mais(pastas: dict[str, Path]) -> None:
    from jarvis.ui.orb_window import montar_config

    preferencias.atualizar({"visual": "visual_de_uma_versao_antiga"})
    config_js = montar_config(_settings())
    assert config_js["visual"] == preferencias.VISUAL_PADRAO and config_js["primeiraVez"] is True


def test_appdata_ausente_no_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    casa = tmp_path / "Usuário Com Espaço"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: casa))
    for valor in (None, "", "   "):
        if valor is None:
            monkeypatch.delenv("APPDATA", raising=False)
        else:
            monkeypatch.setenv("APPDATA", valor)
        caminho = preferencias.caminho_preferencias()
        assert caminho == casa / "AppData" / "Roaming" / "Jarvis" / "preferencias.json"
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert preferencias.caminho_preferencias().parent == tmp_path / "Roaming" / "Jarvis"
    assert preferencias.salvar_visual("cortex") and preferencias.carregar()["visual"] == "cortex"


# ------------------------------------------------------------------ nome
@pytest.mark.parametrize(
    ("nome", "ok"),
    [
        ("😀" * 40, True),
        ("😀" * 41, False),
        ("👨\u200d👩\u200d👧 Família", True),  # emoji com ZWJ
        ("🇧🇷 Mateus", True),
        ("x\ud83d", False),  # metade de um emoji (texto cortado no meio)
        ("a" * 40, True),
        ("a" * 41, False),
        ("\u202eolleh", False),  # inverte o texto na tela
        ("linha\nquebrada", False),
    ],
)
def test_nome_com_emoji_e_limites(pastas: dict[str, Path], nome: str, ok: bool) -> None:
    resposta = _api().salvar_preferencias({"nome": nome})
    assert resposta["ok"] is ok
    if ok:
        assert _settings().user_name == nome
    else:
        assert "40" in resposta["mensagem"]  # mensagem do nome, nao "erro de disco"


# ------------------------------------------------------------------ ElevenLabs
def test_elevenlabs_ligar_pausar_religar_desligar(pastas: dict[str, Path]) -> None:
    armazenamento.salvar_segredos({armazenamento.GEMINI_API_KEY: CHAVE})
    api = _api()
    assert api.salvar_preferencias({"fonte_voz": "elevenlabs"})["ok"] is False  # sem configurar
    assert api.elevenlabs_salvar(EL, VOZ_EL, "Rachel") == {
        "ok": True,
        "mensagem": "Voz do ElevenLabs salva.",
    }
    assert _settings().uses_elevenlabs
    assert api.estado_config()["elevenlabs"]["voz_nome"] == "Rachel"
    assert api.salvar_preferencias({"fonte_voz": "google"})["ok"]
    assert not _settings().uses_elevenlabs and _settings().elevenlabs_configurado
    assert api.salvar_preferencias({"fonte_voz": "elevenlabs"})["ok"]
    assert _settings().uses_elevenlabs
    assert api.elevenlabs_desligar()["ok"] is True
    s = _settings()
    assert not s.uses_elevenlabs and not s.elevenlabs_configurado
    assert "ELEVENLABS" not in pastas["env"].read_text(encoding="utf-8")


def test_elevenlabs_no_env_do_projeto_cenario_do_mateus(pastas: dict[str, Path]) -> None:
    (pastas["projeto"] / ".env").write_text(
        f"GEMINI_API_KEY={CHAVE_PROJETO}\nELEVENLABS_API_KEY={EL_PROJETO}\n"
        f"ELEVENLABS_VOICE_ID={VOZ_PROJETO}\n",
        encoding="utf-8",
    )
    api = _api()
    estado = api.estado_config()
    assert estado["chave_origem"] == "projeto" and estado["fonte_voz"] == "elevenlabs"
    # desligar: o .env do projeto nao e mexido, mas o Jarvis passa a usar a voz do Google
    resposta = api.elevenlabs_desligar()
    assert resposta["ok"] and "projeto" in resposta["mensagem"]
    assert not _settings().uses_elevenlabs
    assert VOZ_PROJETO in (pastas["projeto"] / ".env").read_text(encoding="utf-8")
    # religar pela aba Geral
    assert api.salvar_preferencias({"fonte_voz": "elevenlabs"})["ok"]
    assert _settings().uses_elevenlabs
    # escolher outra voz na janela: o projeto continua mandando, e a resposta AVISA
    resposta = api.elevenlabs_salvar(EL, VOZ_EL, "Rachel")
    assert resposta["ok"] is True and ".env da pasta do projeto" in resposta["mensagem"]
    assert resposta.get("aviso")
    assert _settings().elevenlabs_voice_id == VOZ_PROJETO
    # o nome mostrado nao vira "Rachel" (seria mentira: quem fala e a voz do projeto)
    assert api.estado_config()["elevenlabs"]["voz_nome"] != "Rachel"
    assert EL not in json.dumps(api.estado_config())


# ------------------------------------------------------------------ chave recusada
def test_chave_recusada_avisa_a_janela_mesmo_antes_de_carregar(
    pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """O Google recusa a chave antes de o WebView2 terminar de carregar a pagina."""
    import importlib

    teste_orb = importlib.import_module("test_orb")
    from jarvis.ui.orb_window import OrbWindow

    falso = teste_orb._FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", falso)
    armazenamento.salvar_segredos({armazenamento.GEMINI_API_KEY: CHAVE})
    janela = OrbWindow(_settings(), api=_api())

    class _Recusa:
        def __init__(self, settings: Settings, observer: Any) -> None:
            pass

        async def run(self) -> None:
            raise ChaveInvalidaError("recusada")

    ctrl = Controlador(janela, _settings, fabrica=_Recusa)
    assert ctrl.iniciar()
    assert _esperar(lambda: not ctrl.rodando)
    janela.on_transcript("sistema", "antes de carregar")
    time.sleep(0.05)
    assert falso.window.js == []  # nada vai para a pagina antes de ela carregar...
    teste_orb._load(falso)
    # ...mas nada se perde: o aviso e a fala chegam depois do carregamento
    assert teste_orb._wait_js(falso, lambda js: any("avisoChave" in c for c in js))
    assert teste_orb._wait_js(falso, lambda js: any("antes de carregar" in c for c in js))
    assert any('setState("offline")' in c for c in falso.window.js)


# ------------------------------------------------------------------ controlador
class _AssistenteContado:
    vivos = 0
    maximo = 0
    trava = threading.Lock()
    demora_para_fechar = 0.0

    def __init__(self, settings: Settings, observer: Any) -> None:
        pass

    async def run(self) -> None:
        cls = _AssistenteContado
        with cls.trava:
            cls.vivos += 1
            cls.maximo = max(cls.maximo, cls.vivos)
        try:
            await asyncio.sleep(3600)
        finally:
            time.sleep(cls.demora_para_fechar)  # fechamento lento e bloqueante
            with cls.trava:
                cls.vivos -= 1


@pytest.fixture
def contado() -> Any:
    _AssistenteContado.vivos = 0
    _AssistenteContado.maximo = 0
    _AssistenteContado.demora_para_fechar = 0.0
    return _AssistenteContado


def test_controlador_repetido_e_concorrente(contado: Any) -> None:
    ctrl = Controlador(object(), lambda: Settings(api_key=CHAVE), fabrica=contado)
    for _ in range(30):
        assert ctrl.iniciar() and ctrl.reiniciar()
        assert ctrl.parar()
    assert not ctrl.rodando

    def martelar(semente: int) -> None:
        for i in range(25):
            (ctrl.iniciar, ctrl.parar, ctrl.reiniciar)[(i + semente) % 3]()

    threads = [threading.Thread(target=martelar, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert ctrl.parar()
    assert _esperar(lambda: contado.vivos == 0)
    assert contado.maximo <= 1  # nunca dois assistentes ao mesmo tempo
    assert not [t for t in threading.enumerate() if t.name == "jarvis-assistente"]


def test_controlador_nao_comeca_outro_enquanto_o_velho_nao_parou(
    contado: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import jarvis.controlador as controlador

    monkeypatch.setattr(controlador, "ESPERA_PARAR_S", 0.2)
    contado.demora_para_fechar = 1.0
    ctrl = Controlador(object(), lambda: Settings(api_key=CHAVE), fabrica=contado)
    assert ctrl.iniciar()
    assert _esperar(lambda: contado.vivos == 1)
    assert ctrl.reiniciar() is False  # o velho ainda fecha: nao abre um segundo microfone
    assert contado.maximo == 1
    assert _esperar(lambda: contado.vivos == 0)
    assert ctrl.iniciar() is True  # depois que o velho terminou, inicia normalmente
    assert _esperar(lambda: contado.vivos == 1)
    contado.demora_para_fechar = 0.0
    assert ctrl.parar(2)
    assert contado.maximo == 1


# ------------------------------------------------------------------ microfone do teste
class _Microfone:
    paInt16 = 8

    def __init__(self, demora: float = 0.02) -> None:
        self.abertos = 0
        self.demora = demora
        self.trava = threading.Lock()

    def PyAudio(self) -> _Microfone:  # noqa: N802 - imita o pyaudio
        return self

    def open(self, **kwargs: Any) -> Any:
        with self.trava:
            self.abertos += 1
        dono = self

        class _Fluxo:
            def read(self, n: int, exception_on_overflow: bool = False) -> bytes:
                time.sleep(dono.demora)
                return (3000).to_bytes(2, "little", signed=True) * n

            def stop_stream(self) -> None:
                pass

            def close(self) -> None:
                with dono.trava:
                    dono.abertos -= 1

        return _Fluxo()

    def terminate(self) -> None:
        pass


def test_microfone_abre_e_fecha_certo_mesmo_repetido(pastas: dict[str, Path]) -> None:
    mic = _Microfone()
    niveis: list[float] = []
    janela = types.SimpleNamespace(on_mic_teste=niveis.append)
    ctrl = _Controlador()
    api = _api(janela=janela, modulo_pyaudio=lambda: mic, controlador=ctrl)
    for _ in range(10):
        assert api.microfone_iniciar()["ok"]
        assert api.microfone_parar() is True
    assert _esperar(lambda: mic.abertos == 0)
    threads = [threading.Thread(target=api.microfone_iniciar) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)
    assert mic.abertos == 1  # dez cliques ao mesmo tempo: um microfone so
    assert _esperar(lambda: len(niveis) > 3)
    # concluir a configuracao fecha o microfone antes de o assistente abrir o dele
    armazenamento.salvar_segredos({armazenamento.GEMINI_API_KEY: CHAVE})
    assert api.concluir_configuracao()["ok"]
    assert _esperar(lambda: mic.abertos == 0)
    assert api.microfone_iniciar()["ok"] is False  # com o assistente rodando, o teste recusa


def test_microfone_lento_nao_deixa_rodada_orfa() -> None:
    """Parar e iniciar de novo com um read() lento nao deixa dois microfones abertos."""
    mic = _Microfone(demora=0.6)
    teste = _MedidorMic(lambda nivel: None, modulo_pyaudio=lambda: mic)
    assert teste.iniciar()[0]
    time.sleep(0.05)
    teste.parar(espera_s=0.05)  # a rodada antiga ainda esta presa no read()
    assert teste.iniciar()[0]
    assert _esperar(lambda: mic.abertos == 1, 2.0)
    time.sleep(0.8)
    assert mic.abertos == 1
    teste.parar()
    assert _esperar(lambda: mic.abertos == 0, 2.0)


# ------------------------------------------------------------------ amostras de voz
def test_as_8_amostras_existem_e_viram_data_url_valida() -> None:
    assert len(vozes.IDS) == 8
    for id_voz in vozes.IDS:
        resposta = _api().amostra_voz(id_voz)
        assert resposta["ok"] is True, f"falta a amostra de {id_voz}"
        prefixo = "data:audio/wav;base64,"
        assert resposta["dados"].startswith(prefixo)
        bruto = base64.b64decode(resposta["dados"][len(prefixo) :], validate=True)
        with wave.open(io.BytesIO(bruto)) as w:
            assert w.getnchannels() == 1 and w.getsampwidth() == 2
            duracao = w.getnframes() / w.getframerate()
        assert 1.0 < duracao < 15.0, id_voz
    assert all(v["tem_amostra"] for v in vozes.lista_para_janela())
    for ruim in ("../Charon", "charon", "Charon.wav", "", None, 7):
        assert _api().amostra_voz(ruim)["ok"] is False


# ------------------------------------------------------------------ janela
def test_rajada_de_volume_e_falas_nao_entope_a_janela(
    pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    teste_orb = importlib.import_module("test_orb")
    from jarvis.ui.orb_window import OrbWindow

    falso = teste_orb._FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", falso)
    janela = OrbWindow(None, api=_api())
    teste_orb._load(falso)
    inicio = time.monotonic()
    for i in range(20_000):
        janela.on_level((i % 97) / 97)
    for i in range(300):
        janela.on_tool(f"acao_{i}", i % 4 != 0)
        janela.on_transcript("jarvis", f"fala {i} 😀 </script>")
        janela.on_latency(float("nan") if i % 50 == 0 else 0.5)
    assert time.monotonic() - inicio < 2.0  # quem chama nunca espera a janela
    assert teste_orb._wait_js(falso, lambda js: any("fala 299" in c for c in js), 3.0)
    js = falso.window.js
    assert sum(c.startswith("window.jarvis.setLevel") for c in js) < 200  # volume agrupado
    assert sum(c.startswith("window.jarvis.addTool") for c in js) == 300
    assert not any("NaN" in c for c in js)


def test_api_aguenta_argumentos_estranhos_do_js(pastas: dict[str, Path]) -> None:
    ponte = ponte_js(_api(controlador=_Controlador(), modulo_pyaudio=lambda: _Microfone()))
    estranhos: list[Any] = [None, 0, -1, 1e308, "", "x" * 100_000, [], {}, {"a": [1]}, "😀", True]
    for nome in METODOS_PUBLICOS:
        metodo = getattr(ponte, nome)
        for valor in estranhos:
            for args in ((), (valor,), (valor, valor), (valor, valor, valor)):
                try:
                    resposta = metodo(*args)
                except TypeError:
                    continue  # numero de argumentos errado: o pywebview tambem recusaria
                json.dumps(resposta)  # sempre algo que o JS entende
    ponte.microfone_parar()


# ------------------------------------------------------------------ modos do terminal
@pytest.mark.parametrize("modo", ["voz", "texto"])
def test_modo_terminal_sem_chave_explica(
    pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch, modo: str
) -> None:
    import jarvis.__main__ as principal

    mensagens: list[str] = []
    monkeypatch.setattr(principal, "_tell_user", mensagens.append)
    monkeypatch.setattr(principal, "setup_logging", lambda caminho: None)
    assert principal.main(["--modo", modo]) == 1
    assert "GEMINI_API_KEY" in mensagens[0] and "janela" in mensagens[0]


@pytest.mark.parametrize("onde", ["ambiente", "usuario"])
@pytest.mark.parametrize("modo", ["voz", "texto"])
def test_modo_terminal_com_chave_roda_o_assistente(
    pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch, modo: str, onde: str
) -> None:
    import jarvis.__main__ as principal
    import jarvis.tools as ferramentas
    from jarvis.assistants import live_assistant, text_assistant

    if onde == "ambiente":
        monkeypatch.setenv("GEMINI_API_KEY", CHAVE)
    else:  # a chave que a janela salvou em %APPDATA%\Jarvis\.env tambem vale no terminal
        armazenamento.salvar_segredos({armazenamento.GEMINI_API_KEY: CHAVE})
    rodou: list[tuple[str, str]] = []

    class _Texto:
        def __init__(self, settings: Settings, registry: Any) -> None:
            self.settings = settings

        def run(self) -> None:
            rodou.append(("texto", self.settings.api_key))

    class _Voz(_Texto):
        async def run(self) -> None:  # type: ignore[override]
            rodou.append(("voz", self.settings.api_key))

    monkeypatch.setattr(text_assistant, "TextAssistant", _Texto)
    monkeypatch.setattr(live_assistant, "LiveAssistant", _Voz)
    monkeypatch.setattr(ferramentas, "ToolRegistry", lambda settings: object())
    monkeypatch.setattr(principal, "setup_logging", lambda caminho: None)
    assert principal.main(["--modo", modo]) == 0
    assert rodou == [(modo, CHAVE)]


def test_modo_terminal_ctrl_c_sai_limpo(
    pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import jarvis.__main__ as principal
    import jarvis.tools as ferramentas
    from jarvis.assistants import text_assistant

    monkeypatch.setenv("GEMINI_API_KEY", CHAVE)

    class _Texto:
        def __init__(self, settings: Settings, registry: Any) -> None:
            pass

        def run(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(text_assistant, "TextAssistant", _Texto)
    monkeypatch.setattr(ferramentas, "ToolRegistry", lambda settings: object())
    monkeypatch.setattr(principal, "setup_logging", lambda caminho: None)
    assert principal.main(["--modo", "texto"]) == 0
    assert "Até logo" in capsys.readouterr().out
