"""Vozes prontas do Google (Gemini Live) que a janela de configuracao oferece.

A lista e fixa: so estes ids podem ser salvos pela janela. Cada voz tem uma amostra curta
(``ui/amostras/<Voz>.wav``, gerada uma vez por ``scripts/gerar_amostras_voz.py``) que o botao
"Ouvir" toca. Sem a amostra, o botao mostra "amostra indisponivel" (nada quebra).
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import TypeGuard

from jarvis.config import pasta_pacote

logger = logging.getLogger(__name__)

# (id, descricao curta) na ordem dos cartoes.
# Genero conferido na documentacao oficial do Gemini TTS (Google Cloud, tabela de vozes).
VOZES: tuple[tuple[str, str], ...] = (
    ("Charon", "Masculina, grave e calma (padrão)"),
    ("Puck", "Masculina, animada"),
    ("Kore", "Feminina, firme"),
    ("Fenrir", "Masculina, empolgada"),
    ("Aoede", "Feminina, leve"),
    ("Leda", "Feminina, jovem"),
    ("Orus", "Masculina, firme"),
    ("Zephyr", "Feminina, clara"),
)
VOZ_PADRAO = "Charon"
IDS: tuple[str, ...] = tuple(id_voz for id_voz, _ in VOZES)
DESCRICOES: dict[str, str] = dict(VOZES)

AMOSTRA_MAX_BYTES = 3_000_000  # amostra de ~3 s em WAV e bem menor; acima disso, algo esta errado
FRASE_AMOSTRA = "Olá, senhor. Eu sou o Jarvis, seu assistente pessoal."


def voz_valida(id_voz: object) -> TypeGuard[str]:
    """Diz se ``id_voz`` e um dos ids da lista fixa (com a mesma grafia)."""
    return isinstance(id_voz, str) and id_voz in DESCRICOES


def pasta_amostras() -> Path:
    """Pasta das amostras (funciona em desenvolvimento e no programa instalado)."""
    return pasta_pacote() / "ui" / "amostras"


def caminho_amostra(id_voz: object) -> Path | None:
    """Caminho da amostra da voz, ou None se o id for invalido. Nao garante que exista."""
    if not voz_valida(id_voz):
        return None
    assert isinstance(id_voz, str)
    return pasta_amostras() / f"{id_voz}.wav"


def tem_amostra(id_voz: object) -> bool:
    """True se a voz e valida e a amostra existe."""
    caminho = caminho_amostra(id_voz)
    try:
        return caminho is not None and caminho.is_file()
    except OSError:
        return False


def amostra_data_url(id_voz: object) -> str | None:
    """Amostra como ``data:audio/wav;base64,...`` (o JS toca com ``new Audio(dados)``).

    Returns:
        O texto da URL de dados, ou None se o id for invalido, a amostra nao existir, for
        grande demais ou nao puder ser lida.
    """
    caminho = caminho_amostra(id_voz)
    if caminho is None:
        return None
    try:
        if not caminho.is_file() or caminho.stat().st_size > AMOSTRA_MAX_BYTES:
            return None
        dados = caminho.read_bytes()
    except OSError:
        logger.warning("nao consegui ler a amostra da voz %s", id_voz, exc_info=True)
        return None
    if not dados.startswith(b"RIFF"):
        logger.warning("amostra da voz %s nao e um WAV", id_voz)
        return None
    return "data:audio/wav;base64," + base64.b64encode(dados).decode("ascii")


def lista_para_janela() -> list[dict[str, object]]:
    """``[{id, descricao, tem_amostra}]`` na ordem dos cartoes."""
    return [
        {"id": id_voz, "descricao": descricao, "tem_amostra": tem_amostra(id_voz)}
        for id_voz, descricao in VOZES
    ]
