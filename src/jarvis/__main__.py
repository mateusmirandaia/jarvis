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
from pathlib import Path

from jarvis import __version__
from jarvis.config import Settings
from jarvis.errors import ConfigError
from jarvis.logging_setup import caminho_log_padrao, setup_logging

logger = logging.getLogger(__name__)


def _tell_user(message: str) -> None:
    """Mostra uma mensagem no terminal; sem terminal (atalho), mostra numa janela do Windows.

    Nunca levanta: no programa sem console (pythonw.exe ou o instalado), ``sys.stdout`` pode
    ser None, e qualquer falha so vai para o log.
    """
    try:
        if sys.stdout is None:  # pythonw.exe / instalado: nao existe console
            from jarvis.os_integration.windows import show_message

            show_message("Jarvis", message)
        else:
            print(f"Jarvis: {message}")
    except Exception:  # noqa: BLE001 - avisar nunca pode derrubar o Jarvis
        logger.warning("nao consegui mostrar a mensagem ao usuario", exc_info=True)


def _print_safe(message: str) -> None:
    """``print`` que nao quebra sem console."""
    try:
        if sys.stdout is not None:
            print(message)
    except Exception:  # noqa: BLE001
        pass


def _log_hint(log_file: Path | None) -> str:
    """Onde o log esta, para as mensagens de erro (o caminho real, tambem no instalado)."""
    return str(log_file) if log_file is not None else str(caminho_log_padrao())


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
        help="orb (janela animada + voz, padrão), voz (só terminal) ou texto (chat).",
    )
    parser.add_argument(
        "--criar-atalho",
        action="store_true",
        help="cria o atalho 'Jarvis' na Área de Trabalho e sai.",
    )
    parser.add_argument(
        "--versao",
        action="version",
        version=f"%(prog)s {__version__}",
        help="mostra a versão e sai.",
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

    log_file: Path | None = None
    try:
        # No modo orb a janela abre mesmo sem chave (ela mesma pede a chave).
        settings = Settings.from_env(exigir_chave=args.modo != "orb")
        log_file = setup_logging(settings.log_file)
        logger.info("Jarvis %s iniciando no modo %s", __version__, args.modo)

        if args.modo == "orb":
            _run_orb(settings)
            return 0

        # Imports tardios: so carregam SDK/pyaudio depois que a configuracao foi validada.
        from jarvis.tools import ToolRegistry

        registry = ToolRegistry(settings)
        if args.modo == "texto":
            from jarvis.assistants.text_assistant import TextAssistant

            TextAssistant(settings, registry).run()
        else:
            from jarvis.assistants.live_assistant import LiveAssistant

            asyncio.run(LiveAssistant(settings, registry).run())
    except ConfigError as exc:
        _tell_user(str(exc))
        return 1
    except KeyboardInterrupt:
        _print_safe("\nAté logo, senhor.")
        return 0
    except Exception:  # noqa: BLE001 - ultima rede de seguranca: sem traceback na tela
        logger.exception("falha inesperada ao rodar o Jarvis")
        _tell_user(
            "Senhor, algo inesperado deu errado e precisei parar. "
            f"Os detalhes ficaram em {_log_hint(log_file)}."
        )
        return 1
    return 0


def _carregar_settings_orb() -> Settings:
    """Le as configuracoes de novo (a janela pode ter acabado de salvar chave/voz)."""
    return Settings.from_env(exigir_chave=False)


def _run_orb(settings: Settings) -> None:
    """Abre a janela do orb (sempre) e inicia o assistente de voz se ja houver chave.

    Sem chave, a janela mostra o assistente de configuracao; o assistente de voz so comeca
    quando a pessoa clica em "Começar a usar" (``concluir_configuracao``).
    """
    from jarvis.controlador import Controlador
    from jarvis.os_integration.windows import acquire_single_instance
    from jarvis.ui.api_config import ApiJs
    from jarvis.ui.orb_window import OrbWindow

    if not acquire_single_instance("Local\\JarvisSemHype.Orb"):
        _tell_user("O Jarvis já está aberto, senhor. Procure a janela dele na barra de tarefas.")
        return
    api = ApiJs(carregar_settings=_carregar_settings_orb)
    window = OrbWindow(settings, api=api)  # visual inicial: JARVIS_VISUAL ou a preferencia salva
    controlador = Controlador(window, _carregar_settings_orb)
    api._ligar(controlador=controlador)

    def worker() -> None:
        if settings.has_api_key:
            controlador.iniciar()
        else:
            logger.info("sem chave do Google: a janela vai pedir a configuracao")

    try:
        window.start(worker)  # bloqueia ate o senhor fechar a janela
    finally:
        controlador.parar(espera_s=3.0)
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
