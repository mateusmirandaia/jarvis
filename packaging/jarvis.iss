; Instalador do Jarvis (Inno Setup 6).
;
; Normalmente rodado pelo packaging\build.ps1, que passa a versao lida do pyproject.toml:
;   ISCC.exe /DAppVersion=0.8.0 /DDistDir=<raiz>\dist\Jarvis packaging\jarvis.iss
;
; Instala SEM pedir administrador, na pasta do usuario. A desinstalacao remove o programa,
; mas NAO apaga as configuracoes (%APPDATA%\Jarvis: chave, preferencias e logs) sem perguntar.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist\Jarvis"
#endif
#define AppName "Jarvis"
#define AppExe "Jarvis.exe"

[Setup]
AppId={{6F1C2B9E-3D47-4A8B-9C51-7E2A0D4B8F13}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Mateus Miranda
AppPublisherURL=https://github.com/mateusmirandaia/jarvis
AppSupportURL=https://github.com/mateusmirandaia/jarvis
DefaultDirName={localappdata}\Programs\Jarvis
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Pasta fixa: o [UninstallDelete] apaga {app} inteiro, entao a pessoa nao pode escolher
; uma pasta com outras coisas dentro (ex.: Documentos).
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Jarvis-Setup-{#AppVersion}
SetupIconFile=..\src\jarvis\ui\jarvis.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Mesmo mutex que o Jarvis cria ao abrir: o instalador pede para fechar o Jarvis antes.
AppMutex=Local\JarvisSemHype.Orb
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\src\jarvis\ui\jarvis.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\jarvis.ico"; Comment: "Jarvis - assistente de voz"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\jarvis.ico"; Comment: "Jarvis - assistente de voz"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Somente a pasta do programa. %APPDATA%\Jarvis e tratado no [Code], perguntando antes.
Type: filesandordirs; Name: "{app}"

[Code]
// Pasta unica aceita. DisableDirPage esconde a escolha, mas "Jarvis-Setup.exe /DIR=..." ainda
// mudaria {app}; como o [UninstallDelete] apaga {app} inteiro, outra pasta (ex.: Documentos)
// seria apagada ao desinstalar. Por isso instalar e desinstalar fora dela e recusado.
function PastaEsperada(): String;
begin
  Result := ExpandConstant('{localappdata}\Programs\Jarvis');
end;

function PastaDoAppValida(): Boolean;
begin
  Result := CompareText(RemoveBackslashUnlessRoot(ExpandConstant('{app}')), PastaEsperada()) = 0;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not PastaDoAppValida() then
    Result := 'O Jarvis só pode ser instalado em ' + PastaEsperada() + '.' + #13#10 +
              'Rode o instalador sem o parâmetro /DIR.';
end;

function InitializeUninstall(): Boolean;
begin
  Result := PastaDoAppValida();
  if not Result then
    MsgBox('Este Jarvis está numa pasta inesperada (' + ExpandConstant('{app}') + ').' + #13#10 +
           'Para não apagar outros arquivos, a desinstalação automática foi cancelada.' + #13#10 +
           'Apague manualmente só os arquivos do Jarvis.', mbError, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PastaConfig: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    PastaConfig := ExpandConstant('{userappdata}\Jarvis');
    if DirExists(PastaConfig) and (not UninstallSilent) then
    begin
      if MsgBox('Deseja apagar também as suas configurações do Jarvis?' + #13#10 + #13#10 +
                'Isso inclui a sua chave do Google, as preferências (voz, nome, visual) e os logs, em:' + #13#10 +
                PastaConfig + #13#10 + #13#10 +
                'Escolha "Não" para mantê-las (útil se for instalar de novo).',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(PastaConfig, True, True, True);
      end;
    end;
  end;
end;
