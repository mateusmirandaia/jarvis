"""Configuracao de log em arquivo (o terminal fica livre para a conversa com o Jarvis).

Em desenvolvimento o log fica em ``logs/jarvis.log`` do projeto; no programa instalado
(``sys.frozen``), em ``%APPDATA%\\Jarvis\\logs\\jarvis.log``. Todo texto gravado passa por
``redigir``: se alguma biblioteca colocar uma chave de API numa mensagem ou num traceback
(ex.: a URL do Gemini Live leva ``?key=``), ela vira ``…`` antes de ir para o disco.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_MAX_BYTES = 1_000_000  # 1 MB por arquivo
_BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_PADROES_SEGREDO: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"AIza[0-9A-Za-z_\-]{10,}"), "AIza…"),  # chave do Google
    (re.compile(r"\bsk_[0-9A-Za-z]{10,}"), "sk_…"),  # chave do ElevenLabs
    (re.compile(r"([?&](?:key|api_key|access_token)=)[^&\s'\"]+", re.IGNORECASE), r"\1…"),
    (re.compile(r"((?:xi-api-key|x-goog-api-key)['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+", re.I), r"\1…"),
)


def redigir(texto: str) -> str:
    """Troca por ``…`` qualquer coisa com cara de chave de API dentro de ``texto``."""
    for padrao, troca in _PADROES_SEGREDO:
        texto = padrao.sub(troca, texto)
    return texto


class _FormatoSeguro(logging.Formatter):
    """Formata normalmente (inclusive traceback) e depois apaga as chaves do texto."""

    def format(self, record: logging.LogRecord) -> str:
        return redigir(super().format(record))


def caminho_log_padrao() -> Path:
    """``jarvis.log`` na pasta de logs certa para o modo atual (instalado ou desenvolvimento)."""
    from jarvis.config import LOG_NOME, pasta_logs

    return pasta_logs() / LOG_NOME


def setup_logging(log_file: Path | None = None, level: int = logging.INFO) -> Path | None:
    """Liga o log rotativo em arquivo, criando a pasta se preciso.

    Nao adiciona handler de console: o terminal e a "tela" do Jarvis. Se a pasta nao puder
    ser criada (disco cheio, sem permissao), o Jarvis segue sem log em vez de nao abrir.

    Args:
        log_file: caminho do arquivo de log; None usa ``caminho_log_padrao()``.
        level: nivel minimo registrado.

    Returns:
        O caminho do log em uso, ou None se nao foi possivel abrir o arquivo.
    """
    log_file = Path(log_file) if log_file is not None else caminho_log_padrao()
    root = logging.getLogger()
    root.setLevel(level)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        resolvido = log_file.resolve()
    except OSError:
        return None
    # Evita handlers duplicados se for chamado mais de uma vez (testes, reconexao).
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == resolvido:
            root.removeHandler(handler)
            handler.close()

    try:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
    except OSError:
        return None
    file_handler.setFormatter(_FormatoSeguro(_FORMAT))
    root.addHandler(file_handler)
    return log_file
