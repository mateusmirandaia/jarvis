"""Configuracao do Jarvis lida do arquivo .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from jarvis.errors import ConfigError

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# Valores de exemplo que significam "a chave ainda nao foi colada".
_PLACEHOLDER_KEYS: frozenset[str] = frozenset(
    {
        "cole_sua_chave_aqui",
        "sua_chave_aqui",
        "sua-chave-aqui",
        "coloque_sua_chave_aqui",
        "your_api_key_here",
        "your-api-key",
        "changeme",
        "xxx",
    }
)

_MISSING_KEY_MESSAGE = (
    "Nao encontrei a GEMINI_API_KEY, senhor. Copie o .env.example para .env, "
    "cole a sua chave do Google AI Studio (https://aistudio.google.com/apikey) e rode de novo."
)

__all__ = ["PROJECT_ROOT", "ConfigError", "Settings"]


def _env(name: str, default: str) -> str:
    """Le uma variavel de ambiente, tratando vazio como ausente."""
    value = os.getenv(name, "").strip()
    return value or default


def _is_placeholder(key: str) -> bool:
    """Diz se a chave e vazia ou um texto de exemplo."""
    normalized = key.strip().strip("\"'").lower()
    return not normalized or normalized in _PLACEHOLDER_KEYS or normalized.startswith("<")


_YES: frozenset[str] = frozenset({"sim", "s", "true", "1", "yes", "y"})


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    """Le um inteiro do .env; valor invalido usa o padrao; fora da faixa e ajustado."""
    try:
        value = int(_env(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _optional_key(name: str) -> str:
    """Le uma chave opcional; texto de exemplo conta como vazio."""
    value = os.getenv(name, "").strip()
    return "" if _is_placeholder(value) else value


@dataclass(frozen=True)
class Settings:
    """Configuracoes imutaveis do Jarvis."""

    api_key: str = field(repr=False)  # nunca aparece em log/print
    text_model: str = "gemini-3.5-flash-lite"
    text_fallback_model: str = "gemini-flash-lite-latest"
    live_model: str = "gemini-3.1-flash-live-preview"
    voice: str = "Charon"
    user_name: str = ""  # opcional: "assistente pessoal do <nome>"; vazio = generico
    # Voz opcional do ElevenLabs: com chave + voz preenchidas, o Jarvis fala com ela.
    elevenlabs_api_key: str = field(default="", repr=False)
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_flash_v2_5"
    # Silencio (ms) que encerra a sua fala: menor = responde mais rapido, mas pode cortar pausas.
    silence_ms: int = 500
    # Com fone de ouvido, o microfone fica aberto enquanto ele fala: da para interromper.
    headphones: bool = False
    # Visual da janela do orb forcado pelo .env (ex.: "reator"); vazio = usa a preferencia salva.
    visual: str = ""
    tool_timeout_s: float = 20.0
    delete_timeout_s: float = 120.0
    project_root: Path = PROJECT_ROOT
    log_file: Path = PROJECT_ROOT / "logs" / "jarvis.log"

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        """Carrega as configuracoes do .env e das variaveis de ambiente.

        Args:
            env_file: caminho do .env; se None, usa o .env da raiz do projeto.

        Returns:
            Settings preenchido.

        Raises:
            ConfigError: se a GEMINI_API_KEY estiver ausente ou ainda for o texto de exemplo.
        """
        load_dotenv(env_file or PROJECT_ROOT / ".env")
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if _is_placeholder(api_key):
            raise ConfigError(_MISSING_KEY_MESSAGE)
        return cls(
            api_key=api_key,
            text_model=_env("GEMINI_MODEL", cls.text_model),
            text_fallback_model=_env("GEMINI_MODEL_RESERVA", cls.text_fallback_model),
            live_model=_env("GEMINI_LIVE_MODEL", cls.live_model),
            voice=_env("JARVIS_VOZ", cls.voice),
            user_name=_env("JARVIS_NOME_USUARIO", cls.user_name),
            elevenlabs_api_key=_optional_key("ELEVENLABS_API_KEY"),
            elevenlabs_voice_id=_env("ELEVENLABS_VOICE_ID", ""),
            elevenlabs_model=_env("ELEVENLABS_MODEL", cls.elevenlabs_model),
            silence_ms=_int_env("JARVIS_SILENCIO_MS", cls.silence_ms, minimum=200, maximum=2000),
            headphones=_env("JARVIS_FONE", "nao").lower() in _YES,
            visual=_env("JARVIS_VISUAL", "").lower().replace(" ", ""),
        )

    @property
    def uses_elevenlabs(self) -> bool:
        """True quando a chave e a voz do ElevenLabs estao configuradas."""
        return bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)
