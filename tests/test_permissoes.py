"""Testes das permissoes (tools/permissoes.py, gancho no ToolRegistry, PathGuard e ponte JS).

Regra principal: PADRAO TUDO DESLIGADO. So ``current_time`` e sempre liberada; ferramenta fora
do mapa fica bloqueada; a checagem acontece NA HORA DA CHAMADA.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path
from typing import Any

import pytest

from jarvis.config import Settings
from jarvis.tools import ToolRegistry, permissoes
from jarvis.tools.security import MSG_OUTROS_DRIVES, CaminhoRecusado, PathGuard
from jarvis.ui import preferencias
from jarvis.ui.api_config import METODOS_PUBLICOS, ApiJs, estado_config, ponte_js

DESLIGADO = {
    "arquivos": "nenhum",
    "apps": False,
    "internet": False,
    "email": False,
    "outros_drives": False,
}
TUDO = {
    "arquivos": "ler_gravar_excluir",
    "apps": True,
    "internet": True,
    "email": True,
    "outros_drives": True,
}

# Contrato da rodada 0.9: ferramenta -> o que precisa estar ligado.
CONTRATO: dict[str, tuple[str, Any] | None] = {
    "current_time": None,
    "list_open_apps": ("apps", True),
    "open_app": ("apps", True),
    "close_app": ("apps", True),
    "open_website": ("internet", True),
    "web_search": ("internet", True),
    "draft_email": ("email", True),
    "list_folder": ("arquivos", "ler"),
    "find_file": ("arquivos", "ler"),
    "open_file": ("arquivos", "ler"),
    "read_file": ("arquivos", "ler"),
    "create_folder": ("arquivos", "ler_gravar"),
    "move_or_rename": ("arquivos", "ler_gravar"),
    "copy_item": ("arquivos", "ler_gravar"),
    "create_text_file": ("arquivos", "ler_gravar"),
    "write_word_document": ("arquivos", "ler_gravar"),
    "delete_to_trash": ("arquivos", "ler_gravar_excluir"),
}


class Fonte:
    """Fonte de permissoes mutavel (simula o painel mudando entre duas chamadas)."""

    def __init__(self, **valores: Any) -> None:
        self.valores: dict[str, Any] = {**DESLIGADO, **valores}
        self.leituras = 0

    def __call__(self) -> dict[str, Any]:
        self.leituras += 1
        return dict(self.valores)


@pytest.fixture
def prefs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    arquivo = tmp_path / "cfg" / "preferencias.json"
    monkeypatch.setattr(preferencias, "caminho_preferencias", lambda: arquivo)
    return arquivo


@pytest.fixture
def casa() -> Path:
    """Home do usuario nos testes (o conftest aponta HOME para ``tmp_path/_usuario``)."""
    home = Path.home()
    (home / "Documents").mkdir(parents=True, exist_ok=True)
    return home


def _registry(tmp_path: Path, fonte: Any = None, confirm: Any = None) -> ToolRegistry:
    settings = Settings(api_key="x", project_root=tmp_path / "projeto")
    return ToolRegistry(settings, confirm=confirm or (lambda t, m: False), permissoes_atuais=fonte)


# ================================================================== modelo
def test_padrao_e_tudo_desligado() -> None:
    assert dict(permissoes.PADRAO) == DESLIGADO
    assert permissoes.normalizar(None) == DESLIGADO
    assert permissoes.normalizar({}) == DESLIGADO


@pytest.mark.parametrize(
    "bruto",
    [
        "tudo",
        ["apps"],
        42,
        {"arquivos": "TUDO", "apps": 1, "internet": "true", "email": "sim", "outros_drives": None},
        {"arquivos": ["ler"], "apps": [True]},
        {"arquivos": None},
        {"arquivos": "Ler"},
    ],
)
def test_valor_invalido_vira_desligado(bruto: object) -> None:
    assert permissoes.normalizar(bruto) == DESLIGADO


def test_normalizar_aproveita_o_que_e_valido() -> None:
    assert permissoes.normalizar({"apps": True, "arquivos": "lixo"}) == {
        **DESLIGADO,
        "apps": True,
    }
    assert permissoes.normalizar({**TUDO, "extra": True}) == TUDO


def test_mapa_bate_com_o_contrato() -> None:
    assert dict(permissoes.EXIGENCIAS) == CONTRATO


def test_mapa_conhece_todas_as_ferramentas_registradas(tmp_path: Path) -> None:
    assert set(_registry(tmp_path).names) <= set(permissoes.EXIGENCIAS)


def test_toda_ferramenta_tem_nome_amigavel_com_acento_quando_precisa() -> None:
    for nome in CONTRATO:
        if nome != "current_time":
            assert nome in permissoes.NOMES_AMIGAVEIS, nome
    assert permissoes.nome_amigavel("draft_email") == "preparar e-mails"
    assert permissoes.nome_amigavel("rm_rf") == permissoes.NOME_DESCONHECIDO


def test_mensagem_de_bloqueio_do_contrato() -> None:
    assert permissoes.mensagem_bloqueio("open_app") == (
        "Essa ação está desligada nas permissões (abrir programas). Para liberar, abra a "
        "engrenagem e vá em Permissões."
    )


@pytest.mark.parametrize("ferramenta", sorted(CONTRATO))
def test_tudo_desligado_so_libera_current_time(ferramenta: str) -> None:
    assert permissoes.permitido(ferramenta, DESLIGADO) is (ferramenta == "current_time")


@pytest.mark.parametrize("ferramenta", sorted(CONTRATO))
def test_tudo_ligado_libera_todas_do_mapa(ferramenta: str) -> None:
    assert permissoes.permitido(ferramenta, TUDO)


@pytest.mark.parametrize("nivel", permissoes.NIVEIS_ARQUIVOS)
def test_cada_nivel_de_arquivos(nivel: str) -> None:
    ordem = permissoes.NIVEIS_ARQUIVOS
    for ferramenta, exigencia in CONTRATO.items():
        if exigencia is None or exigencia[0] != "arquivos":
            continue
        esperado = ordem.index(nivel) >= ordem.index(exigencia[1])
        assert permissoes.permitido(ferramenta, {**DESLIGADO, "arquivos": nivel}) is esperado, (
            nivel,
            ferramenta,
        )
    # arquivos nunca liga programas, internet nem e-mail
    for ferramenta in ("open_app", "web_search", "draft_email"):
        assert not permissoes.permitido(ferramenta, {**DESLIGADO, "arquivos": nivel})


@pytest.mark.parametrize("categoria", ["apps", "internet", "email"])
def test_cada_categoria_liga_so_as_suas(categoria: str) -> None:
    ligado = {**DESLIGADO, categoria: True}
    for ferramenta, exigencia in CONTRATO.items():
        esperado = exigencia is None or exigencia[0] == categoria
        assert permissoes.permitido(ferramenta, ligado) is esperado, ferramenta


def test_outros_drives_nao_libera_ferramenta_nenhuma() -> None:
    ligado = {**DESLIGADO, "outros_drives": True}
    assert [f for f in CONTRATO if permissoes.permitido(f, ligado)] == ["current_time"]


@pytest.mark.parametrize(
    "ferramenta", ["run_command", "powershell", "", "CURRENT_TIME", "__init__", None, 3]
)
def test_ferramenta_desconhecida_bloqueada_mesmo_com_tudo_ligado(ferramenta: Any) -> None:
    assert permissoes.permitido(ferramenta, TUDO) is False


@pytest.mark.parametrize(
    "dados",
    [
        None,
        [],
        "tudo",
        {},
        {"arquivos": "ler"},  # incompleto
        {**TUDO, "extra": True},
        {**TUDO, "arquivos": "tudo"},
        {**TUDO, "arquivos": 3},
        {**TUDO, "apps": 1},
        {**TUDO, "internet": "true"},
        {**TUDO, "email": None},
        {**TUDO, "outros_drives": [True]},
        {"__proto__": {}, **TUDO},
        {1: True, **{k: v for k, v in TUDO.items() if k != "apps"}},
    ],
)
def test_validar_e_estrito(dados: object) -> None:
    assert permissoes.validar(dados) is None


def test_validar_aceita_o_modelo_completo() -> None:
    assert permissoes.validar(TUDO) == TUDO
    assert permissoes.validar(DESLIGADO) == DESLIGADO


# ================================================================== ToolRegistry
def test_registry_sem_arquivo_de_preferencias_bloqueia_tudo(tmp_path: Path, prefs: Path) -> None:
    reg = _registry(tmp_path)  # fonte padrao: preferencias.json (nao existe)
    assert not prefs.exists()
    assert "Essa ação está desligada" not in reg.get("current_time")()
    for nome in reg.names:
        if nome == "current_time":
            continue
        resultado = reg.get(nome)(*["x"] * _obrigatorios(reg, nome))
        assert resultado == permissoes.mensagem_bloqueio(nome), nome


def _obrigatorios(reg: ToolRegistry, nome: str) -> int:
    parametros = inspect.signature(reg.get(nome)).parameters.values()
    return sum(p.default is inspect.Parameter.empty for p in parametros)


def test_bloqueada_nao_executa(tmp_path: Path, casa: Path) -> None:
    confirmacoes: list[str] = []
    reg = _registry(
        tmp_path, Fonte(arquivos="ler"), confirm=lambda t, m: confirmacoes.append(m) or True
    )
    pasta = casa / "Documents" / "nova"
    assert reg.get("create_folder")(str(pasta)) == permissoes.mensagem_bloqueio("create_folder")
    assert not pasta.exists()
    alvo = casa / "Documents" / "a.txt"
    alvo.write_text("x", encoding="utf-8")
    assert reg.get("delete_to_trash")(str(alvo)) == permissoes.mensagem_bloqueio("delete_to_trash")
    assert alvo.exists() and confirmacoes == []


def test_registry_preserva_nome_docstring_e_assinatura(tmp_path: Path) -> None:
    from jarvis.tools.file_tools import FileTools

    reg = _registry(tmp_path)
    func = reg.get("move_or_rename")
    assert func.__name__ == "move_or_rename"
    assert func.__doc__ == FileTools.move_or_rename.__doc__
    assert list(inspect.signature(func).parameters) == ["origem", "destino"]


def test_nivel_ler_lista_mas_nao_grava(tmp_path: Path, casa: Path) -> None:
    (casa / "Documents" / "relatorio.txt").write_text("x", encoding="utf-8")
    reg = _registry(tmp_path, Fonte(arquivos="ler"))
    assert "relatorio.txt" in reg.get("list_folder")(str(casa / "Documents"))
    assert "relatorio" in reg.get("find_file")("relatorio", str(casa / "Documents"))
    novo = casa / "Documents" / "b.txt"
    assert "desligada" in reg.get("create_text_file")(str(novo), "oi")
    assert not novo.exists()


def test_nivel_ler_gravar_cria_mas_nao_apaga(tmp_path: Path, casa: Path) -> None:
    reg = _registry(tmp_path, Fonte(arquivos="ler_gravar"))
    novo = casa / "Documents" / "b.txt"
    assert "desligada" not in reg.get("create_text_file")(str(novo), "oi")
    assert novo.read_text(encoding="utf-8") == "oi"
    assert reg.get("delete_to_trash")(str(novo)) == permissoes.mensagem_bloqueio("delete_to_trash")
    assert novo.exists()


def test_nivel_excluir_continua_pedindo_confirmacao(
    tmp_path: Path, casa: Path, as_windows: None, fake_trash: list[str]
) -> None:
    perguntas: list[str] = []
    reg = _registry(
        tmp_path,
        Fonte(arquivos="ler_gravar_excluir"),
        confirm=lambda t, m: perguntas.append(m) is not None,  # sempre "Nao"
    )
    alvo = casa / "Documents" / "apagar.txt"
    alvo.write_text("x", encoding="utf-8")
    resultado = reg.get("delete_to_trash")(str(alvo))
    assert len(perguntas) == 1 and "Nada foi apagado" in resultado
    assert alvo.exists() and fake_trash == []


def test_apps_e_internet_bloqueados_sem_abrir_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import webbrowser

    abertos: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: abertos.append(a[0]) or True)
    reg = _registry(tmp_path, Fonte(arquivos="ler_gravar_excluir", email=True))
    assert reg.get("open_website")("https://example.com") == permissoes.mensagem_bloqueio(
        "open_website"
    )
    assert reg.get("web_search")("tempo") == permissoes.mensagem_bloqueio("web_search")
    assert reg.get("open_app")("calculadora") == permissoes.mensagem_bloqueio("open_app")
    assert abertos == []


def test_mudanca_vale_na_hora(tmp_path: Path, casa: Path) -> None:
    fonte = Fonte()
    reg = _registry(tmp_path, fonte)
    lista = reg.get("list_folder")
    assert lista(str(casa)) == permissoes.mensagem_bloqueio("list_folder")
    fonte.valores["arquivos"] = "ler"
    assert "desligada" not in lista(str(casa))
    fonte.valores["arquivos"] = "nenhum"
    assert lista(str(casa)) == permissoes.mensagem_bloqueio("list_folder")
    assert fonte.leituras >= 3  # leu a cada chamada


def test_mudanca_no_arquivo_vale_na_hora(tmp_path: Path, casa: Path, prefs: Path) -> None:
    reg = _registry(tmp_path)  # le o preferencias.json a cada chamada
    lista = reg.get("list_folder")
    assert "desligada" in lista(str(casa))
    assert preferencias.salvar_permissoes({**DESLIGADO, "arquivos": "ler"})
    assert "desligada" not in lista(str(casa))
    assert preferencias.salvar_permissoes(DESLIGADO)
    assert "desligada" in lista(str(casa))


@pytest.mark.parametrize(
    "conteudo",
    [
        "{nao e json",
        "[]",
        '"tudo"',
        '{"permissoes": "tudo"}',
        '{"permissoes": {"arquivos": "TUDO", "apps": "true"}}',
        "\x00\x01\x02",
    ],
)
def test_arquivo_corrompido_vira_tudo_desligado(
    tmp_path: Path, casa: Path, prefs: Path, conteudo: str
) -> None:
    prefs.parent.mkdir(parents=True, exist_ok=True)
    prefs.write_text(conteudo, encoding="utf-8")
    assert preferencias.carregar_permissoes() == DESLIGADO
    reg = _registry(tmp_path)
    assert reg.get("list_folder")(str(casa)) == permissoes.mensagem_bloqueio("list_folder")
    assert reg.permissoes() == DESLIGADO


def test_fonte_que_quebra_vira_tudo_desligado(tmp_path: Path, casa: Path) -> None:
    def quebrada() -> dict[str, Any]:
        raise OSError("disco sumiu")

    reg = _registry(tmp_path, quebrada)
    assert reg.get("list_folder")(str(casa)) == permissoes.mensagem_bloqueio("list_folder")
    assert "desligada" not in reg.get("current_time")()


def test_fonte_que_devolve_lixo_vira_tudo_desligado(tmp_path: Path, casa: Path) -> None:
    reg = _registry(tmp_path, lambda: "tudo liberado")  # type: ignore[arg-type,return-value]
    assert reg.get("list_folder")(str(casa)) == permissoes.mensagem_bloqueio("list_folder")


# ================================================================== outros discos
def _guarda(tmp_path: Path, ligado: Any) -> tuple[PathGuard, Path, Path]:
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    (home / "OneDrive" / "Documentos").mkdir(parents=True)
    fora = tmp_path / "disco_d"
    fora.mkdir()
    projeto = tmp_path / "projeto"
    projeto.mkdir()
    return PathGuard(projeto, home=home, outros_drives=ligado), home, fora


def test_outros_discos_desligado_so_pastas_pessoais(tmp_path: Path) -> None:
    guard, home, fora = _guarda(tmp_path, lambda: False)
    assert guard.resolve(str(home / "Documents" / "x.txt")) == home / "Documents" / "x.txt"
    assert guard.resolve(str(home / "OneDrive" / "Documentos" / "y.txt"))
    assert guard.resolve("documentos\\z.txt")  # atalho falado continua valendo
    assert guard.resolve(str(home))  # o proprio home
    for caminho in (fora, fora / "x.txt", tmp_path, home.parent / "home2" / "a.txt"):
        with pytest.raises(CaminhoRecusado) as erro:
            guard.resolve(str(caminho))
        assert str(erro.value) == MSG_OUTROS_DRIVES
    with pytest.raises(CaminhoRecusado):
        guard.resolve(str(home / ".." / "disco_d" / "x.txt"))  # ".." para fora


def test_outros_discos_link_dentro_do_home_que_aponta_para_fora(tmp_path: Path) -> None:
    guard, home, fora = _guarda(tmp_path, lambda: False)
    link = home / "Documents" / "atalho"
    try:
        link.symlink_to(fora, target_is_directory=True)
    except OSError:  # pragma: no cover - sistema sem link simbolico
        pytest.skip("sem link simbolico aqui")
    with pytest.raises(CaminhoRecusado):
        guard.resolve(str(link / "x.txt"))


def test_outros_discos_ligado_libera_mas_protegidas_continuam(tmp_path: Path) -> None:
    guard, _home, fora = _guarda(tmp_path, lambda: True)
    assert guard.resolve(str(fora / "x.txt")) == fora / "x.txt"
    assert guard.is_protected(guard.resolve(str(tmp_path / "projeto" / ".env")))
    assert guard.is_protected(Path(Path(fora).anchor))  # raiz do disco


@pytest.mark.parametrize("valor", [None, 1, "sim", "true"])
def test_outros_discos_valor_estranho_vale_desligado(tmp_path: Path, valor: Any) -> None:
    guard, _home, fora = _guarda(tmp_path, lambda: valor)
    with pytest.raises(CaminhoRecusado):
        guard.resolve(str(fora / "x.txt"))


def test_outros_discos_callback_que_quebra_vale_desligado(tmp_path: Path) -> None:
    def quebrada() -> bool:
        raise RuntimeError("x")

    guard, _home, fora = _guarda(tmp_path, quebrada)
    with pytest.raises(CaminhoRecusado):
        guard.resolve(str(fora))


def test_outros_discos_sem_callback_mantem_o_comportamento_antigo(tmp_path: Path) -> None:
    guard, _home, fora = _guarda(tmp_path, None)
    assert guard.resolve(str(fora / "x.txt")) == fora / "x.txt"


def test_outros_discos_pelo_registry_vale_na_hora(tmp_path: Path, casa: Path) -> None:
    fora = tmp_path / "pendrive"
    fora.mkdir()
    (fora / "musica.mp3").write_bytes(b"x")
    fonte = Fonte(arquivos="ler_gravar")
    reg = _registry(tmp_path, fonte)
    assert reg.get("list_folder")(str(fora)) == MSG_OUTROS_DRIVES
    assert reg.get("copy_item")(str(fora / "musica.mp3"), str(casa / "Documents")) == (
        MSG_OUTROS_DRIVES
    )
    assert reg.get("create_folder")(str(fora / "nova")) == MSG_OUTROS_DRIVES
    assert not (fora / "nova").exists()
    fonte.valores["outros_drives"] = True
    assert "musica.mp3" in reg.get("list_folder")(str(fora))
    # pastas pessoais nunca dependeram de "outros discos"
    fonte.valores["outros_drives"] = False
    assert "desligada" not in reg.get("list_folder")(str(casa))


def test_ferramentas_novas_herdam_outros_discos_pelo_guard(tmp_path: Path) -> None:
    """read_file/write_word_document (agente B) usam ``registry.guard.resolve``: herdam."""
    fonte = Fonte(arquivos="ler_gravar")
    reg = _registry(tmp_path, fonte)
    fora = tmp_path / "d"
    with pytest.raises(CaminhoRecusado):
        reg.guard.resolve(str(fora / "a.docx"))
    fonte.valores["outros_drives"] = True
    assert reg.guard.resolve(str(fora / "a.docx")) == fora / "a.docx"


def test_onedrive_fora_do_home_conta_como_pessoal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    onedrive = tmp_path / "OneDrive - Empresa"
    onedrive.mkdir()
    monkeypatch.setenv("OneDriveCommercial", str(onedrive))
    guard = PathGuard(tmp_path / "projeto", outros_drives=lambda: False)  # home real (falso)
    assert guard.resolve(str(onedrive / "a.txt")) == onedrive / "a.txt"
    monkeypatch.setenv("OneDrive", r"\\servidor\pasta")  # rede nunca vira pasta pessoal
    guard = PathGuard(tmp_path / "projeto", outros_drives=lambda: False)
    assert all(not str(p).startswith("\\\\") for p in guard.personal_roots)


# ================================================================== preferencias
def test_salvar_permissoes_preserva_outras_chaves(prefs: Path) -> None:
    assert preferencias.atualizar({"voz": "Kore", "nome": "Ana"})
    assert preferencias.salvar_permissoes({**DESLIGADO, "internet": True})
    dados = json.loads(prefs.read_text(encoding="utf-8"))
    assert dados["voz"] == "Kore" and dados["nome"] == "Ana"
    assert dados["permissoes"] == {**DESLIGADO, "internet": True}
    assert preferencias.carregar_permissoes() == {**DESLIGADO, "internet": True}
    assert not list(prefs.parent.glob(".preferencias-*.tmp"))  # gravacao atomica


@pytest.mark.parametrize("dados", [None, {}, {"apps": True}, {**TUDO, "apps": "sim"}])
def test_salvar_permissoes_invalidas_nao_grava(prefs: Path, dados: object) -> None:
    assert preferencias.salvar_permissoes(TUDO)
    assert preferencias.salvar_permissoes(dados) is False
    assert preferencias.carregar_permissoes() == TUDO


def test_salvar_permissoes_falha_de_disco_devolve_false(
    prefs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    def falha(*_a: Any) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", falha)
    assert preferencias.salvar_permissoes(TUDO) is False
    assert preferencias.carregar_permissoes() == DESLIGADO


def test_quem_ja_usa_o_jarvis_comeca_desligado(prefs: Path) -> None:
    """Arquivo da versao anterior (sem a chave "permissoes"): tudo desligado."""
    assert preferencias.atualizar({"configurado": True, "voz": "Puck", "visual": "globo"})
    assert preferencias.carregar_permissoes() == DESLIGADO


# ================================================================== ponte JS
class _Controlador:
    def __init__(self) -> None:
        self.reinicios = 0
        self.rodando = True

    def iniciar(self) -> bool:
        return True

    def reiniciar(self) -> bool:
        self.reinicios += 1
        return True


def _api(**kwargs: Any) -> ApiJs:
    kwargs.setdefault("carregar_settings", lambda: Settings.from_env(exigir_chave=False))
    kwargs.setdefault("abrir_url", lambda url: True)
    kwargs.setdefault("abrir_pasta", lambda pasta: True)
    return ApiJs(**kwargs)


def test_metodos_novos_estao_na_lista_fechada() -> None:
    assert "permissoes_estado" in METODOS_PUBLICOS
    assert "salvar_permissoes" in METODOS_PUBLICOS
    assert list(METODOS_PUBLICOS) == sorted(METODOS_PUBLICOS)


def test_permissoes_estado(prefs: Path) -> None:
    estado = _api().permissoes_estado()
    assert estado["ok"] is True and estado["permissoes"] == DESLIGADO
    assert [n["id"] for n in estado["niveis"]] == list(permissoes.NIVEIS_ARQUIVOS)
    assert [c["id"] for c in estado["chaves"]] == ["apps", "internet", "email", "outros_drives"]
    assert estado["sempre_bloqueado"] == list(permissoes.SEMPRE_BLOQUEADO)
    excluir = estado["niveis"][-1]["descricao"]
    assert "Mesmo assim ele sempre pergunta antes de apagar" in excluir
    json.dumps(estado)  # vai para o JavaScript


def test_estado_config_traz_as_permissoes(prefs: Path) -> None:
    settings = Settings.from_env(exigir_chave=False)
    assert estado_config(settings)["permissoes"] == DESLIGADO
    preferencias.salvar_permissoes({**DESLIGADO, "apps": True})
    assert estado_config(settings)["permissoes"]["apps"] is True


def test_salvar_permissoes_vale_na_hora_sem_reiniciar(
    tmp_path: Path, casa: Path, prefs: Path
) -> None:
    controlador = _Controlador()
    api = _api(controlador=controlador)
    reg = _registry(tmp_path)
    assert "desligada" in reg.get("list_folder")(str(casa))
    resposta = api.salvar_permissoes({**DESLIGADO, "arquivos": "ler"})
    assert resposta["ok"] is True and resposta["mensagem"] == "Permissões salvas. Já valem agora."
    assert "desligada" not in reg.get("list_folder")(str(casa))
    assert controlador.reinicios == 0


MALICIOSOS: list[Any] = [
    None,
    0,
    True,
    "",
    "x" * 100_000,
    [],
    [TUDO],
    {},
    {"arquivos": "ler"},
    {**TUDO, "__proto__": {"apps": True}},
    {**TUDO, "constructor": 1},
    {**TUDO, "arquivos": "ler_gravar_excluir; rm -rf"},
    {**TUDO, "arquivos": {"toString": "ler"}},
    {**TUDO, "apps": "true"},
    {**TUDO, "apps": 1},
    {**TUDO, "email": [True]},
    {**TUDO, "outros_drives": {"valor": True}},
    {**TUDO, "arquivos": "x" * 100_000},
]


@pytest.mark.parametrize("dados", MALICIOSOS)
def test_salvar_permissoes_recusa_entrada_maliciosa(prefs: Path, dados: Any) -> None:
    api = _api()
    assert api.salvar_permissoes(DESLIGADO)["ok"] is True
    antes = prefs.read_bytes()
    resposta = api.salvar_permissoes(dados)
    assert resposta["ok"] is False and resposta["mensagem"]
    assert prefs.read_bytes() == antes


def test_salvar_permissoes_pela_ponte(prefs: Path) -> None:
    ponte = ponte_js(_api())
    assert ponte.salvar_permissoes(TUDO)["ok"] is True  # type: ignore[attr-defined]
    assert ponte.permissoes_estado()["permissoes"] == TUDO  # type: ignore[attr-defined]
    for nome in ("permissoes_estado", "salvar_permissoes"):
        funcao = getattr(ponte, nome)
        assert set(funcao.__globals__) <= {"__builtins__"}
        assert not funcao.__globals__.get("__builtins__")
        assert not hasattr(funcao, "__self__")
    assert ponte.salvar_permissoes()["ok"] is False  # type: ignore[attr-defined]


def test_salvar_permissoes_nunca_levanta(prefs: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def quebra(*_a: Any, **_k: Any) -> bool:
        raise RuntimeError("x")

    monkeypatch.setattr(preferencias, "salvar_permissoes", quebra)
    monkeypatch.setattr(preferencias, "carregar_permissoes", quebra)
    api = _api()
    assert api.salvar_permissoes(TUDO)["ok"] is False
    estado = api.permissoes_estado()
    assert estado["ok"] is False and estado["permissoes"] == DESLIGADO


# ================================================================== pagina
HTML = (Path(__file__).resolve().parents[1] / "src" / "jarvis" / "ui" / "orb.html").read_text(
    encoding="utf-8"
)


def test_aba_permissoes_entre_geral_e_chave() -> None:
    abas = re.findall(r'role="tab"[^>]*data-aba="([a-z]+)"', HTML)
    assert abas == ["geral", "permissoes", "chave", "elevenlabs", "sobre"]
    assert ">Permissões</button>" in HTML
    assert 'id="cfg-painel-permissoes" role="tabpanel"' in HTML


def test_passo_permissoes_antes_do_ultimo() -> None:
    passos = re.findall(r'<section class="passo" data-passo="(\d)"', HTML)
    assert passos == ["1", "2", "3", "4", "5", "6"]
    bloco = HTML.split('data-passo="5"', 1)[1].split('data-passo="6"', 1)[0]
    assert "Permissões" in bloco
    assert (
        "Por segurança, tudo começa desligado. Ligue só o que quiser — dá para mudar depois na "
        "engrenagem." in bloco
    )
    assert 'id="assist-pular"' in HTML and ">Pular</button>" in HTML


def test_copia_dos_textos_na_pagina_bate_com_o_python() -> None:
    """A pagina tem uma copia dos textos (fora do app); ela tem de ser igual a do Python."""
    descricao = permissoes.descricao_painel()
    textos = [
        texto
        for item in descricao["niveis"] + descricao["chaves"]
        for texto in (item["rotulo"], item["descricao"])
    ] + descricao["sempre_bloqueado"]
    for texto in textos:
        assert json.dumps(texto, ensure_ascii=False) in HTML, texto


def test_csp_continua_igual() -> None:
    assert (
        "default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline';"
        " img-src data:; media-src data:; font-src data:; connect-src 'none'; object-src 'none';"
        " frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'" in HTML
    )
    assert "innerHTML" not in HTML.split("function montarPermissoes", 1)[1].split("\n  }\n", 1)[0]
