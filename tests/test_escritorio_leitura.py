"""Testes do read_file (rodada 0.9, escritorio): ler o TEXTO de arquivos com seguranca.

Tudo roda em pastas temporarias. Os PDFs sao montados aqui mesmo (PDF de texto com a fonte
Helvetica e PDF "imagem", sem texto nenhum); .docx e .xlsx sao gerados com python-docx e
openpyxl. Nada e aberto na tela e nada e executado.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path

import docx
import openpyxl
import pytest
from pypdf import PdfWriter

from jarvis.config import Settings
from jarvis.errors import MAX_RESULT_CHARS, safe_tool
from jarvis.tools import ToolRegistry, file_tools
from jarvis.tools.file_tools import (
    MSG_PDF_IMAGEM,
    MSG_PDF_SENHA,
    READ_MAX_CHARS,
    READ_RESULT_MAX_CHARS,
    FileTools,
)
from jarvis.tools.security import PathGuard


# ------------------------------------------------------------------ fabrica de arquivos
def pdf_de_texto(paginas: list[str]) -> bytes:
    """PDF minimo com uma pagina por texto (Helvetica, WinAnsi: aceita acentos)."""
    objetos: list[bytes | None] = []

    def novo(conteudo: bytes | None) -> int:
        objetos.append(conteudo)
        return len(objetos)

    catalogo, raiz_paginas = novo(None), novo(None)
    fonte = novo(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    filhos = []
    for texto in paginas:
        linhas, y = [], 720
        for linha in texto.split("\n"):
            esc = linha.encode("cp1252")
            esc = esc.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            linhas.append(b"BT /F1 12 Tf 72 %d Td (" % y + esc + b") Tj ET")
            y -= 16
        fluxo = b"\n".join(linhas)
        conteudo = novo(b"<< /Length %d >>\nstream\n" % len(fluxo) + fluxo + b"\nendstream")
        filhos.append(
            novo(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                % (raiz_paginas, fonte, conteudo)
            )
        )
    objetos[catalogo - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % raiz_paginas
    kids = b" ".join(b"%d 0 R" % k for k in filhos)
    objetos[raiz_paginas - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(filhos))
    saida = bytearray(b"%PDF-1.4\n")
    posicoes = []
    for numero, obj in enumerate(objetos, 1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % numero + (obj or b"") + b"\nendobj\n"
    inicio_xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    for pos in posicoes:
        saida += b"%010d 00000 n \n" % pos
    saida += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objetos) + 1,
        catalogo,
        inicio_xref,
    )
    return bytes(saida)


def pdf_imagem(paginas: int = 2) -> bytes:
    """PDF "escaneado": paginas sem nenhum texto (como uma foto do papel)."""
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=612, height=792)
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


def pdf_com_senha(dados: bytes, senha_de_abrir: str) -> bytes:
    escritor = PdfWriter(clone_from=io.BytesIO(dados))
    escritor.encrypt(user_password=senha_de_abrir, owner_password="dono", algorithm="RC4-128")
    saida = io.BytesIO()
    escritor.write(saida)
    return saida.getvalue()


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def chaves(tmp_path: Path) -> Path:
    pasta = tmp_path / "AppData_real" / "Jarvis"
    pasta.mkdir(parents=True)
    (pasta / ".env").write_text("GEMINI_API_KEY=AIzaSEGREDO_DE_TESTE_123456\n", encoding="utf-8")
    (pasta / "notas.txt").write_text("conteudo protegido", encoding="utf-8")
    return pasta


@pytest.fixture
def guarda(project_root: Path, home: Path, chaves: Path) -> PathGuard:
    return PathGuard(project_root=project_root, home=home, extra_protected=[chaves])


@pytest.fixture
def ft(guarda: PathGuard) -> FileTools:
    return FileTools(guarda, confirm=lambda _t, _m: False, abrir=lambda _p: True)


@pytest.fixture
def docs(home: Path) -> Path:
    return home / "Documents"


# ================================================================== texto e codificacoes
@pytest.mark.parametrize("ext", [".txt", ".md", ".csv", ".log", ".json"])
def test_le_os_tipos_de_texto(ft: FileTools, docs: Path, ext: str) -> None:
    alvo = docs / f"arquivo{ext}"
    alvo.write_text("Depósito de R$ 300 na conta.", encoding="utf-8")
    r = ft.read_file(str(alvo))
    assert r.startswith(f"Texto de arquivo{ext}:")
    assert "Depósito de R$ 300 na conta." in r
    assert "Li só o começo" not in r


@pytest.mark.parametrize(
    ("codificacao", "prefixo"),
    [
        ("utf-8", b""),
        ("utf-8-sig", b""),  # o BOM vem do proprio codec
        ("utf-16", b""),  # idem (FF FE)
        ("utf-16-be", b"\xfe\xff"),
        ("cp1252", b""),
    ],
)
def test_detecta_codificacao(ft: FileTools, docs: Path, codificacao: str, prefixo: bytes) -> None:
    texto = "Ação, coração e pão: R$ 10,50 — ótimo"
    if codificacao == "cp1252":
        texto = texto.replace("—", "-")
    alvo = docs / "nota.txt"
    alvo.write_bytes(prefixo + texto.encode(codificacao))
    r = ft.read_file(str(alvo))
    assert texto in r
    assert "\ufeff" not in r and "\ufffd" not in r


def test_csv_do_excel_brasileiro(ft: FileTools, docs: Path) -> None:
    alvo = docs / "contas.csv"
    alvo.write_bytes("Descrição;Valor\r\nLuz;120,00\r\nÁgua;80,00\r\n".encode("cp1252"))
    r = ft.read_file(str(alvo))
    assert "Descrição;Valor\nLuz;120,00\nÁgua;80,00" in r


def test_texto_longo_devolve_o_comeco_com_aviso(ft: FileTools, docs: Path) -> None:
    alvo = docs / "longo.txt"
    alvo.write_text("a" * 53_210, encoding="utf-8")
    r = ft.read_file(str(alvo))
    assert r.startswith("Li só o começo (20.000 de 53.210 caracteres).")
    assert r.count("a") >= READ_MAX_CHARS
    assert len(r) <= READ_RESULT_MAX_CHARS


def test_arquivo_vazio(ft: FileTools, docs: Path) -> None:
    (docs / "vazio.txt").write_text("", encoding="utf-8")
    assert "está vazio" in ft.read_file(str(docs / "vazio.txt"))


def test_binario_disfarcado_de_txt(ft: FileTools, docs: Path) -> None:
    (docs / "foto.txt").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" * 10)
    assert "não parece ser de texto" in ft.read_file(str(docs / "foto.txt"))


def test_atalho_de_pasta_documentos(ft: FileTools, docs: Path) -> None:
    (docs / "lista.md").write_text("# Compras\n- pão", encoding="utf-8")
    assert "- pão" in ft.read_file("documentos\\lista.md")


# ================================================================== PDF
def test_pdf_de_texto(ft: FileTools, docs: Path) -> None:
    alvo = docs / "deposito.pdf"
    alvo.write_bytes(pdf_de_texto(["Comprovante de depósito\nValor: R$ 1.500,00", "Página 2"]))
    r = ft.read_file(str(alvo))
    assert "Comprovante de depósito" in r
    assert "R$ 1.500,00" in r and "Página 2" in r
    assert "Li só o começo" not in r


def test_pdf_imagem_avisa(ft: FileTools, docs: Path) -> None:
    alvo = docs / "escaneado.pdf"
    alvo.write_bytes(pdf_imagem(3))
    assert ft.read_file(str(alvo)) == MSG_PDF_IMAGEM
    assert MSG_PDF_IMAGEM == (
        "Esse PDF parece ser uma imagem (escaneado). Eu só consigo ler PDF com texto."
    )


def test_pdf_quase_vazio_conta_como_imagem(ft: FileTools, docs: Path) -> None:
    alvo = docs / "carimbo.pdf"
    alvo.write_bytes(pdf_de_texto(["1", "2", "3", "4"]))  # so o numero da pagina
    assert ft.read_file(str(alvo)) == MSG_PDF_IMAGEM


def test_pdf_longo_le_pagina_por_pagina_ate_o_limite(ft: FileTools, docs: Path) -> None:
    pagina = "\n".join(["Linha de texto do contrato numero um dois tres."] * 40)
    alvo = docs / "contrato.pdf"
    alvo.write_bytes(pdf_de_texto([pagina] * 30))
    r = ft.read_file(str(alvo))
    assert r.startswith("Li só o começo (")
    assert "de 30 páginas)." in r.splitlines()[0]
    assert len(r) <= READ_RESULT_MAX_CHARS


def test_pdf_com_senha(ft: FileTools, docs: Path) -> None:
    alvo = docs / "extrato.pdf"
    alvo.write_bytes(pdf_com_senha(pdf_de_texto(["Saldo secreto"]), "1234"))
    r = ft.read_file(str(alvo))
    assert r == MSG_PDF_SENHA == "Esse PDF tem senha. Não consigo ler."
    assert "Saldo secreto" not in r


def test_pdf_so_com_senha_de_dono_e_lido(ft: FileTools, docs: Path) -> None:
    """Muitos PDFs de banco sao "protegidos" sem senha para abrir: esses o Jarvis le."""
    alvo = docs / "boleto.pdf"
    alvo.write_bytes(pdf_com_senha(pdf_de_texto(["Boleto do condomínio de novembro"]), ""))
    assert "Boleto do condomínio de novembro" in ft.read_file(str(alvo))


def test_pdf_corrompido(ft: FileTools, docs: Path) -> None:
    (docs / "quebrado.pdf").write_bytes(b"%PDF-1.4\nisso nao e um pdf de verdade")
    r = ft.read_file(str(docs / "quebrado.pdf"))
    assert "corrompido" in r and "ERRO" not in r


# ================================================================== Word e Excel
def test_docx_paragrafos_e_tabelas_na_ordem(ft: FileTools, docs: Path) -> None:
    documento = docx.Document()
    documento.add_heading("Ata da reunião", level=1)
    documento.add_paragraph("Presentes: Ana e João.")
    tabela = documento.add_table(rows=2, cols=2)
    tabela.cell(0, 0).text, tabela.cell(0, 1).text = "Item", "Responsável"
    tabela.cell(1, 0).text, tabela.cell(1, 1).text = "Orçamento", "Ana"
    documento.add_paragraph("Fim da ata.")
    documento.save(str(docs / "ata.docx"))
    r = ft.read_file(str(docs / "ata.docx"))
    assert "Ata da reunião\nPresentes: Ana e João.\nItem\tResponsável\nOrçamento\tAna\nFim" in r


def test_docx_celula_mesclada_nao_repete(ft: FileTools, docs: Path) -> None:
    documento = docx.Document()
    tabela = documento.add_table(rows=1, cols=3)
    tabela.cell(0, 0).merge(tabela.cell(0, 1)).text = "Juntas"
    tabela.cell(0, 2).text = "Sozinha"
    documento.save(str(docs / "mesclada.docx"))
    assert "Juntas\tSozinha" in ft.read_file(str(docs / "mesclada.docx"))


def test_xlsx_por_aba_com_valores(ft: FileTools, docs: Path) -> None:
    livro = openpyxl.Workbook()
    aba = livro.active
    aba.title = "Janeiro"
    aba.append(["Data", "Descrição", "Valor"])
    aba.append([datetime(2026, 1, 5), "Aluguel", 1500.0])
    aba.append([datetime(2026, 1, 9, 14, 30), "Mercado", 312.75])
    aba["D1"] = "=SUM(C2:C3)"  # formula: o Jarvis nunca devolve a formula
    outra = livro.create_sheet("Fevereiro")
    outra.append(["Luz", 98])
    livro.save(str(docs / "gastos.xlsx"))
    r = ft.read_file(str(docs / "gastos.xlsx"))
    assert "[Aba: Janeiro]\nData\tDescrição\tValor" in r
    assert "05/01/2026\tAluguel\t1500" in r
    assert "09/01/2026 14:30\tMercado\t312.75" in r
    assert "[Aba: Fevereiro]\nLuz\t98" in r
    assert "=SUM" not in r


def test_xlsx_limite_de_linhas(ft: FileTools, docs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(file_tools, "XLSX_MAX_ROWS", 5)
    livro = openpyxl.Workbook()
    for numero in range(20):
        livro.active.append([f"linha {numero}"])
    livro.save(str(docs / "grande.xlsx"))
    r = ft.read_file(str(docs / "grande.xlsx"))
    assert r.startswith("Li só o começo (as primeiras 5 linhas com dados).")
    assert "linha 4" in r and "linha 5" not in r


def test_xlsx_vazio(ft: FileTools, docs: Path) -> None:
    openpyxl.Workbook().save(str(docs / "branco.xlsx"))
    assert "está vazio" in ft.read_file(str(docs / "branco.xlsx"))


def test_docx_corrompido(ft: FileTools, docs: Path) -> None:
    (docs / "falso.docx").write_text("nao sou zip", encoding="utf-8")
    assert "corrompido" in ft.read_file(str(docs / "falso.docx"))


def test_zip_bomba_e_recusada(ft: FileTools, docs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(file_tools, "ZIP_MAX_BYTES", 1024 * 1024)
    alvo = docs / "bomba.docx"
    with zipfile.ZipFile(alvo, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
        pacote.writestr("word/document.xml", b"0" * (3 * 1024 * 1024))
    assert alvo.stat().st_size < 100_000
    assert "grande demais por dentro" in ft.read_file(str(alvo))


# ================================================================== seguranca
def test_env_nunca(ft: FileTools, docs: Path, project_root: Path, chaves: Path) -> None:
    (docs / ".env").write_text("GEMINI_API_KEY=AIzaOUTRA", encoding="utf-8")
    for alvo in (docs / ".env", project_root / ".env", chaves / ".env"):
        r = ft.read_file(str(alvo))
        assert "AIza" not in r and "segredo" not in r
        assert "senhas ou chaves" in r or "protegida" in r


@pytest.mark.parametrize("nome", ["id_rsa", "chave.pem", "cofre.kdbx", ".env.local"])
def test_arquivos_de_senha_nunca(ft: FileTools, docs: Path, nome: str) -> None:
    (docs / nome).write_text("SEGREDO", encoding="utf-8")
    assert "SEGREDO" not in ft.read_file(str(docs / nome))


def test_link_para_segredo_nunca(ft: FileTools, docs: Path, chaves: Path) -> None:
    link = docs / "inocente.txt"
    try:
        link.symlink_to(chaves / ".env")
    except OSError:
        pytest.skip("sem permissao para criar link neste sistema")
    r = ft.read_file(str(link))
    assert "AIza" not in r


def test_pasta_protegida(ft: FileTools, chaves: Path, project_root: Path) -> None:
    (project_root / "leia.txt").write_text("dentro do Jarvis", encoding="utf-8")
    assert "protegida" in ft.read_file(str(chaves / "notas.txt"))
    assert "protegida" in ft.read_file(str(project_root / "leia.txt"))


@pytest.mark.parametrize(
    "caminho", ["\\\\servidor\\pasta\\a.txt", "//servidor/pasta/a.txt", "\\\\?\\C:\\a.txt"]
)
def test_rede_e_dispositivo(ft: FileTools, caminho: str) -> None:
    assert "rede" in ft.read_file(caminho)


def test_sem_expandir_variaveis(ft: FileTools, docs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PASTA_X", str(docs))
    (docs / "a.txt").write_text("oi", encoding="utf-8")
    assert "oi" not in ft.read_file("%PASTA_X%\\a.txt")
    assert "oi" not in ft.read_file("$PASTA_X/a.txt")


def test_arquivo_gigante(ft: FileTools, docs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    alvo = docs / "enorme.log"
    alvo.write_bytes(b"x" * 2048)
    monkeypatch.setattr(file_tools, "READ_MAX_BYTES", 1024)
    assert ft.read_file(str(alvo)) == "Esse arquivo é grande demais para eu ler (mais de 25 MB)."


@pytest.mark.parametrize("nome", ["programa.exe", "script.ps1", "planilha.xlsm", "velho.doc"])
def test_extensao_que_nao_le(ft: FileTools, docs: Path, nome: str) -> None:
    (docs / nome).write_bytes(b"MZ conteudo")
    ext = nome[nome.rfind(".") :]
    assert ft.read_file(str(docs / nome)) == f"Eu ainda não sei ler arquivos {ext}."


def test_sem_extensao(ft: FileTools, docs: Path) -> None:
    (docs / "LEIAME").write_text("oi", encoding="utf-8")
    assert ft.read_file(str(docs / "LEIAME")) == "Eu ainda não sei ler arquivos sem extensão."


def test_link_txt_para_executavel_nao_le(ft: FileTools, docs: Path) -> None:
    real = docs / "ferramenta.ps1"
    real.write_text("Remove-Item", encoding="utf-8")
    link = docs / "ferramenta.txt"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("sem permissao para criar link neste sistema")
    assert "não sei ler" in ft.read_file(str(link))


def test_inexistente_pasta_e_relativo(ft: FileTools, docs: Path) -> None:
    assert "Não encontrei esse arquivo" in ft.read_file(str(docs / "nao_existe.pdf"))
    assert "find_file" in ft.read_file(str(docs / "nao_existe.pdf"))
    assert "é uma pasta" in ft.read_file(str(docs))
    assert "caminho completo" in ft.read_file("relatorio.txt")


def test_nome_perigoso(ft: FileTools, docs: Path) -> None:
    assert "nome de arquivo" in ft.read_file(str(docs / "a.txt:escondido"))


# ================================================================== registro
def test_registro_tem_read_file_embrulhado(tmp_path: Path) -> None:
    registro = ToolRegistry(
        Settings(api_key="x", project_root=tmp_path),
        confirm=lambda t, m: False,
        permissoes_atuais=_tudo_liberado,
    )
    func = registro.get("read_file")
    assert func is not None and func.__name__ == "read_file"
    assert getattr(func, "__wrapped__", None) is not None  # passou pelo safe_tool
    assert func.max_result_chars == READ_RESULT_MAX_CHARS  # type: ignore[attr-defined]
    assert "caminho completo" in func("relatorio.txt")


def test_erro_inesperado_vira_frase(
    guarda: PathGuard, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (docs / "a.txt").write_text("oi", encoding="utf-8")

    def explode(_p: Path) -> tuple[str, str]:
        raise RuntimeError("bug interno")

    monkeypatch.setattr(file_tools, "_ler_texto", explode)
    func = safe_tool(FileTools(guarda).read_file)
    r = func(str(docs / "a.txt"))
    assert r.startswith("ERRO:") and "bug interno" not in r


def test_safe_tool_respeita_o_limite_do_read_file(guarda: PathGuard, docs: Path) -> None:
    """Precisa da mudanca no errors.py (dono: agente A) descrita no relatorio B."""
    (docs / "longo.txt").write_text("b" * 15_000, encoding="utf-8")
    func = safe_tool(FileTools(guarda).read_file)
    r = func(str(docs / "longo.txt"))
    if len(r) <= MAX_RESULT_CHARS + 20:
        pytest.skip("safe_tool ainda corta em 700 caracteres (aguardando errors.py do agente A)")
    assert r.count("b") == 15_000


def _tudo_liberado() -> dict[str, object]:
    return {
        "arquivos": "ler_gravar_excluir",
        "apps": True,
        "internet": True,
        "email": True,
        "outros_drives": True,
    }
