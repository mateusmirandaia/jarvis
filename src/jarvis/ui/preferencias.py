"""Preferencias do Jarvis guardadas fora da pasta do projeto (nada secreto fica aqui).

Chaves: ``visual``, ``voz``, ``nome``, ``fone`` (bool), ``configurado`` (bool) e
``elevenlabs_voz_nome``. As chaves de API ficam no ``.env`` da mesma pasta (veja
``jarvis.armazenamento``).

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
import unicodedata
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Lista oficial dos visuais (um arquivo ui/visuais/<id>.js para cada um). A ordem e a da tela
# de escolha. "galaxia" (Galaxia Neural) e o visual de entrada: a janela abre nele quando nada
# foi escolhido. "globo" (o orb original) e o mais simples e fica como reserva quando um visual
# falha (isso e feito no orb.html).
VISUAIS: tuple[str, ...] = (
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
VISUAL_PADRAO = "galaxia"

ARQUIVO = "preferencias.json"
CHAVE_VISUAL = "visual"
CHAVE_VOZ = "voz"
CHAVE_NOME = "nome"
CHAVE_FONE = "fone"
CHAVE_CONFIGURADO = "configurado"
CHAVE_ELEVENLABS_VOZ_NOME = "elevenlabs_voz_nome"
CHAVE_FONTE_VOZ = "fonte_voz"
FONTES_VOZ: tuple[str, ...] = ("google", "elevenlabs")
NOME_MAX = 40


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


def nome_valido(nome: object) -> bool:
    """Diz se ``nome`` serve como "Como devo te chamar?": texto curto, sem quebra de linha.

    Vazio vale (o nome e opcional). Ate ``NOME_MAX`` caracteres depois de tirar os espacos das
    pontas; nenhum caractere de controle (quebra de linha, tab, nulo, separadores Unicode).
    """
    if not isinstance(nome, str):
        return False
    limpo = nome.strip()
    if len(limpo) > NOME_MAX:
        return False
    return not any(
        unicodedata.category(caractere) in {"Cc", "Cf", "Zl", "Zp"} for caractere in limpo
    )


def atualizar(alteracoes: dict[str, Any], caminho: Path | None = None) -> bool:
    """Grava as chaves de ``alteracoes`` no arquivo, preservando as outras.

    A escrita e atomica (arquivo temporario na mesma pasta + ``os.replace``): se o
    computador desligar no meio, o arquivo antigo continua inteiro. Quem chama valida os
    valores; aqui so se garante que da para gravar em JSON.

    Args:
        alteracoes: chaves e valores a gravar (valor None apaga a chave).
        caminho: arquivo a gravar; None usa ``caminho_preferencias()``.

    Returns:
        True se salvou; False se a gravacao falhar.
    """
    temporario: str | None = None
    try:
        arquivo = caminho or caminho_preferencias()
        dados = carregar(arquivo)
        for chave, valor in alteracoes.items():
            if valor is None:
                dados.pop(chave, None)
            else:
                dados[chave] = valor
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
        logger.warning("nao consegui salvar as preferencias %s", sorted(alteracoes), exc_info=True)
        return False
    finally:
        if temporario is not None:
            try:
                os.unlink(temporario)
            except OSError:
                pass
    return True


def salvar_visual(id_visual: object, caminho: Path | None = None) -> bool:
    """Salva o visual escolhido, preservando as outras chaves do arquivo.

    Args:
        id_visual: id do visual (precisa estar em ``VISUAIS``).
        caminho: arquivo a gravar; None usa ``caminho_preferencias()``.

    Returns:
        True se salvou; False se o id for invalido ou a gravacao falhar.
    """
    if not visual_valido(id_visual):
        logger.warning("visual desconhecido, nao salvei: %r", id_visual)
        return False
    if not atualizar({CHAVE_VISUAL: id_visual}, caminho):
        return False
    logger.info("visual salvo: %s", id_visual)
    return True


def visual_inicial(forcado: str = "", caminho: Path | None = None) -> str | None:
    """Decide o visual ao abrir a janela.

    Ordem: ``JARVIS_VISUAL`` do .env (``forcado``) se for valido; senao a preferencia salva;
    senao None, que significa "nada escolhido ainda" (a janela abre no ``VISUAL_PADRAO``).

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
