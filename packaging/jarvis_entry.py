"""Ponto de entrada do executavel do Jarvis (PyInstaller).

O PyInstaller precisa de um script "solto"; ele so chama a mesma CLI do comando `jarvis`.
Sem argumentos, abre a janela (modo orb).
"""

from __future__ import annotations

import multiprocessing
import sys

from jarvis.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
