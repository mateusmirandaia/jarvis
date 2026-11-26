# Segurança do Jarvis

O Jarvis mexe no seu computador. Por isso ele segue regras fixas, escritas no código, que a
IA **não consegue mudar** — nem se alguém pedir com jeitinho. Estas regras valem para todo
mundo que baixar o projeto, seja pelo instalador, seja pelo código.

## 1. Lista fechada de ações

- A IA só pode escolher entre as ferramentas registradas no `ToolRegistry`
  (`src/jarvis/tools/__init__.py`). Qualquer outro nome é recusado.
- **Nunca** existe uma ferramenta de "rodar comando no terminal".
- Ferramentas que existem: data e hora; listar, abrir e fechar apps; abrir sites e pesquisar;
  criar, listar, localizar, abrir, mover/renomear e copiar arquivos e pastas; criar arquivo de
  texto; mandar para a Lixeira (com confirmação manual).
- As regras detalhadas de cada ferramenta de arquivo e de aplicativo estão na seção
  [Regras das ferramentas](#regras-das-ferramentas).

## 1.1 Permissões (tudo começa desligado)

Por cima da lista fechada, a pessoa escolhe na aba **Permissões** o que o Jarvis pode fazer.
O padrão é **tudo desligado** (vale também para quem já usava uma versão anterior). A checagem
acontece **na hora de cada chamada**, dentro do `ToolRegistry`, lendo as preferências atuais:
a IA não consegue contornar, e mudar no painel vale na hora. Ferramenta que não está no mapa
de exigências fica bloqueada. Se as permissões não puderem ser lidas, tudo conta como
desligado. Com **Outros discos** desligado, o `PathGuard` recusa qualquer caminho fora da
pasta do usuário e do OneDrive (depois de seguir links e `..`).

Ler arquivos (`read_file`) segue as mesmas regras de `open_file` (lista positiva de
extensões, sem `.env`/segredos, sem pastas protegidas, sem rede), com limite de tamanho e de
descompactação para `.docx`/`.xlsx`. O texto lido vai para o Google, e isso está avisado no
README. E-mail (`draft_email`) **nunca é enviado**: o Jarvis só abre o e-mail pronto (`mailto:`
ou `.eml` com `X-Unsent: 1`); quebra de linha em destinatário ou assunto é recusada.

## 2. Apagar exige ação manual

- `delete_to_trash` abre uma **janela do Windows** ("Jarvis - confirmação manual") com
  os botões Sim/Não, sempre na frente das outras janelas.
- **Só o seu clique em "Sim" autoriza.** A IA não tem como clicar nem confirmar por você.
  Se você clicar em "Não" ou fechar a janela, nada é apagado.
- A janela tem **prazo**: ela fica aberta por até 110 segundos e depois **fecha sozinha**,
  o que conta como "Não". O Jarvis espera até 120 segundos pela ferramenta; como a janela
  sempre fecha antes (10 segundos de folga), não existe a situação "a IA desistiu, mas a
  janela continuou aberta e um clique atrasado apagou o arquivo".
- Se o Windows não tiver a função de janela com prazo (`MessageBoxTimeoutW`), o pedido é
  recusado por segurança.
- O item vai para a **Lixeira** (biblioteca `send2trash`), nunca é apagado de vez.
  Dá para recuperar.
- Antes de apagar, a personalidade manda o Jarvis localizar o arquivo e dizer o nome
  em voz alta.
- Fora do Windows não existe a janela de confirmação, então apagar é sempre recusado.

## 3. Pastas protegidas

Nada é criado, movido, copiado para dentro ou apagado em:

- a **raiz do disco** em si (por exemplo `C:\`);
- a pasta do **Windows** (`%SystemRoot%`);
- **Arquivos de Programas** e **Arquivos de Programas (x86)**;
- **ProgramData**;
- a **pasta do próprio Jarvis** (o código ou, no instalado, `%LOCALAPPDATA%\Programs\Jarvis`);
- a **pasta das configurações**, `%APPDATA%\Jarvis` (onde ficam o `.env` com as chaves, o
  `preferencias.json` e, no instalado, os logs).

A verificação é feita pelo `PathGuard.is_protected()` (`src/jarvis/tools/security.py`),
sempre com o caminho já resolvido (sem truques com `..`). O `ToolRegistry` passa a pasta das
configurações como pasta protegida extra. A busca de arquivos também pula pastas protegidas e
pastas ocultas (que começam com `.` ou `$`).

## 4. Nunca sobrescreve

- Mover, renomear, copiar ou criar arquivo de texto com um nome que **já existe** é recusado.
- Criar uma pasta que já existe não faz nada (só avisa).
- Arquivos de texto criados pelo Jarvis são sempre `.txt` ou `.md`.

## 5. Processos protegidos

O Jarvis não fecha processos do sistema nem o terminal em que ele mesmo está rodando:
`explorer`, `svchost`, `csrss`, `winlogon`, `lsass`, `services`, `smss`, `wininit`, `dwm`,
`msmpeng` (antivírus), `python`, `pythonw`, `py`, `powershell`, `pwsh`, `cmd`,
`windowsterminal`, `conhost`, `openconsole`.

Fechar um app é feito como se você clicasse no X (o app pode perguntar se quer salvar).
Fechar **à força** só acontece quando você pede explicitamente.

## 6. Onde fica a sua chave

- Quem configura pela janela: a chave do Google (e a do ElevenLabs, se usar) fica em
  **`%APPDATA%\Jarvis\.env`** (`~/.config/jarvis/.env` fora do Windows). Essa pasta é sua,
  fica fora da pasta do programa e é **protegida** contra as ações da IA (seção 3).
- Quem é desenvolvedor pode ter também um `.env` na pasta do projeto ou uma variável de
  ambiente `GEMINI_API_KEY`. O `.env` está no `.gitignore` e **nunca** vai para o GitHub; o
  repositório traz só o `.env.example`, sem chave.
- A janela grava o `.env` do usuário de forma atômica e só aceita as variáveis das chaves, com
  caracteres seguros (sem quebra de linha, aspas, espaço, `#` ou `$`), para ninguém injetar
  outra configuração pelo valor colado. O `.env` do projeto nunca é alterado pela janela.
- A chave **não aparece** no terminal, no log nem na janela: a janela mostra só os 4 últimos
  caracteres (`…abcd`). Todo texto que vai para o log passa por um filtro que troca chaves por
  `…` (inclusive em URLs com `?key=` dentro de mensagens de erro de bibliotecas).
- A chave só sai do seu computador para o próprio serviço (Google ou ElevenLabs).
- Em gravações e lives, **nunca abra o `.env` na tela** e não use o botão **Mostrar** do campo
  da chave. Se a chave vazar, apague-a no Google AI Studio e crie outra (engrenagem > **Chave
  do Google**).
- Ao desinstalar, o instalador **pergunta** antes de apagar `%APPDATA%\Jarvis`.

## 7. A janela só faz o que está na lista

A página da janela (HTML/JavaScript) conversa com o Python pelo pywebview. O pywebview
executaria **qualquer** função que a página pedisse, por isso:

- a janela recebe uma ponte (`ponte_js`, em `src/jarvis/ui/api_config.py`) com **só 15
  funções** (testar e salvar a chave, salvar preferências, vozes, microfone, ElevenLabs,
  aplicar, abrir link); nada de atributos internos;
- nenhuma função devolve uma chave inteira, e nenhuma levanta erro para a página (erro vira
  uma mensagem simples);
- `abrir_link` só aceita **nomes** de uma lista fechada (página da chave do Google, ElevenLabs,
  repositório, Instagram, pasta das configurações e pasta dos logs). A página nunca manda um
  endereço;
- os dados que a página envia (nome, voz, fone, fonte da voz, visual) são validados no Python:
  nome com até 40 caracteres numa linha, voz só da lista das 8, visual só da lista dos 9;
- a página é montada pelo próprio Jarvis, sem internet e sem bibliotecas externas; textos
  vindos de fora (falas, nomes de vozes) entram na página sempre como texto, nunca como HTML,
  e a configuração inicial é injetada como JSON escapado.

## 8. Erros não vazam detalhes técnicos

- Cada ferramenta passa pelo `safe_tool`: se algo der errado, o erro completo vai para o log e
  a IA recebe só uma frase simples para falar (por exemplo: "o Windows não me deu permissão
  para isso").
- Resultados longos são cortados em 700 caracteres para não encher a conversa.
- Cada ferramenta tem tempo máximo (20 s; 120 s para apagar, com a janela de confirmação
  fechando sozinha 10 s antes). Se passar disso, o Jarvis desiste e avisa.
- Logs: `logs\jarvis.log` na pasta do projeto (código) ou `%APPDATA%\Jarvis\logs\jarvis.log`
  (instalado).

## 9. Instalador

- O instalador não pede administrador e instala só para o seu usuário.
- Ele **não tem assinatura digital** (certificado pago), então o Windows mostra "O Windows
  protegeu o computador". Baixe só da página oficial de Releases do GitHub e confira o SHA-256
  e o link do VirusTotal publicados junto com o arquivo. Detalhes em [INSTALADOR.md](INSTALADOR.md).

## 10. Voz e imagem

- A voz padrão é uma voz pronta do Google. Com o ElevenLabs, **só clone a sua própria voz**
  ou a de alguém que autorizou. Nunca clone a voz de um ator ou de outra pessoa sem
  autorização dela.
- "Jarvis" é só um apelido; o projeto não é afiliado à Marvel, à Disney nem ao Google.

## Regras das ferramentas

Correção de segurança de 25/11/2026. Código em `src/jarvis/tools/` e
`src/jarvis/ui/api_config.py`; cada regra tem teste em `tests/test_seguranca_ferramentas.py`.

### Caminhos

- O Jarvis aceita caminho completo ou os atalhos falados **área de trabalho**, **documentos**,
  **downloads**, **imagens**, **músicas** e **vídeos** (OneDrive primeiro).
- **Variáveis não são expandidas** (`%APPDATA%`, `$HOME`): o texto vem da IA e pode ter sido
  "soprado" por um vídeo ou uma live.
- **Rede e dispositivo são recusados**: `\\servidor\pasta`, `//servidor/pasta`,
  `\\host@SSL\DavWWWRoot`, `\\localhost\C$`, `\\?\C:\...`, `\\.\C:`. Uma unidade
  mapeada de rede também conta como protegida.
- **Nomes que o Windows trata de um jeito especial são recusados**: ponto ou espaço no fim
  (`evil.bat.`), `:` no nome (fluxo alternativo, `nota.txt:oculto`), nomes de dispositivo
  (`CON`, `NUL`, `COM1`…), nomes curtos 8.3 (`PROGRA~1`), pastas-atalho do sistema
  (`pasta.{CLSID}`) e os caracteres `< > " | ? *`.

### Pastas e arquivos protegidos

Além das pastas da seção 3, também são protegidas a pasta **`AppData`** inteira do usuário
(onde ficam o **Menu Iniciar** e a pasta **Inicializar**, que roda programas no login), a
pasta de `%APPDATA%`, as pastas de perfil do PowerShell (`Documentos\WindowsPowerShell` e
`Documentos\PowerShell`) e as pastas de chaves `.ssh`, `.aws`, `.azure`, `.kube`, `.gnupg`
e `.docker`.

Pasta protegida não é **lida, listada, procurada, aberta, copiada, movida, criada nem
apagada** — nem como origem, nem como destino. A listagem de uma pasta comum também esconde as
subpastas protegidas.

Arquivos com cara de guardar senha ou chave (`.env`, `.env.*`, `id_rsa`, `id_ed25519`,
`.pem`, `.key`, `.pfx`, `.p12`, `.ppk`, `.kdbx`, `.ovpn`, `.git-credentials`, `.npmrc`,
`.pypirc`, `.netrc`, `credentials.json`, os bancos de senhas dos navegadores…) **não são
abertos, copiados nem movidos**, em qualquer pasta. Uma pasta que tenha um desses arquivos,
um atalho para outra pasta (link simbólico ou junção) ou uma pasta protegida dentro dela
também não é copiada nem movida.

### `open_file`: lista positiva

Abre só pastas (no Explorer) e estas extensões:

- documentos: `.pdf .doc .docx .odt .rtf .txt .md .csv .xls .xlsx .ods .ppt .pptx .odp .epub .log`
- imagens: `.jpg .jpeg .png .gif .webp .bmp .tif .tiff .heic`
- áudio: `.mp3 .wav .m4a .aac .flac .ogg .opus .wma`
- vídeo: `.mp4 .m4v .mkv .avi .mov .wmv .webm`
- compactado: `.zip`

Todo o resto é recusado ("Senhor, não posso abrir esse tipo de arquivo por segurança."),
inclusive `.exe .bat .cmd .ps1 .vbs .js .lnk .url .py .msi .msc .cpl .hta .iso .vhd .chm
.docm .xlsm .html .svg`. Um link simbólico com nome de `.pdf` que aponta para um programa
também é recusado (a extensão do alvo real é conferida).

### Mover, renomear e copiar

- **A extensão não muda.** Renomear `nota.txt` para `nota.bat` (ou `.cmd`, `.url`, `.lnk`…)
  é recusado. Trocas aceitas: `.txt` ↔ `.md`, `.jpg` ↔ `.jpeg`, `.tif` ↔ `.tiff`.
- Pastas podem ganhar qualquer nome comum, menos um nome de programa ou atalho (`x.exe`).
- Nunca sobrescreve (como antes).
- **Pastas pessoais inteiras** (a pasta do usuário, OneDrive, Área de Trabalho, Documentos,
  Downloads, Imagens, Músicas, Vídeos, e qualquer pasta que contenha uma delas, como
  `C:\Users`) não são movidas, renomeadas nem apagadas. Subpastas delas continuam livres.
- **Cópia até 2 GB e 20 mil itens.** Acima disso a cópia passaria do tempo da ferramenta;
  use o Explorer. Mover para outro disco segue o mesmo limite.

### Apagar

- Enquanto a janela "Sim/Não" está aberta, **nenhuma outra ação altera arquivos** (mover,
  copiar, criar, apagar respondem "estou esperando a sua confirmação na janela"). Listar e
  procurar continuam funcionando.
- O Jarvis guarda a identidade do item (id do arquivo, disco, tamanho e data) antes da
  janela; se ela mudar até o clique, **nada é apagado**.
- **Pendrive, cartão, CD e rede** não têm Lixeira (o item seria apagado de vez): apagar ali é
  recusado. Só disco interno.

### `open_app`

- Abre os apps conhecidos pelo nome (calculadora, bloco de notas, paint, explorador de
  arquivos, navegador, chrome, edge, word, excel, powerpoint, vs code, spotify, whatsapp) e,
  se não for um deles (ou ele não abrir), procura um **atalho `.lnk` do Menu Iniciar** (do
  usuário e de todos os usuários) pelo nome exibido e abre o atalho.
- **Nunca** executa um nome do PATH, da pasta atual ou um caminho (`C:\...\x.exe`).
- **Nunca** abre, mesmo que exista atalho: `cmd`, `powershell`, `pwsh`, Windows Terminal,
  `regedit`, `mshta`, `wscript`, `cscript`, `rundll32`, `certutil`, `bitsadmin`, `msiexec`,
  `logoff`, `shutdown`, `taskkill`, `reg`, `schtasks`, `sc`, `net`, `diskpart`, `format`,
  `bcdedit`, `wmic`, `mmc`, `control`, `msconfig`, `python`, `bash`/`wsl`, prompts de comando
  e desinstaladores. O Jarvis lê o alvo do `.lnk` (caminho, argumentos e variáveis como
  `%windir%\system32\cmd.exe`) e recusa se ele apontar para um desses programas ou para algo
  que não seja `.exe` (`.bat`, `.msc`, `.cpl`…). Atalhos das pastas **Ferramentas do
  Windows**, **Ferramentas Administrativas**, **Sistema do Windows** e **Windows PowerShell**
  não são abertos.
- Nome ambíguo: o Jarvis pergunta qual (até 5 opções).

### `close_app`

- O nome precisa ter **pelo menos 3 letras**.
- Casa pelo app conhecido, pelo nome exato do processo (`firefox` = `firefox.exe`) ou por
  **palavra inteira** do título da janela (`tese` casa "Tese_final.docx", `ese` não).
- Se o nome casar janelas de **mais de um programa**, o Jarvis pergunta qual em vez de fechar
  (os apps conhecidos, como "navegador", fecham todas as janelas deles do jeito normal).
- **À força** só um programa por vez; se casar mais de um, ele pergunta.
- Nunca fecha: o próprio Jarvis (`jarvis.exe`, `python`, `pythonw`, o WebView2), os da
  seção 5 e `sihost`, `ctfmon`, `fontdrvhost`, `shellexperiencehost`,
  `startmenuexperiencehost`, `searchhost`, `textinputhost`, `runtimebroker`,
  `applicationframehost`, `lockapp`.

### Tempo esgotado

Se uma ação passa do tempo, o Jarvis avisa que **ela pode ter terminado mesmo assim** e pede
para conferir antes de repetir (a ação não é cancelada no meio; por isso a cópia tem limite
de tamanho).

### A janela (pywebview)

- O pywebview resolve o nome chamado pela página com `getattr` encadeado (`a.b.c`, sem
  filtrar `__`). A ponte `ponte_js` agora é uma classe só com `__slots__`; cada uma das 15
  funções fica num slot (sem `__self__`/`__func__`), foi criada num espaço de nomes vazio
  (`__globals__` e `__builtins__` vazios) e guarda o método só na closure. Um teste varre
  todos os nomes `a.b.c.d` a partir da ponte e prova que nenhum chega a módulos, aos globais
  do Python, à `ApiJs`, a métodos ou a células da closure.
- `LINKS` é somente leitura e `abrir_link` só abre `https://` dos hosts da lista
  (aistudio.google.com, elevenlabs.io, github.com, www.instagram.com).
- O `orb.html` tem uma **CSP**: `default-src 'none'`, sem rede (`connect-src 'none'`),
  imagens e áudio só `data:`, sem `<object>`, `<iframe>`, workers, `<base>` ou formulários.
  `script-src` libera `'unsafe-inline'` e `'unsafe-eval'` porque o próprio pywebview usa
  `eval()` (no `evaluate_js`) e `new Function` (para montar `window.pywebview.api`).

### Log

Além dos formatos conhecidos (`AIza…`, `sk_…`), o log apaga o **valor exato** das chaves em
uso (carregadas das configurações ou coladas na janela), qualquer que seja o formato.

### Instalador

- `packaging\build.ps1` instala as **versões exatas** de `packaging\requirements-build.txt`
  (todas as dependências e o PyInstaller), instala o Jarvis com `--no-deps` e roda
  `pip check`.
- O instalador recusa instalar fora de `%LOCALAPPDATA%\Programs\Jarvis` (mesmo com
  `/DIR=`), e o desinstalador não apaga nada se o Jarvis estiver em outra pasta — porque o
  desinstalador apaga a pasta do programa inteira.

### O que ainda vale saber

- Um atalho do Menu Iniciar que só tem a lista de itens do Shell (sem caminho legível) é
  julgado pelo nome. O Jarvis não consegue criar nem mover atalhos para o Menu Iniciar.
- Apps conhecidos (`chrome`, `winword`…) são abertos pelo nome via `ShellExecute`, que
  procura também na pasta atual do Jarvis — que é a pasta do programa, protegida.

## Encontrou uma falha?

Veja o [SECURITY.md](../SECURITY.md). Em resumo: abra uma *issue* no GitHub descrevendo o
problema **sem** colar a sua chave, caminhos pessoais ou o conteúdo do seu `.env`.
