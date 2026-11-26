"""Ferramentas de navegador: abrir sites e pesquisar no Google.

O texto de um arquivo lido (read_file) ou de um site pode tentar mandar a IA "abrir" um
endereco com dados do senhor no meio (vazamento). Por isso o endereco e curto, so http(s),
sem "usuario@" antes do site e sem quebra de linha; a pesquisa tambem e curta.
"""

from __future__ import annotations

import logging
import re
import webbrowser
from collections.abc import Callable
from urllib.parse import quote_plus, urlsplit

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.google.com/search?q="
URL_MAX_CHARS = 300
SEARCH_MAX_CHARS = 200
MSG_ENDERECO = (
    "Esse endereço não parece um site comum (é longo demais ou tem partes estranhas). "
    "Não abri. Diga só o nome do site, como youtube.com."
)
MSG_PESQUISA_LONGA = "Essa pesquisa é comprida demais. Diga em poucas palavras o que procurar."
_ESQUEMA = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)
_PROIBIDOS = re.compile(r"[\x00-\x20\x7f\\]")


def _abrir_no_navegador(url: str) -> None:
    webbrowser.open(url)


def endereco_seguro(endereco: str) -> str | None:
    """URL https/http pronta para abrir, ou None se for estranha (veja a docstring do modulo).

    Args:
        endereco: o que a IA pediu (ex.: "youtube.com" ou "https://g1.globo.com").
    """
    url = str(endereco).strip()
    if not url or len(url) > URL_MAX_CHARS or _PROIBIDOS.search(url):
        return None
    if not url.lower().startswith(("http://", "https://")):
        if _ESQUEMA.match(url) and not re.match(r"^[^:/]+:\d+(/|$)", url):
            return None  # outro protocolo (javascript:, file:, ms-settings:...)
        url = "https://" + url
    try:
        partes = urlsplit(url)
    except ValueError:
        return None
    if not partes.hostname or "@" in partes.netloc:
        return None
    return url


class WebTools:
    """Abre paginas no navegador padrao."""

    TOOL_NAMES: tuple[str, ...] = ("open_website", "web_search")

    def __init__(self, abrir: Callable[[str], object] | None = None) -> None:
        """Cria as ferramentas de navegador.

        Args:
            abrir: abre uma URL (injetavel em testes). None usa o navegador padrao.
        """
        self._abrir = abrir

    def _abrir_url(self, url: str) -> None:
        (self._abrir or _abrir_no_navegador)(url)

    def open_website(self, endereco: str) -> str:
        """Abre um site no navegador padrao.

        Args:
            endereco: endereco do site, ex.: "youtube.com".
        """
        url = endereco_seguro(endereco)
        if url is None:
            logger.warning("endereco recusado: %r", str(endereco)[:80])
            return MSG_ENDERECO
        self._abrir_url(url)
        logger.info("site aberto: %s", url)
        return f"Site aberto: {url}"

    def web_search(self, termo: str) -> str:
        """Abre o navegador padrao com uma pesquisa no Google.

        Args:
            termo: o que pesquisar (poucas palavras).
        """
        termo = " ".join(str(termo).split())
        if len(termo) > SEARCH_MAX_CHARS:
            return MSG_PESQUISA_LONGA
        self._abrir_url(SEARCH_URL + quote_plus(termo))
        logger.info("pesquisa aberta: %s", termo)
        return f"Pesquisa aberta no navegador: {termo}"
