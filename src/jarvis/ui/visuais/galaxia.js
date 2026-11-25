/* Visual "galaxia" — Galáxia Neural (paleta nuvem).
 * Galáxia espiral de 3 braços (820 pontos) girando em Transformative Teal que se fecha num
 * cérebro (2 hemisférios + cerebelo), com sinapses e impulsos em branco Cloud Dancer, e volta
 * a ser galáxia. Ciclo de ~13 s. Fiel à referência aprovada (ref_galaxia.html), portada para
 * o contrato: desenha só na área q, tudo acumulado por dt, pontos em lotes por faixa de
 * profundidade e cor, sem alocar por quadro.
 */
(function () {
  "use strict";

  var N = 820;
  var CICLO = 13; // segundos
  var MAX_PULSOS = 90;
  var DOIS_PI = Math.PI * 2;

  // fallback da paleta nuvem (o shell pode ainda não ter a paleta)
  var PADRAO = {
    fundo: "#041012",
    escura: "#1E7F7A",
    primaria: "#2BA79B",
    clara: "#9FE3DA",
    ouvindo: "#5FC8BE",
    destaque: "#F0EEE9",
    erro: "#FF6B6B",
  };

  // faixas de profundidade (d = 0 longe .. 1 perto); as bordas .35 e .62 são as trocas de cor
  // da referência (escura | primaria | clara)
  var BORDAS = [0.175, 0.35, 0.49, 0.62, 0.75, 0.875];
  var NB = BORDAS.length + 1; // 7 faixas + 1 lote "quente" (Cloud Dancer)
  var FAIXA_COR = [0, 0, 1, 1, 2, 2, 2]; // 0 escura, 1 primaria, 2 clara
  var FAIXA_D = [0.0875, 0.2625, 0.42, 0.555, 0.685, 0.8125, 0.9375];

  function suave(atual, alvo, dt, taxa) {
    return atual + (alvo - atual) * (1 - Math.exp(-dt * taxa));
  }

  function easeInOut(x) {
    return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  }

  function hexRgb(hex, padrao) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ""));
    if (!m) m = /^#?([0-9a-f]{6})$/i.exec(padrao);
    var n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function misturar(a, b, u) {
    return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
  }

  function rgbStr(c) {
    return "rgb(" + Math.round(c[0]) + "," + Math.round(c[1]) + "," + Math.round(c[2]) + ")";
  }

  function criar() {
    // ---- geometria (mesma semente e fórmulas da referência) ----
    var seed = 11;
    function rnd() {
      seed = (seed * 16807) % 2147483647;
      return seed / 2147483647;
    }
    var gx = new Float32Array(N), gy = new Float32Array(N), gz = new Float32Array(N);
    var bx = new Float32Array(N), by = new Float32Array(N), bz = new Float32Array(N);
    var ph = new Float32Array(N);
    var i, j;
    for (i = 0; i < N; i++) {
      ph[i] = rnd() * 6.28;
      var braco = i % 3, rr = Math.pow(rnd(), 0.7);
      var ang = braco * 2.094 + rr * 5.2 + (rnd() - 0.5) * 0.5;
      var nucleo = rr < 0.12;
      gx[i] = Math.cos(ang) * rr * 1.05;
      gy[i] = (rnd() - 0.5) * (nucleo ? 0.18 : 0.05);
      gz[i] = Math.sin(ang) * rr * 1.05;
      var x, y, z;
      if (i < 44) {
        // cerebelo
        var a = rnd() * 6.28, b = rnd() * 3.14;
        x = Math.cos(a) * Math.sin(b) * 0.28;
        y = 0.42 + Math.cos(b) * 0.16;
        z = -0.5 + Math.sin(a) * Math.sin(b) * 0.22;
      } else {
        // hemisférios com sulcos
        var lado = i % 2 ? 1 : -1, u = rnd() * 6.28, v = Math.acos(2 * rnd() - 1);
        var ex = Math.cos(u) * Math.sin(v), ey = Math.cos(v), ez = Math.sin(u) * Math.sin(v);
        if (lado * ex < -0.2) ex = lado * (-0.2 + (lado * ex + 0.2) * 0.15);
        var sulco = 1 + 0.07 * Math.sin(9 * u + 3 * v) * Math.sin(7 * v);
        x = lado * 0.06 + ex * 0.46 * sulco + lado * 0.36;
        y = ey * 0.5 * sulco - 0.02;
        z = ez * 0.72 * sulco * (1 + 0.08 * ey);
      }
      bx[i] = x * 1.05;
      by[i] = y * 1.05;
      bz[i] = z * 1.05;
    }

    // sinapses: vizinho mais próximo (no cérebro) de TODOS os pontos — os dois hemisférios e o
    // cerebelo ficam ligados, com a mesma densidade de linhas da referência (~1 por ponto);
    // pares mútuos (i↔j) entram uma vez só
    var viz = new Int32Array(N), vizD = new Float32Array(N);
    for (i = 0; i < N; i++) {
      var d1 = 9, j1 = -1;
      for (j = 0; j < N; j++) {
        if (j === i) continue;
        var dx = bx[i] - bx[j], dy = by[i] - by[j], dz = bz[i] - bz[j];
        var dd = dx * dx + dy * dy + dz * dz;
        if (dd < d1) { d1 = dd; j1 = j; }
      }
      viz[i] = j1;
      vizD[i] = d1;
    }
    var tmpA = [], tmpB = [];
    for (i = 0; i < N; i++) {
      j = viz[i];
      if (j < 0 || vizD[i] >= 0.03) continue;
      if (j < i && viz[j] === i) continue;
      tmpA.push(i);
      tmpB.push(j);
    }
    var NL = tmpA.length;
    var la = Int32Array.from(tmpA), lb = Int32Array.from(tmpB);

    // impulsos (pool fixo)
    var pl = new Int32Array(MAX_PULSOS), pt = new Float32Array(MAX_PULSOS), pv = new Float32Array(MAX_PULSOS);
    for (i = 0; i < MAX_PULSOS; i++) {
      pl[i] = Math.floor(rnd() * NL);
      pt[i] = rnd();
      pv[i] = 0.6 + rnd() * 1.2;
    }

    // buffers do quadro
    var P = new Float32Array(N * 3);
    var faixa = new Uint8Array(N);

    // ---- cores (recalculadas só quando a paleta muda) ----
    // OFF_PASSOS tons entre a cor normal e a cor de alerta, para o offline entrar sem salto
    var OFF_PASSOS = 12;
    var cor = { chave: null, banda: [[], [], []], quente: [], linha: [], haloTeal: null, haloNuvem: null, haloErro: null };
    function atualizarCores(c) {
      var chave = c.escura + c.primaria + c.clara + c.destaque + c.falando + c.ouvindo + c.erro;
      if (chave === cor.chave) return;
      cor.chave = chave;
      var escura = hexRgb(c.escura, PADRAO.escura);
      var prim = hexRgb(c.primaria, PADRAO.primaria);
      var clara = hexRgb(c.clara, PADRAO.clara);
      var nuvem = hexRgb(c.falando || c.destaque, PADRAO.destaque);
      var linha = hexRgb(c.ouvindo, PADRAO.ouvindo);
      var erro = hexRgb(c.erro, PADRAO.erro);
      var preto = [0, 0, 0], branco = [255, 255, 255];
      var bases = [escura, prim, clara];
      var alvos = [misturar(erro, preto, 0.45), erro, misturar(erro, branco, 0.25)];
      for (var k = 0; k < 3; k++) {
        cor.banda[k].length = 0;
        for (var s = 0; s <= OFF_PASSOS; s++) cor.banda[k].push(rgbStr(misturar(bases[k], alvos[k], s / OFF_PASSOS)));
      }
      cor.quente.length = 0;
      cor.linha.length = 0;
      var quenteOff = misturar(erro, branco, 0.4);
      for (s = 0; s <= OFF_PASSOS; s++) {
        cor.quente.push(rgbStr(misturar(nuvem, quenteOff, s / OFF_PASSOS)));
        cor.linha.push(rgbStr(misturar(linha, erro, s / OFF_PASSOS)));
      }
      cor.rgbEscura = escura;
      cor.rgbNuvem = nuvem;
      cor.rgbErro = erro;
      cor.haloTeal = cor.haloNuvem = cor.haloErro = null; // gradientes recriados sob demanda
    }

    // halos: gradiente em coordenadas unitárias (o ctx é escalado por R), criado uma vez
    function halo(ctx, rgb, a) {
      var g = ctx.createRadialGradient(0, 0, 0, 0, 0, 1.4);
      g.addColorStop(0, "rgba(" + rgb[0] + "," + rgb[1] + "," + rgb[2] + "," + a + ")");
      g.addColorStop(1, "rgba(" + rgb[0] + "," + rgb[1] + "," + rgb[2] + ",0)");
      return g;
    }

    // ---- estado animado (tudo acumulado por dt) ----
    var rot = 0, spin = 0, ciclo = 0, brilhoT = 0, tAnt = -1;
    var fechar = 0;      // 0 = segue o ciclo, 1 = cérebro fechado (thinking/speaking)
    var velGiro = 1;     // multiplicador do giro
    var velCiclo = 1;    // multiplicador do ciclo galáxia → cérebro
    var nPulsos = 30;    // impulsos ativos (suavizado)
    var velPulso = 1;
    var tamPontos = 1;
    var reage = 0;       // peso do listening (pontos respondem ao nível)
    var fala = 0;        // peso do speaking
    var off = 0;         // peso do offline
    var nivelS = 0;

    function desenhar(ctx, q) {
      var t = q.t || 0;
      var dt = q.dt;
      if (!(dt >= 0)) dt = tAnt < 0 ? 0 : Math.max(0, Math.min(0.1, t - tAnt));
      tAnt = t;
      if (dt > 0.1) dt = 0.1;
      var c = q.cores || PADRAO;
      atualizarCores(c);
      var estado = q.estado || "idle";
      var nivel = q.nivel > 0 ? Math.min(1, q.nivel) : 0;
      var previa = !!q.previa;

      // alvos por estado
      var aFechar = 0, aGiro = 1, aCiclo = 1, aPulsos = 30, aVelP = 1, aTam = 1, aReage = 0, aFala = 0, aOff = 0;
      if (estado === "listening") {
        aGiro = 1.45 + nivel * 0.6; aCiclo = 1.1; aTam = 1.05; aReage = 1;
      } else if (estado === "thinking") {
        aFechar = 1; aGiro = 1.6; aPulsos = 85; aVelP = 2.8; aTam = 1.05;
      } else if (estado === "speaking") {
        aFechar = 1; aGiro = 0.9; aPulsos = 40 + nivel * 45; aVelP = 0.9 + nivel * 2.2; aTam = 1.35 + nivel * 0.35; aFala = 1;
      } else if (estado === "offline") {
        aGiro = 0.08; aCiclo = 0.05; aPulsos = 6; aVelP = 0.15; aTam = 0.9; aOff = 1;
      }
      fechar = suave(fechar, aFechar, dt, 1.6);
      velGiro = suave(velGiro, aGiro, dt, 2.5);
      velCiclo = suave(velCiclo, aCiclo, dt, 2);
      nPulsos = suave(nPulsos, aPulsos, dt, 3);
      velPulso = suave(velPulso, aVelP, dt, 4);
      tamPontos = suave(tamPontos, aTam, dt, 6);
      reage = suave(reage, aReage, dt, 3);
      fala = suave(fala, aFala, dt, 3);
      off = suave(off, aOff, dt, 2);
      nivelS = suave(nivelS, nivel, dt, 14);

      // giro da referência: rot .005 e spin .012 por quadro a 60 fps
      rot += dt * 0.3 * velGiro;
      spin += dt * 0.72 * velGiro;
      ciclo += (dt / CICLO) * velCiclo;
      if (ciclo >= 1) ciclo -= Math.floor(ciclo);
      brilhoT += dt * (off > 0.5 ? 0.3 : 1 + fala * nivelS);

      var cyc = ciclo, mc;
      if (cyc < 0.22) mc = 0;
      else if (cyc < 0.42) mc = easeInOut((cyc - 0.22) / 0.2);
      else if (cyc < 0.8) mc = 1;
      else mc = 1 - easeInOut((cyc - 0.8) / 0.2);
      var m = mc + (1 - mc) * fechar;

      var x0 = q.x || 0, y0 = q.y || 0, w = q.w || 680, h = q.h || 560;
      var base = Math.min(w, h);
      if (!(base > 4)) return;
      var cx = x0 + w / 2, cy = y0 + h / 2, R = base * 0.4;
      // listening: a galáxia "respira" com o microfone
      R *= 1 + reage * nivelS * 0.05;
      var kTam = Math.sqrt(R / 176);
      if (kTam < 0.7) kTam = 0.7;
      else if (kTam > 1.5) kTam = 1.5;

      var iOff = Math.round(off * OFF_PASSOS);
      ctx.save();
      ctx.beginPath();
      ctx.rect(x0, y0, w, h);
      ctx.clip();

      // ---- halo (só na área; sem halo na prévia) ----
      if (!previa) {
        if (!cor.haloTeal) {
          cor.haloTeal = halo(ctx, cor.rgbEscura, 0.28);
          cor.haloNuvem = halo(ctx, cor.rgbNuvem, 0.1);
          cor.haloErro = halo(ctx, cor.rgbErro, 0.14);
        }
        ctx.save();
        ctx.translate(cx, cy);
        ctx.scale(R, R);
        var wNuvem = m * (1 - off), wTeal = (1 - m) * (1 - off);
        var hb = 1 + fala * nivelS * 0.8;
        ctx.beginPath();
        ctx.arc(0, 0, 1.4, 0, DOIS_PI);
        if (wTeal > 0.01) { ctx.globalAlpha = Math.min(1, wTeal); ctx.fillStyle = cor.haloTeal; ctx.fill(); }
        if (wNuvem > 0.01) { ctx.globalAlpha = Math.min(1, wNuvem * hb); ctx.fillStyle = cor.haloNuvem; ctx.fill(); }
        if (off > 0.01) { ctx.globalAlpha = off; ctx.fillStyle = cor.haloErro; ctx.fill(); }
        ctx.restore();
        ctx.globalAlpha = 1;
      }

      // ---- projeção ----
      var cr = Math.cos(rot), sr = Math.sin(rot);
      var ti = 0.45 - m * 0.15, ci = Math.cos(ti), si = Math.sin(ti);
      var cs = Math.cos(spin), ss = Math.sin(spin);
      var um = 1 - m;
      var onda = reage * nivelS;
      for (i = 0; i < N; i++) {
        var rx = gx[i] * cs - gz[i] * ss, rz = gx[i] * ss + gz[i] * cs;
        var px = rx * um + bx[i] * m, py = gy[i] * um + by[i] * m, pz = rz * um + bz[i] * m;
        if (onda > 0.002) {
          var f = 1 + onda * (0.04 + 0.07 * Math.sin(ph[i] * 5 + brilhoT * 7));
          px *= f; py *= f; pz *= f;
        }
        var x1 = px * cr - pz * sr, z1 = px * sr + pz * cr;
        var y1 = py * ci - z1 * si, z2 = py * si + z1 * ci, pp = 2.8 / (2.8 + z2);
        var o = i * 3;
        P[o] = cx + x1 * R * pp;
        P[o + 1] = cy + y1 * R * pp;
        var d = (1 - z2) / 2;
        P[o + 2] = d;
        var fb = 0;
        while (fb < NB - 1 && d > BORDAS[fb]) fb++;
        if (off < 0.5 && ph[i] < 0.8 && Math.sin(brilhoT * 3 + ph[i] * 3) > 0.4) fb = NB; // quente
        faixa[i] = fb;
      }

      var passo = previa ? 2 : 1;

      // ---- sinapses e impulsos (só quando há cérebro) ----
      if (m > 0.05) {
        ctx.lineWidth = Math.max(0.4, 0.6 * kTam);
        ctx.strokeStyle = cor.linha[iOff];
        ctx.globalAlpha = Math.min(1, (0.3 + fala * nivelS * 0.25) * m * (1 - off * 0.4));
        ctx.beginPath();
        for (var l = 0; l < NL; l += passo) {
          var a3 = la[l] * 3, b3 = lb[l] * 3;
          ctx.moveTo(P[a3], P[a3 + 1]);
          ctx.lineTo(P[b3], P[b3 + 1]);
        }
        ctx.stroke();

        var np = Math.round(nPulsos);
        if (previa) np = Math.ceil(np / 2);
        var vp = 0.72 * velPulso;
        var rNuc = 1.8 * kTam * (1 + fala * nivelS * 0.8);
        var rBri = 5 * kTam * (1 + fala * nivelS * 0.6);
        // avança todos (mesmo os inativos, para não "acordarem" juntos)
        for (var k = 0; k < MAX_PULSOS; k++) {
          pt[k] += dt * vp * pv[k];
          if (pt[k] > 1) {
            pt[k] -= Math.floor(pt[k]);
            pl[k] = Math.floor(rnd() * NL);
          }
        }
        ctx.fillStyle = cor.quente[iOff];
        // brilho largo (um caminho só)
        ctx.globalAlpha = Math.min(1, 0.15 * m * (1 + fala * nivelS));
        ctx.beginPath();
        for (k = 0; k < np; k++) {
          var A = la[pl[k]] * 3, Bq = lb[pl[k]] * 3, u2 = pt[k];
          var qx = P[A] + (P[Bq] - P[A]) * u2, qy = P[A + 1] + (P[Bq + 1] - P[A + 1]) * u2;
          ctx.moveTo(qx + rBri, qy);
          ctx.arc(qx, qy, rBri, 0, DOIS_PI);
        }
        ctx.fill();
        // núcleo
        ctx.globalAlpha = 0.95 * m * (1 - off * 0.3);
        ctx.beginPath();
        for (k = 0; k < np; k++) {
          A = la[pl[k]] * 3; Bq = lb[pl[k]] * 3; u2 = pt[k];
          qx = P[A] + (P[Bq] - P[A]) * u2; qy = P[A + 1] + (P[Bq + 1] - P[A + 1]) * u2;
          ctx.moveTo(qx + rNuc, qy);
          ctx.arc(qx, qy, rNuc, 0, DOIS_PI);
        }
        ctx.fill();
      }

      // ---- pontos, em lotes por faixa de profundidade ----
      var tam = kTam * tamPontos * (1 + reage * nivelS * 0.5);
      var brilhoOff = 1 - off * 0.35;
      for (var fx = 0; fx <= NB; fx++) {
        var quente = fx === NB;
        if (quente) {
          if (off >= 0.5) break;
          ctx.fillStyle = cor.quente[iOff];
          ctx.globalAlpha = 0.9;
        } else {
          ctx.fillStyle = cor.banda[FAIXA_COR[fx]][iOff];
          ctx.globalAlpha = (0.25 + FAIXA_D[fx] * 0.75) * brilhoOff;
        }
        ctx.beginPath();
        var tem = false;
        for (i = 0; i < N; i += passo) {
          if (faixa[i] !== fx) continue;
          var o2 = i * 3, dd2 = P[o2 + 2];
          if (dd2 < 0) dd2 = 0;
          else if (dd2 > 1) dd2 = 1;
          var sz = (0.6 + dd2 * 1.7) * tam;
          ctx.rect(P[o2] - sz / 2, P[o2 + 1] - sz / 2, sz, sz);
          tem = true;
        }
        if (tem) ctx.fill();
      }

      ctx.globalAlpha = 1;
      ctx.restore();
    }

    return { desenhar: desenhar };
  }

  window.JarvisVisuais.registrar({
    id: "galaxia",
    nome: "Galáxia Neural",
    descricao: "Galáxia de pontos que se fecha num cérebro, nas cores de 2026.",
    paleta: "nuvem",
    hud: true,
    criar: criar,
  });
})();
