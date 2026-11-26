"""Ferramentas de escritorio: preparar e-mails (sem NUNCA enviar).

Regras de seguranca:

1. O Jarvis so PREPARA o e-mail e abre na tela; quem revisa e clica em Enviar e o senhor.
   Nada aqui usa SMTP, Outlook por automacao (COM/pywin32) ou qualquer API de envio.
2. E-mail curto vai por ``mailto:`` (abre o programa de e-mail padrao). E-mail longo vira um
   arquivo .eml com ``X-Unsent: 1`` (o Outlook classico abre como rascunho editavel) em
   Documentos\\Jarvis\\Rascunhos\\, nunca por cima de outro arquivo.
3. Destinatarios sao validados (lista separada por virgula ou ponto e virgula; vazio = o
   senhor preenche). Quebra de linha no destinatario ou no assunto e recusada: seria um
   jeito de enfiar cabecalhos escondidos (Cc, Bcc...) no e-mail.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from datetime import datetime
from email.message import EmailMessage
from email.policy import default as politica_padrao
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote

from jarvis.os_integration import windows
from jarvis.tools.security import PathGuard

logger = logging.getLogger(__name__)

MAILTO_MAX_CHARS = 1800  # o Windows e alguns programas cortam links maiores que ~2000
EMAIL_MAX_RECIPIENTS = 20
EMAIL_MAX_SUBJECT = 250
EMAIL_MAX_BODY = 100_000
DRAFT_MAX_COPIES = 100
DRAFTS_FOLDER = ("Jarvis", "Rascunhos")

MSG_PRONTO = "Deixei o e-mail pronto para o senhor revisar e enviar."
MSG_RASCUNHO = MSG_PRONTO + " O rascunho ficou em {alvo}."
MSG_RASCUNHO_SEM_ABRIR = (
    "Salvei o rascunho do e-mail em {alvo}, mas não achei um programa de e-mail para abrir. "
    "Abra o arquivo pelo Explorer."
)
MSG_SO_WINDOWS = "Esta ação só funciona no Windows."
MSG_QUEBRA = "Senhor, o destinatário e o assunto não podem ter quebra de linha."
MSG_ENDERECO = (
    "Esse e-mail não parece válido: {endereco}. Diga o endereço completo, como nome@empresa.com."  # noqa: E501
)
MSG_MUITOS = "Senhor, são destinatários demais (mais de 20). Diga menos endereços."
MSG_ASSUNTO_GRANDE = "Senhor, o assunto está comprido demais. Diga um assunto mais curto."
MSG_CORPO_GRANDE = "Senhor, o texto do e-mail é grande demais (mais de 100 mil letras)."
MSG_VAZIO = "Senhor, diga o assunto ou o texto do e-mail."
MSG_PROTEGIDO = "Senhor, não consigo salvar o rascunho na pasta Documentos."
MSG_NOMES = "Senhor, há rascunhos demais com o mesmo horário. Tente de novo em um instante."

# Endereco simples e seguro (nome@dominio.tld). Sem % ? & = / nem espacos: nada que mude o
# sentido do link mailto ou do cabecalho.
_ENDERECO = re.compile(
    r"^[A-Za-z0-9_+'-]+(?:\.[A-Za-z0-9_+'-]+)*"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
# Quebras de linha em qualquer forma (inclusive as do Unicode que o Python tambem quebra).
_QUEBRAS = re.compile(r"[\r\n\x0b\x0c\x1c-\x1e\x85  ]")
_CONTROLE = re.compile(r"[\x00-\x08\x0e-\x1b\x1f\x7f]")


def _abrir_no_windows(alvo: str | Path) -> bool:
    """Abre com o programa padrao (so no Windows). False = nao abriu (outro sistema)."""
    if not windows.IS_WINDOWS:
        return False
    windows.open_with_shell(alvo)
    return True


def validar_destinatarios(para: str) -> list[str] | str:
    """Lista de enderecos validos ou a frase de recusa.

    Args:
        para: enderecos separados por virgula ou ponto e virgula (vazio = nenhum).
    """
    texto = str(para)
    if _QUEBRAS.search(texto) or _CONTROLE.search(texto):
        return MSG_QUEBRA
    enderecos = [e.strip() for e in re.split(r"[,;]", texto) if e.strip()]
    if len(enderecos) > EMAIL_MAX_RECIPIENTS:
        return MSG_MUITOS
    for endereco in enderecos:
        if len(endereco) > 254 or not _ENDERECO.fullmatch(endereco):
            return MSG_ENDERECO.format(endereco=endereco[:60])
    return enderecos


def montar_mailto(enderecos: list[str], assunto: str, corpo: str) -> str:
    """Link ``mailto:`` (RFC 6068): tudo codificado, quebra de linha do corpo vira %0D%0A."""
    destino = ",".join(quote(e, safe="@") for e in enderecos)
    campos = []
    if assunto:
        campos.append("subject=" + quote(assunto, safe=""))
    if corpo:
        campos.append("body=" + quote(corpo.replace("\n", "\r\n"), safe=""))
    return f"mailto:{destino}" + ("?" + "&".join(campos) if campos else "")


def montar_eml(enderecos: list[str], assunto: str, corpo: str) -> bytes:
    """Rascunho .eml (UTF-8, CRLF) marcado como NAO enviado (``X-Unsent: 1``)."""
    mensagem = EmailMessage(policy=politica_padrao)
    if enderecos:
        mensagem["To"] = ", ".join(enderecos)
    mensagem["Subject"] = assunto
    mensagem["X-Unsent"] = "1"
    mensagem.set_content(corpo or "")
    return mensagem.as_bytes(policy=politica_padrao.clone(linesep="\r\n"))


class OfficeTools:
    """Acoes de escritorio expostas a IA (lista fechada em ``TOOL_NAMES``)."""

    TOOL_NAMES: ClassVar[tuple[str, ...]] = ("draft_email",)

    def __init__(
        self,
        guard: PathGuard,
        abrir: Callable[[str | Path], bool] | None = None,
        agora: Callable[[], datetime] | None = None,
    ) -> None:
        """Cria as ferramentas de escritorio.

        Args:
            guard: guarda de caminhos (pasta Documentos e pastas protegidas).
            abrir: abre um link ou arquivo no programa padrao e diz se abriu (injetavel em
                testes). None usa o ``os.startfile`` do Windows (em outros sistemas, nao abre).
            agora: relogio (injetavel em testes) para o nome do rascunho.
        """
        self._guard = guard
        self._abrir = abrir
        self._agora = agora or datetime.now
        self._lock = threading.Lock()

    def _abrir_alvo(self, alvo: str | Path) -> bool:
        return (self._abrir or _abrir_no_windows)(alvo)

    def draft_email(self, para: str, assunto: str, corpo: str) -> str:
        """Prepara um e-mail e abre na tela, PRONTO PARA O SENHOR REVISAR E ENVIAR. Voce
        NUNCA envia: so deixa pronto. Use quando o senhor pedir para escrever ou mandar um
        e-mail para alguem. Se ele nao disser o endereco, pergunte ou deixe "para" vazio.

        Args:
            para: e-mail(s) do destinatario, ex.: "ana@empresa.com" ou
                "ana@empresa.com; joao@empresa.com". Vazio = o senhor preenche.
            assunto: assunto do e-mail, em uma linha.
            corpo: o texto do e-mail (pode ter varias linhas e paragrafos).
        """
        enderecos = validar_destinatarios(para)
        if isinstance(enderecos, str):
            return enderecos
        assunto = str(assunto)
        if _QUEBRAS.search(assunto) or _CONTROLE.search(assunto):
            return MSG_QUEBRA
        assunto = " ".join(assunto.replace("\t", " ").split())
        if len(assunto) > EMAIL_MAX_SUBJECT:
            return MSG_ASSUNTO_GRANDE
        corpo = _CONTROLE.sub("", str(corpo)).replace("\r\n", "\n").replace("\r", "\n")
        corpo = corpo.strip("\n")
        if len(corpo) > EMAIL_MAX_BODY:
            return MSG_CORPO_GRANDE
        if not assunto and not corpo.strip():
            return MSG_VAZIO

        link = montar_mailto(enderecos, assunto, corpo)
        if len(link) <= MAILTO_MAX_CHARS:
            try:
                if not self._abrir_alvo(link):
                    return MSG_SO_WINDOWS
                logger.info("e-mail preparado por mailto (%d caracteres)", len(link))
                return MSG_PRONTO
            except OSError:
                # Sem programa de e-mail para "mailto:": tenta o rascunho .eml.
                logger.warning("mailto nao abriu; vou salvar um rascunho .eml")
        return self._rascunho_eml(enderecos, assunto, corpo)

    def _rascunho_eml(self, enderecos: list[str], assunto: str, corpo: str) -> str:
        pasta = self._guard.user_folders()["documentos"].joinpath(*DRAFTS_FOLDER)
        if self._guard.is_protected(pasta):
            return MSG_PROTEGIDO
        dados = montar_eml(enderecos, assunto, corpo)
        with self._lock:
            pasta.mkdir(parents=True, exist_ok=True)
            base = f"E-mail {self._agora():%Y-%m-%d %H-%M-%S}"
            alvo: Path | None = None
            for numero in range(1, DRAFT_MAX_COPIES + 1):
                nome = base if numero == 1 else f"{base} ({numero})"
                candidato = pasta / f"{nome}.eml"
                try:
                    # "xb" = so cria: nunca escreve por cima de outro rascunho.
                    with candidato.open("xb") as handle:
                        handle.write(dados)
                except FileExistsError:
                    continue
                alvo = candidato
                break
        if alvo is None:
            return MSG_NOMES
        logger.info("rascunho de e-mail salvo: %s", alvo)
        try:
            aberto = self._abrir_alvo(alvo)
        except OSError:
            aberto = False
        if not aberto:
            return MSG_RASCUNHO_SEM_ABRIR.format(alvo=alvo)
        return MSG_RASCUNHO.format(alvo=alvo)
