/* Visual "esfera" — Esfera Holográfica dourada (paleta aurora).
 * Meridianos em 3 grupos girando em 3D (projeção ortográfica leve), anéis de latitude,
 * duas faixas giroscópio tracejadas, filamentos de energia piscando, faíscas na casca e
 * um "olho" central que respira. Caixa de referência 680x580, raio 235.
 */
(function () {
  "use strict";

  var OURO_CLARO = "#FFE3A3";
  var AMBAR_PADRAO = "#FFB23F";
  var R = 235;
  var CAIXA_L = 600;
  var CAIXA_A = 590;
  var GRAU = Math.PI / 180;

  // quadros-chave do piscar dos filamentos (fração, opacidade)
  var FLK_T = [0, 0.1, 0.14, 0.18, 0.4, 1];
  var FLK_V = [0.05, 1, 0.3, 0.9, 0.1, 0.05];
  function piscar(f) {
    f = f - Math.floor(f);
    for (var i = 1; i < FLK_T.length; i++) {
      if (f <= FLK_T[i]) {
        var u = (f - FLK_T[i - 1]) / (FLK_T[i] - FLK_T[i - 1]);
        return FLK_V[i - 1] + (FLK_V[i] - FLK_V[i - 1]) * u;
      }
    }
    return FLK_V[0];
  }

  function rnd(semente) {
    var s = semente >>> 0;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }

  function hexA(hex, a) {
    var h = String(hex).replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var v = parseInt(h, 16);
    if (!(v >= 0)) v = 0xffffff;
    return "rgba(" + ((v >> 16) & 255) + "," + ((v >> 8) & 255) + "," + (v & 255) + "," + a + ")";
  }

  function criar() {
    var r = rnd(77);

    // meridianos: 3 grupos x 6
    var NM = 18;
    var merOpac = new Float32Array(NM);
    var merLarg = new Float32Array(NM);
    for (var i = 0; i < NM; i++) {
      merOpac[i] = 0.35 + r() * 0.5;
      merLarg[i] = i % 3 === 0 ? 1.4 : 0.8;
    }
    var GRUPO_GIRO = [0.32, -0.21, 0.12]; // rad/s do giro 3D em torno do eixo do grupo
    var GRUPO_DERIVA = [(Math.PI * 2) / 44, -(Math.PI * 2) / 68, (Math.PI * 2) / 120]; // giro 2D lento

    var LATS = [-60, -35, -12, 12, 35, 60];

    // filamentos: 26 polilinhas de 8 pontos (coordenadas locais)
    var NF = 26;
    var fil = new Float32Array(NF * 16);
    var filFase = new Float32Array(NF);
    var filVel = new Float32Array(NF);
    for (i = 0; i < NF; i++) {
      var a = r() * Math.PI * 2;
      var r0 = 40 + r() * 80, r1 = 150 + r() * (R - 150);
      for (var s = 0; s < 8; s++) {
        var rr = r0 + ((r1 - r0) * s) / 7;
        var aa = a + (r() - 0.5) * 0.24 + s * 0.03;
        fil[i * 16 + s * 2] = Math.cos(aa) * rr;
        fil[i * 16 + s * 2 + 1] = Math.sin(aa) * rr;
      }
      filFase[i] = r();
      filVel[i] = 1 / (2 + r() * 2);
    }

    // faíscas: pontos numa casca 3D (raio relativo 0.55..1), girando
    var NS = 120;
    var fx = new Float32Array(NS), fy = new Float32Array(NS), fz = new Float32Array(NS);
    var fr = new Float32Array(NS), ff = new Float32Array(NS), fc = new Uint8Array(NS);
    for (i = 0; i < NS; i++) {
      var u = r() * 2 - 1, th = r() * Math.PI * 2;
      var rad = Math.sqrt(0.3 + r() * 0.7);
      var sq = Math.sqrt(1 - u * u);
      fx[i] = Math.cos(th) * sq * rad;
      fy[i] = u * rad;
      fz[i] = Math.sin(th) * sq * rad;
      fr[i] = 0.6 + r() * 1.4;
      ff[i] = r() * 6.28;
      fc[i] = r() < 0.4 ? 1 : 0;
    }

    var TRACO_GIRO1 = [90, 18, 6, 18];
    var TRACO_GIRO2 = [4, 8];
    var TRACO_OLHO = [3, 5];
    var SEM_TRACO = [];

    var giro = 0, deriva = 0, pisca = 0, tAnt = -1;
    var grads = {};

    function gradOuro(ctx, raio, c1, c2, fundo) {
      var k = raio + c1 + c2;
      var g = grads[k];
      if (!g) {
        g = ctx.createRadialGradient(0, 0, 0, 0, 0, raio);
        g.addColorStop(0, hexA(c1, 0.9));
        g.addColorStop(0.25, hexA(c2, 0.35));
        g.addColorStop(1, hexA(fundo, 0));
        grads[k] = g;
      }
      return g;
    }

    function desenhar(ctx, q) {
      var t = q.t || 0;
      var dt = q.dt;
      if (!(dt >= 0)) dt = tAnt < 0 ? 0 : Math.max(0, Math.min(0.1, t - tAnt));
      tAnt = t;
      var c = q.cores || {};
      var estado = q.estado || "idle";
      var nivel = q.nivel || 0;
      var agit = q.agitacao == null ? 0.15 : q.agitacao;
      var mist = q.mistura || 0;
      var offline = estado === "offline";
      var previa = !!q.previa;
      var falando = estado === "speaking";

      var ambar = c.falando || c.destaque || AMBAR_PADRAO;
      var ouro = OURO_CLARO;
      if (offline) ambar = ouro = c.erro || "#FF5C7A";
      var acento = offline
        ? ambar
        : estado === "listening"
          ? c.ouvindo || c.primaria || ambar
          : estado === "thinking"
            ? c.pensando || c.escura || ambar
            : ambar;
      var fundo = c.fundo || "#05070F";

      var velo = offline ? 0.04 : 0.3 + agit * 1.7;
      giro += dt * velo;
      deriva += dt * (offline ? 0.05 : 0.5 + agit);
      pisca += dt * (offline ? 0.1 : 0.6 + agit * 1.4 + (falando ? nivel * 1.5 : 0));
      var brilho = offline ? 0.45 : 0.78 + 0.12 * mist + (falando ? 0.1 * nivel : 0);

      var x = q.x || 0, y = q.y || 0, w = q.w || 680, h = q.h || 580;
      var esc = Math.min(w / CAIXA_L, h / CAIXA_A);
      if (!(esc > 0)) return;
      var linhaMin = 0.55 / esc;

      ctx.save();
      ctx.translate(x + w / 2, y + h / 2);
      ctx.scale(esc, esc);
      ctx.lineCap = "round";

      // halo âmbar
      ctx.globalAlpha = (offline ? 0.2 : 0.3 + 0.15 * mist) + (falando ? 0.25 * nivel : 0);
      ctx.fillStyle = gradOuro(ctx, R + 30, ouro, ambar, fundo);
      ctx.beginPath();
      ctx.arc(0, 0, R + 30, 0, Math.PI * 2);
      ctx.fill();

      // ---- meridianos (grandes círculos girando em 3D) ----
      ctx.strokeStyle = ambar;
      for (var g = 0; g < 3; g++) {
        var tauBase = g * 38 * GRAU + deriva * GRUPO_DERIVA[g];
        for (var k = 0; k < 6; k++) {
          var idx = g * 6 + k;
          var phi = (k * 30 + g * 10) * GRAU + giro * GRUPO_GIRO[g] * 3;
          var cphi = Math.cos(phi), sphi = Math.sin(phi);
          var rx = R * Math.abs(cphi);
          if (rx < 0.5) rx = 0.5;
          var tau = tauBase + k * 4 * GRAU;
          // metade da frente: alfa em (-90°, 90°) se sin(2phi) > 0, senão a outra metade
          var ini = sphi * cphi >= 0 ? -Math.PI / 2 : Math.PI / 2;
          ctx.lineWidth = Math.max(merLarg[idx], linhaMin);
          ctx.globalAlpha = merOpac[idx] * brilho;
          ctx.beginPath();
          ctx.ellipse(0, 0, rx, R, tau, ini, ini + Math.PI);
          ctx.stroke();
          if (!previa) {
            ctx.globalAlpha = merOpac[idx] * brilho * 0.35;
            ctx.beginPath();
            ctx.ellipse(0, 0, rx, R, tau, ini + Math.PI, ini + Math.PI * 2);
            ctx.stroke();
          }
        }
      }

      // ---- anéis de latitude ----
      ctx.lineWidth = Math.max(0.7, linhaMin);
      for (var li = 0; li < LATS.length; li++) {
        var lat = LATS[li] * GRAU;
        var ly = R * Math.sin(lat);
        var lrx = R * Math.cos(lat);
        ctx.globalAlpha = 0.45 * brilho;
        ctx.beginPath();
        ctx.ellipse(0, ly, lrx, lrx * 0.18, 0, 0, Math.PI);
        ctx.stroke();
        ctx.globalAlpha = 0.2 * brilho;
        ctx.beginPath();
        ctx.ellipse(0, ly, lrx, lrx * 0.18, 0, Math.PI, Math.PI * 2);
        ctx.stroke();
      }
      // contorno da casca
      ctx.globalAlpha = 0.55 * brilho;
      ctx.lineWidth = Math.max(1.2, linhaMin);
      ctx.beginPath();
      ctx.arc(0, 0, R, 0, Math.PI * 2);
      ctx.stroke();

      // ---- faixas giroscópio ----
      ctx.save();
      ctx.rotate(-18 * GRAU - deriva * ((Math.PI * 2) / 68));
      ctx.setLineDash(TRACO_GIRO1);
      ctx.lineDashOffset = -giro * 40;
      ctx.strokeStyle = ouro;
      ctx.globalAlpha = 0.18 * brilho;
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.ellipse(0, 0, R + 18, 70, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 0.95 * brilho;
      ctx.lineWidth = 2.4;
      ctx.stroke();
      ctx.restore();

      ctx.save();
      ctx.rotate(32 * GRAU + deriva * ((Math.PI * 2) / 44));
      ctx.setLineDash(TRACO_GIRO2);
      ctx.lineDashOffset = giro * 25;
      ctx.strokeStyle = ambar;
      ctx.globalAlpha = 0.85 * brilho;
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.ellipse(0, 0, R - 30, 48, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
      ctx.setLineDash(SEM_TRACO);

      // ---- filamentos de energia ----
      ctx.save();
      ctx.rotate(deriva * ((Math.PI * 2) / 120));
      ctx.strokeStyle = ouro;
      ctx.lineJoin = "round";
      var forca = offline ? 0.25 : falando ? 0.55 + 0.6 * nivel : estado === "thinking" ? 0.95 : 0.7;
      var nf = previa ? 12 : NF;
      for (var fi = 0; fi < nf; fi++) {
        var op = piscar(pisca * filVel[fi] * 1.3 + filFase[fi]) * forca;
        if (op < 0.04) continue;
        var o = fi * 16;
        for (var passe = 0; passe < 2; passe++) {
          ctx.globalAlpha = Math.min(1, op * (passe === 0 ? 0.25 : 1));
          ctx.lineWidth = passe === 0 ? 4.5 : Math.max(1.1, linhaMin);
          ctx.beginPath();
          ctx.moveTo(fil[o], fil[o + 1]);
          for (var s2 = 1; s2 < 8; s2++) ctx.lineTo(fil[o + s2 * 2], fil[o + s2 * 2 + 1]);
          ctx.stroke();
        }
      }
      ctx.restore();

      // ---- faíscas na casca (rotação 3D em torno de eixo inclinado) ----
      var ang = giro * 0.9;
      var ca = Math.cos(ang), sa = Math.sin(ang);
      var ct = Math.cos(0.35), st = Math.sin(0.35);
      var ns = previa ? 50 : NS;
      for (var cor2 = 0; cor2 < 2; cor2++) {
        ctx.fillStyle = cor2 ? ouro : ambar;
        for (i = 0; i < ns; i++) {
          if (fc[i] !== cor2) continue;
          var px = fx[i] * ca + fz[i] * sa;
          var pz = -fx[i] * sa + fz[i] * ca;
          var py = fy[i] * ct - pz * st;
          pz = fy[i] * st + pz * ct;
          var prof = 0.45 + 0.55 * (pz * 0.5 + 0.5);
          var bl = 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * (2.6 + agit * 3) + ff[i]));
          ctx.globalAlpha = bl * prof * brilho;
          var raio = fr[i] * (0.7 + 0.3 * prof);
          ctx.beginPath();
          ctx.arc(px * R, py * R, raio, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      // ---- olho central ----
      var resp = 1 + 0.06 * Math.sin(t * ((Math.PI * 2) / 3) * (offline ? 0.2 : 1 + agit));
      if (falando) resp += nivel * 0.22;
      else if (estado === "listening") resp += nivel * 0.1;
      ctx.save();
      ctx.scale(resp, resp);
      ctx.globalAlpha = offline ? 0.5 : 0.9 + (falando ? 0.1 * nivel : 0);
      ctx.fillStyle = gradOuro(ctx, 56, ouro, ambar, fundo);
      ctx.beginPath();
      ctx.arc(0, 0, 56, 0, Math.PI * 2);
      ctx.fill();
      ctx.setLineDash(TRACO_OLHO);
      ctx.lineDashOffset = -giro * 12;
      ctx.strokeStyle = acento;
      ctx.lineWidth = Math.max(1, linhaMin);
      ctx.globalAlpha = 0.9;
      ctx.beginPath();
      ctx.arc(0, 0, 44, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash(SEM_TRACO);
      ctx.strokeStyle = ouro;
      ctx.globalAlpha = 1;
      ctx.lineWidth = 2.4;
      if (!previa) {
        ctx.shadowColor = ambar;
        ctx.shadowBlur = 10 * esc + (falando ? 8 * nivel * esc : 0);
      }
      ctx.beginPath();
      ctx.arc(0, 0, 30, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = ouro;
      ctx.beginPath();
      ctx.arc(0, 0, 9, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      ctx.restore();
    }

    return { desenhar: desenhar };
  }

  window.JarvisVisuais.registrar({
    id: "esfera",
    nome: "Esfera Holográfica",
    descricao: "Esfera dourada de meridianos girando, com filamentos de energia.",
    paleta: "aurora",
    hud: true,
    criar: criar,
  });
})();
