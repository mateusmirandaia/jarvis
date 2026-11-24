/* Visual "mapa" — Mapa Mental Vivo (paleta aurora).
 * Núcleo JARVIS no centro, 7 ramos curvos para os nós primários, folhas com rótulos,
 * impulsos de luz correndo pelos ramos e poeira de estrelas no fundo.
 * Geometria em coordenadas de uma caixa 680x580 (centro 340,290), escalada para a área.
 */
(function () {
  "use strict";

  var FONTE = 'Bahnschrift, "Segoe UI", sans-serif';
  var CAIXA_L = 760; // largura de referência (inclui folga para os rótulos das folhas)
  var CAIXA_A = 600;

  // nome, chave de cor, folhas
  var RAMOS = [
    ["Voz", "ouvindo", ["microfone", "anti-eco", "voz Charon"]],
    ["Cérebro", "pensando", ["Gemini Live", "persona", "contexto"]],
    ["Ferramentas", "falando", ["14 ações", "apps", "data e hora"]],
    ["Arquivos", "falando", ["criar pasta", "mover", "Lixeira"]],
    ["Web", "ouvindo", ["abrir site", "pesquisar"]],
    ["Segurança", "erro", ["PathGuard", "clique Sim/Não", "nunca sobrescreve"]],
    ["Memória", "pensando", ["conversa", "turnos"]],
  ];
  var I_VOZ = 0, I_CEREBRO = 1, I_FERRAMENTAS = 2, I_ARQUIVOS = 3, I_WEB = 4, I_MEMORIA = 6;

  var CORES_PADRAO = {
    fundo: "#05070F", linha: "#1A2444", texto: "#E6F1FF", texto2: "#8FA3BF",
    ouvindo: "#38E1FF", pensando: "#8B7CFF", falando: "#FFB23F", erro: "#FF5C7A",
  };

  function cor(c, chave) {
    if (c && c[chave]) return c[chave];
    if (c) {
      if (chave === "ouvindo" && c.primaria) return c.primaria;
      if (chave === "pensando" && c.escura) return c.escura;
      if (chave === "falando" && c.destaque) return c.destaque;
    }
    return CORES_PADRAO[chave] || "#FFFFFF";
  }

  // gerador pseudo-aleatório determinístico (mesmo desenho em toda abertura)
  function rnd(semente) {
    var s = semente >>> 0;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }

  // curva quadrática como no mockup: controle deslocado perpendicularmente
  function curva(x1, y1, x2, y2, dobra) {
    var mx = (x1 + x2) / 2, my = (y1 + y2) / 2, dx = x2 - x1, dy = y2 - y1;
    return { x1: x1, y1: y1, cx: mx - dy * dobra, cy: my + dx * dobra, x2: x2, y2: y2 };
  }

  function ramoDaFerramenta(nome) {
    var n = String(nome || "").toLowerCase();
    // nomes reais das ferramentas (ingles: create_folder, move_or_rename, delete_to_trash...)
    if (/arquivo|pasta|mover|copiar|renomear|lixeira|file|folder|move|copy|rename|trash/.test(n)) {
      return I_ARQUIVOS;
    }
    if (/site|pesquis|navegador|web/.test(n)) return I_WEB;
    return I_FERRAMENTAS;
  }

  function criar() {
    var r = rnd(42);
    var n = RAMOS.length;
    var ramos = [];
    for (var bi = 0; bi < n; bi++) {
      var a = -Math.PI / 2 + (bi * 2 * Math.PI) / n;
      var px = Math.cos(a) * 160, py = Math.sin(a) * 150;
      var folhas = [];
      var lista = RAMOS[bi][2];
      for (var li = 0; li < lista.length; li++) {
        var la = a + (li - (lista.length - 1) / 2) * 0.36;
        var lx = Math.cos(la) * 255, ly = Math.sin(la) * 232;
        var ca = Math.cos(la);
        var alinh = ca > 0.2 ? "left" : ca < -0.2 ? "right" : "center";
        folhas.push({
          nome: lista[li],
          c: curva(px, py, lx, ly, -0.12),
          x: lx, y: ly,
          alinh: alinh,
          tx: lx + (alinh === "left" ? 9 : alinh === "right" ? -9 : 0),
          ty: ly + (alinh !== "center" ? 4 : Math.sin(la) > 0 ? 16 : -10),
          sempre: r() < 0.5, // impulso visível mesmo com o ramo apagado
          fase: r(),
          vel: 1 / (1.6 + r() * 1.4),
          piscaFase: r() * 6.28,
        });
      }
      ramos.push({
        nome: RAMOS[bi][0],
        chave: RAMOS[bi][1],
        x: px, y: py,
        c: curva(Math.cos(a) * 62, Math.sin(a) * 62, px, py, 0.18),
        folhas: folhas,
        fase: bi * 0.3 / 2.4,
        fonte: "600 " + (RAMOS[bi][0].length > 8 ? 10.5 : 11.5) + "px " + FONTE,
      });
    }

    // poeira de estrelas (normalizada na área)
    var NE = 140;
    var estrelas = new Float32Array(NE * 5);
    for (var i = 0; i < NE; i++) {
      estrelas[i * 5] = r();
      estrelas[i * 5 + 1] = r();
      estrelas[i * 5 + 2] = 0.4 + r() * 0.9; // raio
      estrelas[i * 5 + 3] = r() * 6.28; // fase
      estrelas[i * 5 + 4] = 6.28 / (2 + r() * 3); // velocidade do piscar
    }

    // estado animado
    var ativo = new Float32Array(n); // 0..1 suavizado por ramo
    var evTempo = new Float32Array(n); // segundos restantes de destaque por evento
    var evErro = new Uint8Array(n);
    var fase = 0; // acumulador de fase dos impulsos
    var giro = 0; // acumulador das órbitas
    var tAnt = -1;

    var TRACO_ORB1 = [2, 7];
    var TRACO_ORB2 = [40, 10, 4, 10];
    var TRACO_NUCLEO = [1, 4];
    var SEM_TRACO = [];
    var grads = {}; // gradientes em coordenadas locais (reutilizados entre quadros)

    function gradNucleo(ctx, c1, c2) {
      var k = "n" + c1 + c2;
      var g = grads[k];
      if (!g) {
        g = ctx.createRadialGradient(0, 0, 0, 0, 0, 110);
        g.addColorStop(0, hexA(c1, 0.55));
        g.addColorStop(0.6, hexA(c2, 0.12));
        g.addColorStop(1, hexA(c2, 0));
        grads[k] = g;
      }
      return g;
    }

    function gradBorda(ctx, a, b, c) {
      var k = "b" + a + b + c;
      var g = grads[k];
      if (!g) {
        g = ctx.createLinearGradient(-58, 0, 58, 0);
        g.addColorStop(0, a);
        g.addColorStop(0.5, b);
        g.addColorStop(1, c);
        grads[k] = g;
      }
      return g;
    }

    function ponto(c, u, saida) {
      var v = 1 - u;
      saida[0] = v * v * c.x1 + 2 * v * u * c.cx + u * u * c.x2;
      saida[1] = v * v * c.y1 + 2 * v * u * c.cy + u * u * c.y2;
    }
    var P = [0, 0];

    function tracarCurva(ctx, c) {
      ctx.beginPath();
      ctx.moveTo(c.x1, c.y1);
      ctx.quadraticCurveTo(c.cx, c.cy, c.x2, c.y2);
      ctx.stroke();
    }

    // impulso: trecho curto da curva terminando em u, com brilho
    function impulso(ctx, c, u, larg, alfa, corI, esc, cauda) {
      if (alfa <= 0.01) return;
      var u0 = u - (cauda || 0.09);
      if (u0 < 0) u0 = 0;
      var env = Math.sin(Math.PI * u);
      ctx.strokeStyle = corI;
      for (var passe = 0; passe < 2; passe++) {
        ctx.globalAlpha = alfa * env * (passe === 0 ? 0.22 : 0.95);
        ctx.lineWidth = passe === 0 ? larg + 6 : Math.max(larg + 1.4, 1.2 / esc);
        ctx.beginPath();
        for (var s = 0; s <= 5; s++) {
          ponto(c, u0 + ((u - u0) * s) / 5, P);
          if (s === 0) ctx.moveTo(P[0], P[1]);
          else ctx.lineTo(P[0], P[1]);
        }
        ctx.stroke();
      }
    }

    function desenhar(ctx, q) {
      var t = q.t || 0;
      var dt = q.dt;
      if (!(dt >= 0)) dt = tAnt < 0 ? 0 : Math.max(0, Math.min(0.1, t - tAnt));
      tAnt = t;
      var c = q.cores || CORES_PADRAO;
      var estado = q.estado || "idle";
      var nivel = q.nivel || 0;
      var agit = q.agitacao == null ? 0.15 : q.agitacao;
      var mist = q.mistura || 0;
      var offline = estado === "offline";
      var previa = !!q.previa;
      var corErro = cor(c, "erro");
      var corFundo = c.fundo || CORES_PADRAO.fundo;

      // velocidades integradas (sem saltos ao trocar de estado)
      var vel = 0.12 + agit * 1.5 + (estado === "speaking" ? nivel * 0.7 : 0);
      fase += dt * vel;
      giro += dt * (0.25 + agit * 1.6);

      // alvos de ativação por estado
      for (var i = 0; i < n; i++) {
        var alvo = 0;
        if (estado === "listening" && i === I_VOZ) alvo = 0.75 + nivel * 0.25;
        else if (estado === "thinking" && i === I_CEREBRO) alvo = 1;
        else if (estado === "speaking" && (i === I_VOZ || i === I_MEMORIA)) alvo = 0.8 + nivel * 0.2;
        else if (estado === "idle") alvo = 0.12 * (0.5 + 0.5 * Math.sin(t * 0.5 - i * 0.9));
        if (evTempo[i] > 0) {
          evTempo[i] -= dt;
          alvo = 1;
          if (evTempo[i] <= 0) evErro[i] = 0;
        }
        if (offline) alvo = 0;
        ativo[i] += (alvo - ativo[i]) * Math.min(1, dt * 5);
      }

      var x = q.x || 0, y = q.y || 0, w = q.w || 680, h = q.h || 580;

      // ---- poeira de estrelas (na área inteira) ----
      ctx.save();
      ctx.fillStyle = offline ? corErro : cor(c, "texto2");
      var ne = previa ? 60 : 140;
      for (var k = 0; k < ne; k++) {
        var o = k * 5;
        var rr = estrelas[o + 2];
        ctx.globalAlpha = (offline ? 0.25 : 0.55) * (0.3 + 0.7 * (0.5 + 0.5 * Math.sin(t * estrelas[o + 4] + estrelas[o + 3])));
        ctx.fillRect(x + estrelas[o] * w - rr / 2, y + estrelas[o + 1] * h - rr / 2, rr, rr);
      }
      ctx.restore();

      var esc = Math.min(w / CAIXA_L, h / CAIXA_A);
      if (!(esc > 0)) return;
      var cx = x + w / 2, cy = y + h / 2;
      var mostraFolhas = 10.5 * esc >= 6.5 && !(previa && esc < 0.75);
      var mostraNomes = 11 * esc >= 5.5;

      ctx.save();
      ctx.translate(cx, cy);
      ctx.scale(esc, esc);
      ctx.lineCap = "round";
      var linhaMin = 0.6 / esc;

      // ---- órbitas ----
      var corO1 = offline ? corErro : cor(c, "pensando");
      var corO2 = offline ? corErro : cor(c, "ouvindo");
      ctx.lineWidth = Math.max(1, linhaMin);
      ctx.setLineDash(TRACO_ORB1);
      ctx.lineDashOffset = -giro * 4;
      ctx.strokeStyle = corO1;
      ctx.globalAlpha = 0.6;
      ctx.beginPath();
      ctx.arc(0, 0, 120, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash(TRACO_ORB2);
      ctx.lineDashOffset = giro * 9;
      ctx.strokeStyle = corO2;
      ctx.globalAlpha = 0.3;
      ctx.beginPath();
      ctx.arc(0, 0, 205, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash(SEM_TRACO);
      ctx.strokeStyle = c.linha || CORES_PADRAO.linha;
      ctx.globalAlpha = 0.9;
      ctx.beginPath();
      ctx.arc(0, 0, 262, 0, Math.PI * 2);
      ctx.stroke();

      // ---- ramos, folhas e impulsos ----
      for (var b = 0; b < n; b++) {
        var R = ramos[b];
        var at = ativo[b];
        var corR = cor(c, R.chave);
        if (offline) corR = corErro;
        else if (evTempo[b] > 0 && evErro[b] && Math.floor(t * 6) % 2 === 0) corR = corErro;
        var larg = 1.3 + 0.9 * at;
        if (estado === "speaking" && at > 0.3) larg += nivel * 1.2;

        // ligações das folhas
        ctx.strokeStyle = corR;
        ctx.lineWidth = Math.max(1, linhaMin);
        ctx.globalAlpha = (offline ? 0.18 : 0.3) + 0.4 * at;
        for (var f = 0; f < R.folhas.length; f++) tracarCurva(ctx, R.folhas[f].c);

        // brilho largo do ramo aceso
        if (at > 0.05) {
          ctx.globalAlpha = 0.13 * at;
          ctx.lineWidth = larg + 7;
          tracarCurva(ctx, R.c);
          ctx.globalAlpha = 0.08 * at;
          ctx.lineWidth = 5;
          for (f = 0; f < R.folhas.length; f++) tracarCurva(ctx, R.folhas[f].c);
        }

        // ramo principal
        ctx.lineWidth = Math.max(larg, linhaMin);
        ctx.globalAlpha = (offline ? 0.3 : 0.45) + 0.45 * at;
        tracarCurva(ctx, R.c);

        {
          var alfaImp = offline ? 0.25 : 1;
          // impulsos no ramo: 1 sempre, +2 quando ativo
          impulso(ctx, R.c, (fase + R.fase) % 1, larg, alfaImp * (0.55 + 0.45 * at), corR, esc, 0.09 + 0.08 * at);
          if (at > 0.02 && !previa) {
            impulso(ctx, R.c, (fase + R.fase + 0.33) % 1, larg, alfaImp * at, corR, esc, 0.09 + 0.08 * at);
            impulso(ctx, R.c, (fase + R.fase + 0.66) % 1, larg, alfaImp * at, corR, esc, 0.09 + 0.08 * at);
          } else if (at > 0.02) {
            impulso(ctx, R.c, (fase + R.fase + 0.5) % 1, larg, alfaImp * at, corR, esc, 0.09 + 0.08 * at);
          }
          // impulsos nas folhas
          for (f = 0; f < R.folhas.length; f++) {
            var F = R.folhas[f];
            var af = (F.sempre ? 0.5 + 0.5 * at : at) * alfaImp;
            if (af > 0.02) impulso(ctx, F.c, (fase * F.vel * 2.4 + F.fase) % 1, 1, af, corR, esc);
          }
        }

        // nós das folhas
        ctx.fillStyle = corFundo;
        ctx.lineWidth = Math.max(1.5, linhaMin);
        for (f = 0; f < R.folhas.length; f++) {
          F = R.folhas[f];
          ctx.globalAlpha = (0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * 2.6 + F.piscaFase))) * (offline ? 0.5 : 0.7 + 0.3 * at);
          ctx.beginPath();
          ctx.arc(F.x, F.y, 4, 0, Math.PI * 2);
          ctx.fill();
          ctx.stroke();
        }

        // nó primário
        var raio = 20 + 4 * at;
        if (b === I_VOZ && estado === "listening") raio += nivel * 6;
        if (at > 0.05) {
          // halo suave do nó ativo
          ctx.globalAlpha = 0.16 * at;
          ctx.fillStyle = corR;
          ctx.beginPath();
          ctx.arc(R.x, R.y, raio + 9, 0, Math.PI * 2);
          ctx.fill();
          // anel que pisca
          ctx.globalAlpha = at * (0.3 + 0.35 * (0.5 + 0.5 * Math.sin(t * 2.6 + b)));
          ctx.lineWidth = Math.max(1, linhaMin);
          ctx.beginPath();
          ctx.arc(R.x, R.y, raio + 7 + (b === I_VOZ ? nivel * 4 : 0), 0, Math.PI * 2);
          ctx.stroke();
        }
        ctx.globalAlpha = 1;
        ctx.fillStyle = corFundo;
        ctx.strokeStyle = corR;
        ctx.lineWidth = Math.max(1.2 + 0.8 * at, linhaMin);
        ctx.beginPath();
        ctx.arc(R.x, R.y, raio, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = offline ? 0.6 : 0.75 + 0.25 * at;
        ctx.stroke();
      }

      // ---- núcleo ----
      var corEstado = offline
        ? corErro
        : estado === "listening"
          ? cor(c, "ouvindo")
          : estado === "speaking"
            ? cor(c, "falando")
            : cor(c, "pensando");
      var resp = 1 + 0.06 * Math.sin(t * ((Math.PI * 2) / 3) * (offline ? 0.3 : 1));
      if (estado === "speaking" || estado === "listening") resp += nivel * 0.08;
      ctx.globalAlpha = offline ? 0.5 : 0.8 + 0.2 * mist;
      ctx.fillStyle = gradNucleo(ctx, corEstado, offline ? corErro : cor(c, "ouvindo"));
      ctx.beginPath();
      ctx.arc(0, 0, 110 * (0.95 + 0.05 * resp), 0, Math.PI * 2);
      ctx.fill();

      ctx.save();
      ctx.scale(resp, resp);
      ctx.globalAlpha = 1;
      ctx.fillStyle = corFundo;
      ctx.beginPath();
      ctx.arc(0, 0, 58, 0, Math.PI * 2);
      ctx.fill();
      // borda em degradê ciano -> violeta -> âmbar (com brilho moderado)
      ctx.strokeStyle = offline
        ? corErro
        : gradBorda(ctx, cor(c, "ouvindo"), cor(c, "pensando"), cor(c, "falando"));
      ctx.globalAlpha = 0.25;
      ctx.lineWidth = 7;
      ctx.beginPath();
      ctx.arc(0, 0, 58, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.lineWidth = 2.5;
      ctx.stroke();
      ctx.setLineDash(TRACO_NUCLEO);
      ctx.lineDashOffset = giro * 3;
      ctx.strokeStyle = corO1;
      ctx.lineWidth = Math.max(1, linhaMin);
      ctx.globalAlpha = 0.8;
      ctx.beginPath();
      ctx.arc(0, 0, 46, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash(SEM_TRACO);
      ctx.restore();

      // satélites girando em volta do núcleo
      var ag = giro * 0.55;
      var sx = Math.cos(ag) * 70, sy = Math.sin(ag) * 70;
      ctx.fillStyle = offline ? corErro : cor(c, "falando");
      ctx.globalAlpha = 0.3;
      ctx.beginPath();
      ctx.arc(sx, sy, 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(sx, sy, 3.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = offline ? corErro : cor(c, "ouvindo");
      ctx.beginPath();
      ctx.arc(-sx, -sy, 2.5, 0, Math.PI * 2);
      ctx.fill();

      // ---- rótulos ----
      ctx.textBaseline = "alphabetic";
      if (mostraFolhas) {
        ctx.font = "10.5px " + FONTE;
        ctx.fillStyle = cor(c, "texto2");
        for (b = 0; b < n; b++) {
          ctx.globalAlpha = offline ? 0.5 : 0.75 + 0.25 * ativo[b];
          var fl = ramos[b].folhas;
          for (f = 0; f < fl.length; f++) {
            ctx.textAlign = fl[f].alinh;
            ctx.fillText(fl[f].nome, fl[f].tx, fl[f].ty);
          }
        }
      }
      if (mostraNomes) {
        ctx.textAlign = "center";
        ctx.fillStyle = cor(c, "texto");
        for (b = 0; b < n; b++) {
          ctx.globalAlpha = offline ? 0.6 : 0.85 + 0.15 * ativo[b];
          ctx.font = ramos[b].fonte;
          ctx.fillText(ramos[b].nome, ramos[b].x, ramos[b].y + 4);
        }
        ctx.globalAlpha = 1;
        ctx.font = "800 17px " + FONTE;
        ctx.fillText("J A R V I S", 0, 6);
      }
      ctx.restore();
    }

    function evento(e) {
      if (!e || e.tipo !== "tool") return;
      var i = ramoDaFerramenta(e.nome);
      evTempo[i] = 3;
      evErro[i] = e.ok === false ? 1 : 0;
    }

    return { desenhar: desenhar, evento: evento };
  }

  // "#rrggbb" + alfa -> "rgba(...)" (usado só ao criar gradientes, que ficam em cache)
  function hexA(hex, a) {
    var h = String(hex).replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var v = parseInt(h, 16);
    if (!(v >= 0)) v = 0xffffff;
    return "rgba(" + ((v >> 16) & 255) + "," + ((v >> 8) & 255) + "," + (v & 255) + "," + a + ")";
  }

  window.JarvisVisuais.registrar({
    id: "mapa",
    nome: "Mapa Mental",
    descricao: "Núcleo com ramos vivos que acendem conforme o que o Jarvis faz.",
    paleta: "aurora",
    hud: true,
    criar: criar,
  });
})();
