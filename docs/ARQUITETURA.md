# Arquitetura do Jarvis

Este documento explica como as peças se conectam. Se você está começando, leia de cima
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
2. `Settings.from_env()` carrega o `.env`. Sem chave, mostra uma mensagem amigável e sai.
3. `setup_logging()` liga o log em `logs/jarvis.log` (o terminal fica limpo, só a conversa).
4. `ToolRegistry(settings)` monta a lista fechada de ferramentas.
5. Inicia o modo escolhido:
   - **orb** (padrão): abre a janela do orb (`OrbWindow`, na thread principal) e roda o
     `LiveAssistant` numa thread em segundo plano, com a janela como observador. Só uma janela
     do Jarvis pode ficar aberta por vez.
   - **voz**: `LiveAssistant` no terminal.
   - **texto**: `TextAssistant` no terminal.

### Como a janela é montada (visuais)

O pywebview recebe a página como **texto** (`create_window(html=...)`), então ela não consegue
carregar arquivos vizinhos. Por isso o Python monta uma página única antes de abrir a janela:

```
Settings.visual (JARVIS_VISUAL) --+
                                  +--> preferencias.visual_inicial() --> montar_config()
preferencias.json (salvo) --------+        (.env > salvo > None)          {visual, primeiraVez,
                                                                            info: voz, modelo,
                                                                            fone, nome}
                                                                                 |
orb.html ----------------------------------------------------------------> montar_html()
   /*JARVIS_CONFIG*/      <-- "window.JARVIS_CONFIG = {...};" (JSON, "</" escapado)
   <!--JARVIS_VISUAIS-->  <-- um <script> por ui/visuais/*.js, em ordem alfabética
                                                                                 |
                                                                                 v
                                        webview.create_window(html=..., js_api=_ApiJs())
```

1. `preferencias.visual_inicial()` decide o visual: `JARVIS_VISUAL` do `.env` (se for um id
   válido), senão o salvo em `preferencias.json`, senão `None` (primeira vez: a página abre a
   tela de escolha).
2. `montar_html()` troca os dois marcadores do `orb.html`. Se um marcador faltar, a página segue
   sem aquela parte e fica um aviso no log (a janela nunca deixa de abrir por isso).
3. Cada `visuais/<id>.js` chama `JarvisVisuais.registrar({id, nome, descricao, paleta, hud,
   criar()})`. A lista oficial de ids é `preferencias.VISUAIS`, e um teste garante que cada id
   tem o seu `.js` e vice-versa.
4. Quando a pessoa escolhe um visual, a página chama `window.pywebview.api.salvar_visual(id)`.
   O `_ApiJs` só expõe esse método: ele valida o id e grava o arquivo de forma atômica
   (temporário + `os.replace`), sem apagar outras chaves. Nunca levanta erro: devolve `False`.

### Como a janela recebe os eventos

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
| `jarvis/__main__.py` | Linha de comando. Trata `ConfigError` (mensagem amigável) e Ctrl+C ("Até logo, senhor."). |
| `jarvis/config.py` | `Settings`: chave, modelos, voz, nome do usuário (opcional), visual forçado (`JARVIS_VISUAL`), tempos máximos, pasta do projeto, arquivo de log. Lê o `.env`. |
| `jarvis/errors.py` | `JarvisError`, `ConfigError`, `friendly_message()` (erro técnico -> frase simples) e `safe_tool()` (embrulha cada ferramenta: nunca levanta exceção, corta resultados longos, preserva nome/docstring/assinatura para a SDK). |
| `jarvis/logging_setup.py` | Log rotativo (1 MB, 3 cópias, UTF-8) em `logs/`. |
| `jarvis/persona.py` | `build_system_prompt()`: a personalidade de mordomo britânico e as regras (agir sem pedir licença, apagar só com confirmação manual, erro em uma frase). |
| `jarvis/os_integration/shortcut.py` | `create_desktop_shortcut()`: cria `Jarvis.lnk` na Área de Trabalho apontando para o `pythonw.exe` do ambiente (`-m jarvis --modo orb`). Nunca sobrescreve. |
| `jarvis/ui/orb_window.py` | `montar_config()` e `montar_html()` (injeção da configuração e dos visuais) e `OrbWindow`: janela do pywebview (WebView2, 1280x760, mínimo 900x600) que implementa o `AssistantObserver`. Nunca derruba o assistente se a janela falhar. |
| `jarvis/ui/orb.html` | A "casca" da janela: registro dos visuais, tela de escolha com prévias, botão "Trocar visual", painel (conversa, volume, latência, camadas, atividade) e legenda. Sem bibliotecas nem internet. |
| `jarvis/ui/visuais/*.js` | Um arquivo por visual (`globo`, `cortex`, `reator`, `holograma`, `mapa`, `esfera`, `aura`), em Canvas 2D puro. Cada um reage aos 5 estados e ao volume. |
| `jarvis/ui/preferencias.py` | `VISUAIS` (lista oficial), `carregar()`, `salvar_visual()` (atômico, nunca levanta) e `visual_inicial()` (`.env` > salvo > primeira vez). Arquivo em `%APPDATA%\Jarvis\` no Windows ou `~/.config/jarvis/` nos outros. |
| `jarvis/assistants/voice_output.py` | `VoiceOutput`: decide quem fala. Sem ElevenLabs, o áudio do Gemini toca direto; com ElevenLabs, o texto da resposta vira frases (`split_sentences`) faladas pelo ElevenLabs e o áudio do Gemini fica de reserva. Se o ElevenLabs falhar, volta para o Gemini sem travar. Interrupções descartam frases pendentes. |
| `jarvis/assistants/elevenlabs_voice.py` | `ElevenLabsVoice`: streaming HTTP do ElevenLabs em PCM 24 kHz (mesmo formato do alto-falante), modelo Flash v2.5 por padrão. |
| `jarvis/assistants/observer.py` | `AssistantObserver` (protocolo: estado, volume, falas, ações e latência), `NullObserver` e `pcm_level()` (volume do áudio). |
| `jarvis/os_integration/windows.py` | Tudo que fala direto com o Windows: listar janelas do Alt+Tab, fechar janela (WM_CLOSE), encerrar processo, caixa de confirmação Sim/Não, abrir com o programa padrão. Fora do Windows, devolve valores seguros. |
| `jarvis/tools/security.py` | `PathGuard` (atalhos "área de trabalho", "documentos", "downloads"; pastas protegidas), processos protegidos, extensões executáveis, `normalize()`. |
| `jarvis/tools/system_tools.py` | `current_time`. |
| `jarvis/tools/app_tools.py` | `list_open_apps`, `open_app`, `close_app`. |
| `jarvis/tools/web_tools.py` | `open_website`, `web_search`. |
| `jarvis/tools/file_tools.py` | `create_folder`, `list_folder`, `find_file`, `open_file`, `move_or_rename`, `copy_item`, `create_text_file`, `delete_to_trash`. |
| `jarvis/tools/__init__.py` | `ToolRegistry`: cria as classes, aplica o `safe_tool`, expõe `functions`, `names`, `get()`, `timeout_for()`. |
| `jarvis/assistants/audio.py` | `AudioIO`: microfone 16 kHz e saída 24 kHz (PCM16 mono, blocos de 512). |
| `jarvis/assistants/live_assistant.py` | `LiveAssistant`: sessão do Gemini Live, envio de áudio, fila de reprodução, chamadas de ferramenta em thread com tempo máximo, interrupção, transcrições "Você:"/"Jarvis:" e "[ação]" no terminal. |
| `jarvis/assistants/text_assistant.py` | `TextAssistant`: chat no terminal com as mesmas ferramentas e fallback de modelo. |

## Decisões importantes

- **Lista fechada.** A IA só enxerga as ferramentas registradas no `ToolRegistry`. Ação nova =
  método novo + nome em `TOOL_NAMES` + teste.
- **Live na API `v1beta`.** Na SDK `google-genai` 3.x o padrão é `v1`, e o Live responde
  HTTP 404. O cliente do Live é criado com `HttpOptions(api_version="v1beta")`.
- **Ferramentas em thread com tempo máximo.** Cada chamada roda em
  `asyncio.to_thread` dentro de `asyncio.wait_for`: 20 s para a maioria e 120 s para
  `delete_to_trash` (ela espera o seu clique na janela). A janela de confirmação usa
  `MessageBoxTimeoutW` e fecha sozinha 10 s antes desse limite (conta como "Não"), para
  que um clique atrasado nunca apague nada depois que o Jarvis já desistiu.
- **Persona genérica.** O projeto é público: por padrão o Jarvis é "seu assistente pessoal".
  Quem quiser pode pôr o próprio nome em `JARVIS_NOME_USUARIO` no `.env`. Ele sempre chama
  o usuário de "senhor".
- **Erro nunca derruba o Jarvis.** O `safe_tool` registra o erro completo no log e devolve à
  IA uma frase curta para ela falar.
- **Código em inglês, conversa em português.** Classes e funções em inglês; docstrings,
  mensagens e parâmetros das ferramentas (`caminho`, `origem`, `destino`...) em português,
  porque é a língua em que a IA conversa com você.
