"""Configuracao do Jarvis: variaveis de ambiente, .env do projeto, .env do usuario e preferencias.

Ordem de prioridade (a primeira fonte que tiver o valor ganha):

1. variaveis de ambiente do processo;
2. ``.env`` da pasta do projeto (modo desenvolvedor; nao existe no Jarvis instalado);
3. ``.env`` da pasta do usuario (``%APPDATA%\\Jarvis\\.env``), onde a janela de configuracao
   salva as chaves.

Para voz, nome e fone de ouvido, se nenhuma das fontes acima definir o valor, vale o que foi
escolhido na janela (``preferencias.json``) e, por fim, o padrao.

Quando o Jarvis roda congelado (instalador feito com PyInstaller, ``sys.frozen``), nao existe
pasta do projeto: o ``.env`` do projeto simplesmente nao e procurado e os logs vao para
``%APPDATA%\\Jarvis\\logs``.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from jarvis.errors import ConfigError

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
    "Nao encontrei a GEMINI_API_KEY, senhor. Abra o Jarvis pela janela (comando jarvis, sem "
    "--modo) para configurar a chave, ou copie o .env.example para .env e cole a sua chave do "
    "Google AI Studio (https://aistudio.google.com/apikey)."
)

LOG_NOME = "jarvis.log"

__all__ = [
    "PROJECT_ROOT",
    "ConfigError",
    "Settings",
    "congelado",
    "pasta_logs",
    "pasta_pacote",
    "raiz_projeto",
]


# ------------------------------------------------------------------ modo congelado
def congelado() -> bool:
    """True quando o Jarvis roda pelo instalador (PyInstaller define ``sys.frozen``)."""
    return bool(getattr(sys, "frozen", False))


def pasta_pacote() -> Path:
    """Pasta do pacote ``jarvis`` (onde ficam ``ui/orb.html``, ``ui/visuais``, ``ui/amostras``).

    Congelado, os arquivos de dados ficam em ``sys._MEIPASS/jarvis``; em desenvolvimento, na
    pasta deste arquivo.
    """
    if congelado():
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base) / "jarvis"
        return Path(sys.executable).resolve().parent / "jarvis"
    return Path(__file__).resolve().parent


def raiz_projeto() -> Path:
    """Pasta do projeto (desenvolvimento) ou a pasta do programa instalado (congelado)."""
    if congelado():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def pasta_usuario() -> Path:
    """Pasta de dados do usuario (a mesma do ``preferencias.json``)."""
    from jarvis.ui import preferencias

    return preferencias.caminho_preferencias().parent


def pasta_logs() -> Path:
    """Pasta dos logs: ``%APPDATA%\\Jarvis\\logs`` congelado; ``logs`` do projeto em dev."""
    if congelado():
        return pasta_usuario() / "logs"
    return raiz_projeto() / "logs"


def _log_padrao() -> Path:
    return pasta_logs() / LOG_NOME


PROJECT_ROOT: Path = raiz_projeto()


# ------------------------------------------------------------------------ leitura
def _is_placeholder(key: str) -> bool:
    """Diz se a chave e vazia ou um texto de exemplo."""
    normalized = key.strip().strip("\"'").lower()
    return not normalized or normalized in _PLACEHOLDER_KEYS or normalized.startswith("<")


_YES: frozenset[str] = frozenset({"sim", "s", "true", "1", "yes", "y"})

# Chaves secretas: texto de exemplo conta como "nao definido" (passa para a proxima fonte).
_SEGREDOS: frozenset[str] = frozenset(
    {"GEMINI_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"}
)


def _ler_dotenv(caminho: Path | None) -> dict[str, str]:
    """Le um arquivo .env sem mexer em ``os.environ``; arquivo ausente/ilegivel = vazio."""
    if caminho is None:
        return {}
    try:
        if not caminho.is_file():
            return {}
        valores = dotenv_values(caminho, encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return {chave: valor for chave, valor in valores.items() if isinstance(valor, str)}


class _Fontes:
    """Procura cada variavel nas fontes, na ordem de prioridade, tratando vazio como ausente."""

    def __init__(self, camadas: list[tuple[str, Mapping[str, str]]]) -> None:
        self._camadas = camadas

    def valor(self, nome: str, padrao: str = "") -> str:
        return self.origem(nome)[0] or padrao

    def origem(self, nome: str) -> tuple[str, str]:
        """Devolve (valor, nome da fonte) ou ("", "") se nenhuma fonte define."""
        for fonte, camada in self._camadas:
            bruto = camada.get(nome)
            if not isinstance(bruto, str):
                continue
            valor = bruto.strip()
            if not valor:
                continue
            if nome in _SEGREDOS and _is_placeholder(valor):
                continue
            return valor, fonte
        return "", ""

    def inteiro(self, nome: str, padrao: int, minimo: int, maximo: int) -> int:
        """Le um inteiro; valor invalido usa o padrao; fora da faixa e ajustado."""
        try:
            valor = int(self.valor(nome, str(padrao)))
        except ValueError:
            return padrao
        return max(minimo, min(maximo, valor))


def _fontes(env_file: Path | None, env_usuario: Path | None) -> _Fontes:
    if env_file is not None:
        projeto = _ler_dotenv(env_file)
    elif congelado():
        projeto = {}  # instalado: nao existe .env de projeto
    else:
        projeto = _ler_dotenv(raiz_projeto() / ".env")
    if env_usuario is None:
        from jarvis import armazenamento

        env_usuario = armazenamento.caminho_env_usuario()
    usuario = _ler_dotenv(env_usuario)
    return _Fontes([("ambiente", dict(os.environ)), ("projeto", projeto), ("usuario", usuario)])


@dataclass(frozen=True)
class Settings:
    """Configuracoes imutaveis do Jarvis."""

    api_key: str = field(repr=False)  # nunca aparece em log/print; "" = ainda nao configurada
    text_model: str = "gemini-3.5-flash-lite"
    text_fallback_model: str = "gemini-flash-lite-latest"
    live_model: str = "gemini-3.1-flash-live-preview"
    voice: str = "Charon"
    user_name: str = ""  # opcional: "assistente pessoal do <nome>"; vazio = generico
    # Voz opcional do ElevenLabs: com chave + voz preenchidas, o Jarvis fala com ela.
    elevenlabs_api_key: str = field(default="", repr=False)
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_flash_v2_5"
    elevenlabs_pausado: bool = False  # a pessoa escolheu "voz do Google" na engrenagem
    # Silencio (ms) que encerra a sua fala: menor = responde mais rapido, mas pode cortar pausas.
    silence_ms: int = 500
    # Com fone de ouvido, o microfone fica aberto enquanto ele fala: da para interromper.
    headphones: bool = False
    # Visual da janela do orb forcado pelo .env (ex.: "reator"); vazio = usa a preferencia salva.
    visual: str = ""
    tool_timeout_s: float = 20.0
    delete_timeout_s: float = 120.0
    project_root: Path = field(default_factory=raiz_projeto)
    log_file: Path = field(default_factory=_log_padrao)
    # De onde veio a GEMINI_API_KEY: "ambiente", "projeto", "usuario" ou "" (sem chave).
    api_key_source: str = ""

    @classmethod
    def from_env(
        cls,
        env_file: Path | None = None,
        *,
        exigir_chave: bool = True,
        env_usuario: Path | None = None,
        preferencias_arquivo: Path | None = None,
    ) -> Settings:
        """Carrega as configuracoes de todas as fontes (veja a docstring do modulo).

        Nao altera ``os.environ``: carregar de novo depois de salvar uma chave nova pega a
        chave nova.

        Args:
            env_file: .env do projeto; None usa o ``.env`` da raiz do projeto (nenhum, se
                congelado).
            exigir_chave: True (modos voz/texto) levanta ConfigError sem chave; False (modo
                orb) devolve ``api_key=""`` para a janela abrir e pedir a chave.
            env_usuario: .env do usuario; None usa ``%APPDATA%\\Jarvis\\.env``.
            preferencias_arquivo: preferencias.json; None usa o caminho padrao.

        Returns:
            Settings preenchido.

        Raises:
            ConfigError: sem GEMINI_API_KEY (ou texto de exemplo) e ``exigir_chave`` True.
        """
        from jarvis import vozes
        from jarvis.ui import preferencias

        fontes = _fontes(env_file, env_usuario)
        prefs = preferencias.carregar(preferencias_arquivo)
        api_key, origem = fontes.origem("GEMINI_API_KEY")
        if not api_key and exigir_chave:
            raise ConfigError(_MISSING_KEY_MESSAGE)

        voz = fontes.valor("JARVIS_VOZ")
        if not voz:
            salva = prefs.get(preferencias.CHAVE_VOZ)
            voz = salva if vozes.voz_valida(salva) else cls.voice
        nome = fontes.valor("JARVIS_NOME_USUARIO")
        if not nome:
            salvo = prefs.get(preferencias.CHAVE_NOME)
            nome = (
                salvo.strip() if isinstance(salvo, str) and preferencias.nome_valido(salvo) else ""
            )
        fone_env = fontes.valor("JARVIS_FONE")
        if fone_env:
            fone = fone_env.lower() in _YES
        else:
            fone = prefs.get(preferencias.CHAVE_FONE) is True

        return cls(
            api_key=api_key,
            text_model=fontes.valor("GEMINI_MODEL", cls.text_model),
            text_fallback_model=fontes.valor("GEMINI_MODEL_RESERVA", cls.text_fallback_model),
            live_model=fontes.valor("GEMINI_LIVE_MODEL", cls.live_model),
            voice=voz,
            user_name=nome,
            elevenlabs_api_key=fontes.valor("ELEVENLABS_API_KEY"),
            elevenlabs_voice_id=fontes.valor("ELEVENLABS_VOICE_ID"),
            elevenlabs_model=fontes.valor("ELEVENLABS_MODEL", cls.elevenlabs_model),
            silence_ms=fontes.inteiro("JARVIS_SILENCIO_MS", cls.silence_ms, 200, 2000),
            headphones=fone,
            elevenlabs_pausado=prefs.get(preferencias.CHAVE_FONTE_VOZ) == "google",
            visual=fontes.valor("JARVIS_VISUAL").lower().replace(" ", ""),
            api_key_source=origem,
        )

    @property
    def has_api_key(self) -> bool:
        """True quando existe uma GEMINI_API_KEY (de qualquer fonte)."""
        return bool(self.api_key)

    @property
    def elevenlabs_configurado(self) -> bool:
        """True quando a chave e a voz do ElevenLabs existem (ligadas ou nao)."""
        return bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)

    @property
    def uses_elevenlabs(self) -> bool:
        """True quando o ElevenLabs esta configurado e a pessoa nao escolheu a voz do Google."""
        return self.elevenlabs_configurado and not self.elevenlabs_pausado
