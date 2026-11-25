"""Jarvis por texto no terminal: Gemini + ferramentas da lista fechada."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from google import genai
from google.genai import errors, types

from jarvis.persona import build_system_prompt

if TYPE_CHECKING:
    from google.genai.chats import Chat

    from jarvis.config import Settings
    from jarvis.tools import ToolRegistry

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
SWITCH_MODEL_AT = 1  # na 2a falha troca para o modelo reserva
BUSY_MESSAGE = "O servidor do Google esta ocupado, senhor. Tente de novo em instantes."
KEY_MESSAGE = "senhor, estou com um problema com a chave ou a cota do Google."
GENERIC_MESSAGE = "senhor, estou com um problema agora. Pode repetir?"
EXIT_WORDS = ("sair", "exit")


class TextAssistant:
    """Chat por texto com chamada automatica de ferramentas e modelo reserva."""

    def __init__(self, settings: Settings, registry: ToolRegistry) -> None:
        self.settings = settings
        self.registry = registry
        # Modelo principal e reserva (usada quando o principal esta lotado, erro 5xx).
        self.models = [settings.text_model, settings.text_fallback_model]
        self.client = genai.Client(
            api_key=settings.api_key,
            http_options=types.HttpOptions(
                timeout=12_000,  # 12 s por tentativa (o Google exige no minimo 10 s)
                retry_options=types.HttpRetryOptions(attempts=1),  # sem retry escondido
            ),
        )
        self.config = types.GenerateContentConfig(
            system_instruction=build_system_prompt(
                registry.guard.user_folders(), registry.app_names, settings.user_name
            ),
            tools=list(registry.functions),  # a SDK chama a funcao e devolve a resposta final
        )
        self.model_index = 0
        self.chat: Chat = self._new_chat()

    @property
    def current_model(self) -> str:
        return self.models[self.model_index]

    def _new_chat(self, history: list[types.Content] | None = None) -> Chat:
        return self.client.chats.create(
            # list(...) copia o historico e deixa o tipo como a SDK espera (lista invariante).
            model=self.current_model,
            config=self.config,
            history=list(history or []),
        )

    def _switch_model(self) -> None:
        """Troca para o proximo modelo preservando o historico da conversa."""
        if len(self.models) < 2:
            return
        history = self.chat.get_history()
        self.model_index = (self.model_index + 1) % len(self.models)
        self.chat = self._new_chat(history)
        logger.warning("servidor lotado, trocando para %s", self.current_model)
        print(f"(servidor lotado, trocando para {self.current_model})")

    def _send(self, text: str) -> str:
        """Envia com backoff em erro 5xx e troca de modelo; pode levantar ClientError."""
        for attempt in range(MAX_ATTEMPTS):
            try:
                return self.chat.send_message(text).text or "Feito, senhor."
            except errors.ServerError as error:  # 503 e parecidos: servidor ocupado
                logger.warning("ServerError em %s: %s", self.current_model, error)
                time.sleep(2 + attempt * 2)
                if attempt == SWITCH_MODEL_AT:
                    self._switch_model()
        return BUSY_MESSAGE

    def ask(self, text: str) -> str:
        """Manda a fala ao Gemini e devolve a resposta. Nunca levanta excecao."""
        try:
            return self._send(text)
        except errors.ClientError as error:  # chave errada, cota estourada etc.
            logger.error("ClientError %s", error)
            return KEY_MESSAGE
        except Exception:  # noqa: BLE001 - avisa e continua, nunca trava
            logger.exception("falha no assistente de texto")
            return GENERIC_MESSAGE

    def run(self) -> None:
        """REPL no terminal: 'Voce:' / 'Jarvis:'; linha vazia e ignorada; 'sair' encerra."""
        print(f"Jarvis pronto ({self.current_model}). Digite 'sair' para encerrar.")
        while True:
            try:
                text = input("Voce: ").strip()
            except EOFError:  # Ctrl+Z/Ctrl+D ou entrada fechada: encerra sem traceback
                break
            if not text:  # mandar vazio da erro 400
                continue
            if text.lower() in EXIT_WORDS:
                break
            print("Jarvis:", self.ask(text))
