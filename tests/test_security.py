"""Testes do PathGuard e do normalize (tools/security.py)."""

from __future__ import annotations

from pathlib import Path

from jarvis.tools.security import (
    EXECUTABLE_EXTENSIONS,
    PROTECTED_PROCESSES,
    PathGuard,
    normalize,
)


def test_normalize_remove_acentos_maiusculas_e_espacos() -> None:
    assert normalize("  Área de Trabalho  ") == "area de trabalho"
    assert normalize("RELATÓRIO Ação") == "relatorio acao"
    assert normalize("downloads") == "downloads"


def test_user_folders_tem_os_tres_atalhos(guard: PathGuard, home: Path) -> None:
    pastas = guard.user_folders()
    assert set(pastas) >= {"area de trabalho", "documentos", "downloads"}
    assert pastas["area de trabalho"] == home / "Desktop"
    assert pastas["documentos"] == home / "Documents"
    assert pastas["downloads"] == home / "Downloads"


def test_user_folders_prefere_onedrive(project_root: Path, home: Path) -> None:
    onedrive_desktop = home / "OneDrive" / "Desktop"
    onedrive_desktop.mkdir(parents=True)
    guard = PathGuard(project_root=project_root, home=home)
    assert guard.user_folders()["area de trabalho"] == onedrive_desktop


def test_resolve_atalho_sozinho(guard: PathGuard, home: Path) -> None:
    assert guard.resolve("area de trabalho") == home / "Desktop"
    assert guard.resolve("Downloads") == home / "Downloads"


def test_resolve_atalho_com_acento_e_maiuscula(guard: PathGuard, home: Path) -> None:
    assert guard.resolve("Área de Trabalho") == home / "Desktop"
    assert guard.resolve("Documentos\\Notas") == home / "Documents" / "Notas"


def test_resolve_atalho_com_subpasta(guard: PathGuard, home: Path) -> None:
    assert guard.resolve("area de trabalho\\Fotos") == home / "Desktop" / "Fotos"
    assert guard.resolve("area de trabalho/Fotos") == home / "Desktop" / "Fotos"


def test_resolve_tira_aspas_e_espacos(guard: PathGuard, home: Path) -> None:
    assert guard.resolve('  "downloads"  ') == home / "Downloads"


def test_resolve_caminho_completo(guard: PathGuard, tmp_path: Path) -> None:
    alvo = tmp_path / "qualquer" / "lugar"
    assert guard.resolve(str(alvo)) == alvo


def test_resolve_letra_de_disco_vira_raiz(guard: PathGuard) -> None:
    assert str(guard.resolve("C:")) in ("C:\\", "C:/")


def test_is_protected_pasta_do_projeto(guard: PathGuard, project_root: Path) -> None:
    assert guard.is_protected(project_root)
    assert guard.is_protected(project_root / ".env")
    assert guard.is_protected(project_root / "src" / "jarvis")


def test_is_protected_nao_engana_com_ponto_ponto(guard: PathGuard, project_root: Path) -> None:
    truque = project_root / "src" / ".." / ".env"
    assert guard.is_protected(truque)


def test_is_protected_raiz_do_disco(guard: PathGuard, tmp_path: Path) -> None:
    assert guard.is_protected(Path(tmp_path.anchor))


def test_pastas_do_usuario_nao_sao_protegidas(guard: PathGuard, home: Path, tmp_path: Path) -> None:
    assert not guard.is_protected(home / "Desktop")
    assert not guard.is_protected(home / "Desktop" / "Fotos")
    assert not guard.is_protected(tmp_path / "livre")


def test_pasta_com_nome_parecido_nao_e_protegida(guard: PathGuard, project_root: Path) -> None:
    vizinha = project_root.parent / (project_root.name + "_copia")
    assert not guard.is_protected(vizinha)


def test_constantes_de_seguranca() -> None:
    nomes = {normalize(p).removesuffix(".exe") for p in PROTECTED_PROCESSES}
    for processo in ("explorer", "svchost", "python", "powershell", "cmd", "conhost"):
        assert processo in nomes
    for ext in (".exe", ".bat", ".ps1", ".cmd", ".vbs", ".msi"):
        assert ext in EXECUTABLE_EXTENSIONS
