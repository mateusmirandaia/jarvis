# Changelog

Todas as mudanças importantes do Jarvis ficam registradas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa
[Versionamento Semântico](https://semver.org/lang/pt-BR/). O dia a dia do desenvolvimento está
em [docs/DIARIO.md](docs/DIARIO.md).

## [Não publicado]

### Corrigido

- **Jarvis mudo com o ElevenLabs.** Se o senhor interrompesse no meio de uma frase (ou o
  cliente do ElevenLabs desse um erro inesperado), a fila de áudio da frase nunca terminava e
  o Jarvis parava de falar até reiniciar. Agora a fila sempre fecha; erro inesperado cai para
  a voz do Google, como os outros erros do ElevenLabs.
- **Python 3.11.** Parar o assistente usava um parâmetro que só existe no 3.12
  (`shutdown_default_executor(timeout=...)`); no 3.11 o fechamento agora espera no máximo 3 s
  do mesmo jeito.

### Alterado

- Mensagens que aparecem para a pessoa com acento e mais claras: perda de conexão ("Senhor,
  perdi a conexão. Tento de novo em 4 s…"), troca para a voz do Google, "O Jarvis já está
  aberto", chave ausente e criação do atalho.
- Persona: "assistente pessoal **de** {nome}".
- Vozes do Google mostram o gênero (ex.: "Masculina, grave e calma"), conferido na
  documentação oficial do Gemini TTS.
- Dependências com faixa de versão (`google-genai>=3.6,<4`, `httpx>=0.27,<1`,
  `pywebview>=5,<7`, `pyaudio>=0.2.14`, `python-dotenv>=1,<2`, `send2trash>=1.8,<3`),
  link do repositório no pacote e Python 3.13 nos classificadores.
- Limpeza interna: `config.pasta_usuario` usa a de `armazenamento`; removido o apelido
  antigo `orb_window._ApiJs`.

### Segurança

Correção das falhas encontradas no teste de ataque de 25/11/2026 (regras completas em
[docs/SEGURANCA.md](docs/SEGURANCA.md#regras-das-ferramentas)).

- **Abrir arquivo usa lista positiva** de documentos, fotos, áudio e vídeo (antes era uma
  lista de proibidos que deixava passar `.lnk`, `.url`, `.py`, `.msc`, `.iso`, `.docm`…).
- **Mover/renomear/copiar não troca a extensão** (`nota.txt` não vira `nota.cmd`) e não leva
  nada para o `AppData` (Menu Iniciar, pasta Inicializar) nem para o perfil do PowerShell.
- Nomes com ponto/espaço no fim, `:` (fluxo alternativo), nomes de dispositivo, nomes 8.3 e
  pastas `{CLSID}` são recusados.
- **Chaves não saem da pasta protegida**: a origem também é checada ao copiar, mover, abrir,
  listar e procurar; arquivos de senha (`.env`, `id_rsa`, `.pem`…) não são abertos, copiados
  nem movidos em pasta nenhuma; pastas com links ou com esses arquivos não são copiadas.
- **Caminhos de rede e de dispositivo** (`\\servidor\pasta`, `\\?\`, `\\.\`) são recusados, e
  variáveis (`%APPDATA%`) não são mais expandidas.
- **`open_app`** abre só os apps conhecidos ou atalhos do Menu Iniciar pelo nome; nunca
  executáveis do PATH/pasta atual nem `cmd`, `powershell`, `regedit`, `mshta`, `logoff`,
  `shutdown` e afins, mesmo com atalho (o alvo do `.lnk` é conferido).
- **`close_app`** exige 3 letras, casa por palavra inteira, pergunta quando casa mais de um
  programa, força só um por vez e protege o próprio Jarvis e mais processos do Windows.
- **Apagar**: nenhuma outra alteração de arquivo enquanto a janela está aberta; se o item mudar
  até o clique, nada é apagado; pendrive e rede (sem Lixeira) são recusados.
- Pastas pessoais inteiras (Documentos, Área de Trabalho, a pasta do usuário…) não são movidas
  nem apagadas.
- **Janela**: a ponte do pywebview não expõe mais `__globals__`/closures (a página não alcança
  o Python), `LINKS` é somente leitura e só abre `https://` da lista; o `orb.html` ganhou CSP.
- Cópia limitada a 2 GB / 20 mil itens; quando uma ação passa do tempo, o Jarvis avisa que
  ela pode ter terminado e pede para conferir antes de repetir.
- O log apaga o valor exato das chaves em uso, de qualquer formato.
- Build com versões fixas (`packaging/requirements-build.txt` + `pip check`); o instalador
  recusa `/DIR=` fora de `%LOCALAPPDATA%\Programs\Jarvis` e o desinstalador não apaga pasta
  inesperada.

### Adicionado

- Atalhos falados **imagens**, **músicas** e **vídeos**.

## [0.8.0] - 2026-11-25

### Adicionado

- **Configuração pela janela.** Na primeira abertura (sem chave do Google em lugar nenhum), a
  janela mostra um assistente de 5 passos: boas-vindas, chave do Google (com link para criar a
  chave grátis e botão **Testar**), microfone (barra de volume e caixinha "Estou usando fone de
  ouvido"), personalizar (nome, voz e visual) e "Tudo pronto". O assistente de voz começa ao
  clicar em **Começar a usar**, sem reiniciar a janela.
- **Engrenagem** no canto superior direito, com 4 abas: **Geral** (nome, "Qual voz eu uso?",
  voz do Google, fone, visual), **Chave do Google** (mostra só `…abcd`, testa e troca a chave),
  **Voz personalizada (ElevenLabs)** (buscar vozes da conta ou colar o ID, testar com
  confirmação de gasto de créditos, voltar para a voz do Google) e **Sobre** (versão,
  repositório, pastas de configurações e logs). **Salvar e aplicar** reinicia a voz na hora.
- **8 vozes do Google** escolhíveis na janela (Charon, Puck, Kore, Fenrir, Aoede, Leda, Orus,
  Zephyr), cada uma com botão **Ouvir** que toca uma amostra.
- **Fonte de voz** (`fonte_voz` no `preferencias.json`): alterna entre a voz do Google e a do
  ElevenLabs sem apagar a chave do ElevenLabs.
- Aviso **"Atualizar chave"** na janela quando o Google recusa a chave; o assistente para em
  vez de ficar reconectando.
- Chaves salvas pela janela em `%APPDATA%\Jarvis\.env` (`~/.config/jarvis/.env` fora do
  Windows), com escrita atômica e só caracteres seguros.
- **Instalador para Windows** (`Jarvis-Setup-<versão>.exe`): PyInstaller (pasta onedir, sem
  console) + Inno Setup 6, sem pedir administrador, em `%LOCALAPPDATA%\Programs\Jarvis`, com
  atalhos na Área de Trabalho e no Menu Iniciar. O desinstalador pergunta antes de apagar as
  configurações. `packaging/build.ps1` gera tudo num comando e mostra o SHA-256.
- `scripts/gerar_amostras_voz.py`: gera as amostras das 8 vozes com o TTS do Gemini.
- Módulos novos: `controlador.py`, `armazenamento.py`, `verificacao.py`, `microfone.py`,
  `vozes.py` e `ui/api_config.py`.
- `CHANGELOG.md`, `SECURITY.md`, modelos de issue e testes automáticos no GitHub Actions
  (ruff + pytest em Windows e Linux, Python 3.12).

### Mudado

- `jarvis` (modo orb) **abre a janela mesmo sem chave**, para ela mesma pedir a configuração.
  Os modos `--modo voz` e `--modo texto` continuam exigindo a chave.
- Ordem de leitura das configurações: variáveis de ambiente > `.env` do projeto >
  `%APPDATA%\Jarvis\.env`; para voz, nome e fone, depois disso vale a escolha da janela
  (`preferencias.json`) e, por fim, o padrão.
- No programa instalado não existe `.env` de projeto, e os logs ficam em
  `%APPDATA%\Jarvis\logs\jarvis.log`.
- A janela recebe só uma ponte com 15 funções (`ponte_js`), e não o objeto da API inteiro.
- A pasta das configurações (`%APPDATA%\Jarvis`) passou a ser protegida contra as ações da IA.
- O log apaga chaves de API de qualquer texto antes de gravar.
- `.env` lido à mão aceita UTF-8 com BOM, UTF-16 e ANSI (Bloco de Notas/PowerShell).
- **README reescrito**: caminho 1 (instalador, para leigos) e caminho 2 (código, Python 3.12);
  o `.env` virou a seção "Avançado (desenvolvedores)".
- `.env.example`: só a `GEMINI_API_KEY` vem ativa; todo o resto vem comentado, para não prender
  as escolhas feitas na janela.

### Corrigido

- Copiar o `.env.example` para `.env` prendia `JARVIS_VOZ` e `JARVIS_FONE` (o `.env` ganha da
  janela) e pulava o assistente de configuração. Agora a janela avisa quando o `.env` manda, e o
  `.env.example` não traz mais essas linhas ativas.

## [0.7.0] - 2026-11-25

### Adicionado

- Visual **Globo Cognitivo** (`cerebro`): globo de 760 pontos que se transforma num cérebro
  (dois hemisférios e cerebelo), com ligações e impulsos, e volta a ser globo. Paleta `aurora`.
- Visual **Galáxia Neural** (`galaxia`): galáxia espiral de três braços (820 pontos) que se
  fecha num cérebro e se abre de novo.
- Paleta **`nuvem`**, com as cores do ano de 2026: Transformative Teal (WGSN/Coloro) e Cloud
  Dancer (Pantone).

### Mudado

- A **Galáxia Neural** virou o visual padrão: a janela abre direto nela, sem tela de escolha;
  troca pelo botão "Trocar visual".
- Tela de escolha com 9 cartões.

## [0.6.0] - 2026-11-24

### Adicionado

- **Visuais escolhíveis**: 7 visuais para a janela (globo, córtex, reator, holograma, mapa,
  esfera, aura), tela "Escolha o visual do Jarvis" com prévia animada e botão "Trocar visual".
- Escolha salva fora do projeto, em `%APPDATA%\Jarvis\preferencias.json`.
- `JARVIS_VISUAL` no `.env` para forçar um visual.
- Painéis com dados reais: conversa, volume do microfone, latência até cada resposta,
  ações executadas, linha do tempo dos estados, ranking de ferramentas.
- Eventos novos do assistente para a janela: `on_tool` e `on_latency`.

### Corrigido

- Visual Aura pesado: de ~40 ms para ~7 ms por quadro.

## [0.5.0] - 2026-11-23

### Adicionado

- Projeto reorganizado em pacote (`src/jarvis`), com o comando `jarvis`, testes com pytest,
  lint com ruff e documentação em `docs/`.
- Modo voz em tempo real com o Gemini Live, modo texto no terminal e lista fechada de ações
  no Windows (apps, sites, arquivos e pastas, Lixeira com confirmação manual).
- Janela animada (orb) com pywebview e atalho na Área de Trabalho (`jarvis --criar-atalho`).
- Voz opcional do ElevenLabs (o Gemini ouve e pensa, o ElevenLabs fala), com volta automática
  para a voz do Google se falhar.

[Não publicado]: https://github.com/mateusmirandaia/jarvis/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/mateusmirandaia/jarvis/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/mateusmirandaia/jarvis/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/mateusmirandaia/jarvis/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/mateusmirandaia/jarvis/releases/tag/v0.5.0
