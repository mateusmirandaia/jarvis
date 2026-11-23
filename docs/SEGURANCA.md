# Segurança do Jarvis

O Jarvis mexe no seu computador. Por isso ele segue regras fixas, escritas no código, que a
IA **não consegue mudar** — nem se alguém pedir com jeitinho. Estas regras valem para todo
mundo que baixar o projeto.

## 1. Lista fechada de ações

- A IA só pode escolher entre as ferramentas registradas no `ToolRegistry`
  (`src/jarvis/tools/__init__.py`). Qualquer outro nome é recusado.
- **Nunca** existe uma ferramenta de "rodar comando no terminal".
- Programas são abertos **pelo nome** ("calculadora", "chrome"), nunca por caminho.
- Arquivos executáveis e scripts **não são abertos** por caminho: `.exe`, `.bat`, `.cmd`,
  `.ps1`, `.vbs`, `.js`, `.msi`, `.scr`, `.com`, `.reg`, `.jar`, `.hta`, `.wsf`.

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
- a **pasta do próprio Jarvis** (onde ficam o código e o seu `.env` com a chave).

A verificação é feita pelo `PathGuard.is_protected()` (`src/jarvis/tools/security.py`),
sempre com o caminho já resolvido (sem truques com `..`). A busca de arquivos também pula
pastas protegidas e pastas ocultas (que começam com `.` ou `$`).

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

## 6. A chave fica só no `.env`

- A `GEMINI_API_KEY` é lida do arquivo `.env`, que está no `.gitignore` e **nunca** vai
  para o GitHub. O repositório traz apenas o `.env.example`, sem chave.
- A chave não aparece no terminal nem no log.
- Em gravações e lives, **nunca abra o `.env` na tela**. Se a chave vazar, apague-a no
  Google AI Studio e crie outra.

## 7. Erros não vazam detalhes técnicos

- Cada ferramenta passa pelo `safe_tool`: se algo der errado, o erro completo vai para
  `logs/jarvis.log` e a IA recebe só uma frase simples para falar
  (por exemplo: "o Windows não me deu permissão para isso").
- Resultados longos são cortados em 700 caracteres para não encher a conversa.
- Cada ferramenta tem tempo máximo (20 s; 120 s para apagar, com a janela de confirmação
  fechando sozinha 10 s antes). Se passar disso, o Jarvis desiste e avisa.

## 8. Voz e imagem

- A voz é uma voz pronta do Google. **Nunca clone a voz de um ator ou de outra pessoa**
  sem autorização dela.
- "Jarvis" é só um apelido; o projeto não é afiliado à Marvel, à Disney nem ao Google.

## Encontrou uma falha?

Abra uma *issue* no GitHub descrevendo o problema **sem** colar a sua chave, caminhos
pessoais ou o conteúdo do seu `.env`.
