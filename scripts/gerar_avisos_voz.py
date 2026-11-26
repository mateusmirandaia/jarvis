"""Gera os avisos gravados do Jarvis (WAV) com o TTS do Gemini.

Roda UMA vez, antes do build do instalador. Os avisos tocam sem internet quando algo da
errado e vao junto no pacote (src/jarvis/avisos/):

- internet_<Voz>.wav, uma para cada voz do Google (8 arquivos);
- elevenlabs_Charon.wav (a voz personalizada falhou; sempre na voz Charon).

Uso (na raiz do projeto, com o ambiente ativado):

    python scripts/gerar_avisos_voz.py                 # gera so os que faltam
    python scripts/gerar_avisos_voz.py --vozes Puck,Kore
    python scripts/gerar_avisos_voz.py --forcar        # refaz todos
    python scripts/gerar_avisos_voz.py --modelo gemini-3.8-flash-lite-tts

Mesmas opcoes, mesma busca da chave e mesmo formato do gerar_amostras_voz.py (de onde vem
quase todo o codigo). A chave NUNCA e impressa.

Codigos de saida: 0 = tudo certo; 1 = algum aviso falhou; 2 = erro de configuracao
(sem chave, voz desconhecida).
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import sys
import time
import wave
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_AVISOS = RAIZ_PROJETO / "src" / "jarvis" / "avisos"


def _carregar_amostras() -> ModuleType:
    """Importa o gerar_amostras_voz.py ao lado deste arquivo (a pasta scripts nao e pacote)."""
    nome = "gerar_amostras_voz"
    if nome in sys.modules:
        return sys.modules[nome]
    caminho = Path(__file__).resolve().parent / f"{nome}.py"
    spec = importlib.util.spec_from_file_location(nome, caminho)
    if spec is None or spec.loader is None:  # pragma: no cover - arquivo sumiu
        raise ImportError(f"nao encontrei {caminho}")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    return modulo


amostras = _carregar_amostras()

VOZES: tuple[str, ...] = amostras.VOZES
VOZ_ELEVENLABS = "Charon"
MODELO_PADRAO: str = amostras.MODELO_PADRAO
PAUSA_PADRAO_S: float = amostras.PAUSA_PADRAO_S
ESPERA_COTA_S: float = amostras.ESPERA_COTA_S
TAXA_ESPERADA = 24_000

# Mesmos textos de jarvis/avisos.py (o teste confere que batem).
TEXTO_INTERNET = (
    "Desculpe, estou tendo problemas com a sua internet. Aguarde um momento ou tente daqui a pouco."
)
TEXTO_ELEVENLABS = "Minha voz personalizada está com problemas. Vou continuar com a voz padrão."
ESTILO = (
    "assistente educado, calmo e tranquilizador, falando português do Brasil com sotaque "
    "brasileiro, devagar e com clareza"
)


def lista_de_avisos(vozes: Sequence[str]) -> list[tuple[str, str, str]]:
    """[(nome do arquivo, voz, frase)] na ordem de geracao."""
    itens = [(f"internet_{voz}.wav", voz, TEXTO_INTERNET) for voz in vozes]
    if VOZ_ELEVENLABS in vozes:
        itens.append((f"elevenlabs_{VOZ_ELEVENLABS}.wav", VOZ_ELEVENLABS, TEXTO_ELEVENLABS))
    return itens


def montar_pedido(modelo: str, voz: str, frase: str) -> tuple[Any, Any]:
    """Como o ``montar_pedido`` das amostras, mas com a frase do aviso."""
    from google.genai import types

    campos_voz = getattr(types.VoiceConfig, "model_fields", {})
    campos_parte = getattr(types.Part, "model_fields", {})
    novo = (
        not amostras._modelo_legado(modelo)
        and "voice" in campos_voz
        and "speech_metadata" in campos_parte
    )
    if novo:
        voice_config = types.VoiceConfig(voice=voz)
        parte = types.Part(text=frase, speech_metadata=types.SpeechMetadata(style=ESTILO))
    else:
        voice_config = types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)
        )
        parte = types.Part(text=f"Fale como um {ESTILO}: {frase}")
    contents = [types.Content(role="user", parts=[parte])]
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=voice_config),
    )
    return contents, config


def gerar_audio(cliente: Any, modelo: str, voz: str, frase: str) -> tuple[bytes, str | None]:
    """Pede a frase ao Gemini e devolve (bytes do audio, mime)."""
    contents, config = montar_pedido(modelo, voz, frase)
    try:
        resposta = cliente.models.generate_content(model=modelo, contents=contents, config=config)
    except Exception as exc:
        if amostras._e_erro_de_cota(exc):
            raise amostras.ErroCota(str(exc)) from exc
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


def conferir_formato(arquivo: Path) -> None:
    """O Jarvis so toca aviso PCM 16-bit 24 kHz mono: outro formato vira erro aqui."""
    with wave.open(str(arquivo), "rb") as w:
        formato = (w.getnchannels(), w.getsampwidth(), w.getframerate())
    if formato != (1, 2, TAXA_ESPERADA):
        raise ValueError(
            f"formato {formato} (canais, bytes, taxa); o Jarvis precisa de (1, 2, 24000)"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gerar_avisos_voz",
        description="Gera os avisos gravados (internet e ElevenLabs) do Jarvis.",
    )
    parser.add_argument(
        "--vozes",
        help=f"vozes separadas por virgula (padrao: todas — {', '.join(VOZES)}). "
        f"O aviso do ElevenLabs sai junto quando {VOZ_ELEVENLABS} esta na lista.",
    )
    parser.add_argument(
        "--forcar", action="store_true", help="refaz os avisos que ja existem (sobrescreve)."
    )
    parser.add_argument(
        "--modelo", default=MODELO_PADRAO, help=f"modelo de TTS do Gemini (padrao: {MODELO_PADRAO})"
    )
    parser.add_argument(
        "--saida", type=Path, default=PASTA_AVISOS, help="pasta dos avisos (padrao: a do app)."
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=PAUSA_PADRAO_S,
        help=f"segundos de espera entre os pedidos (padrao: {PAUSA_PADRAO_S:g}).",
    )
    return parser


def main(argv: Sequence[str] | None = None, cliente: Any = None) -> int:
    """Gera os avisos. `cliente` permite injetar um cliente falso nos testes."""
    args = _parser().parse_args(argv)
    try:
        vozes = amostras._parse_vozes(args.vozes)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    saida: Path = args.saida
    itens = lista_de_avisos(vozes)
    pendentes = [item for item in itens if args.forcar or not (saida / item[0]).exists()]
    for item in itens:
        if item not in pendentes:
            print(f"[pula] {item[0]} ja existe (use --forcar para refazer)")
    if not pendentes:
        print("Nada a fazer: todos os avisos pedidos ja existem.")
        return 0

    chave = ""
    if cliente is None:
        chave, origem = amostras.carregar_chave(RAIZ_PROJETO)
        if not chave:
            print(
                "Erro: nao encontrei a GEMINI_API_KEY. Defina a variavel de ambiente, ponha no "
                ".env do projeto ou configure o Jarvis pela janela e rode de novo.",
                file=sys.stderr,
            )
            return 2
        print(f"Usando a chave da {origem} e o modelo {args.modelo}.")
        cliente = amostras._criar_cliente(chave)

    falhas: list[str] = []
    for indice, (nome, voz, frase) in enumerate(pendentes):
        if indice and args.pausa > 0:
            time.sleep(args.pausa)
        destino = saida / nome
        try:
            try:
                dados, mime = gerar_audio(cliente, args.modelo, voz, frase)
            except amostras.ErroCota:
                print(
                    f"[cota] limite de pedidos da conta atingido; esperando {ESPERA_COTA_S:g} s "
                    "para tentar de novo..."
                )
                time.sleep(ESPERA_COTA_S)
                dados, mime = gerar_audio(cliente, args.modelo, voz, frase)
            amostras.gravar_wav(destino, dados, mime)
            try:
                conferir_formato(destino)
            except Exception:
                destino.unlink(missing_ok=True)  # arquivo no formato errado nao fica na pasta
                raise
        except amostras.ErroCota:
            restantes = [item[0] for item in pendentes[indice:]]
            print(
                "Erro: a conta gratis do Google atingiu o limite de pedidos de voz (cota). "
                "Espere alguns minutos (ou ate amanha, se for o limite diario) e rode de novo: "
                "os avisos prontos serao pulados. Faltaram: " + ", ".join(restantes),
                file=sys.stderr,
            )
            falhas.extend(restantes)
            break
        except Exception as exc:  # noqa: BLE001 - um aviso com erro nao derruba os outros
            mensagem = amostras._sem_segredo(f"{type(exc).__name__}: {exc}", chave)
            print(f"[erro] {nome}: {mensagem}", file=sys.stderr)
            falhas.append(nome)
            continue
        print(f"[ok] {destino}")

    if falhas:
        print(f"Falharam: {', '.join(falhas)}", file=sys.stderr)
        return 1
    print("Pronto: avisos gerados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
