"""Gera as amostras de voz do Jarvis (um WAV por voz do Google) com o TTS do Gemini.

Roda UMA vez, antes do build do instalador. As amostras tocam no botao "Ouvir" da
configuracao e vao junto no pacote (src/jarvis/ui/amostras/<Voz>.wav).

Uso (na raiz do projeto, com o ambiente ativado):

    python scripts/gerar_amostras_voz.py                 # gera so as que faltam
    python scripts/gerar_amostras_voz.py --vozes Puck,Kore
    python scripts/gerar_amostras_voz.py --forcar        # refaz todas
    python scripts/gerar_amostras_voz.py --modelo gemini-3.8-flash-lite-tts

A chave vem, nesta ordem: variavel de ambiente GEMINI_API_KEY > .env da raiz do projeto >
%APPDATA%\\Jarvis\\.env (outros sistemas: ~/.config/jarvis/.env). A chave NUNCA e impressa.

Codigos de saida: 0 = tudo certo; 1 = alguma voz falhou; 2 = erro de configuracao
(sem chave, voz desconhecida).
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import re
import sys
import time
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Any

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_AMOSTRAS = RAIZ_PROJETO / "src" / "jarvis" / "ui" / "amostras"

# Mesma lista do contrato (jarvis/vozes.py). Ordem = ordem dos cartoes na tela.
VOZES: tuple[str, ...] = ("Charon", "Puck", "Kore", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr")

FRASE = "Olá, senhor. Eu sou o Jarvis, seu assistente pessoal."
ESTILO = (
    "mordomo britânico educado, calmo e cordial, falando português do Brasil com sotaque brasileiro"
)

# Modelo de TTS atual do Gemini (docs: ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts).
MODELO_PADRAO = "gemini-3.8-flash-tts"
PAUSA_PADRAO_S = 20.0  # a conta gratis aceita poucos pedidos de TTS por minuto
ESPERA_COTA_S = 60.0  # ao bater na cota, espera isso e tenta mais uma vez

TAXA_PADRAO = 24_000  # PCM 16-bit, 24 kHz, mono
LARGURA_AMOSTRA = 2
CANAIS = 1

_PLACEHOLDERS = frozenset(
    {"cole_sua_chave_aqui", "sua_chave_aqui", "your_api_key_here", "changeme", "xxx"}
)


class ErroCota(Exception):
    """A conta do Google atingiu o limite de pedidos (HTTP 429 / RESOURCE_EXHAUSTED)."""


# ---------------------------------------------------------------- chave


def pasta_usuario() -> Path:
    """Pasta de configuracao do usuario (a mesma do preferencias.json)."""
    appdata = os.environ.get("APPDATA")
    if os.name == "nt" and appdata:
        return Path(appdata) / "Jarvis"
    return Path.home() / ".config" / "jarvis"


def _chave_valida(valor: str | None) -> str:
    """Devolve a chave limpa, ou "" se for vazia ou texto de exemplo."""
    chave = (valor or "").strip().strip("\"'")
    if not chave or chave.lower() in _PLACEHOLDERS or chave.startswith("<"):
        return ""
    return chave


def _ler_env(arquivo: Path) -> str:
    """Le GEMINI_API_KEY de um arquivo .env sem mexer nas variaveis do processo."""
    if not arquivo.is_file():
        return ""
    from dotenv import dotenv_values

    return _chave_valida(dotenv_values(arquivo).get("GEMINI_API_KEY"))


def carregar_chave(raiz: Path = RAIZ_PROJETO) -> tuple[str, str]:
    """Procura a chave nas tres fontes do contrato.

    Returns:
        (chave, origem): origem e uma descricao curta, sem a chave; ("", "") se nao achou.
    """
    chave = _chave_valida(os.environ.get("GEMINI_API_KEY"))
    if chave:
        return chave, "variavel de ambiente"
    chave = _ler_env(raiz / ".env")
    if chave:
        return chave, ".env do projeto"
    chave = _ler_env(pasta_usuario() / ".env")
    if chave:
        return chave, "pasta de configuracao do usuario"
    return "", ""


def _sem_segredo(texto: str, chave: str) -> str:
    """Remove a chave de qualquer texto antes de mostrar (mensagens de erro do SDK etc.)."""
    if chave:
        texto = texto.replace(chave, "***")
    return re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "***", texto)


# ---------------------------------------------------------------- audio


def _taxa_do_mime(mime: str | None) -> int:
    """Extrai a taxa de amostragem de um mime como 'audio/L16;codec=pcm;rate=24000'."""
    achado = re.search(r"rate=(\d+)", mime or "")
    return int(achado.group(1)) if achado else TAXA_PADRAO


def gravar_wav(destino: Path, dados: bytes, mime: str | None = None) -> None:
    """Grava o audio do Gemini como WAV valido, de forma atomica.

    Os modelos novos devolvem um WAV completo (cabecalho RIFF); os preview antigos devolvem PCM
    cru 16-bit 24 kHz mono. Os dois casos viram um WAV escrito pelo modulo wave.
    """
    if dados[:4] == b"RIFF":
        with wave.open(io.BytesIO(dados), "rb") as origem:
            canais = origem.getnchannels()
            largura = origem.getsampwidth()
            taxa = origem.getframerate()
            quadros = origem.readframes(origem.getnframes())
    else:
        canais, largura, taxa, quadros = CANAIS, LARGURA_AMOSTRA, _taxa_do_mime(mime), dados
    if not quadros:
        raise ValueError("o Google devolveu um audio vazio")

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".wav.tmp")
    with wave.open(str(temporario), "wb") as saida:
        saida.setnchannels(canais)
        saida.setsampwidth(largura)
        saida.setframerate(taxa)
        saida.writeframes(quadros)
    os.replace(temporario, destino)


# ---------------------------------------------------------------- Gemini


def _modelo_legado(modelo: str) -> bool:
    """Modelos preview antigos: estilo vai no texto e a voz em prebuilt_voice_config."""
    return "preview" in modelo or modelo.startswith("gemini-2")


def montar_pedido(modelo: str, voz: str) -> tuple[Any, Any]:
    """Monta (contents, config) para o generate_content de TTS."""
    from google.genai import types

    campos_voz = getattr(types.VoiceConfig, "model_fields", {})
    campos_parte = getattr(types.Part, "model_fields", {})
    novo = (
        not _modelo_legado(modelo) and "voice" in campos_voz and "speech_metadata" in campos_parte
    )

    if novo:
        # Gemini 3.8 TTS: o texto e lido ao pe da letra; o tom vai em speech_metadata.style.
        voice_config = types.VoiceConfig(voice=voz)
        parte = types.Part(text=FRASE, speech_metadata=types.SpeechMetadata(style=ESTILO))
    else:
        voice_config = types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
        )
        parte = types.Part(text=f"Fale como um {ESTILO}: {FRASE}")

    contents = [types.Content(role="user", parts=[parte])]
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=voice_config),
    )
    return contents, config


def _e_erro_de_cota(exc: BaseException) -> bool:
    codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return codigo == 429 or "RESOURCE_EXHAUSTED" in str(exc)


def gerar_audio(cliente: Any, modelo: str, voz: str) -> tuple[bytes, str | None]:
    """Pede a frase ao Gemini e devolve (bytes do audio, mime)."""
    contents, config = montar_pedido(modelo, voz)
    try:
        resposta = cliente.models.generate_content(model=modelo, contents=contents, config=config)
    except Exception as exc:
        if _e_erro_de_cota(exc):
            raise ErroCota(str(exc)) from exc
        raise
    try:
        inline = resposta.candidates[0].content.parts[0].inline_data
    except (AttributeError, IndexError, TypeError) as exc:
        raise ValueError("a resposta do Google veio sem audio") from exc
    dados = inline.data
    if isinstance(dados, str):
        dados = base64.b64decode(dados)
    if not dados:
        raise ValueError("a resposta do Google veio sem audio")
    return dados, getattr(inline, "mime_type", None)


def _criar_cliente(chave: str) -> Any:
    from google import genai

    return genai.Client(api_key=chave)


# ---------------------------------------------------------------- CLI


def _parse_vozes(texto: str | None) -> list[str]:
    """Converte 'puck, Kore' em ['Puck', 'Kore'] (ordem da lista oficial). Levanta ValueError."""
    if not texto:
        return list(VOZES)
    por_nome = {v.lower(): v for v in VOZES}
    pedidas = [p.strip().lower() for p in texto.split(",") if p.strip()]
    desconhecidas = [p for p in pedidas if p not in por_nome]
    if desconhecidas:
        raise ValueError(
            f"voz desconhecida: {', '.join(desconhecidas)}. Opcoes: {', '.join(VOZES)}"
        )
    escolhidas = {por_nome[p] for p in pedidas}
    return [v for v in VOZES if v in escolhidas]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gerar_amostras_voz",
        description="Gera as amostras WAV das vozes do Google para o botao 'Ouvir' do Jarvis.",
    )
    parser.add_argument(
        "--vozes", help=f"vozes separadas por virgula (padrao: todas — {', '.join(VOZES)})"
    )
    parser.add_argument(
        "--forcar", action="store_true", help="refaz as amostras que ja existem (sobrescreve)."
    )
    parser.add_argument(
        "--modelo", default=MODELO_PADRAO, help=f"modelo de TTS do Gemini (padrao: {MODELO_PADRAO})"
    )
    parser.add_argument(
        "--saida", type=Path, default=PASTA_AMOSTRAS, help="pasta das amostras (padrao: a do app)."
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=PAUSA_PADRAO_S,
        help=f"segundos de espera entre as vozes (padrao: {PAUSA_PADRAO_S:g}).",
    )
    return parser


def main(argv: Sequence[str] | None = None, cliente: Any = None) -> int:
    """Gera as amostras. `cliente` permite injetar um cliente falso nos testes."""
    args = _parser().parse_args(argv)
    try:
        vozes = _parse_vozes(args.vozes)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    saida: Path = args.saida
    pendentes = [v for v in vozes if args.forcar or not (saida / f"{v}.wav").exists()]
    for voz in vozes:
        if voz not in pendentes:
            print(f"[pula] {voz}.wav ja existe (use --forcar para refazer)")
    if not pendentes:
        print("Nada a fazer: todas as amostras pedidas ja existem.")
        return 0

    chave = ""
    if cliente is None:
        chave, origem = carregar_chave()
        if not chave:
            print(
                "Erro: nao encontrei a GEMINI_API_KEY. Defina a variavel de ambiente, ponha no "
                ".env do projeto ou configure o Jarvis pela janela e rode de novo.",
                file=sys.stderr,
            )
            return 2
        print(f"Usando a chave da {origem} e o modelo {args.modelo}.")
        cliente = _criar_cliente(chave)

    falhas: list[str] = []
    for indice, voz in enumerate(pendentes):
        if indice and args.pausa > 0:
            time.sleep(args.pausa)
        destino = saida / f"{voz}.wav"
        try:
            try:
                dados, mime = gerar_audio(cliente, args.modelo, voz)
            except ErroCota:
                print(
                    f"[cota] limite de pedidos da conta atingido; esperando {ESPERA_COTA_S:g} s "
                    "para tentar de novo..."
                )
                time.sleep(ESPERA_COTA_S)
                dados, mime = gerar_audio(cliente, args.modelo, voz)
            gravar_wav(destino, dados, mime)
        except ErroCota:
            restantes = pendentes[indice:]
            print(
                "Erro: a conta gratis do Google atingiu o limite de pedidos de voz (cota). "
                "Espere alguns minutos (ou ate amanha, se for o limite diario) e rode de novo: "
                "as amostras prontas serao puladas. Faltaram: " + ", ".join(restantes),
                file=sys.stderr,
            )
            falhas.extend(restantes)
            break
        except Exception as exc:  # noqa: BLE001 - uma voz com erro nao derruba as outras
            mensagem = _sem_segredo(f"{type(exc).__name__}: {exc}", chave)
            print(f"[erro] {voz}: {mensagem}", file=sys.stderr)
            falhas.append(voz)
            continue
        print(f"[ok] {destino}")

    if falhas:
        print(f"Falharam: {', '.join(falhas)}", file=sys.stderr)
        return 1
    print("Pronto: amostras geradas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
