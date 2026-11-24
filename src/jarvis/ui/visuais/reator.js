// Visual "Reator de Plasma": núcleo com mini-cérebro, anéis tracejados girando em sentidos
// opostos, marcações e raios elétricos. Canvas 2D puro.
(function () {
  "use strict";

  // ---------- utilitários de cor (cache de parse, sem alocar por quadro além de poucas strings)
  var cacheRgb = {};
  function rgb(hex) {
    var c = cacheRgb[hex];
    if (c) return c;
    var h = String(hex || "#000000").replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16) || 0;
    c = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    cacheRgb[hex] = c;
    return c;
  }
  function mistura(a, b, t) {
    if (t <= 0.001) return a;
    if (t >= 0.999) return b;
    var x = rgb(a);
    var y = rgb(b);
    return (
      "rgb(" +
      Math.round(x[0] + (y[0] - x[0]) * t) +
      "," +
      Math.round(x[1] + (y[1] - x[1]) * t) +
      "," +
      Math.round(x[2] + (y[2] - x[2]) * t) +
      ")"
    );
  }
  function rgba(cor, a) {
    var x = cor.charAt(0) === "#" ? rgb(cor) : null;
    if (!x) {
      var m = cor.match(/\d+/g) || [0, 0, 0];
      x = [m[0], m[1], m[2]];
    }
    return "rgba(" + x[0] + "," + x[1] + "," + x[2] + "," + a + ")";
  }
  function aleatorio(semente) {
    var s = semente >>> 0;
    return function () {
      s = (s + 0x6d2b79f5) >>> 0;
      var t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function suave(atual, alvo, dt, vel) {
    return atual + (alvo - atual) * Math.min(1, dt * vel);
  }

  var PADRAO = {
    primaria: "#2FB5A8",
    escura: "#0E5E5A",
    destaque: "#C6F000",
    erro: "#E2483B",
    texto: "#9FB3AF",
    fundo: "#030605",
  };

  function pontosCerebro(n, seed) {
    var rnd = aleatorio(seed);
    var xs = new Float32Array(n);
    var ys = new Float32Array(n);
    var k = 0;
    while (k < n) {
      var lado = rnd() < 0.5 ? -1 : 1;
      var x = rnd() * 2 - 1;
      var y = rnd() * 2 - 1;
      var rx = 0.92 + 0.12 * y; // ovo: mais largo atrás (embaixo)
      if ((x / rx) * (x / rx) + y * y > 1) continue;
      xs[k] = lado * (12 + (x + 1) * 72);
      ys[k] = y * 205;
      k++;
    }
    return { xs: xs, ys: ys, n: n };
  }

  function ligacoes(p, viz) {
    var vistos = {};
    var a = [];
    var b = [];
    var d = new Float32Array(p.n);
    var idx = [];
    for (var i = 0; i < p.n; i++) idx.push(i);
    for (i = 0; i < p.n; i++) {
      for (var j = 0; j < p.n; j++) {
        var dx = p.xs[i] - p.xs[j];
        var dy = p.ys[i] - p.ys[j];
        d[j] = i === j ? 1e12 : dx * dx + dy * dy;
      }
      idx.sort(function (u, v) {
        return d[u] - d[v];
      });
      for (var m = 0; m < viz; m++) {
        var o = idx[m];
        var lo = Math.min(i, o);
        var hi = Math.max(i, o);
        var chave = lo * 10000 + hi;
        if (vistos[chave]) continue;
        vistos[chave] = 1;
        a.push(lo);
        b.push(hi);
      }
    }
    // adjacência: arestas por nó
    var adj = [];
    for (i = 0; i < p.n; i++) adj.push([]);
    for (i = 0; i < a.length; i++) {
      adj[a[i]].push(i);
      adj[b[i]].push(i);
    }
    return { a: Int16Array.from(a), b: Int16Array.from(b), n: a.length, adj: adj };
  }

  function contorno(lado) {
    var pts = [];
    for (var t = 0; t <= 360; t += 6) {
      var ang = (t * Math.PI) / 180;
      var y = Math.sin(ang);
      var x = Math.cos(ang) * (0.92 + 0.12 * y);
      pts.push(lado * (12 + (x + 1) * 72), y * 205);
    }
    return Float32Array.from(pts);
  }

  function giros(lado, seed) {
    var rnd = aleatorio(seed);
    var out = [];
    for (var g = 0; g < 9; g++) {
      var y0 = rnd() * 1.7 - 0.85;
      var caminho = [];
      for (var s = 0; s <= 10; s++) {
        var x = -0.85 + s * 0.17;
        var y = y0 + Math.sin(s * 1.3 + rnd()) * 0.07;
        var rx = 0.92 + 0.12 * y;
        if ((x / rx) * (x / rx) + y * y > 0.9) continue;
        caminho.push(lado * (12 + (x + 1) * 72), y * 205);
      }
      if (caminho.length > 4) out.push(Float32Array.from(caminho));
    }
    return out;
  }

  function polilinha(ctx, arr, fechar) {
    ctx.moveTo(arr[0], arr[1]);
    for (var i = 2; i < arr.length; i += 2) ctx.lineTo(arr[i], arr[i + 1]);
    if (fechar) ctx.closePath();
  }

  function pulsoRaio(arr, rnd, r0, r1, ang) {
    // raio elétrico: 10 pontos com desvio angular aleatório (escreve no array existente)
    for (var s = 0; s <= 9; s++) {
      var rr = r0 + ((r1 - r0) * s) / 9;
      var a = ang + (rnd() * 0.18 - 0.09);
      arr[s * 2] = Math.cos(a) * rr;
      arr[s * 2 + 1] = Math.sin(a) * rr;
    }
  }
  // curva de brilho do raio (como o keyframe "flicker" do mockup), u em 0..1
  function cintila(u) {
    if (u <= 0 || u >= 1) return 0;
    if (u < 0.27) return u / 0.27;
    if (u < 0.4) return 1 - ((u - 0.27) / 0.13) * 0.8;
    if (u < 0.53) return 0.2 + ((u - 0.4) / 0.13) * 0.7;
    return 0.9 * (1 - (u - 0.53) / 0.47);
  }

  JarvisVisuais.registrar({
    id: "reator",
    nome: "Reator de Plasma",
    descricao: "Núcleo de energia com anéis girando e raios elétricos.",
    paleta: "petroleo",
    hud: true,
    criar: function () {
      // mini-cérebro do núcleo
      var N = 120;
      var P = pontosCerebro(N, 5);
      var E = ligacoes(P, 3);
      var lados = [contorno(-1), contorno(1)];
      var sulcos = giros(-1, 4).concat(giros(1, 6));
      var rnd = aleatorio(11);
      var raio = new Float32Array(N);
      var quente = new Uint8Array(N);
      var fase = new Float32Array(N);
      for (var i = 0; i < N; i++) {
        raio[i] = 1.6 + rnd() * 2;
        quente[i] = rnd() < 0.22 ? 1 : 0;
        fase[i] = rnd() * Math.PI * 2;
      }

      // anéis: raio, tracejado, cor ("p" primária, "e" escura, "d" destaque), sentido/período, largura
      var aneis = [
        { r: 255, traco: [2, 6], cor: "p", per: 40, dir: 1, lw: 1 },
        { r: 232, traco: [60, 14, 8, 14], cor: "e", per: 26, dir: -1, lw: 6 },
        { r: 210, traco: [1, 3], cor: "p", per: 9, dir: 1, lw: 1 },
        { r: 186, traco: [120, 30], cor: "d", per: 40, dir: 1, lw: 2 },
        { r: 160, traco: [4, 10], cor: "p", per: 26, dir: -1, lw: 3 },
      ];
      var angAnel = new Float32Array(aneis.length + 1);
      for (i = 0; i < angAnel.length; i++) angAnel[i] = rnd() * Math.PI * 2;
      // marcações do anel externo (72, uma grande a cada 6) — pré-calculadas
      var ticks = new Float32Array(72 * 4);
      for (i = 0; i < 72; i++) {
        var a = (i * 5 * Math.PI) / 180;
        var l1 = i % 6 === 0 ? 262 : 266;
        var l2 = i % 6 === 0 ? 276 : 271;
        ticks[i * 4] = Math.cos(a) * l1;
        ticks[i * 4 + 1] = Math.sin(a) * l1;
        ticks[i * 4 + 2] = Math.cos(a) * l2;
        ticks[i * 4 + 3] = Math.sin(a) * l2;
      }

      // raios elétricos: 10 fixos, reciclados
      var NR = 10;
      var rPts = [];
      var rVida = new Float32Array(NR); // 0..1 enquanto visível; <0 = esperando
      var rDur = new Float32Array(NR);
      var rAng = new Float32Array(NR);
      var rLen = new Float32Array(NR);
      var rTrem = new Float32Array(NR);
      for (i = 0; i < NR; i++) {
        rPts.push(new Float32Array(20));
        rVida[i] = -rnd() * 2.5;
        rDur[i] = 0.9;
        rAng[i] = rnd() * Math.PI * 2;
        rLen[i] = 150 + rnd() * 90;
        pulsoRaio(rPts[i], rnd, 70, rLen[i], rAng[i]);
      }

      // pulsos do mini-cérebro
      var MAXP = 40;
      var pAresta = new Int16Array(MAXP);
      var pDir = new Int8Array(MAXP);
      var pProg = new Float32Array(MAXP);
      var pVivo = new Uint8Array(MAXP);

      var SEM_TRACO = [];
      var est = { tempo: 0, off: 0, acum: 0, grad: null, gradCor: "", gradN: null, gradNCor: "" };

      return {
        desenhar: function (ctx, q) {
          var cores = q.cores || PADRAO;
          var cPri = cores.primaria || PADRAO.primaria;
          var cEsc = cores.escura || PADRAO.escura;
          var cDes = cores.destaque || PADRAO.destaque;
          var cErr = cores.erro || PADRAO.erro;
          var cFun = cores.fundo || PADRAO.fundo;
          var dt = Math.min(0.1, Math.max(0, q.dt || 0));
          var estado = q.estado || "idle";
          var nivel = Math.max(0, Math.min(1, q.nivel || 0));
          var mist = q.mistura || 0;
          var agit = q.agitacao == null ? 0.15 : q.agitacao;
          var previa = !!q.previa;
          var falando = estado === "speaking";
          var ouvindo = estado === "listening";
          var pensando = estado === "thinking";

          est.off = suave(est.off, estado === "offline" ? 1 : 0, dt, 3);
          var off = est.off;
          var corP = mistura(cPri, cErr, off * 0.85);
          var corE = mistura(cEsc, cErr, off * 0.45);
          var corD = mistura(cDes, cErr, off);
          var vel = (0.35 + agit * 1.7) * (1 - off * 0.94);
          est.tempo += dt * vel;
          var T = est.tempo;

          // giro dos anéis: thinking acelera bastante
          var giro = (0.6 + agit * 2.6 + (falando ? nivel * 0.8 : 0)) * (1 - off * 0.95);
          for (i = 0; i < aneis.length; i++) {
            angAnel[i] += ((dt * Math.PI * 2) / aneis[i].per) * aneis[i].dir * giro;
          }
          angAnel[aneis.length] -= ((dt * Math.PI * 2) / 26) * giro;

          // raios: frequência por estado
          var espera;
          if (off > 0.5) espera = 6;
          else if (falando) espera = 1.1 - nivel * 0.95;
          else if (pensando) espera = 0.8;
          else if (ouvindo) espera = 2 - nivel * 1.2;
          else espera = 2.6;
          for (i = 0; i < NR; i++) {
            if (rVida[i] < 0) {
              rVida[i] += dt;
              if (rVida[i] >= 0) {
                rAng[i] = rnd() * Math.PI * 2;
                rLen[i] = (150 + rnd() * 90) * (falando ? 0.9 + nivel * 0.2 : 1);
                rDur[i] = pensando ? 0.5 : falando ? 0.45 + rnd() * 0.3 : 0.9;
                pulsoRaio(rPts[i], rnd, 70, rLen[i], rAng[i]);
              }
            } else {
              rVida[i] += dt / rDur[i];
              rTrem[i] += dt;
              if (rTrem[i] > 0.07) {
                rTrem[i] = 0;
                pulsoRaio(rPts[i], rnd, 70, rLen[i], rAng[i]);
              }
              if (rVida[i] >= 1) rVida[i] = -(espera * (0.3 + rnd() * 1.4));
            }
          }

          // pulsos do mini-cérebro
          var alvo = off > 0.5 ? 1 : pensando ? 34 : falando ? 10 + nivel * 26 : ouvindo ? 8 + nivel * 20 : 6;
          if (previa) alvo *= 0.6;
          var velP = (pensando ? 3.2 : falando ? 1.4 + nivel * 2.4 : ouvindo ? 1.2 + nivel * 1.2 : 0.8) * (1 - off * 0.85);
          var vivos = 0;
          for (var j = 0; j < MAXP; j++) vivos += pVivo[j];
          est.acum += dt * Math.max(0, alvo - vivos) * 3;
          while (est.acum >= 1) {
            est.acum -= 1;
            for (j = 0; j < MAXP; j++) {
              if (!pVivo[j]) {
                pVivo[j] = 1;
                pAresta[j] = (rnd() * E.n) | 0;
                pDir[j] = rnd() < 0.5 ? 1 : -1;
                pProg[j] = -0.6;
                break;
              }
            }
          }
          for (j = 0; j < MAXP; j++) {
            if (!pVivo[j]) continue;
            pProg[j] += dt * velP;
            if (pProg[j] >= 1) pVivo[j] = 0;
          }

          var k = Math.min(q.w, q.h) / 560;
          var cx = q.x + q.w / 2;
          var cy = q.y + q.h / 2;

          ctx.save();
          ctx.translate(cx, cy);
          ctx.scale(k, k);
          ctx.lineCap = "round";
          ctx.lineJoin = "round";

          // ----- halo
          var corHalo = mistura(corP, corD, falando ? 0.3 + nivel * 0.55 : mist * 0.35);
          if (!est.grad || est.gradCor !== corHalo) {
            est.grad = ctx.createRadialGradient(0, 0, 40, 0, 0, 275);
            est.grad.addColorStop(0, rgba(corHalo, 0.26));
            est.grad.addColorStop(0.5, rgba(corHalo, 0.08));
            est.grad.addColorStop(1, rgba(corHalo, 0));
            est.gradCor = corHalo;
          }
          ctx.globalAlpha = Math.min(1, 0.6 + mist * 0.2 + (falando ? nivel * 0.45 : 0) + (ouvindo ? nivel * 0.3 : 0)) * (1 - off * 0.5);
          ctx.fillStyle = est.grad;
          ctx.beginPath();
          ctx.arc(0, 0, 275, 0, Math.PI * 2);
          ctx.fill();

          // ----- anéis tracejados
          var vivoAnel = 0.7 + mist * 0.15 + (ouvindo ? nivel * 0.25 : 0);
          for (i = 0; i < aneis.length; i++) {
            var an = aneis[i];
            if (previa && i === 2) continue;
            ctx.save();
            ctx.rotate(angAnel[i]);
            ctx.setLineDash(an.traco);
            ctx.strokeStyle = an.cor === "p" ? corP : an.cor === "e" ? corE : corD;
            ctx.lineWidth = an.lw;
            var al = 0.85 * vivoAnel;
            if (an.cor === "d") al = (0.45 + mist * 0.35 + (falando ? nivel * 0.3 : 0)) * (1 - off * 0.3);
            ctx.globalAlpha = Math.min(1, al);
            var rr = an.r * (1 + (ouvindo || falando ? nivel * 0.012 * Math.sin(T * 3 + i) : 0));
            ctx.beginPath();
            ctx.arc(0, 0, rr, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
          ctx.setLineDash(SEM_TRACO);

          // ----- marcações girando
          ctx.save();
          ctx.rotate(angAnel[aneis.length]);
          ctx.strokeStyle = corP;
          ctx.lineWidth = 1.2;
          ctx.globalAlpha = 0.75 * vivoAnel;
          ctx.beginPath();
          for (i = 0; i < 72; i++) {
            ctx.moveTo(ticks[i * 4], ticks[i * 4 + 1]);
            ctx.lineTo(ticks[i * 4 + 2], ticks[i * 4 + 3]);
          }
          ctx.stroke();
          ctx.restore();

          // ----- raios elétricos
          ctx.strokeStyle = corD;
          for (var passe = 0; passe < (previa ? 1 : 2); passe++) {
            for (i = 0; i < NR; i++) {
              if (rVida[i] < 0) continue;
              var b = cintila(rVida[i]);
              if (b <= 0.02) continue;
              var arr = rPts[i];
              if (passe === 0 && !previa) {
                ctx.globalAlpha = b * 0.22;
                ctx.lineWidth = 6;
              } else {
                ctx.globalAlpha = b;
                ctx.lineWidth = 1.6;
              }
              ctx.beginPath();
              ctx.moveTo(arr[0], arr[1]);
              for (var s = 2; s < 20; s += 2) ctx.lineTo(arr[s], arr[s + 1]);
              ctx.stroke();
            }
          }

          // ----- núcleo (respira; ao falar pulsa com o nível)
          var resp = 1 + Math.sin(T * 2.24) * 0.04 + (falando ? nivel * 0.09 : 0) + (ouvindo ? nivel * 0.04 : 0);
          ctx.save();
          ctx.scale(resp, resp);
          var corNucleo = mistura(cFun, corE, 0.22);
          if (!est.gradN || est.gradNCor !== corNucleo + corD) {
            est.gradN = ctx.createRadialGradient(0, 0, 0, 0, 0, 118);
            est.gradN.addColorStop(0, rgba(corE, 0.4));
            est.gradN.addColorStop(0.6, corNucleo);
            est.gradN.addColorStop(0.9, corNucleo);
            est.gradN.addColorStop(1, rgba(mistura(corNucleo, corD, 0.25), 1));
            est.gradNCor = corNucleo + corD;
          }
          ctx.globalAlpha = 1;
          ctx.fillStyle = est.gradN;
          ctx.beginPath();
          ctx.arc(0, 0, 118, 0, Math.PI * 2);
          ctx.fill();
          var aBorda = (0.65 + mist * 0.2 + (falando ? nivel * 0.35 : 0)) * (1 - off * 0.3);
          ctx.strokeStyle = corD;
          if (!previa) {
            ctx.globalAlpha = aBorda * 0.25;
            ctx.lineWidth = 7;
            ctx.stroke();
          }
          ctx.globalAlpha = Math.min(1, aBorda);
          ctx.lineWidth = 1.5;
          ctx.stroke();

          // mini-cérebro
          ctx.translate(0, 4);
          ctx.scale(0.52, 0.5);
          ctx.strokeStyle = corP;
          ctx.globalAlpha = 0.6;
          ctx.lineWidth = 2;
          ctx.beginPath();
          polilinha(ctx, lados[0], true);
          polilinha(ctx, lados[1], true);
          ctx.stroke();
          if (!previa) {
            ctx.strokeStyle = corE;
            ctx.globalAlpha = 0.7;
            ctx.lineWidth = 1.8;
            ctx.beginPath();
            for (i = 0; i < sulcos.length; i++) polilinha(ctx, sulcos[i], false);
            ctx.stroke();
          }
          ctx.strokeStyle = corE;
          ctx.globalAlpha = 0.9;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          for (i = 0; i < E.n; i++) {
            ctx.moveTo(P.xs[E.a[i]], P.ys[E.a[i]]);
            ctx.lineTo(P.xs[E.b[i]], P.ys[E.b[i]]);
          }
          ctx.stroke();
          // pulsos
          ctx.strokeStyle = corD;
          ctx.lineWidth = 3.6;
          ctx.globalAlpha = (pensando ? 1 : 0.6 + mist * 0.3 + nivel * 0.2) * (1 - off * 0.4);
          ctx.beginPath();
          for (j = 0; j < MAXP; j++) {
            if (!pVivo[j]) continue;
            var ea = E.a[pAresta[j]];
            var eb = E.b[pAresta[j]];
            var x1 = P.xs[ea];
            var y1 = P.ys[ea];
            var x2 = P.xs[eb];
            var y2 = P.ys[eb];
            if (pDir[j] < 0) {
              x1 = P.xs[eb];
              y1 = P.ys[eb];
              x2 = P.xs[ea];
              y2 = P.ys[ea];
            }
            var u0 = Math.max(0, pProg[j]);
            var u1 = Math.min(1, pProg[j] + 0.6);
            if (u1 <= u0) continue;
            ctx.moveTo(x1 + (x2 - x1) * u0, y1 + (y2 - y1) * u0);
            ctx.lineTo(x1 + (x2 - x1) * u1, y1 + (y2 - y1) * u1);
          }
          ctx.stroke();
          // neurônios
          ctx.fillStyle = corP;
          ctx.globalAlpha = 0.9;
          ctx.beginPath();
          for (i = 0; i < N; i++) {
            if (quente[i]) continue;
            ctx.moveTo(P.xs[i] + raio[i], P.ys[i]);
            ctx.arc(P.xs[i], P.ys[i], raio[i], 0, Math.PI * 2);
          }
          ctx.fill();
          ctx.fillStyle = corD;
          var vp = pensando ? 5 : falando ? 2.5 + nivel * 3 : 2.85;
          var base = 0.25 + (falando ? nivel * 0.4 : 0);
          for (i = 0; i < N; i++) {
            if (!quente[i]) continue;
            ctx.globalAlpha = (base + (1 - base) * (0.5 + 0.5 * Math.sin(T * vp + fase[i]))) * (off > 0.5 ? 0.5 : 1);
            ctx.beginPath();
            ctx.arc(P.xs[i], P.ys[i], raio[i], 0, Math.PI * 2);
            ctx.fill();
          }
          ctx.restore();

          ctx.restore();
        },
      };
    },
  });
})();
