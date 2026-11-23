"""Assistentes do Jarvis: voz em tempo real (Gemini Live) e texto (terminal)."""

from __future__ import annotations

from jarvis.assistants.live_assistant import LiveAssistant
from jarvis.assistants.observer import AssistantObserver, NullObserver
from jarvis.assistants.text_assistant import TextAssistant

__all__ = ["AssistantObserver", "LiveAssistant", "NullObserver", "TextAssistant"]
