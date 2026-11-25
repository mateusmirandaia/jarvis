"""Ferramentas de aplicativos: listar, abrir e fechar apps do Windows.

Abrir: so os apps conhecidos (``APPS``) ou atalhos ``.lnk`` do Menu Iniciar, pelo nome que
aparece no menu. Nunca um executavel do PATH, da pasta atual ou por caminho, e nunca
ferramentas de sistema perigosas (``BLOCKED_PROGRAMS``), mesmo que tenham atalho.

Fechar: nome com pelo menos 3 letras, casado por palavra inteira; fechar a forca so um
programa por vez; processos do sistema e do proprio Jarvis nunca.
"""

from __future__ import annotations

import logging
import os
import re
import struct
import webbrowser
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from jarvis.os_integration import windows
from jarvis.tools.security import PROTECTED_PROCESSES, normalize

logger = logging.getLogger(__name__)

# nome falado -> (comando para abrir, processos que representam o app)
APPS: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "calculadora": ("calc.exe", ("calculatorapp.exe", "calc.exe")),
    "bloco de notas": ("notepad.exe", ("notepad.exe",)),
    "paint": ("mspaint.exe", ("mspaint.exe",)),
    "explorador de arquivos": ("explorer.exe", ()),
    "navegador": (None, ("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe")),
    "chrome": ("chrome", ("chrome.exe",)),
    "edge": ("msedge", ("msedge.exe",)),
    "word": ("winword", ("winword.exe",)),
    "excel": ("excel", ("excel.exe",)),
    "powerpoint": ("powerpnt", ("powerpnt.exe",)),
    "vs code": ("code", ("code.exe",)),
    "spotify": ("spotify", ("spotify.exe",)),
    "whatsapp": ("whatsapp:", ("whatsapp.exe", "whatsapp.root.exe")),
}
APP_NAMES: tuple[str, ...] = tuple(APPS)

BROWSERS: frozenset[str] = frozenset(
    {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
)

# Programas que o Jarvis nunca abre (nem por nome, nem por atalho do Menu Iniciar).
BLOCKED_PROGRAMS: frozenset[str] = frozenset(
    {
        "cmd",
        "powershell",
        "powershell_ise",
        "pwsh",
        "wt",
        "windowsterminal",
        "regedit",
        "regedt32",
        "mshta",
        "wscript",
        "cscript",
        "rundll32",
        "certutil",
        "bitsadmin",
        "msiexec",
        "logoff",
        "shutdown",
        "taskkill",
        "reg",
        "schtasks",
        "sc",
        "net",
        "net1",
        "diskpart",
        "format",
        "bcdedit",
        "wmic",
        "mmc",
        "control",
        "msconfig",
        "gpedit",
        "secpol",
        "compmgmt",
        "taskschd",
        "services",
        "bash",
        "wsl",
        "python",
        "pythonw",
        "py",
        "conhost",
        "runas",
    }
)
# Nomes exibidos de atalhos que abrem um terminal ou o registro (em ingles e portugues).
BLOCKED_SHORTCUT_WORDS: tuple[str, ...] = (
    "prompt de comando",
    "command prompt",
    "terminal",
    "powershell",
    "editor do registro",
    "registry editor",
    "executar",
    "prompt",
    "uninstall",
    "uninstaller",
    "desinstalar",
)
# Pastas do Menu Iniciar com ferramentas de sistema: atalhos dali nao sao abertos.
BLOCKED_START_FOLDERS: frozenset[str] = frozenset(
    {
        "administrative tools",
        "ferramentas administrativas",
        "windows tools",
        "ferramentas do windows",
        "windows powershell",
        "system tools",
        "ferramentas do sistema",
        "windows system",
        "sistema do windows",
    }
)
# Atalho do Menu Iniciar so abre se o alvo (quando da para ler) for um .exe.
_SHORTCUT_TARGETS_OK: frozenset[str] = frozenset({".exe", ""})

MIN_NAME_CHARS = 3
START_MENU_MAX_DEPTH = 4
START_MENU_MAX_FILES = 3000

ONLY_WINDOWS = "Esta acao so funciona no Windows."
MSG_BLOQUEADO = "Senhor, esse programa eu nao abro por seguranca."
MSG_CAMINHO = "Senhor, abro apps pelo nome do Menu Iniciar, nao por caminho."
MSG_NOME_CURTO = "Senhor, diga o nome do aplicativo, com pelo menos 3 letras."
MSG_FORCA_VARIOS = (
    "Senhor, isso fecharia a forca mais de um programa ({nomes}). Diga qual deles, por favor."
)
MSG_VARIOS = "Senhor, achei janelas de mais de um programa: {nomes}. Qual delas devo fechar?"


def _palavras(texto: str) -> list[str]:
    return [p for p in re.split(r"[^0-9a-z+#]+", normalize(texto)) if p]


def _contem_frase(texto: str, frase: str) -> bool:
    """True se ``frase`` aparece em ``texto`` como palavras inteiras (sem acento/caixa)."""
    alvo, palavras = _palavras(frase), _palavras(texto)
    if not alvo:
        return False
    n = len(alvo)
    return any(palavras[i : i + n] == alvo for i in range(len(palavras) - n + 1))


def _stem(nome: str) -> str:
    return normalize(PureWindowsPath(nome).stem if nome.lower().endswith(".exe") else nome)


def is_blocked_name(nome: str) -> bool:
    """True se o nome pedido/exibido e de um programa perigoso (cmd, regedit, logoff...)."""
    norm = normalize(nome).removesuffix(".exe")
    if norm in BLOCKED_PROGRAMS:
        return True
    if any(p.removesuffix(".exe") in BLOCKED_PROGRAMS for p in _palavras(nome)):
        return True
    return any(_contem_frase(nome, frase) for frase in BLOCKED_SHORTCUT_WORDS)


# ------------------------------------------------------------------ atalhos .lnk
def start_menu_folders() -> list[Path]:
    """Pastas "Programas" do Menu Iniciar do usuario e de todos os usuarios."""
    pastas: list[Path] = []
    for var in ("APPDATA", "ProgramData"):
        base = os.environ.get(var)
        if base:
            pastas.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return pastas


@dataclass(frozen=True)
class Shortcut:
    """Um atalho .lnk do Menu Iniciar."""

    name: str
    path: Path
    folder: str


def list_shortcuts(folders: list[Path] | None = None) -> list[Shortcut]:
    """Atalhos .lnk do Menu Iniciar (sem seguir links de pasta, ate 4 niveis)."""
    atalhos: list[Shortcut] = []
    for raiz in folders if folders is not None else start_menu_folders():
        if not raiz.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(raiz, followlinks=False):
            atual = Path(dirpath)
            if len(atual.relative_to(raiz).parts) >= START_MENU_MAX_DEPTH:
                dirnames[:] = []
            for nome in filenames:
                if nome.lower().endswith(".lnk"):
                    pasta = atual.relative_to(raiz).as_posix()
                    atalhos.append(Shortcut(nome[:-4], atual / nome, pasta))
            if len(atalhos) >= START_MENU_MAX_FILES:
                return atalhos
    return atalhos


def _ler_texto(dados: bytes, pos: int, unicode: bool) -> tuple[str, int]:
    (quantos,) = struct.unpack_from("<H", dados, pos)
    pos += 2
    tamanho = quantos * (2 if unicode else 1)
    bruto = dados[pos : pos + tamanho]
    texto = bruto.decode("utf-16-le" if unicode else "cp1252", errors="replace")
    return texto, pos + tamanho


def _ler_c_string(dados: bytes, pos: int, unicode: bool) -> str:
    if unicode:
        fim = pos
        while fim + 1 < len(dados) and dados[fim : fim + 2] != b"\x00\x00":
            fim += 2
        return dados[pos:fim].decode("utf-16-le", errors="replace")
    fim = dados.find(b"\x00", pos)
    return dados[pos : fim if fim >= 0 else len(dados)].decode("cp1252", errors="replace")


@dataclass(frozen=True)
class ShortcutInfo:
    """O que um .lnk executa: caminhos (local, relativo, variavel de ambiente) e argumentos."""

    paths: tuple[str, ...]
    arguments: str


def read_shortcut(lnk: Path) -> ShortcutInfo:
    """Le um atalho .lnk (formato MS-SHLLINK) sem abrir nada.

    Pega o caminho local (LinkInfo), o caminho relativo, os argumentos e o bloco de variaveis
    de ambiente (ex.: ``%windir%\\system32\\cmd.exe``). Atalhos de apps da Loja ou
    "anunciados" (MSI) nao tem esses campos: ``paths`` volta vazio.

    Raises:
        ValueError: se o arquivo nao for um atalho valido.
    """
    dados = lnk.read_bytes()[:1_000_000]
    if len(dados) < 0x4C or struct.unpack_from("<I", dados, 0)[0] != 0x4C:
        raise ValueError("nao e um atalho .lnk")
    (flags,) = struct.unpack_from("<I", dados, 0x14)
    unicode = bool(flags & 0x80)
    pos = 0x4C
    paths: list[str] = []
    arguments = ""
    if flags & 0x01:  # HasLinkTargetIDList
        (tamanho,) = struct.unpack_from("<H", dados, pos)
        pos += 2 + tamanho
    if flags & 0x02:  # HasLinkInfo
        inicio = pos
        (info_tam, cab_tam, _info_flags, _vol, base_off) = struct.unpack_from("<5I", dados, pos)
        if base_off:
            paths.append(_ler_c_string(dados, inicio + base_off, False))
        if cab_tam >= 0x24:
            (base_uni,) = struct.unpack_from("<I", dados, inicio + 0x1C)
            if base_uni:
                paths.append(_ler_c_string(dados, inicio + base_uni, True))
        pos = inicio + info_tam
    for bit in (0x04, 0x08, 0x10, 0x20, 0x40):  # nome, relativo, pasta, argumentos, icone
        if flags & bit:
            texto, pos = _ler_texto(dados, pos, unicode)
            if bit == 0x08:
                paths.append(texto)
            elif bit == 0x20:
                arguments = texto
    while pos + 8 <= len(dados):  # ExtraData
        (tamanho, assinatura) = struct.unpack_from("<II", dados, pos)
        if tamanho < 4:
            break
        if assinatura == 0xA0000001 and tamanho >= 0x314:  # EnvironmentVariableDataBlock
            paths.append(_ler_c_string(dados, pos + 8, False))
            paths.append(_ler_c_string(dados, pos + 8 + 260, True))
        pos += tamanho
    return ShortcutInfo(tuple(p.strip().strip('"') for p in paths if p.strip()), arguments)


def shortcut_is_safe(atalho: Shortcut) -> bool:
    """True se o atalho pode ser aberto (nem pasta de sistema, nem alvo perigoso)."""
    pastas = {normalize(p) for p in atalho.folder.split("/") if p and p != "."}
    if pastas & BLOCKED_START_FOLDERS:
        return False
    if is_blocked_name(atalho.name):
        return False
    try:
        info = read_shortcut(atalho.path)
    except (OSError, ValueError, struct.error):
        logger.warning("atalho ilegivel recusado: %s", atalho.path)
        return False
    for caminho in info.paths:
        nome = PureWindowsPath(caminho).name
        if _stem(nome) in BLOCKED_PROGRAMS or is_blocked_name(PureWindowsPath(nome).stem):
            return False
        if PureWindowsPath(nome).suffix.lower() not in _SHORTCUT_TARGETS_OK:
            return False
    for token in re.split(r"[\s\"',;=]+", info.arguments):
        if token and _stem(PureWindowsPath(token).name) in BLOCKED_PROGRAMS:
            return False
    return True


def find_shortcut(nome: str, atalhos: list[Shortcut]) -> Shortcut | list[Shortcut] | None:
    """Melhor atalho para ``nome``: exato > comeca com > contem (palavras inteiras).

    Returns:
        O atalho, uma lista (empate entre programas diferentes) ou None.
    """
    chave = normalize(nome)
    exatos = [a for a in atalhos if normalize(a.name) == chave]
    if exatos:
        return exatos[0]
    comeca = [a for a in atalhos if _palavras(a.name)[: len(_palavras(chave))] == _palavras(chave)]
    contem = [a for a in atalhos if _contem_frase(a.name, chave)]
    for grupo in (comeca, contem):
        if not grupo:
            continue
        nomes = {normalize(a.name) for a in grupo}
        if len(nomes) == 1:
            return grupo[0]
        return sorted(grupo, key=lambda a: (len(a.name), a.name))[:5]
    return None


class AppTools:
    """Abre e fecha aplicativos pelo nome, nunca por caminho, nunca processos do sistema."""

    TOOL_NAMES: tuple[str, ...] = ("list_open_apps", "open_app", "close_app")

    def __init__(self, start_menu: list[Path] | None = None) -> None:
        """Cria as ferramentas de apps.

        Args:
            start_menu: pastas do Menu Iniciar (testes); None usa as do Windows.
        """
        self._start_menu = start_menu

    @property
    def app_names(self) -> list[str]:
        """Nomes de apps conhecidos (usados no prompt do sistema)."""
        return list(APP_NAMES)

    def _windows(self) -> list[windows.Window]:
        return windows.list_windows(PROTECTED_PROCESSES)

    def list_open_apps(self) -> str:
        """Lista os aplicativos abertos na tela (processo e titulo da janela)."""
        apps = self._windows()
        if not apps:
            return "Nao encontrei janelas abertas (ou nao estou no Windows)."
        return " | ".join(f"{w.process}: {w.title[:60]}" for w in apps[:25])

    def open_app(self, nome: str) -> str:
        """Abre um aplicativo pelo nome (ex.: calculadora, chrome, word, excel, spotify) ou
        pelo nome que aparece no Menu Iniciar do Windows.

        Args:
            nome: nome do app.
        """
        if not windows.IS_WINDOWS:
            return ONLY_WINDOWS
        texto = str(nome).strip()
        key = normalize(texto)
        if any(sep in texto for sep in ("\\", "/", ":")):
            logger.warning("abertura por caminho recusada: %s", texto)
            return MSG_CAMINHO
        key = key.removesuffix(".exe").strip()
        if is_blocked_name(key):
            logger.warning("app bloqueado recusado: %s", texto)
            return MSG_BLOQUEADO
        if len(key.replace(" ", "")) < MIN_NAME_CHARS:
            return MSG_NOME_CURTO
        if key == "navegador":
            webbrowser.open("about:blank")
            return "Navegador aberto."
        command = APPS.get(key, (None, ()))[0]
        if command is not None:
            try:
                windows.open_with_shell(command)
                return f"{texto} aberto."
            except OSError:
                logger.info("app conhecido %s nao abriu pelo nome; tentando o Menu Iniciar", key)
        return self._abrir_atalho(texto, key)

    def _abrir_atalho(self, texto: str, key: str) -> str:
        achado = find_shortcut(key, list_shortcuts(self._start_menu))
        if achado is None:
            return f"Senhor, nao encontrei o app '{texto}' no Menu Iniciar."
        if isinstance(achado, list):
            nomes = ", ".join(a.name for a in achado)
            return f"Senhor, achei mais de um: {nomes}. Qual deles?"
        if not shortcut_is_safe(achado):
            logger.warning("atalho perigoso recusado: %s", achado.path)
            return MSG_BLOQUEADO
        try:
            windows.open_with_shell(achado.path)
        except OSError:
            return f"Senhor, o Windows nao conseguiu abrir '{achado.name}'."
        logger.info("atalho aberto: %s", achado.path)
        return f"{achado.name} aberto."

    def close_app(self, nome: str, forcar: bool = False) -> str:
        """Fecha um aplicativo aberto (pelo nome do app ou por uma palavra do titulo da janela).
        Fecha a janela do jeito normal (o app pode perguntar se quer salvar).

        Args:
            nome: ex.: "navegador", "calculadora", "firefox", ou parte do titulo da janela.
            forcar: True so se o senhor pedir para fechar a forca (perde o que nao foi salvo).
        """
        if not windows.IS_WINDOWS:
            return ONLY_WINDOWS
        key = normalize(str(nome)).removesuffix(".exe").strip()
        if len(key.replace(" ", "")) < MIN_NAME_CHARS:
            return MSG_NOME_CURTO
        open_windows = [w for w in self._windows() if w.process.lower() not in PROTECTED_PROCESSES]
        conhecido = key in APPS
        known = {p.lower() for p in APPS.get(key, (None, ()))[1]}
        targets = [w for w in open_windows if w.process.lower() in known]
        if not targets and (known & BROWSERS or key == "navegador"):
            targets = [w for w in open_windows if w.process.lower() in BROWSERS]
        if not targets:
            compact = key.replace(" ", "")
            targets = [
                w
                for w in open_windows
                if _stem(w.process).replace(" ", "") == compact or _contem_frase(w.title, key)
            ]
        if not targets:
            return f"Nao achei '{nome}' aberto. Abertos agora: {self.list_open_apps()}"
        processes = sorted({w.process for w in targets}, key=str.lower)
        if forcar:
            if len({p.lower() for p in processes}) > 1:
                return MSG_FORCA_VARIOS.format(nomes=", ".join(processes))
            windows.kill_process(processes[0])
            return "Fechado a forca: " + processes[0]
        if not conhecido and len({p.lower() for p in processes}) > 1:
            return MSG_VARIOS.format(nomes=", ".join(processes))
        for w in targets:
            windows.close_window(w.hwnd)
        return "Fechei: " + " | ".join(f"{w.process} ({w.title[:40]})" for w in targets)
