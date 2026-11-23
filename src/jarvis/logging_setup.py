"""Configuracao de log em arquivo (o terminal fica livre para a conversa com o Jarvis)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_MAX_BYTES = 1_000_000  # 1 MB por arquivo
_BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(log_file: Path, level: int = logging.INFO) -> None:
    """Liga o log rotativo em arquivo, criando a pasta se preciso.

    Nao adiciona handler de console: o terminal e a "tela" do Jarvis.

    Args:
        log_file: caminho do arquivo de log (ex.: logs/jarvis.log).
        level: nivel minimo registrado.
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    # Evita handlers duplicados se for chamado mais de uma vez (testes, reconexao).
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename) == (
            log_file.resolve()
        ):
            root.removeHandler(handler)
            handler.close()

    file_handler = RotatingFileHandler(
        log_file, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(file_handler)
