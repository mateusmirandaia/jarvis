# Arquitetura do Jarvis

Este documento descreve a versão 0.9.0 e explica como as peças se conectam. Se você está começando, leia de cima
para baixo: primeiro o fluxo, depois o papel de cada arquivo.

## Fluxo do modo voz

```
 Você fala
    |
    v
+-------------+   PCM16 mono 16 kHz    +----------------------------+
|  Microfone  | ---------------------> |  AudioIO (assistants/      |
+-------------+   blocos de 512        |  audio.py, pyaudio)        |
                                       +-------------+--------------+
                                                     |
                                                     v
                                  +--------------------------------------+
                                  |  LiveAssistant (live_assistant.py)   |
                                  |  - conexão com o Gemini Live (v1beta)|
                                  |  - meio-duplex: não escuta enquanto  |
                                  |    fala (evita eco)                  |
                                  |  - reconecta sozinho (até 15 s)      |
                                  +------+---------------------+---------+
                                         |                     ^
                         áudio + prompt  |                     | áudio da resposta
                         + ferramentas   v                     | + transcrições
                                  +--------------------------------------+
                                  |        Gemini Live (Google)          |
                                  |  entende a fala, decide e responde   |
                                  +------+-------------------------------+
                                         |
                          "chame a ferramenta X com estes argumentos"
                                         v
                                  +--------------------------------------+
                                  |  ToolRegistry (tools/__init__.py)    |
                                  |  - só aceita nomes da LISTA FECHADA  |
                                  |  - cada ferramenta embrulhada pelo   |
                                  |    safe_tool (erro vira frase)       |
                                  |  - tempo máximo por ferramenta       |
                                  +------+-------------------------------+
                                         |
            +-------------+--------------+--------------+------------------+
            v             v                             v                  v
     SystemTools      AppTools                      WebTools           FileTools
     (data/hora)      (abrir/fechar apps)           (sites/pesquisa)   (arquivos)
                            |                                              |
                            v                                              v
                    os_integration/windows.py                     tools/security.py
                    (janelas, processos, caixa                    (PathGuard: pastas
                     de confirmação Sim/Não)                       protegidas, atalhos)
                                         |
                       resultado em texto (até 700 caracteres)
                                         v
                                  Gemini Live -> resposta falada
                                         |
                                         v
+---------------+   PCM16 mono 24 kHz   +----------------------------+
| Alto-falante  | <-------------------- |  AudioIO                   |
|  (use fone)   |                       +----------------------------+
+---------------+
```

No **modo texto** o caminho é o mesmo, trocando microfone/alto-falante pelo teclado/tela e o
Gemini Live pelo modelo de texto (`TextAssistant`), com troca automática para o modelo
reserva quando o principal responde com erro 5xx.

## Inicialização (`jarvis` / `python -m jarvis`)

1. `__main__.main()` lê os argumentos (`--modo orb|voz|texto`, `--criar-atalho`, `--versao`).
2. `Settings.from_env()` junta as configurações de todas as fontes (veja
   [Prioridade das configurações](#prioridade-das-configurações)).
   - Nos modos **voz** e **texto** (`exigir_chave=True`), sem chave ele mostra uma mensagem
     amigável e sai com código 1.
   - No modo **orb** (`exigir_chave=False`), sem chave ele **não sai**: devolve `api_key=""` e
     a janela abre no assistente de configuração.
3. `setup_logging()` liga o log rotativo (`logs/jarvis.log` do projeto; no programa instalado,
   `%APPDATA%\Jarvis\logs\jarvis.log`). Todo texto passa por `redigir`, que troca chaves por `…`.
4. Modo escolhido:
   - **orb** (padrão): `_run_orb()` garante uma janela só (`acquire_single_instance`), cria a
     `ApiJs`, a `OrbWindow` (thread principal) e o `Controlador`. Se já houver chave, o
     controlador inicia o `LiveAssistant` em segundo plano; senão, espera o fim do assistente
     de configuração. Ao fechar a janela, o controlador para o assistente.
   - **voz**: `ToolRegistry` + `LiveAssistant` no terminal.
   - **texto**: `ToolRegistry` + `TextAssistant` no terminal.

## Prioridade das configurações

`config.py` lê três fontes, nesta ordem (**a primeira que tiver o valor ganha**; vazio e texto
de exemplo como `cole_sua_chave_aqui` contam como "não definido"):

1. variáveis de ambiente do processo;
2. `.env` da pasta do projeto (só em desenvolvimento; congelado, não é procurado);
3. `.env` da pasta do usuário, `%APPDATA%\Jarvis\.env` (`~/.config/jarvis/.env` fora do
   Windows), que é **onde a janela grava as chaves** (`armazenamento.py`).

Para **voz, nome e fone**, se nenhuma fonte acima definir, vale o `preferencias.json` (escolha
da janela) e, por fim, o padrão (`Charon`, vazio, sem fone). A **fonte de voz** (`fonte_voz`:
`google` ou `elevenlabs`) só existe no `preferencias.json`: com `google`, a chave do ElevenLabs
pode continuar guardada, mas o Jarvis fala com a voz do Google (`Settings.elevenlabs_pausado`).

| Configuração | Ambiente | `.env` do projeto | `%APPDATA%\Jarvis\.env` | `preferencias.json` | Padrão |
|---|---|---|---|---|---|
| `GEMINI_API_KEY`, `ELEVENLABS_*` | 1º | 2º | 3º | — | vazio |
| `JARVIS_VOZ`, `JARVIS_NOME_USUARIO`, `JARVIS_FONE` | 1º | 2º | 3º | 4º (`voz`, `nome`, `fone`) | `Charon` / vazio / sem fone |
| Fonte da voz (Google ou ElevenLabs) | — | — | — | `fonte_voz` | ElevenLabs se configurado, senão Google |
| Visual | 1º (`JARVIS_VISUAL`) | 2º | 3º | 4º (`visual`) | `galaxia` |
| Modelos, `JARVIS_SILENCIO_MS` | 1º | 2º | 3º | — | veja o README |

Consequência importante: uma linha `JARVIS_VOZ=...` no `.env` do projeto **prende** a voz e a
janela não consegue trocá-la. A `ApiJs` detecta isso depois de salvar e devolve um aviso
(`MSG_PREFS_DO_ENV`); para a chave e o ElevenLabs há avisos parecidos (`MSG_CHAVE_DO_PROJETO`,
`MSG_EL_PRESA`). Por isso o `.env.example` traz só a `GEMINI_API_KEY` ativa.

`Settings.api_key_source` diz de onde veio a chave (`ambiente`, `projeto`, `usuario` ou `""`);
a aba **Chave do Google** usa isso para avisar que trocar a chave ali não muda a que vale.

## Configuração pela janela

### Quem fala com quem

```
 orb.html (JavaScript)                       Python
 ---------------------                       ------
 window.pywebview.api.<método>(...)  ---->   PonteJs (ponte_js)  ---->  ApiJs (api_config.py)
                                             só os 15 métodos           |-- verificacao.py (testa chaves)
                                                                        |-- armazenamento.py (.env do usuário)
                                                                        |-- preferencias.py (preferencias.json)
                                                                        |-- vozes.py (amostras)
                                                                        |-- microfone.py (teste do microfone)
                                                                        '-- Controlador (iniciar/reiniciar)
 window.jarvis.setMicTeste(n)        <----   OrbWindow (fila "despachante", evaluate_js)
 window.jarvis.avisoChave(msg)       <----   Controlador -> OrbWindow.on_aviso_chave
```

- O pywebview executa **qualquer** nome que a página mandar, inclusive atributos internos. Por
  isso a janela não recebe a `ApiJs`, e sim `ponte_js(api)`: uma classe `PonteJs` sem
  atributos (`__slots__ = ()`) que só tem as funções de `METODOS_PUBLICOS` e guarda a `ApiJs`
  na closure. Um teste garante que esses são os únicos métodos públicos.
- Os 15 métodos: `abrir_link`, `amostra_voz`, `aplicar_configuracao`, `concluir_configuracao`,
  `elevenlabs_desligar`, `elevenlabs_listar_vozes`, `elevenlabs_salvar`, `elevenlabs_testar`,
  `estado_config`, `microfone_iniciar`, `microfone_parar`, `salvar_chave`,
  `salvar_preferencias`, `salvar_visual`, `testar_chave`.
- Todo método é embrulhado por `_seguro`: nenhum levanta exceção para o JavaScript; erro vira
  `{"ok": False, "mensagem": ...}` (ou `False`). Nenhum devolve ou registra uma chave: só
  `chave_final` (`…abcd`, os 4 últimos caracteres).
- `abrir_link` só aceita **nomes** de uma lista fechada (`LINKS`: chave do Google, ElevenLabs,
  repositório, Instagram; e as pastas `pasta_config` e `pasta_logs`). A página nunca manda URL.
- Chamadas de Python para a página (nível do microfone no teste, aviso de chave inválida) vão
  pela fila da `OrbWindow`, nunca direto da `ApiJs`.

### Assistente da primeira vez (5 passos)

`montar_config()` põe `precisaConfigurar: true` no `JARVIS_CONFIG` quando **nenhuma fonte**
tem chave. A página então abre o assistente:

1. **Boas-vindas.**
2. **Chave do Google**: `abrir_link("chave_google")` e `testar_chave(chave)`
   (`verificacao.testar_chave_gemini`, com tempo máximo de 12 s e mensagens simples para
   chave inválida, sem internet, limite da conta grátis e Google instável).
3. **Microfone**: `microfone_iniciar()` abre o `TesteMicrofone` numa thread e manda o volume
   ~20 vezes por segundo (`setMicTeste`); `microfone_parar()` fecha. Para sozinho em 5 min.
   Caixinha "Estou usando fone de ouvido".
4. **Personalizar**: nome (até 40 caracteres, numa linha), voz (cartões com **Ouvir**, que chama
   `amostra_voz(id)` e recebe o WAV como `data:audio/wav;base64,...`) e visual.
5. **Tudo pronto**: "Começar a usar" chama `salvar_chave`, `salvar_preferencias` e
   `concluir_configuracao()`, que marca `configurado: true` e pede ao `Controlador` para iniciar
   o assistente de voz. O assistente de configuração fecha e a janela continua aberta, já ouvindo.

### Engrenagem (4 abas)

| Aba | Métodos usados |
|---|---|
| Geral | `salvar_preferencias({nome, voz, fone, fonte_voz})`, `amostra_voz`, `salvar_visual` |
| Chave do Google | `testar_chave` (campo vazio testa a chave salva), `salvar_chave` |
| Voz personalizada (ElevenLabs) | `elevenlabs_listar_vozes`, `elevenlabs_testar` (gasta créditos; a página pede confirmação), `elevenlabs_salvar`, `elevenlabs_desligar` |
| Sobre | `abrir_link("repositorio" / "instagram" / "pasta_config" / "pasta_logs")` |

"Salvar e aplicar" grava o que mudou (chave nova só depois de testada; ElevenLabs validado antes
das preferências, para não salvar pela metade) e chama `aplicar_configuracao()`, que faz
`Controlador.reiniciar()` com as configurações novas.

`salvar_preferencias` aceita `fonte_voz` (`google` | `elevenlabs`); escolher `elevenlabs` sem
chave e voz do ElevenLabs configuradas é recusado. `elevenlabs_desligar` apaga a chave e a voz do
`.env` do usuário e marca `fonte_voz=google`; se elas estiverem no `.env` do projeto, ficam lá,
mas o Jarvis passa a falar com a voz do Google.

### Controlador

`controlador.py` roda o `LiveAssistant` numa thread com o **próprio loop asyncio**. `iniciar`,
`parar` e `reiniciar` podem ser chamados de qualquer thread (um comando por vez); parar cancela
a tarefa dentro do loop dela, o que fecha microfone, alto-falante e a conexão do jeito normal.
Se uma rodada não terminar a tempo (5 s), ele não começa outra enquanto ela viver (seriam dois
assistentes no mesmo microfone). Se o Google recusar a chave ao conectar (`ChaveInvalidaError`),
ele não tenta de novo: põe o estado `offline` e chama `on_aviso_chave`, e a janela mostra o
botão **Atualizar chave**. Qualquer outra falha vira uma linha "sistema" na conversa.

### Gravação no disco

- `armazenamento.salvar_segredos()` só aceita `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`,
  `ELEVENLABS_VOICE_ID` e `ELEVENLABS_MODEL`, com valores só de caracteres seguros
  (`[A-Za-z0-9_.:-]`, até 256), para ninguém injetar outra variável pelo valor. Grava de forma
  atômica (temporário na mesma pasta + `os.replace`) e preserva as outras linhas e comentários.
  O `.env` do projeto **nunca** é alterado pela janela.
- `armazenamento.ler_texto_env()` lê `.env` editado à mão no Windows em UTF-8 com BOM, UTF-16 ou
  ANSI (cp1252), para a chave não sumir por causa da codificação.
- `preferencias.atualizar()` também é atômico e nunca apaga as outras chaves do JSON.

## Modo congelado (instalador)

O instalador empacota o Jarvis com PyInstaller (pasta "onedir", sem console) e Inno Setup
(veja [INSTALADOR.md](INSTALADOR.md)). Quando roda assim, `sys.frozen` é verdadeiro e
`config.congelado()` devolve `True`:

- `pasta_pacote()` aponta para `sys._MEIPASS/jarvis` (onde ficam `ui/orb.html`, `ui/visuais` e
  `ui/amostras`); em desenvolvimento, para a pasta do pacote;
- o `.env` do projeto **não** é procurado (só ambiente e `%APPDATA%\Jarvis\.env`);
- os logs vão para `%APPDATA%\Jarvis\logs`;
- `packaging/jarvis_entry.py` chama a mesma `main()` da CLI; sem argumentos, abre a janela;
- sem console (`sys.stdout` é `None`), as mensagens para o usuário viram uma caixa do Windows.

## Como a janela é montada (visuais)

O pywebview recebe a página como **texto** (`create_window(html=...)`), então ela não consegue
carregar arquivos vizinhos. Por isso o Python monta uma página única antes de abrir a janela:

```
Settings.visual (JARVIS_VISUAL) --+
                                  +--> preferencias.visual_inicial() --> montar_config()
preferencias.json (salvo) --------+    (.env > salvo > "galaxia")         {visual, primeiraVez,
                                                                            info, config,
                                                                            precisaConfigurar}
                                                                                 |
orb.html ----------------------------------------------------------------> montar_html()
   /*JARVIS_CONFIG*/      <-- "window.JARVIS_CONFIG = {...};" (JSON, "</" escapado)
   <!--JARVIS_VISUAIS-->  <-- um <script> por ui/visuais/*.js, em ordem alfabética
                                                                                 |
                                                                                 v
                                   webview.create_window(html=..., js_api=ponte_js(ApiJs))
```

1. `preferencias.visual_inicial()` decide o visual: `JARVIS_VISUAL` (se for um id válido),
   senão o salvo em `preferencias.json`, senão `None` (nada escolhido). Nesse caso
   `montar_config()` usa `preferencias.VISUAL_PADRAO` (`galaxia`, a Galáxia Neural) e marca
   `primeiraVez: true` só como informação: a janela abre direto no visual e a tela de escolha
   aparece apenas pelo botão "Trocar visual" (ou "Escolher visual" no assistente e na
   engrenagem). No `orb.html`, id desconhecido também cai na `galaxia`; um visual que **falha**
   (erro ao criar ou desenhar) cai no `globo`, o mais simples, e o `globo` cai num círculo de
   reserva.
2. `config` é o mesmo objeto de `estado_config()` (sem chaves: só `chave_final`), e
   `precisaConfigurar` diz se o assistente de configuração deve abrir.
3. `montar_html()` troca os dois marcadores do `orb.html`. Se um marcador faltar, a página segue
   sem aquela parte e fica um aviso no log (a janela nunca deixa de abrir por isso).
4. Cada `visuais/<id>.js` chama `JarvisVisuais.registrar({id, nome, descricao, paleta, hud,
   criar()})`. A lista oficial de ids é `preferencias.VISUAIS`, e um teste garante que cada id
   tem o seu `.js` e vice-versa.
5. Quando a pessoa escolhe um visual, a página chama `salvar_visual(id)` (um dos 15 métodos da
   ponte): ele valida o id e grava de forma atômica, sem apagar outras chaves. Nunca levanta
   erro: devolve `False`.

**Paletas.** Cada visual declara uma `paleta`; o `orb.html` aplica as mesmas cores em três
lugares: variáveis CSS (`body[data-paleta=...]`, para o painel e os textos), o objeto
`PALETAS` (entregue ao visual em `q.cores`) e as cores dos estados (indicador, camadas, linha do
tempo e gráficos, via `corEstado()`/`corGrafico()`). Todas têm as chaves `fundo`, `superficie`,
`linha`, `texto`, `texto2`, `primaria`, `escura`, `destaque` e `erro`.

| Paleta | Visuais | Base | Ouvindo / Pensando / Falando |
|---|---|---|---|
| `petroleo` | globo, cortex, reator, holograma | fundo `#030605`, primária `#2FB5A8`, destaque limão `#C6F000` | primária / primária / destaque |
| `aurora` | mapa, esfera, cerebro | fundo `#05070F`, texto `#E6F1FF` | `#38E1FF` / `#8B7CFF` / `#FFB23F` |
| `aura` | aura | fundo `#02040B`, primária `#2F7BFF`, ouro `#FFD25A` | `#7DB8FF` / `#2F7BFF` / `#FFD25A` |
| `nuvem` | galaxia | Transformative Teal (WGSN/Coloro 2026) + Cloud Dancer (Pantone 2026): fundo `#041012`, superfície `#08201F`, linha `#12403D`, texto `#F0EEE9`, texto2 `#8FB8B2`, primária `#2BA79B`, escura `#1E7F7A`, clara `#9FE3DA`, destaque `#F0EEE9`, erro `#FF6B6B` | `#5FC8BE` / `#9FE3DA` / `#F0EEE9` |

Na `nuvem`, o texto principal tem contraste 16,6:1 sobre o fundo e o secundário 8,9:1 (7,8:1
sobre a superfície dos painéis), acima do mínimo de 4,5:1 para letra pequena.

## Como a janela recebe os eventos

```
LiveAssistant --on_state / on_level / on_transcript--> OrbWindow --evaluate_js--> orb.html
             --on_tool(nome, ok) / on_latency(s)---->            window.jarvis.setState,
   ouvindo / pensando / falando / sem conexao        setLevel, addLine, addTool, setLatency
                                                     (no max. 30 atualizacoes de volume por s)
```

- `on_latency(segundos)` sai no mesmo ponto em que o atraso vai para o log: da última vez que
  ele ouviu o senhor até o primeiro áudio da resposta (uma vez por resposta).
- `on_tool(nome, ok)` sai depois de cada ação executada. `ok` é `False` quando a ação não é
  permitida, estoura o tempo, levanta erro ou devolve um texto `"ERRO: ..."` do `safe_tool`.
- Os dois eventos chegaram na v0.6.0. O `LiveAssistant` os chama com `getattr` e dentro de
  `try/except`: um observador antigo (sem esses métodos) ou com defeito nunca derruba o
  assistente.
- A `OrbWindow` só **enfileira** o JavaScript (com `json.dumps` em todo valor); uma thread
  própria envia para a janela. O loop de voz nunca espera a interface.

O `LiveAssistant` não sabe nada de janela: ele só avisa um `AssistantObserver`. No terminal,
o observador é o `NullObserver` (não faz nada). Assim dá para trocar a interface sem mexer na
lógica de voz.

## Papel de cada módulo

| Módulo | Responsabilidade |
|---|---|
| `jarvis/__main__.py` | Linha de comando. Modo orb abre a janela mesmo sem chave; modos voz/texto tratam `ConfigError` (mensagem amigável) e Ctrl+C ("Até logo, senhor."). Sem console, as mensagens viram caixa do Windows. |
| `jarvis/config.py` | `Settings`: chave e de onde ela veio, modelos, voz, nome, fone, ElevenLabs (e se está pausado), visual forçado, tempos máximos, pasta do projeto, arquivo de log. Lê as fontes na ordem de prioridade. `congelado()`, `pasta_pacote()`, `raiz_projeto()`, `pasta_logs()`. |
| `jarvis/armazenamento.py` | `.env` de segredos da pasta do usuário: `salvar_segredos()` (lista fechada de variáveis, valores seguros, escrita atômica, preserva o resto), `ler_texto_env()` (BOM/UTF-16/ANSI) e `final_da_chave()` (`…abcd`). |
| `jarvis/controlador.py` | `Controlador`: inicia, para e reinicia o `LiveAssistant` numa thread com loop próprio; avisa a janela quando a chave é recusada (`on_aviso_chave`). |
| `jarvis/verificacao.py` | Testes rápidos das chaves: `testar_chave_gemini`, `listar_vozes_elevenlabs`, `testar_voz_elevenlabs`, verificações de formato. Mensagens curtas em português; a chave nunca vai para log, mensagem ou exceção. Rede injetável para os testes. |
| `jarvis/microfone.py` | `TesteMicrofone` (volume do microfone para a barra do passo 3, numa thread, com limite de 5 min) e `tocar_pcm` (toca o teste da voz do ElevenLabs). |
| `jarvis/vozes.py` | Lista fixa das 8 vozes do Google (`VOZES`, `voz_valida`) e as amostras `ui/amostras/<Voz>.wav` (no máximo 3 MB, precisa começar com `RIFF`) entregues como `data:` URL. |
| `jarvis/errors.py` | `JarvisError`, `ConfigError`, `ChaveInvalidaError`, `friendly_message()` (erro técnico -> frase simples) e `safe_tool()` (embrulha cada ferramenta: nunca levanta exceção, corta resultados longos, preserva nome/docstring/assinatura para a SDK). |
| `jarvis/logging_setup.py` | Log rotativo (1 MB, 3 cópias, UTF-8) na pasta de logs do modo atual, com `redigir` apagando chaves. |
| `jarvis/persona.py` | `build_system_prompt()`: a personalidade de mordomo britânico e as regras (agir sem pedir licença, apagar só com confirmação manual, erro em uma frase). |
| `jarvis/os_integration/shortcut.py` | `create_desktop_shortcut()`: cria `Jarvis.lnk` na Área de Trabalho apontando para o `pythonw.exe` do ambiente (`-m jarvis --modo orb`). Nunca sobrescreve. (O instalador cria os próprios atalhos.) |
| `jarvis/os_integration/windows.py` | Tudo que fala direto com o Windows: listar janelas do Alt+Tab, fechar janela (WM_CLOSE), encerrar processo, caixa de confirmação Sim/Não, caixa de mensagem, instância única, abrir com o programa padrão. Fora do Windows, devolve valores seguros. |
| `jarvis/ui/orb_window.py` | `montar_config()` e `montar_html()` (injeção da configuração e dos visuais) e `OrbWindow`: janela do pywebview (WebView2, 1280x760, mínimo 900x600) que implementa o `AssistantObserver`, recebe `on_mic_teste`/`on_aviso_chave` e envia tudo pela fila. Nunca derruba o assistente se a janela falhar. |
| `jarvis/ui/api_config.py` | `ApiJs` (os 17 métodos que a página chama, incluindo `permissoes_estado` e `salvar_permissoes`), `estado_config()` (resumo sem chaves) e `ponte_js()` (a fachada que o pywebview recebe). |
| `jarvis/ui/orb.html` | A "casca" da janela: assistente de 6 passos (com o passo Permissões), engrenagem com 5 abas (com a aba Permissões), tela de escolha com prévias, botão "Trocar visual", aviso "Atualizar chave", painel (conversa, volume, latência, camadas, atividade) e legenda. Sem bibliotecas nem internet. |
| `jarvis/ui/visuais/*.js` | Um arquivo por visual (`galaxia`, `globo`, `cortex`, `reator`, `holograma`, `mapa`, `esfera`, `aura`, `cerebro`), em Canvas 2D puro. Cada um reage aos 5 estados e ao volume. |
| `jarvis/ui/preferencias.py` | `preferencias.json`: `VISUAIS`, `VISUAL_PADRAO`, chaves `visual`, `voz`, `nome`, `fone`, `configurado`, `fonte_voz`, `elevenlabs_voz_nome`, `permissoes`; `carregar()`, `atualizar()` e `salvar_visual()` (atômicos, nunca levantam), `nome_valido()`, `visual_inicial()`. Arquivo em `%APPDATA%\Jarvis\` no Windows ou `~/.config/jarvis/` nos outros. |
| `jarvis/avisos.py` e `jarvis/avisos/` | Falas de aviso já gravadas (offline): `internet_<Voz>.wav` nas 8 vozes e `elevenlabs_Charon.wav`. `avisos.py` acha o arquivo certo (cai para Charon) e toca sem travar; o aviso de internet toca no máximo 1 vez a cada 30 s. Gerados por `scripts/gerar_avisos_voz.py`. |
| `jarvis/ui/amostras/` | `<Voz>.wav` de cada voz do Google (geradas por `scripts/gerar_amostras_voz.py`). |
| `jarvis/assistants/voice_output.py` | `VoiceOutput`: decide quem fala. Sem ElevenLabs, o áudio do Gemini toca direto; com ElevenLabs, o texto da resposta vira frases (`split_sentences`) faladas pelo ElevenLabs e o áudio do Gemini fica de reserva. Se o ElevenLabs falhar, volta para o Gemini sem travar. Interrupções descartam frases pendentes. |
| `jarvis/assistants/elevenlabs_voice.py` | `ElevenLabsVoice`: streaming HTTP do ElevenLabs em PCM 24 kHz (mesmo formato do alto-falante), modelo Flash v2.5 por padrão. |
| `jarvis/assistants/observer.py` | `AssistantObserver` (protocolo: estado, volume, falas, ações e latência), `NullObserver` e `pcm_level()` (volume do áudio). |
| `jarvis/assistants/audio.py` | `AudioIO`: microfone 16 kHz e saída 24 kHz (PCM16 mono, blocos de 512). |
| `jarvis/assistants/live_assistant.py` | `LiveAssistant`: sessão do Gemini Live, envio de áudio, fila de reprodução, chamadas de ferramenta em thread com tempo máximo, interrupção, transcrições e reconexão. Vigia o tempo de resposta: se o modelo não responder em `resposta_timeout_s` (12 s) depois da fala, toca o aviso de internet e reconecta. Conectar tem limite de 15 s; fechar microfone e alto-falante, de 1 s. Chave recusada levanta `ChaveInvalidaError` (reconectar não resolve). |
| `jarvis/assistants/text_assistant.py` | `TextAssistant`: chat no terminal com as mesmas ferramentas e fallback de modelo. |
| `jarvis/tools/__init__.py` | `ToolRegistry`: cria as classes, aplica o `safe_tool` e a **checagem de permissão na hora da chamada**, protege a pasta do projeto **e** a pasta do usuário (`%APPDATA%\Jarvis`), expõe `functions`, `names`, `get()`, `timeout_for()`. |
| `jarvis/tools/security.py` | `PathGuard` (atalhos "área de trabalho", "documentos", "downloads"; pastas protegidas), processos protegidos, extensões executáveis, `normalize()`. |
| `jarvis/tools/permissoes.py` | Modelo das permissões (`arquivos` em 4 níveis, `apps`, `internet`, `email`, `outros_drives`), padrão tudo desligado, mapa ferramenta → exigência (ferramenta fora do mapa = bloqueada), mensagens e a lista "Sempre bloqueado" do painel. |
| `jarvis/tools/office_tools.py` | `draft_email`: `mailto:` quando cabe, senão `.eml` com `X-Unsent: 1` em `Documentos\Jarvis\Rascunhos`. Nunca envia. |
| `jarvis/tools/system_tools.py` | `current_time`. |
| `jarvis/tools/app_tools.py` | `list_open_apps`, `open_app`, `close_app`. |
| `jarvis/tools/web_tools.py` | `open_website`, `web_search`. |
| `jarvis/tools/file_tools.py` | `create_folder`, `list_folder`, `find_file`, `open_file`, `move_or_rename`, `copy_item`, `create_text_file`, `read_file` (texto, PDF com texto, Word, Excel; até 25 MB e 20 mil caracteres), `write_word_document` (`.docx` novo, nunca sobrescreve), `delete_to_trash`. |
| `scripts/gerar_amostras_voz.py` | Gera as amostras das 8 vozes com o TTS do Gemini (uma vez; pula as que existem; nunca mostra a chave). |
| `packaging/` | `jarvis_entry.py` (ponto de entrada), `jarvis.spec` (PyInstaller), `jarvis.iss` (Inno Setup) e `build.ps1` (faz tudo e mostra o SHA-256). |

## Decisões importantes

- **Lista fechada.** A IA só enxerga as ferramentas registradas no `ToolRegistry`. Ação nova =
  método novo + nome em `TOOL_NAMES` + teste. A página da janela também tem a sua lista
  fechada: os 15 métodos da `PonteJs`.
- **Configuração sem arquivo.** Quem não é programador nunca precisa abrir um `.env`: a janela
  testa e grava as chaves em `%APPDATA%\Jarvis\.env` e as escolhas em `preferencias.json`,
  fora da pasta do programa (sobrevivem a atualizações e reinstalações).
- **Live na API `v1beta`.** Na SDK `google-genai` 3.x o padrão é `v1`, e o Live responde
  HTTP 404. O cliente do Live é criado com `HttpOptions(api_version="v1beta")`.
- **Ferramentas em thread com tempo máximo.** Cada chamada roda em
  `asyncio.to_thread` dentro de `asyncio.wait_for`: 20 s para a maioria e 120 s para
  `delete_to_trash` (ela espera o seu clique na janela). A janela de confirmação usa
  `MessageBoxTimeoutW` e fecha sozinha 10 s antes desse limite (conta como "Não"), para
  que um clique atrasado nunca apague nada depois que o Jarvis já desistiu.
- **Persona genérica.** O projeto é público: por padrão o Jarvis é "seu assistente pessoal".
  Quem quiser põe o próprio nome na janela ("Como devo te chamar?"). Ele sempre chama o
  usuário de "senhor".
- **Erro nunca derruba o Jarvis.** O `safe_tool` registra o erro completo no log e devolve à
  IA uma frase curta para ela falar. Na janela, `_seguro` faz o mesmo para o JavaScript.
- **Nomes em português e inglês (misto).** O código começou em inglês (`LiveAssistant`,
  `ToolRegistry`, `create_folder`...) e os módulos mais novos estão em português
  (`controlador`, `armazenamento`, `verificacao`, `salvar_preferencias`...). Docstrings,
  mensagens e parâmetros das ferramentas (`caminho`, `origem`, `destino`...) são em português,
  porque é a língua em que a IA conversa com você. Os nomes das ferramentas seguem em inglês
  para não quebrar o que a IA já conhece.
