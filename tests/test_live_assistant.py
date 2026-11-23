"""Testes do LiveAssistant sem internet e sem microfone (so configuracao e ferramentas)."""

from __future__ import annotations

import asyncio
import time
import warnings
from pathlib import Path

import pytest

from jarvis.config import Settings
from jarvis.tools import ToolRegistry

pytest.importorskip("google.genai")

from jarvis.assistants.live_assistant import LiveAssistant  # noqa: E402


@pytest.fixture
def assistant(tmp_path: Path) -> LiveAssistant:
    settings = Settings(api_key="x", project_root=tmp_path, user_name="Carlos")
    registry = ToolRegistry(settings, confirm=lambda title, message: False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return LiveAssistant(settings, registry)


def test_cliente_live_usa_v1beta(assistant: LiveAssistant) -> None:
    # Sem v1beta a SDK 3.x usa v1 e o Live responde HTTP 404.
    api_client = getattr(assistant.client, "_api_client", None)
    http_options = getattr(api_client, "_http_options", None)
    if http_options is None:
        pytest.skip("esta versao da SDK nao expoe as opcoes HTTP")
    assert http_options.api_version == "v1beta"


def test_config_tem_todas_as_ferramentas(assistant: LiveAssistant) -> None:
    declarations = assistant.config.tools[0].function_declarations
    assert [d.name for d in declarations] == assistant.registry.names


def test_config_usa_nome_do_usuario(assistant: LiveAssistant) -> None:
    assert "assistente pessoal do Carlos" in str(assistant.config.system_instruction)


def test_acao_fora_da_lista_e_recusada(assistant: LiveAssistant) -> None:
    assert asyncio.run(assistant._execute("run_command", {"cmd": "del"})) == "Acao nao permitida."


def test_argumento_errado_vira_frase(assistant: LiveAssistant) -> None:
    resultado = asyncio.run(assistant._execute("current_time", {"inventado": 1}))
    assert resultado.startswith("ERRO:")


def test_acao_lenta_vira_frase_de_tempo(
    assistant: LiveAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(assistant.registry, "get", lambda name: lambda: time.sleep(0.5) or "ok")
    monkeypatch.setattr(assistant.registry, "timeout_for", lambda name, settings: 0.05)
    resultado = asyncio.run(assistant._execute("lenta", {}))
    assert "demorou demais" in resultado


def test_ferramentas_sao_assincronas(assistant: LiveAssistant) -> None:
    from google.genai import types

    declarations = assistant.config.tools[0].function_declarations
    assert all(d.behavior == types.Behavior.NON_BLOCKING for d in declarations)


def test_resultado_da_acao_volta_quando_ele_terminar_de_falar(assistant: LiveAssistant) -> None:
    from google.genai import types

    sent: list = []

    class FakeSession:
        async def send_tool_response(self, function_responses):
            sent.extend(function_responses)

    call = types.FunctionCall(id="1", name="current_time", args={})
    asyncio.run(
        assistant._handle_tool_call(FakeSession(), types.LiveServerToolCall(function_calls=[call]))
    )
    assert sent and sent[0].scheduling == types.FunctionResponseScheduling.WHEN_IDLE
    assert sent[0].id == "1"


def test_sessao_que_caiu_nao_derruba_a_acao(assistant: LiveAssistant) -> None:
    from google.genai import types

    class BrokenSession:
        async def send_tool_response(self, function_responses):
            raise ConnectionError("sessao fechada")

    call = types.FunctionCall(id="2", name="current_time", args={})
    asyncio.run(  # nao pode levantar
        assistant._handle_tool_call(
            BrokenSession(), types.LiveServerToolCall(function_calls=[call])
        )
    )
