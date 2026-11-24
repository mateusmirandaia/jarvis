/* Visual "aura" — Aura (paleta aura, HUD mínimo). DELICADO: linhas finas, brilho sutil.
 * Silhueta de cabeça e ombros feita de luz azul (sem rosto), linhas de contorno que acendem
 * em onda, núcleo laranja/dourado pulsando, espinha neural dourada, partículas se desfazendo
 * do alto da cabeça e ondas de energia dos dois lados com raios finos estalando.
 * Coordenadas da figura numa caixa 1280x760 (centro x=640), escalada e centrada na área.
 * Não desenha texto (letreiro, status e conversa são do shell).
 */
(function () {
  "use strict";

  var SIL =
    "M640,95 C715,95 762,160 762,245 C762,300 742,350 712,380 C700,392 695,410 695,440 " +
    "C700,470 760,500 860,530 C930,550 960,600 975,760 L305,760 C320,600 350,550 420,530 " +
    "C520,500 580,470 585,440 C585,410 580,392 568,380 C538,350 518,300 518,245 C518,160 565,95 640,95Z";

  var PADRAO = {
    fundo: "#02040B", primaria: "#2F7BFF", clara: "#7DB8FF", gelo: "#D6ECFF",
    nucleo: "#FF7A1A", ouro: "#FFD25A", erro: "#FF5C7A",
  };

  // piscar dos raios/espinha: (fração, opacidade)
  var FLK_T = [0, 0.06, 0.1, 0.14, 0.32, 1];
  var FLK_V = [0, 1, 0.25, 0.95, 0, 0];
  function piscar(f) {
    if (f <= 0 || f >= 1) return 0;
    for (var i = 1; i < FLK_T.length; i++) {
      if (f <= FLK_T[i]) {
        var u = (f - FLK_T[i - 1]) / (FLK_T[i] - FLK_T[i - 1]);
        return FLK_V[i - 1] + (FLK_V[i] - FLK_V[i - 1]) * u;
      }
    }
    return 0;
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

  function cor(c, k) {
    return (c && c[k]) || PADRAO[k];
  }

  function criar() {
    var r = rnd(31);
    var silhueta = typeof Path2D === "function" ? new Path2D(SIL) : null;

    // meia-largura da silhueta por altura (lado direito da curva, amostrado uma vez):
    // as linhas de contorno vão de borda a borda sem ctx.clip, que é caro por quadro
    var SEG = [
      [640, 95, 715, 95, 762, 160, 762, 245],
      [762, 245, 762, 300, 742, 350, 712, 380],
      [712, 380, 700, 392, 695, 410, 695, 440],
      [695, 440, 700, 470, 760, 500, 860, 530],
      [860, 530, 930, 550, 960, 600, 975, 760],
    ];
    var amX = [], amY = [];
    for (var sg = 0; sg < SEG.length; sg++) {
      var segC = SEG[sg];
      for (var st = 0; st <= 40; st++) {
        var tt = st / 40, mt = 1 - tt;
        var b0 = mt * mt * mt, b1 = 3 * mt * mt * tt, b2 = 3 * mt * tt * tt, b3 = tt * tt * tt;
        amX.push(b0 * segC[0] + b1 * segC[2] + b2 * segC[4] + b3 * segC[6]);
        amY.push(b0 * segC[1] + b1 * segC[3] + b2 * segC[5] + b3 * segC[7]);
      }
    }
    function meiaLargura(y) {
      if (y <= amY[0]) return 0;
      for (var j = 1; j < amY.length; j++) {
        if (amY[j] >= y) {
          var f = (y - amY[j - 1]) / Math.max(1e-6, amY[j] - amY[j - 1]);
          return amX[j - 1] + (amX[j] - amX[j - 1]) * f - 640;
        }
      }
      return amX[amX.length - 1] - 640;
    }
    var MEIA = new Float32Array(200);
    for (var yi = 0; yi < 200; yi++) MEIA[yi] = meiaLargura(98 + yi * 5);

    // estrelas de fundo (normalizadas: x na largura, y na metade de cima)
    var NE = 90;
    var est = new Float32Array(NE * 4);
    for (var i = 0; i < NE; i++) {
      est[i * 4] = r();
      est[i * 4 + 1] = r() * 0.5;
      est[i * 4 + 2] = 0.3 + r() * 0.6;
      est[i * 4 + 3] = r() * 6.28;
    }

    // cristas de energia: 24 por lado
    var NR = 24;
    var crFase = new Float32Array(NR * 2);
    for (i = 0; i < NR * 2; i++) crFase[i] = r() * 6;

    // partículas que se desfazem do alto da cabeça
    var NP = 280;
    var px0 = new Float32Array(NP), py0 = new Float32Array(NP);
    var pdur = new Float32Array(NP), pdes = new Float32Array(NP), ptam = new Float32Array(NP);
    var pcor = new Uint8Array(NP);
    for (i = 0; i < NP; i++) {
      var a = -1.9 + r() * 1.8;
      var rad = 118 + r() * 57;
      px0[i] = 640 + Math.cos(a) * rad * 0.95;
      py0[i] = 245 + Math.sin(a) * rad * 1.1;
      pdur[i] = 3 + r() * 3;
      pdes[i] = r();
      ptam[i] = 0.35 + r() * 0.9;
      pcor[i] = Math.floor(r() * 3);
    }

    // raios (pool reciclado): 3 por lado, 22 pontos cada
    var NB = 6, NPB = 22;
    var raioU = new Float32Array(NB * NPB); // posição ao longo do lado (0..1)
    var raioY = new Float32Array(NB * NPB); // y na caixa
    var raioVida = new Float32Array(NB); // tempo decorrido
    var raioDur = new Float32Array(NB);
    var raioEspera = new Float32Array(NB);
    var raioOuro = new Uint8Array(NB);
    function novoRaio(b) {
      var u = 0.06 + r() * 0.7, yy = 330 + r() * 140;
      for (var s = 0; s < NPB; s++) {
        raioU[b * NPB + s] = u;
        raioY[b * NPB + s] = yy;
        u += (5 + r() * 7) / 620;
        yy += -9 + r() * 19;
      }
      raioVida[b] = 0;
      raioDur[b] = 0.7 + r() * 0.9;
      raioOuro[b] = r() < 0.6 ? 1 : 0;
    }
    for (i = 0; i < NB; i++) {
      novoRaio(i);
      raioVida[i] = r() * raioDur[i];
      raioEspera[i] = r() * 2;
    }

    // espinha neural (caixa): tronco + ramos
    var ESPINHA = [
      [400, 26], [450, -30], [500, 40], [540, -46], [580, 60],
    ];

    var grads = {};
    var tAnt = -1, tPart = 0, tLinhas = 0, tOnda = 0, tEspinha = 0;
    // núcleo: esfera de partículas (espiral de Fibonacci, como o Globo) girando no lugar do rosto
    var NS = 520;
    var esX = new Float32Array(NS), esY = new Float32Array(NS), esZ = new Float32Array(NS);
    var esF = new Float32Array(NS);
    var angOuro = Math.PI * (3 - Math.sqrt(5));
    for (var ie = 0; ie < NS; ie++) {
      var ey0 = 1 - (ie / (NS - 1)) * 2;
      var er0 = Math.sqrt(1 - ey0 * ey0);
      esX[ie] = Math.cos(angOuro * ie) * er0;
      esY[ie] = ey0;
      esZ[ie] = Math.sin(angOuro * ie) * er0;
      esF[ie] = r() * Math.PI * 2;
    }
    var rotN = 0;

    function gradNucleo(ctx, c0, c1, c2) {
      var k = "n" + c0 + c1 + c2;
      if (!grads[k]) {
        var g = ctx.createRadialGradient(0, 0, 0, 0, 0, 78);
        g.addColorStop(0, c0);
        g.addColorStop(0.22, c1);
        g.addColorStop(0.62, hexA(c2, 0.85));
        g.addColorStop(1, hexA(c2, 0));
        grads[k] = g;
      }
      return grads[k];
    }

    function gradCorpo(ctx) {
      if (!grads.corpo) {
        var g = ctx.createRadialGradient(640, 294, 0, 640, 294, 470);
        g.addColorStop(0, "rgba(14,42,107,0.9)");
        g.addColorStop(1, "rgba(2,4,11,0.95)");
        grads.corpo = g;
      }
      return grads.corpo;
    }

    function gradCeu(ctx) {
      if (!grads.ceu) {
        var g = ctx.createRadialGradient(640, 266, 0, 640, 266, 760);
        g.addColorStop(0, "rgba(11,31,85,0.8)");
        g.addColorStop(1, "rgba(2,4,11,0)");
        grads.ceu = g;
      }
      return grads.ceu;
    }

    function gradChao(ctx, c1) {
      var k = "c" + c1;
      if (!grads[k]) {
        var g = ctx.createLinearGradient(0, 400, 0, 760);
        g.addColorStop(0, hexA(c1, 0));
        g.addColorStop(0.2, hexA(c1, 0.13));
        g.addColorStop(1, hexA(c1, 0));
        grads[k] = g;
      }
      return grads[k];
    }

    function desenhar(ctx, q) {
      var t = q.t || 0;
      var dt = q.dt;
      if (!(dt >= 0)) dt = tAnt < 0 ? 0 : Math.max(0, Math.min(0.1, t - tAnt));
      tAnt = t;
      var c = q.cores || PADRAO;
      var estado = q.estado || "idle";
      var nivel = q.nivel || 0;
      var agit = q.agitacao == null ? 0.15 : q.agitacao;
      var offline = estado === "offline";
      var previa = !!q.previa;
      var falando = estado === "speaking";
      var ouvindo = estado === "listening";
      var pensando = estado === "thinking";

      var cPrim = cor(c, "primaria"), cClara = cor(c, "clara"), cGelo = cor(c, "gelo");
      var cNucleo = cor(c, "nucleo"), cOuro = cor(c, "ouro"), cErro = cor(c, "erro");
      var cBorda = offline ? cErro : cClara;

      // relógios integrados (sem saltos na troca de estado)
      tPart += dt * (offline ? 0.08 : 0.7 + agit * 0.8);
      tLinhas += dt * (offline ? 0.1 : 0.8 + agit * 2.2);
      tOnda += dt * (offline ? 0.05 : 0.35 + agit * 0.6 + (falando ? nivel * 0.5 : 0));
      tEspinha += dt * (offline ? 0.1 : 0.6 + agit * 1.2 + (falando ? nivel : 0));

      var x = q.x || 0, y = q.y || 0, w = q.w || 1280, h = q.h || 760;
      var k = Math.min(w / 1280, h / 760);
      if (!(k > 0)) return;
      var ox = x + w / 2 - 640 * k;
      var oy = y + (h - 760 * k) / 2;
      var meio = x + w / 2;
      var fina = Math.max(0.5, 0.35 / k); // largura mínima (em unidades da caixa)

      ctx.save();
      ctx.lineCap = "round";
      ctx.lineJoin = "round";

      // ---- céu ----
      ctx.save();
      ctx.translate(ox, oy);
      ctx.scale(k, k);
      ctx.globalAlpha = offline ? 0.5 : 1;
      ctx.fillStyle = gradCeu(ctx);
      ctx.fillRect((x - ox) / k, (y - oy) / k, w / k, h / k);
      ctx.restore();

      // ---- estrelas ----
      ctx.fillStyle = cClara;
      var ne = previa ? 40 : NE;
      for (i = 0; i < ne; i++) {
        var o = i * 4;
        ctx.globalAlpha = (offline ? 0.3 : 0.6) * (0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * 3.1 + est[o + 3])));
        var tam = Math.max(0.6, est[o + 2] * k * 1.6);
        ctx.fillRect(x + est[o] * w, oy + est[o + 1] * 760 * k, tam, tam);
      }

      // ---- ondas de energia laterais (largura toda) ----
      var nr = previa ? 10 : NR;
      var amostras = previa ? 40 : 64;
      var esqIni = x - 60 * k, esqFim = meio - 80 * k;
      var dirIni = meio + 80 * k, dirFim = x + w + 60 * k;
      for (var lado = 0; lado < 2; lado++) {
        var x0 = lado === 0 ? esqIni : dirIni;
        var x1 = lado === 0 ? esqFim : dirFim;
        var balanco = Math.sin(t * ((Math.PI * 2) / (lado === 0 ? 9 : 11))) * 26 * k * (lado === 0 ? -1 : 1);
        if (offline) balanco *= 0.2;
        for (var kr = 0; kr < nr; kr++) {
          var ki = previa ? kr * 2.4 : kr; // índice equivalente no mockup
          var base = 430 + ki * 13;
          var amp = (80 - ki * 2.4) * (falando ? 1 + nivel * 0.25 : 1);
          var ph = crFase[lado * NR + kr];
          var op = Math.max(0.08, 0.7 - ki * 0.028) * (offline ? 0.35 : 0.85 + 0.15 * agit);
          ctx.strokeStyle = offline ? (ki < 2 ? cErro : cPrim) : ki < 2 ? cGelo : ki < 7 ? cClara : cPrim;
          ctx.lineWidth = (ki < 3 ? 0.9 : 0.55) * Math.max(0.75, k);
          ctx.globalAlpha = op;
          ctx.beginPath();
          for (var s = 0; s <= amostras; s++) {
            var u = s / amostras;
            var sm = u * 120;
            var fora = lado === 0 ? 1 - u : u;
            var yy =
              base -
              amp * (0.35 + 0.65 * fora) * (0.6 + 0.4 * Math.sin(sm * 0.16 + ph + tOnda)) -
              6 * Math.sin(sm * 0.45 + ph - tOnda * 1.7);
            var xx = x0 + (x1 - x0) * u + balanco;
            if (s === 0) ctx.moveTo(xx, oy + yy * k);
            else ctx.lineTo(xx, oy + yy * k);
          }
          ctx.stroke();
        }
        // raios finos estalando sobre as cristas
        if (!previa || lado === 1) {
          for (var b = lado * 3; b < lado * 3 + 3; b++) {
            if (raioEspera[b] > 0) {
              raioEspera[b] -= dt * (0.4 + agit * 1.6 + (falando ? nivel : 0));
              continue;
            }
            raioVida[b] += dt;
            var fr = raioVida[b] / raioDur[b];
            if (fr >= 1) {
              novoRaio(b);
              raioEspera[b] = 0.6 + r() * (offline ? 8 : 3.2);
              continue;
            }
            var opR = piscar(fr);
            if (opR < 0.03) continue;
            ctx.strokeStyle = offline ? cErro : raioOuro[b] ? cOuro : cGelo;
            for (var passe = 0; passe < 2; passe++) {
              ctx.globalAlpha = opR * (passe === 0 ? 0.18 : 0.9);
              ctx.lineWidth = passe === 0 ? 3 * Math.max(0.75, k) : 0.9 * Math.max(0.75, k);
              ctx.beginPath();
              for (s = 0; s < NPB; s++) {
                var bx = x0 + (x1 - x0) * raioU[b * NPB + s] + balanco;
                var by = oy + raioY[b * NPB + s] * k;
                if (s === 0) ctx.moveTo(bx, by);
                else ctx.lineTo(bx, by);
              }
              ctx.stroke();
            }
          }
        }
      }
      // brilho do "chão" sob as cristas (suave, sem bordas)
      ctx.save();
      ctx.translate(x, oy);
      ctx.scale(1, k);
      ctx.globalAlpha = offline ? 0.4 : 1;
      ctx.fillStyle = gradChao(ctx, cPrim);
      ctx.fillRect(0, 400, w, 360);
      ctx.restore();

      // ---- figura (coordenadas da caixa) ----
      ctx.save();
      ctx.translate(ox, oy);
      ctx.scale(k, k);

      var pulsoBorda = 0.5 + 0.5 * Math.sin(t * ((Math.PI * 2) / 2.2));
      var vivo = offline ? 0.35 : 0.65 + 0.35 * pulsoBorda;
      if (ouvindo) vivo = Math.min(1.3, vivo + 0.25 + nivel * 0.5);

      if (silhueta) {
        // aura externa: traços largos e transparentes (brilho sem filtro)
        ctx.strokeStyle = offline ? cErro : cPrim;
        ctx.globalAlpha = 0.05 * vivo;
        ctx.lineWidth = 26;
        ctx.stroke(silhueta);
        ctx.globalAlpha = 0.08 * vivo;
        ctx.lineWidth = 14;
        ctx.stroke(silhueta);
        ctx.globalAlpha = 0.12 * vivo;
        ctx.lineWidth = 6;
        ctx.stroke(silhueta);

        ctx.globalAlpha = 1;
        ctx.fillStyle = gradCorpo(ctx);
        ctx.fill(silhueta);

        ctx.save();

        // linhas de contorno horizontais acendendo em onda
        var passo = previa ? 10 : 5;
        var ondula = offline ? 0.3 : pensando ? 2 + 5 * agit : 1 + 1.5 * agit;
        var freq = pensando ? 7 : 2.2;
        ctx.strokeStyle = offline ? cPrim : cClara;
        ctx.lineWidth = Math.max(0.5, fina);
        // agrupa as linhas em 8 níveis de brilho: 8 traços por quadro em vez de ~130
        var baseA = offline ? 0.08 : 0.15, faixaA = offline ? 0.12 : 0.45;
        for (var nv = 0; nv < 8; nv++) {
          ctx.globalAlpha = baseA + faixaA * (nv / 7);
          ctx.beginPath();
          var li = 0;
          for (var yl = 98; yl < 760; yl += passo) {
            var onda = 0.5 + 0.5 * Math.sin(((tLinhas - li * 0.03 * (passo / 5)) * Math.PI * 2) / 3);
            if (Math.round(onda * 7) === nv) {
              var hw = MEIA[Math.min(199, Math.round((yl - 98) / 5))] - 1.5;
              if (hw > 4) {
                var d = ondula * Math.sin(t * freq + li * 0.35) * Math.min(1, hw / 60);
                var sag = Math.min(10, hw * 0.12);
                ctx.moveTo(640 - hw, yl);
                ctx.bezierCurveTo(640 - hw * 0.5, yl + sag + d, 640 + hw * 0.5, yl + sag - d, 640 + hw, yl);
              }
            }
            li++;
          }
          ctx.stroke();
        }

        // núcleo no lugar do rosto
        var pul = 0.5 + 0.5 * Math.sin(t * ((Math.PI * 2) / (falando ? 1.4 : 2.2)));
        var escN = 0.88 + 0.22 * pul;
        if (falando) escN = 0.95 + 0.12 * pul + nivel * 0.45;
        else if (ouvindo) escN += nivel * 0.12;
        if (offline) escN = 0.8;
        ctx.save();
        ctx.translate(640, 255);
        ctx.scale(escN, escN);
        // brilho quente e discreto atrás da esfera
        ctx.globalAlpha = offline ? 0.18 : 0.16 + (falando ? nivel * 0.25 : 0) + (pensando ? 0.06 : 0);
        ctx.fillStyle = offline
          ? gradNucleo(ctx, "#FFE1E6", cErro, cErro)
          : gradNucleo(ctx, "#FFF8DE", cOuro, cNucleo);
        ctx.beginPath();
        ctx.arc(0, 0, 78, 0, Math.PI * 2);
        ctx.fill();

        // esfera de partículas girando (3 faixas de profundidade = 3 preenchimentos)
        rotN += dt * (offline ? 0.04 : 0.22 + agit * 0.9 + (falando ? nivel * 0.8 : 0));
        var cosR = Math.cos(rotN), sinR = Math.sin(rotN);
        var incl = 0.38, cosI = Math.cos(incl), sinI = Math.sin(incl);
        var ondaN = offline ? 0 : (pensando ? 0.09 : 0.02) + nivel * (falando ? 0.2 : ouvindo ? 0.1 : 0);
        var RN = 60;
        var passoN = previa ? 3 : 1;
        var coresN = offline ? [cErro, cErro, "#FFE1E6"] : [cNucleo, cOuro, "#FFF3D0"];
        var alfasN = offline ? [0.18, 0.35, 0.55] : [0.28, 0.6, 0.95];
        for (var fx = 0; fx < 3; fx++) {
          ctx.fillStyle = coresN[fx];
          ctx.globalAlpha = alfasN[fx];
          ctx.beginPath();
          for (var ip = 0; ip < NS; ip += passoN) {
            var desl = 1 + Math.sin(t * 3 + esF[ip] + esY[ip] * 4) * ondaN;
            var npx = esX[ip] * desl, npy = esY[ip] * desl, npz = esZ[ip] * desl;
            var nx1 = npx * cosR - npz * sinR;
            var nz1 = npx * sinR + npz * cosR;
            var ny1 = npy * cosI - nz1 * sinI;
            var nz2 = npy * sinI + nz1 * cosI;
            var prof = (1 - nz2) / 2; // 0 = fundo, 1 = frente
            var faixa = prof < 0.4 ? 0 : prof < 0.72 ? 1 : 2;
            if (faixa !== fx) continue;
            var persp = 2.6 / (2.6 + nz2);
            var tamP = (0.7 + prof * 1.5) * (1 + (falando ? nivel * 0.5 : 0)) * (previa ? 1.6 : 1);
            ctx.rect(nx1 * RN * persp - tamP / 2, ny1 * RN * persp - tamP / 2, tamP, tamP);
          }
          ctx.fill();
        }
        // anel fino que acende com a voz
        ctx.strokeStyle = offline ? cErro : cOuro;
        ctx.globalAlpha = offline ? 0.1 : 0.06 + (falando ? nivel * 0.5 : 0);
        ctx.lineWidth = 0.7;
        ctx.beginPath();
        ctx.arc(0, 0, RN * 1.28, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();

        // espinha neural dourada
        var corEsp = offline ? cErro : cOuro;
        ctx.strokeStyle = corEsp;
        ctx.globalAlpha = 0.45;
        ctx.lineWidth = Math.max(0.6, fina);
        ctx.beginPath();
        ctx.moveTo(640, 330);
        ctx.lineTo(640, 600);
        ctx.stroke();
        var fe = tEspinha / 2.6;
        var opE = 0.15 + 0.85 * piscar(fe - Math.floor(fe));
        ctx.globalAlpha = opE;
        ctx.lineWidth = Math.max(0.8, fina);
        ctx.beginPath();
        for (var e = 0; e < ESPINHA.length; e++) {
          var ey = ESPINHA[e][0], edx = ESPINHA[e][1];
          ctx.moveTo(640, ey);
          ctx.lineTo(640 + edx, ey + 18);
          ctx.lineTo(640 + edx * 1.6, ey + 10);
        }
        ctx.moveTo(640, 330);
        ctx.lineTo(640, 600);
        ctx.stroke();
        // sinal descendo pela espinha (mais frequente pensando/falando)
        if (!offline) {
          var fs = (tEspinha * 0.6) % 1;
          var sy = 330 + 270 * fs;
          ctx.fillStyle = cOuro;
          ctx.globalAlpha = 0.25 * Math.sin(Math.PI * fs);
          ctx.beginPath();
          ctx.arc(640, sy, 4, 0, Math.PI * 2);
          ctx.fill();
          ctx.globalAlpha = 0.9 * Math.sin(Math.PI * fs);
          ctx.beginPath();
          ctx.arc(640, sy, 1.3, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore(); // fim do bloco interno

        // borda nítida com brilho fino
        ctx.strokeStyle = cBorda;
        ctx.globalAlpha = Math.min(1, 0.22 * vivo);
        ctx.lineWidth = 4.5;
        ctx.stroke(silhueta);
        ctx.globalAlpha = Math.min(1, vivo);
        ctx.lineWidth = 1.6;
        ctx.stroke(silhueta);
        ctx.strokeStyle = offline ? cErro : "#FFFFFF";
        ctx.globalAlpha = offline ? 0.4 : 0.85;
        ctx.lineWidth = Math.max(0.7, fina);
        ctx.stroke(silhueta);
      }

      // partículas se desfazendo do alto da cabeça (para cima/direita)
      var np = previa ? 100 : NP;
      for (var cc = 0; cc < 3; cc++) {
        ctx.fillStyle = offline ? cErro : cc === 0 ? cGelo : cc === 1 ? cClara : "#FFFFFF";
        for (i = 0; i < np; i++) {
          if (pcor[i] !== cc) continue;
          var p = tPart / pdur[i] + pdes[i];
          p -= Math.floor(p);
          var al = p < 0.15 ? p / 0.15 : 1 - (p - 0.15) / 0.85;
          if (al < 0.02) continue;
          ctx.globalAlpha = al * (offline ? 0.4 : 0.9);
          var tp = ptam[i] * 1.6 * (falando ? 1 + nivel * 0.3 : 1);
          ctx.fillRect(px0[i] + 70 * p - tp / 2, py0[i] - 110 * p - tp / 2, tp, tp);
        }
      }

      ctx.restore(); // caixa
      ctx.restore();
    }

    return { desenhar: desenhar };
  }

  window.JarvisVisuais.registrar({
    id: "aura",
    nome: "Aura",
    descricao: "Silhueta de luz azul com núcleo dourado e ondas de energia.",
    paleta: "aura",
    hud: "minimo",
    criar: criar,
  });
})();
