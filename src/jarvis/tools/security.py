"""Regras de seguranca compartilhadas pelas ferramentas do Jarvis.

- Processos do sistema e o proprio Jarvis nunca sao fechados.
- Programas e scripts nunca sao executados por caminho (so apps conhecidos e atalhos do
  Menu Iniciar, pelo nome).
- Arquivos so sao abertos se a extensao estiver na lista POSITIVA de documentos e midia.
- Pastas do sistema, a raiz do disco, a pasta do projeto (onde fica a chave .env), a pasta
  das configuracoes, o AppData (Menu Iniciar e Inicializar ficam la) e pastas de chaves
  (.ssh, .aws...) sao protegidas: nada e lido, aberto, criado, movido ou apagado nelas.
- Caminhos de rede (\\\\servidor\\pasta), de dispositivo (\\\\?\\, \\\\.\\), com fluxo
  alternativo (":") ou com ponto/espaco no fim do nome sao recusados.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path, PureWindowsPath

logger = logging.getLogger(__name__)

# Nomes de imagem como o tasklist mostra, sempre em minusculo e com ".exe".
PROTECTED_PROCESSES: frozenset[str] = frozenset(
    {
        # nucleo do Windows
        "explorer.exe",
        "svchost.exe",
        "csrss.exe",
        "winlogon.exe",
        "lsass.exe",
        "services.exe",
        "smss.exe",
        "wininit.exe",
        "dwm.exe",
        "msmpeng.exe",
        "sihost.exe",
        "ctfmon.exe",
        "fontdrvhost.exe",
        "shellexperiencehost.exe",
        "startmenuexperiencehost.exe",
        "searchhost.exe",
        "searchapp.exe",
        "searchui.exe",
        "textinputhost.exe",
        "runtimebroker.exe",
        "applicationframehost.exe",
        "lockapp.exe",
        "securityhealthsystray.exe",
        # o proprio Jarvis (instalado ou pelo codigo) e o terminal dele
        "jarvis.exe",
        "python.exe",
        "pythonw.exe",
        "py.exe",
        "pyw.exe",
        "powershell.exe",
        "pwsh.exe",
        "cmd.exe",
        "windowsterminal.exe",
        "conhost.exe",
        "openconsole.exe",
        "msedgewebview2.exe",
    }
)

# Extensoes que executam algo (so para mensagens e para o teste de regressao): a regra que
# vale e a lista POSITIVA ``OPENABLE_EXTENSIONS`` abaixo.
EXECUTABLE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".ps1",
        ".psm1",
        ".psd1",
        ".ps1xml",
        ".vbs",
        ".vbe",
        ".js",
        ".jse",
        ".wsf",
        ".wsh",
        ".msi",
        ".msp",
        ".msix",
        ".appx",
        ".appinstaller",
        ".scr",
        ".com",
        ".pif",
        ".cpl",
        ".msc",
        ".reg",
        ".jar",
        ".hta",
        ".lnk",
        ".url",
        ".py",
        ".pyw",
        ".application",
        ".appref-ms",
        ".settingcontent-ms",
        ".library-ms",
        ".search-ms",
        ".scf",
        ".inf",
        ".chm",
        ".iso",
        ".img",
        ".vhd",
        ".vhdx",
        ".xll",
        ".docm",
        ".xlsm",
        ".pptm",
        ".dotm",
        ".diagcab",
        ".rdp",
        ".dll",
        ".sys",
    }
)

# Lista POSITIVA: o que open_file abre com o programa padrao (documentos, fotos, audio, video).
OPENABLE_EXTENSIONS: frozenset[str] = frozenset(
    {
        # documentos
        ".pdf",
        ".doc",
        ".docx",
        ".odt",
        ".rtf",
        ".txt",
        ".md",
        ".csv",
        ".xls",
        ".xlsx",
        ".ods",
        ".ppt",
        ".pptx",
        ".odp",
        ".epub",
        ".log",
        # imagens
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
        ".heic",
        # audio
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".opus",
        ".wma",
        # video
        ".mp4",
        ".m4v",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".webm",
        # compactado (abre no Explorer)
        ".zip",
    }
)

# Ao mover/renomear/copiar, a extensao so pode mudar dentro do mesmo grupo.
EXTENSION_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({".txt", ".md"}),
    frozenset({".jpg", ".jpeg"}),
    frozenset({".tif", ".tiff"}),
)

# Arquivos que costumam guardar senhas e chaves: nao sao abertos, copiados nem movidos.
SECRET_NAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".git-credentials",
        ".npmrc",
        ".pypirc",
        ".netrc",
        "_netrc",
        "credentials",
        "credentials.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "login data",
        "cookies",
        "local state",
        "logins.json",
        "key3.db",
        "key4.db",
    }
)
SECRET_EXTENSIONS: frozenset[str] = frozenset(
    {".pem", ".key", ".pfx", ".p12", ".ppk", ".kdbx", ".ovpn", ".env"}
)

# Pastas dentro do home que guardam chaves ou sao executadas pelo Windows/apps.
_HOME_PROTECTED: tuple[str, ...] = (
    "AppData",  # Menu Iniciar, Inicializar, configuracoes e programas do usuario
    ".ssh",
    ".aws",
    ".azure",
    ".kube",
    ".gnupg",
    ".docker",
)
# Pastas de perfil do PowerShell (um profile.ps1 ali roda ao abrir o PowerShell).
_POWERSHELL_PROFILES: tuple[str, ...] = ("WindowsPowerShell", "PowerShell")

_DEVICE_NAMES = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.IGNORECASE)
_SHORT_NAME = re.compile(r"~\d")
_CLSID = re.compile(r"\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}", re.I)

MSG_REDE = "Senhor, nao mexo em pastas de rede nem em caminhos especiais do Windows."
MSG_NOME = "Senhor, esse nome de arquivo nao e seguro. Use um nome comum, sem ponto no fim."
MSG_OUTROS_DRIVES = "Acesso a outros discos (como D: ou pendrive) está desligado nas permissões."
# Variaveis que o OneDrive cria no Windows (pessoal e de trabalho/escola).
_ONEDRIVE_VARS: tuple[str, ...] = ("OneDrive", "OneDriveConsumer", "OneDriveCommercial")


class CaminhoRecusado(ValueError):
    """Caminho recusado por seguranca; a mensagem ja e a frase para o senhor."""


def normalize(text: str) -> str:
    """Deixa o texto em minusculo, sem acentos e sem espacos nas pontas."""
    decomposed = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def suffix_of(path: Path | str) -> str:
    """Extensao em minusculo do nome final (como o Windows ve: sem ponto/espaco no fim)."""
    name = PureWindowsPath(str(path)).name.rstrip(" .")
    return PureWindowsPath(name).suffix.lower() if name else ""


def is_secret(path: Path | str) -> bool:
    """True para arquivos com cara de guardar senha ou chave (.env, id_rsa, .pem...)."""
    name = PureWindowsPath(str(path)).name.lower().rstrip(" .")
    if name in SECRET_NAMES or name.startswith(".env."):
        return True
    return suffix_of(name) in SECRET_EXTENSIONS


def same_extension_family(old: str, new: str) -> bool:
    """True se trocar a extensao ``old`` por ``new`` nao muda o tipo do arquivo."""
    if old == new:
        return True
    return any(old in grupo and new in grupo for grupo in EXTENSION_GROUPS)


def _is_network_or_device(text: str) -> bool:
    texto = text.strip()
    if texto.startswith(("\\\\", "//", "\\/", "/\\")):
        return True
    drive = PureWindowsPath(texto).drive
    return drive.startswith(("\\\\", "//"))


def check_syntax(path: Path | str) -> None:
    """Recusa caminhos de rede/dispositivo e nomes que o Windows trata de um jeito especial.

    Raises:
        CaminhoRecusado: com a frase para o senhor.
    """
    texto = str(path)
    if _is_network_or_device(texto):
        raise CaminhoRecusado(MSG_REDE)
    puro = PureWindowsPath(texto)
    for parte in puro.parts[1:] if puro.anchor else puro.parts:
        if parte in (".", ".."):
            continue
        if ":" in parte:  # fluxo alternativo (arquivo.txt:escondido) ou unidade no meio
            raise CaminhoRecusado(MSG_NOME)
        if parte != parte.rstrip(" ."):  # "evil.bat." e "evil.bat " viram evil.bat
            raise CaminhoRecusado(MSG_NOME)
        if _DEVICE_NAMES.match(parte) or _SHORT_NAME.search(parte) or _CLSID.search(parte):
            raise CaminhoRecusado(MSG_NOME)
        if any(ord(ch) < 32 for ch in parte) or any(ch in '<>"|?*' for ch in parte):
            raise CaminhoRecusado(MSG_NOME)


def _system_folders() -> list[Path]:
    """Pastas do Windows que nunca podem ser alteradas."""
    return [
        Path(os.environ.get("SystemRoot", r"C:\Windows")),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("ProgramData", r"C:\ProgramData")),
    ]


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError):  # laco de links, caminho invalido
        return path.absolute()


class PathGuard:
    """Traduz caminhos falados em ``Path`` e diz se um caminho e protegido.

    Args:
        project_root: pasta do projeto Jarvis (protegida, pois guarda a chave).
        home: pasta do usuario; padrao ``Path.home()`` (injetavel para testes).
        extra_protected: outras pastas protegidas (ex.: ``%APPDATA%\\Jarvis``, com as chaves).
        outros_drives: funcao chamada A CADA ``resolve()`` que diz se a permissao "Outros
            discos" esta ligada. Desligada (ou erro): so caminhos dentro das pastas pessoais
            (home e OneDrive) passam. None = sem essa restricao (o ``ToolRegistry`` sempre
            injeta a funcao; None fica para usos internos e testes antigos).
    """

    def __init__(
        self,
        project_root: Path,
        home: Path | None = None,
        extra_protected: list[Path] | None = None,
        outros_drives: Callable[[], bool] | None = None,
    ) -> None:
        self._project_root = Path(project_root)
        self._home = Path(home) if home is not None else Path.home()
        self._outros_drives = outros_drives
        self._pessoais = [self._home, self._home / "OneDrive"]
        if home is None:  # OneDrive fora do home (o Windows guarda o caminho nestas variaveis)
            for nome in _ONEDRIVE_VARS:
                valor = os.environ.get(nome, "").strip()
                if valor and Path(valor).is_absolute() and not _is_network_or_device(valor):
                    self._pessoais.append(Path(valor))
        extras = [Path(pasta) for pasta in extra_protected or []]
        appdata = os.environ.get("APPDATA")
        home_protected = [self._home / nome for nome in _HOME_PROTECTED]
        profiles = [
            docs / nome for docs in self._documents_candidates() for nome in _POWERSHELL_PROFILES
        ]
        self._protected = [
            *_system_folders(),
            self._project_root,
            *extras,
            *home_protected,
            *([Path(appdata)] if appdata else []),
            *profiles,
        ]

    @property
    def project_root(self) -> Path:
        """Pasta do projeto Jarvis."""
        return self._project_root

    @property
    def home(self) -> Path:
        """Pasta do usuario usada para os atalhos."""
        return self._home

    @property
    def protected_folders(self) -> list[Path]:
        """Pastas protegidas (copia), na ordem em que sao checadas."""
        return list(self._protected)

    @property
    def personal_roots(self) -> list[Path]:
        """Pastas pessoais (home e OneDrive): o limite quando "Outros discos" esta desligado."""
        return list(self._pessoais)

    def outros_drives_ligado(self) -> bool:
        """Consulta a permissao "Outros discos" agora (erro ou valor estranho = desligado)."""
        if self._outros_drives is None:
            return True
        try:
            return self._outros_drives() is True
        except Exception:  # noqa: BLE001 - permissao ilegivel vale como desligada
            logger.warning("nao consegui ler a permissao de outros discos", exc_info=True)
            return False

    def is_personal(self, path: Path) -> bool:
        """True se ``path`` (ja resolvido, seguindo links) fica dentro do home ou do OneDrive."""
        alvo = _safe_resolve(Path(path))
        return any(alvo.is_relative_to(_safe_resolve(base)) for base in self._pessoais)

    def _checar_disco(self, path: Path) -> Path:
        if not self.outros_drives_ligado() and not self.is_personal(path):
            logger.info("outro disco recusado (permissao desligada): %s", path)
            raise CaminhoRecusado(MSG_OUTROS_DRIVES)
        return path

    def _documents_candidates(self) -> list[Path]:
        home = self._home
        return [
            home / "OneDrive" / "Documentos",
            home / "OneDrive" / "Documents",
            home / "Documents",
        ]

    def _folder_options(self) -> dict[str, list[Path]]:
        home = self._home
        return {
            "area de trabalho": [
                home / "OneDrive" / "Área de Trabalho",
                home / "OneDrive" / "Desktop",
                home / "Desktop",
                home / "Área de Trabalho",
            ],
            "documentos": self._documents_candidates(),
            "downloads": [home / "Downloads"],
            "imagens": [
                home / "OneDrive" / "Imagens",
                home / "OneDrive" / "Pictures",
                home / "Pictures",
                home / "Imagens",
            ],
            "musicas": [home / "Music", home / "Músicas"],
            "videos": [home / "Videos", home / "Vídeos"],
        }

    def user_folders(self) -> dict[str, Path]:
        """Atalhos falados -> pasta real (OneDrive primeiro, como o Windows costuma usar)."""
        return {
            name: next((p for p in candidates if p.is_dir()), candidates[-1])
            for name, candidates in self._folder_options().items()
        }

    def user_roots(self) -> list[Path]:
        """Pastas pessoais inteiras (home, OneDrive, Area de Trabalho, Documentos...)."""
        roots = [self._home, self._home / "OneDrive"]
        for candidates in self._folder_options().values():
            roots.extend(candidates)
        return roots

    def is_user_root(self, path: Path) -> bool:
        """True se ``path`` e uma pasta pessoal inteira ou contem uma (ex.: o home, C:\\Users).

        Essas pastas nao podem ser movidas, renomeadas nem apagadas pelo Jarvis.
        """
        alvo = _safe_resolve(Path(path))
        for root in self.user_roots():
            base = _safe_resolve(root)
            if base == alvo or base.is_relative_to(alvo):
                return True
        return False

    def contains_protected(self, path: Path) -> bool:
        """True se dentro de ``path`` existe uma pasta protegida (ex.: o projeto do Jarvis)."""
        alvo = _safe_resolve(Path(path))
        return any(_safe_resolve(p).is_relative_to(alvo) for p in self._protected)

    def resolve(self, text: str, base: Path | None = None) -> Path:
        """Aceita caminho completo, "C:" (vira "C:\\") ou atalhos como "area de trabalho\\x".

        Nao expande variaveis (%APPDATA%, $HOME): o texto vem da IA e pode ter sido injetado.

        Args:
            text: caminho dito pelo usuario ou escolhido pela IA.
            base: pasta para caminho RELATIVO (ex.: Documentos no Word). Sem ``base``, o
                relativo fica relativo (a pasta atual do processo). A regra de "Outros discos"
                e conferida no caminho FINAL, ja juntado a ``base``.

        Raises:
            CaminhoRecusado: caminho de rede, de dispositivo, com nome perigoso ou (com a
                permissao "Outros discos" desligada) fora das pastas pessoais.
        """
        raw = str(text).strip().strip('"').strip()
        if _is_network_or_device(raw):
            logger.warning("caminho de rede/dispositivo recusado: %r", raw[:80])
            raise CaminhoRecusado(MSG_REDE)
        norm = normalize(raw).replace("\\", "/")
        for alias, folder in self.user_folders().items():
            if norm == alias or norm.startswith(alias + "/"):
                rest = raw[len(alias) :].lstrip("\\/")
                path = folder / rest if rest else folder
                check_syntax(path)
                return self._checar_disco(path)
        if len(raw) == 2 and raw[1] == ":":
            raw += "\\"
        path = Path(os.path.expanduser(raw)) if raw.startswith("~") else Path(raw)
        if base is not None and not path.is_absolute() and not path.anchor:
            path = Path(base) / path
        check_syntax(path)
        return self._checar_disco(path)

    def is_protected(self, path: Path) -> bool:
        """True para a raiz do disco, pastas do sistema, do projeto e das chaves (e o de dentro).

        Caminhos de rede ou de dispositivo tambem contam como protegidos.

        Args:
            path: caminho a verificar (nao precisa existir).
        """
        if _is_network_or_device(str(path)):
            return True
        resolved = _safe_resolve(Path(path))
        if _is_network_or_device(str(resolved)):  # unidade mapeada vira \\servidor\pasta
            return True
        if resolved == Path(resolved.anchor):
            return True
        for folder in self._protected:
            base = _safe_resolve(folder)
            if resolved == base or resolved.is_relative_to(base):
                logger.info("caminho protegido bloqueado: %s", resolved)
                return True
        return False
