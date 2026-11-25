# Instalador do Jarvis (Windows)

Como gerar o `Jarvis-Setup-<versão>.exe`, testar e publicar. O instalador não pede
administrador, instala em `%LOCALAPPDATA%\Programs\Jarvis` e cria atalhos na Área de Trabalho e
no Menu Iniciar.

Arquivos envolvidos (pasta `packaging/`):

| Arquivo | O que faz |
|---|---|
| `jarvis_entry.py` | Ponto de entrada do executável (chama a mesma CLI do comando `jarvis`). |
| `jarvis.spec` | Receita do PyInstaller: pasta "onedir", sem console, com ícone, `orb.html`, visuais e amostras de voz. |
| `jarvis.iss` | Receita do Inno Setup 6: instalação por usuário, atalhos, desinstalador. |
| `build.ps1` | Faz tudo: ambiente de build, PyInstaller, Inno Setup e SHA-256. |

## Pré-requisitos (só na máquina que GERA o instalador)

- **Windows 10/11 64 bits.**
- **Python 3.12** ([python.org/downloads/release/python-31210](https://www.python.org/downloads/release/python-31210/),
  "Windows installer (64-bit)"; marque "Add python.exe to PATH").
  O `build.ps1` usa `py -3.12` (ou `python`, se o lançador `py` não existir).
- **Inno Setup 6** ([jrsoftware.org/isdl.php](https://jrsoftware.org/isdl.php)) ou
  `winget install JRSoftware.InnoSetup`. O script acha o `ISCC.exe` no PATH ou nas pastas padrão.

Quem só **usa** o Jarvis não precisa de nada disso: o instalador já leva o Python junto.

## 1. Gerar as amostras de voz (uma vez)

As amostras tocam no botão **Ouvir** dos cartões de voz. Com a sua chave no `.env` do projeto
(ou na variável `GEMINI_API_KEY`):

```powershell
.venv\Scripts\activate
python scripts\gerar_amostras_voz.py
```

Gera `src\jarvis\ui\amostras\<Voz>.wav` para as 8 vozes, pulando as que já existem
(`--forcar` refaz, `--vozes Puck,Kore` escolhe, `--modelo` troca o modelo de TTS). Ele espera
uns segundos entre as vozes por causa do limite da conta grátis; se bater na cota, avisa e é só
rodar de novo mais tarde. Sem as amostras o instalador funciona, mas o Ouvir mostra
"amostra indisponível".

## 2. Gerar o instalador (1 comando)

No PowerShell, na raiz do projeto:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

No fim aparecem o caminho (`dist\Jarvis-Setup-<versão>.exe`) e o **SHA-256** (também salvo em
`dist\Jarvis-Setup-<versão>.exe.sha256.txt`). A versão vem do `pyproject.toml`.

Opções: `-SoExecutavel` (para depois do PyInstaller; teste `dist\Jarvis\Jarvis.exe` direto),
`-Limpar` (recria o `.venv-build` do zero), `-Python "C:\caminho\python.exe"`.

## 3. Testar numa máquina limpa

Use um PC sem Python, ou uma máquina virtual / **Windows Sandbox** (Recursos do Windows >
"Área Restrita do Windows"):

1. Copie o `Jarvis-Setup-<versão>.exe` e dê dois cliques. Não deve pedir senha de administrador.
2. Confira: atalho **Jarvis** na Área de Trabalho e no Menu Iniciar, com o ícone.
3. Abra: deve aparecer o assistente de configuração (boas-vindas → chave → microfone →
   personalizar → pronto). Teste a chave, o microfone e o Ouvir de cada voz.
4. Feche e abra de novo: deve ir direto para o visual salvo, sem configuração.
5. Rode o instalador de novo por cima (atualização): as configurações continuam.
6. Desinstale (Configurações > Aplicativos): ele pergunta se quer apagar as configurações.
   "Não" mantém `%APPDATA%\Jarvis`; "Sim" apaga.

Se a janela não abrir, veja o log (abaixo). No Windows 10 antigo pode faltar o **WebView2**
([developer.microsoft.com/microsoft-edge/webview2](https://developer.microsoft.com/microsoft-edge/webview2/)).

## Aviso do SmartScreen (instalador sem assinatura)

O instalador **não tem assinatura digital** (certificado pago). Na primeira vez o Windows mostra
"O Windows protegeu o computador". Para instalar:

1. Clique em **"Mais informações"**;
2. Clique em **"Executar assim mesmo"**.

Explique isso na página de download, junto com o link do VirusTotal e o SHA-256, para a pessoa
conferir que o arquivo é o mesmo que você publicou. Alguns antivírus podem acusar falso positivo
em executáveis do PyInstaller; o UPX fica desligado para reduzir isso.

## Enviar ao VirusTotal e publicar

1. Abra [virustotal.com](https://www.virustotal.com), aba **File**, envie o `Jarvis-Setup-<versão>.exe`.
2. Espere a análise e copie o link da página do resultado (ela mostra o mesmo SHA-256 do build).
3. Na release do GitHub (ou na página de download), publique: o instalador, o SHA-256 e o link
   do VirusTotal. Para quem quiser conferir no próprio PC:
   ```powershell
   Get-FileHash .\Jarvis-Setup-<versão>.exe -Algorithm SHA256
   ```

## Onde ficam os dados do usuário

| O quê | Onde |
|---|---|
| Programa | `%LOCALAPPDATA%\Programs\Jarvis\` (apagado ao desinstalar) |
| Chave do Google e do ElevenLabs | `%APPDATA%\Jarvis\.env` |
| Preferências (voz, nome, visual, fone) | `%APPDATA%\Jarvis\preferencias.json` |
| Logs | `%APPDATA%\Jarvis\logs\jarvis.log` |

A pasta `%APPDATA%\Jarvis` **não** é apagada pelo desinstalador sem perguntar.
