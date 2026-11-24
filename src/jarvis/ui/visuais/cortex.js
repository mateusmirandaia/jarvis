// Visual "Córtex Neural": cérebro visto de cima, dois hemisférios de neurônios ligados,
// pulsos (sinapses) correndo pelas ligações. Canvas 2D puro.
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

  // ---------- geometria (unidades da caixa do mockup 600x560, centro em 0,0)
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

  JarvisVisuais.registrar({
    id: "cortex",
    nome: "Córtex Neural",
    descricao: "Cérebro de neurônios visto de cima, com sinapses disparando.",
    paleta: "petroleo",
    hud: true,
    criar: function () {
      var N = 230;
      var P = pontosCerebro(N, 3);
      var E = ligacoes(P, 3);
      var rnd = aleatorio(4);
      var raio = new Float32Array(N);
      var quente = new Uint8Array(N);
      var fase = new Float32Array(N);
      for (var i = 0; i < N; i++) {
        raio[i] = 1.2 + rnd() * 1.6;
        quente[i] = rnd() < 0.22 ? 1 : 0;
        fase[i] = rnd() * Math.PI * 2;
      }
      var lados = [contorno(-1), contorno(1)];
      var sulcos = giros(-1, 2).concat(giros(1, 4));
      var flash = new Float32Array(N); // brilho de chegada da sinapse

      // pulsos: lista fixa reciclada
      var MAXP = 90;
      var pAresta = new Int16Array(MAXP);
      var pDir = new Int8Array(MAXP);
      var pProg = new Float32Array(MAXP);
      var pVel = new Float32Array(MAXP);
      var pVivo = new Uint8Array(MAXP);
      var pSaltos = new Int8Array(MAXP);

      var est = { tempo: 0, off: 0, acum: 0, gradK: -1, grad: null, gradX: 0, gradY: 0, gradCor: "" };

      function soltar(k, aresta, dir) {
        pAresta[k] = aresta;
        pDir[k] = dir;
        pProg[k] = -0.4;
        pVel[k] = 0.9 + rnd() * 0.8;
        pVivo[k] = 1;
      }
      function novoPulso() {
        for (var k = 0; k < MAXP; k++) {
          if (!pVivo[k]) {
            soltar(k, (rnd() * E.n) | 0, rnd() < 0.5 ? 1 : -1);
            pSaltos[k] = (rnd() * 3) | 0;
            return;
          }
        }
      }

      return {
        desenhar: function (ctx, q) {
          var cores = q.cores || PADRAO;
          var cPri = cores.primaria || PADRAO.primaria;
          var cEsc = cores.escura || PADRAO.escura;
          var cDes = cores.destaque || PADRAO.destaque;
          var cErr = cores.erro || PADRAO.erro;
          var dt = Math.min(0.1, Math.max(0, q.dt || 0));
          var estado = q.estado || "idle";
          var nivel = Math.max(0, Math.min(1, q.nivel || 0));
          var mist = q.mistura || 0;
          var agit = q.agitacao == null ? 0.15 : q.agitacao;
          var previa = !!q.previa;

          est.off = suave(est.off, estado === "offline" ? 1 : 0, dt, 3);
          var off = est.off;
          var falando = estado === "speaking";
          var ouvindo = estado === "listening";
          var pensando = estado === "thinking";

          // cores efetivas
          var corP = mistura(cPri, cErr, off * 0.85);
          var corE = mistura(cEsc, cErr, off * 0.45);
          var corD = mistura(cDes, cErr, off);
          var vel = (0.35 + agit * 1.7) * (1 - off * 0.92);
          est.tempo += dt * vel;
          var T = est.tempo;

          // escala: caixa 600x560 do mockup
          var k = Math.min(q.w, q.h) / 560;
          var cx = q.x + q.w / 2;
          var cy = q.y + q.h / 2;
          var resp = 1 + Math.sin(T * 1.6) * 0.008 + (ouvindo ? nivel * 0.025 : 0) + (falando ? nivel * 0.03 : 0);

          // ----- pulsos: quantos e quão rápidos
          var alvo;
          if (off > 0.5) alvo = 2;
          else if (pensando) alvo = 70;
          else if (falando) alvo = 18 + nivel * 60;
          else if (ouvindo) alvo = 12 + nivel * 45;
          else alvo = 9;
          if (previa) alvo *= 0.6;
          var velP = (pensando ? 3.4 : falando ? 1.5 + nivel * 2.5 : ouvindo ? 1.2 + nivel * 1.5 : 0.8) * (1 - off * 0.85);
          var vivos = 0;
          for (var j = 0; j < MAXP; j++) vivos += pVivo[j];
          est.acum += dt * Math.max(0, alvo - vivos) * 3;
          while (est.acum >= 1) {
            est.acum -= 1;
            novoPulso();
          }
          for (j = 0; j < MAXP; j++) {
            if (!pVivo[j]) continue;
            pProg[j] += dt * velP * pVel[j];
            if (pProg[j] >= 1) {
              var a0 = E.a[pAresta[j]];
              var b0 = E.b[pAresta[j]];
              var fim = pDir[j] > 0 ? b0 : a0;
              flash[fim] = 1;
              // propaga para uma ligação vizinha (cadeia de sinapses)
              if (pSaltos[j] > 0 && E.adj[fim].length > 1) {
                var lista = E.adj[fim];
                var prox = lista[(rnd() * lista.length) | 0];
                if (prox === pAresta[j]) prox = lista[(lista.indexOf(prox) + 1) % lista.length];
                pSaltos[j]--;
                var sj = pSaltos[j];
                soltar(j, prox, E.a[prox] === fim ? 1 : -1);
                pSaltos[j] = sj;
                pProg[j] = 0;
              } else {
                pVivo[j] = 0;
              }
            }
          }
          var decai = Math.min(1, dt * 2.5);
          for (i = 0; i < N; i++) if (flash[i] > 0) flash[i] = Math.max(0, flash[i] - decai);

          ctx.save();
          ctx.translate(cx, cy);
          ctx.scale(k * resp, k * resp);
          ctx.lineCap = "round";
          ctx.lineJoin = "round";

          // ----- halo (gradiente em cache)
          var corHalo = mistura(corP, corD, falando ? 0.35 + nivel * 0.5 : mist * 0.3);
          if (!est.grad || est.gradCor !== corHalo) {
            est.grad = ctx.createRadialGradient(0, 0, 0, 0, 0, 260);
            est.grad.addColorStop(0, rgba(corHalo, 0.24));
            est.grad.addColorStop(0.55, rgba(corHalo, 0.07));
            est.grad.addColorStop(1, rgba(corHalo, 0));
            est.gradCor = corHalo;
          }
          var aHalo = 0.55 + mist * 0.25 + (falando ? nivel * 0.5 : 0) + (ouvindo ? nivel * 0.3 : 0);
          ctx.globalAlpha = Math.min(1, aHalo) * (1 - off * 0.5);
          ctx.fillStyle = est.grad;
          ctx.beginPath();
          ctx.ellipse(0, 0, 260, 250, 0, 0, Math.PI * 2);
          ctx.fill();

          // ----- contorno dos hemisférios (brilho = traço largo translúcido + traço fino)
          var vivo = 0.55 + (ouvindo ? 0.15 + nivel * 0.3 : 0) + mist * 0.2;
          ctx.strokeStyle = corP;
          if (!previa) {
            ctx.globalAlpha = 0.13 * vivo * 1.6;
            ctx.lineWidth = 6;
            ctx.beginPath();
            polilinha(ctx, lados[0], true);
            polilinha(ctx, lados[1], true);
            ctx.stroke();
          }
          ctx.globalAlpha = Math.min(1, vivo);
          ctx.lineWidth = 1.3;
          ctx.beginPath();
          polilinha(ctx, lados[0], true);
          polilinha(ctx, lados[1], true);
          ctx.stroke();

          // fissura longitudinal
          ctx.globalAlpha = 0.35;
          ctx.strokeStyle = corE;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(0, -200);
          ctx.lineTo(0, 205);
          ctx.stroke();

          // ----- sulcos (giros)
          ctx.globalAlpha = 0.6 + mist * 0.15;
          ctx.strokeStyle = corE;
          ctx.lineWidth = 1;
          ctx.beginPath();
          for (i = 0; i < sulcos.length; i++) polilinha(ctx, sulcos[i], false);
          ctx.stroke();

          // ----- ligações
          ctx.globalAlpha = 0.85;
          ctx.strokeStyle = corE;
          ctx.lineWidth = 0.8;
          ctx.beginPath();
          var passo = previa ? 2 : 1;
          for (i = 0; i < E.n; i += passo) {
            var ia = E.a[i];
            var ib = E.b[i];
            ctx.moveTo(P.xs[ia], P.ys[ia]);
            ctx.lineTo(P.xs[ib], P.ys[ib]);
          }
          ctx.stroke();

          // ----- pulsos (segmento que desliza pela ligação)
          var aPulso = (pensando ? 1 : falando ? 0.75 + nivel * 0.25 : ouvindo ? 0.7 + nivel * 0.3 : 0.6) * (1 - off * 0.4);
          for (var passe = 0; passe < (previa ? 1 : 2); passe++) {
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
                var tx = x1;
                var ty = y1;
                x1 = x2;
                y1 = y2;
                x2 = tx;
                y2 = ty;
              }
              var u0 = Math.max(0, pProg[j]);
              var u1 = Math.min(1, pProg[j] + 0.6);
              if (u1 <= u0) continue;
              ctx.moveTo(x1 + (x2 - x1) * u0, y1 + (y2 - y1) * u0);
              ctx.lineTo(x1 + (x2 - x1) * u1, y1 + (y2 - y1) * u1);
            }
            ctx.strokeStyle = corD;
            if (passe === 0 && !previa) {
              ctx.globalAlpha = 0.22 * aPulso;
              ctx.lineWidth = 6;
            } else {
              ctx.globalAlpha = aPulso;
              ctx.lineWidth = 2.2;
            }
            ctx.stroke();
          }

          // ----- neurônios comuns (um caminho só)
          ctx.globalAlpha = 0.9;
          ctx.fillStyle = corP;
          ctx.beginPath();
          for (i = 0; i < N; i += passo) {
            if (quente[i] || flash[i] > 0.05) continue;
            ctx.moveTo(P.xs[i] + raio[i], P.ys[i]);
            ctx.arc(P.xs[i], P.ys[i], raio[i], 0, Math.PI * 2);
          }
          ctx.fill();

          // ----- neurônios quentes (piscam em destaque) e os que receberam sinapse
          ctx.fillStyle = corD;
          var velPisca = pensando ? 4.2 : falando ? 2.2 + nivel * 3 : 2.85;
          var base = 0.25 + (falando ? nivel * 0.35 : 0) + (ouvindo ? nivel * 0.25 : 0);
          for (i = 0; i < N; i += passo) {
            var f = flash[i];
            if (!quente[i] && f <= 0.05) continue;
            var al = quente[i] ? base + (1 - base) * (0.5 + 0.5 * Math.sin(T * velPisca + fase[i])) : 0;
            al = Math.max(al, f);
            if (off > 0.5) al *= 0.5;
            var rr = raio[i] * (1 + f * 0.8);
            if (al > 0.6 && !previa) {
              ctx.globalAlpha = (al - 0.6) * 0.4;
              ctx.beginPath();
              ctx.arc(P.xs[i], P.ys[i], rr * 2.1, 0, Math.PI * 2);
              ctx.fill();
            }
            ctx.globalAlpha = al;
            ctx.beginPath();
            ctx.arc(P.xs[i], P.ys[i], rr, 0, Math.PI * 2);
            ctx.fill();
          }

          ctx.restore();
        },
      };
    },
  });
})();
