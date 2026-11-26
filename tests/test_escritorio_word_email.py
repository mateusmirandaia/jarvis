"""Testes do write_word_document e do draft_email (rodada 0.9, escritorio).

O "abridor" (os.startfile no Windows) e injetado: anota o que seria aberto e nada abre de
verdade. Nada e enviado: o teste troca o SMTP por uma bomba que falha se for chamada.
"""

from __future__ import annotations

import email
import smtplib
import socket
from datetime import datetime
from email import policy
from pathlib import Path
from urllib.parse import unquote

import docx
import pytest

from jarvis.config import Settings
from jarvis.os_integration import windows
from jarvis.tools import ToolRegistry, file_tools, office_tools
from jarvis.tools.file_tools import FileTools
from jarvis.tools.office_tools import MAILTO_MAX_CHARS, MSG_PRONTO, OfficeTools
from jarvis.tools.security import PathGuard

RAIZ = Path(__file__).resolve().parents[1]
AGORA = datetime(2026, 11, 26, 9, 15, 30)


class Abridor:
    """Finge o os.startfile: anota o alvo; ``falha`` simula "sem programa associado"."""

    def __init__(self, falha_em: tuple[str, ...] = ()) -> None:
        self.abertos: list[str] = []
        self.falha_em = falha_em

    def __call__(self, alvo: str | Path) -> bool:
        texto = str(alvo)
        if any(texto.startswith(p) or texto.endswith(p) for p in self.falha_em):
            raise OSError("nenhum programa associado")
        self.abertos.append(texto)
        return True


@pytest.fixture(autouse=True)
def nada_e_enviado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Qualquer tentativa de enviar (SMTP ou conexao de rede) quebra o teste."""

    def bomba(*_a: object, **_k: object) -> None:
        raise AssertionError("o Jarvis tentou ENVIAR algo")

    monkeypatch.setattr(smtplib, "SMTP", bomba)
    monkeypatch.setattr(smtplib, "SMTP_SSL", bomba)
    monkeypatch.setattr(socket, "create_connection", bomba)


@pytest.fixture
def chaves(tmp_path: Path) -> Path:
    pasta = tmp_path / "AppData_real" / "Jarvis"
    pasta.mkdir(parents=True)
    return pasta


@pytest.fixture
def guarda(project_root: Path, home: Path, chaves: Path) -> PathGuard:
    return PathGuard(project_root=project_root, home=home, extra_protected=[chaves])


@pytest.fixture
def docs(home: Path) -> Path:
    return home / "Documents"


@pytest.fixture
def abridor() -> Abridor:
    return Abridor()


@pytest.fixture
def ft(guarda: PathGuard, abridor: Abridor) -> FileTools:
    return FileTools(guarda, confirm=lambda _t, _m: False, abrir=abridor)


@pytest.fixture
def ot(guarda: PathGuard, abridor: Abridor) -> OfficeTools:
    return OfficeTools(guarda, abrir=abridor, agora=lambda: AGORA)


def _paragrafos(caminho: Path) -> list[tuple[str, str]]:
    return [(p.style.name, p.text) for p in docx.Document(str(caminho)).paragraphs]


# ================================================================== Word
def test_cria_docx_em_documentos_por_padrao(ft: FileTools, docs: Path, abridor: Abridor) -> None:
    r = ft.write_word_document("ata da reunião", "Primeiro parágrafo.\n\nSegundo.", "Ata")
    alvo = docs / "ata da reunião.docx"
    assert r == f"Documento do Word criado e aberto: {alvo}"
    assert _paragrafos(alvo) == [
        ("Heading 1", "Ata"),
        ("Normal", "Primeiro parágrafo."),
        ("Normal", "Segundo."),
    ]
    assert abridor.abertos == [str(alvo)]


def test_sem_caminho_usa_o_titulo_como_nome(ft: FileTools, docs: Path) -> None:
    ft.write_word_document("", "texto", "Relatório: março/2026?")
    assert (docs / "Relatório março 2026.docx").is_file()
    ft.write_word_document("documentos", "texto", "")
    assert (docs / "Documento do Jarvis.docx").is_file()


def test_linhas_simples_ficam_no_mesmo_paragrafo(ft: FileTools, docs: Path) -> None:
    ft.write_word_document("carta", "Prezado João,\nobrigado.\n\n\n\nAbraços", "")
    paragrafos = _paragrafos(docs / "carta.docx")
    assert [t for _s, t in paragrafos] == ["Prezado João,\nobrigado.", "Abraços"]


def test_nunca_sobrescreve(ft: FileTools, docs: Path) -> None:
    original = docs / "proposta.docx"
    original.write_bytes(b"conteudo do senhor")
    r1 = ft.write_word_document(str(original), "nova versão", "")
    r2 = ft.write_word_document("documentos\\proposta", "terceira", "")
    assert original.read_bytes() == b"conteudo do senhor"
    assert r1.endswith("proposta (2).docx") and r2.endswith("proposta (3).docx")
    assert _paragrafos(docs / "proposta (3).docx")[0][1] == "terceira"


def test_extensao_vira_docx(ft: FileTools, docs: Path) -> None:
    ft.write_word_document("notas.txt", "a", "")
    ft.write_word_document("relatorio v1.2", "b", "")
    ft.write_word_document("macro.docm", "c", "")
    assert (docs / "notas.docx").is_file()
    assert (docs / "relatorio v1.2.docx").is_file()
    assert (docs / "macro.docx").is_file() and not (docs / "macro.docm").exists()


def test_pasta_inexistente_nao_e_criada(ft: FileTools, docs: Path) -> None:
    r = ft.write_word_document(str(docs / "Clientes" / "x.docx"), "a", "")
    assert r.startswith("A pasta ") and "não existe" in r
    assert not (docs / "Clientes").exists()


def test_area_de_trabalho_e_caminho_completo(ft: FileTools, home: Path, tmp_path: Path) -> None:
    ft.write_word_document("area de trabalho\\lembrete", "a", "")
    assert (home / "Desktop" / "lembrete.docx").is_file()
    livre = tmp_path / "livre"
    livre.mkdir()
    ft.write_word_document(str(livre / "x.docx"), "a", "")
    assert (livre / "x.docx").is_file()


def test_word_pasta_protegida_rede_e_segredo(
    ft: FileTools, project_root: Path, chaves: Path, docs: Path
) -> None:
    assert "protegida" in ft.write_word_document(str(project_root / "a.docx"), "a", "")
    assert "protegida" in ft.write_word_document(str(chaves / "a"), "a", "")
    assert "rede" in ft.write_word_document("\\\\servidor\\pasta\\a.docx", "a", "")
    assert "nome de arquivo" in ft.write_word_document(str(docs / "a.docx:x"), "a", "")
    assert not list(project_root.glob("*.docx")) and not list(chaves.iterdir())


def test_word_texto_vazio_ou_gigante(ft: FileTools, docs: Path) -> None:
    assert ft.write_word_document("x", "  \n ", "") == "Senhor, diga o texto do documento."
    assert "grande demais" in ft.write_word_document("x", "a" * 200_001, "")
    assert not list(docs.glob("*.docx"))


def test_word_caracteres_de_controle_nao_quebram(ft: FileTools, docs: Path) -> None:
    r = ft.write_word_document("ditado", "texto\x00 com\x07 lixo\x1b", "Tí\x0btulo")
    assert "criado" in r
    assert _paragrafos(docs / "ditado.docx") == [
        ("Heading 1", "Título"),
        ("Normal", "texto com lixo"),
    ]


def test_word_sem_autor_python_docx(ft: FileTools, docs: Path) -> None:
    ft.write_word_document("x", "a", "Meu título")
    props = docx.Document(str(docs / "x.docx")).core_properties
    assert props.author == "" and props.title == "Meu título"


def test_word_fora_do_windows_so_cria(
    guarda: PathGuard, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(windows, "IS_WINDOWS", False)
    r = FileTools(guarda).write_word_document("x", "a", "")
    assert r == f"Documento do Word criado: {docs / 'x.docx'}"


def test_word_no_windows_usa_o_shell(
    guarda: PathGuard, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    abertos: list[str] = []
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "open_with_shell", lambda alvo: abertos.append(str(alvo)))
    FileTools(guarda).write_word_document("x", "a", "")
    assert abertos == [str(docs / "x.docx")]


def test_word_criado_mas_nao_abriu(guarda: PathGuard, docs: Path) -> None:
    r = FileTools(guarda, abrir=Abridor(falha_em=(".docx",))).write_word_document("x", "a", "")
    assert "não consegui abrir" in r and (docs / "x.docx").is_file()


def test_word_espera_a_janela_de_apagar(ft: FileTools, docs: Path) -> None:
    ft._confirmando.set()
    try:
        assert ft.write_word_document("x", "a", "") == file_tools.MSG_OCUPADO
    finally:
        ft._confirmando.clear()
    assert not (docs / "x.docx").exists()


# ================================================================== e-mail
def test_mailto_curto(ot: OfficeTools, abridor: Abridor, docs: Path) -> None:
    r = ot.draft_email("ana@empresa.com; joao@empresa.com.br", "Relatório", "Olá!\nSegue.")
    assert r == MSG_PRONTO == "Deixei o e-mail pronto para o senhor revisar e enviar."
    (link,) = abridor.abertos
    assert link.startswith("mailto:ana@empresa.com,joao@empresa.com.br?subject=")
    assert "Relat%C3%B3rio" in link and "body=Ol%C3%A1%21%0D%0ASegue." in link
    assert unquote(link.split("body=")[1]) == "Olá!\r\nSegue."
    assert not (docs / "Jarvis").exists()  # mailto nao cria arquivo


def test_mailto_sem_destinatario(ot: OfficeTools, abridor: Abridor) -> None:
    assert ot.draft_email("", "Oi", "") == MSG_PRONTO
    assert abridor.abertos == ["mailto:?subject=Oi"]


def test_mailto_caracteres_especiais_nao_viram_parametros(
    ot: OfficeTools, abridor: Abridor
) -> None:
    ot.draft_email("ana@empresa.com", "a&cc=hacker@mal.com", "x&bcc=hacker@mal.com?=#%")
    (link,) = abridor.abertos
    assert link.count("&") == 1  # so o que separa subject de body
    assert "%26cc%3Dhacker%40mal.com" in link and "%26bcc%3Dhacker" in link


def test_email_longo_vira_eml_com_x_unsent(ot: OfficeTools, abridor: Abridor, docs: Path) -> None:
    corpo = "Prezada Ana,\n\n" + "Segue o relatório completo do mês. " * 80 + "\n\nAtenciosamente"
    r = ot.draft_email("ana@empresa.com", "Relatório de novembro", corpo)
    pasta = docs / "Jarvis" / "Rascunhos"
    alvo = pasta / "E-mail 2026-11-26 09-15-30.eml"
    assert r == f"{MSG_PRONTO} O rascunho ficou em {alvo}."
    assert abridor.abertos == [str(alvo)]
    bruto = alvo.read_bytes()
    assert b"\r\n" in bruto
    msg = email.message_from_bytes(bruto, policy=policy.default)
    assert msg["X-Unsent"] == "1"
    assert msg["To"] == "ana@empresa.com"
    assert msg["Subject"] == "Relatório de novembro"
    assert msg.get_content().replace("\r\n", "\n").strip() == corpo.strip()


def test_limite_do_mailto(ot: OfficeTools, abridor: Abridor, docs: Path) -> None:
    ot.draft_email("a@b.com", "x", "y" * (MAILTO_MAX_CHARS - 40))
    assert abridor.abertos[-1].startswith("mailto:")
    ot.draft_email("a@b.com", "x", "y" * MAILTO_MAX_CHARS)
    assert abridor.abertos[-1].endswith(".eml")


def test_eml_nunca_sobrescreve(ot: OfficeTools, docs: Path) -> None:
    for _ in range(3):
        ot.draft_email("", "x", "z" * 3000)
    nomes = sorted(p.name for p in (docs / "Jarvis" / "Rascunhos").iterdir())
    assert nomes == [
        "E-mail 2026-11-26 09-15-30 (2).eml",
        "E-mail 2026-11-26 09-15-30 (3).eml",
        "E-mail 2026-11-26 09-15-30.eml",
    ]


def test_sem_programa_para_mailto_cai_no_eml(guarda: PathGuard, docs: Path) -> None:
    abridor = Abridor(falha_em=("mailto:",))
    r = OfficeTools(guarda, abrir=abridor, agora=lambda: AGORA).draft_email("a@b.com", "x", "y")
    assert r.startswith(MSG_PRONTO) and "rascunho" in r
    assert abridor.abertos[0].endswith(".eml")


def test_sem_programa_nenhum(guarda: PathGuard, docs: Path) -> None:
    abridor = Abridor(falha_em=("mailto:", ".eml"))
    r = OfficeTools(guarda, abrir=abridor, agora=lambda: AGORA).draft_email("a@b.com", "x", "y")
    assert "não achei um programa de e-mail" in r
    assert list((docs / "Jarvis" / "Rascunhos").glob("*.eml"))


@pytest.mark.parametrize(
    "para",
    [
        "ana",
        "ana@",
        "ana@empresa",
        "ana @empresa.com",
        "ana@empresa.com?cc=x@y.com",
        "ana%40x@empresa.com",
        "Ana <ana@empresa.com>",
        "ana@empresa..com",
        ".ana@empresa.com",
        "javascript:alert(1)@x.com",
    ],
)
def test_destinatario_invalido(ot: OfficeTools, abridor: Abridor, para: str) -> None:
    r = ot.draft_email(para, "x", "y")
    assert "não parece válido" in r
    assert abridor.abertos == []


@pytest.mark.parametrize(
    ("para", "assunto"),
    [
        ("ana@empresa.com\r\nBcc: hacker@mal.com", "x"),
        ("ana@empresa.com\nCc: hacker@mal.com", "x"),
        ("ana@empresa.com", "Oi\r\nBcc: hacker@mal.com"),
        ("ana@empresa.com", "Oi\nX-Header: 1"),
        ("ana@empresa.com", "Oi Bcc: hacker@mal.com"),
        ("ana@empresa.com", "Oi\x85Bcc: hacker@mal.com"),
        ("ana@empresa.com", "Oi\x00"),
    ],
)
def test_injecao_de_cabecalho(
    ot: OfficeTools, abridor: Abridor, docs: Path, para: str, assunto: str
) -> None:
    r = ot.draft_email(para, assunto, "corpo " * 1000)
    assert r == "Senhor, o destinatário e o assunto não podem ter quebra de linha."
    assert abridor.abertos == []
    assert not (docs / "Jarvis").exists()


def test_corpo_com_bcc_fica_no_corpo(ot: OfficeTools, docs: Path) -> None:
    ot.draft_email("ana@empresa.com", "x", "Bcc: hacker@mal.com\r\n\r\n" + "texto " * 400)
    (alvo,) = (docs / "Jarvis" / "Rascunhos").iterdir()
    msg = email.message_from_bytes(alvo.read_bytes(), policy=policy.default)
    assert msg["Bcc"] is None and msg["To"] == "ana@empresa.com"


def test_email_limites(ot: OfficeTools, abridor: Abridor) -> None:
    muitos = ";".join(f"p{n}@empresa.com" for n in range(21))
    assert "demais" in ot.draft_email(muitos, "x", "y")
    assert "comprido" in ot.draft_email("", "a" * 251, "y")
    assert "grande demais" in ot.draft_email("", "x", "y" * 100_001)
    assert ot.draft_email("", " ", "\n") == "Senhor, diga o assunto ou o texto do e-mail."
    assert abridor.abertos == []


def test_email_fora_do_windows(guarda: PathGuard, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows, "IS_WINDOWS", False)
    assert (
        OfficeTools(guarda).draft_email("a@b.com", "x", "y") == "Esta ação só funciona no Windows."
    )


def test_email_no_windows_usa_o_shell(guarda: PathGuard, monkeypatch: pytest.MonkeyPatch) -> None:
    abertos: list[str] = []
    monkeypatch.setattr(windows, "IS_WINDOWS", True)
    monkeypatch.setattr(windows, "open_with_shell", lambda alvo: abertos.append(str(alvo)))
    assert OfficeTools(guarda).draft_email("a@b.com", "x", "y") == MSG_PRONTO
    assert abertos == ["mailto:a@b.com?subject=x&body=y"]


def test_codigo_nunca_envia() -> None:
    """Nada de SMTP, Outlook por automacao (COM/pywin32) ou bibliotecas de rede."""
    fonte = (RAIZ / "src" / "jarvis" / "tools" / "office_tools.py").read_text(encoding="utf-8")
    codigo = "\n".join(
        linha for linha in fonte.splitlines() if linha.strip().startswith(("import", "from"))
    )
    for proibido in ("smtplib", "win32com", "pywin32", "comtypes", "httpx", "socket", "requests"):
        assert proibido not in codigo, proibido
    assert "send(" not in fonte and "sendmail" not in fonte
    assert not hasattr(office_tools, "smtplib")


# ================================================================== registro e persona
def test_registro_tem_as_ferramentas_novas_embrulhadas(tmp_path: Path) -> None:
    registro = ToolRegistry(
        Settings(api_key="x", project_root=tmp_path),
        confirm=lambda t, m: False,
        permissoes_atuais=_tudo_liberado,
    )
    for nome in ("read_file", "write_word_document", "draft_email"):
        func = registro.get(nome)
        assert func is not None and func.__name__ == nome
        assert getattr(func, "__wrapped__", None) is not None  # safe_tool
        assert func.__doc__ and "Args:" in func.__doc__
    assert registro.names[-3:] == ["read_file", "write_word_document", "draft_email"]


def test_registro_assinaturas_do_contrato(tmp_path: Path) -> None:
    import inspect

    registro = ToolRegistry(
        Settings(api_key="x", project_root=tmp_path),
        confirm=lambda t, m: False,
        permissoes_atuais=_tudo_liberado,
    )
    sig = inspect.signature(registro.get("write_word_document"))
    assert list(sig.parameters) == ["caminho", "texto", "titulo"]
    assert sig.parameters["titulo"].default == ""
    assert list(inspect.signature(registro.get("read_file")).parameters) == ["caminho"]
    assert list(inspect.signature(registro.get("draft_email")).parameters) == [
        "para",
        "assunto",
        "corpo",
    ]


def test_registro_erro_inesperado_no_email_vira_frase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_a: object) -> str:
        raise RuntimeError("falha interna")

    monkeypatch.setattr(office_tools, "montar_mailto", explode)
    registro = ToolRegistry(
        Settings(api_key="x", project_root=tmp_path),
        confirm=lambda t, m: False,
        permissoes_atuais=_tudo_liberado,
    )
    r = registro.get("draft_email")("a@b.com", "x", "y")
    assert r.startswith("ERRO:") and "falha interna" not in r


def test_persona_explica_o_escritorio() -> None:
    from jarvis.persona import build_system_prompt

    texto = build_system_prompt({"documentos": Path("/casa/Documents")}, [])
    for trecho in ("find_file", "read_file", "write_word_document", "draft_email"):
        assert trecho in texto
    assert "NUNCA envia" in texto and "Nunca diga que enviou" in texto
    assert "So le PDF com texto" in texto


def _tudo_liberado() -> dict[str, object]:
    return {
        "arquivos": "ler_gravar_excluir",
        "apps": True,
        "internet": True,
        "email": True,
        "outros_drives": True,
    }
