"""Linha de comando do Jarvis.

`jarvis` abre o orb (janela com voz), `jarvis --modo voz` roda so no terminal,
`jarvis --modo texto` e o chat por texto e `jarvis --criar-atalho` cria o icone na
Area de Trabalho. Tambem funciona com `python -m jarvis`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING

from jarvis import __version__
from jarvis.config import Settings
from jarvis.errors import ConfigError
from jarvis.logging_setup import setup_logging

if TYPE_CHECKING:
    from jarvis.tools import ToolRegistry

logger = logging.getLogger(__name__)


def _tell_user(message: str) -> None:
    """Mostra uma mensagem no terminal; sem terminal (atalho), mostra numa janela do Windows."""
    if sys.stdout is None:  # pythonw.exe: nao existe console
        from jarvis.os_integration.windows import show_message

        show_message("Jarvis", message)
    else:
        print(f"Jarvis: {message}")


def _build_parser() -> argparse.ArgumentParser:
    """Cria o parser de argumentos da CLI."""
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description="Jarvis: assistente pessoal de voz com Gemini.",
    )
    parser.add_argument(
        "--modo",
        choices=("orb", "voz", "texto"),
        default="orb",
        help="orb (janela animada + voz, padrao), voz (so terminal) ou texto (chat).",
    )
    parser.add_argument(
        "--criar-atalho",
        action="store_true",
        help="cria o atalho 'Jarvis' na Area de Trabalho e sai.",
    )
    parser.add_argument(
        "--versao",
        action="version",
        version=f"%(prog)s {__version__}",
        help="mostra a versao e sai.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Ponto de entrada da CLI.

    Args:
        argv: argumentos (sem o nome do programa); None usa sys.argv.

    Returns:
        Codigo de saida: 0 em sucesso, 1 em erro de configuracao ou falha inesperada.
    """
    args = _build_parser().parse_args(argv)
    # Console do Windows nao quebra com acento/emoji em titulo de janela.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(errors="replace")

    if args.criar_atalho:
        return _create_shortcut()

    try:
        settings = Settings.from_env()
        setup_logging(settings.log_file)
        logger.info("Jarvis %s iniciando no modo %s", __version__, args.modo)

        # Imports tardios: so carregam SDK/pyaudio depois que a configuracao foi validada.
        from jarvis.tools import ToolRegistry

        registry = ToolRegistry(settings)
        if args.modo == "texto":
            from jarvis.assistants.text_assistant import TextAssistant

            TextAssistant(settings, registry).run()
        elif args.modo == "orb":
            _run_orb(settings, registry)
        else:
            from jarvis.assistants.live_assistant import LiveAssistant

            asyncio.run(LiveAssistant(settings, registry).run())
    except ConfigError as exc:
        _tell_user(str(exc))
        return 1
    except KeyboardInterrupt:
        print("\nAte logo, senhor.")
        return 0
    except Exception:  # noqa: BLE001 - ultima rede de seguranca: sem traceback na tela
        logger.exception("falha inesperada ao rodar o Jarvis")
        _tell_user(
            "Senhor, algo inesperado deu errado e precisei parar. "
            "Os detalhes ficaram em logs/jarvis.log."
        )
        return 1
    return 0


def _run_orb(settings: Settings, registry: ToolRegistry) -> None:
    """Abre a janela do orb e roda o assistente de voz numa thread em segundo plano."""
    from jarvis.assistants.live_assistant import LiveAssistant
    from jarvis.os_integration.windows import acquire_single_instance
    from jarvis.ui.orb_window import OrbWindow

    if not acquire_single_instance("Local\\JarvisSemHype.Orb"):
        _tell_user("O Jarvis ja esta aberto, senhor.")
        return
    window = OrbWindow(settings)  # visual inicial: JARVIS_VISUAL ou a preferencia salva
    assistant = LiveAssistant(settings, registry, observer=window)

    def worker() -> None:
        try:
            asyncio.run(assistant.run())
        except Exception as error:  # noqa: BLE001 - mostra no orb em vez de sumir calado
            logger.exception("o assistente parou")
            window.on_state("offline")
            if isinstance(error, ConfigError):
                message = str(error)
            else:
                message = "Senhor, algo deu errado e precisei parar. Veja logs/jarvis.log."
            window.on_transcript("sistema", message)

    window.start(worker)  # bloqueia ate o senhor fechar a janela
    logger.info("janela do orb fechada")


def _create_shortcut() -> int:
    """Cria o atalho na Area de Trabalho (modo orb, sem terminal)."""
    from jarvis.config import PROJECT_ROOT
    from jarvis.os_integration.shortcut import create_desktop_shortcut
    from jarvis.ui.orb_window import ICON_FILE

    _tell_user(create_desktop_shortcut(PROJECT_ROOT, ICON_FILE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
