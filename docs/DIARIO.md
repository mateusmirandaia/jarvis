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
| 2026-11-25 | 7 | Dois visuais novos de pontos que viram cerebro: Globo Cognitivo (`cerebro`, globo de 760 pontos que vira cerebro, paleta aurora) e Galaxia Neural (`galaxia`, galaxia espiral de 820 pontos que se fecha num cerebro, paleta nova `nuvem` com Transformative Teal e Cloud Dancer, as cores do ano de 2026); tela de escolha com 9 cartoes (5 + 4); a Galaxia Neural virou o visual de entrada (abre direto nela, sem tela de escolha; troca pelo botao) | - | - | [UAU] |
| 2026-11-25 | 8 | Instalador para Windows: PyInstaller (pasta onedir, sem console, com icone, orb.html, visuais e amostras) + Inno Setup 6 (sem pedir admin, em %LOCALAPPDATA%\Programs\Jarvis, atalhos na Area de Trabalho e no Menu Iniciar, desinstalador que pergunta antes de apagar as configuracoes) e `packaging/build.ps1`, que gera tudo num comando e mostra o SHA-256 para o VirusTotal; script `scripts/gerar_amostras_voz.py` gera as amostras das 8 vozes do Google com o TTS do Gemini | O `.gitignore` ignorava todo `*.wav` (as amostras sumiriam do repositorio): exceção para `src/jarvis/ui/amostras/` | - | [VERDADE] sem assinatura digital o Windows avisa "protegeu o computador": e preciso explicar o "Executar assim mesmo" |
