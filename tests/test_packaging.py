"""Testes do empacotamento (spec do PyInstaller, Inno Setup, build.ps1) e das amostras de voz.

Rodam em qualquer sistema, sem PyInstaller, sem Inno Setup e sem internet (SDK mockado).
"""

from __future__ import annotations

import ast
import importlib.util
import io
import re
import sys
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parents[1]
PACKAGING = RAIZ / "packaging"
SPEC = PACKAGING / "jarvis.spec"
ISS = PACKAGING / "jarvis.iss"
BUILD = PACKAGING / "build.ps1"
SCRIPT = RAIZ / "scripts" / "gerar_amostras_voz.py"
UI = RAIZ / "src" / "jarvis" / "ui"

CHAVE_FALSA = "AIzaSyTESTE_chave_super_secreta_1234567890"


def _ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8-sig")


@pytest.fixture
def gerador() -> ModuleType:
    """Importa scripts/gerar_amostras_voz.py como modulo (a pasta scripts nao e pacote)."""
    spec = importlib.util.spec_from_file_location("gerar_amostras_voz", SCRIPT)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gerar_amostras_voz"] = modulo
    spec.loader.exec_module(modulo)
    yield modulo
    sys.modules.pop("gerar_amostras_voz", None)


def _secao(texto: str, nome: str) -> str:
    """Conteudo de uma secao [nome] do .iss (ate a proxima secao)."""
    achado = re.search(rf"^\[{nome}\]\s*$(.*?)(?=^\[\w+\]\s*$|\Z)", texto, re.M | re.S)
    assert achado, f"secao [{nome}] nao encontrada"
    return achado.group(1)


def _pcm(segundos: float = 0.1, taxa: int = 24_000) -> bytes:
    return b"\x01\x00" * int(segundos * taxa)


def _wav_bytes(pcm: bytes, taxa: int = 24_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(pcm)
    return buffer.getvalue()


class _ClienteFalso:
    """Imita genai.Client: client.models.generate_content(...) devolve audio."""

    def __init__(self, dados: bytes, mime: str = "audio/wav", erro: Exception | None = None):
        self.chamadas: list[dict] = []
        self._dados, self._mime, self._erro = dados, mime, erro
        self.models = self

    def generate_content(self, **kwargs):
        self.chamadas.append(kwargs)
        if self._erro is not None:
            raise self._erro
        inline = SimpleNamespace(data=self._dados, mime_type=self._mime)
        parte = SimpleNamespace(inline_data=inline)
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[parte]))])


@pytest.fixture
def sem_chave(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, gerador: ModuleType) -> None:
    """Nenhuma fonte de chave: sem variavel, sem .env do projeto e sem pasta do usuario."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(gerador, "RAIZ_PROJETO", tmp_path / "projeto")
    monkeypatch.setattr(gerador, "pasta_usuario", lambda: tmp_path / "usuario")


# ------------------------------------------------------------------ spec do PyInstaller


def test_spec_e_python_valido() -> None:
    ast.parse(_ler(SPEC))


def test_spec_referencia_arquivos_que_existem() -> None:
    texto = _ler(SPEC)
    for trecho in ('"orb.html"', '"visuais"', '"jarvis.ico"', '"amostras"', "jarvis_entry.py"):
        assert trecho in texto
    assert (UI / "orb.html").is_file()
    assert (UI / "jarvis.ico").is_file()
    assert list((UI / "visuais").glob("*.js"))
    assert (UI / "amostras" / "LEIA.md").is_file()
    assert (PACKAGING / "jarvis_entry.py").is_file()


def test_spec_onedir_sem_console_e_coleta_dependencias() -> None:
    texto = _ler(SPEC)
    assert "console=False" in texto
    assert "COLLECT(" in texto  # onedir
    assert 'name="Jarvis"' in texto
    for pacote in ("google.genai", "webview", "send2trash", "pyaudio"):
        assert f'"{pacote}"' in texto
    assert "webview.platforms.edgechromium" in texto
    assert "webview.platforms.winforms" in texto


def test_entry_chama_main() -> None:
    texto = _ler(PACKAGING / "jarvis_entry.py")
    ast.parse(texto)
    assert "from jarvis.__main__ import main" in texto


# ------------------------------------------------------------------ Inno Setup


def test_iss_sem_admin_e_na_pasta_do_usuario() -> None:
    texto = _ler(ISS)
    assert re.search(r"^PrivilegesRequired=lowest\s*$", texto, re.MULTILINE)
    assert re.search(r"^DefaultDirName=\{localappdata\}\\Programs\\Jarvis\s*$", texto, re.MULTILINE)
    assert "BrazilianPortuguese.isl" in texto
    assert "AppVersion={#AppVersion}" in texto
    assert "#ifndef AppVersion" in texto


def test_iss_atalhos_com_icone() -> None:
    texto = _ler(ISS)
    assert "{autodesktop}" in texto
    assert "{autoprograms}" in texto
    assert texto.count("IconFilename:") >= 2


def test_iss_nao_apaga_configuracao_sem_perguntar() -> None:
    texto = _ler(ISS)
    secao = _secao(texto, "UninstallDelete")
    linhas = [linha for linha in secao.splitlines() if linha.strip() and not linha.startswith(";")]
    assert linhas, "deveria apagar ao menos a pasta do programa"
    for linha in linhas:
        assert "userappdata" not in linha.lower()
        assert "appdata" not in linha.lower()
    assert 'Name: "{app}"' in secao
    codigo = _secao(texto, "Code")
    assert "{userappdata}\\Jarvis" in codigo
    # O DelTree so roda dentro do "if MsgBox(...) = IDYES".
    assert codigo.index("MsgBox(") < codigo.index("IDYES") < codigo.index("DelTree(")
    assert "MB_DEFBUTTON2" in codigo  # "Nao" e o botao padrao


def test_iss_pasta_fixa_porque_o_desinstalador_apaga_app_inteiro() -> None:
    # Com {app} apagado inteiro no [UninstallDelete], escolher "Documentos" como pasta de
    # instalacao apagaria os documentos ao desinstalar.
    texto = _ler(ISS)
    assert re.search(r"^DisableDirPage=yes\s*$", texto, re.MULTILINE)


# ------------------------------------------------------------------ build.ps1


def test_build_referencia_spec_iss_e_versao() -> None:
    texto = _ler(BUILD)
    assert "jarvis.spec" in texto
    assert "jarvis.iss" in texto
    assert "pyproject.toml" in texto
    assert "/DAppVersion=" in texto
    assert "ISCC.exe" in texto
    assert "jrsoftware.org" in texto
    assert "SHA256" in texto
    assert ".venv-build" in texto
    assert "pyinstaller" in texto.lower()


def test_build_ps1_so_ascii() -> None:
    """O PowerShell 5.1 le .ps1 sem BOM como ANSI: sem acentos para nao virar lixo."""
    assert all(ord(c) < 128 for c in _ler(BUILD))


def test_versao_do_pyproject_bate_com_regex_do_build() -> None:
    padrao = r'^\s*version\s*=\s*"([^"]+)"'
    achado = re.search(padrao, (RAIZ / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    assert achado and re.fullmatch(r"\d+\.\d+\.\d+.*", achado.group(1))


# ------------------------------------------------------------------ gerar_amostras_voz.py


def test_script_importa_sem_chave_e_tem_opcoes(gerador: ModuleType, sem_chave: None) -> None:
    ajuda = gerador._parser().format_help()
    assert "--forcar" in ajuda
    assert "--vozes" in ajuda
    assert "--modelo" in ajuda
    assert gerador.VOZES == ("Charon", "Puck", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr")
    assert gerador.FRASE == "Olá, senhor. Eu sou o Jarvis, seu assistente pessoal."


def test_vozes_do_script_batem_com_jarvis_vozes(gerador: ModuleType) -> None:
    vozes = pytest.importorskip("jarvis.vozes")
    texto = Path(vozes.__file__).read_text(encoding="utf-8")
    for voz in gerador.VOZES:
        assert f'"{voz}"' in texto


def test_sem_chave_sai_com_erro_claro(
    gerador: ModuleType, sem_chave: None, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    codigo = gerador.main(["--saida", str(tmp_path / "amostras"), "--pausa", "0"])
    assert codigo == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_voz_desconhecida(gerador: ModuleType, tmp_path: Path) -> None:
    assert gerador.main(["--vozes", "Jarvisson", "--saida", str(tmp_path)]) == 2


def test_gera_wav_valido_e_nao_sobrescreve(
    gerador: ModuleType,
    sem_chave: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", CHAVE_FALSA)
    cliente = _ClienteFalso(_wav_bytes(_pcm()))
    chaves_usadas: list[str] = []

    def criar(chave: str):
        chaves_usadas.append(chave)
        return cliente

    monkeypatch.setattr(gerador, "_criar_cliente", criar)
    saida = tmp_path / "amostras"

    assert gerador.main(["--vozes", "Puck", "--saida", str(saida), "--pausa", "0"]) == 0
    arquivo = saida / "Puck.wav"
    with wave.open(str(arquivo), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 24_000
        assert w.getnframes() > 0
    assert chaves_usadas == [CHAVE_FALSA]
    assert len(cliente.chamadas) == 1
    chamada = cliente.chamadas[0]
    assert chamada["model"] == gerador.MODELO_PADRAO
    assert chamada["config"].response_modalities == ["AUDIO"]

    # Segunda vez: ja existe -> pula, sem chamar o Google e sem mexer no arquivo.
    arquivo.write_bytes(b"conteudo antigo")
    assert gerador.main(["--vozes", "Puck", "--saida", str(saida), "--pausa", "0"]) == 0
    assert arquivo.read_bytes() == b"conteudo antigo"
    assert len(cliente.chamadas) == 1

    # Com --forcar: refaz.
    assert gerador.main(["--vozes", "Puck", "--saida", str(saida), "--pausa", "0", "--forcar"]) == 0
    assert arquivo.read_bytes() != b"conteudo antigo"
    assert len(cliente.chamadas) == 2

    saida_total = capsys.readouterr()
    assert CHAVE_FALSA not in saida_total.out + saida_total.err


def test_pcm_cru_vira_wav(gerador: ModuleType, tmp_path: Path) -> None:
    destino = tmp_path / "Kore.wav"
    gerador.gravar_wav(destino, _pcm(0.2, 16_000), "audio/L16;codec=pcm;rate=16000")
    with wave.open(str(destino), "rb") as w:
        assert w.getframerate() == 16_000
        assert w.getnframes() == int(0.2 * 16_000)
    assert not list(tmp_path.glob("*.tmp"))


def test_pedido_do_modelo_novo_usa_estilo_separado(gerador: ModuleType) -> None:
    contents, config = gerador.montar_pedido("gemini-3.8-flash-tts", "Charon")
    parte = contents[0].parts[0]
    assert parte.text == gerador.FRASE  # o texto e lido ao pe da letra
    assert "mordomo" in parte.speech_metadata.style
    assert config.speech_config.voice_config.voice == "Charon"


def test_pedido_do_modelo_legado_usa_prebuilt(gerador: ModuleType) -> None:
    contents, config = gerador.montar_pedido("gemini-3.1-flash-tts-preview", "Orus")
    assert config.speech_config.voice_config.prebuilt_voice_config.voice_name == "Orus"
    assert gerador.FRASE in contents[0].parts[0].text


def test_erro_nao_mostra_a_chave_e_da_exit_1(
    gerador: ModuleType,
    sem_chave: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", CHAVE_FALSA)
    erro = RuntimeError(f"400 API key invalid: key={CHAVE_FALSA}")
    monkeypatch.setattr(gerador, "_criar_cliente", lambda chave: _ClienteFalso(b"", erro=erro))
    codigo = gerador.main(["--vozes", "Puck,Kore", "--saida", str(tmp_path), "--pausa", "0"])
    assert codigo == 1
    saida = capsys.readouterr()
    assert CHAVE_FALSA not in saida.out + saida.err
    assert "Puck" in saida.err and "Kore" in saida.err
    assert not list(tmp_path.glob("*.wav"))


def test_cota_para_com_mensagem_clara(
    gerador: ModuleType,
    sem_chave: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class ErroApi(Exception):
        code = 429

    monkeypatch.setenv("GEMINI_API_KEY", CHAVE_FALSA)
    monkeypatch.setattr(gerador, "ESPERA_COTA_S", 0)
    cliente = _ClienteFalso(b"", erro=ErroApi("RESOURCE_EXHAUSTED"))
    monkeypatch.setattr(gerador, "_criar_cliente", lambda chave: cliente)
    codigo = gerador.main(["--vozes", "Puck,Kore", "--saida", str(tmp_path), "--pausa", "0"])
    assert codigo == 1
    assert len(cliente.chamadas) == 2  # tentou Puck, esperou, tentou de novo e parou
    assert "limite" in capsys.readouterr().err


def test_chave_do_env_do_projeto(
    gerador: ModuleType, sem_chave: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projeto = tmp_path / "projeto"
    projeto.mkdir()
    (projeto / ".env").write_text(f"GEMINI_API_KEY={CHAVE_FALSA}\n", encoding="utf-8")
    chave, origem = gerador.carregar_chave(projeto)
    assert chave == CHAVE_FALSA
    assert CHAVE_FALSA not in origem
    import os

    assert "GEMINI_API_KEY" not in os.environ  # nao vaza para o ambiente do processo


def test_chave_da_pasta_do_usuario_e_placeholder(
    gerador: ModuleType, sem_chave: None, tmp_path: Path
) -> None:
    usuario = tmp_path / "usuario"
    usuario.mkdir()
    (usuario / ".env").write_text("GEMINI_API_KEY=cole_sua_chave_aqui\n", encoding="utf-8")
    assert gerador.carregar_chave(tmp_path / "projeto") == ("", "")
    (usuario / ".env").write_text(f"GEMINI_API_KEY={CHAVE_FALSA}\n", encoding="utf-8")
    assert gerador.carregar_chave(tmp_path / "projeto")[0] == CHAVE_FALSA
