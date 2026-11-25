# Jarvis — assistente de IA por voz (grátis, em português)

![Python 3.12](https://img.shields.io/badge/python-3.12%20recomendado-blue)
![Gemini](https://img.shields.io/badge/IA-Google%20Gemini-4285F4)
![Windows](https://img.shields.io/badge/sistema-Windows%2010%2F11-0078D6)
![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-green)

Um assistente pessoal que **ouve, conversa e age** no seu computador. Você fala
"Jarvis, abre a calculadora" ou "cria uma pasta Fotos na área de trabalho" e ele faz,
respondendo com voz em português, no tom de um mordomo britânico educado.

Feito para quem está começando: tudo explicado passo a passo, sem pagar nada
(usa a camada gratuita do Google Gemini).

> Série "Cobram pra te ensinar. Eu ensino de graça."

---

## O que ele faz

- **Conversa por voz em tempo real** usando o Gemini Live (ouvido e boca da IA).
- **Configura tudo pela janela**: na primeira vez, um assistente de 5 passos pede a chave
  grátis do Google, testa o microfone e deixa você escolher a voz, o nome e o visual.
  Depois, tudo muda pela **engrenagem** no canto de cima. Não precisa editar arquivo nenhum.
- **8 vozes do Google** para escolher (com botão **Ouvir**) ou, se quiser, uma voz sua do
  ElevenLabs (opcional e paga).
- **Janela animada com 9 visuais à escolha** (do orb original a um cérebro neural, um reator
  de plasma, uma silhueta de luz e uma galáxia que vira cérebro): todos mudam quando ele está
  ouvindo, pensando ou falando e pulsam no ritmo da voz dele. Veja [Visuais](#visuais).
- **Modo texto** no terminal, para quem não tem microfone ou quer testar rápido.
- **Executa ações no Windows** a partir de uma **lista fechada** de ferramentas:
  - dizer a data e a hora;
  - listar, abrir e fechar aplicativos (calculadora, bloco de notas, Chrome, Word, Excel, Spotify...);
  - abrir sites e fazer pesquisas no Google;
  - criar, listar, localizar, abrir, mover, renomear e copiar arquivos e pastas;
  - criar arquivos de texto (`.txt` ou `.md`);
  - mandar arquivos para a **Lixeira** — só depois que **você** clica em "Sim" numa janela.
- **Nunca trava por causa de um erro**: se uma ação falhar, ele avisa em uma frase simples
  e o detalhe técnico vai para o arquivo de log.

## Do que você precisa

| Item | Detalhe |
|---|---|
| Sistema | Windows 10 ou 11 (as ações no computador só funcionam no Windows) |
| Microfone | qualquer um, inclusive o do notebook |
| Fone de ouvido | **recomendado**: sem fone, o Jarvis pode ouvir a própria voz |
| Chave do Gemini | grátis no [Google AI Studio](https://aistudio.google.com/apikey) (a janela do Jarvis mostra como criar) |
| Python | **só no caminho 2** (desenvolvedores): Python 3.12 |

## Instalação

Existem dois caminhos. **Escolha um só.**

- **Caminho 1 — Instalador (recomendado para quem não é programador).** Baixa, instala e usa.
- **Caminho 2 — Pelo código (desenvolvedores).** Você instala o Python e roda o projeto.

Nos dois caminhos, a **chave do Google é colada na própria janela do Jarvis**, no assistente
de configuração. Você **não** precisa criar nem editar arquivo `.env`.

### Caminho 1 — Instalador para Windows (recomendado)

> O instalador sai na página de [Releases do GitHub](https://github.com/mateusmirandaia/jarvis/releases)
> quando a versão for publicada. Enquanto não houver um `Jarvis-Setup-<versão>.exe` lá, use o
> caminho 2.

1. Baixe o arquivo `Jarvis-Setup-<versão>.exe` na página de Releases.
2. Dê dois cliques nele. Ele **não pede senha de administrador**.
3. **Se aparecer a tela azul "O Windows protegeu o computador":** isso acontece porque o
   instalador não tem assinatura digital (um certificado pago). Clique em
   **"Mais informações"** e depois em **"Executar assim mesmo"**. Se quiser conferir que o
   arquivo é o original, compare o SHA-256 e veja o link do VirusTotal publicados junto com ele.
4. Siga o instalador até o fim. Ele cria o atalho **Jarvis** na Área de Trabalho e no Menu Iniciar.
5. Abra o Jarvis pelo atalho. Na primeira vez aparece o **assistente de configuração**
   (veja [Primeira abertura](#primeira-abertura-o-assistente-de-configuração)).

Para desinstalar: Configurações do Windows > Aplicativos > Jarvis > Desinstalar. Ele
**pergunta** se você quer apagar também as suas configurações (chave, preferências e logs).

### Caminho 2 — Pelo código (desenvolvedores)

Abra o **PowerShell** (tecla Windows, digite "PowerShell", Enter) e siga na ordem.

**1. Instale o Python 3.12.**

Baixe na página da versão 3.12 do python.org:
[python.org/downloads/release/python-31210](https://www.python.org/downloads/release/python-31210/)
(role até "Files" e escolha **Windows installer (64-bit)**). Na primeira tela do instalador,
**marque "Add python.exe to PATH"** antes de clicar em "Install Now".

> **Por que 3.12 e não a mais nova?** O Jarvis usa o `PyAudio` (microfone e alto-falante).
> Em versões muito novas do Python ele pode ainda não ter o pacote pronto para Windows, e aí a
> instalação tenta compilar e dá erro. Com o 3.12 ele instala sem complicação.
> (O 3.11 também funciona.)

Feche e abra o PowerShell de novo e confira:

```powershell
python --version
```

Deve aparecer `Python 3.12.x`. Se você tiver outras versões instaladas, use `py -3.12` no
lugar de `python` no passo 3.

**2. Baixe o projeto** — escolha uma opção:

- **Com Git:**
  ```powershell
  git clone https://github.com/mateusmirandaia/jarvis.git
  cd jarvis
  ```
- **Sem Git (ZIP):** no GitHub clique em **Code > Download ZIP** e extraia. **Atenção:** a
  pasta extraída se chama **`jarvis-main`** (e às vezes fica uma `jarvis-main` dentro de outra).
  Entre na pasta que tem o arquivo `pyproject.toml`, por exemplo:
  ```powershell
  cd "$env:USERPROFILE\Downloads\jarvis-main"
  dir pyproject.toml
  ```
  Se o `dir` disser que não achou o arquivo, entre na `jarvis-main` de dentro
  (`cd jarvis-main`) e confira de novo.

**3. Crie e ative o ambiente virtual** (uma "caixinha" só para as bibliotecas do Jarvis):

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Se aparecer `(.venv)` no começo da linha, deu certo.

> Se o PowerShell disser que "a execução de scripts foi desabilitada", rode uma vez
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, confirme com `S` e tente de novo.

**4. Instale o Jarvis:**

```powershell
python -m pip install -e .
```

**5. Abra o Jarvis:**

```powershell
jarvis
```

A janela abre e o **assistente de configuração** pede a chave do Google (veja a próxima
seção). **Não copie o `.env.example` para `.env`**: a janela salva a chave sozinha, no lugar
certo. O `.env` é só para quem quer configurar à mão (veja
[Avançado (desenvolvedores)](#avançado-desenvolvedores)).

**6. (Recomendado) Crie o atalho na Área de Trabalho:**

```powershell
jarvis --criar-atalho
```

Aparece o ícone **Jarvis** na Área de Trabalho. Dois cliques nele abrem a janela, sem terminal.

### Primeira abertura: o assistente de configuração

Quando o Jarvis não encontra nenhuma chave do Google, a janela mostra um assistente de
**5 passos**:

1. **Boas-vindas.** Clique em **Começar**.
2. **Sua chave do Google.** Clique em **Criar minha chave grátis** (abre o Google AI Studio no
   navegador), entre com a sua conta Google, clique em **Create API key** e copie a chave.
   Volte, cole no campo e clique em **Testar**. Só dá para avançar com a chave funcionando.
3. **Microfone.** Fale alguma coisa: a barra tem que se mexer. Marque **"Estou usando fone de
   ouvido"** se estiver de fone.
4. **Personalizar.** Diga como ele deve te chamar (opcional), escolha uma das 8 vozes
   (botão **Ouvir** para escutar) e, se quiser, o visual.
5. **Tudo pronto.** Clique em **Começar a usar** e fale: "Jarvis, que horas são?"

Nas próximas vezes ele abre direto no visual e já começa a ouvir.

## A engrenagem (configurações)

O botão de **engrenagem**, no canto superior direito, abre as configurações em 4 abas:

| Aba | O que tem |
|---|---|
| **Geral** | Como ele te chama, **Qual voz eu uso?** (Google ou ElevenLabs), a voz do Google (com **Ouvir**), a caixinha **"Estou usando fone de ouvido"** e o visual. |
| **Chave do Google** | Mostra só o final da chave salva (`…abcd`), botão para criar uma chave nova, campo para colar e **Testar**. |
| **Voz personalizada (ElevenLabs)** | Liga uma voz do ElevenLabs (opcional e paga). Veja [Voz do ElevenLabs](#voz-do-elevenlabs-opcional-e-paga). |
| **Sobre** | Versão, link do repositório e botões para abrir a pasta das configurações e a pasta dos logs. |

Clique em **Salvar e aplicar**: o Jarvis reinicia a voz com as escolhas novas, sem fechar a janela.

Se a chave do Google parar de funcionar, aparece um aviso com o botão **Atualizar chave**.

## Como usar

| Comando | O que faz |
|---|---|
| Atalho **Jarvis** | Abre a janela e já começa a ouvir. Feche a janela para sair. |
| `jarvis` | O mesmo que o atalho (caminho 2, com o ambiente ativado). |
| `jarvis --modo voz` | Voz **só no terminal**, mostrando as falas e as ações. Ctrl+C para sair. |
| `jarvis --modo texto` | Modo **texto** no terminal. Digite `sair` para encerrar. |
| `jarvis --criar-atalho` | Cria o atalho **Jarvis** na Área de Trabalho (abre a janela). |
| `jarvis --versao` | Mostra a versão instalada. |
| `python -m jarvis` | Mesmo que `jarvis` (útil se o comando não for encontrado). |

Os modos de terminal (`--modo voz` e `--modo texto`) não têm o assistente de configuração:
eles usam a chave que você já salvou pela janela (ou a do `.env`). Sem chave, eles avisam e saem.

### Exemplos de comandos de voz

- "Que horas são?"
- "Abre a calculadora." / "Abre o Spotify."
- "Quais aplicativos estão abertos?"
- "Fecha o navegador." / "Fecha o bloco de notas à força."
- "Abre o youtube.com."
- "Pesquisa receita de bolo de cenoura."
- "Cria uma pasta chamada Projetos na área de trabalho."
- "O que tem na pasta Downloads?"
- "Procura o arquivo orçamento nos documentos."
- "Move o arquivo foto.jpg da área de trabalho para a pasta Fotos."
- "Cria um arquivo lista de compras na área de trabalho com arroz, feijão e café."
- "Manda o arquivo rascunho.txt para a Lixeira." (vai abrir uma janela pedindo sua confirmação)

## Vozes

### Qual voz eu uso?

Na engrenagem, aba **Geral**, você escolhe quem fala:

- **Voz do Google** (grátis, padrão): uma das 8 vozes prontas abaixo.
- **Minha voz do ElevenLabs** (opcional e paga): só aparece depois que você configura a aba
  **Voz personalizada**.

### As 8 vozes do Google

Clique em **Ouvir** em cada cartão para escutar uma amostra antes de escolher.

| Voz | Jeito |
|---|---|
| `Charon` | Masculina, grave e calma (padrão) |
| `Puck` | Masculina, animada |
| `Kore` | Feminina, firme |
| `Fenrir` | Masculina, empolgada |
| `Aoede` | Feminina, leve |
| `Leda` | Feminina, jovem |
| `Orus` | Masculina, firme |
| `Zephyr` | Feminina, clara |

Para trocar: engrenagem > **Geral** > escolha a voz > **Salvar e aplicar**.

### Voz do ElevenLabs (opcional e paga)

Se você tem conta no ElevenLabs, o Jarvis pode falar com uma voz de lá (a sua, ou uma voz
criada do zero). O Gemini continua sendo o ouvido e o cérebro; só a fala muda.

1. No ElevenLabs, crie uma chave (API key) com as **duas permissões** abaixo (veja
   [Permissões da chave do ElevenLabs](#permissões-da-chave-do-elevenlabs)).
2. No Jarvis, abra a engrenagem > aba **Voz personalizada (ElevenLabs)** e cole a chave.
3. Clique em **Buscar minhas vozes** e escolha uma (ou **Prefiro colar o ID da voz**, se a sua
   chave não puder listar as vozes).
4. Se quiser, clique em **Testar a voz** (ele pergunta antes, porque o teste gasta créditos).
5. Clique em **Salvar e aplicar**.

Para voltar à voz grátis: aba Voz personalizada > **Voltar para a voz do Google**, ou em
**Geral** marque **Voz do Google**.

#### Permissões da chave do ElevenLabs

O ElevenLabs deixa escolher o que cada chave pode fazer. O Jarvis precisa de duas permissões:

| Permissão | Para quê | Sem ela |
|---|---|---|
| **Text to Speech** (acesso) | Falar com a voz escolhida | O Jarvis não consegue falar com o ElevenLabs e volta para a voz do Google. |
| **Voices** (leitura / *read*) | Listar as suas vozes no botão **Buscar minhas vozes** | Aparece o aviso de que falta a permissão "Voices: read". A voz ainda funciona se você colar o **ID da voz** à mão. |

Como fazer no site do ElevenLabs:

1. Entre na sua conta e abra a área de **API Keys** (em *Developers*).
2. Clique para criar uma chave nova. Se a opção de **restringir a chave** estiver ligada, marque
   **Text to Speech** e **Voices: read**. As outras permissões podem ficar desligadas, porque o
   Jarvis não usa.
3. Copie a chave e cole no Jarvis.

Se você já tem uma chave e só faltava uma permissão, dá para **editar as permissões dessa
chave** na mesma área de API Keys, sem criar outra. Depois, volte ao Jarvis e clique de novo em
**Buscar minhas vozes**.

> Dica: liberar só essas duas permissões é mais seguro. Se a chave vazar, ela não serve para
> mexer no resto da sua conta.

O que muda na prática:

- **Custo:** cada fala consome créditos do seu plano do ElevenLabs.
- **Velocidade:** um pouco mais lenta que a voz do Google (cerca de 2 s contra cerca de 1 s),
  porque o texto passa por mais um serviço. O Jarvis fala frase por frase para compensar.
- **Segurança:** se o ElevenLabs falhar (sem créditos, chave errada, rede), o Jarvis avisa
  uma vez e continua com a voz do Google. Nunca trava.

> **Importante:** só clone a **sua própria voz**, ou a de alguém que **autorizou** por escrito.
> Nunca clone a voz de um ator, de um personagem ou de outra pessoa sem autorização dela.

## Visuais

A janela do Jarvis tem **9 visuais**. Ele abre na **Galáxia Neural**; para usar outro,
clique em **"Trocar visual"** (canto superior direito) ou em **Escolher visual** na engrenagem:
aparece a tela **"Escolha o visual do Jarvis"**, com uma prévia animada de cada um. Clique no que
preferir e ele fica salvo.

| id | Nome | Como é |
|---|---|---|
| `galaxia` | Galáxia Neural (padrão) | Uma galáxia espiral de três braços (820 pontos) girando, que se fecha num cérebro com sinapses e impulsos brancos e depois se abre de novo em galáxia. |
| `globo` | Globo | O orb original: uma esfera de partículas, simples e centralizada. |
| `cortex` | Córtex Neural | Um cérebro visto de cima, feito de neurônios ligados, com sinapses disparando. |
| `reator` | Reator de Plasma | Núcleo de energia com anéis girando e raios elétricos. |
| `holograma` | Holograma | Cabeça em fatias de ressonância, com uma linha de varredura. |
| `mapa` | Mapa Mental | O "JARVIS" no centro e ramos para voz, cérebro, ferramentas, arquivos e mais. |
| `esfera` | Esfera Holográfica | Esfera dourada de meridianos girando, com um "olho" que respira. |
| `aura` | Aura | Silhueta de cabeça e ombros feita de luz azul, com um núcleo dourado. |
| `cerebro` | Globo Cognitivo | Um globo de 760 pontos (ciano e gelo) girando, que se transforma num cérebro (dois hemisférios e cerebelo, com sulcos), com ligações violeta e impulsos âmbar correndo, e volta a ser globo. |

A **Galáxia Neural** usa uma paleta própria, a `nuvem`, feita com as cores do ano de 2026:
**Transformative Teal** (verde-azulado, cor do ano WGSN/Coloro 2026) nos pontos e
**Cloud Dancer** (branco suave, cor do ano Pantone 2026) nas sinapses, nos impulsos e no texto.

Os visuais com painel (todos menos o `globo` e o `aura`) mostram também a conversa, o volume
do microfone, a latência real até cada resposta e as ações executadas, com a hora.

"Voltar" (ou a tecla Esc) fecha a tela de escolha sem mudar nada. Se um visual der erro, a
janela cai sozinha no `globo`, o mais simples (sem mudar a sua escolha salva).

Tudo roda **sem internet**: os visuais são desenhados em Canvas, sem bibliotecas externas.

## Onde ficam as configurações e os logs

Tudo fica numa pasta sua, **fora** da pasta do programa (assim nada se perde quando você
atualiza o Jarvis). Na engrenagem > **Sobre** há botões para abrir essas pastas.

| O quê | Windows | Outros sistemas |
|---|---|---|
| Chaves (Google e ElevenLabs) | `%APPDATA%\Jarvis\.env` | `~/.config/jarvis/.env` |
| Preferências (voz, nome, fone, visual) | `%APPDATA%\Jarvis\preferencias.json` | `~/.config/jarvis/preferencias.json` |
| Logs do programa instalado (caminho 1) | `%APPDATA%\Jarvis\logs\jarvis.log` | — |
| Logs pelo código (caminho 2) | `logs\jarvis.log`, na pasta do projeto | `logs/jarvis.log` |

Apagar o `preferencias.json` faz o Jarvis voltar a abrir na Galáxia Neural com a voz padrão.

## Avançado (desenvolvedores)

**Você não precisa disto para usar o Jarvis.** A janela faz tudo. Esta seção é para quem
quer configurar por arquivo ou por variável de ambiente.

### De onde o Jarvis lê as configurações

Para cada configuração, **a primeira fonte que tiver o valor ganha**:

1. **Variáveis de ambiente** do Windows/terminal (ex.: `$env:GEMINI_API_KEY = "..."`);
2. **`.env` da pasta do projeto** (só no caminho 2; o programa instalado não procura este arquivo);
3. **`.env` da pasta do usuário** (`%APPDATA%\Jarvis\.env`), **onde a janela salva as chaves**.

Para **voz, nome e fone de ouvido**, se nenhuma das três fontes definir o valor, vale o que
você escolheu na janela (`preferencias.json`) e, por fim, o padrão.

> **Cuidado:** uma linha no `.env` do projeto (ou uma variável de ambiente) **ganha** das
> escolhas feitas na janela. Por exemplo, com `JARVIS_VOZ=Charon` no `.env`, trocar a voz pela
> engrenagem não muda nada (a janela avisa quando isso acontece). Para a janela voltar a
> mandar, **apague a linha** do `.env`. O mesmo vale para a chave: se o `.env` do projeto tem
> uma `GEMINI_API_KEY`, o assistente de configuração não aparece e trocar a chave pela
> engrenagem não muda a chave usada.

Se você mesmo assim quiser um `.env` no projeto, copie o modelo (`copy .env.example .env`).
Nele só a `GEMINI_API_KEY` vem ativa; o resto vem comentado com `#` justamente para não
prender as escolhas da janela. Tire o `#` só das linhas que quiser forçar.

### Variáveis aceitas

| Variável | Para que serve | Padrão |
|---|---|---|
| `GEMINI_API_KEY` | Sua chave grátis do Google AI Studio (o texto de exemplo `cole_sua_chave_aqui` conta como "sem chave") | — |
| `JARVIS_NOME_USUARIO` | Seu nome ("assistente pessoal de ...") | escolha da janela, senão vazio |
| `JARVIS_VOZ` | Voz do Google (`Charon`, `Puck`, `Kore`, `Fenrir`, `Aoede`, `Leda`, `Orus`, `Zephyr`) | escolha da janela, senão `Charon` |
| `JARVIS_FONE` | `sim` se você usa fone: dá para interromper ele no meio da fala | escolha da janela, senão `nao` |
| `JARVIS_VISUAL` | Força um visual da janela (veja [Visuais](#visuais)). Vazio = usa o que você escolheu | vazio |
| `JARVIS_SILENCIO_MS` | Silêncio (ms) que encerra a sua fala, de 200 a 2000. Menor = responde mais rápido | `500` |
| `GEMINI_LIVE_MODEL` | Modelo de voz em tempo real | `gemini-3.1-flash-live-preview` |
| `GEMINI_MODEL` | Modelo do modo texto | `gemini-3.5-flash-lite` |
| `GEMINI_MODEL_RESERVA` | Modelo reserva do modo texto (usado em erro 5xx) | `gemini-flash-lite-latest` |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | Voz do ElevenLabs (opcional e paga) | vazio |
| `ELEVENLABS_MODEL` | Modelo de voz do ElevenLabs | `eleven_flash_v2_5` |

### Gerar o instalador

Na máquina que gera o instalador (Windows, Python 3.12 e [Inno Setup 6](https://jrsoftware.org/isdl.php)):

```powershell
python scripts\gerar_amostras_voz.py                               # amostras do botão "Ouvir" (uma vez)
powershell -ExecutionPolicy Bypass -File packaging\build.ps1      # gera dist\Jarvis-Setup-<versão>.exe
```

O instalador não pede administrador, instala em `%LOCALAPPDATA%\Programs\Jarvis` e cria os
atalhos. O passo a passo completo (testar numa máquina limpa, SmartScreen, VirusTotal) está em
[docs/INSTALADOR.md](docs/INSTALADOR.md).

## Segurança (resumo)

O Jarvis foi feito para ser seguro para qualquer pessoa que baixar:

- **Lista fechada de ações.** A IA só escolhe entre as ferramentas do projeto. Ela nunca
  roda comandos livres de terminal.
- **Apagar só com clique manual.** Abre uma janela do Windows e só o seu clique em "Sim"
  autoriza. A IA não consegue confirmar sozinha. A janela fecha sozinha depois de um tempo
  (vale como "Não"). E o arquivo vai para a **Lixeira** (dá para recuperar).
- **Pastas protegidas.** Raiz do disco (`C:\`), Windows, Arquivos de Programas, ProgramData,
  a pasta do Jarvis e a pasta das configurações (`%APPDATA%\Jarvis`, onde fica a sua chave):
  nada é criado, movido ou apagado nelas.
- **Nunca sobrescreve.** Mover, copiar ou criar com um nome que já existe é recusado.
- **Processos do sistema e o terminal do Jarvis não podem ser fechados.**
- **A chave não sai do seu computador** (só vai para o Google). Ela fica em
  `%APPDATA%\Jarvis\.env`, nunca aparece no log, e a janela mostra só os 4 últimos caracteres.

Detalhes em [docs/SEGURANCA.md](docs/SEGURANCA.md). Achou uma falha? Veja [SECURITY.md](SECURITY.md).

## Estrutura de pastas

```
jarvis/
├── pyproject.toml            # dependências, versão e o comando "jarvis"
├── requirements.txt          # mesmas dependências, para quem prefere pip install -r
├── .env.example              # modelo de .env (só para o modo avançado)
├── CHANGELOG.md              # o que mudou em cada versão
├── SECURITY.md               # como reportar uma falha de segurança
├── src/jarvis/
│   ├── __main__.py           # linha de comando (jarvis / python -m jarvis)
│   ├── config.py             # Settings: lê ambiente, .env do projeto, .env do usuário e preferências
│   ├── armazenamento.py      # grava as chaves no .env da pasta do usuário (atômico)
│   ├── controlador.py        # liga, desliga e reinicia o assistente de voz sem travar a janela
│   ├── verificacao.py        # testa as chaves do Google e do ElevenLabs
│   ├── microfone.py          # teste do microfone do assistente de configuração
│   ├── vozes.py              # as 8 vozes do Google e as amostras do botão "Ouvir"
│   ├── errors.py             # erros amigáveis e o "safe_tool"
│   ├── logging_setup.py      # log em arquivo (com as chaves apagadas)
│   ├── persona.py            # personalidade (prompt de sistema)
│   ├── os_integration/
│   │   ├── windows.py        # janelas, processos e caixa de confirmação do Windows
│   │   └── shortcut.py       # atalho na Área de Trabalho
│   ├── ui/
│   │   ├── orb_window.py     # janela (pywebview): monta o HTML e recebe os eventos
│   │   ├── orb.html          # a "casca": assistente, engrenagem, tela de escolha, painel
│   │   ├── api_config.py     # funções que a janela pode chamar (lista fechada)
│   │   ├── preferencias.py   # voz, nome, fone e visual (fora da pasta do projeto)
│   │   ├── visuais/          # um .js por visual (galaxia, globo, cortex...), Canvas puro
│   │   ├── amostras/         # um .wav por voz do Google (botão "Ouvir")
│   │   └── jarvis.ico        # ícone
│   ├── tools/                # a LISTA FECHADA de ações
│   │   ├── __init__.py       # ToolRegistry (registro das ferramentas)
│   │   ├── security.py       # PathGuard, pastas e processos protegidos
│   │   ├── system_tools.py   # data e hora
│   │   ├── app_tools.py      # abrir, listar e fechar apps
│   │   ├── web_tools.py      # sites e pesquisa
│   │   └── file_tools.py     # arquivos e pastas
│   └── assistants/
│       ├── observer.py       # eventos para a interface (estado, volume, legendas)
│       ├── voice_output.py   # quem fala: voz do Google ou do ElevenLabs
│       ├── elevenlabs_voice.py # voz opcional do ElevenLabs (streaming)
│       ├── audio.py          # microfone e alto-falante (pyaudio)
│       ├── live_assistant.py # modo voz (Gemini Live)
│       └── text_assistant.py # modo texto
├── packaging/                # instalador: PyInstaller (jarvis.spec), Inno Setup (jarvis.iss), build.ps1
├── scripts/
│   └── gerar_amostras_voz.py # gera as amostras das 8 vozes (uma vez, antes do instalador)
├── examples/
│   └── 01_cerebro_texto.py   # versão didática: só o "cérebro" (usado nos vídeos)
├── tests/                    # testes automáticos (pytest)
├── .github/                  # modelos de issue e testes automáticos no GitHub
└── docs/
    ├── ARQUITETURA.md
    ├── SEGURANCA.md
    ├── INSTALADOR.md
    └── DIARIO.md
```

Mais detalhes em [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Como contribuir / rodar os testes

```powershell
python -m pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
```

Os testes rodam em qualquer sistema (inclusive Linux), sem internet e sem microfone. No
GitHub eles rodam sozinhos em Windows e Linux a cada envio (`.github/workflows/testes.yml`).

Para criar uma **ação nova**: escreva o método na classe de ferramentas certa em
`src/jarvis/tools/`, com docstring em português e seção `Args` (a IA lê essa descrição),
acrescente o nome em `TOOL_NAMES` e escreva um teste. Ações que mexem em arquivos devem
passar pelo `PathGuard`.

## Problemas comuns

| O que acontece | O que fazer |
|---|---|
| "O Windows protegeu o computador" ao instalar | Clique em **"Mais informações"** e depois em **"Executar assim mesmo"** (o instalador não tem assinatura paga). |
| `python` não é reconhecido | Reinstale o Python 3.12 marcando **"Add python.exe to PATH"** e abra um PowerShell novo. |
| "a execução de scripts foi desabilitada" | Rode `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e confirme com `S`. |
| `pip install` diz que não achou `pyproject.toml` | Você está na pasta errada. No ZIP, entre na `jarvis-main` que tem o `pyproject.toml` (veja o passo 2 do caminho 2). |
| Erro ao instalar o `pyaudio` | Quase sempre é Python novo demais. Instale o **Python 3.12**, apague a pasta `.venv` e refaça os passos 3 e 4. |
| `jarvis` não é reconhecido | Ative o ambiente (`.venv\Scripts\activate`) ou use `python -m jarvis`. |
| O assistente de configuração não apareceu | Já existe uma chave em algum lugar: no `.env` da pasta do projeto ou numa variável `GEMINI_API_KEY`. Para usar a janela, apague essa linha/variável. |
| Troquei a voz (ou o fone) na engrenagem e nada mudou | O `.env` do projeto tem `JARVIS_VOZ` (ou `JARVIS_FONE`, `JARVIS_NOME_USUARIO`) e ele ganha da janela. Apague a linha do `.env`. |
| "Essa chave não parece completa" com uma chave nova do Google | As chaves novas do Google têm um ponto no meio e não começam com `AIza`. Versões antigas do Jarvis recusavam esse formato: instale a versão mais nova e cole a chave de novo. |
| "Sua chave não tem a permissão Voices: read" (ElevenLabs) | Libere a permissão **Voices: read** na chave (veja [Permissões da chave do ElevenLabs](#permissões-da-chave-do-elevenlabs)) ou cole o ID da voz à mão. |
| "Sua chave não tem a permissão Text to Speech" (ElevenLabs) | Libere a permissão **Text to Speech** na chave. Sem ela o Jarvis não consegue usar a voz do ElevenLabs. |
| "A chave do Google parou de funcionar" | Clique em **Atualizar chave** (ou engrenagem > **Chave do Google**), crie uma chave nova e cole. |
| Ele não me ouve | Confira o microfone padrão do Windows (Configurações > Sistema > Som > Entrada) e a permissão em Configurações > Privacidade > Microfone. |
| Ele responde a si mesmo / se interrompe | Use fone de ouvido e marque **"Estou usando fone de ouvido"** na engrenagem (aba Geral). Sem fone, deixe essa caixinha **desmarcada**. |
| O botão "Ouvir" diz "amostra indisponível" | Faltam as amostras de voz (só acontece no caminho 2). A voz funciona normalmente; para ter as amostras, veja [docs/INSTALADOR.md](docs/INSTALADOR.md). |
| Quero escolher o visual de novo | Clique em "Trocar visual" na janela (ou apague o `preferencias.json`, veja [Onde ficam](#onde-ficam-as-configurações-e-os-logs)). |
| A janela não abre | Instale o **WebView2** (já vem no Windows 11). No caminho 2, rode `jarvis --modo voz` para ver a mensagem. |
| Qualquer outro problema | Veja o log (engrenagem > Sobre > Logs > **Abrir pasta**): o erro completo fica registrado lá. |

## Limites conhecidos

- **A camada grátis tem cota.** Se usar muito num dia, o Google pode recusar por um tempo.
- **A API às vezes fica instável** (erro 5xx, "modelo sobrecarregado"). No modo texto o Jarvis
  tenta o modelo reserva; no modo voz ele reconecta sozinho.
- **As ações no computador só funcionam no Windows.** Em outros sistemas ele conversa,
  mas avisa que não consegue executar.
- O modelo Live é "preview": o nome pode mudar. Se parar de funcionar, confira o nome
  atual no Google AI Studio e ajuste `GEMINI_LIVE_MODEL` (veja [Avançado](#avançado-desenvolvedores)).

## Créditos e aviso

"Jarvis" é só um apelido. Este projeto **não é afiliado à Marvel, à Disney nem ao Google**.
A voz padrão é uma voz pronta do Google (não clonada de ator) e o visual é original.

O que mudou em cada versão: [CHANGELOG.md](CHANGELOG.md). Diário de desenvolvimento:
[docs/DIARIO.md](docs/DIARIO.md).

## Licença

[MIT](LICENSE): uso livre. Pode usar, copiar, modificar, distribuir e até vender, para
qualquer fim. A única condição é manter o aviso de copyright e a licença junto do código.
