# Jarvis — assistente de IA por voz (grátis, em português)

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
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
- **Orb animado**: uma janela com uma esfera de partículas que muda quando ele está ouvindo,
  pensando ou falando, e pulsa no ritmo da voz dele. Abre com dois cliques num **atalho na
  Área de Trabalho**.
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

## Requisitos

| Item | Detalhe |
|---|---|
| Sistema | Windows 10 ou 11 (as ações no computador só funcionam no Windows) |
| Python | 3.11 ou mais novo ([python.org](https://www.python.org/downloads/) — marque "Add Python to PATH" na instalação) |
| Microfone | qualquer um, inclusive o do notebook |
| Fone de ouvido | **recomendado**: sem fone, o Jarvis pode ouvir a própria voz |
| Chave do Gemini | grátis no [Google AI Studio](https://aistudio.google.com/apikey) |

## Instalação passo a passo (PowerShell)

Abra o **PowerShell** (tecla Windows, digite "PowerShell", Enter) e siga na ordem.

**1. Baixe o projeto** — escolha uma opção:

- Com Git:
  ```powershell
  git clone https://github.com/mateusmirandaia/jarvis.git
  cd jarvis
  ```
- Sem Git: no GitHub clique em **Code > Download ZIP**, extraia a pasta e, no PowerShell,
  entre nela com `cd "C:\caminho\da\pasta\jarvis"`.

**2. Crie e ative o ambiente virtual** (uma "caixinha" só para as bibliotecas do Jarvis):

```powershell
python -m venv .venv
.venv\Scripts\activate
```

Se aparecer `(.venv)` no começo da linha, deu certo.

> Se o PowerShell disser que "a execução de scripts foi desabilitada", rode uma vez
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, confirme com `S` e tente de novo.

**3. Instale o Jarvis:**

```powershell
python -m pip install -e .
```

**4. Crie o seu arquivo de configuração:**

```powershell
copy .env.example .env
notepad .env
```

**5. Cole a sua chave** no lugar de `cole_sua_chave_aqui`, salve e feche o Bloco de Notas.
Pegue a chave em [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (botão "Create API key").

**6. (Opcional) Ponha o seu nome** na linha `JARVIS_NOME_USUARIO` do mesmo `.env`, por exemplo
`JARVIS_NOME_USUARIO=Carlos`. Assim o Jarvis se apresenta como "assistente pessoal do Carlos".
Deixe vazio para ele ser apenas "seu assistente pessoal". Em qualquer caso, ele chama você
de "senhor".

**7. (Recomendado) Crie o atalho na Área de Trabalho:**

```powershell
jarvis --criar-atalho
```

Aparece o ícone **Jarvis** na Área de Trabalho. Dois cliques nele abrem o orb, sem terminal.

Pronto.

## Configurações do `.env`

Só a `GEMINI_API_KEY` é obrigatória. O resto tem valor padrão.

| Linha | Para que serve | Padrão |
|---|---|---|
| `GEMINI_API_KEY` | Sua chave grátis do Google AI Studio (**obrigatória**) | — |
| `JARVIS_NOME_USUARIO` | Seu nome ("assistente pessoal do ...") | vazio |
| `JARVIS_VOZ` | Voz pronta do Google | `Charon` |
| `JARVIS_FONE` | `sim` se você usa fone: dá para interromper ele no meio da fala | `nao` |
| `JARVIS_SILENCIO_MS` | Silêncio (ms) que encerra a sua fala. Menor = responde mais rápido | `500` |
| `GEMINI_LIVE_MODEL` | Modelo de voz em tempo real | `gemini-3.1-flash-live-preview` |
| `GEMINI_MODEL` / `GEMINI_MODEL_RESERVA` | Modelos do modo texto | `gemini-3.5-flash-lite` |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | Voz do ElevenLabs (opcional e paga) | vazio |

## Como usar

Sempre com o ambiente ativado (`.venv\Scripts\activate`):

| Comando | O que faz |
|---|---|
| `jarvis` | Abre o **orb** (janela animada) e já começa a ouvir. Feche a janela para sair. |
| `jarvis --modo voz` | Voz **só no terminal**, mostrando as falas e as ações. Ctrl+C para sair. |
| `jarvis --modo texto` | Modo **texto** no terminal. Digite `sair` para encerrar. |
| `jarvis --criar-atalho` | Cria o atalho **Jarvis** na Área de Trabalho (abre o orb). |
| `jarvis --versao` | Mostra a versão instalada. |
| `python -m jarvis` | Mesmo que `jarvis` (útil se o comando não for encontrado). |

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

## Segurança (resumo)

O Jarvis foi feito para ser seguro para qualquer pessoa que baixar:

- **Lista fechada de ações.** A IA só escolhe entre as ferramentas do projeto. Ela nunca
  roda comandos livres de terminal e nunca executa `.exe`, `.bat`, `.ps1` e afins por caminho.
- **Apagar só com clique manual.** Abre uma janela do Windows e só o seu clique em "Sim"
  autoriza. A IA não consegue confirmar sozinha. A janela fecha sozinha depois de um tempo
  (vale como "Não"). E o arquivo vai para a **Lixeira** (dá para recuperar).
- **Pastas protegidas.** Raiz do disco (`C:\`), Windows, Arquivos de Programas, ProgramData e
  a própria pasta do Jarvis (onde fica a sua chave): nada é criado, movido ou apagado nelas.
- **Nunca sobrescreve.** Mover, copiar ou criar com um nome que já existe é recusado.
- **Processos do sistema e o terminal do Jarvis não podem ser fechados.**
- **A chave fica só no `.env`**, que está no `.gitignore` e nunca vai para o GitHub.

Detalhes em [docs/SEGURANCA.md](docs/SEGURANCA.md).

## Quer usar a sua própria voz?

O modo voz usa o **Gemini Live**, que fala com **vozes prontas do Google**. Para trocar,
edite a linha `JARVIS_VOZ` no seu `.env`, por exemplo:

```
JARVIS_VOZ=Puck
```

Algumas opções: `Charon` (padrão, grave e calma), `Puck`, `Kore`, `Fenrir`, `Aoede`, `Orus`.
A lista completa está na documentação do Gemini (Live API, "voices").

### Voz do ElevenLabs (opcional e paga)

Se você tem conta no ElevenLabs, o Jarvis pode falar com uma voz de lá (a sua, ou uma voz
criada do zero). O Gemini continua sendo o ouvido e o cérebro; só a fala muda.

1. Pegue a chave em *Settings > API Keys* e o **ID da voz** na aba *Voices*.
2. No `.env`, preencha:
   ```
   ELEVENLABS_API_KEY=sua_chave
   ELEVENLABS_VOICE_ID=id_da_voz
   ```
3. Rode `jarvis` de novo. No terminal aparece `voz ElevenLabs eleven_flash_v2_5`.

O que muda na prática:

- **Custo:** cada fala consome créditos do seu plano do ElevenLabs.
- **Velocidade:** um pouco mais lenta que a voz do Google, porque o texto passa por mais
  um serviço. O Jarvis fala frase por frase para compensar.
- **Segurança:** se o ElevenLabs falhar (sem créditos, chave errada, rede), o Jarvis avisa
  uma vez e continua com a voz do Google. Nunca trava.
- Deixe as duas linhas **vazias** para voltar à voz grátis do Google.

> **Importante:** nunca clone a voz de um ator, de um personagem ou de outra pessoa sem
> autorização dela. Use a sua própria voz ou uma voz criada do zero.

## Estrutura de pastas

```
jarvis/
├── pyproject.toml            # dependências e o comando "jarvis"
├── requirements.txt          # mesmas dependências, para quem prefere pip install -r
├── .env.example              # modelo de configuração (copie para .env)
├── src/jarvis/
│   ├── __main__.py           # linha de comando (jarvis / python -m jarvis)
│   ├── config.py             # lê o .env (Settings)
│   ├── errors.py             # erros amigáveis e o "safe_tool"
│   ├── logging_setup.py      # log em logs/jarvis.log
│   ├── persona.py            # personalidade (prompt de sistema)
│   ├── os_integration/
│   │   ├── windows.py        # janelas, processos e caixa de confirmação do Windows
│   │   └── shortcut.py       # atalho na Área de Trabalho
│   ├── ui/
│   │   ├── orb_window.py     # janela do orb (pywebview)
│   │   ├── orb.html          # a animação da esfera (Canvas, sem internet)
│   │   └── jarvis.ico        # ícone do atalho
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
├── examples/
│   └── 01_cerebro_texto.py   # versão didática: só o "cérebro" (usado nos vídeos)
├── tests/                    # testes automáticos (pytest)
└── docs/
    ├── ARQUITETURA.md
    ├── SEGURANCA.md
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

Os testes rodam em qualquer sistema (inclusive Linux), sem internet e sem microfone.

Para criar uma **ação nova**: escreva o método na classe de ferramentas certa em
`src/jarvis/tools/`, com docstring em português e seção `Args` (a IA lê essa descrição),
acrescente o nome em `TOOL_NAMES` e escreva um teste. Ações que mexem em arquivos devem
passar pelo `PathGuard`.

## Problemas comuns

| O que acontece | O que fazer |
|---|---|
| `python` não é reconhecido | Reinstale o Python marcando **"Add Python to PATH"** e abra um PowerShell novo. |
| "a execução de scripts foi desabilitada" | Rode `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e confirme com `S`. |
| `jarvis` não é reconhecido | Ative o ambiente (`.venv\Scripts\activate`) ou use `python -m jarvis`. |
| Erro ao instalar o `pyaudio` | Atualize o pip (`python -m pip install --upgrade pip`) e tente de novo. Use Python 3.11 ou 3.12. |
| "Não encontrei a GEMINI_API_KEY" | Confira se o arquivo se chama `.env` (e não `.env.txt`) e se a chave foi colada sem aspas. |
| Ele não me ouve | Confira o microfone padrão do Windows (Configurações > Sistema > Som > Entrada). |
| Ele responde a si mesmo / se interrompe | Use fone de ouvido, ou deixe `JARVIS_FONE=nao`. |
| A janela do orb não abre | Instale o **WebView2** da Microsoft (já vem no Windows 11) e rode `jarvis --modo voz` para ver a mensagem. |
| Qualquer outro problema | Veja o arquivo `logs\jarvis.log`: o erro completo fica registrado lá. |

## Limites conhecidos

- **A camada grátis tem cota.** Se usar muito num dia, o Google pode recusar por um tempo.
- **A API às vezes fica instável** (erro 5xx, "modelo sobrecarregado"). No modo texto o Jarvis
  tenta o modelo reserva; no modo voz ele reconecta sozinho.
- **As ações no computador só funcionam no Windows.** Em outros sistemas ele conversa,
  mas avisa que não consegue executar.
- O modelo Live é "preview": o nome pode mudar. Se parar de funcionar, confira o nome
  atual no Google AI Studio e ajuste `GEMINI_LIVE_MODEL` no `.env`.

## Créditos e aviso

"Jarvis" é só um apelido. Este projeto **não é afiliado à Marvel, à Disney nem ao Google**.
A voz é uma voz pronta do Google (não clonada de ator) e o visual é original.

Diário de desenvolvimento: [docs/DIARIO.md](docs/DIARIO.md).

## Licença

[MIT](LICENSE): uso livre. Pode usar, copiar, modificar, distribuir e até vender, para
qualquer fim. A única condição é manter o aviso de copyright e a licença junto do código.
