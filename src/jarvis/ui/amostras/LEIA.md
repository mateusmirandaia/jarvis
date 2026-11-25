# Amostras de voz

Uma amostra curta por voz do Google, tocada pelo botão **Ouvir** nos cartões de voz
(assistente de configuração e engrenagem > Geral). Nome do arquivo = id da voz:

`Charon.wav`, `Puck.wav`, `Kore.wav`, `Fenrir.wav`, `Aoede.wav`, `Leda.wav`, `Orus.wav`, `Zephyr.wav`

Frase: "Olá, senhor. Eu sou o Jarvis, seu assistente pessoal." (WAV PCM 16-bit, 24 kHz, mono).

## Como gerar

São geradas **uma vez**, pelo script, com a sua chave do Gemini e o modelo de TTS do Google:

```powershell
python scripts/gerar_amostras_voz.py            # só as que faltam
python scripts/gerar_amostras_voz.py --forcar   # refaz todas
python scripts/gerar_amostras_voz.py --vozes Puck,Kore
```

O script pula as que já existem, espera entre uma voz e outra (a conta grátis tem limite de
pedidos por minuto) e nunca mostra a chave. Rode antes de gerar o instalador: os `.wav`
desta pasta vão junto no pacote.

Se um arquivo não existir, o botão Ouvir mostra "amostra indisponível" (nada quebra).

> O `.gitignore` ignora `*.wav` em geral, mas abre exceção para esta pasta: as amostras
> são versionadas no repositório.
