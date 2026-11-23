"""Testes da voz do ElevenLabs e do roteamento de fala (sem rede)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.assistants.elevenlabs_voice import ElevenLabsError, split_sentences
from jarvis.assistants.observer import NullObserver
from jarvis.assistants.voice_output import FALLBACK_NOTICE, VoiceOutput
from jarvis.config import Settings


class RecordingObserver(NullObserver):
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []

    def on_transcript(self, speaker: str, text: str) -> None:
        self.lines.append((speaker, text))


class FakeVoice:
    """Simula o ElevenLabs: devolve o texto em bytes ou falha a partir da frase N."""

    def __init__(self, fail_from: int | None = None) -> None:
        self.spoken: list[str] = []
        self.fail_from = fail_from
        self.closed = False

    async def stream(self, text: str):
        if self.fail_from is not None and len(self.spoken) >= self.fail_from:
            raise ElevenLabsError("HTTP 401: sem creditos")
        self.spoken.append(text)
        yield f"<{text}>".encode()

    async def close(self) -> None:
        self.closed = True


def _drain(queue: asyncio.Queue[bytes]) -> list[bytes]:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


async def _run_briefly(output: VoiceOutput) -> None:
    task = asyncio.create_task(output.run())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# ------------------------------------------------------------------ split_sentences
def test_split_sentences_separa_frases_completas() -> None:
    sentences, rest = split_sentences("Pois nao, senhor. Sao dez horas! E o cafe")
    assert sentences == ["Pois nao, senhor.", "Sao dez horas!"]
    assert rest == "E o cafe"


def test_split_sentences_espera_frase_terminar() -> None:
    assert split_sentences("Pois nao") == ([], "Pois nao")
    assert split_sentences("") == ([], "")


def test_split_sentences_corta_na_virgula_se_trecho_grande() -> None:
    longo = "Senhor, " + "a " * 40 + "e mais, isto continua"
    sentences, rest = split_sentences(longo)
    assert sentences and sentences[0].endswith(",")
    assert rest


# ------------------------------------------------------------------ config
def test_settings_elevenlabs_opcional(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=abc\nELEVENLABS_API_KEY=cole_sua_chave_aqui\n", encoding="utf-8")
    for name in ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env(env)
    assert settings.uses_elevenlabs is False  # texto de exemplo nao conta como chave


def test_settings_elevenlabs_ligado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "GEMINI_API_KEY=abc\nELEVENLABS_API_KEY=sk_123\nELEVENLABS_VOICE_ID=voz1\n",
        encoding="utf-8",
    )
    for name in ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env(env)
    assert settings.uses_elevenlabs is True
    assert settings.elevenlabs_model == "eleven_flash_v2_5"
    assert "sk_123" not in repr(settings)  # chave nunca aparece em log


# ------------------------------------------------------------------ VoiceOutput
def test_sem_elevenlabs_audio_do_gemini_vai_direto() -> None:
    async def scenario() -> list[bytes]:
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        output = VoiceOutput(queue, NullObserver())
        output.on_model_audio(b"gemini")
        output.on_model_text("Ola, senhor.")
        output.on_turn_complete()
        await _run_briefly(output)
        return _drain(queue)

    assert asyncio.run(scenario()) == [b"gemini"]


def test_com_elevenlabs_fala_as_frases_e_guarda_o_gemini() -> None:
    async def scenario():
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        voice = FakeVoice()
        output = VoiceOutput(queue, NullObserver(), voice)  # type: ignore[arg-type]
        output.on_model_audio(b"gemini")
        output.on_model_text("Pois nao, senhor. Sao ")
        output.on_model_text("dez horas")
        output.on_turn_complete()
        await _run_briefly(output)
        return _drain(queue), voice

    audio, voice = asyncio.run(scenario())
    assert voice.spoken == ["Pois nao, senhor.", "Sao dez horas"]
    assert audio == [b"<Pois nao, senhor.>", b"<Sao dez horas>"]  # audio do Gemini nao toca


def test_falha_do_elevenlabs_volta_para_voz_do_gemini() -> None:
    async def scenario():
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        observer = RecordingObserver()
        voice = FakeVoice(fail_from=0)
        output = VoiceOutput(queue, observer, voice)  # type: ignore[arg-type]
        output.on_model_audio(b"reserva")
        output.on_model_text("Pois nao, senhor. ")
        await _run_briefly(output)
        output.on_model_audio(b"depois")  # ja na voz do Gemini
        return _drain(queue), observer, voice, output

    audio, observer, voice, output = asyncio.run(scenario())
    assert audio == [b"reserva", b"depois"]
    assert ("sistema", FALLBACK_NOTICE) in observer.lines
    assert voice.closed and output.uses_elevenlabs is False


def test_interrupcao_descarta_frases_pendentes() -> None:
    async def scenario():
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        voice = FakeVoice()
        output = VoiceOutput(queue, NullObserver(), voice)  # type: ignore[arg-type]
        output.on_model_text("Frase antiga. ")
        output.on_interrupted()
        output.on_model_text("Frase nova. ")
        await _run_briefly(output)
        return _drain(queue), voice

    audio, voice = asyncio.run(scenario())
    assert voice.spoken == ["Frase nova."]
    assert audio == [b"<Frase nova.>"]


def test_primeira_fala_sai_na_primeira_virgula() -> None:
    sentences, rest = split_sentences("Sou seu mordomo digital, apto a", first_piece=True)
    assert sentences == ["Sou seu mordomo digital,"]
    assert rest.strip() == "apto a"


def test_frase_que_termina_no_fim_do_trecho_sai_sem_esperar_espaco() -> None:
    assert split_sentences("e gerenciar aplicativos.") == (["e gerenciar aplicativos."], "")


def test_primeira_fala_curta_demais_espera() -> None:
    assert split_sentences("Sim,", first_piece=True) == ([], "Sim,")
