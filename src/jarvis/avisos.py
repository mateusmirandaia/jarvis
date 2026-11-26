"""Avisos gravados (offline) que o Jarvis toca quando algo da errado.

Os avisos sao WAV PCM 16-bit, 24 kHz, mono, gerados UMA vez por
``scripts/gerar_avisos_voz.py`` e guardados em ``jarvis/avisos/`` (no programa instalado:
``sys._MEIPASS/jarvis/avisos``, pela mesma ``pasta_pacote()`` das amostras de voz):

- ``internet_<Voz>.wav``: problema de internet, na voz do Google escolhida;
- ``elevenlabs_Charon.wav``: a voz personalizada (ElevenLabs) falhou.

Nunca usa TTS na hora (sem internet nao ha TTS). Voz desconhecida ou arquivo faltando: usa o
Charon. Nada existe ou o arquivo esta estragado: devolve None (quem chamou so escreve o texto
na tela e registra no log). Nada aqui levanta excecao.
"""

from __future__ import annotations

import io
import logging
import threading
import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from jarvis.config import pasta_pacote

logger = logging.getLogger(__name__)

TipoAviso = Literal["internet", "elevenlabs"]

VOZ_RESERVA = "Charon"
INTERVALO_INTERNET_S = 30.0  # o aviso de internet toca no maximo 1 vez a cada 30 s

TEXTO_INTERNET = (
    "Desculpe, estou tendo problemas com a sua internet. Aguarde um momento ou tente daqui a pouco."
)
TEXTO_ELEVENLABS = "Minha voz personalizada está com problemas. Vou continuar com a voz padrão."
TEXTOS: dict[str, str] = {"internet": TEXTO_INTERNET, "elevenlabs": TEXTO_ELEVENLABS}

TAXA = 24_000  # igual a saida de audio do Jarvis (SPEAKER_RATE)
LARGURA_AMOSTRA = 2
CANAIS = 1
MAX_BYTES = 5_000_000  # um aviso de ~6 s tem ~300 KB; acima disso algo esta errado

_cache: dict[tuple[str, int, int], bytes] = {}
_cache_trava = threading.Lock()


def pasta_avisos() -> Path:
    """Pasta dos avisos (funciona em desenvolvimento e no programa instalado)."""
    return pasta_pacote() / "avisos"


def nome_arquivo(tipo: str, voz: str) -> str:
    """``internet_Charon.wav``, ``elevenlabs_Charon.wav``..."""
    return f"{tipo}_{voz}.wav"


def _vozes_validas() -> tuple[str, ...]:
    from jarvis import vozes

    return vozes.IDS


def candidatos(tipo: str, voz: object, pasta: Path | None = None) -> list[Path]:
    """Arquivos a tentar, em ordem: a voz pedida (se for uma das 8) e depois o Charon."""
    base = pasta if pasta is not None else pasta_avisos()
    nomes: list[str] = []
    if isinstance(voz, str) and voz in _vozes_validas():
        nomes.append(voz)
    if VOZ_RESERVA not in nomes:
        nomes.append(VOZ_RESERVA)
    return [base / nome_arquivo(tipo, nome) for nome in nomes]


def ler_pcm(caminho: Path) -> bytes | None:
    """PCM de um WAV de aviso; None se faltar, for grande demais ou estiver no formato errado."""
    try:
        if not caminho.is_file():
            return None
        info = caminho.stat()
        if info.st_size > MAX_BYTES:
            logger.warning("aviso %s grande demais (%d bytes)", caminho.name, info.st_size)
            return None
        chave = (str(caminho), info.st_mtime_ns, info.st_size)
        with _cache_trava:
            if chave in _cache:
                return _cache[chave]
        bruto = caminho.read_bytes()
        with wave.open(io.BytesIO(bruto), "rb") as arquivo:
            formato = (arquivo.getnchannels(), arquivo.getsampwidth(), arquivo.getframerate())
            quadros = arquivo.readframes(arquivo.getnframes())
    except (OSError, EOFError, wave.Error):
        logger.warning("nao consegui ler o aviso %s", caminho.name, exc_info=True)
        return None
    if formato != (CANAIS, LARGURA_AMOSTRA, TAXA):
        logger.warning(
            "aviso %s fora do formato (canais, bytes, taxa)=%s; esperado %s",
            caminho.name,
            formato,
            (CANAIS, LARGURA_AMOSTRA, TAXA),
        )
        return None
    if not quadros:
        logger.warning("aviso %s esta vazio", caminho.name)
        return None
    with _cache_trava:
        _cache[chave] = quadros
    return quadros


def pcm_aviso(tipo: TipoAviso, voz: object, pasta: Path | None = None) -> bytes | None:
    """Audio do aviso na voz pedida (ou no Charon). None quando nada serve: so texto."""
    try:
        for caminho in candidatos(tipo, voz, pasta):
            pcm = ler_pcm(caminho)
            if pcm is not None:
                if caminho.name != nome_arquivo(tipo, str(voz)):
                    logger.info("aviso %s: usando %s", tipo, caminho.name)
                return pcm
    except Exception:  # noqa: BLE001 - aviso nunca derruba o Jarvis
        logger.warning("falha ao procurar o aviso %s", tipo, exc_info=True)
        return None
    logger.warning("aviso %s sem audio gravado: so texto na tela", tipo)
    return None


def duracao_s(pcm: bytes) -> float:
    """Duracao, em segundos, de um PCM 16-bit 24 kHz mono."""
    return len(pcm) / (TAXA * LARGURA_AMOSTRA * CANAIS)


class LimiteDeAviso:
    """Deixa um aviso tocar no maximo uma vez a cada ``intervalo_s`` segundos."""

    def __init__(self, intervalo_s: float, relogio: Callable[[], float] = time.monotonic) -> None:
        self._intervalo = intervalo_s
        self._relogio = relogio
        self._ultimo: float | None = None

    def pode(self) -> bool:
        """True (e marca a hora) se ja passou o intervalo desde o ultimo aviso."""
        agora = self._relogio()
        if self._ultimo is not None and agora - self._ultimo < self._intervalo:
            return False
        self._ultimo = agora
        return True
