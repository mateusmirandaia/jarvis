<#
.SYNOPSIS
    Gera o instalador do Jarvis: dist\Jarvis-Setup-<versao>.exe

.DESCRIPTION
    1. cria (ou reaproveita) o ambiente de build .venv-build na raiz do projeto;
    2. instala o Jarvis e o PyInstaller nele;
    3. roda o PyInstaller com packaging\jarvis.spec (gera dist\Jarvis\Jarvis.exe);
    4. acha o ISCC.exe do Inno Setup 6 e compila packaging\jarvis.iss;
    5. mostra o caminho e o SHA-256 do instalador (para o VirusTotal e a pagina de download).

    Uso (PowerShell, na raiz do projeto):
        powershell -ExecutionPolicy Bypass -File packaging\build.ps1

.PARAMETER Python
    Comando do Python usado para criar o ambiente de build (padrao: "py -3.12", ou "python").

.PARAMETER SoExecutavel
    Para depois do PyInstaller (nao precisa do Inno Setup).

.PARAMETER Limpar
    Apaga o .venv-build antes, para um build do zero.
#>
[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$SoExecutavel,
    [switch]$Limpar
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Escrever([string]$texto) { Write-Host "==> $texto" -ForegroundColor Cyan }
function Falhar([string]$texto) {
    Write-Host ""
    Write-Host "ERRO: $texto" -ForegroundColor Red
    exit 1
}
function Conferir([string]$etapa) {
    if ($LASTEXITCODE -ne 0) { Falhar "$etapa terminou com erro (codigo $LASTEXITCODE). Veja as mensagens acima." }
}

$Raiz = Split-Path -Parent $PSScriptRoot
$Spec = Join-Path $PSScriptRoot "jarvis.spec"
$Iss = Join-Path $PSScriptRoot "jarvis.iss"
$Venv = Join-Path $Raiz ".venv-build"
$Dist = Join-Path $Raiz "dist"
$Work = Join-Path $Raiz "build"
$PastaApp = Join-Path $Dist "Jarvis"

Set-Location $Raiz

# --- versao (pyproject.toml) -------------------------------------------------------------
$linhaVersao = Select-String -Path (Join-Path $Raiz "pyproject.toml") -Pattern '^\s*version\s*=\s*"([^"]+)"' |
    Select-Object -First 1
if (-not $linhaVersao) { Falhar "nao achei a linha version = ""..."" no pyproject.toml." }
$Versao = $linhaVersao.Matches[0].Groups[1].Value
Escrever "Jarvis versao $Versao"

# --- Python e ambiente de build ----------------------------------------------------------
if ($Limpar -and (Test-Path $Venv)) {
    Escrever "Apagando o ambiente de build antigo"
    Remove-Item -Recurse -Force $Venv
}
$PyVenv = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $PyVenv)) {
    if (-not $Python) {
        if (Get-Command py -ErrorAction SilentlyContinue) { $Python = "py -3.12" }
        elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" }
        else { Falhar "nao achei o Python. Instale o Python 3.12 de https://www.python.org/downloads/ (marque 'Add Python to PATH')." }
    }
    Escrever "Criando o ambiente de build em .venv-build (com: $Python)"
    $partes = $Python -split " "
    $exe = $partes[0]
    $resto = @()
    if ($partes.Count -gt 1) { $resto = $partes[1..($partes.Count - 1)] }
    & $exe @resto -m venv $Venv
    Conferir "A criacao do ambiente de build"
}

Escrever "Instalando o Jarvis e o PyInstaller no ambiente de build"
& $PyVenv -m pip install --upgrade pip --quiet
Conferir "A atualizacao do pip"
& $PyVenv -m pip install $Raiz pyinstaller --quiet
Conferir "A instalacao das dependencias"

# --- amostras de voz -----------------------------------------------------------------------
$amostras = @(Get-ChildItem -Path (Join-Path $Raiz "src\jarvis\ui\amostras") -Filter *.wav -ErrorAction SilentlyContinue)
if ($amostras.Count -eq 0) {
    Write-Host "AVISO: nenhuma amostra de voz encontrada. O botao Ouvir vai mostrar 'amostra indisponivel'." -ForegroundColor Yellow
    Write-Host "       Para gerar: python scripts\gerar_amostras_voz.py" -ForegroundColor Yellow
} else {
    Escrever "$($amostras.Count) amostra(s) de voz vao no pacote"
}

# --- PyInstaller ---------------------------------------------------------------------------
Escrever "Gerando o executavel com o PyInstaller (demora alguns minutos)"
& $PyVenv -m PyInstaller --noconfirm --clean --distpath $Dist --workpath $Work $Spec
Conferir "O PyInstaller"
$Exe = Join-Path $PastaApp "Jarvis.exe"
if (-not (Test-Path $Exe)) { Falhar "o PyInstaller terminou, mas nao achei $Exe." }
Escrever "Executavel pronto: $Exe"

if ($SoExecutavel) {
    Escrever "Parando aqui (-SoExecutavel). Teste abrindo $Exe"
    exit 0
}

# --- Inno Setup ----------------------------------------------------------------------------
$candidatos = @()
$noPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($noPath) { $candidatos += $noPath.Source }
foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles, (Join-Path $env:LOCALAPPDATA "Programs"))) {
    if ($base) { $candidatos += (Join-Path $base "Inno Setup 6\ISCC.exe") }
}
$Iscc = $candidatos | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $Iscc) {
    Falhar ("nao achei o Inno Setup 6 (ISCC.exe). Baixe e instale de https://jrsoftware.org/isdl.php " +
        "(ou rode: winget install JRSoftware.InnoSetup) e rode este script de novo. " +
        "O executavel ja esta pronto em $PastaApp.")
}

Escrever "Compilando o instalador com $Iscc"
& $Iscc "/DAppVersion=$Versao" "/DDistDir=$PastaApp" "/O$Dist" $Iss
Conferir "O Inno Setup"

$Setup = Join-Path $Dist "Jarvis-Setup-$Versao.exe"
if (-not (Test-Path $Setup)) { Falhar "o Inno Setup terminou, mas nao achei $Setup." }

$Hash = (Get-FileHash -Algorithm SHA256 -Path $Setup).Hash.ToLower()
$ArquivoHash = "$Setup.sha256.txt"
"$Hash  Jarvis-Setup-$Versao.exe" | Out-File -FilePath $ArquivoHash -Encoding ascii

Write-Host ""
Write-Host "Instalador pronto!" -ForegroundColor Green
Write-Host "  Arquivo: $Setup"
Write-Host "  SHA-256: $Hash"
Write-Host "  (o SHA-256 tambem ficou salvo em $ArquivoHash)"
Write-Host ""
Write-Host "Proximo passo: envie o instalador ao https://www.virustotal.com e publique o link junto com o SHA-256."
