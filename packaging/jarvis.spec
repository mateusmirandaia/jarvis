# PyInstaller spec do Jarvis (pasta "onedir", sem console).
#
# Gerar (na raiz do projeto):  pyinstaller --noconfirm --clean packaging/jarvis.spec
# Resultado: dist/Jarvis/Jarvis.exe (+ dist/Jarvis/_internal/). O build.ps1 faz tudo isso.
#
# Os arquivos da interface vao para jarvis/ui/ dentro do pacote: o codigo os acha pelo
# __file__ dos modulos (sys._MEIPASS/jarvis/ui/...), igual em desenvolvimento.
# ruff: noqa: F821  (Analysis, PYZ, EXE, COLLECT e SPECPATH sao injetados pelo PyInstaller)

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

RAIZ = Path(SPECPATH).resolve().parent
SRC = RAIZ / "src"
UI = SRC / "jarvis" / "ui"
ICONE = UI / "jarvis.ico"
ORB_HTML = UI / "orb.html"
VISUAIS = UI / "visuais"
AMOSTRAS = UI / "amostras"

for obrigatorio in (ORB_HTML, ICONE, VISUAIS):
    if not obrigatorio.exists():
        raise SystemExit(f"Arquivo obrigatorio nao encontrado: {obrigatorio}")

datas = [
    (str(ORB_HTML), "jarvis/ui"),
    (str(ICONE), "jarvis/ui"),
]
datas += [(str(js), "jarvis/ui/visuais") for js in sorted(VISUAIS.glob("*.js"))]
amostras = sorted(AMOSTRAS.glob("*.wav"))
if not amostras:
    print("AVISO: nenhuma amostra de voz em src/jarvis/ui/amostras (rode scripts/gerar_amostras_voz.py).")
datas += [(str(wav), "jarvis/ui/amostras") for wav in amostras]
if (AMOSTRAS / "LEIA.md").exists():
    datas.append((str(AMOSTRAS / "LEIA.md"), "jarvis/ui/amostras"))

binaries = []
hiddenimports = collect_submodules("jarvis")

# Pacotes com dados/submodulos carregados dinamicamente. Um pacote ausente (ex.: pywebview
# no Linux, onde o build serve so para conferir o spec) nao derruba o build.
for pacote in ("google.genai", "webview", "send2trash", "pyaudio", "clr_loader", "pythonnet"):
    try:
        d, b, h = collect_all(pacote)
    except Exception as erro:  # noqa: BLE001
        print(f"AVISO: nao consegui coletar {pacote}: {erro}")
        continue
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += [
    "dotenv",
    "httpx",
    "websockets",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
]
if sys.platform == "win32":
    hiddenimports += ["clr"]  # pythonnet: o backend WinForms/EdgeChromium do pywebview

a = Analysis(
    [str(Path(SPECPATH) / "jarvis_entry.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Jarvis",
    icon=str(ICONE),
    console=False,
    debug=False,
    strip=False,
    upx=False,  # UPX aumenta os falsos positivos de antivirus
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Jarvis",
)
