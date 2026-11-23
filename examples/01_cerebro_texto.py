"""Exemplo 01 - O "cerebro" do Jarvis: chat por texto no terminal, com personalidade.

E a primeira camada do projeto, sem voz e sem acoes: so a IA conversando.
Bom para entender o basico antes de ir para o pacote completo.

Como rodar (com o .env ja configurado na raiz do projeto):
    python examples/01_cerebro_texto.py

Digite "sair" para encerrar.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

# 1) Le o arquivo .env da raiz do projeto (a pasta acima de examples/).
RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")

CHAVE = os.getenv("GEMINI_API_KEY", "")
MODELO = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not CHAVE or CHAVE == "cole_sua_chave_aqui":
    sys.exit("Falta a chave: copie .env.example para .env e cole a sua GEMINI_API_KEY.")

# 2) A personalidade: e so um texto que a IA recebe antes de qualquer conversa.
PERSONALIDADE = """Voce e o Jarvis, assistente pessoal do senhor.
Fala portugues do Brasil, com educacao de mordomo britanico e uma ironia leve.
Chama o usuario de "senhor". Respostas curtas: no maximo 2 frases,
porque elas vao virar voz."""

# 3) O cliente conversa com o Google. O "chat" guarda o historico da conversa.
client = genai.Client(api_key=CHAVE)
chat = client.chats.create(
    model=MODELO,
    config=types.GenerateContentConfig(system_instruction=PERSONALIDADE),
)

print(f"Jarvis pronto (modelo {MODELO}). Digite 'sair' para encerrar.")

# 4) O loop: voce escreve, a IA responde, para sempre (ate digitar "sair").
while True:
    try:
        fala = input("Voce: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not fala:
        continue
    if fala.lower() in ("sair", "exit"):
        break
    try:
        resposta = chat.send_message(fala)
        print("Jarvis:", resposta.text)
    except Exception as erro:  # internet caiu, cota acabou, modelo sobrecarregado...
        print("Jarvis: Perdao, senhor, nao consegui pensar agora. Tente de novo.")
        print(f"   (detalhe tecnico: {type(erro).__name__})")

print("Jarvis: Ate logo, senhor.")
