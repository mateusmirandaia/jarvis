# Avisos gravados

Frases curtas que o Jarvis toca quando algo dá errado, **sem precisar de internet**
(WAV PCM 16-bit, 24 kHz, mono). Nunca são geradas na hora.

| Arquivo | Quando toca | Frase |
|---|---|---|
| `internet_<Voz>.wav` (8 vozes) | a conexão cai, erro de rede/servidor, ou ele fica 12 s sem responder | "Desculpe, estou tendo problemas com a sua internet. Aguarde um momento ou tente daqui a pouco." |
| `elevenlabs_Charon.wav` | a voz personalizada (ElevenLabs) falha | "Minha voz personalizada está com problemas. Vou continuar com a voz padrão." |

Vozes: `Charon`, `Puck`, `Kore`, `Fenrir`, `Aoede`, `Leda`, `Orus`, `Zephyr`.

O aviso de internet toca na voz do Google escolhida (também para quem usa ElevenLabs) e no
máximo 1 vez a cada 30 s. Se o arquivo da voz faltar, usa o do Charon; se nada existir, o
Jarvis só escreve o aviso na tela (nada trava).

## Como gerar

Uma vez, antes do build do instalador, com a sua chave do Gemini:

```powershell
python scripts/gerar_avisos_voz.py            # só os que faltam
python scripts/gerar_avisos_voz.py --forcar   # refaz todos
python scripts/gerar_avisos_voz.py --vozes Puck,Kore
```

O script nunca mostra a chave. Os `.wav` desta pasta vão junto no pacote.
