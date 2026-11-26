"""Testes da correcao de seguranca de 25/11/2026 (achados C1, C2, A1-A3, M1, M2, M5, B1-B4).

Cada bloco cita o achado. Tudo roda em pastas temporarias; o "Windows" e simulado com
monkeypatch (nenhuma janela abre, nada e executado de verdade).
"""

from __future__ import annotations

import json
import re
import struct
import sys
import threading
import types
import warnings
from pathlib import Path

import pytest

from jarvis.os_integration import windows
from jarvis.tools import app_tools, file_tools
from jarvis.tools.app_tools import AppTools
from jarvis.tools.file_tools import FileTools
from jarvis.tools.security import (
    EXECUTABLE_EXTENSIONS,
    OPENABLE_EXTENSIONS,
    CaminhoRecusado,
    PathGuard,
)

RAIZ = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def chaves(tmp_path: Path) -> Path:
    """Simula %APPDATA%\\Jarvis com a chave (pasta protegida extra do ToolRegistry)."""
    pasta = tmp_path / "AppData_real" / "Jarvis"
    pasta.mkdir(parents=True)
    (pasta / ".env").write_text("GEMINI_API_KEY=AIzaSEGREDO_DE_TESTE_123456\n", encoding="utf-8")
    return pasta


@pytest.fixture
def guarda(project_root: Path, home: Path, chaves: Path) -> PathGuard:
    return PathGuard(project_root=project_root, home=home, extra_protected=[chaves])


@pytest.fixture
def shell(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Finge ser Windows (disco interno) e anota o que iria para o os.startfile."""
    chamados: list[str] = []
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "open_with_shell", lambda alvo: chamados.append(str(alvo)))
    monkeypatch.setattr(windows, "drive_type", lambda _p: windows.DRIVE_FIXED)
    return chamados


@pytest.fixture
def lixeira(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    enviados: list[str] = []
    monkeypatch.setattr(file_tools, "send2trash", enviados.append)
    return enviados


def _ft(guarda: PathGuard, resposta: bool = True) -> FileTools:
    return FileTools(guarda, confirm=lambda _t, _m: resposta)


# ================================================================== C1 execucao de codigo
def test_c1_txt_nao_vira_script_na_pasta_inicializar(guarda: PathGuard, home: Path) -> None:
    startup = home / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup"
    startup.mkdir(parents=True)
    ft = _ft(guarda)
    assert "Arquivo criado" in ft.create_text_file("area de trabalho\\nota.txt", "@echo off")
    r = ft.move_or_rename("area de trabalho\\nota.txt", str(startup / "atualizador.cmd"))
    assert "protegida" in r
    r = ft.move_or_rename("area de trabalho\\nota.txt", str(startup / "nota.txt"))
    assert "protegida" in r
    assert "protegida" in ft.create_text_file(str(startup / "x.txt"), "oi")
    assert list(startup.iterdir()) == []


@pytest.mark.parametrize("novo", ["nota.bat", "nota.cmd", "nota.url", "nota.lnk", "nota.ps1"])
def test_c1_renomear_nao_troca_o_tipo(guarda: PathGuard, home: Path, novo: str) -> None:
    d = home / "Desktop"
    (d / "nota.txt").write_text("calc.exe", encoding="utf-8")
    ft = _ft(guarda)
    r = ft.move_or_rename(str(d / "nota.txt"), str(d / novo))
    assert "nao troco o tipo" in r and (d / "nota.txt").exists() and not (d / novo).exists()
    r = ft.copy_item(str(d / "nota.txt"), str(d / novo))
    assert "nao troco o tipo" in r and not (d / novo).exists()


def test_c1_renomear_comum_continua_funcionando(guarda: PathGuard, home: Path) -> None:
    d = home / "Desktop"
    (d / "a.txt").write_text("x", encoding="utf-8")
    (d / "foto.jpg").write_bytes(b"x")
    (d / "Projeto").mkdir()
    ft = _ft(guarda)
    assert "Movido" in ft.move_or_rename(str(d / "a.txt"), str(d / "a.md"))  # txt <-> md
    assert "Movido" in ft.move_or_rename(str(d / "foto.jpg"), str(d / "praia.jpeg"))
    assert "Movido" in ft.move_or_rename(str(d / "Projeto"), str(d / "Projeto 2024"))
    assert "Copiado" in ft.copy_item(str(d / "praia.jpeg"), "documentos")
    assert (home / "Documents" / "praia.jpeg").exists()
    assert "nome de programa" in ft.move_or_rename(str(d / "Projeto 2024"), str(d / "x.exe"))


def test_c1_cadeia_url_para_bat_quebrada(guarda: PathGuard, home: Path, shell: list) -> None:
    d = home / "Desktop"
    ft = _ft(guarda)
    ft.create_text_file(str(d / "b.txt"), "[InternetShortcut]\r\nURL=file:///C:/a.bat\r\n")
    assert "nao troco o tipo" in ft.move_or_rename(str(d / "b.txt"), str(d / "b.url"))
    (d / "b.url").write_text("[InternetShortcut]", encoding="utf-8")  # ja existia (download)
    assert ft.open_file(str(d / "b.url")) == file_tools.MSG_ABRIR_TIPO
    assert shell == []


@pytest.mark.parametrize("ext", sorted(EXECUTABLE_EXTENSIONS))
def test_c1_open_file_recusa_tudo_fora_da_lista_positiva(
    guarda: PathGuard, home: Path, shell: list, ext: str
) -> None:
    alvo = home / "Downloads" / f"fatura{ext}"
    alvo.write_bytes(b"x")
    assert FileTools(guarda).open_file(str(alvo)) == file_tools.MSG_ABRIR_TIPO
    assert shell == []


@pytest.mark.parametrize("ext", [".html", ".svg", ".xml", ".hta", ".bin", ".dat", ""])
def test_c1_open_file_desconhecido_tambem_e_recusado(
    guarda: PathGuard, home: Path, shell: list, ext: str
) -> None:
    alvo = home / "Downloads" / f"arquivo{ext}"
    alvo.write_bytes(b"x")
    assert FileTools(guarda).open_file(str(alvo)) == file_tools.MSG_ABRIR_TIPO
    assert shell == []


@pytest.mark.parametrize("ext", [".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".jpg", ".mp4", ".mp3"])
def test_c1_open_file_abre_documentos_e_midia(
    guarda: PathGuard, home: Path, shell: list, ext: str
) -> None:
    assert ext in OPENABLE_EXTENSIONS
    alvo = home / "Documents" / f"Relatório Final{ext.upper()}"
    alvo.write_bytes(b"x")
    assert FileTools(guarda).open_file(str(alvo)).startswith("Aberto")
    assert shell == [str(alvo)]


def test_c1_open_file_abre_pasta(guarda: PathGuard, home: Path, shell: list) -> None:
    assert FileTools(guarda).open_file("documentos").startswith("Aberto")
    assert shell == [str(home / "Documents")]


def test_c1_link_com_nome_de_pdf_para_programa_e_recusado(
    guarda: PathGuard, home: Path, shell: list
) -> None:
    programa = home / "Downloads" / "setup.exe"
    programa.write_bytes(b"MZ")
    disfarce = home / "Desktop" / "boleto.pdf"
    disfarce.symlink_to(programa)
    assert FileTools(guarda).open_file(str(disfarce)) == file_tools.MSG_ABRIR_TIPO
    assert shell == []


@pytest.mark.parametrize(
    "nome",
    [
        "evil.bat.",
        "evil.bat .",
        "evil.bat::$DATA",
        "nota.txt:oculto",
        "CON.txt",
        "nul",
        "PROGRA~1",
        "pasta.{645FF040-5081-101B-9F08-00AA002F954E}",
        'a"b.txt',
        "a|b.txt",
    ],
)
def test_c1_nomes_especiais_do_windows_sao_recusados(
    guarda: PathGuard, home: Path, shell: list, nome: str
) -> None:
    d = home / "Desktop"
    (d / "a.txt").write_text("x", encoding="utf-8")
    ft = _ft(guarda)
    for resultado in (
        ft.open_file(f"area de trabalho\\{nome}"),
        ft.move_or_rename(str(d / "a.txt"), f"area de trabalho\\{nome}"),
        ft.copy_item(str(d / "a.txt"), str(d / nome)),
        ft.create_text_file(f"area de trabalho\\{nome}", "x"),
        ft.create_folder(f"area de trabalho\\{nome}"),
    ):
        assert resultado.startswith("Senhor"), resultado
    assert shell == []
    assert sorted(p.name for p in d.iterdir()) == ["a.txt"]


def test_c1_espaco_no_fim_vira_o_nome_real_e_cai_na_lista_positiva(
    guarda: PathGuard, home: Path, shell: list
) -> None:
    (home / "Desktop" / "evil.bat").write_text("calc", encoding="utf-8")
    for nome in ("evil.bat ", "evil.bat\t"):
        r = FileTools(guarda).open_file(f"area de trabalho\\{nome}")
        assert r.startswith("Senhor"), r
    assert shell == []


def test_c1_powershell_profile_e_menu_iniciar_protegidos(guarda: PathGuard, home: Path) -> None:
    perfil = home / "Documents" / "WindowsPowerShell"
    perfil.mkdir()
    assert guarda.is_protected(perfil / "profile.ps1")
    assert guarda.is_protected(home / "AppData" / "Roaming" / "Microsoft" / "Windows")
    assert guarda.is_protected(home / ".ssh" / "id_rsa")


# ================================================================== C2 chaves
def test_c2_env_protegido_nao_sai_da_pasta(
    guarda: PathGuard, home: Path, chaves: Path, project_root: Path, shell: list
) -> None:
    ft = _ft(guarda)
    for origem in (chaves / ".env", project_root / ".env"):
        assert "protegida" in ft.copy_item(str(origem), "area de trabalho\\notas.txt")
        assert "protegida" in ft.move_or_rename(str(origem), "documentos")
        assert "protegida" in ft.open_file(str(origem))
    assert "protegida" in ft.list_folder(str(chaves))
    assert "protegida" in ft.find_file("env", onde=str(chaves))
    assert list((home / "Desktop").iterdir()) == []
    assert shell == []


def test_c2_arquivos_de_senha_fora_da_pasta_protegida(
    guarda: PathGuard, home: Path, shell: list
) -> None:
    outro = home / "Documents" / "outro_projeto"
    outro.mkdir()
    for nome in (".env", ".env.local", "id_rsa", "cert.pem", "senhas.kdbx"):
        (outro / nome).write_text("segredo", encoding="utf-8")
        ft = _ft(guarda)
        assert ft.open_file(str(outro / nome)) == file_tools.MSG_SEGREDO
        assert ft.copy_item(str(outro / nome), "area de trabalho") == file_tools.MSG_SEGREDO
    assert _ft(guarda).copy_item(str(outro), "area de trabalho") == file_tools.MSG_CONTEM_SEGREDO
    assert shell == []


def test_c2_pasta_com_atalho_para_a_pasta_das_chaves(
    guarda: PathGuard, home: Path, chaves: Path
) -> None:
    pasta = home / "Documents" / "inocente"
    pasta.mkdir()
    (pasta / "link").symlink_to(chaves, target_is_directory=True)
    r = _ft(guarda).copy_item(str(pasta), "area de trabalho")
    assert r == file_tools.MSG_CONTEM_LINK
    assert not (home / "Desktop" / "inocente").exists()


def test_c2_pasta_que_contem_o_projeto_nao_e_copiada(
    project_root: Path, tmp_path: Path, home: Path
) -> None:
    g = PathGuard(project_root=project_root, home=home)
    r = _ft(g).copy_item(str(project_root.parent), str(home / "Desktop"))
    assert r == file_tools.MSG_CONTEM_PROTEGIDO


@pytest.mark.parametrize(
    "caminho",
    [
        r"\\servidor\pasta\k.txt",
        r"\\host@SSL\DavWWWRoot\k",
        r"\\localhost\C$\Users",
        r"\\?\C:\Users\x\AppData\Roaming\Jarvis\.env",
        r"\\.\C:\x",
        "//servidor/pasta/k.txt",
    ],
)
def test_c2_rede_e_dispositivo_recusados(
    guarda: PathGuard, home: Path, shell: list, caminho: str
) -> None:
    with pytest.raises(CaminhoRecusado):
        guarda.resolve(caminho)
    assert guarda.is_protected(Path(caminho))
    (home / "Desktop" / "a.txt").write_text("x", encoding="utf-8")
    ft = _ft(guarda)
    assert ft.copy_item("area de trabalho\\a.txt", caminho).startswith("Senhor, nao mexo")
    assert ft.open_file(caminho).startswith("Senhor, nao mexo")
    assert ft.list_folder(caminho).startswith("Senhor, nao mexo")
    assert shell == []


def test_c2_sem_expandir_variaveis(guarda: PathGuard, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_POC", "/etc")
    assert guarda.resolve("$JARVIS_POC/x") == Path("$JARVIS_POC/x")
    assert guarda.resolve("%APPDATA%\\Jarvis\\.env") == Path("%APPDATA%\\Jarvis\\.env")


def test_c2_registry_protege_a_pasta_das_configuracoes(tmp_path: Path) -> None:
    from jarvis.armazenamento import pasta_usuario
    from jarvis.config import Settings
    from jarvis.tools import ToolRegistry

    reg = ToolRegistry(Settings(api_key="x", project_root=tmp_path / "p"), confirm=lambda *_: 0)
    assert reg.guard.is_protected(pasta_usuario() / ".env")


# ================================================================== A1 ponte da janela
def _nested(obj: object, nome: str) -> object:
    """Igual ao ``get_nested_attribute`` do pywebview (webview/util.py, 5.x e 6.x)."""
    for parte in nome.split("."):
        obj = getattr(obj, parte, None)
        if obj is None:
            return None
    return obj


def _ponte() -> tuple[object, list[str]]:
    from jarvis.ui.api_config import ApiJs, ponte_js

    abertos: list[str] = []
    return ponte_js(ApiJs(abrir_url=lambda u: abertos.append(u) or True)), abertos


_PERIGOSOS = (
    "__globals__",
    "__closure__",
    "__self__",
    "__func__",
    "__wrapped__",
    "__dict__",
    "__builtins__",
    "__code__",
    "__class__",
    "__base__",
    "__bases__",
    "__mro__",
    "__init__",
    "__call__",
    "__get__",
    "__module__",
    "__objclass__",
    "cell_contents",
    "f_globals",
    "gi_frame",
)
_FOLHAS = (str, bytes, int, float, bool, type(None), complex)


def _proibido(valor: object, modulos_dicts: set[int]) -> str | None:
    from jarvis.ui.api_config import ApiJs

    if isinstance(valor, types.ModuleType):
        return "modulo"
    if isinstance(valor, ApiJs):
        return "ApiJs"
    if isinstance(valor, dict) and id(valor) in modulos_dicts:
        return "globais de um modulo"
    if isinstance(valor, types.CellType):
        return "celula da closure"
    if isinstance(valor, types.MethodType):
        return "metodo ligado"
    if isinstance(valor, types.FunctionType):
        if set(valor.__globals__) - {"__builtins__"} or valor.__globals__.get("__builtins__"):
            return "funcao com globais"
        if valor.__builtins__:
            return "funcao com builtins"
    return None


def test_a1_getattr_encadeado_nao_alcanca_nada_alem_das_funcoes_publicas() -> None:
    """Varre TODOS os nomes "a.b.c.d" (dir() + dunders perigosos) a partir da ponte."""
    ponte, _ = _ponte()
    # Guarda os dicts vivos: alguns "modulos" (ex.: _openssl.lib da cryptography, que o
    # pypdf carrega) criam um __dict__ novo a cada acesso; sem isso o id seria reusado.
    dicts_vivos = [m.__dict__ for m in list(sys.modules.values()) if m is not None]
    modulos_dicts = {id(d) for d in dicts_vivos}
    guardados: list[object] = []  # mantem vivos (ids nao se repetem)
    vistos: set[int] = set()
    fila: list[tuple[object, str]] = [(ponte, "")]
    for _nivel in range(4):
        proxima: list[tuple[object, str]] = []
        for obj, caminho in fila:
            try:
                nomes = set(dir(obj)) | set(_PERIGOSOS)
            except Exception:  # noqa: BLE001
                nomes = set(_PERIGOSOS)
            for nome in sorted(nomes):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", DeprecationWarning)
                        valor = getattr(obj, nome, None)
                except Exception:  # noqa: BLE001
                    continue
                if valor is None:
                    continue
                nome_completo = f"{caminho}.{nome}" if caminho else nome
                motivo = _proibido(valor, modulos_dicts)
                assert motivo is None, f"'{nome_completo}' alcanca {motivo}"
                if isinstance(valor, _FOLHAS) or id(valor) in vistos:
                    continue
                vistos.add(id(valor))
                guardados.append(valor)
                proxima.append((valor, nome_completo))
        fila = proxima
    assert len(vistos) > 100  # a varredura andou de verdade


def test_a1_dunders_da_pywebview_nao_servem_para_nada() -> None:
    from jarvis.ui import api_config

    ponte, abertos = _ponte()
    assert _nested(ponte, "abrir_link.__self__") is None
    assert _nested(ponte, "abrir_link.__func__") is None
    assert _nested(ponte, "abrir_link.__func__.__closure__") is None
    assert _nested(ponte, "abrir_link.__closure__.cell_contents") is None
    assert _nested(ponte, "abrir_link.__globals__.get")("os") is None
    assert _nested(ponte, "abrir_link.__globals__.get")("LINKS") is None
    # O ataque do relatorio: trocar LINKS pelos globais da funcao e abrir um .exe.
    globais_antes = dict(vars(api_config))
    _nested(ponte, "abrir_link.__globals__.update")({"LINKS": {"x": r"C:\malware.exe"}})
    _nested(ponte, "abrir_link.__builtins__.update")({"getattr": "x"})
    assert _nested(ponte, "abrir_link")("x") is False
    assert dict(vars(api_config)) == globais_antes
    assert _nested(ponte, "abrir_link")("repositorio") is True  # continua funcionando
    assert abertos == ["https://github.com/mateusmirandaia/jarvis"]


def test_a1_pywebview_enxerga_exatamente_as_funcoes_publicas() -> None:
    """Replica do ``get_functions`` do pywebview: o que vira window.pywebview.api."""
    import inspect

    from jarvis.ui.api_config import METODOS_PUBLICOS

    ponte, _ = _ponte()
    funcoes = {}
    for nome in dir(ponte):
        if nome.startswith("_"):
            continue
        attr = getattr(ponte, nome)
        if inspect.ismethod(attr) or inspect.isfunction(attr):
            funcoes[nome] = list(inspect.getfullargspec(attr).args)[1:]
    assert sorted(funcoes) == sorted(METODOS_PUBLICOS)
    with pytest.raises(AttributeError):
        ponte.nova = 1  # type: ignore[attr-defined]


def test_a1_links_imutaveis_e_so_https_da_lista(monkeypatch: pytest.MonkeyPatch) -> None:
    from jarvis.ui import api_config
    from jarvis.ui.api_config import ApiJs, url_segura

    with pytest.raises(TypeError):
        api_config.LINKS["x"] = "C:\\malware.exe"  # type: ignore[index]
    for ruim in (
        "C:\\malware.exe",
        "file:///C:/x.bat",
        "http://github.com/x",
        "https://evil.example/",
        "https://github.com@evil.example/",
        "https://github.com:444/",
        "https://github.com/\nx",
        None,
    ):
        assert not url_segura(ruim), ruim
    abertos: list[str] = []
    monkeypatch.setattr(api_config, "LINKS", {"x": "file:///C:/Windows/System32/calc.exe"})
    assert ApiJs(abrir_url=lambda u: abertos.append(u) or True).abrir_link("x") is False
    assert abertos == []
    assert api_config._abrir_url("file:///C:/x.bat") is False


def test_a1_orb_html_tem_csp() -> None:
    from jarvis.ui.orb_window import ORB_HTML

    texto = ORB_HTML.read_text(encoding="utf-8")
    achado = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', texto)
    assert achado, "orb.html sem CSP"
    regras = {r.split()[0]: r.split()[1:] for r in achado.group(1).split(";") if r.strip()}
    assert regras["default-src"] == ["'none'"]
    assert regras["connect-src"] == ["'none'"]
    assert regras["img-src"] == ["data:"] and regras["media-src"] == ["data:"]
    assert regras["base-uri"] == ["'none'"] and regras["form-action"] == ["'none'"]
    assert "'unsafe-eval'" in regras["script-src"]  # o pywebview usa eval/new Function
    assert not any("http" in v for valores in regras.values() for v in valores)
    assert texto.index("Content-Security-Policy") < texto.index("<script")


def test_a1_csp_no_chrome_bloqueia_rede_e_deixa_o_pywebview_funcionar(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    chrome = Path("/usr/bin/google-chrome")
    if not chrome.exists():
        pytest.skip("Chrome nao encontrado")
    from jarvis.ui.orb_window import montar_config, montar_html

    arquivo = tmp_path / "orb.html"
    arquivo.write_text(montar_html(montar_config(None)), encoding="utf-8")
    sonda = """
      window.__csp = [];
      document.addEventListener('securitypolicyviolation', e => __csp.push(e.violatedDirective));
      window.__eval = eval('1 + 1');
      window.__fn = new Function('return 3')();
      fetch('https://example.com/x').catch(() => {});
      const im = new Image(); im.src = 'https://example.com/a.png';
      const s = document.createElement('script'); s.src = 'https://example.com/a.js';
      document.head.appendChild(s);
    """
    with sync_api.sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=str(chrome), args=["--no-sandbox"])
        pagina = navegador.new_page()
        pagina.goto(arquivo.as_uri())
        # Como o pywebview: codigo injetado roda como script da propria pagina (CSP vale).
        pagina.evaluate(
            "c => { const s = document.createElement('script'); s.textContent = c;"
            " document.head.appendChild(s); }",
            sonda,
        )
        pagina.wait_for_timeout(500)
        resultado = pagina.evaluate("[window.__eval, window.__fn, window.__csp]")
        navegador.close()
    assert resultado[0] == 2 and resultado[1] == 3  # eval e new Function liberados
    bloqueados = set(resultado[2])
    assert {"connect-src", "img-src", "script-src-elem"} <= bloqueados


# ================================================================== A2 fechar apps
_JANELAS = [
    windows.Window("WINWORD.EXE", "Tese_final.docx - Word", 1),
    windows.Window("chrome.exe", "Banco - Google Chrome", 2),
    windows.Window("Jarvis.exe", "Jarvis", 3),
    windows.Window("sihost.exe", "x", 4),
    windows.Window("msedge.exe", "Notas da Tese - Edge", 5),
    windows.Window("notepad.exe", "lista.txt - Bloco de Notas", 6),
]


@pytest.fixture
def janelas(monkeypatch: pytest.MonkeyPatch) -> tuple[list[int], list[str]]:
    fechadas: list[int] = []
    mortos: list[str] = []
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "list_windows", lambda excl=(): list(_JANELAS))
    monkeypatch.setattr(windows, "close_window", fechadas.append)
    monkeypatch.setattr(windows, "kill_process", lambda p: mortos.append(p) or True)
    return fechadas, mortos


@pytest.mark.parametrize("nome", ["", " ", "e", "ab", " x "])
def test_a2_nome_curto_nao_fecha_nada(janelas, nome: str) -> None:
    fechadas, mortos = janelas
    assert AppTools().close_app(nome) == app_tools.MSG_NOME_CURTO
    assert AppTools().close_app(nome, forcar=True) == app_tools.MSG_NOME_CURTO
    assert fechadas == [] and mortos == []


def test_a2_casa_por_palavra_inteira(janelas) -> None:
    fechadas, _ = janelas
    assert "Nao achei" in AppTools().close_app("ese")  # pedaco de "Tese"
    assert fechadas == []
    AppTools().close_app("chrome")
    assert fechadas == [2]


def test_a2_varios_programas_pergunta_antes(janelas) -> None:
    fechadas, mortos = janelas
    r = AppTools().close_app("tese")  # Word e Edge
    assert "mais de um programa" in r and fechadas == []
    r = AppTools().close_app("tese", forcar=True)
    assert "mais de um programa" in r and mortos == []
    r = AppTools().close_app("navegador", forcar=True)  # chrome + edge
    assert "mais de um programa" in r and mortos == []


def test_a2_forcar_um_programa_so(janelas) -> None:
    _, mortos = janelas
    assert AppTools().close_app("bloco de notas", forcar=True) == "Fechado a forca: notepad.exe"
    assert mortos == ["notepad.exe"]


def test_a2_jarvis_e_sistema_nunca(janelas) -> None:
    fechadas, mortos = janelas
    for nome in ("jarvis", "Jarvis.exe", "sihost"):
        assert "Nao achei" in AppTools().close_app(nome, forcar=True)
    assert fechadas == [] and mortos == []


# ================================================================== A3 abrir apps
@pytest.fixture
def menu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[str]]:
    """Menu Iniciar falso (usuario e todos os usuarios) e Windows simulado."""
    abertos: list[str] = []
    usuario = tmp_path / "Roaming"
    todos = tmp_path / "ProgramData"
    monkeypatch.setenv("APPDATA", str(usuario))
    monkeypatch.setenv("ProgramData", str(todos))
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "open_with_shell", lambda alvo: abertos.append(str(alvo)))
    raiz = todos / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    raiz.mkdir(parents=True)
    (usuario / "Microsoft" / "Windows" / "Start Menu" / "Programs").mkdir(parents=True)
    return raiz, abertos


def _lnk(destino: Path, alvo: str = "", argumentos: str = "", alvo_variavel: str = "") -> Path:
    """Escreve um .lnk minimo (MS-SHLLINK) com caminho local, argumentos e/ou variavel."""
    flags = 0x80  # IsUnicode
    corpo = b""
    if alvo:
        flags |= 0x02
        base = alvo.encode("cp1252") + b"\0"
        volume = struct.pack("<IIII", 0x10, 3, 0, 0x10) + b"\0"
        cab = 0x1C
        vol_off = cab
        base_off = vol_off + len(volume)
        sufixo_off = base_off + len(base)
        tamanho = sufixo_off + 1
        corpo += struct.pack("<7I", tamanho, cab, 1, vol_off, base_off, 0, sufixo_off)
        corpo += volume + base + b"\0"
    if argumentos:
        flags |= 0x20
        corpo += struct.pack("<H", len(argumentos)) + argumentos.encode("utf-16-le")
    extra = b""
    if alvo_variavel:
        ansi = alvo_variavel.encode("cp1252").ljust(260, b"\0")
        uni = alvo_variavel.encode("utf-16-le").ljust(520, b"\0")
        extra = struct.pack("<II", 0x314, 0xA0000001) + ansi + uni
    cabecalho = struct.pack("<I", 0x4C) + b"\x01\x14\x02\x00\x00\x00\x00\x00\xc0" + b"\x00" * 6
    cabecalho += b"\x46" + struct.pack("<I", flags) + b"\x00" * (0x4C - 4 - 16 - 4)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(cabecalho + corpo + extra + b"\0\0\0\0")
    return destino


def test_a3_lnk_de_teste_e_lido_como_o_windows(tmp_path: Path) -> None:
    lnk = _lnk(tmp_path / "a.lnk", r"C:\Apps\Spotify.exe", "--x", r"%windir%\system32\cmd.exe")
    info = app_tools.read_shortcut(lnk)
    assert r"C:\Apps\Spotify.exe" in info.paths and r"%windir%\system32\cmd.exe" in info.paths
    assert info.arguments == "--x"
    ruim = tmp_path / "b.lnk"
    ruim.write_bytes(b"x")
    with pytest.raises(ValueError):
        app_tools.read_shortcut(ruim)


@pytest.mark.parametrize(
    "nome",
    sorted(app_tools.BLOCKED_PROGRAMS)
    + ["CMD.EXE", "Windows PowerShell", "Prompt de Comando", "Editor do Registro", "control"],
)
def test_a3_programas_perigosos_nunca(menu, nome: str) -> None:
    raiz, abertos = menu
    _lnk(raiz / f"{nome}.lnk", r"C:\Windows\System32\notepad.exe")  # mesmo com atalho
    assert AppTools().open_app(nome) == app_tools.MSG_BLOQUEADO
    assert abertos == []


@pytest.mark.parametrize("nome", ["taskmgr", "notepad2", "setup", "atualizador"])
def test_a3_nada_do_path_nem_da_pasta_atual(menu, nome: str) -> None:
    _, abertos = menu
    assert "nao encontrei" in AppTools().open_app(nome)
    assert abertos == []


@pytest.mark.parametrize(
    "nome", [r"C:\Windows\System32\cmd.exe", "Downloads/setup.exe", "file:calc", r"..\x"]
)
def test_a3_nunca_por_caminho(menu, nome: str) -> None:
    _, abertos = menu
    assert AppTools().open_app(nome) == app_tools.MSG_CAMINHO
    assert abertos == []


def test_a3_apps_conhecidos_continuam(menu) -> None:
    _, abertos = menu
    assert AppTools().open_app("Calculadora") == "Calculadora aberto."
    assert AppTools().open_app("bloco de notas") == "bloco de notas aberto."
    assert abertos == ["calc.exe", "notepad.exe"]


def test_a3_abre_atalho_do_menu_iniciar_pelo_nome(menu, tmp_path: Path) -> None:
    raiz, abertos = menu
    lnk_todos = _lnk(raiz / "OBS Studio" / "OBS Studio (64bit).lnk", r"C:\Apps\obs64.exe")
    usuario = tmp_path / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    lnk_usuario = _lnk(usuario / "Discord Inc" / "Discord.lnk", r"C:\Users\x\Discord\Update.exe")
    assert AppTools().open_app("discord") == "Discord aberto."
    assert AppTools().open_app("OBS Studio") == "OBS Studio (64bit) aberto."
    assert abertos == [str(lnk_usuario), str(lnk_todos)]


def test_a3_app_conhecido_que_falha_cai_no_menu(menu, monkeypatch: pytest.MonkeyPatch) -> None:
    raiz, abertos = menu
    lnk = _lnk(raiz / "Spotify.lnk", r"C:\Users\x\AppData\Roaming\Spotify\Spotify.exe")

    def shell(alvo: object) -> None:
        if alvo == "spotify":
            raise OSError("nao achei")
        abertos.append(str(alvo))

    monkeypatch.setattr(windows, "open_with_shell", shell)
    assert AppTools().open_app("spotify") == "Spotify aberto."
    assert abertos == [str(lnk)]


@pytest.mark.parametrize(
    ("arquivo", "alvo", "argumentos", "variavel"),
    [
        ("Windows System/Executar.lnk", "", "", ""),
        ("Windows Tools/Visualizador.lnk", r"C:\Windows\x.exe", "", ""),
        ("Atualizador.lnk", "", "", r"%windir%\system32\cmd.exe"),
        ("Atualizador.lnk", r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "", ""),
        ("Atualizador.lnk", r"C:\Windows\explorer.exe", "cmd /c calc", ""),
        ("Atualizador.lnk", r"C:\Users\x\run.bat", "", ""),
        ("Atualizador.lnk", r"C:\Windows\System32\compmgmt.msc", "", ""),
        ("Atualizador.lnk", r"C:\Windows\System32\mshta.exe", "https://x", ""),
        ("Desinstalar Atualizador.lnk", r"C:\Apps\unins000.exe", "", ""),
    ],
)
def test_a3_atalho_perigoso_e_recusado(
    menu, arquivo: str, alvo: str, argumentos: str, variavel: str
) -> None:
    raiz, abertos = menu
    _lnk(raiz / arquivo, alvo, argumentos, variavel)
    nome = Path(arquivo).stem
    r = AppTools().open_app(nome)
    assert r in (app_tools.MSG_BLOQUEADO,) or "nao encontrei" in r
    assert abertos == []


def test_a3_atalho_ilegivel_e_recusado(menu) -> None:
    raiz, abertos = menu
    (raiz / "Atualizador.lnk").write_bytes(b"nao sou um atalho")
    assert AppTools().open_app("atualizador") == app_tools.MSG_BLOQUEADO
    assert abertos == []


def test_a3_nome_ambiguo_pergunta(menu) -> None:
    raiz, abertos = menu
    _lnk(raiz / "Visual Studio 2022.lnk", r"C:\VS\devenv.exe")
    _lnk(raiz / "Visual Studio Installer.lnk", r"C:\VS\installer.exe")
    assert "mais de um" in AppTools().open_app("visual studio")
    assert abertos == []


# ================================================================== M1 corrida no apagar
def test_m1_outras_acoes_esperam_a_janela(guarda: PathGuard, home: Path, lixeira: list) -> None:
    d = home / "Desktop"
    (d / "lixo.tmp").write_text("descartavel", encoding="utf-8")
    fotos = home / "Documents" / "Fotos da familia"
    fotos.mkdir()
    (fotos / "1.jpg").write_text("foto", encoding="utf-8")
    pronto, liberar = threading.Event(), threading.Event()

    def humano(_t: str, msg: str) -> bool:
        assert "lixo.tmp" in msg
        pronto.set()
        liberar.wait(5)
        return True

    ft = FileTools(guarda, confirm=humano)
    t = threading.Thread(target=lambda: ft.delete_to_trash(str(d / "lixo.tmp")))
    t.start()
    assert pronto.wait(5)
    respostas = [
        ft.move_or_rename(str(d / "lixo.tmp"), str(home / "Downloads")),
        ft.move_or_rename(str(fotos), str(d / "lixo.tmp")),
        ft.copy_item(str(fotos), str(d)),
        ft.create_text_file(str(d / "y.txt"), "y"),
        ft.create_folder(str(d / "nova")),
        ft.delete_to_trash(str(fotos)),
    ]
    assert ft.list_folder("area de trabalho").endswith("lixo.tmp")  # ler continua livre
    liberar.set()
    t.join(5)
    assert all(r == file_tools.MSG_OCUPADO for r in respostas), respostas
    assert lixeira == [str(d / "lixo.tmp")]
    assert (fotos / "1.jpg").exists()


def test_m1_item_trocado_por_fora_nao_e_apagado(
    guarda: PathGuard, home: Path, lixeira: list
) -> None:
    d = home / "Desktop"
    alvo = d / "lixo.tmp"
    alvo.write_text("descartavel", encoding="utf-8")

    def humano_e_troca(_t: str, _m: str) -> bool:
        alvo.unlink()  # outro programa troca o item enquanto a janela esta aberta
        alvo.mkdir()
        (alvo / "importante.docx").write_text("x", encoding="utf-8")
        return True

    r = FileTools(guarda, confirm=humano_e_troca).delete_to_trash(str(alvo))
    assert r == file_tools.MSG_MUDOU
    assert lixeira == []


def test_m1_trava_liberada_depois_de_recusar(guarda: PathGuard, home: Path, lixeira) -> None:
    d = home / "Desktop"
    (d / "a.txt").write_text("x", encoding="utf-8")
    ft = _ft(guarda, resposta=False)
    assert "NAO autorizou" in ft.delete_to_trash(str(d / "a.txt"))
    assert "Movido" in ft.move_or_rename(str(d / "a.txt"), str(d / "b.txt"))


# ================================================================== M2 pastas pessoais
@pytest.mark.parametrize("alvo", ["documentos", "area de trabalho", "downloads", "HOME", "PAI"])
def test_m2_pastas_pessoais_inteiras(
    guarda: PathGuard, home: Path, lixeira: list, alvo: str
) -> None:
    caminho = {"HOME": str(home), "PAI": str(home.parent)}.get(alvo, alvo)
    ft = _ft(guarda)
    assert ft.move_or_rename(caminho, str(home / "Downloads" / "velho")) in (
        file_tools.MSG_PASTA_PESSOAL,
        file_tools.MSG_CONTEM_PROTEGIDO,
        file_tools.MSG_PROTEGIDO,
    )
    assert ft.delete_to_trash(caminho) in (
        file_tools.MSG_PASTA_PESSOAL,
        file_tools.MSG_CONTEM_PROTEGIDO,
    )
    assert (home / "Documents").is_dir() and (home / "Desktop").is_dir()
    assert lixeira == []


def test_m2_subpastas_continuam_livres(guarda: PathGuard, home: Path, lixeira: list) -> None:
    pasta = home / "Documents" / "Contratos"
    pasta.mkdir()
    ft = _ft(guarda)
    assert "Movido" in ft.move_or_rename(str(pasta), str(home / "Desktop" / "Contratos 2025"))
    assert "Lixeira" in ft.delete_to_trash(str(home / "Desktop" / "Contratos 2025"))


# ================================================================== M5 pendrive e rede
@pytest.mark.parametrize(
    "tipo", [windows.DRIVE_REMOVABLE, windows.DRIVE_REMOTE, windows.DRIVE_CDROM, 0, 1, 6]
)
def test_m5_sem_lixeira_nao_apaga(
    guarda: PathGuard, home: Path, lixeira: list, monkeypatch: pytest.MonkeyPatch, tipo: int
) -> None:
    monkeypatch.setattr(windows, "drive_type", lambda _p: tipo)
    perguntas: list[str] = []
    alvo = home / "Desktop" / "a.txt"
    alvo.write_text("x", encoding="utf-8")
    ft = FileTools(guarda, confirm=lambda _t, m: perguntas.append(m) or True)
    assert ft.delete_to_trash(str(alvo)) == file_tools.MSG_SEM_LIXEIRA
    assert perguntas == [] and lixeira == [] and alvo.exists()


def test_m5_has_recycle_bin(monkeypatch: pytest.MonkeyPatch) -> None:
    assert windows.has_recycle_bin(r"\\servidor\pasta\a.txt") is False
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "drive_type", lambda _p: windows.DRIVE_FIXED)
    assert windows.has_recycle_bin("C:\\a.txt") is True

    def quebra(_p: object) -> int:
        raise OSError

    monkeypatch.setattr(windows, "drive_type", quebra)
    assert windows.has_recycle_bin("C:\\a.txt") is False


# ================================================================== B1 copia grande / tempo
def test_b1_copia_grande_recusada(
    guarda: PathGuard, home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(file_tools, "COPY_MAX_BYTES", 10)
    d = home / "Desktop"
    (d / "video.mp4").write_bytes(b"x" * 11)
    (d / "pasta").mkdir()
    for i in range(3):
        (d / "pasta" / f"{i}.jpg").write_bytes(b"x" * 5)
    ft = _ft(guarda)
    assert ft.copy_item(str(d / "video.mp4"), "documentos") == file_tools.MSG_GRANDE
    assert ft.copy_item(str(d / "pasta"), "documentos") == file_tools.MSG_GRANDE
    assert "Movido" in ft.move_or_rename(str(d / "video.mp4"), "documentos")  # mesmo disco


def test_b1_tempo_esgotado_manda_conferir() -> None:
    from jarvis.errors import friendly_message

    texto = friendly_message(TimeoutError())
    assert "pode ter terminado" in texto and "confira antes de repetir" in texto


# ================================================================== B2 / B3 empacotamento
def test_b2_build_usa_versoes_fixas() -> None:
    req = (RAIZ / "packaging" / "requirements-build.txt").read_text(encoding="utf-8")
    linhas = [ln.strip() for ln in req.splitlines() if ln.strip() and not ln.startswith("#")]
    assert linhas and all(re.fullmatch(r"[A-Za-z0-9_.\-]+==[0-9][\w.]*", ln) for ln in linhas)
    nomes = {ln.split("==")[0].lower().replace("_", "-") for ln in linhas}
    for dep in ("google-genai", "pywebview", "pyinstaller", "pyaudio", "send2trash", "httpx"):
        assert dep in nomes
    build = (RAIZ / "packaging" / "build.ps1").read_text(encoding="utf-8-sig")
    assert "requirements-build.txt" in build and "--no-deps" in build
    assert "pip check" in build
    assert "pip install $Raiz pyinstaller" not in build


def test_b3_instalador_recusa_outra_pasta() -> None:
    iss = (RAIZ / "packaging" / "jarvis.iss").read_text(encoding="utf-8-sig")
    codigo = iss[iss.index("[Code]") :]
    assert "function PrepareToInstall" in codigo and "function InitializeUninstall" in codigo
    assert "{localappdata}\\Programs\\Jarvis" in codigo
    assert codigo.count("PastaDoAppValida()") >= 3


# ================================================================== B4 log
def test_b4_log_apaga_o_valor_exato_das_chaves(tmp_path: Path) -> None:
    from jarvis.config import Settings
    from jarvis.logging_setup import redigir, registrar_segredos
    from jarvis.tools import ToolRegistry

    chave = "chave-formato-novo-0123456789"
    el = "xi_formato_diferente_abcdef"
    assert chave in redigir(f"falhou com {chave}")
    ToolRegistry(
        Settings(api_key=chave, elevenlabs_api_key=el, project_root=tmp_path), confirm=None
    )
    texto = redigir(json.dumps({"erro": f"x {chave} y", "el": el}))
    assert chave not in texto and el not in texto
    registrar_segredos("", "curta", None, 123)  # ignorados, sem erro
    assert redigir("curta") == "curta"
