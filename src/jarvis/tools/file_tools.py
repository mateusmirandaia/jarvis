"""Ferramentas de arquivos e pastas do Jarvis.

Regras de seguranca:

1. Nada e sobrescrito: mover, copiar ou criar arquivo com um nome que ja existe e recusado.
2. Pastas do sistema e a pasta do proprio Jarvis (onde fica a chave) sao protegidas.
3. Programas e scripts nunca sao abertos por caminho.
4. Apagar exige confirmacao MANUAL (janela do Windows) e vai para a LIXEIRA. A janela
   fecha sozinha (contando como "Nao") antes de o Jarvis desistir de esperar.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from send2trash import send2trash

from jarvis.os_integration import windows
from jarvis.tools.security import EXECUTABLE_EXTENSIONS, PathGuard, normalize

logger = logging.getLogger(__name__)

CONFIRM_TITLE = "Jarvis - confirmacao manual"
TEXT_EXTENSIONS = (".txt", ".md")
SEARCH_MAX_DEPTH = 3
SEARCH_MAX_RESULTS = 8
LIST_MAX_ITEMS = 40
SKIPPED_PREFIXES = (".", "$")


class FileTools:
    """Acoes de arquivo expostas a IA (lista fechada em ``TOOL_NAMES``)."""

    TOOL_NAMES: ClassVar[tuple[str, ...]] = (
        "create_folder",
        "list_folder",
        "find_file",
        "open_file",
        "move_or_rename",
        "copy_item",
        "create_text_file",
        "delete_to_trash",
    )

    def __init__(
        self,
        guard: PathGuard,
        confirm: Callable[[str, str], bool] | None = None,
        confirm_timeout_s: float | None = None,
    ) -> None:
        """Cria as ferramentas de arquivo.

        Args:
            guard: guarda de caminhos (atalhos de pasta e pastas protegidas).
            confirm: funcao de confirmacao manual (titulo, mensagem) -> bool, injetavel em
                testes. None usa a janela Sim/Nao do Windows.
            confirm_timeout_s: segundos ate a janela do Windows fechar sozinha (conta como
                "Nao"). Deve ser MENOR que o tempo maximo da ferramenta. None = sem prazo.
        """
        self._guard = guard
        self._confirm = confirm
        self._confirm_timeout_s = confirm_timeout_s

    def _ask_confirmation(self, message: str) -> bool:
        """Pergunta ao senhor (janela do Windows ou a funcao injetada)."""
        if self._confirm is not None:
            return self._confirm(CONFIRM_TITLE, message)
        return windows.confirm_dialog(CONFIRM_TITLE, message, timeout_s=self._confirm_timeout_s)

    # ------------------------------------------------------------------ ferramentas
    def create_folder(self, caminho: str) -> str:
        """Cria uma pasta (e as pastas intermediarias).

        Ex.: "C:\\Projetos\\Novo" ou "area de trabalho\\Fotos".

        Args:
            caminho: caminho completo ou comecando por "area de trabalho", "documentos",
                "downloads".
        """
        target = self._guard.resolve(caminho)
        if self._guard.is_protected(target):
            return "Essa pasta e protegida (sistema ou pasta do Jarvis)."
        if target.exists():
            return f"Ja existe: {target}"
        target.mkdir(parents=True)
        logger.info("pasta criada: %s", target)
        return f"Pasta criada: {target}"

    def list_folder(self, caminho: str) -> str:
        """Lista o conteudo de uma pasta (ate 40 itens).

        Args:
            caminho: caminho completo ou "area de trabalho", "documentos", "downloads".
        """
        target = self._guard.resolve(caminho)
        if not target.is_dir():
            return f"Pasta nao encontrada: {target}"
        items = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        listing = " | ".join(
            ("[pasta] " if p.is_dir() else "") + p.name for p in items[:LIST_MAX_ITEMS]
        )
        return f"{target}: {listing}"

    def find_file(self, nome: str, onde: str = "area de trabalho") -> str:
        """Procura arquivos ou pastas pelo nome (busca parcial, ignora acentos), ate 3 niveis.

        Args:
            nome: parte do nome, ex.: "relatorio vendas".
            onde: "area de trabalho", "documentos", "downloads" ou um caminho completo.
        """
        root = self._guard.resolve(onde)
        if not root.is_dir():
            return f"Pasta nao encontrada: {root}"
        wanted = normalize(nome).replace(" ", "")
        found: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            current = Path(dirpath)
            dirnames[:] = [
                d
                for d in dirnames
                if not d.startswith(SKIPPED_PREFIXES) and not self._guard.is_protected(current / d)
            ]
            if len(current.relative_to(root).parts) >= SEARCH_MAX_DEPTH:
                dirnames[:] = []
            for item in dirnames + filenames:
                if wanted in normalize(item).replace(" ", ""):
                    found.append(str(current / item))
            if len(found) >= SEARCH_MAX_RESULTS:
                break
        if not found:
            return f"Nada com '{nome}' em {root}."
        return "Encontrei: " + " | ".join(found[:SEARCH_MAX_RESULTS])

    def open_file(self, caminho: str) -> str:
        """Abre um arquivo ou pasta com o programa padrao (documentos, fotos, videos, pastas).

        Args:
            caminho: caminho completo (use find_file antes).
        """
        target = self._guard.resolve(caminho)
        if not target.exists():
            return f"Nao existe: {target}"
        if target.suffix.lower() in EXECUTABLE_EXTENSIONS:
            return "Por seguranca, nao executo programas ou scripts por caminho."
        if not windows.IS_WINDOWS:
            return "Esta acao so funciona no Windows."
        windows.open_with_shell(target)
        logger.info("aberto: %s", target)
        return f"Aberto: {target}"

    def move_or_rename(self, origem: str, destino: str) -> str:
        """Move ou renomeia um arquivo/pasta. Nunca sobrescreve o que ja existe.

        Args:
            origem: caminho completo atual.
            destino: novo caminho completo (ou pasta de destino existente).
        """
        source, dest = self._guard.resolve(origem), self._guard.resolve(destino)
        if not source.exists():
            return f"Nao existe: {source}"
        if dest.is_dir():
            dest = dest / source.name
        if self._guard.is_protected(source) or self._guard.is_protected(dest):
            return "Origem ou destino protegido (sistema ou pasta do Jarvis)."
        if dest.exists():
            return f"Ja existe algo em {dest}. Nao sobrescrevo."
        shutil.move(str(source), str(dest))
        logger.info("movido: %s -> %s", source, dest)
        return f"Movido para: {dest}"

    def copy_item(self, origem: str, destino: str) -> str:
        """Copia um arquivo ou pasta. Nunca sobrescreve.

        Args:
            origem: caminho completo.
            destino: novo caminho completo (ou pasta de destino existente).
        """
        source, dest = self._guard.resolve(origem), self._guard.resolve(destino)
        if not source.exists():
            return f"Nao existe: {source}"
        if dest.is_dir():
            dest = dest / source.name
        if self._guard.is_protected(dest):
            return "Destino protegido (sistema ou pasta do Jarvis)."
        if dest.exists():
            return f"Ja existe algo em {dest}. Nao sobrescrevo."
        if source.is_dir():
            shutil.copytree(str(source), str(dest))
        else:
            shutil.copy2(str(source), str(dest))
        logger.info("copiado: %s -> %s", source, dest)
        return f"Copiado para: {dest}"

    def create_text_file(self, caminho: str, conteudo: str) -> str:
        """Cria um arquivo de texto novo (.txt ou .md) com o conteudo dado. Nunca sobrescreve.

        Args:
            caminho: ex.: "area de trabalho\\lista de compras.txt".
            conteudo: o texto do arquivo.
        """
        target = self._guard.resolve(caminho)
        if target.suffix.lower() not in TEXT_EXTENSIONS:
            target = target.with_suffix(".txt")
        if self._guard.is_protected(target):
            return "Local protegido (sistema ou pasta do Jarvis)."
        if target.exists():
            return f"Ja existe: {target}. Nao sobrescrevo."
        target.parent.mkdir(parents=True, exist_ok=True)
        # "x" = so cria: falha se o arquivo surgir entre a checagem e a escrita.
        with target.open("x", encoding="utf-8") as handle:
            handle.write(conteudo)
        logger.info("arquivo criado: %s", target)
        return f"Arquivo criado: {target}"

    def delete_to_trash(self, caminho: str) -> str:
        """Manda um arquivo ou pasta para a LIXEIRA. Abre uma janela no Windows e SO o clique
        do senhor em "Sim" autoriza. Avise o senhor para confirmar na tela.

        Args:
            caminho: caminho completo (use find_file antes).
        """
        target = self._guard.resolve(caminho)
        if not target.exists():
            return "Esse arquivo nao existe. Use find_file primeiro."
        if self._guard.is_protected(target):
            return "Protegido: nao apago nada do sistema nem da pasta do Jarvis."
        # A janela real so existe no Windows; com confirm injetado (testes), segue.
        if self._confirm is None and not windows.IS_WINDOWS:
            return "Esta acao so funciona no Windows."
        kind = "a PASTA" if target.is_dir() else "o arquivo"
        if not self._ask_confirmation(f"Mandar {kind} para a Lixeira?\n\n{target}"):
            logger.info("apagar recusado na janela: %s", target)
            return "O senhor NAO autorizou na janela (ou o tempo acabou). Nada foi apagado."
        send2trash(str(target))
        logger.info("enviado para a lixeira: %s", target)
        return f"'{target.name}' foi para a Lixeira (autorizado manualmente)."
