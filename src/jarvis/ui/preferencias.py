"""Preferencias do Jarvis guardadas fora da pasta do projeto (hoje: o visual escolhido).

O arquivo fica em ``%APPDATA%\\Jarvis\\preferencias.json`` no Windows e em
``~/.config/jarvis/preferencias.json`` nos outros sistemas. Ele e pequeno, em JSON, e pode
ganhar outras chaves no futuro: salvar uma preferencia nunca apaga as outras.

Nenhuma funcao daqui levanta excecao: erro de disco vira log + valor seguro
(``{}`` ao carregar, ``False`` ao salvar). A interface nunca pode derrubar o assistente.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Lista oficial dos visuais (um arquivo ui/visuais/<id>.js para cada um). A ordem e a da tela
# de escolha; "globo" e o orb original e o padrao quando nada foi escolhido.
VISUAIS: tuple[str, ...] = ("globo", "cortex", "reator", "holograma", "mapa", "esfera", "aura")
VISUAL_PADRAO = "globo"

ARQUIVO = "preferencias.json"
CHAVE_VISUAL = "visual"


def caminho_preferencias() -> Path:
    """Devolve o caminho do arquivo de preferencias conforme o sistema operacional."""
    if sys.platform == "win32":
        appdata = os.getenv("APPDATA", "").strip()
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Jarvis" / ARQUIVO
    return Path.home() / ".config" / "jarvis" / ARQUIVO


def visual_valido(id_visual: object) -> bool:
    """Diz se ``id_visual`` e um dos ids de ``VISUAIS``."""
    return isinstance(id_visual, str) and id_visual in VISUAIS


def carregar(caminho: Path | None = None) -> dict[str, Any]:
    """Le as preferencias salvas.

    Args:
        caminho: arquivo a ler; None usa ``caminho_preferencias()``.

    Returns:
        O conteudo do arquivo; ``{}`` se ele nao existir, estiver corrompido ou nao puder ser lido.
    """
    try:
        arquivo = caminho or caminho_preferencias()
        if not arquivo.exists():
            return {}
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError, RuntimeError):
        logger.warning("nao consegui ler as preferencias; usando o padrao", exc_info=True)
        return {}
    if not isinstance(dados, dict):
        logger.warning("arquivo de preferencias com formato inesperado; usando o padrao")
        return {}
    return dados


def salvar_visual(id_visual: object, caminho: Path | None = None) -> bool:
    """Salva o visual escolhido, preservando as outras chaves do arquivo.

    A escrita e atomica (arquivo temporario na mesma pasta + ``os.replace``): se o
    computador desligar no meio, o arquivo antigo continua inteiro.

    Args:
        id_visual: id do visual (precisa estar em ``VISUAIS``).
        caminho: arquivo a gravar; None usa ``caminho_preferencias()``.

    Returns:
        True se salvou; False se o id for invalido ou a gravacao falhar.
    """
    if not visual_valido(id_visual):
        logger.warning("visual desconhecido, nao salvei: %r", id_visual)
        return False
    temporario: str | None = None
    try:
        arquivo = caminho or caminho_preferencias()
        dados = carregar(arquivo)
        dados[CHAVE_VISUAL] = id_visual
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        descritor, temporario = tempfile.mkstemp(
            prefix=".preferencias-", suffix=".tmp", dir=arquivo.parent
        )
        with os.fdopen(descritor, "w", encoding="utf-8") as saida:
            json.dump(dados, saida, ensure_ascii=False, indent=2)
            saida.flush()
            os.fsync(saida.fileno())
        os.replace(temporario, arquivo)
        temporario = None
    except (OSError, ValueError, TypeError, RuntimeError):
        logger.warning("nao consegui salvar o visual %s", id_visual, exc_info=True)
        return False
    finally:
        if temporario is not None:
            try:
                os.unlink(temporario)
            except OSError:
                pass
    logger.info("visual salvo: %s", id_visual)
    return True


def visual_inicial(forcado: str = "", caminho: Path | None = None) -> str | None:
    """Decide o visual ao abrir a janela.

    Ordem: ``JARVIS_VISUAL`` do .env (``forcado``) se for valido; senao a preferencia salva;
    senao None, que significa "primeira vez" (a janela abre a tela de escolha).

    Args:
        forcado: valor de ``Settings.visual`` (vazio = nao forcado).
        caminho: arquivo de preferencias; None usa ``caminho_preferencias()``.

    Returns:
        O id do visual ou None.
    """
    if forcado:
        if visual_valido(forcado):
            return forcado
        logger.warning("JARVIS_VISUAL=%r nao existe; opcoes: %s", forcado, ", ".join(VISUAIS))
    salvo = carregar(caminho).get(CHAVE_VISUAL)
    return salvo if visual_valido(salvo) else None
