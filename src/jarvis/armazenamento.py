"""Segredos do Jarvis (chaves de API) no ``.env`` da pasta do usuario.

O arquivo fica em ``%APPDATA%\\Jarvis\\.env`` no Windows (``~/.config/jarvis/.env`` nos outros
sistemas), ao lado do ``preferencias.json``. A janela de configuracao grava SEMPRE aqui; o
``.env`` da pasta do projeto (modo desenvolvedor) nunca e alterado.

Regras:
- escrita atomica (arquivo temporario na mesma pasta + ``os.replace``);
- linhas que nao sao das chaves alteradas (outras variaveis, comentarios, linhas em branco)
  ficam exatamente como estavam;
- valores so com caracteres seguros (sem quebra de linha, aspas, espaco, ``#`` ou ``$``), para
  ninguem conseguir injetar outra variavel pelo valor;
- nenhum valor e escrito em log ou devolvido em mensagem.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path

logger = logging.getLogger(__name__)

ARQUIVO = ".env"

GEMINI_API_KEY = "GEMINI_API_KEY"
ELEVENLABS_API_KEY = "ELEVENLABS_API_KEY"
ELEVENLABS_VOICE_ID = "ELEVENLABS_VOICE_ID"
ELEVENLABS_MODEL = "ELEVENLABS_MODEL"
CHAVES_PERMITIDAS: frozenset[str] = frozenset(
    {GEMINI_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL}
)

_VALOR_SEGURO = re.compile(r"[A-Za-z0-9_.:\-]{1,256}")
_LINHA_VARIAVEL = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")

_CABECALHO = (
    "# Chaves do Jarvis salvas pela janela de configuracao.\n"
    "# Nao compartilhe este arquivo nem mostre na tela.\n"
)


def pasta_usuario() -> Path:
    """Pasta de dados do usuario (a mesma do ``preferencias.json``)."""
    from jarvis.ui import preferencias

    return preferencias.caminho_preferencias().parent


def caminho_env_usuario() -> Path:
    """Caminho do ``.env`` de segredos do usuario."""
    return pasta_usuario() / ARQUIVO


def valor_seguro(valor: object) -> bool:
    """True se ``valor`` pode ir para o .env sem aspas e sem risco de injetar linhas."""
    return isinstance(valor, str) and _VALOR_SEGURO.fullmatch(valor) is not None


def final_da_chave(chave: str) -> str:
    """Mostra so os 4 ultimos caracteres (``"…abcd"``); chave curta demais vira ``"…"``.

    Args:
        chave: a chave completa (nunca e devolvida).

    Returns:
        ``""`` sem chave; ``"…"`` + 4 ultimos caracteres para chaves de 12+ caracteres.
    """
    if not chave:
        return ""
    if len(chave) < 12:
        return "…"
    return "…" + chave[-4:]


def salvar_segredos(alteracoes: Mapping[str, str | None], caminho: Path | None = None) -> bool:
    """Grava (ou apaga, com valor None) chaves no .env do usuario, preservando o resto.

    Args:
        alteracoes: nome da variavel -> valor novo (None apaga a linha). So aceita nomes de
            ``CHAVES_PERMITIDAS`` e valores seguros (``valor_seguro``).
        caminho: arquivo a gravar; None usa ``caminho_env_usuario()``.

    Returns:
        True se gravou; False se algum nome/valor for invalido ou o disco falhar.
    """
    if not alteracoes:
        return True
    for nome, valor in alteracoes.items():
        if nome not in CHAVES_PERMITIDAS:
            logger.warning("variavel nao permitida no .env do usuario: %r", nome)
            return False
        if valor is not None and not valor_seguro(valor):
            logger.warning("valor recusado para %s (formato invalido)", nome)
            return False

    temporario: str | None = None
    try:
        arquivo = caminho or caminho_env_usuario()
        linhas = _ler_linhas(arquivo)
        novas = _aplicar(linhas, alteracoes)
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        descritor, temporario = tempfile.mkstemp(prefix=".env-", suffix=".tmp", dir=arquivo.parent)
        with os.fdopen(descritor, "w", encoding="utf-8", newline="\n") as saida:
            saida.write("".join(novas))
            saida.flush()
            os.fsync(saida.fileno())
        os.replace(temporario, arquivo)
        temporario = None
    except (OSError, UnicodeError, RuntimeError):
        logger.warning("nao consegui salvar as chaves em %s", sorted(alteracoes), exc_info=True)
        return False
    finally:
        if temporario is not None:
            try:
                os.unlink(temporario)
            except OSError:
                pass
    logger.info("chaves atualizadas no .env do usuario: %s", ", ".join(sorted(alteracoes)))
    return True


def ler_texto_env(arquivo: Path) -> str:
    """Le um .env editado a mao no Windows sem perder a chave por causa da codificacao.

    O Bloco de Notas e o PowerShell gravam UTF-8 com BOM, "Unicode" (UTF-16) ou ANSI
    (cp1252). Com BOM, a primeira variavel viraria ``\\ufeffGEMINI_API_KEY`` e a chave
    sumiria; em ANSI, um comentario com acento quebraria a leitura inteira.
    """
    dados = arquivo.read_bytes()
    if dados.startswith((b"\xff\xfe", b"\xfe\xff")):
        return dados.decode("utf-16")
    try:
        return dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        return dados.decode("cp1252", errors="replace")


def _ler_linhas(arquivo: Path) -> list[str]:
    if not arquivo.exists():
        return []
    texto = ler_texto_env(arquivo)
    linhas = texto.splitlines(keepends=True)
    if linhas and not linhas[-1].endswith(("\n", "\r")):
        linhas[-1] += "\n"
    return linhas


def _aplicar(linhas: list[str], alteracoes: Mapping[str, str | None]) -> list[str]:
    """Troca a primeira linha de cada variavel alterada, tira as repetidas e acrescenta as novas."""
    feitas: set[str] = set()
    resultado: list[str] = []
    for linha in linhas:
        achado = _LINHA_VARIAVEL.match(linha)
        nome = achado.group(1) if achado else None
        if nome is None or nome not in alteracoes:
            resultado.append(linha)
            continue
        if nome in feitas:
            continue  # linha repetida da mesma variavel: a primeira ja foi trocada
        feitas.add(nome)
        valor = alteracoes[nome]
        if valor is not None:
            resultado.append(f"{nome}={valor}\n")
    pendentes = [
        f"{nome}={valor}\n"
        for nome, valor in alteracoes.items()
        if nome not in feitas and valor is not None
    ]
    if pendentes:
        if not resultado:
            resultado.append(_CABECALHO)
        resultado.extend(pendentes)
    return resultado
