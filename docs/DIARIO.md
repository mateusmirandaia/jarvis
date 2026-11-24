# Diario do Jarvis

Uma linha por sessao: o que fiz, o que quebrou, como resolvi, quanto tempo levou.
Marque [UAU] para momento de Reels e [VERDADE] para o que o guru nao conta.

| Data | Etapa | O que fiz | O que quebrou / como resolvi | Tempo | Marca |
|---|---|---|---|---|---|
| 2026-11-23 | 0 | Pasta do projeto criada | - | - | - |
| 2026-11-23 | - | Reorganizacao em pacote profissional: layout src/, comando `jarvis`, modulos separados (config, ferramentas, seguranca, assistentes), testes com pytest, lint com ruff e documentacao em docs/ | - | - | - |
| 2026-11-23 | 5 | Orb animado (pywebview + Canvas) e atalho na Area de Trabalho | - | - | [UAU] |
| 2026-11-23 | 6 | Voz opcional do ElevenLabs (Gemini ouve e pensa, ElevenLabs fala), com volta automatica para a voz do Google | - | - | [VERDADE] voz propria = mais uma etapa = mais atraso |
| 2026-11-24 | 7 | Visuais escolhiveis: 7 visuais para a janela (globo, cortex, reator, holograma, mapa, esfera, aura), tela de escolha com previa animada, preferencia salva fora do projeto, painel com acoes e latencia reais | - | - | [UAU] |
| 2026-11-24 | 7 | Paineis mais ricos (sessao, linha do tempo dos estados, ranking de ferramentas, tempo em cada estado, historico da voz, latencia min/med/max) so com dados reais; nucleo da Aura virou esfera de particulas | Aura pesada (clip por quadro): linhas de contorno calculadas por largura da silhueta, de ~40 ms para ~7 ms por quadro | - | [UAU] |
