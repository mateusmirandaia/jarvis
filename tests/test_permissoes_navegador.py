"""Aba Permissoes e passo Permissoes do assistente num Chrome de verdade.

Usa a mesma mesa de teste de ``test_e2e_navegador.py`` (ApiJs, OrbWindow e Controlador reais,
assistente de voz falso). So roda onde houver Playwright e Chrome; para rodar aqui:
``PYTHONPATH=src:<site-packages do venv> python3 -m pytest tests/test_permissoes_navegador.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from jarvis.config import Settings  # noqa: E402
from jarvis.tools import ToolRegistry, permissoes  # noqa: E402
from jarvis.ui import preferencias  # noqa: E402
from test_e2e_navegador import (  # noqa: E402
    CHAVE_BOA,
    _Assistente,
    _configurar,
    _sem_erros,
    abrir,
    navegador,
    pastas,
)

__all__ = ["abrir", "navegador", "pastas"]  # fixtures importadas

DESLIGADO = dict(permissoes.PADRAO)


def _registry(pastas: dict[str, Path]) -> ToolRegistry:
    """Registro com a fonte PADRAO (le o preferencias.json a cada chamada)."""
    return ToolRegistry(
        Settings(api_key="x", project_root=pastas["projeto"]), confirm=lambda t, m: False
    )


def _checado(m: Any, seletor: str) -> bool:
    return m.pg.is_checked(seletor)


def test_aba_permissoes_mostra_tudo_desligado_e_salva_na_hora(
    abrir: Any, pastas: dict[str, Path]
) -> None:
    _configurar(pastas)
    m = abrir()
    assert m.ate("document.getElementById('pilula-texto').textContent !== ''")
    inicios = len(_Assistente.log)
    reg = _registry(pastas)
    casa = Path.home()
    casa.mkdir(parents=True, exist_ok=True)
    assert reg.get("list_folder")(str(casa)) == permissoes.mensagem_bloqueio("list_folder")

    m.pg.click("#btn-config")
    # teclado: da aba Geral, seta para a direita vai para Permissoes
    m.pg.focus("#cfg-aba-geral")
    m.pg.keyboard.press("ArrowRight")
    assert m.pg.evaluate("document.activeElement.id") == "cfg-aba-permissoes"
    assert m.visivel("#cfg-painel-permissoes")
    assert m.ate("document.querySelectorAll('#cfg-permissoes input').length === 8")
    assert _checado(m, "#cfg-perm-arquivos-nenhum")
    for chave in ("apps", "internet", "email", "outros_drives"):
        assert not _checado(m, f"#cfg-perm-{chave}")
        assert m.pg.get_attribute(f"#cfg-perm-{chave}", "role") == "switch"
    # cada nivel com a explicacao ligada ao controle (leitor de tela)
    desc = m.pg.get_attribute("#cfg-perm-arquivos-ler_gravar_excluir", "aria-describedby")
    assert "Mesmo assim ele sempre pergunta antes de apagar" in m.texto(desc)
    rotulo = m.pg.evaluate("document.querySelector('label[for=\"cfg-perm-apps\"]').textContent")
    assert rotulo == "Abrir e fechar programas"
    # Sempre bloqueado: so leitura, sem nenhum controle
    itens = m.pg.locator("#cfg-permissoes .perm-bloqueado li")
    assert itens.count() == len(permissoes.SEMPRE_BLOQUEADO)
    assert m.pg.locator("#cfg-permissoes .perm-bloqueado input").count() == 0
    assert "Pastas de rede" in m.texto("cfg-painel-permissoes")

    # escolher "Só ler" pelo teclado e ligar internet
    m.pg.focus("#cfg-perm-arquivos-nenhum")
    m.pg.keyboard.press("ArrowDown")
    assert _checado(m, "#cfg-perm-arquivos-ler")
    m.pg.focus("#cfg-perm-internet")
    m.pg.keyboard.press("Space")
    assert _checado(m, "#cfg-perm-internet")
    assert m.pg.get_attribute("#cfg-perm-internet", "aria-checked") == "true"
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('ok')", 6000)
    assert "Já valem agora" in m.texto("config-status")
    assert preferencias.carregar()["permissoes"] == {
        **DESLIGADO,
        "arquivos": "ler",
        "internet": True,
    }
    # vale na hora, sem reconectar o assistente
    assert len(_Assistente.log) == inicios
    assert "desligada" not in reg.get("list_folder")(str(casa))
    assert reg.get("open_app")("calculadora") == permissoes.mensagem_bloqueio("open_app")

    # salvar de novo sem mudar nada
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').textContent === 'Nada mudou.'")

    # fechar e abrir: mostra o que foi salvo
    m.pg.click("#config-fechar")
    assert m.ate("document.getElementById('config').hidden")
    m.pg.click("#btn-config")
    m.pg.click("#cfg-aba-permissoes")
    assert m.ate("document.getElementById('cfg-perm-arquivos-ler').checked")
    assert _checado(m, "#cfg-perm-internet") and not _checado(m, "#cfg-perm-apps")
    _sem_erros(m)


def test_aba_permissoes_mudanca_junto_com_voz_reconecta_uma_vez(
    abrir: Any, pastas: dict[str, Path]
) -> None:
    _configurar(pastas)
    m = abrir()
    assert m.ate("document.getElementById('pilula-texto').textContent !== ''")
    inicios = len(_Assistente.log)
    m.pg.click("#btn-config")
    m.pg.click("#cfg-vozes .cartao-voz:nth-child(2) label")  # Puck
    m.pg.click("#cfg-aba-permissoes")
    m.pg.click("label[for='cfg-perm-arquivos-ler_gravar_excluir']")
    m.pg.click("label[for='cfg-perm-outros_drives']")
    m.pg.click("#config-salvar")
    assert m.ate("document.getElementById('config-status').classList.contains('ok')", 8000)
    assert len(_Assistente.log) == inicios + 1
    assert preferencias.carregar_permissoes() == {
        **DESLIGADO,
        "arquivos": "ler_gravar_excluir",
        "outros_drives": True,
    }
    _sem_erros(m)


def test_fechar_com_permissao_nao_salva_avisa(abrir: Any, pastas: dict[str, Path]) -> None:
    _configurar(pastas)
    m = abrir()
    m.pg.click("#btn-config")
    m.pg.click("#cfg-aba-permissoes")
    m.pg.click("label[for='cfg-perm-apps']")
    m.pg.click("#config-fechar")
    assert m.ate("document.getElementById('config-status').classList.contains('erro')")
    m.pg.click("#config-fechar")  # descarta
    assert m.ate("document.getElementById('config').hidden")
    assert preferencias.carregar_permissoes() == DESLIGADO
    _sem_erros(m)


def _ate_o_passo_de_permissoes(m: Any) -> None:
    m.pg.click("#assist-avancar")  # 1 -> 2
    m.pg.fill("#assist-chave", CHAVE_BOA)
    m.pg.click("#assist-testar")
    assert m.ate("document.getElementById('assist-chave-res').classList.contains('ok')")
    m.pg.click("#assist-avancar")  # 2 -> 3
    m.pg.click("#assist-avancar")  # 3 -> 4
    m.pg.click("#assist-avancar")  # 4 -> 5
    assert m.texto("assist-passo") == "Passo 5 de 6"
    assert m.pg.evaluate("document.querySelectorAll('.assist-pontos li').length") == 6


@pytest.mark.parametrize(("largura", "altura"), [(900, 600), (1920, 1080)])
def test_assistente_passo_permissoes_ligar_e_concluir(
    abrir: Any, pastas: dict[str, Path], largura: int, altura: int
) -> None:
    m = abrir(largura, altura)
    _ate_o_passo_de_permissoes(m)
    assert "Por segurança, tudo começa desligado." in m.texto("assistente")
    assert m.visivel("#assist-pular")
    # foco no seletor de Arquivos (que comeca em Nenhum) e tudo desligado
    assert m.pg.evaluate("document.activeElement.id") == "assist-perm-arquivos-nenhum"
    for chave in ("apps", "internet", "email", "outros_drives"):
        assert not _checado(m, f"#assist-perm-{chave}")
    m.pg.click("label[for='assist-perm-arquivos-ler_gravar']")
    m.pg.click("label[for='assist-perm-apps']")
    m.pg.click("label[for='assist-perm-email']")
    m.pg.click("#assist-avancar")  # 5 -> 6
    assert m.texto("assist-passo") == "Passo 6 de 6"
    assert not m.visivel("#assist-pular")
    # Voltar mantem a escolha
    m.pg.click("#assist-voltar")
    assert _checado(m, "#assist-perm-arquivos-ler_gravar") and _checado(m, "#assist-perm-apps")
    m.pg.click("#assist-avancar")
    m.pg.click("#assist-avancar")  # Comecar a usar
    assert m.ate("document.getElementById('assistente').hidden", 6000)
    assert m.ctrl.rodando
    assert preferencias.carregar_permissoes() == {
        **DESLIGADO,
        "arquivos": "ler_gravar",
        "apps": True,
        "email": True,
    }
    # a engrenagem mostra o que foi escolhido no assistente
    m.pg.click("#btn-config")
    m.pg.click("#cfg-aba-permissoes")
    assert m.ate("document.getElementById('cfg-perm-arquivos-ler_gravar').checked")
    assert _checado(m, "#cfg-perm-apps") and _checado(m, "#cfg-perm-email")
    _sem_erros(m)


def test_assistente_pular_mantem_tudo_desligado(abrir: Any, pastas: dict[str, Path]) -> None:
    m = abrir()
    _ate_o_passo_de_permissoes(m)
    m.pg.click("label[for='assist-perm-arquivos-ler_gravar_excluir']")
    m.pg.click("label[for='assist-perm-internet']")
    m.pg.click("#assist-pular")  # desfaz o que foi ligado
    assert m.texto("assist-passo") == "Passo 6 de 6"
    m.pg.click("#assist-voltar")
    assert _checado(m, "#assist-perm-arquivos-nenhum")
    assert not _checado(m, "#assist-perm-internet")
    m.pg.click("#assist-avancar")
    m.pg.click("#assist-avancar")  # Comecar a usar
    assert m.ate("document.getElementById('assistente').hidden", 6000)
    assert preferencias.carregar_permissoes() == DESLIGADO
    assert preferencias.carregar()["permissoes"] == DESLIGADO  # gravado explicitamente
    _sem_erros(m)


def test_assistente_enter_no_passo_permissoes_avanca(abrir: Any, pastas: dict[str, Path]) -> None:
    m = abrir()
    _ate_o_passo_de_permissoes(m)
    m.pg.keyboard.press("ArrowDown")  # Nenhum -> So ler
    assert _checado(m, "#assist-perm-arquivos-ler")
    m.pg.keyboard.press("Enter")
    assert m.texto("assist-passo") == "Passo 6 de 6"
    _sem_erros(m)
