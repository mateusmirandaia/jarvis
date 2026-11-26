"""Apps modernos do Windows (Calculadora etc.) e log detalhado.

Bug real (26/11): o Jarvis abria a Calculadora mas nao a via para fechar, porque a janela
dos apps modernos pertence ao ApplicationFrameHost.exe (processo protegido). Agora o
list_windows troca a moldura pelo processo real (CalculatorApp.exe) ou, se nao der (app
minimizado), por "app do Windows", que ainda fecha pelo titulo.
"""

from __future__ import annotations

import logging

import pytest

from jarvis.assistants import live_assistant
from jarvis.config import Settings
from jarvis.os_integration import windows
from jarvis.tools.app_tools import AppTools


def _janelas(monkeypatch: pytest.MonkeyPatch, lista: list[windows.Window]):
    fechadas: list[int] = []
    mortos: list[str] = []
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(
        windows,
        "list_windows",
        lambda excl=(): [w for w in lista if w.process.lower() not in set(excl)],
    )
    monkeypatch.setattr(windows, "close_window", fechadas.append)
    monkeypatch.setattr(windows, "kill_process", lambda p: mortos.append(p) or True)
    return fechadas, mortos


def test_calculadora_resolvida_aparece_e_fecha(monkeypatch: pytest.MonkeyPatch) -> None:
    fechadas, _ = _janelas(monkeypatch, [windows.Window("CalculatorApp.exe", "Calculadora", 7)])
    assert "Calculadora" in AppTools().list_open_apps()
    assert AppTools().close_app("calculadora").startswith("Fechei")
    assert fechadas == [7]


def test_calculadora_forcada_mata_o_processo_real(monkeypatch: pytest.MonkeyPatch) -> None:
    _, mortos = _janelas(monkeypatch, [windows.Window("CalculatorApp.exe", "Calculadora", 7)])
    assert AppTools().close_app("calculadora", forcar=True) == "Fechado a forca: CalculatorApp.exe"
    assert mortos == ["CalculatorApp.exe"]


def test_app_moderno_sem_processo_fecha_pelo_titulo(monkeypatch: pytest.MonkeyPatch) -> None:
    fechadas, mortos = _janelas(
        monkeypatch, [windows.Window(windows.APP_MODERNO, "Calculadora", 9)]
    )
    assert "Calculadora" in AppTools().list_open_apps()
    assert AppTools().close_app("calculadora").startswith("Fechei")
    # forcar nao tenta matar a moldura protegida: fecha a janela do jeito normal
    assert AppTools().close_app("calculadora", forcar=True).startswith("Fechei")
    assert fechadas == [9, 9] and mortos == []


def test_moldura_crua_continua_protegida(monkeypatch: pytest.MonkeyPatch) -> None:
    fechadas, mortos = _janelas(
        monkeypatch, [windows.Window("ApplicationFrameHost.exe", "Calculadora", 9)]
    )
    assert "Nao achei" in AppTools().close_app("calculadora", forcar=True)
    assert fechadas == [] and mortos == []


def test_log_detalhado_ligado_pelo_codigo_e_desligavel(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.delenv("JARVIS_LOG_DETALHADO", raising=False)
    monkeypatch.setattr("jarvis.config.congelado", lambda: False)
    assert _carregar(tmp_path).log_detalhado is True
    monkeypatch.setenv("JARVIS_LOG_DETALHADO", "0")
    assert _carregar(tmp_path).log_detalhado is False


def test_log_detalhado_desligado_no_instalador(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("JARVIS_LOG_DETALHADO", raising=False)
    monkeypatch.setattr("jarvis.config.congelado", lambda: True)
    assert _carregar(tmp_path).log_detalhado is False
    monkeypatch.setenv("JARVIS_LOG_DETALHADO", "1")
    assert _carregar(tmp_path).log_detalhado is True


def _carregar(tmp_path) -> Settings:
    return Settings.from_env(
        tmp_path / "nao.env",
        exigir_chave=False,
        env_usuario=tmp_path / "u.env",
        preferencias_arquivo=tmp_path / "p.json",
    )


def test_curto_encurta_e_tira_quebras() -> None:
    assert live_assistant._curto("a\n b  c") == "a b c"
    texto = live_assistant._curto("x" * 500)
    assert len(texto) == 301 and texto.endswith("…")


def test_execute_registra_acao_com_tempo_e_resultado(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import asyncio

    class _Reg:
        def get(self, name):
            return lambda **kw: "Fechei: CalculatorApp.exe (Calculadora)"

        def timeout_for(self, name, settings):
            return 5

    assistente = live_assistant.LiveAssistant.__new__(live_assistant.LiveAssistant)
    assistente.registry = _Reg()
    assistente.settings = Settings(api_key="x", log_detalhado=True)
    assistente._notify_tool = lambda *a, **k: None
    with caplog.at_level(logging.INFO, logger="jarvis.assistants.live_assistant"):
        r = asyncio.run(assistente._execute("close_app", {"nome": "calculadora"}))
    assert r.startswith("Fechei")
    texto = caplog.text
    assert "acao pedida: close_app" in texto and "calculadora" in texto
    assert "acao close_app terminou em" in texto and "CalculatorApp.exe" in texto
