"""Ferramentas de arquivos e pastas do Jarvis.

Regras de seguranca (detalhes em docs/SEGURANCA.md, "Regras das ferramentas"):

1. Nada e sobrescrito: mover, copiar ou criar arquivo com um nome que ja existe e recusado.
2. Pastas protegidas (sistema, Jarvis, chaves, AppData) nao sao lidas, abertas nem alteradas,
   nem como ORIGEM nem como DESTINO. Arquivos com senhas/chaves (.env, .pem...) tambem nao.
3. ``open_file`` so abre documentos e midia da lista POSITIVA (``OPENABLE_EXTENSIONS``).
4. Mover/renomear/copiar nunca troca o TIPO do arquivo (a extensao fica a mesma).
5. Pastas pessoais inteiras (home, Area de Trabalho, Documentos...) nao sao movidas nem apagadas.
6. Apagar exige confirmacao MANUAL (janela do Windows) e vai para a LIXEIRA. Enquanto a
   janela esta aberta, nenhuma outra acao altera arquivos; se o item mudar ate o clique,
   nada e apagado. Pendrive e rede nao tem Lixeira: apagar ali e recusado.
"""

from __future__ import annotations

import functools
import logging
import os
import shutil
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, TypeVar

from send2trash import send2trash

from jarvis.os_integration import windows
from jarvis.tools.security import (
    EXECUTABLE_EXTENSIONS,
    OPENABLE_EXTENSIONS,
    CaminhoRecusado,
    PathGuard,
    is_secret,
    normalize,
    same_extension_family,
    suffix_of,
)

logger = logging.getLogger(__name__)

CONFIRM_TITLE = "Jarvis - confirmacao manual"
TEXT_EXTENSIONS = (".txt", ".md")
SEARCH_MAX_DEPTH = 3
SEARCH_MAX_RESULTS = 8
LIST_MAX_ITEMS = 40
SKIPPED_PREFIXES = (".", "$")
COPY_MAX_BYTES = 2 * 1024**3  # 2 GB: acima disso a copia passaria do tempo da ferramenta
COPY_MAX_FILES = 20_000
LOCK_WAIT_S = 10.0

MSG_PROTEGIDO = "Senhor, essa pasta e protegida (sistema, chaves ou pasta do Jarvis)."
MSG_SEGREDO = "Senhor, esse arquivo guarda senhas ou chaves; por seguranca nao mexo nele."
MSG_ABRIR_TIPO = "Senhor, nao posso abrir esse tipo de arquivo por seguranca."
MSG_TIPO = "Senhor, nao troco o tipo do arquivo. Mantenha a mesma extensao ({ext})."
MSG_NOME_PASTA = "Senhor, pasta nao pode ter nome de programa ou atalho."
MSG_PASTA_PESSOAL = "Senhor, nao movo nem apago pastas pessoais inteiras."
MSG_CONTEM_PROTEGIDO = "Senhor, essa pasta contem a pasta do Jarvis ou de chaves; nao mexo nela."
MSG_CONTEM_SEGREDO = "Senhor, essa pasta tem arquivos de senhas ou chaves; nao copio nem movo."
MSG_CONTEM_LINK = "Senhor, essa pasta tem atalhos para outras pastas; nao copio nem movo."
MSG_GRANDE = "Senhor, e grande demais para eu copiar com seguranca (mais de 2 GB ou de 20 mil itens). Use o Explorer."  # noqa: E501
MSG_OCUPADO = "Senhor, estou esperando a sua confirmacao na janela. Responda la e peca de novo."
MSG_MUDOU = "Senhor, o item mudou enquanto eu esperava a confirmacao. Nada foi apagado."
MSG_SEM_LIXEIRA = (
    "Senhor, esse item esta num pendrive ou na rede, onde nao ha Lixeira; ele seria apagado "
    "de vez. Nao apago; se quiser, apague pelo Explorer."
)
ONLY_WINDOWS = "Esta acao so funciona no Windows."

_F = TypeVar("_F", bound=Callable[..., str])


def _recusas(func: _F) -> _F:
    """Transforma ``CaminhoRecusado`` na frase curta dele (o resto vai para o safe_tool)."""

    @functools.wraps(func)
    def embrulho(*args: Any, **kwargs: Any) -> str:
        try:
            return func(*args, **kwargs)
        except CaminhoRecusado as recusa:
            return str(recusa)

    return embrulho  # type: ignore[return-value]


def _assinatura(path: Path) -> tuple[int, int, int, int, bool]:
    """Identidade do item (id do arquivo, volume, tamanho, data, e pasta?) sem seguir links."""
    st = path.stat(follow_symlinks=False)
    return (st.st_ino, st.st_dev, st.st_size, st.st_mtime_ns, path.is_dir())


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


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
        # Uma alteracao de arquivo por vez; enquanto a janela de apagar esta aberta,
        # as outras alteracoes sao recusadas na hora (nada de trocar o item por baixo).
        self._lock = threading.Lock()
        self._confirmando = threading.Event()

    def _ask_confirmation(self, message: str) -> bool:
        """Pergunta ao senhor (janela do Windows ou a funcao injetada)."""
        if self._confirm is not None:
            return self._confirm(CONFIRM_TITLE, message)
        return windows.confirm_dialog(CONFIRM_TITLE, message, timeout_s=self._confirm_timeout_s)

    def _alterando(self, acao: Callable[[], str]) -> str:
        """Roda uma alteracao de arquivo com a trava (recusa se ha confirmacao aberta)."""
        if self._confirmando.is_set():
            return MSG_OCUPADO
        if not self._lock.acquire(timeout=LOCK_WAIT_S):
            return MSG_OCUPADO
        try:
            if self._confirmando.is_set():
                return MSG_OCUPADO
            return acao()
        finally:
            self._lock.release()

    # ------------------------------------------------------------------ checagens
    def _origem_bloqueada(self, source: Path) -> str | None:
        """Mensagem de recusa para ler/abrir/copiar ``source``, ou None se pode."""
        if self._guard.is_protected(source):
            return MSG_PROTEGIDO
        if is_secret(source) or is_secret(_resolver(source)):
            return MSG_SEGREDO
        return None

    def _conteudo_bloqueado(self, source: Path, limitar_tamanho: bool) -> str | None:
        """Varre a pasta ``source`` (sem seguir links): segredos, links e tamanho."""
        if self._guard.contains_protected(source):
            return MSG_CONTEM_PROTEGIDO
        if not source.is_dir():
            if limitar_tamanho and source.stat().st_size > COPY_MAX_BYTES:
                return MSG_GRANDE
            return None
        total, itens = 0, 0
        for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
            atual = Path(dirpath)
            for nome in dirnames + filenames:
                item = atual / nome
                itens += 1
                if _is_link(item):
                    return MSG_CONTEM_LINK
                if is_secret(item):
                    return MSG_CONTEM_SEGREDO
            if limitar_tamanho:
                for nome in filenames:
                    try:
                        total += (atual / nome).stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
                if total > COPY_MAX_BYTES or itens > COPY_MAX_FILES:
                    return MSG_GRANDE
        return None

    def _destino_bloqueado(self, source: Path, dest: Path) -> str | None:
        """Mensagem de recusa para levar ``source`` a ``dest``, ou None se pode."""
        if self._guard.is_protected(dest):
            return MSG_PROTEGIDO
        if is_secret(dest):
            return MSG_SEGREDO
        if source.is_dir():
            # Pasta pode ganhar qualquer nome comum, mas nunca um nome de programa ("x.exe").
            if suffix_of(dest) in EXECUTABLE_EXTENSIONS:
                return MSG_NOME_PASTA
            return None
        old, new = suffix_of(source), suffix_of(dest)
        if not same_extension_family(old, new):
            return MSG_TIPO.format(ext=old or "sem extensao")
        return None

    # ------------------------------------------------------------------ ferramentas
    @_recusas
    def create_folder(self, caminho: str) -> str:
        """Cria uma pasta (e as pastas intermediarias).

        Ex.: "C:\\Projetos\\Novo" ou "area de trabalho\\Fotos".

        Args:
            caminho: caminho completo ou comecando por "area de trabalho", "documentos",
                "downloads", "imagens", "musicas", "videos".
        """
        target = self._guard.resolve(caminho)
        if self._guard.is_protected(target):
            return MSG_PROTEGIDO

        def criar() -> str:
            if target.exists():
                return f"Ja existe: {target}"
            target.mkdir(parents=True)
            logger.info("pasta criada: %s", target)
            return f"Pasta criada: {target}"

        return self._alterando(criar)

    @_recusas
    def list_folder(self, caminho: str) -> str:
        """Lista o conteudo de uma pasta (ate 40 itens).

        Args:
            caminho: caminho completo ou "area de trabalho", "documentos", "downloads".
        """
        target = self._guard.resolve(caminho)
        if self._guard.is_protected(target):
            return MSG_PROTEGIDO
        if not target.is_dir():
            return f"Pasta nao encontrada: {target}"
        items = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        items = [p for p in items if not self._guard.is_protected(p)]
        listing = " | ".join(
            ("[pasta] " if p.is_dir() else "") + p.name for p in items[:LIST_MAX_ITEMS]
        )
        return f"{target}: {listing}"

    @_recusas
    def find_file(self, nome: str, onde: str = "area de trabalho") -> str:
        """Procura arquivos ou pastas pelo nome (busca parcial, ignora acentos), ate 3 niveis.

        Args:
            nome: parte do nome, ex.: "relatorio vendas".
            onde: "area de trabalho", "documentos", "downloads" ou um caminho completo.
        """
        root = self._guard.resolve(onde)
        if self._guard.is_protected(root):
            return MSG_PROTEGIDO
        if not root.is_dir():
            return f"Pasta nao encontrada: {root}"
        wanted = normalize(nome).replace(" ", "")
        if not wanted:
            return "Senhor, diga parte do nome que devo procurar."
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

    @_recusas
    def open_file(self, caminho: str) -> str:
        """Abre um documento, foto, musica, video ou pasta com o programa padrao.
        Programas, scripts e atalhos nao sao abertos (para apps, use open_app).

        Args:
            caminho: caminho completo (use find_file antes).
        """
        target = self._guard.resolve(caminho)
        bloqueio = self._origem_bloqueada(target)
        if bloqueio:
            return bloqueio
        if not target.exists():
            return f"Nao existe: {target}"
        if not target.is_dir():
            real = _resolver(target)
            if (
                suffix_of(target) not in OPENABLE_EXTENSIONS
                or suffix_of(real) not in OPENABLE_EXTENSIONS
            ):
                logger.warning("open_file recusou o tipo: %s", target)
                return MSG_ABRIR_TIPO
        if not windows.IS_WINDOWS:
            return ONLY_WINDOWS
        windows.open_with_shell(target)
        logger.info("aberto: %s", target)
        return f"Aberto: {target}"

    @_recusas
    def move_or_rename(self, origem: str, destino: str) -> str:
        """Move ou renomeia um arquivo/pasta. Nunca sobrescreve e nunca troca a extensao.

        Args:
            origem: caminho completo atual.
            destino: novo caminho completo (ou pasta de destino existente).
        """
        source, dest = self._guard.resolve(origem), self._guard.resolve(destino)

        def mover() -> str:
            nonlocal dest
            bloqueio = self._origem_bloqueada(source)
            if bloqueio:
                return bloqueio
            if not source.exists() and not source.is_symlink():
                return f"Nao existe: {source}"
            if self._guard.is_user_root(source):
                return MSG_PASTA_PESSOAL
            if dest.is_dir():
                dest = dest / source.name
            bloqueio = self._destino_bloqueado(source, dest)
            if bloqueio:
                return bloqueio
            if dest.exists() or dest.is_symlink():
                return f"Ja existe algo em {dest}. Nao sobrescrevo."
            outro_disco = _disco(source) != _disco(dest.parent)
            bloqueio = self._conteudo_bloqueado(source, limitar_tamanho=outro_disco)
            if bloqueio:
                return bloqueio
            shutil.move(str(source), str(dest))
            logger.info("movido: %s -> %s", source, dest)
            return f"Movido para: {dest}"

        return self._alterando(mover)

    @_recusas
    def copy_item(self, origem: str, destino: str) -> str:
        """Copia um arquivo ou pasta (ate 2 GB). Nunca sobrescreve e nunca troca a extensao.

        Args:
            origem: caminho completo.
            destino: novo caminho completo (ou pasta de destino existente).
        """
        source, dest = self._guard.resolve(origem), self._guard.resolve(destino)

        def copiar() -> str:
            nonlocal dest
            bloqueio = self._origem_bloqueada(source)
            if bloqueio:
                return bloqueio
            if not source.exists():
                return f"Nao existe: {source}"
            if dest.is_dir():
                dest = dest / source.name
            bloqueio = self._destino_bloqueado(source, dest)
            if bloqueio:
                return bloqueio
            if dest.exists() or dest.is_symlink():
                return f"Ja existe algo em {dest}. Nao sobrescrevo."
            bloqueio = self._conteudo_bloqueado(source, limitar_tamanho=True)
            if bloqueio:
                return bloqueio
            if source.is_dir():
                shutil.copytree(str(source), str(dest), symlinks=True)
            else:
                shutil.copy2(str(source), str(dest))
            logger.info("copiado: %s -> %s", source, dest)
            return f"Copiado para: {dest}"

        return self._alterando(copiar)

    @_recusas
    def create_text_file(self, caminho: str, conteudo: str) -> str:
        """Cria um arquivo de texto novo (.txt ou .md) com o conteudo dado. Nunca sobrescreve.

        Args:
            caminho: ex.: "area de trabalho\\lista de compras.txt".
            conteudo: o texto do arquivo.
        """
        target = self._guard.resolve(caminho)
        if suffix_of(target) not in TEXT_EXTENSIONS:
            target = target.with_suffix(".txt")
        if self._guard.is_protected(target):
            return MSG_PROTEGIDO

        def criar() -> str:
            if target.exists():
                return f"Ja existe: {target}. Nao sobrescrevo."
            target.parent.mkdir(parents=True, exist_ok=True)
            # "x" = so cria: falha se o arquivo surgir entre a checagem e a escrita.
            with target.open("x", encoding="utf-8") as handle:
                handle.write(conteudo)
            logger.info("arquivo criado: %s", target)
            return f"Arquivo criado: {target}"

        return self._alterando(criar)

    @_recusas
    def delete_to_trash(self, caminho: str) -> str:
        """Manda um arquivo ou pasta para a LIXEIRA. Abre uma janela no Windows e SO o clique
        do senhor em "Sim" autoriza. Avise o senhor para confirmar na tela.

        Args:
            caminho: caminho completo (use find_file antes).
        """
        target = self._guard.resolve(caminho)
        # A janela real so existe no Windows; com confirm injetado (testes), segue.
        if self._confirm is None and not windows.IS_WINDOWS:
            return ONLY_WINDOWS
        if self._confirmando.is_set() or not self._lock.acquire(timeout=LOCK_WAIT_S):
            return MSG_OCUPADO
        try:
            # Tudo checado COM a trava: nenhuma outra acao troca o item ate o fim.
            if self._guard.is_protected(target):
                return "Protegido: nao apago nada do sistema nem da pasta do Jarvis."
            if not target.exists() and not target.is_symlink():
                return "Esse arquivo nao existe. Use find_file primeiro."
            if self._guard.is_user_root(target):
                return MSG_PASTA_PESSOAL
            if self._guard.contains_protected(target):
                return MSG_CONTEM_PROTEGIDO
            if not windows.has_recycle_bin(target):
                return MSG_SEM_LIXEIRA
            self._confirmando.set()
            antes = _assinatura(target)
            kind = "a PASTA" if target.is_dir() else "o arquivo"
            if not self._ask_confirmation(f"Mandar {kind} para a Lixeira?\n\n{target}"):
                logger.info("apagar recusado na janela: %s", target)
                return "O senhor NAO autorizou na janela (ou o tempo acabou). Nada foi apagado."
            try:
                depois = _assinatura(target)
            except OSError:
                depois = None
            if depois != antes:
                logger.warning("item mudou durante a confirmacao; nada apagado: %s", target)
                return MSG_MUDOU
            send2trash(str(target))
        finally:
            self._confirmando.clear()
            self._lock.release()
        logger.info("enviado para a lixeira: %s", target)
        return f"'{target.name}' foi para a Lixeira (autorizado manualmente)."


def _resolver(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path


def _disco(path: Path) -> int | None:
    """Volume do caminho (st_dev) ou None se nao der para saber."""
    atual = path
    while True:
        try:
            return atual.stat().st_dev
        except OSError:
            if atual.parent == atual:
                return None
            atual = atual.parent
