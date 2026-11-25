"""API que a pagina da janela chama (``window.pywebview.api``): configuracao do Jarvis.

O pywebview expoe ao JavaScript TODO metodo e atributo publico deste objeto. Por isso:
- so existem os metodos publicos da lista do contrato (nomes exatos);
- todo estado interno fica em atributos com ``_`` (o pywebview ignora);
- nenhum metodo levanta excecao para o JS: erro vira ``{"ok": False, "mensagem": ...}``;
- nenhuma chave e devolvida nem registrada em log (so os 4 ultimos caracteres, ``"…abcd"``);
- links abertos so de uma lista FECHADA de nomes (a pagina nunca manda URL).

Chamadas de Python para a pagina (nivel do microfone, aviso de chave) vao pela fila da
``OrbWindow`` (o "despachante"), nunca direto daqui.
"""

from __future__ import annotations

import functools
import logging
import os
import sys
import types
import webbrowser
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlsplit

from jarvis import __version__, armazenamento, verificacao, vozes
from jarvis.config import Settings
from jarvis.logging_setup import registrar_segredos
from jarvis.microfone import MSG_EM_USO, TesteMicrofone, tocar_pcm
from jarvis.ui import preferencias

if TYPE_CHECKING:
    from jarvis.controlador import Controlador

logger = logging.getLogger(__name__)

# Lista FECHADA de destinos de abrir_link. Nenhuma URL vem da pagina. Somente leitura.
LINKS: Mapping[str, str] = types.MappingProxyType(
    {
        "chave_google": "https://aistudio.google.com/apikey",
        "elevenlabs": "https://elevenlabs.io",
        "repositorio": "https://github.com/mateusmirandaia/jarvis",
        "instagram": "https://www.instagram.com/mateusmirandaia.ia/",
    }
)
# Hosts aceitos por abrir_link (segunda trava: mesmo que LINKS fosse trocado).
HOSTS_LINKS: frozenset[str] = frozenset(
    {"aistudio.google.com", "elevenlabs.io", "github.com", "www.instagram.com"}
)
PASTAS: tuple[str, ...] = ("pasta_config", "pasta_logs")

# Nomes exatos do contrato (um teste garante que sao os unicos metodos publicos).
METODOS_PUBLICOS: tuple[str, ...] = (
    "abrir_link",
    "amostra_voz",
    "aplicar_configuracao",
    "concluir_configuracao",
    "elevenlabs_desligar",
    "elevenlabs_listar_vozes",
    "elevenlabs_salvar",
    "elevenlabs_testar",
    "estado_config",
    "microfone_iniciar",
    "microfone_parar",
    "salvar_chave",
    "salvar_preferencias",
    "salvar_visual",
    "testar_chave",
)

VOZ_NOME_MAX = 60

MSG_ERRO = "Algo deu errado. Tente de novo; se continuar, veja o log."
MSG_SALVAR_FALHOU = "Não consegui salvar no disco. Confira se há espaço livre e tente de novo."
MSG_SEM_CHAVE = "Falta a chave do Google. Cole e teste a chave antes de continuar."
MSG_CHAVE_DO_PROJETO = (
    "Chave salva. Atenção: o arquivo .env da pasta do projeto tem outra chave, e ela continua "
    "valendo enquanto estiver lá."
)
MSG_PREFS_DO_ENV = (
    "Atenção: o arquivo .env define {variaveis}, e ele continua valendo enquanto estiver lá. "
    "Apague essa linha do .env para usar o que você escolheu aqui."
)
MSG_NOME = "O nome pode ter até 40 letras, numa linha só."
MSG_VOZ = "Escolha uma das vozes da lista."
MSG_FONE = "Opção de fone inválida."
MSG_FONTE = "Escolha a voz do Google ou a voz do ElevenLabs."
MSG_FONTE_SEM_EL = "Configure a voz do ElevenLabs na aba Voz personalizada antes de ligá-la."
MSG_DADOS = "Dados inválidos."
MSG_AMOSTRA = "amostra indisponível"
MSG_EL_SEM_CHAVE = "Cole a chave do ElevenLabs."
MSG_EL_DO_PROJETO = (
    "A voz do ElevenLabs está definida no arquivo .env da pasta do projeto. Apague as linhas "
    "ELEVENLABS_API_KEY e ELEVENLABS_VOICE_ID de lá para voltar à voz do Google."
)
MSG_EL_PRESA = (
    "Salvei, mas o arquivo .env da pasta do projeto define outra chave ou voz do ElevenLabs, e "
    "ela continua valendo. Apague as linhas ELEVENLABS_API_KEY e ELEVENLABS_VOICE_ID de lá "
    "para usar a voz escolhida aqui."
)
MSG_NAO_INICIOU = "Não consegui iniciar o Jarvis. Veja o log."


class _Janela(Protocol):
    def on_mic_teste(self, nivel: float) -> None: ...


def _carregar_padrao() -> Settings:
    settings = Settings.from_env(exigir_chave=False)
    registrar_segredos(settings.api_key, settings.elevenlabs_api_key)
    return settings


def url_segura(url: object) -> bool:
    """True so para ``https://`` de um host da lista ``HOSTS_LINKS`` (sem usuario/senha)."""
    if not isinstance(url, str) or any(ch.isspace() or ord(ch) < 32 for ch in url):
        return False
    partes = urlsplit(url)
    return (
        partes.scheme == "https"
        and partes.hostname in HOSTS_LINKS
        and partes.username is None
        and partes.port is None
    )


def _abrir_url(url: str) -> bool:
    """Abre no navegador padrao; no Windows, se o webbrowser falhar, tenta o shell."""
    if not url_segura(url):
        logger.warning("url fora da lista recusada")
        return False
    if webbrowser.open(url, new=2):
        return True
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]  # noqa: S606 - so https da lista
        return True
    return False


def _abrir_pasta(pasta: Path) -> bool:
    pasta.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(pasta))  # type: ignore[attr-defined]  # noqa: S606 - so pastas nossas
        return True
    return bool(webbrowser.open(pasta.resolve().as_uri()))


def _texto(valor: object) -> str:
    """Texto colado pela pessoa sem espacos/quebras nas pontas; nao-texto vira ``""``."""
    return valor.strip() if isinstance(valor, str) else ""


def estado_config(settings: Settings, prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resumo da configuracao para a pagina (``JARVIS_CONFIG.config`` e ``estado_config()``).

    Nunca inclui chaves: so ``chave_final`` (``"…abcd"``).
    """
    if prefs is None:
        prefs = preferencias.carregar()
    voz_nome = prefs.get(preferencias.CHAVE_ELEVENLABS_VOZ_NOME)
    visual = preferencias.visual_inicial(settings.visual) or preferencias.VISUAL_PADRAO
    return {
        "configurado": prefs.get(preferencias.CHAVE_CONFIGURADO) is True,
        "tem_chave": settings.has_api_key,
        "chave_final": armazenamento.final_da_chave(settings.api_key),
        # extra (fora do contrato): "ambiente" | "projeto" | "usuario" | "" — de onde veio a
        # chave; com "projeto"/"ambiente", trocar a chave pela janela nao muda a que vale.
        "chave_origem": settings.api_key_source,
        "voz": settings.voice,
        "nome": settings.user_name,
        "fone": settings.headphones,
        "visual": visual,
        # "google" | "elevenlabs": qual voz o Jarvis usa agora (escolha da engrenagem).
        "fonte_voz": "elevenlabs" if settings.uses_elevenlabs else "google",
        "elevenlabs": {
            "ativo": settings.uses_elevenlabs,
            "configurado": settings.elevenlabs_configurado,
            "voz_id": settings.elevenlabs_voice_id,
            "voz_nome": voz_nome if isinstance(voz_nome, str) else "",
            "chave_final": armazenamento.final_da_chave(settings.elevenlabs_api_key),
        },
        "versao": __version__,
        "pasta_config": str(armazenamento.pasta_usuario()),
        "pasta_logs": str(settings.log_file.parent),
        "vozes": vozes.lista_para_janela(),
    }


def _seguro(padrao: Callable[[], Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorador: qualquer excecao vira o valor ``padrao()`` (e um log sem detalhes da chave)."""

    def decorador(metodo: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(metodo)
        def embrulho(*args: Any, **kwargs: Any) -> Any:
            try:
                return metodo(*args, **kwargs)
            except Exception as erro:  # noqa: BLE001 - nunca levanta para o JavaScript
                logger.warning("falha em %s: %s", metodo.__name__, type(erro).__name__)
                return padrao()

        return embrulho

    return decorador


def _falha() -> dict[str, Any]:
    return {"ok": False, "mensagem": MSG_ERRO}


class ApiJs:
    """Objeto exposto como ``window.pywebview.api`` (veja a docstring do modulo)."""

    def __init__(
        self,
        *,
        carregar_settings: Callable[[], Settings] | None = None,
        controlador: Controlador | None = None,
        janela: _Janela | None = None,
        fabrica_gemini: Callable[[str], Any] | None = None,
        transporte_http: Any = None,
        transporte_http_async: Any = None,
        tocar: Callable[[bytes], None] | None = None,
        modulo_pyaudio: Callable[[], Any] | None = None,
        abrir_url: Callable[[str], bool] | None = None,
        abrir_pasta: Callable[[Path], bool] | None = None,
    ) -> None:
        self._carregar = carregar_settings or _carregar_padrao
        self._controlador = controlador
        self._janela = janela
        self._fabrica_gemini = fabrica_gemini
        self._transporte_http = transporte_http
        self._transporte_http_async = transporte_http_async
        self._tocar = tocar or tocar_pcm
        self._abrir_url = abrir_url or _abrir_url
        self._abrir_pasta = abrir_pasta or _abrir_pasta
        self._microfone = TesteMicrofone(self._nivel_microfone, modulo_pyaudio=modulo_pyaudio)

    def _ligar(
        self, *, controlador: Controlador | None = None, janela: _Janela | None = None
    ) -> None:
        """Liga o controlador e a janela depois de criados (privado: o JS nao enxerga)."""
        if controlador is not None:
            self._controlador = controlador
        if janela is not None:
            self._janela = janela

    def _nivel_microfone(self, nivel: float) -> None:
        janela = self._janela
        if janela is not None:
            janela.on_mic_teste(nivel)

    def _encerrar(self) -> None:
        """Para o teste do microfone (a janela chama ao fechar)."""
        self._microfone.parar()

    # ------------------------------------------------------------------ visual
    @_seguro(lambda: False)
    def salvar_visual(self, id_visual: object) -> bool:
        """Salva o visual escolhido na tela de escolha; devolve True se gravou."""
        return preferencias.salvar_visual(id_visual)

    # ------------------------------------------------------------------ estado
    @_seguro(lambda: {})
    def estado_config(self) -> dict[str, Any]:
        """Configuracao atual (sem chaves). Veja ``estado_config()`` do modulo."""
        return estado_config(self._carregar())

    # ------------------------------------------------------------------ Google
    @_seguro(_falha)
    def testar_chave(self, chave: object = "") -> dict[str, Any]:
        """Testa a chave colada (vazio = testa a chave ja salva). ``{ok, mensagem}``."""
        texto = _texto(chave)
        if not texto:
            texto = self._carregar().api_key
        registrar_segredos(texto)
        resultado = verificacao.testar_chave_gemini(texto, self._fabrica_gemini)
        return resultado.como_dict()

    @_seguro(_falha)
    def salvar_chave(self, chave: object) -> dict[str, Any]:
        """Salva a chave no .env do usuario, se o formato for plausivel (nao testa de novo)."""
        texto = _texto(chave)
        registrar_segredos(texto)
        if not verificacao.chave_google_plausivel(texto):
            return {"ok": False, "mensagem": verificacao.MSG_FORMATO}
        if not armazenamento.salvar_segredos({armazenamento.GEMINI_API_KEY: texto}):
            return {"ok": False, "mensagem": MSG_SALVAR_FALHOU}
        settings = self._carregar()
        if settings.api_key_source in {"ambiente", "projeto"} and settings.api_key != texto:
            return {"ok": True, "mensagem": MSG_CHAVE_DO_PROJETO}
        return {"ok": True, "mensagem": "Chave salva."}

    # ------------------------------------------------------------------- vozes
    @_seguro(lambda: {"ok": False, "dados": "", "mensagem": MSG_AMOSTRA})
    def amostra_voz(self, id_voz: object) -> dict[str, Any]:
        """``{ok: True, dados: "data:audio/wav;base64,..."}`` ou ``{ok: False, dados: ""}``."""
        dados = vozes.amostra_data_url(id_voz)
        if dados is None:
            return {"ok": False, "dados": "", "mensagem": MSG_AMOSTRA}
        return {"ok": True, "dados": dados, "mensagem": ""}

    # --------------------------------------------------------------- microfone
    @_seguro(_falha)
    def microfone_iniciar(self) -> dict[str, Any]:
        """Comeca o teste do microfone: a pagina recebe ``window.jarvis.setMicTeste(n)``."""
        controlador = self._controlador
        if controlador is not None and controlador.rodando:
            return {"ok": False, "mensagem": MSG_EM_USO}
        ok, mensagem = self._microfone.iniciar()
        return {"ok": ok, "mensagem": mensagem}

    @_seguro(lambda: False)
    def microfone_parar(self) -> bool:
        """Para o teste do microfone (sempre True)."""
        return self._microfone.parar()

    # ----------------------------------------------------------- preferencias
    @_seguro(_falha)
    def salvar_preferencias(self, dados: object) -> dict[str, Any]:
        """Salva ``{nome, voz, fone, fonte_voz}`` (qualquer subconjunto) no preferencias.json.

        ``fonte_voz`` ("google" | "elevenlabs") escolhe qual voz o Jarvis usa sem apagar a
        chave do ElevenLabs: com "google", ele fala com a voz do Google escolhida aqui.
        """
        if not isinstance(dados, dict):
            return {"ok": False, "mensagem": MSG_DADOS}
        alteracoes: dict[str, Any] = {}
        if "nome" in dados:
            nome = dados["nome"]
            if nome is None:
                nome = ""
            if not preferencias.nome_valido(nome):
                return {"ok": False, "mensagem": MSG_NOME}
            alteracoes[preferencias.CHAVE_NOME] = nome.strip()
        if "voz" in dados:
            if not vozes.voz_valida(dados["voz"]):
                return {"ok": False, "mensagem": MSG_VOZ}
            alteracoes[preferencias.CHAVE_VOZ] = dados["voz"]
        if "fone" in dados:
            if not isinstance(dados["fone"], bool):
                return {"ok": False, "mensagem": MSG_FONE}
            alteracoes[preferencias.CHAVE_FONE] = dados["fone"]
        if "fonte_voz" in dados:
            fonte = dados["fonte_voz"]
            if fonte not in preferencias.FONTES_VOZ:
                return {"ok": False, "mensagem": MSG_FONTE}
            if fonte == "elevenlabs" and not self._carregar().elevenlabs_configurado:
                return {"ok": False, "mensagem": MSG_FONTE_SEM_EL}
            alteracoes[preferencias.CHAVE_FONTE_VOZ] = fonte
        if not alteracoes:
            return {"ok": True, "mensagem": ""}
        if not preferencias.atualizar(alteracoes):
            return {"ok": False, "mensagem": MSG_SALVAR_FALHOU}
        logger.info("preferencias salvas: %s", ", ".join(sorted(alteracoes)))
        return {"ok": True, "mensagem": self._aviso_env_manda(alteracoes)}

    def _aviso_env_manda(self, alteracoes: dict[str, Any]) -> str:
        """Aviso quando o .env (do projeto ou do ambiente) define o que acabou de ser salvo.

        O .env ganha das preferencias (ex.: ``JARVIS_VOZ=Charon`` copiado do .env.example):
        sem o aviso, trocar a voz pela janela pareceria nao funcionar.
        """
        settings = self._carregar()
        atuais = {
            preferencias.CHAVE_NOME: ("JARVIS_NOME_USUARIO", settings.user_name),
            preferencias.CHAVE_VOZ: ("JARVIS_VOZ", settings.voice),
            preferencias.CHAVE_FONE: ("JARVIS_FONE", settings.headphones),
        }
        presas = [
            variavel
            for chave, (variavel, atual) in atuais.items()
            if chave in alteracoes and alteracoes[chave] != atual
        ]
        if not presas:
            return ""
        return MSG_PREFS_DO_ENV.format(variaveis=", ".join(presas))

    # --------------------------------------------------------------- assistente
    @_seguro(_falha)
    def concluir_configuracao(self) -> dict[str, Any]:
        """Marca ``configurado=true`` e inicia o assistente de voz."""
        self._microfone.parar()
        if not self._carregar().has_api_key:
            return {"ok": False, "mensagem": MSG_SEM_CHAVE}
        if not preferencias.atualizar({preferencias.CHAVE_CONFIGURADO: True}):
            return {"ok": False, "mensagem": MSG_SALVAR_FALHOU}
        controlador = self._controlador
        if controlador is None or not controlador.iniciar():
            return {"ok": False, "mensagem": MSG_NAO_INICIOU}
        logger.info("configuracao concluida")
        return {"ok": True, "mensagem": ""}

    @_seguro(_falha)
    def aplicar_configuracao(self) -> dict[str, Any]:
        """Reinicia o assistente com as configuracoes salvas (sem fechar a janela)."""
        self._microfone.parar()
        if not self._carregar().has_api_key:
            return {"ok": False, "mensagem": MSG_SEM_CHAVE}
        controlador = self._controlador
        if controlador is None or not controlador.reiniciar():
            return {"ok": False, "mensagem": MSG_NAO_INICIOU}
        logger.info("configuracao aplicada: assistente reiniciado")
        return {"ok": True, "mensagem": ""}

    # --------------------------------------------------------------- ElevenLabs
    def _chave_elevenlabs(self, chave: object) -> str:
        texto = _texto(chave) or self._carregar().elevenlabs_api_key
        registrar_segredos(texto)
        return texto

    @_seguro(lambda: {"ok": False, "vozes": [], "mensagem": MSG_ERRO})
    def elevenlabs_listar_vozes(self, chave: object = "") -> dict[str, Any]:
        """Vozes da conta: ``{ok, vozes: [{id, nome}], mensagem}`` (vazio = chave salva)."""
        texto = self._chave_elevenlabs(chave)
        if not texto:
            return {"ok": False, "vozes": [], "mensagem": MSG_EL_SEM_CHAVE}
        return verificacao.listar_vozes_elevenlabs(texto, transport=self._transporte_http)

    @_seguro(_falha)
    def elevenlabs_testar(self, chave: object = "", voz_id: object = "") -> dict[str, Any]:
        """Fala UMA frase curta com a voz (gasta creditos). Vazios = os valores salvos."""
        settings = self._carregar()
        texto = _texto(chave) or settings.elevenlabs_api_key
        registrar_segredos(texto)
        voz = _texto(voz_id) or settings.elevenlabs_voice_id
        if not texto:
            return {"ok": False, "mensagem": MSG_EL_SEM_CHAVE}
        resultado = verificacao.testar_voz_elevenlabs(
            texto,
            voz,
            self._tocar,
            modelo=settings.elevenlabs_model,
            transport=self._transporte_http_async,
        )
        return resultado.como_dict()

    @_seguro(_falha)
    def elevenlabs_salvar(
        self, chave: object = "", voz_id: object = "", voz_nome: object = ""
    ) -> dict[str, Any]:
        """Liga a voz do ElevenLabs (chave vazia = mantem a chave ja salva)."""
        texto = self._chave_elevenlabs(chave)
        voz = _texto(voz_id)
        if not verificacao.chave_elevenlabs_plausivel(texto):
            return {"ok": False, "mensagem": verificacao.EL_MSG_FORMATO}
        if not verificacao.voz_elevenlabs_plausivel(voz):
            return {"ok": False, "mensagem": verificacao.EL_MSG_VOZ_FORMATO}
        nome = _texto(voz_nome)[:VOZ_NOME_MAX]
        if not nome or not nome.isprintable():
            nome = voz  # nome vindo da lista do ElevenLabs; sem nome limpo, mostra o ID
        segredos = {armazenamento.ELEVENLABS_API_KEY: texto, armazenamento.ELEVENLABS_VOICE_ID: voz}
        if not armazenamento.salvar_segredos(segredos):
            return {"ok": False, "mensagem": MSG_SALVAR_FALHOU}
        # O .env do projeto (ou o ambiente) ganha do .env do usuario: se ele define outra
        # chave/voz, a escolhida aqui nao vale. Avisa e nao troca o nome mostrado.
        valendo = self._carregar()
        presa = valendo.elevenlabs_voice_id != voz or valendo.elevenlabs_api_key != texto
        alteracoes: dict[str, Any] = {preferencias.CHAVE_FONTE_VOZ: "elevenlabs"}
        if not presa:
            alteracoes[preferencias.CHAVE_ELEVENLABS_VOZ_NOME] = nome
        preferencias.atualizar(alteracoes)
        logger.info("voz do ElevenLabs salva%s", " (o .env do projeto manda)" if presa else "")
        if presa:
            return {"ok": True, "mensagem": MSG_EL_PRESA, "aviso": MSG_EL_PRESA}
        return {"ok": True, "mensagem": "Voz do ElevenLabs salva."}

    @_seguro(_falha)
    def elevenlabs_desligar(self) -> dict[str, Any]:
        """Volta para a voz do Google.

        Apaga a chave e a voz do ElevenLabs do .env do usuario e marca ``fonte_voz=google``.
        Se a chave estiver no .env do projeto (modo desenvolvedor), ela fica la guardada,
        mas o Jarvis passa a usar a voz do Google; da para religar na engrenagem.
        """
        segredos: dict[str, str | None] = {
            armazenamento.ELEVENLABS_API_KEY: None,
            armazenamento.ELEVENLABS_VOICE_ID: None,
        }
        if not armazenamento.salvar_segredos(segredos):
            return {"ok": False, "mensagem": MSG_SALVAR_FALHOU}
        if not preferencias.atualizar({preferencias.CHAVE_FONTE_VOZ: "google"}):
            return {"ok": False, "mensagem": MSG_SALVAR_FALHOU}
        if not self._carregar().elevenlabs_configurado:
            preferencias.atualizar({preferencias.CHAVE_ELEVENLABS_VOZ_NOME: None})
            logger.info("voz do ElevenLabs desligada")
            return {"ok": True, "mensagem": "Voltei para a voz do Google."}
        logger.info("voz do ElevenLabs pausada (chave no .env do projeto)")
        return {
            "ok": True,
            "mensagem": "Voltei para a voz do Google. A chave do ElevenLabs continua no .env "
            "do projeto: para religar, escolha a voz do ElevenLabs em Geral.",
        }

    # ------------------------------------------------------------------- links
    @_seguro(lambda: False)
    def abrir_link(self, nome: object) -> bool:
        """Abre um destino da lista fechada (sites no navegador padrao, pastas no Explorer)."""
        if not isinstance(nome, str):
            return False
        if nome in LINKS:
            url = LINKS[nome]
            if not url_segura(url):
                logger.warning("abrir_link %s: endereco fora da lista recusado", nome)
                return False
            aberto = bool(self._abrir_url(url))
            logger.info("abrir_link %s: %s", nome, "ok" if aberto else "falhou")
            return aberto
        if nome == "pasta_config":
            return bool(self._abrir_pasta(armazenamento.pasta_usuario()))
        if nome == "pasta_logs":
            return bool(self._abrir_pasta(self._carregar().log_file.parent))
        logger.warning("abrir_link com destino desconhecido: %r", nome[:40])
        return False


# Fabrica das funcoes da ponte, compilada num espaco de nomes VAZIO (sem modulos, sem
# builtins). O pywebview resolve o nome pedido pela pagina com getattr encadeado ("a.b.c",
# sem filtrar "__"): assim "abrir_link.__globals__" e so este dicionario descartavel, e nao
# os globais deste modulo (LINKS, os, webbrowser...). A funcao gerada nao le nenhum global:
# o metodo da ApiJs fica so na closure, que o getattr nao alcanca.
_FABRICA_FONTE = """
def fabrica(metodo):
    def chamar(*args):
        return metodo(*args)
    return chamar
"""


def _criar_chamada(metodo: Callable[..., Any], nome: str) -> Callable[..., Any]:
    caixa: dict[str, Any] = {"__builtins__": {}}
    exec(compile(_FABRICA_FONTE, "<ponte_js>", "exec"), caixa)  # noqa: S102 - texto fixo acima
    chamar = caixa.pop("fabrica")(metodo)
    caixa.clear()
    caixa["__builtins__"] = {}
    chamar.__name__ = nome
    chamar.__qualname__ = f"PonteJs.{nome}"
    chamar.__doc__ = getattr(metodo, "__doc__", None)
    return chamar


def ponte_js(api: ApiJs) -> object:
    """Objeto entregue ao pywebview: so as 15 funcoes do contrato, e nada mais.

    O pywebview executa qualquer nome que a pagina mandar, inclusive "a.b.c" resolvido com
    getattr encadeado e nomes com ``_``/``__``. Por isso a janela nao recebe a ``ApiJs``, e
    sim esta fachada:

    - a classe nao tem nenhuma funcao Python (so ``__slots__``), entao ``__class__``,
      ``__init__``, ``__setattr__``... sao todos do proprio Python (sem ``__globals__``);
    - cada uma das 15 funcoes fica num slot da instancia (nao vira metodo: sem ``__self__``
      nem ``__func__``) e foi criada por ``_criar_chamada``: ``__globals__`` e um dicionario
      vazio e descartavel, e a ``ApiJs`` fica so na closure.
    """
    classe = type("PonteJs", (), {"__slots__": METODOS_PUBLICOS, "__module__": "jarvis.ponte"})
    ponte = classe()
    for nome in METODOS_PUBLICOS:
        object.__setattr__(ponte, nome, _criar_chamada(getattr(api, nome), nome))
    return ponte
