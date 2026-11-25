"""Testes da configuracao 0.8.0: armazenamento, preferencias, vozes, API do JS, controlador,
verificacao das chaves e modo congelado. Sem rede, sem janela e sem microfone (tudo falso).
"""

from __future__ import annotations

import array
import asyncio
import json
import logging
import sys
import threading
import time
import warnings
from pathlib import Path
from typing import Any

import httpx
import pytest

from jarvis import armazenamento, config, verificacao, vozes
from jarvis.config import Settings
from jarvis.controlador import MSG_CHAVE_PAROU, Controlador
from jarvis.errors import ChaveInvalidaError, ConfigError
from jarvis.logging_setup import redigir
from jarvis.microfone import TesteMicrofone as _MedidorMic
from jarvis.ui import api_config, preferencias
from jarvis.ui.api_config import METODOS_PUBLICOS, ApiJs

CHAVE = "AIzaSyTESTE_segredo_super_secreto_12345678"
CHAVE_NOVA = "AIzaSyNOVA_chave_outra_coisa_abcdefgh9876"
CHAVE_EL = "sk_0123456789abcdef0123456789abcdef0123456789abcdef"
VOZ_EL = "21m00Tcm4TlvDq8ikWAM"


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def pastas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Pasta do usuario e do projeto falsas (nada toca no disco real)."""
    usuario = tmp_path / "AppData" / "Jarvis"
    projeto = tmp_path / "projeto"
    projeto.mkdir()
    monkeypatch.setattr(preferencias, "caminho_preferencias", lambda: usuario / "preferencias.json")
    monkeypatch.setattr(config, "raiz_projeto", lambda: projeto)
    return {"usuario": usuario, "projeto": projeto, "env": usuario / ".env"}


def _settings() -> Settings:
    return Settings.from_env(exigir_chave=False)


class _Janela:
    def __init__(self) -> None:
        self.niveis: list[float] = []

    def on_mic_teste(self, nivel: float) -> None:
        self.niveis.append(nivel)


class _ControladorFalso:
    def __init__(self, rodando: bool = False, resultado: bool = True) -> None:
        self.rodando = rodando
        self.resultado = resultado
        self.chamadas: list[str] = []

    def iniciar(self) -> bool:
        self.chamadas.append("iniciar")
        return self.resultado

    def reiniciar(self) -> bool:
        self.chamadas.append("reiniciar")
        return self.resultado


class _ClienteGemini:
    def __init__(self, erro: Exception | None = None) -> None:
        self.models = self
        self.erro = erro
        self.chamadas = 0

    def list(self, config: Any = None) -> Any:
        self.chamadas += 1
        if self.erro is not None:
            raise self.erro
        return iter(["models/gemini"])


def _api(**kwargs: Any) -> ApiJs:
    kwargs.setdefault("carregar_settings", _settings)
    kwargs.setdefault("abrir_url", lambda url: True)
    kwargs.setdefault("abrir_pasta", lambda pasta: True)
    return ApiJs(**kwargs)


# ------------------------------------------------------------------ armazenamento
def test_salvar_segredos_cria_arquivo_e_le(pastas: dict[str, Path]) -> None:
    assert armazenamento.caminho_env_usuario() == pastas["env"]
    assert armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})
    texto = pastas["env"].read_text(encoding="utf-8")
    assert f"GEMINI_API_KEY={CHAVE}\n" in texto
    assert texto.startswith("#")  # cabecalho explicando o arquivo


def test_salvar_segredos_preserva_outras_linhas(pastas: dict[str, Path]) -> None:
    pastas["env"].parent.mkdir(parents=True)
    original = (
        "# meu comentario\n"
        "OUTRA=valor com espaco\n"
        "\n"
        "GEMINI_API_KEY=antiga\n"
        "ELEVENLABS_MODEL=eleven_flash_v2_5\n"
        "GEMINI_API_KEY=repetida\n"
        "FIM=1"
    )
    pastas["env"].write_text(original, encoding="utf-8")
    assert armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE, "ELEVENLABS_VOICE_ID": VOZ_EL})
    linhas = pastas["env"].read_text(encoding="utf-8").splitlines()
    assert linhas == [
        "# meu comentario",
        "OUTRA=valor com espaco",
        "",
        f"GEMINI_API_KEY={CHAVE}",
        "ELEVENLABS_MODEL=eleven_flash_v2_5",
        "FIM=1",
        f"ELEVENLABS_VOICE_ID={VOZ_EL}",
    ]


def test_salvar_segredos_none_apaga_a_linha(pastas: dict[str, Path]) -> None:
    armazenamento.salvar_segredos({"ELEVENLABS_API_KEY": CHAVE_EL, "GEMINI_API_KEY": CHAVE})
    assert armazenamento.salvar_segredos({"ELEVENLABS_API_KEY": None})
    texto = pastas["env"].read_text(encoding="utf-8")
    assert "ELEVENLABS_API_KEY" not in texto and CHAVE in texto


@pytest.mark.parametrize(
    "alteracao",
    [
        {"GEMINI_API_KEY": "abc\nJARVIS_VOZ=Puck"},  # injecao de linha
        {"GEMINI_API_KEY": "com espaco"},
        {"GEMINI_API_KEY": 'aspas"'},
        {"GEMINI_API_KEY": "$(rm -rf)"},
        {"GEMINI_API_KEY": ""},
        {"PATH": "x"},  # variavel fora da lista
    ],
)
def test_salvar_segredos_recusa_valores_e_nomes_perigosos(
    pastas: dict[str, Path], alteracao: dict[str, str]
) -> None:
    assert armazenamento.salvar_segredos(alteracao) is False
    assert not pastas["env"].exists()


def test_salvar_segredos_e_atomico(
    pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})

    def disco_cheio(origem: str, destino: str) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(armazenamento.os, "replace", disco_cheio)
    assert armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE_NOVA}) is False
    assert CHAVE in pastas["env"].read_text(encoding="utf-8")  # o antigo continua inteiro
    assert [p.name for p in pastas["env"].parent.iterdir() if p.suffix == ".tmp"] == []


def test_final_da_chave() -> None:
    assert armazenamento.final_da_chave("") == ""
    assert armazenamento.final_da_chave("curta") == "…"
    assert armazenamento.final_da_chave(CHAVE) == "…5678"


# ------------------------------------------------------------------ precedencia
def test_precedencia_ambiente_projeto_usuario(
    pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    armazenamento.salvar_segredos({"GEMINI_API_KEY": "AIzaUSUARIO_aaaaaaaaaaaaaaaaaaaa"})
    assert _settings().api_key == "AIzaUSUARIO_aaaaaaaaaaaaaaaaaaaa"
    assert _settings().api_key_source == "usuario"
    (pastas["projeto"] / ".env").write_text(
        "GEMINI_API_KEY=AIzaPROJETO_bbbbbbbbbbbbbbbbbbbb\n", encoding="utf-8"
    )
    assert _settings().api_key == "AIzaPROJETO_bbbbbbbbbbbbbbbbbbbb"
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaAMBIENTE_cccccccccccccccccc")
    assert _settings().api_key == "AIzaAMBIENTE_cccccccccccccccccc"
    assert _settings().api_key_source == "ambiente"


def test_texto_de_exemplo_no_projeto_cai_para_o_usuario(pastas: dict[str, Path]) -> None:
    (pastas["projeto"] / ".env").write_text("GEMINI_API_KEY=cole_sua_chave_aqui\n", "utf-8")
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})
    assert _settings().api_key == CHAVE


def test_from_env_nao_altera_os_environ(pastas: dict[str, Path]) -> None:
    import os

    (pastas["projeto"] / ".env").write_text(f"GEMINI_API_KEY={CHAVE}\nJARVIS_VOZ=Puck\n", "utf-8")
    assert Settings.from_env().api_key == CHAVE
    assert "GEMINI_API_KEY" not in os.environ and "JARVIS_VOZ" not in os.environ


def test_chave_nova_salva_vale_ao_recarregar(pastas: dict[str, Path]) -> None:
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})
    assert _settings().api_key == CHAVE
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE_NOVA})
    assert _settings().api_key == CHAVE_NOVA


def test_sem_chave_modo_orb_nao_levanta_e_voz_texto_levanta(pastas: dict[str, Path]) -> None:
    settings = _settings()
    assert settings.api_key == "" and not settings.has_api_key and settings.api_key_source == ""
    with pytest.raises(ConfigError, match="janela"):
        Settings.from_env()


def test_modo_dev_do_mateus_continua_igual(pastas: dict[str, Path]) -> None:
    """Tudo no .env do projeto, nada salvo pela janela: mesmos valores de antes."""
    (pastas["projeto"] / ".env").write_text(
        f"GEMINI_API_KEY={CHAVE}\nJARVIS_VOZ=Orus\nJARVIS_NOME_USUARIO=Mateus\n"
        f"JARVIS_FONE=sim\nELEVENLABS_API_KEY={CHAVE_EL}\nELEVENLABS_VOICE_ID={VOZ_EL}\n"
        "JARVIS_SILENCIO_MS=700\n",
        encoding="utf-8",
    )
    settings = Settings.from_env()
    assert (settings.voice, settings.user_name, settings.headphones) == ("Orus", "Mateus", True)
    assert settings.uses_elevenlabs and settings.silence_ms == 700
    assert settings.log_file == pastas["projeto"] / "logs" / "jarvis.log"


# ------------------------------------------------------------------ preferencias novas
def test_preferencias_voz_nome_fone(pastas: dict[str, Path]) -> None:
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})
    preferencias.salvar_visual("reator")
    assert preferencias.atualizar({"voz": "Kore", "nome": "Ana", "fone": True})
    settings = _settings()
    assert (settings.voice, settings.user_name, settings.headphones) == ("Kore", "Ana", True)
    assert preferencias.carregar()["visual"] == "reator"  # preservou


def test_env_do_projeto_ganha_das_preferencias(pastas: dict[str, Path]) -> None:
    preferencias.atualizar({"voz": "Kore", "nome": "Ana", "fone": True})
    (pastas["projeto"] / ".env").write_text("JARVIS_VOZ=Puck\nJARVIS_FONE=nao\n", "utf-8")
    settings = _settings()
    assert (settings.voice, settings.user_name, settings.headphones) == ("Puck", "Ana", False)


def test_preferencias_invalidas_no_arquivo_sao_ignoradas(pastas: dict[str, Path]) -> None:
    preferencias.atualizar({"voz": "Hacker", "nome": "a\nb", "fone": "sim"})
    settings = _settings()
    assert (settings.voice, settings.user_name, settings.headphones) == ("Charon", "", False)


def test_atualizar_none_apaga_chave(pastas: dict[str, Path]) -> None:
    preferencias.atualizar({"voz": "Kore", "nome": "Ana"})
    preferencias.atualizar({"nome": None})
    assert preferencias.carregar() == {"voz": "Kore"}


@pytest.mark.parametrize(
    ("nome", "valido"),
    [
        ("", True),
        ("Mateus", True),
        ("  Zé  ", True),
        ("a" * 40, True),
        ("a" * 41, False),
        ("a\nb", False),
        ("a\rb", False),
        ("a\u2028b", False),
        ("a\x00", False),
        (None, False),
    ],
)
def test_nome_valido(nome: object, valido: bool) -> None:
    assert preferencias.nome_valido(nome) is valido


# ------------------------------------------------------------------ vozes
def test_vozes_lista_fixa() -> None:
    assert vozes.IDS == ("Charon", "Puck", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr")
    assert vozes.VOZ_PADRAO == "Charon" == vozes.IDS[0]
    assert vozes.DESCRICOES["Charon"] == "Masculina, grave e calma (padrão)"
    assert vozes.DESCRICOES["Orus"] == "Masculina, firme"
    assert vozes.DESCRICOES["Kore"].startswith("Feminina")


@pytest.mark.parametrize("ruim", ["charon", "../etc/passwd", "Charon.wav", "", None, 1, ["Puck"]])
def test_voz_invalida(ruim: object) -> None:
    assert vozes.voz_valida(ruim) is False
    assert vozes.caminho_amostra(ruim) is None
    assert vozes.amostra_data_url(ruim) is None


def test_amostra_existente_e_ausente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vozes, "pasta_amostras", lambda: tmp_path)
    (tmp_path / "Puck.wav").write_bytes(b"RIFF....WAVEfmt ")
    (tmp_path / "Kore.wav").write_bytes(b"isto nao e wav")
    assert vozes.amostra_data_url("Puck").startswith("data:audio/wav;base64,UklGR")
    assert vozes.amostra_data_url("Kore") is None
    assert vozes.amostra_data_url("Leda") is None
    lista = vozes.lista_para_janela()
    assert [v["id"] for v in lista] == list(vozes.IDS)
    assert {v["id"]: v["tem_amostra"] for v in lista}["Puck"] is True
    assert {v["id"]: v["tem_amostra"] for v in lista}["Leda"] is False


def test_pasta_amostras_em_desenvolvimento() -> None:
    assert vozes.pasta_amostras() == Path(vozes.__file__).resolve().parent / "ui" / "amostras"


# ------------------------------------------------------------------ modo congelado
@pytest.fixture
def congelado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    meipass = tmp_path / "Jarvis" / "_internal"
    meipass.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Jarvis" / "Jarvis.exe"))
    monkeypatch.setattr(
        preferencias, "caminho_preferencias", lambda: tmp_path / "AppData" / "preferencias.json"
    )
    return tmp_path


def test_congelado_acha_arquivos_no_meipass(congelado: Path) -> None:
    from jarvis.logging_setup import caminho_log_padrao

    assert config.congelado() is True
    assert config.pasta_pacote() == congelado / "Jarvis" / "_internal" / "jarvis"
    assert (
        vozes.pasta_amostras() == congelado / "Jarvis" / "_internal" / "jarvis" / "ui" / "amostras"
    )
    assert config.raiz_projeto() == congelado / "Jarvis"
    assert config.pasta_logs() == congelado / "AppData" / "logs"
    assert caminho_log_padrao() == congelado / "AppData" / "logs" / "jarvis.log"


def test_congelado_ignora_env_de_projeto_e_loga_no_appdata(congelado: Path) -> None:
    (congelado / "Jarvis" / ".env").write_text(f"GEMINI_API_KEY={CHAVE}\n", "utf-8")
    settings = _settings()
    assert settings.api_key == ""
    assert settings.log_file == congelado / "AppData" / "logs" / "jarvis.log"
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE_NOVA})
    assert _settings().api_key == CHAVE_NOVA


def test_setup_logging_congelado_cria_pasta_e_redige(congelado: Path) -> None:
    from jarvis.logging_setup import setup_logging

    caminho = setup_logging()
    assert caminho == congelado / "AppData" / "logs" / "jarvis.log"
    log = logging.getLogger("jarvis.teste_redacao")
    log.warning("url wss://x/ws?key=%s&alt=1 e %s", CHAVE, CHAVE_EL)
    for handler in logging.getLogger().handlers:
        handler.flush()
    texto = caminho.read_text(encoding="utf-8")
    assert "url wss://x/ws?key=…" in texto
    assert CHAVE not in texto and CHAVE_EL not in texto
    raiz = logging.getLogger()
    for handler in list(raiz.handlers):
        if getattr(handler, "baseFilename", "") == str(caminho):
            raiz.removeHandler(handler)
            handler.close()


def test_redigir() -> None:
    assert CHAVE not in redigir(f"erro {CHAVE}")
    assert CHAVE_EL not in redigir(f"{{'xi-api-key': '{CHAVE_EL}'}}")
    assert redigir("nada secreto") == "nada secreto"


def test_pasta_pacote_em_desenvolvimento() -> None:
    assert config.congelado() is False
    assert config.pasta_pacote() == Path(config.__file__).resolve().parent


# ------------------------------------------------------------------ API: superficie
def test_api_expoe_exatamente_os_metodos_do_contrato() -> None:
    api = _api()
    publicos = sorted(nome for nome in dir(api) if not nome.startswith("_"))
    assert publicos == sorted(METODOS_PUBLICOS)
    assert len(METODOS_PUBLICOS) == 15
    assert all(nome.startswith("_") for nome in vars(api))


def test_estado_config_sem_chave(pastas: dict[str, Path]) -> None:
    estado = _api().estado_config()
    assert estado["tem_chave"] is False and estado["chave_final"] == ""
    assert estado["configurado"] is False
    assert estado["voz"] == "Charon" and estado["visual"] == "galaxia"
    assert estado["elevenlabs"] == {
        "ativo": False,
        "configurado": False,
        "voz_id": "",
        "voz_nome": "",
        "chave_final": "",
    }
    assert estado["fonte_voz"] == "google"
    assert estado["versao"] == "0.8.0"
    assert estado["pasta_config"] == str(pastas["usuario"])
    assert [v["id"] for v in estado["vozes"]] == list(vozes.IDS)
    assert set(estado) >= {
        "configurado",
        "tem_chave",
        "chave_final",
        "voz",
        "nome",
        "fone",
        "visual",
        "elevenlabs",
        "versao",
        "pasta_config",
        "pasta_logs",
        "vozes",
    }


def test_estado_config_com_tudo_nunca_mostra_chave(pastas: dict[str, Path]) -> None:
    api = _api()
    armazenamento.salvar_segredos(
        {"GEMINI_API_KEY": CHAVE, "ELEVENLABS_API_KEY": CHAVE_EL, "ELEVENLABS_VOICE_ID": VOZ_EL}
    )
    preferencias.atualizar({"configurado": True, "elevenlabs_voz_nome": "Rachel"})
    estado = api.estado_config()
    texto = json.dumps(estado)
    assert CHAVE not in texto and CHAVE_EL not in texto
    assert estado["chave_final"] == "…5678" and estado["configurado"] is True
    assert estado["elevenlabs"] == {
        "ativo": True,
        "configurado": True,
        "voz_id": VOZ_EL,
        "voz_nome": "Rachel",
        "chave_final": "…cdef",
    }


def test_montar_config_tem_config_e_precisa_configurar(pastas: dict[str, Path]) -> None:
    from jarvis.ui.orb_window import montar_config

    sem = montar_config(_settings())
    assert sem["precisaConfigurar"] is True and sem["config"]["tem_chave"] is False
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})
    com = montar_config(_settings())
    assert com["precisaConfigurar"] is False and com["config"]["chave_final"] == "…5678"
    assert CHAVE not in json.dumps(com)


# ------------------------------------------------------------------ API: chave do Google
def test_testar_chave_ok(pastas: dict[str, Path]) -> None:
    cliente = _ClienteGemini()
    api = _api(fabrica_gemini=lambda chave: cliente)
    assert api.testar_chave(f"  {CHAVE}\n") == {"ok": True, "mensagem": verificacao.MSG_OK}
    assert cliente.chamadas == 1


def _client_error(codigo: int, mensagem: str, status: str) -> Exception:
    from google.genai import errors

    corpo = {"error": {"code": codigo, "message": mensagem, "status": status}}
    classe = errors.ClientError if codigo < 500 else errors.ServerError
    return classe(codigo, corpo, None)


@pytest.mark.parametrize(
    ("erro", "mensagem"),
    [
        (
            lambda: _client_error(
                400, "API key not valid. Please pass a valid API key.", "INVALID_ARGUMENT"
            ),
            verificacao.MSG_INVALIDA,
        ),
        (
            lambda: _client_error(403, "Permission denied", "PERMISSION_DENIED"),
            verificacao.MSG_INVALIDA,
        ),
        (
            lambda: _client_error(429, "Resource exhausted", "RESOURCE_EXHAUSTED"),
            verificacao.MSG_LIMITE,
        ),
        (lambda: _client_error(503, "Overloaded", "UNAVAILABLE"), verificacao.MSG_GOOGLE_INSTAVEL),
        (lambda: httpx.ConnectError("sem rota"), verificacao.MSG_SEM_INTERNET),
        (lambda: httpx.ReadTimeout("demorou"), verificacao.MSG_SEM_INTERNET),
        (lambda: ValueError("???"), verificacao.MSG_INESPERADO),
    ],
)
def test_testar_chave_mapeia_erros(
    pastas: dict[str, Path], erro: Any, mensagem: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    api = _api(fabrica_gemini=lambda chave: _ClienteGemini(erro()))
    resultado = api.testar_chave(CHAVE)
    assert resultado == {"ok": False, "mensagem": mensagem}
    assert CHAVE not in caplog.text


@pytest.mark.parametrize(
    "ruim", ["", "curta", "AIza com espaco no meio xxxxx", None, 123, {"k": 1}]
)
def test_testar_chave_formato_invalido_nem_chama_o_google(
    pastas: dict[str, Path], ruim: object
) -> None:
    cliente = _ClienteGemini()
    api = _api(fabrica_gemini=lambda chave: cliente)
    assert api.testar_chave(ruim) == {"ok": False, "mensagem": verificacao.MSG_FORMATO}
    assert cliente.chamadas == 0


def test_testar_chave_vazia_testa_a_salva(pastas: dict[str, Path]) -> None:
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})
    recebidas: list[str] = []

    def fabrica(chave: str) -> _ClienteGemini:
        recebidas.append(chave)
        return _ClienteGemini()

    assert _api(fabrica_gemini=fabrica).testar_chave("")["ok"] is True
    assert recebidas == [CHAVE]


def test_fabrica_padrao_usa_timeout_de_12s(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = verificacao._cliente_gemini_padrao(CHAVE)
    opcoes = cliente._api_client._http_options
    assert opcoes.timeout >= 10_000


def test_salvar_chave(pastas: dict[str, Path], caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    api = _api()
    resultado = api.salvar_chave(f" {CHAVE} ")
    assert resultado["ok"] is True and CHAVE not in json.dumps(resultado)
    assert _settings().api_key == CHAVE
    assert api.salvar_chave("abc\nGEMINI_API_KEY=x")["ok"] is False
    assert api.salvar_chave(None)["ok"] is False
    assert _settings().api_key == CHAVE
    assert CHAVE not in caplog.text
    assert not (pastas["projeto"] / ".env").exists()  # nunca escreve no .env do projeto


def test_salvar_chave_avisa_quando_o_projeto_manda(pastas: dict[str, Path]) -> None:
    (pastas["projeto"] / ".env").write_text(f"GEMINI_API_KEY={CHAVE}\n", "utf-8")
    resultado = _api().salvar_chave(CHAVE_NOVA)
    assert resultado == {"ok": True, "mensagem": api_config.MSG_CHAVE_DO_PROJETO}
    assert (pastas["projeto"] / ".env").read_text("utf-8") == f"GEMINI_API_KEY={CHAVE}\n"


# ------------------------------------------------------------------ API: vozes e preferencias
def test_amostra_voz(
    pastas: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vozes, "pasta_amostras", lambda: tmp_path)
    (tmp_path / "Puck.wav").write_bytes(b"RIFF1234WAVE")
    api = _api()
    ok = api.amostra_voz("Puck")
    assert ok["ok"] is True and ok["dados"].startswith("data:audio/wav;base64,")
    assert api.amostra_voz("Kore") == {"ok": False, "dados": "", "mensagem": "amostra indisponível"}
    assert api.amostra_voz("../../segredo")["ok"] is False
    assert api.amostra_voz({"id": "Puck"})["ok"] is False


def test_salvar_preferencias_ok(pastas: dict[str, Path]) -> None:
    preferencias.salvar_visual("aura")
    api = _api()
    assert api.salvar_preferencias({"nome": "  Ana  ", "voz": "Leda", "fone": True}) == {
        "ok": True,
        "mensagem": "",
    }
    assert preferencias.carregar() == {"visual": "aura", "nome": "Ana", "voz": "Leda", "fone": True}
    assert api.salvar_preferencias({"nome": ""})["ok"] is True
    assert preferencias.carregar()["nome"] == ""


def test_salvar_preferencias_avisa_quando_o_env_manda(pastas: dict[str, Path]) -> None:
    # Caso do Mateus: JARVIS_VOZ no .env do projeto (copiado do .env.example) ganha da janela.
    (pastas["projeto"] / ".env").write_text("JARVIS_VOZ=Charon\n", encoding="utf-8")
    api = _api()
    resultado = api.salvar_preferencias({"voz": "Puck", "nome": "Ana"})
    assert resultado["ok"] is True
    assert "JARVIS_VOZ" in resultado["mensagem"]
    assert "JARVIS_NOME_USUARIO" not in resultado["mensagem"]  # o nome nao esta no .env
    assert preferencias.carregar()["voz"] == "Puck"  # salvou mesmo assim
    assert api.salvar_preferencias({"voz": "Charon"}) == {"ok": True, "mensagem": ""}


@pytest.mark.parametrize(
    "dados",
    [
        {"voz": "Hacker"},
        {"voz": "charon"},
        {"nome": "linha1\nlinha2"},
        {"nome": "x" * 41},
        {"nome": 123},
        {"fone": "sim"},
        "nao e dict",
        None,
        ["nome"],
    ],
)
def test_salvar_preferencias_recusa_invalidos(pastas: dict[str, Path], dados: object) -> None:
    preferencias.salvar_visual("aura")
    resultado = _api().salvar_preferencias(dados)
    assert resultado["ok"] is False and resultado["mensagem"]
    assert preferencias.carregar() == {"visual": "aura"}  # nada mudou


def test_salvar_visual_continua(pastas: dict[str, Path]) -> None:
    api = _api()
    assert api.salvar_visual("reator") is True
    assert api.salvar_visual("<script>") is False


# ------------------------------------------------------------------ API: assistente
def test_concluir_configuracao(pastas: dict[str, Path]) -> None:
    controlador = _ControladorFalso()
    api = _api(controlador=controlador)
    assert api.concluir_configuracao() == {"ok": False, "mensagem": api_config.MSG_SEM_CHAVE}
    assert controlador.chamadas == []
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})
    assert api.concluir_configuracao() == {"ok": True, "mensagem": ""}
    assert controlador.chamadas == ["iniciar"]
    assert preferencias.carregar()["configurado"] is True


def test_aplicar_configuracao_reinicia(pastas: dict[str, Path]) -> None:
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})
    controlador = _ControladorFalso()
    api = _api(controlador=controlador)
    assert api.aplicar_configuracao()["ok"] is True
    assert controlador.chamadas == ["reiniciar"]
    controlador.resultado = False
    assert api.aplicar_configuracao()["ok"] is False
    assert _api().aplicar_configuracao()["ok"] is False  # sem controlador: nao levanta


def test_api_nunca_levanta(pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args: Any, **kwargs: Any) -> Settings:
        raise RuntimeError("inesperado")

    api = _api(carregar_settings=explode)
    assert api.estado_config() == {}
    assert api.testar_chave("")["ok"] is False
    assert api.concluir_configuracao()["ok"] is False
    assert api.aplicar_configuracao()["ok"] is False
    assert api.elevenlabs_testar("", "")["ok"] is False
    assert api.elevenlabs_listar_vozes("")["ok"] is False
    assert api.abrir_link("pasta_logs") is False


# ------------------------------------------------------------------ API: microfone
class _StreamFalso:
    def __init__(self) -> None:
        self.fechado = False

    def read(self, n: int, exception_on_overflow: bool = True) -> bytes:
        time.sleep(0.005)
        return array.array("h", [3000, -3000] * (n // 2)).tobytes()

    def stop_stream(self) -> None:
        pass

    def close(self) -> None:
        self.fechado = True


class _PyAudioFalso:
    paInt16 = 8

    def __init__(self, falhar: bool = False) -> None:
        self.falhar = falhar
        self.stream = _StreamFalso()
        self.terminado = False
        self.abertos: list[dict] = []

    def PyAudio(self) -> _PyAudioFalso:  # noqa: N802 - imita o pyaudio
        return self

    def open(self, **kwargs: Any) -> _StreamFalso:
        if self.falhar:
            raise OSError("sem microfone")
        self.abertos.append(kwargs)
        return self.stream

    def terminate(self) -> None:
        self.terminado = True


def _esperar(condicao: Any, tempo: float = 2.0) -> bool:
    fim = time.monotonic() + tempo
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.01)
    return False


def test_microfone_mede_nivel_e_para(pastas: dict[str, Path]) -> None:
    falso = _PyAudioFalso()
    janela = _Janela()
    api = _api(janela=janela, modulo_pyaudio=lambda: falso, controlador=_ControladorFalso())
    assert api.microfone_iniciar() == {"ok": True, "mensagem": ""}
    assert api.microfone_iniciar()["ok"] is True  # de novo: nao abre outro
    assert _esperar(lambda: len(janela.niveis) >= 3)
    assert all(0.0 < n <= 1.0 for n in janela.niveis[:3])
    assert api.microfone_parar() is True
    assert _esperar(lambda: falso.terminado)
    assert falso.stream.fechado and janela.niveis[-1] == 0.0
    assert len(falso.abertos) == 1 and falso.abertos[0]["rate"] == 16_000
    assert api.microfone_parar() is True  # parar de novo nao quebra


def test_microfone_sem_pyaudio(pastas: dict[str, Path]) -> None:
    def sem() -> Any:
        raise ImportError("pyaudio")

    resultado = _api(modulo_pyaudio=sem).microfone_iniciar()
    assert resultado["ok"] is False and "microfone" in resultado["mensagem"]


def test_microfone_sem_dispositivo(pastas: dict[str, Path]) -> None:
    falso = _PyAudioFalso(falhar=True)
    resultado = _api(modulo_pyaudio=lambda: falso).microfone_iniciar()
    assert resultado["ok"] is False and "microfone" in resultado["mensagem"]
    assert falso.terminado


def test_microfone_recusa_com_assistente_rodando(pastas: dict[str, Path]) -> None:
    falso = _PyAudioFalso()
    api = _api(modulo_pyaudio=lambda: falso, controlador=_ControladorFalso(rodando=True))
    assert api.microfone_iniciar()["ok"] is False
    assert falso.abertos == []


def test_concluir_para_o_microfone(pastas: dict[str, Path]) -> None:
    armazenamento.salvar_segredos({"GEMINI_API_KEY": CHAVE})
    falso = _PyAudioFalso()
    api = _api(modulo_pyaudio=lambda: falso, controlador=_ControladorFalso(), janela=_Janela())
    api.microfone_iniciar()
    assert api.concluir_configuracao()["ok"] is True
    assert _esperar(lambda: falso.terminado)


def test_teste_microfone_para_sozinho_no_limite() -> None:
    falso = _PyAudioFalso()
    niveis: list[float] = []
    teste = _MedidorMic(niveis.append, modulo_pyaudio=lambda: falso, limite_s=0.05)
    assert teste.iniciar()[0] is True
    assert _esperar(lambda: falso.terminado)
    assert not teste.ativo


# ------------------------------------------------------------------ API: ElevenLabs
def _transporte(status: int, corpo: Any, registro: list[httpx.Request] | None = None) -> Any:
    def responder(request: httpx.Request) -> httpx.Response:
        if registro is not None:
            registro.append(request)
        if isinstance(corpo, bytes):
            return httpx.Response(status, content=corpo)
        return httpx.Response(status, json=corpo)

    return httpx.MockTransport(responder)


def test_elevenlabs_listar_vozes_ok(pastas: dict[str, Path]) -> None:
    pedidos: list[httpx.Request] = []
    corpo = {
        "voices": [
            {"voice_id": VOZ_EL, "name": "Rachel"},
            {"voice_id": "../../hack", "name": "ruim"},
            {"voice_id": "AbCdEfGh12345678", "name": "Nome\ncom quebra"},
        ]
    }
    api = _api(transporte_http=_transporte(200, corpo, pedidos))
    resultado = api.elevenlabs_listar_vozes(CHAVE_EL)
    assert resultado == {
        "ok": True,
        "vozes": [
            {"id": VOZ_EL, "nome": "Rachel"},
            {"id": "AbCdEfGh12345678", "nome": "Nomecom quebra"},
        ],
        "mensagem": "",
    }
    assert pedidos[0].url == httpx.URL(verificacao.ELEVENLABS_VOICES_URL)
    assert pedidos[0].headers["xi-api-key"] == CHAVE_EL


def test_elevenlabs_listar_sem_permissao(
    pastas: dict[str, Path], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    corpo = {
        "detail": {
            "status": "missing_permissions",
            "message": "The API key you used is missing the permission voices_read",
        }
    }
    resultado = _api(transporte_http=_transporte(401, corpo)).elevenlabs_listar_vozes(CHAVE_EL)
    assert resultado["ok"] is False and resultado["vozes"] == []
    assert "Voices: read" in resultado["mensagem"]
    assert CHAVE_EL not in caplog.text


def test_elevenlabs_listar_chave_invalida(pastas: dict[str, Path]) -> None:
    corpo = {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}
    resultado = _api(transporte_http=_transporte(401, corpo)).elevenlabs_listar_vozes(CHAVE_EL)
    assert resultado["mensagem"] == verificacao.EL_MSG_INVALIDA


def test_elevenlabs_listar_sem_rede(pastas: dict[str, Path]) -> None:
    def falha(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rede")

    api = _api(transporte_http=httpx.MockTransport(falha))
    assert api.elevenlabs_listar_vozes(CHAVE_EL)["mensagem"] == verificacao.EL_MSG_SEM_INTERNET


def test_elevenlabs_listar_formato_invalido_e_chave_salva(pastas: dict[str, Path]) -> None:
    api = _api(transporte_http=_transporte(200, {"voices": []}))
    assert api.elevenlabs_listar_vozes("x y")["mensagem"] == verificacao.EL_MSG_FORMATO
    assert api.elevenlabs_listar_vozes("")["mensagem"] == api_config.MSG_EL_SEM_CHAVE
    armazenamento.salvar_segredos({"ELEVENLABS_API_KEY": CHAVE_EL})
    assert api.elevenlabs_listar_vozes("")["mensagem"] == verificacao.EL_MSG_SEM_VOZES


def test_elevenlabs_testar_toca_o_audio(pastas: dict[str, Path]) -> None:
    pedidos: list[httpx.Request] = []
    tocados: list[bytes] = []
    pcm = b"\x01\x00" * 2400
    api = _api(transporte_http_async=_transporte(200, pcm, pedidos), tocar=tocados.append)
    assert api.elevenlabs_testar(CHAVE_EL, VOZ_EL)["ok"] is True
    assert tocados == [pcm]
    assert VOZ_EL in str(pedidos[0].url) and pedidos[0].headers["xi-api-key"] == CHAVE_EL


@pytest.mark.parametrize(
    ("status", "corpo", "mensagem"),
    [
        (
            401,
            {"detail": {"status": "missing_permissions", "message": "missing text_to_speech"}},
            verificacao.EL_MSG_SEM_PERMISSAO_FALA,
        ),
        (
            401,
            {"detail": {"status": "quota_exceeded", "message": "quota"}},
            verificacao.EL_MSG_SEM_CREDITOS,
        ),
        (
            404,
            {"detail": {"status": "voice_not_found", "message": "x"}},
            verificacao.EL_MSG_VOZ_NAO_ACHADA,
        ),
        (401, {"detail": {"status": "invalid_api_key"}}, verificacao.EL_MSG_INVALIDA),
    ],
)
def test_elevenlabs_testar_erros(
    pastas: dict[str, Path], status: int, corpo: dict, mensagem: str
) -> None:
    tocados: list[bytes] = []
    api = _api(transporte_http_async=_transporte(status, corpo), tocar=tocados.append)
    assert api.elevenlabs_testar(CHAVE_EL, VOZ_EL) == {"ok": False, "mensagem": mensagem}
    assert tocados == []


@pytest.mark.parametrize("voz", ["../../v1/user", "a b", "", "x" * 100, None])
def test_elevenlabs_testar_recusa_voz_estranha(pastas: dict[str, Path], voz: object) -> None:
    pedidos: list[httpx.Request] = []
    api = _api(transporte_http_async=_transporte(200, b"\x00\x00", pedidos), tocar=lambda d: None)
    assert api.elevenlabs_testar(CHAVE_EL, voz)["ok"] is False
    assert pedidos == []


def test_elevenlabs_salvar_e_desligar(pastas: dict[str, Path]) -> None:
    api = _api()
    assert api.elevenlabs_salvar(CHAVE_EL, VOZ_EL, "Rachel")["ok"] is True
    settings = _settings()
    assert settings.uses_elevenlabs and settings.elevenlabs_voice_id == VOZ_EL
    assert preferencias.carregar()["elevenlabs_voz_nome"] == "Rachel"
    # trocar so a voz, mantendo a chave salva
    assert api.elevenlabs_salvar("", "AbCdEfGh12345678", "Outra\nvoz")["ok"] is True
    assert _settings().elevenlabs_voice_id == "AbCdEfGh12345678"
    assert preferencias.carregar()["elevenlabs_voz_nome"] == "AbCdEfGh12345678"
    assert api.elevenlabs_desligar() == {"ok": True, "mensagem": "Voltei para a voz do Google."}
    assert not _settings().uses_elevenlabs
    assert "ELEVENLABS" not in pastas["env"].read_text("utf-8")
    assert "elevenlabs_voz_nome" not in preferencias.carregar()


def test_elevenlabs_salvar_recusa_invalidos(pastas: dict[str, Path]) -> None:
    api = _api()
    assert api.elevenlabs_salvar("", VOZ_EL, "x")["ok"] is False  # sem chave salva
    assert api.elevenlabs_salvar(CHAVE_EL + "\nGEMINI_API_KEY=x", VOZ_EL, "x")["ok"] is False
    assert api.elevenlabs_salvar(CHAVE_EL, "../x", "x")["ok"] is False
    assert not pastas["env"].exists()


def test_elevenlabs_desligar_quando_o_projeto_define(pastas: dict[str, Path]) -> None:
    (pastas["projeto"] / ".env").write_text(
        f"ELEVENLABS_API_KEY={CHAVE_EL}\nELEVENLABS_VOICE_ID={VOZ_EL}\n", "utf-8"
    )
    assert _settings().uses_elevenlabs
    resultado = _api().elevenlabs_desligar()
    assert resultado["ok"] is True
    assert "projeto" in resultado["mensagem"]
    # a chave continua no .env do projeto, mas o Jarvis passa a usar a voz do Google
    assert _settings().elevenlabs_configurado
    assert not _settings().uses_elevenlabs
    assert "ELEVENLABS_API_KEY" in (pastas["projeto"] / ".env").read_text("utf-8")


def test_fonte_voz_escolhe_google_ou_elevenlabs(pastas: dict[str, Path]) -> None:
    """O caso do Mateus: ElevenLabs no .env do projeto e voz do Google escolhida na janela."""
    (pastas["projeto"] / ".env").write_text(
        f"ELEVENLABS_API_KEY={CHAVE_EL}\nELEVENLABS_VOICE_ID={VOZ_EL}\n", "utf-8"
    )
    api = _api()
    assert api.estado_config()["fonte_voz"] == "elevenlabs"
    assert api.salvar_preferencias({"voz": "Puck", "fonte_voz": "google"})["ok"] is True
    s = _settings()
    assert not s.uses_elevenlabs and s.voice == "Puck"
    estado = api.estado_config()
    assert estado["fonte_voz"] == "google"
    assert estado["elevenlabs"] == {**estado["elevenlabs"], "ativo": False, "configurado": True}
    assert api.salvar_preferencias({"fonte_voz": "elevenlabs"})["ok"] is True
    assert _settings().uses_elevenlabs
    assert api.salvar_preferencias({"fonte_voz": "outra"})["ok"] is False


def test_fonte_elevenlabs_recusada_sem_configurar(pastas: dict[str, Path]) -> None:
    resultado = _api().salvar_preferencias({"fonte_voz": "elevenlabs"})
    assert resultado == {"ok": False, "mensagem": api_config.MSG_FONTE_SEM_EL}


# ------------------------------------------------------------------ API: links
def test_abrir_link_lista_fechada(pastas: dict[str, Path]) -> None:
    urls: list[str] = []
    abertas: list[Path] = []
    api = _api(
        abrir_url=lambda u: urls.append(u) or True, abrir_pasta=lambda p: abertas.append(p) or True
    )
    assert api.abrir_link("chave_google") is True
    assert api.abrir_link("elevenlabs") is True
    assert api.abrir_link("repositorio") is True
    assert api.abrir_link("instagram") is True
    assert urls == [
        "https://aistudio.google.com/apikey",
        "https://elevenlabs.io",
        "https://github.com/mateusmirandaia/jarvis",
        "https://www.instagram.com/mateusmirandaia.ia/",
    ]
    assert api.abrir_link("pasta_config") is True
    assert api.abrir_link("pasta_logs") is True
    assert abertas == [pastas["usuario"], pastas["projeto"] / "logs"]


@pytest.mark.parametrize(
    "nome",
    ["https://evil.example", "file:///C:/Windows", "CHAVE_GOOGLE", "", None, 1, ["repositorio"]],
)
def test_abrir_link_desconhecido(pastas: dict[str, Path], nome: object) -> None:
    chamadas: list[object] = []
    api = _api(
        abrir_url=lambda u: chamadas.append(u) or True,
        abrir_pasta=lambda p: chamadas.append(p) or True,
    )
    assert api.abrir_link(nome) is False
    assert chamadas == []


# ------------------------------------------------------------------ chave fora de log/retorno
def test_chave_nunca_aparece_em_retorno_nem_log(
    pastas: dict[str, Path], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    api = _api(
        fabrica_gemini=lambda chave: _ClienteGemini(
            _client_error(400, "API key not valid", "INVALID_ARGUMENT")
        ),
        transporte_http=_transporte(401, {"detail": {"status": "missing_permissions"}}),
        transporte_http_async=_transporte(401, {"detail": {"status": "invalid_api_key"}}),
        tocar=lambda d: None,
        controlador=_ControladorFalso(),
    )
    retornos = [
        api.testar_chave(CHAVE),
        api.salvar_chave(CHAVE),
        api.estado_config(),
        api.elevenlabs_listar_vozes(CHAVE_EL),
        api.elevenlabs_testar(CHAVE_EL, VOZ_EL),
        api.elevenlabs_salvar(CHAVE_EL, VOZ_EL, "Rachel"),
        api.estado_config(),
        api.concluir_configuracao(),
        api.aplicar_configuracao(),
    ]
    texto = json.dumps(retornos, ensure_ascii=False)
    for segredo in (CHAVE, CHAVE_EL):
        assert segredo not in texto
        assert segredo not in caplog.text
    assert "AIza" not in texto


# ------------------------------------------------------------------ controlador
class _AssistenteFalso:
    criados: list[_AssistenteFalso] = []

    def __init__(self, settings: Settings, observer: Any) -> None:
        self.settings = settings
        self.comecou = threading.Event()
        self.terminou = threading.Event()
        _AssistenteFalso.criados.append(self)

    async def run(self) -> None:
        self.comecou.set()
        try:
            await asyncio.sleep(3600)
        finally:
            self.terminou.set()


class _Observador:
    def __init__(self) -> None:
        self.eventos: list[tuple[str, Any]] = []

    def on_state(self, state: str) -> None:
        self.eventos.append(("state", state))

    def on_transcript(self, speaker: str, text: str) -> None:
        self.eventos.append(("transcript", (speaker, text)))

    def on_aviso_chave(self, mensagem: str) -> None:
        self.eventos.append(("aviso_chave", mensagem))

    def on_level(self, level: float) -> None:
        self.eventos.append(("level", level))


@pytest.fixture
def controlador_falso() -> Any:
    _AssistenteFalso.criados = []
    chave = {"valor": CHAVE}
    observador = _Observador()
    controlador = Controlador(
        observador,
        lambda: Settings(api_key=chave["valor"]),
        fabrica=_AssistenteFalso,
    )
    yield controlador, observador, chave
    controlador.parar(espera_s=2)


def test_controlador_iniciar_parar(controlador_falso: Any) -> None:
    controlador, _obs, _chave = controlador_falso
    assert controlador.iniciar() is True
    assert _esperar(lambda: _AssistenteFalso.criados)  # criado na thread do assistente
    primeiro = _AssistenteFalso.criados[0]
    assert primeiro.comecou.wait(2)
    assert controlador.rodando
    assert controlador.iniciar() is True and len(_AssistenteFalso.criados) == 1  # ja rodava
    assert controlador.parar() is True
    assert primeiro.terminou.is_set() and not controlador.rodando
    assert controlador.parar() is True  # parar de novo nao quebra


def test_controlador_reiniciar_pega_configuracao_nova(controlador_falso: Any) -> None:
    controlador, _obs, chave = controlador_falso
    controlador.iniciar()
    assert _esperar(lambda: _AssistenteFalso.criados)
    assert _AssistenteFalso.criados[0].comecou.wait(2)
    chave["valor"] = CHAVE_NOVA
    assert controlador.reiniciar() is True
    assert _AssistenteFalso.criados[0].terminou.is_set()
    assert _esperar(lambda: len(_AssistenteFalso.criados) == 2)
    assert _AssistenteFalso.criados[1].comecou.wait(2)
    assert _AssistenteFalso.criados[1].settings.api_key == CHAVE_NOVA


def test_controlador_sem_chave_nao_inicia(controlador_falso: Any) -> None:
    controlador, _obs, chave = controlador_falso
    chave["valor"] = ""
    assert controlador.iniciar() is False
    assert _AssistenteFalso.criados == [] and not controlador.rodando


def test_controlador_nao_trava_quem_chama() -> None:
    class Lento(_AssistenteFalso):
        def __init__(self, settings: Settings, observer: Any) -> None:
            time.sleep(0.3)  # criar o assistente demora (SDK, ferramentas)
            super().__init__(settings, observer)

    controlador = Controlador(_Observador(), lambda: Settings(api_key=CHAVE), fabrica=Lento)
    inicio = time.monotonic()
    controlador.iniciar()
    assert time.monotonic() - inicio < 0.2
    assert controlador.parar(espera_s=3) is True


def _controlador_que_falha(erro: BaseException) -> tuple[Controlador, _Observador]:
    class Falha:
        def __init__(self, settings: Settings, observer: Any) -> None:
            pass

        async def run(self) -> None:
            raise erro

    observador = _Observador()
    return Controlador(observador, lambda: Settings(api_key=CHAVE), fabrica=Falha), observador


def test_controlador_chave_recusada_avisa_a_janela() -> None:
    controlador, observador = _controlador_que_falha(ChaveInvalidaError("recusada"))
    controlador.iniciar()
    assert _esperar(lambda: ("aviso_chave", MSG_CHAVE_PAROU) in observador.eventos)
    assert ("state", "offline") in observador.eventos
    assert _esperar(lambda: not controlador.rodando)


def test_controlador_erro_qualquer_vira_mensagem() -> None:
    controlador, observador = _controlador_que_falha(RuntimeError("boom"))
    controlador.iniciar()
    assert _esperar(lambda: any(k == "transcript" for k, _ in observador.eventos))
    assert ("state", "offline") in observador.eventos
    assert not any(k == "aviso_chave" for k, _ in observador.eventos)


def test_controlador_observador_antigo_sem_aviso_chave() -> None:
    class Antigo:
        def __init__(self) -> None:
            self.falas: list[tuple[str, str]] = []

        def on_state(self, state: str) -> None:
            pass

        def on_transcript(self, speaker: str, text: str) -> None:
            self.falas.append((speaker, text))

    class Falha:
        def __init__(self, settings: Settings, observer: Any) -> None:
            pass

        async def run(self) -> None:
            raise ChaveInvalidaError("x")

    antigo = Antigo()
    Controlador(antigo, lambda: Settings(api_key=CHAVE), fabrica=Falha).iniciar()
    assert _esperar(lambda: ("sistema", MSG_CHAVE_PAROU) in antigo.falas)


# ------------------------------------------------------------------ LiveAssistant: chave
def test_erro_de_autenticacao_reconhece_live_e_rest() -> None:
    from google.genai import errors

    assert verificacao.erro_de_autenticacao(
        errors.APIError(1008, "API key not valid. Please pass a valid API key.", None)
    )
    assert verificacao.erro_de_autenticacao(_client_error(403, "denied", "PERMISSION_DENIED"))
    grupo = ExceptionGroup("tarefas", [_client_error(401, "x", "UNAUTHENTICATED")])
    assert verificacao.erro_de_autenticacao(grupo)
    assert not verificacao.erro_de_autenticacao(errors.APIError(1011, "internal error", None))
    assert not verificacao.erro_de_autenticacao(
        errors.APIError(1008, "models/x is not found for API version v1beta", None)
    )
    assert not verificacao.erro_de_autenticacao(RuntimeError("API key not valid"))


def _live_falso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, erro: Exception) -> Any:
    pytest.importorskip("google.genai")
    from jarvis.assistants import live_assistant
    from jarvis.tools import ToolRegistry

    class AudioFalso:
        def close(self) -> None:
            pass

    monkeypatch.setattr(live_assistant, "AudioIO", AudioFalso)
    settings = Settings(api_key="x", project_root=tmp_path)
    registry = ToolRegistry(settings, confirm=lambda title, message: False)
    observador = _Observador()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assistente = live_assistant.LiveAssistant(settings, registry, observer=observador)
    tentativas: list[int] = []

    async def sessao() -> None:
        tentativas.append(1)
        if len(tentativas) > 1:
            raise asyncio.CancelledError
        raise erro

    async def sem_espera(_segundos: float) -> None:
        return None

    monkeypatch.setattr(assistente, "_session", sessao)
    monkeypatch.setattr(live_assistant.asyncio, "sleep", sem_espera)
    return assistente, observador, tentativas


def test_live_para_de_reconectar_com_chave_recusada(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from google.genai import errors

    erro = errors.APIError(1008, f"API key not valid. url ?key={CHAVE}", None)
    assistente, observador, tentativas = _live_falso(monkeypatch, tmp_path, erro)
    with pytest.raises(ChaveInvalidaError) as capturado:
        asyncio.run(assistente.run())
    assert tentativas == [1]  # nao tentou de novo
    assert ("state", "offline") in observador.eventos
    assert CHAVE not in str(capturado.value)
    assert capturado.value.__cause__ is None and capturado.value.__suppress_context__


def test_live_queda_comum_continua_reconectando(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    assistente, _obs, tentativas = _live_falso(monkeypatch, tmp_path, RuntimeError("rede caiu"))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(assistente.run())
    assert len(tentativas) == 2  # reconectou


# ------------------------------------------------------------------ OrbWindow: novas chamadas
def test_orb_envia_mic_teste_e_aviso_chave(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import importlib

    teste_orb = importlib.import_module("test_orb")
    from jarvis.ui.orb_window import OrbWindow

    fake = teste_orb._FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(preferencias, "caminho_preferencias", lambda: tmp_path / "p.json")
    api = _api()
    janela = OrbWindow(None, api=api)
    ponte = fake.created_with["js_api"]
    assert ponte is not api  # a janela recebe a fachada, nao a ApiJs
    assert not hasattr(ponte, "_abrir_url")
    teste_orb._load(fake)
    for nivel in (0.1, 0.2, 0.3):
        janela.on_mic_teste(nivel)
    janela.on_mic_teste(float("nan"))
    janela.on_mic_teste("x")  # type: ignore[arg-type]
    janela.on_aviso_chave('A chave "parou" </script>')
    janela.abrir_configuracao("chave")
    janela.abrir_configuracao("javascript:alert(1)")
    assert teste_orb._wait_js(fake, lambda js: "window.jarvis.setMicTeste(0.300)" in js)
    assert teste_orb._wait_js(fake, lambda js: 'window.jarvis.abrirConfiguracao("chave")' in js)
    js = fake.window.js
    assert 'window.jarvis.avisoChave("A chave \\"parou\\" </script>")' in js
    assert "window.jarvis.abrirConfiguracao()" in js  # aba desconhecida = sem aba
    assert sum(c.startswith("window.jarvis.setMicTeste") for c in js) <= 3


def test_cli_orb_sem_chave_abre_a_janela(
    pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import jarvis.__main__ as principal

    chamadas: list[Settings] = []
    monkeypatch.setattr(principal, "_run_orb", lambda settings: chamadas.append(settings))
    monkeypatch.setattr(principal, "setup_logging", lambda caminho: None)
    assert principal.main([]) == 0
    assert chamadas and chamadas[0].api_key == ""


def test_cli_voz_sem_chave_explica(
    pastas: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    import jarvis.__main__ as principal

    mensagens: list[str] = []
    monkeypatch.setattr(principal, "_tell_user", mensagens.append)
    monkeypatch.setattr(principal, "setup_logging", lambda caminho: None)
    assert principal.main(["--modo", "voz"]) == 1
    assert "GEMINI_API_KEY" in mensagens[0] and "janela" in mensagens[0]


def test_tell_user_sem_console_nao_quebra(monkeypatch: pytest.MonkeyPatch) -> None:
    import jarvis.__main__ as principal
    from jarvis.os_integration import windows

    def explode(titulo: str, mensagem: str) -> None:
        raise OSError("sem janela")

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(windows, "show_message", explode)
    principal._tell_user("oi")
    principal._print_safe("oi")


def test_ferramentas_protegem_a_pasta_do_usuario(pastas: dict[str, Path], tmp_path: Path) -> None:
    from jarvis.tools import ToolRegistry

    registry = ToolRegistry(
        Settings(api_key="x", project_root=tmp_path / "p"), confirm=lambda t, m: False
    )
    assert registry.guard.is_protected(pastas["usuario"] / ".env")


def test_ponte_js_so_expoe_o_contrato() -> None:
    """A janela recebe uma fachada: nada de nomes privados nem atributos da ApiJs."""
    from jarvis.ui.api_config import METODOS_PUBLICOS, ApiJs, ponte_js

    chamadas: list[tuple[str, tuple]] = []

    class Falsa(ApiJs):
        def __init__(self) -> None:  # nao precisa do estado real
            pass

        def salvar_visual(self, id_visual: object) -> bool:
            chamadas.append(("salvar_visual", (id_visual,)))
            return True

    ponte = ponte_js(Falsa())
    publicos = sorted(n for n in dir(ponte) if not n.startswith("_"))
    assert publicos == sorted(METODOS_PUBLICOS)
    assert not hasattr(ponte, "_abrir_url")
    assert not hasattr(ponte, "_api")
    assert not hasattr(ponte, "__dict__")
    assert ponte.salvar_visual("galaxia") is True
    assert chamadas == [("salvar_visual", ("galaxia",))]


# ---------------------------------------------------------- chave do Google (formato novo)
_CHAVE_NOVA_FALSA = "AQ.Ab8RN6Lfake_chave_de_teste-0123456789abcdefghijklmn"


@pytest.mark.parametrize(
    "chave",
    ["AIzaSyBOA_falsa_0123456789abcdefghijklmn", _CHAVE_NOVA_FALSA],
)
def test_chave_google_plausivel_aceita_formato_antigo_e_novo(chave: str) -> None:
    assert verificacao.chave_google_plausivel(chave)


@pytest.mark.parametrize(
    "chave",
    [
        "",
        "curta",
        ".AQAb8RN6Lfake_chave_de_teste_01234",
        "AQ.Ab8RN6Lfake_chave_de_teste_0123.",
        "AQ.Ab8 RN6Lfake_chave_de_teste_0123",
        "AQ.Ab8/RN6Lfake_chave_de_teste_0123",
    ],
)
def test_chave_google_plausivel_recusa_formatos_ruins(chave: str) -> None:
    assert not verificacao.chave_google_plausivel(chave)


def test_redigir_apaga_chave_google_formato_novo() -> None:
    saida = redigir(f"erro com a chave {_CHAVE_NOVA_FALSA} no pedido")
    assert "Ab8RN6L" not in saida
