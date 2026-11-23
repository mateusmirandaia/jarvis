"""Ferramentas de navegador: abrir sites e pesquisar no Google."""

from __future__ import annotations

import logging
import webbrowser
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.google.com/search?q="


class WebTools:
    """Abre paginas no navegador padrao."""

    TOOL_NAMES: tuple[str, ...] = ("open_website", "web_search")

    def open_website(self, endereco: str) -> str:
        """Abre um site no navegador padrao.

        Args:
            endereco: endereco do site, ex.: "youtube.com".
        """
        url = endereco.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        logger.info("site aberto: %s", url)
        return f"Site aberto: {url}"

    def web_search(self, termo: str) -> str:
        """Abre o navegador padrao com uma pesquisa no Google.

        Args:
            termo: o que pesquisar.
        """
        webbrowser.open(SEARCH_URL + quote_plus(termo))
        logger.info("pesquisa aberta: %s", termo)
        return f"Pesquisa aberta no navegador: {termo}"
