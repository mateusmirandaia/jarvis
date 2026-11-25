# Política de segurança

As regras de segurança do Jarvis (lista fechada de ações, pastas protegidas, onde fica a chave,
o que a janela pode fazer) estão explicadas em [docs/SEGURANCA.md](docs/SEGURANCA.md).

## Versões que recebem correção

Só a versão mais recente (a última do [CHANGELOG.md](CHANGELOG.md)) recebe correções de
segurança. Antes de reportar, confira se o problema acontece nela.

## Como reportar uma falha

1. Se o GitHub mostrar o botão **"Report a vulnerability"** (aba *Security* do repositório),
   use ele: o relato fica privado até a correção.
2. Se não houver esse botão, abra uma *issue* com o título começando por `[segurança]` e
   descreva **só o comportamento** (o que você pediu ao Jarvis, o que ele fez e o que deveria
   ter feito). Não publique um passo a passo de ataque; eu entro em contato para os detalhes.

## Nunca cole no relato

- a sua chave do Google (`GEMINI_API_KEY`) ou do ElevenLabs, nem um pedaço dela;
- o conteúdo do seu `.env` (do projeto ou de `%APPDATA%\Jarvis\.env`);
- caminhos com o seu nome de usuário ou dados pessoais (troque por `C:\Users\<usuario>\...`);
- trechos do log sem revisar antes (o Jarvis apaga as chaves do log, mas confira).

Se você colou uma chave por engano em qualquer lugar público, **apague a chave** no
[Google AI Studio](https://aistudio.google.com/apikey) (ou no ElevenLabs) e crie outra. Depois
é só colar a nova na engrenagem do Jarvis, aba **Chave do Google**.
