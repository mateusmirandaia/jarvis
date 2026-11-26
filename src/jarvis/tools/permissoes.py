"""Permissoes das ferramentas: o que a pessoa liberou na engrenagem (aba Permissoes).

Modelo (nomes fixos, guardado em ``preferencias.json`` na chave ``"permissoes"``)::

    {"arquivos": "nenhum" | "ler" | "ler_gravar" | "ler_gravar_excluir",
     "apps": bool, "internet": bool, "email": bool, "outros_drives": bool}

Regras:
- PADRAO TUDO DESLIGADO. Sem chave no arquivo, arquivo corrompido ou valor estranho: desligado.
- So ``current_time`` e sempre liberada.
- Ferramenta que nao esta no mapa ``EXIGENCIAS`` fica bloqueada (lista fechada).
- ``outros_drives`` e um modificador aplicado no caminho (``PathGuard``), nao uma ferramenta.

Este modulo nao le disco: quem le e grava e ``jarvis.ui.preferencias``. Nada aqui levanta
excecao para quem chama.
"""

from __future__ import annotations

import types
from collections.abc import Mapping
from typing import Any

# Frase de "Outros discos" desligado (a recusa acontece no PathGuard, em security.py).
from jarvis.tools.security import MSG_OUTROS_DRIVES as MSG_OUTROS_DRIVES

# ------------------------------------------------------------------ modelo
CHAVE_ARQUIVOS = "arquivos"
CHAVE_APPS = "apps"
CHAVE_INTERNET = "internet"
CHAVE_EMAIL = "email"
CHAVE_OUTROS_DRIVES = "outros_drives"

# Niveis de Arquivos, do menor para o maior (cada um inclui os anteriores).
NIVEIS_ARQUIVOS: tuple[str, ...] = ("nenhum", "ler", "ler_gravar", "ler_gravar_excluir")
CHAVES_BOOL: tuple[str, ...] = (CHAVE_APPS, CHAVE_INTERNET, CHAVE_EMAIL, CHAVE_OUTROS_DRIVES)
CHAVES: tuple[str, ...] = (CHAVE_ARQUIVOS, *CHAVES_BOOL)

PADRAO: Mapping[str, Any] = types.MappingProxyType(
    {
        CHAVE_ARQUIVOS: "nenhum",
        CHAVE_APPS: False,
        CHAVE_INTERNET: False,
        CHAVE_EMAIL: False,
        CHAVE_OUTROS_DRIVES: False,
    }
)

# ------------------------------------------------------- ferramenta -> exigencia
# Cada exigencia e (chave, valor minimo). Para "arquivos", o valor e o nivel minimo; para as
# outras, True. None = sempre liberada.
_LER = (CHAVE_ARQUIVOS, "ler")
_GRAVAR = (CHAVE_ARQUIVOS, "ler_gravar")
_EXCLUIR = (CHAVE_ARQUIVOS, "ler_gravar_excluir")
EXIGENCIAS: Mapping[str, tuple[str, Any] | None] = types.MappingProxyType(
    {
        "current_time": None,
        # programas
        "list_open_apps": (CHAVE_APPS, True),
        "open_app": (CHAVE_APPS, True),
        "close_app": (CHAVE_APPS, True),
        # internet
        "open_website": (CHAVE_INTERNET, True),
        "web_search": (CHAVE_INTERNET, True),
        # e-mail (so prepara; nunca envia)
        "draft_email": (CHAVE_EMAIL, True),
        # arquivos: ler
        "list_folder": _LER,
        "find_file": _LER,
        "open_file": _LER,
        "read_file": _LER,
        # arquivos: ler e gravar
        "create_folder": _GRAVAR,
        "move_or_rename": _GRAVAR,
        "copy_item": _GRAVAR,
        "create_text_file": _GRAVAR,
        "write_word_document": _GRAVAR,
        # arquivos: excluir (a janela Sim/Nao continua obrigatoria)
        "delete_to_trash": _EXCLUIR,
    }
)

# Nomes que a pessoa ve/ouve (com acento), usados na mensagem de bloqueio.
NOMES_AMIGAVEIS: Mapping[str, str] = types.MappingProxyType(
    {
        "list_open_apps": "ver os programas abertos",
        "open_app": "abrir programas",
        "close_app": "fechar programas",
        "open_website": "abrir sites",
        "web_search": "pesquisar na internet",
        "draft_email": "preparar e-mails",
        "list_folder": "ver o que tem nas pastas",
        "find_file": "procurar arquivos",
        "open_file": "abrir arquivos",
        "read_file": "ler arquivos",
        "create_folder": "criar pastas",
        "move_or_rename": "mover ou renomear arquivos",
        "copy_item": "copiar arquivos",
        "create_text_file": "criar arquivos de texto",
        "write_word_document": "criar documentos do Word",
        "delete_to_trash": "mandar arquivos para a Lixeira",
    }
)
NOME_DESCONHECIDO = "ação desconhecida"

MSG_BLOQUEIO = (
    "Essa ação está desligada nas permissões ({nome}). Para liberar, abra a engrenagem e vá "
    "em Permissões."
)

# Textos do painel (aba Permissoes e passo do assistente). A pagina tambem tem uma copia
# fixa, usada fora do app; estes vem do Python via ``permissoes_estado()``.
DESCRICOES_ARQUIVOS: Mapping[str, str] = types.MappingProxyType(
    {
        "nenhum": "Não mexe em nenhum arquivo nem pasta.",
        "ler": "Vê pastas, procura, abre e lê arquivos. Não muda nada.",
        "ler_gravar": "Também cria pastas e documentos, copia, move e renomeia.",
        "ler_gravar_excluir": (
            "Também manda arquivos para a Lixeira. Mesmo assim ele sempre pergunta antes de apagar."
        ),
    }
)
ROTULOS_ARQUIVOS: Mapping[str, str] = types.MappingProxyType(
    {
        "nenhum": "Nenhum",
        "ler": "Só ler",
        "ler_gravar": "Ler e gravar",
        "ler_gravar_excluir": "Ler, gravar e excluir",
    }
)
DESCRICOES_CHAVES: Mapping[str, tuple[str, str]] = types.MappingProxyType(
    {
        CHAVE_APPS: ("Abrir e fechar programas", "Abre, fecha e lista os programas pelo nome."),
        CHAVE_INTERNET: ("Abrir sites e pesquisar", "Abre sites e faz pesquisas no navegador."),
        CHAVE_EMAIL: (
            "Preparar e-mails",
            "Deixa o e-mail pronto no seu programa de e-mail. Quem envia é você.",
        ),
        CHAVE_OUTROS_DRIVES: (
            "Outros discos",
            "Também mexe em outros discos, como D: ou pendrive. Desligado: só nas suas pastas.",
        ),
    }
)
SEMPRE_BLOQUEADO: tuple[str, ...] = (
    "Arquivos de chave e senha (.env e afins)",
    "Pasta do Windows",
    "Arquivos de Programas",
    "ProgramData",
    "Raiz dos discos (como C:\\)",
    "A pasta do próprio Jarvis e das configurações dele",
    "Terminal, PowerShell, Prompt de Comando, Regedit, executáveis e scripts",
    "Pastas de rede",
)


def normalizar(bruto: object) -> dict[str, Any]:
    """Devolve um dicionario COMPLETO e valido; qualquer valor invalido vira desligado.

    Args:
        bruto: o que veio do preferencias.json (pode ser qualquer coisa).
    """
    resultado = dict(PADRAO)
    if not isinstance(bruto, Mapping):
        return resultado
    nivel = bruto.get(CHAVE_ARQUIVOS)
    if isinstance(nivel, str) and nivel in NIVEIS_ARQUIVOS:
        resultado[CHAVE_ARQUIVOS] = nivel
    for chave in CHAVES_BOOL:
        # So True de verdade liga (1, "sim", "true" nao contam).
        resultado[chave] = bruto.get(chave) is True
    return resultado


def validar(dados: object) -> dict[str, Any] | None:
    """Validacao ESTRITA do que a pagina mandou: devolve o modelo completo ou None.

    Diferente de ``normalizar``, aqui qualquer coisa errada recusa tudo: precisa ter
    EXATAMENTE as 5 chaves, ``arquivos`` com um dos 4 niveis e as outras com bool de verdade.

    Args:
        dados: dicionario vindo do JavaScript.
    """
    if not isinstance(dados, Mapping) or len(dados) != len(CHAVES):
        return None
    if any(not isinstance(chave, str) or chave not in CHAVES for chave in dados):
        return None
    nivel = dados[CHAVE_ARQUIVOS]
    if not isinstance(nivel, str) or nivel not in NIVEIS_ARQUIVOS:
        return None
    if any(not isinstance(dados[chave], bool) for chave in CHAVES_BOOL):
        return None
    return {CHAVE_ARQUIVOS: nivel, **{chave: dados[chave] for chave in CHAVES_BOOL}}


def nome_amigavel(ferramenta: str) -> str:
    """Nome em portugues da acao (para a mensagem de bloqueio)."""
    return NOMES_AMIGAVEIS.get(ferramenta, NOME_DESCONHECIDO)


def permitido(ferramenta: str, permissoes: object) -> bool:
    """True se a ferramenta pode rodar com estas permissoes (lista fechada).

    Args:
        ferramenta: nome da ferramenta (ex.: "open_app").
        permissoes: modelo (sera normalizado; invalido = desligado).
    """
    if not isinstance(ferramenta, str) or ferramenta not in EXIGENCIAS:
        return False
    exigencia = EXIGENCIAS[ferramenta]
    if exigencia is None:
        return True
    atuais = normalizar(permissoes)
    chave, minimo = exigencia
    if chave == CHAVE_ARQUIVOS:
        return NIVEIS_ARQUIVOS.index(atuais[CHAVE_ARQUIVOS]) >= NIVEIS_ARQUIVOS.index(minimo)
    return atuais[chave] is True


def mensagem_bloqueio(ferramenta: str) -> str:
    """Frase devolvida a IA quando a ferramenta esta desligada."""
    return MSG_BLOQUEIO.format(nome=nome_amigavel(ferramenta))


def outros_drives(permissoes: object) -> bool:
    """True se o modificador "Outros discos" esta ligado."""
    return normalizar(permissoes)[CHAVE_OUTROS_DRIVES]


def descricao_painel() -> dict[str, Any]:
    """Textos do painel (sem estado): niveis, chaves e a lista "Sempre bloqueado"."""
    return {
        "niveis": [
            {
                "id": nivel,
                "rotulo": ROTULOS_ARQUIVOS[nivel],
                "descricao": DESCRICOES_ARQUIVOS[nivel],
            }
            for nivel in NIVEIS_ARQUIVOS
        ],
        "chaves": [
            {"id": chave, "rotulo": rotulo, "descricao": descricao}
            for chave, (rotulo, descricao) in DESCRICOES_CHAVES.items()
        ],
        "sempre_bloqueado": list(SEMPRE_BLOQUEADO),
    }
