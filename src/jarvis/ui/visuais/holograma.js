// Visual "Holograma": cérebro/cabeça em 26 fatias horizontais com pontos, meridianos,
// linha de varredura e projetor no chão. Canvas 2D puro.
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

  JarvisVisuais.registrar({
    id: "holograma",
    nome: "Holograma",
    descricao: "Cérebro holográfico em 26 fatias com varredura de ressonância.",
    paleta: "petroleo",
    hud: true,
    criar: function () {
      var rnd = aleatorio(21);
      var NF = 26;
      var TOPO = -230;
      var BASE = 240;
      var fy = new Float32Array(NF);
      var fw = new Float32Array(NF);
      var fDest = new Uint8Array(NF);
      for (var i = 0; i < NF; i++) {
        var t = i / (NF - 1);
        fy[i] = TOPO + t * (BASE - TOPO);
        var w;
        if (t < 0.78) {
          var u = (t / 0.78) * 2 - 1;
          w = 235 * Math.sqrt(Math.max(0, 1 - u * u)) * (1 - 0.1 * u);
        } else {
          w = 40 - (t - 0.78) * 60; // tronco cerebral
        }
        fw[i] = Math.max(w, 14);
        fDest[i] = i % 5 === 2 ? 1 : 0;
      }
      // pontos nas fatias (ângulo fixo; giram juntos)
      var lf = [];
      var la = [];
      var lr = [];
      var lq = [];
      var lp = [];
      for (i = 0; i < NF; i++) {
        var nd = Math.floor(fw[i] / 14) + 1;
        for (var d = 0; d < nd; d++) {
          lf.push(i);
          la.push(rnd() * Math.PI * 2);
          lr.push(1.2 + rnd() * 1.4);
          lq.push(rnd() < 0.25 ? 1 : 0);
          lp.push(rnd() * Math.PI * 2);
        }
      }
      var ND = lf.length;
      var pF = Int16Array.from(lf);
      var pA = Float32Array.from(la);
      var pR = Float32Array.from(lr);
      var pQ = Uint8Array.from(lq);
      var pP = Float32Array.from(lp);
      // posição calculada por quadro (buffers fixos)
      var px = new Float32Array(ND);
      var py = new Float32Array(ND);
      var pAl = new Float32Array(ND);
      var fAl = new Float32Array(NF);
      var fEsc = new Float32Array(NF);

      var est = {
        tempo: 0,
        off: 0,
        rot: 0,
        varre: 0,
        yAnt: 0,
        grad: null,
        gradCor: "",
        feixe: null,
        feixeCor: "",
        cone: null,
        coneCor: "",
      };

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
          var falando = estado === "speaking";
          var ouvindo = estado === "listening";
          var pensando = estado === "thinking";

          est.off = suave(est.off, estado === "offline" ? 1 : 0, dt, 3);
          var off = est.off;
          var corP = mistura(cPri, cErr, off * 0.85);
          var corE = mistura(cEsc, cErr, off * 0.45);
          var corD = mistura(cDes, cErr, off);
          var corBranco = mistura(corP, "#ffffff", 0.72 * (1 - off * 0.6));
          var vel = (0.35 + agit * 1.7) * (1 - off * 0.94);
          est.tempo += dt * vel;
          var T = est.tempo;
          est.rot += dt * (0.18 + agit * 0.5) * (1 - off * 0.95);
          // varredura: período ~9 s ida e volta em idle; thinking bem mais rápida
          var velV = (0.45 + agit * 2.6 + (falando ? nivel * 0.6 : 0)) * (1 - off * 0.95);
          est.varre += ((dt * Math.PI * 2) / 9) * velV;
          var fv = 0.5 - 0.5 * Math.cos(est.varre); // 0..1 com ease nas pontas
          var yScan = TOPO - 10 + fv * (BASE - TOPO + 10);
          var subindo = yScan < est.yAnt;
          est.yAnt = yScan;

          // brilho de cada fatia: onda descendo + varredura + nível
          var periodo = pensando ? 1.1 : 2.4;
          var ganho = ouvindo ? 0.15 + nivel * 0.35 : falando ? 0.25 + nivel * 0.6 : pensando ? 0.2 : 0;
          for (i = 0; i < NF; i++) {
            var onda = 0.5 + 0.5 * Math.sin(((T * 2.4) / periodo) * Math.PI * 2 * 0.42 - i * 0.24);
            var a = 0.18 + 0.82 * onda;
            var dScan = Math.abs(fy[i] - yScan);
            var perto = dScan < 40 ? 1 - dScan / 40 : 0;
            a = a * (0.55 + ganho) + perto * 0.6;
            fAl[i] = Math.min(1, a) * (1 - off * 0.35);
            fEsc[i] = 1 + (falando ? nivel * 0.07 * onda : 0) + (ouvindo ? nivel * 0.03 * onda : 0) + perto * 0.02;
          }

          var k = Math.min(q.w, q.h) / 590;
          var cx = q.x + q.w / 2;
          var cy = q.y + q.h / 2 - 6 * k;

          ctx.save();
          ctx.translate(cx, cy);
          ctx.scale(k, k);
          ctx.lineCap = "round";

          // ----- halo
          var corHalo = mistura(corP, corD, falando ? 0.25 + nivel * 0.5 : mist * 0.3);
          if (!est.grad || est.gradCor !== corHalo) {
            est.grad = ctx.createRadialGradient(0, -40, 10, 0, -20, 290);
            est.grad.addColorStop(0, rgba(corHalo, 0.2));
            est.grad.addColorStop(0.55, rgba(corHalo, 0.06));
            est.grad.addColorStop(1, rgba(corHalo, 0));
            est.gradCor = corHalo;
          }
          ctx.globalAlpha = Math.min(1, 0.6 + mist * 0.2 + nivel * (falando ? 0.45 : ouvindo ? 0.3 : 0)) * (1 - off * 0.5);
          ctx.fillStyle = est.grad;
          ctx.fillRect(-300, -300, 600, 600);

          // ----- cone de luz do projetor
          if (!est.cone || est.coneCor !== corP) {
            est.cone = ctx.createLinearGradient(0, 262, 0, 40);
            est.cone.addColorStop(0, rgba(corP, 0.09));
            est.cone.addColorStop(1, rgba(corP, 0));
            est.coneCor = corP;
          }
          ctx.globalAlpha = 0.7 + mist * 0.3;
          ctx.fillStyle = est.cone;
          ctx.beginPath();
          ctx.moveTo(-70, 262);
          ctx.lineTo(70, 262);
          ctx.lineTo(170, 60);
          ctx.lineTo(-170, 60);
          ctx.closePath();
          ctx.fill();

          // ----- meridianos curvos girando (frente mais forte, fundo apagado)
          ctx.strokeStyle = corE;
          ctx.lineWidth = 1;
          var nm = previa ? 5 : 9;
          for (var m = 0; m < nm; m++) {
            var ang = (m / nm) * Math.PI * 2 + est.rot;
            var cxm = Math.sin(ang) * 255;
            var frente = Math.cos(ang);
            ctx.globalAlpha = (frente > 0 ? 0.55 + frente * 0.4 : 0.18 + (1 + frente) * 0.2) * (1 - off * 0.3);
            ctx.beginPath();
            ctx.moveTo(0, TOPO);
            ctx.quadraticCurveTo(cxm, (TOPO + BASE) / 2 - 40, 0, BASE - 60);
            ctx.stroke();
          }

          // ----- fatias (elipses achatadas)
          ctx.lineWidth = 1.2;
          for (i = 0; i < NF; i++) {
            var rx = fw[i] * fEsc[i];
            var dS = Math.abs(fy[i] - yScan);
            var cor = fDest[i] || dS < 18 ? corD : corP;
            if (falando && fAl[i] > 0.75 && i % 2 === 0) cor = corD;
            ctx.strokeStyle = cor;
            ctx.globalAlpha = fAl[i];
            ctx.beginPath();
            ctx.ellipse(0, fy[i], rx, rx * 0.22, 0, 0, Math.PI * 2);
            ctx.stroke();
          }

          // ----- pontos nas fatias (girando; os de trás mais apagados)
          var passo = previa ? 2 : 1;
          var vp = pensando ? 4.5 : falando ? 2.6 + nivel * 3 : 2.85;
          for (i = 0; i < ND; i += passo) {
            var f = pF[i];
            var aa = pA[i] + est.rot;
            var r2 = fw[f] * fEsc[f];
            var s = Math.sin(aa);
            px[i] = Math.cos(aa) * r2;
            py[i] = fy[f] + s * r2 * 0.22;
            var pisca = 0.25 + 0.75 * (0.5 + 0.5 * Math.sin(T * vp + pP[i]));
            pAl[i] = pisca * (s < 0 ? 0.4 : 1) * (0.5 + fAl[f] * 0.5);
          }
          // em 4 faixas de opacidade, 2 cores -> 8 caminhos no total
          for (var cor2 = 0; cor2 < 2; cor2++) {
            ctx.fillStyle = cor2 ? corD : corBranco;
            for (var fx = 0; fx < 4; fx++) {
              var lim0 = fx / 4;
              var lim1 = (fx + 1) / 4;
              ctx.globalAlpha = (lim0 + lim1) / 2;
              ctx.beginPath();
              var algum = false;
              for (i = 0; i < ND; i += passo) {
                if (pQ[i] !== cor2) continue;
                var av = pAl[i];
                if (av < lim0 || av >= lim1 + (fx === 3 ? 1 : 0)) continue;
                ctx.moveTo(px[i] + pR[i], py[i]);
                ctx.arc(px[i], py[i], pR[i], 0, Math.PI * 2);
                algum = true;
              }
              if (algum) ctx.fill();
            }
          }

          // ----- linha de varredura + feixe (rastro do lado oposto ao movimento)
          if (!est.feixe || est.feixeCor !== corD) {
            est.feixe = ctx.createLinearGradient(0, -34, 0, 0);
            est.feixe.addColorStop(0, rgba(corD, 0));
            est.feixe.addColorStop(1, rgba(corD, 0.28));
            est.feixeCor = corD;
          }
          // largura da varredura acompanha a fatia daquela altura
          var posF = ((yScan - TOPO) / (BASE - TOPO)) * (NF - 1);
          var i0 = Math.max(0, Math.min(NF - 1, Math.floor(posF)));
          var i1 = Math.min(NF - 1, i0 + 1);
          var fr = Math.max(0, Math.min(1, posF - i0));
          var lw = Math.max(60, fw[i0] + (fw[i1] - fw[i0]) * fr) + 45;
          var aScan = (0.75 + mist * 0.25) * (1 - off * 0.5);
          ctx.save();
          ctx.translate(0, yScan);
          if (subindo) ctx.scale(1, -1);
          ctx.globalAlpha = aScan;
          ctx.fillStyle = est.feixe;
          ctx.fillRect(-lw, -34, lw * 2, 34);
          ctx.restore();
          ctx.fillStyle = corD;
          if (!previa) {
            ctx.globalAlpha = aScan * 0.25;
            ctx.fillRect(-lw - 10, yScan - 3, lw * 2 + 20, 6);
          }
          ctx.globalAlpha = aScan;
          ctx.fillRect(-lw - 10, yScan - 1, lw * 2 + 20, 2);

          // ----- projetor no chão
          ctx.strokeStyle = corP;
          ctx.lineWidth = 1;
          var pulsoChao = 0.5 + 0.5 * Math.sin(T * 2);
          for (var e = 0; e < 3; e++) {
            var rr = 150 - e * 40;
            ctx.globalAlpha = (0.4 + e * 0.2) * (0.7 + 0.3 * pulsoChao) * (1 - off * 0.3);
            ctx.beginPath();
            ctx.ellipse(0, 262, rr, rr * 0.16, 0, 0, Math.PI * 2);
            ctx.stroke();
          }
          ctx.fillStyle = corD;
          ctx.globalAlpha = (0.35 + 0.35 * pulsoChao + (falando ? nivel * 0.3 : 0)) * (1 - off * 0.4);
          ctx.beginPath();
          ctx.ellipse(0, 262, 26, 4.5, 0, 0, Math.PI * 2);
          ctx.fill();

          ctx.restore();
        },
      };
    },
  });
})();
