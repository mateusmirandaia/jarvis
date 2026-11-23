"""Ferramentas de sistema: data e hora."""

from __future__ import annotations

from datetime import datetime

WEEKDAYS: tuple[str, ...] = (
    "segunda-feira",
    "terca-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sabado",
    "domingo",
)


class SystemTools:
    """Informacoes do proprio computador."""

    TOOL_NAMES: tuple[str, ...] = ("current_time",)

    def current_time(self) -> str:
        """Informa a data, o dia da semana e a hora atuais do computador."""
        now = datetime.now()
        return f"{WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y}, {now:%H:%M}"
