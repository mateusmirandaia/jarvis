"""Testes de friendly_message e safe_tool (errors.py)."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from jarvis.errors import MAX_RESULT_CHARS, ConfigError, JarvisError, friendly_message, safe_tool


@pytest.mark.parametrize(
    ("erro", "trecho"),
    [
        (PermissionError("negado"), "permissao"),
        (FileNotFoundError("sumiu"), "nao encontrei"),
        (TimeoutError(), "demorou demais"),
        (asyncio.TimeoutError(), "demorou demais"),  # noqa: UP041 - testa o alias antigo tambem
        (OSError("falhou"), "o Windows recusou"),
        (ValueError("x"), "algo inesperado"),
        (RuntimeError("y"), "algo inesperado"),
    ],
)
def test_friendly_message(erro: BaseException, trecho: str) -> None:
    msg = friendly_message(erro)
    assert msg.startswith("ERRO: ")
    assert trecho in msg
    assert "sem termos tecnicos" in msg


def test_friendly_message_nao_vaza_detalhe_tecnico() -> None:
    msg = friendly_message(PermissionError(r"[WinError 5] Acesso negado: C:\segredo"))
    assert "WinError" not in msg
    assert "segredo" not in msg


def test_hierarquia_de_erros() -> None:
    assert issubclass(ConfigError, JarvisError)
    assert issubclass(JarvisError, Exception)


def _ferramenta_exemplo(caminho: str, forcar: bool = False) -> str:
    """Docstring de exemplo.

    Args:
        caminho: um caminho.
        forcar: se forca.
    """
    return f"ok {caminho} {forcar}"


def test_safe_tool_preserva_nome_doc_e_assinatura() -> None:
    embrulhada = safe_tool(_ferramenta_exemplo)
    assert embrulhada.__name__ == "_ferramenta_exemplo"
    assert embrulhada.__doc__ == _ferramenta_exemplo.__doc__
    assert inspect.signature(embrulhada) == inspect.signature(_ferramenta_exemplo)


def test_safe_tool_repassa_argumentos() -> None:
    embrulhada = safe_tool(_ferramenta_exemplo)
    assert embrulhada("x", forcar=True) == "ok x True"


def test_safe_tool_converte_resultado_para_str() -> None:
    assert safe_tool(lambda: 42)() == "42"


def test_safe_tool_corta_resultado_longo() -> None:
    resultado = safe_tool(lambda: "a" * (MAX_RESULT_CHARS * 3))()
    assert resultado.startswith("a" * MAX_RESULT_CHARS)
    assert resultado.endswith("(cortado)")
    assert len(resultado) < MAX_RESULT_CHARS + 30


def test_safe_tool_nao_corta_resultado_curto() -> None:
    texto = "b" * MAX_RESULT_CHARS
    assert safe_tool(lambda: texto)() == texto


@pytest.mark.parametrize(
    "erro", [ValueError("x"), PermissionError("y"), FileNotFoundError("z"), ZeroDivisionError()]
)
def test_safe_tool_nunca_levanta(erro: Exception) -> None:
    def quebra() -> str:
        raise erro

    resultado = safe_tool(quebra)()
    assert resultado == friendly_message(erro)


def test_safe_tool_registra_no_log(caplog: pytest.LogCaptureFixture) -> None:
    def quebra() -> str:
        raise ValueError("detalhe interno")

    with caplog.at_level("ERROR"):
        safe_tool(quebra)()
    assert any("detalhe interno" in (r.exc_text or "") or r.exc_info for r in caplog.records)
