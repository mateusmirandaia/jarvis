/* Visual "cerebro" — Globo Cognitivo (paleta aurora).
 * Globo de 760 pontos (espiral de Fibonacci) girando que se transforma num cérebro
 * (2 hemisférios + cerebelo, com sulcos), com ligações violeta e impulsos âmbar correndo
 * pelas ligações; depois volta a ser globo. Ciclo de ~12 s.
 * Toda a geometria (pontos, ligações por vizinhos) é pré-calculada em criar().
 * Pontos desenhados em lotes (cor x faixa de profundidade) para ficar leve.
 */
(function () {
  "use strict";

  var N = 760;
  var MAX_IMPULSOS = 80;
  var CICLO = 12; // segundos do ciclo globo -> cérebro -> globo
  var PERSP = 2.8;
  var INCL = 0.32; // inclinação fixa do eixo (rad)
  var NB = 4; // faixas de profundidade
  // limites das faixas em d (0 = fundo, 1 = frente) e opacidade de cada faixa
  var FAIXA_ALFA = [0.31, 0.56, 0.77, 0.93];

  var PADRAO = {
    fundo: "#05070F",
    texto: "#E6F1FF",
    ouvindo: "#38E1FF",
    pensando: "#8B7CFF",
    falando: "#FFB23F",
    erro: "#FF5C7A",
  };

  function suave(x) {
    return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  }

  function lerHex(hex, saida, o) {
    var h = String(hex || "").replace("#", "");
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var v = parseInt(h, 16);
    if (!(v >= 0) || h.length !== 6) v = 0xffffff;
    saida[o] = (v >> 16) & 255;
    saida[o + 1] = (v >> 8) & 255;
    saida[o + 2] = v & 255;
  }

  function criar() {
    var semente = 7;
    function rnd() {
      semente = (semente * 16807) % 2147483647;
      return semente / 2147483647;
    }

    // ---- geometria (igual à referência) ----
    var ga = Math.PI * (3 - Math.sqrt(5));
    var SX = new Float32Array(N), SY = new Float32Array(N), SZ = new Float32Array(N);
    var BX = new Float32Array(N), BY = new Float32Array(N), BZ = new Float32Array(N);
    var FASE = new Float32Array(N);
    var i, j;
    for (i = 0; i < N; i++) {
      var yy = 1 - (i / (N - 1)) * 2, rr = Math.sqrt(1 - yy * yy);
      SX[i] = Math.cos(ga * i) * rr;
      SY[i] = yy;
      SZ[i] = Math.sin(ga * i) * rr;
      FASE[i] = rnd() * 6.28;
      var bx, by, bz;
      if (i < 40) {
        // cerebelo
        var a = rnd() * 6.28, b = rnd() * 3.14;
        bx = Math.cos(a) * Math.sin(b) * 0.28;
        by = 0.42 + Math.cos(b) * 0.16;
        bz = -0.5 + Math.sin(a) * Math.sin(b) * 0.22;
      } else {
        // hemisférios com sulcos
        var lado = i % 2 ? 1 : -1, u = rnd() * 6.28, v = Math.acos(2 * rnd() - 1);
        var ex = Math.cos(u) * Math.sin(v), ey = Math.cos(v), ez = Math.sin(u) * Math.sin(v);
        if (lado * ex < -0.2) ex = lado * (-0.2 + (lado * ex + 0.2) * 0.15);
        var g = 1 + 0.07 * Math.sin(9 * u + 3 * v) * Math.sin(7 * v);
        bx = lado * 0.06 + ex * 0.46 * g + lado * 0.36;
        by = ey * 0.5 * g - 0.02;
        bz = ez * 0.72 * g * (1 + 0.08 * ey);
      }
      BX[i] = bx * 1.05;
      BY[i] = by * 1.05;
      BZ[i] = bz * 1.05;
    }

    // ligações: metade dos pontos como origem (como na referência), mas alternando a
    // paridade (0, 3, 4, 7, 8, ...) para cobrir os DOIS hemisférios (lado = i % 2);
    // 2 vizinhos mais próximos de cada origem (O(n²), uma vez)
    var la = [], lb = [];
    for (var o = 0; o < N; o += 2) {
      i = o + ((o >> 1) & 1);
      if (i >= N) break;
      var d0 = 9, j0 = -1, d1 = 9, j1 = -1;
      for (j = 0; j < N; j++) {
        if (j === i) continue;
        var dx = BX[i] - BX[j], dy = BY[i] - BY[j], dz = BZ[i] - BZ[j];
        var dd = dx * dx + dy * dy + dz * dz;
        if (dd < d1) {
          d1 = dd;
          j1 = j;
          if (d1 < d0) {
            var td = d0, tj = j0;
            d0 = d1;
            j0 = j1;
            d1 = td;
            j1 = tj;
          }
        }
      }
      if (j0 >= 0 && d0 < 0.03) { la.push(i); lb.push(j0); }
      if (j1 >= 0 && d1 < 0.03) { la.push(i); lb.push(j1); }
    }
    var NL = la.length;
    var LA = new Int16Array(la), LB = new Int16Array(lb);

    // impulsos
    var impL = new Int32Array(MAX_IMPULSOS);
    var impT = new Float32Array(MAX_IMPULSOS);
    var impV = new Float32Array(MAX_IMPULSOS);
    for (i = 0; i < MAX_IMPULSOS; i++) {
      impL[i] = Math.floor(rnd() * NL);
      impT[i] = rnd();
      impV[i] = 0.6 + rnd() * 1.2;
    }

    // buffers do quadro (reutilizados)
    var P = new Float32Array(N * 3);
    var balde = new Int16Array(3 * NB * N); // 3 cores x NB faixas
    var nBalde = new Int32Array(3 * NB);
    var TAM = new Float32Array(N);

    // estado interno suavizado
    var rot = 0, fase = 0, piscar = 0, tAnt = -1;
    var wOuv = 0, wPen = 0, wFal = 0, wOff = 0, segura = 0;
    var velRot = 0.36, velImp = 1, nImp = 26;
    var nivelS = 0;

    // cores (rgb) — relidas só quando a paleta muda
    var paletaRef = null;
    var RGB = new Float32Array(18); // texto, ouvindo, pensando, falando, erro, fundo

    function mix(o1, o2, k, o3, k2) {
      // retorna "rgb()" de lerp(lerp(c1,c2,k), c3, k2)
      var r = RGB[o1] + (RGB[o2] - RGB[o1]) * k;
      var g = RGB[o1 + 1] + (RGB[o2 + 1] - RGB[o1 + 1]) * k;
      var b = RGB[o1 + 2] + (RGB[o2 + 2] - RGB[o1 + 2]) * k;
      r += (RGB[o3] - r) * k2;
      g += (RGB[o3 + 1] - g) * k2;
      b += (RGB[o3 + 2] - b) * k2;
      return "rgb(" + (r | 0) + "," + (g | 0) + "," + (b | 0) + ")";
    }

    function rgba(o, a) {
      return "rgba(" + RGB[o] + "," + RGB[o + 1] + "," + RGB[o + 2] + "," + a + ")";
    }

    function desenhar(ctx, q) {
      var t = q.t || 0;
      var dt = q.dt;
      if (!(dt >= 0)) dt = tAnt < 0 ? 0 : Math.max(0, Math.min(0.1, t - tAnt));
      if (dt > 0.1) dt = 0.1;
      tAnt = t;
      var estado = q.estado || "idle";
      var nivel = q.nivel > 0 ? Math.min(1, q.nivel) : 0;
      var previa = !!q.previa;

      // paleta
      var c = q.cores || PADRAO;
      if (c !== paletaRef) {
        paletaRef = c;
        lerHex(c.texto || PADRAO.texto, RGB, 0);
        lerHex(c.ouvindo || c.primaria || PADRAO.ouvindo, RGB, 3);
        lerHex(c.pensando || c.escura || PADRAO.pensando, RGB, 6);
        lerHex(c.falando || c.destaque || PADRAO.falando, RGB, 9);
        lerHex(c.erro || PADRAO.erro, RGB, 12);
        lerHex(c.fundo || PADRAO.fundo, RGB, 15);
        hc.chave = "";
      }

      // pesos de estado (suaves, sem saltos)
      var k = Math.min(1, dt * 2.5);
      wOuv += ((estado === "listening" ? 1 : 0) - wOuv) * k;
      wPen += ((estado === "thinking" ? 1 : 0) - wPen) * k;
      wFal += ((estado === "speaking" ? 1 : 0) - wFal) * k;
      wOff += ((estado === "offline" ? 1 : 0) - wOff) * k;
      var alvoSegura = estado === "thinking" || estado === "speaking" ? 1 : 0;
      segura += (alvoSegura - segura) * Math.min(1, dt * 1.4);
      nivelS += (nivel - nivelS) * Math.min(1, dt * 12);

      // velocidades
      var alvoRot = 0.36 * (1 + 0.15 * wOuv + 1.6 * wPen + 0.5 * wFal) * (1 - 0.92 * wOff);
      velRot += (alvoRot - velRot) * Math.min(1, dt * 2);
      var alvoImp = (1 + 1.4 * wPen + wFal * (0.3 + 1.6 * nivelS)) * (1 - 0.9 * wOff);
      velImp += (alvoImp - velImp) * Math.min(1, dt * 4);
      var alvoN = 26 + 50 * wPen + wFal * (8 + 30 * nivelS) - 16 * wOff;
      nImp += (alvoN - nImp) * Math.min(1, dt * 3);

      rot += velRot * dt;
      piscar += dt * (1 + 1.5 * wPen + wFal * (0.5 + 2 * nivelS)) * (1 - 0.85 * wOff);

      // ciclo automático; ouvindo: fica mais tempo no globo
      var cyc0 = fase - Math.floor(fase);
      var velFase = (1 - 0.95 * wOff) / CICLO;
      if (cyc0 < 0.2) velFase *= 1 - 0.6 * wOuv;
      else velFase *= 1 + 0.4 * wOuv;
      fase += velFase * dt;
      var cyc = fase - Math.floor(fase);
      var mAuto;
      if (cyc < 0.2) mAuto = 0;
      else if (cyc < 0.4) mAuto = suave((cyc - 0.2) / 0.2);
      else if (cyc < 0.8) mAuto = 1;
      else mAuto = 1 - suave((cyc - 0.8) / 0.2);
      var m = mAuto + (1 - mAuto) * segura;

      // área
      var ax = q.x || 0, ay = q.y || 0;
      var aw = q.w > 0 ? q.w : 640, ah = q.h > 0 ? q.h : 440;
      var cx = ax + aw / 2, cy = ay + ah / 2;
      var R = Math.min(aw, ah) * 0.36;
      var escPonto = Math.max(0.55, Math.min(1.15, Math.min(aw, ah) / 440));

      // cores do quadro
      var mc = m < 0.35 ? 0 : m > 0.65 ? 1 : (m - 0.35) / 0.3; // ciano -> violeta
      var corFundo = mix(3, 6, mc, 12, wOff);
      var corFrente = mix(0, 0, 0, 12, wOff * 0.6);
      var corQuente = mix(9, 9, 0, 12, wOff);
      var CORES = [corFundo, corFrente, corQuente];
      var corLig = mix(6, 6, 0, 12, wOff);

      var cr = Math.cos(rot), sr = Math.sin(rot), ci = Math.cos(INCL), si = Math.sin(INCL);

      // halo (só na área)
      if (!previa) {
        desenharHalo(ctx, cx, cy, R, ax, ay, aw, ah, mc, wOff, wFal, nivelS);
      }

      // projeção
      var pulso = 0.03 * (1 - m);
      var reage = wOuv * nivelS * 0.07;
      var tt = t;
      for (i = 0; i < N; i++) {
        var w = 1 + Math.sin(tt * 2.2 + FASE[i]) * pulso + reage * (0.6 + 0.4 * Math.sin(tt * 9 + FASE[i] * 2));
        var x = (SX[i] + (BX[i] - SX[i]) * m) * w;
        var y = (SY[i] + (BY[i] - SY[i]) * m) * w;
        var z = (SZ[i] + (BZ[i] - SZ[i]) * m) * w;
        var x1 = x * cr - z * sr, z1 = x * sr + z * cr;
        var y1 = y * ci - z1 * si, z2 = y * si + z1 * ci;
        var pp = PERSP / (PERSP + z2);
        P[i * 3] = cx + x1 * R * pp;
        P[i * 3 + 1] = cy + y1 * R * pp;
        P[i * 3 + 2] = z2;
      }

      // ligações e impulsos
      if (m > 0.05) {
        ctx.lineWidth = 0.6 * Math.max(0.8, escPonto);
        ctx.strokeStyle = corLig;
        ctx.globalAlpha = Math.min(1, 0.35 * m * (1 + 0.35 * wPen + 0.25 * wFal * nivelS));
        ctx.beginPath();
        for (i = 0; i < NL; i++) {
          var a3 = LA[i] * 3, b3 = LB[i] * 3;
          ctx.moveTo(P[a3], P[a3 + 1]);
          ctx.lineTo(P[b3], P[b3 + 1]);
        }
        ctx.stroke();

        var nAtivos = Math.min(MAX_IMPULSOS, Math.ceil(previa ? nImp * 0.5 : nImp));
        var passo = 0.72 * velImp * dt;
        var raio = 1.8 * escPonto * (1 + wFal * nivelS * 0.4);
        var raioH = raio * (2.8 - 0.5 * wFal);
        ctx.fillStyle = corQuente;
        // brilho externo
        ctx.globalAlpha = Math.min(1, 0.18 * m * (1 + wFal * nivelS));
        ctx.beginPath();
        for (i = 0; i < nAtivos; i++) {
          impT[i] += passo * impV[i];
          if (impT[i] > 1) {
            impT[i] -= 1;
            impL[i] = Math.floor(rnd() * NL);
          }
          var ia = LA[impL[i]] * 3, ib = LB[impL[i]] * 3, f = impT[i];
          var px = P[ia] + (P[ib] - P[ia]) * f, py = P[ia + 1] + (P[ib + 1] - P[ia + 1]) * f;
          ctx.moveTo(px + raioH, py);
          ctx.arc(px, py, raioH, 0, 6.2832);
        }
        ctx.fill();
        // núcleo
        ctx.globalAlpha = Math.min(1, 0.95 * m * (0.75 + 0.25 * (1 - wFal) + 0.25 * wFal * nivelS));
        ctx.beginPath();
        for (i = 0; i < nAtivos; i++) {
          var ja = LA[impL[i]] * 3, jb = LB[impL[i]] * 3, g2 = impT[i];
          var qx = P[ja] + (P[jb] - P[ja]) * g2, qy = P[ja + 1] + (P[jb + 1] - P[ja + 1]) * g2;
          ctx.moveTo(qx + raio, qy);
          ctx.arc(qx, qy, raio, 0, 6.2832);
        }
        ctx.fill();
      }

      // pontos em baldes (cor x faixa)
      for (i = 0; i < 3 * NB; i++) nBalde[i] = 0;
      var limQuente = 0.9 + wFal * nivelS * 1.4 + wPen * 0.4;
      var escTam = escPonto * (1 + m * 0.15) * (1 + wFal * (0.25 + 0.35 * nivelS)) * (1 + wOuv * nivelS * 0.3);
      var passoI = previa ? 2 : 1;
      for (i = 0; i < N; i += passoI) {
        var dz = (1 - P[i * 3 + 2]) / 2;
        if (dz < 0) dz = 0;
        else if (dz > 1) dz = 1;
        TAM[i] = (0.6 + dz * 1.7) * escTam;
        var fx = dz < 0.3 ? 0 : dz < 0.6 ? 1 : dz < 0.8 ? 2 : 3;
        var cor = dz > 0.6 ? 1 : 0;
        if (m > 0.5 && FASE[i] < limQuente && wOff < 0.5) {
          var bl = 0.5 + 0.5 * Math.sin(piscar * 3 + FASE[i] * 3);
          if (bl > 0.7) cor = 2;
        }
        var bi = cor * NB + fx;
        balde[bi * N + nBalde[bi]++] = i;
      }
      for (var cc = 0; cc < 3; cc++) {
        ctx.fillStyle = CORES[cc];
        for (var fb = 0; fb < NB; fb++) {
          var idx = cc * NB + fb, n = nBalde[idx];
          if (!n) continue;
          ctx.globalAlpha = FAIXA_ALFA[fb] * (1 - 0.35 * wOff);
          ctx.beginPath();
          var base = idx * N;
          for (j = 0; j < n; j++) {
            var p = balde[base + j], s = TAM[p];
            ctx.rect(P[p * 3] - s / 2, P[p * 3 + 1] - s / 2, s, s);
          }
          ctx.fill();
        }
      }
      ctx.globalAlpha = 1;

      // anel do globo
      var aAnel = 0.25 * (1 - m);
      if (aAnel > 0.005) {
        ctx.strokeStyle = corFundo;
        ctx.globalAlpha = aAnel;
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.arc(cx, cy, R * 1.12, 0, 6.2832);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }

    // halos coloridos cacheados por geometria (ciano, violeta, âmbar, erro)
    var hc = { chave: "", ciano: null, violeta: null, ambar: null, erro: null };
    function desenharHalo(ctx, cx, cy, R, ax, ay, aw, ah, mc, off, fal, niv) {
      var chave = cx + "|" + cy + "|" + R + "|" + RGB[3] + RGB[6] + RGB[9] + RGB[12];
      if (chave !== hc.chave) {
        hc.chave = chave;
        hc.ciano = grad(ctx, cx, cy, R, 3, 0.18);
        hc.violeta = grad(ctx, cx, cy, R, 6, 0.22);
        hc.ambar = grad(ctx, cx, cy, R, 9, 0.16);
        hc.erro = grad(ctx, cx, cy, R, 12, 0.16);
      }
      var vivo = 1 - off;
      var aC = (1 - mc) * vivo, aV = mc * vivo, aA = fal * (0.25 + 0.75 * niv) * vivo;
      if (aC > 0.01) { ctx.globalAlpha = aC; ctx.fillStyle = hc.ciano; ctx.fillRect(ax, ay, aw, ah); }
      if (aV > 0.01) { ctx.globalAlpha = aV; ctx.fillStyle = hc.violeta; ctx.fillRect(ax, ay, aw, ah); }
      if (aA > 0.01) { ctx.globalAlpha = aA; ctx.fillStyle = hc.ambar; ctx.fillRect(ax, ay, aw, ah); }
      if (off > 0.01) { ctx.globalAlpha = off * 0.7; ctx.fillStyle = hc.erro; ctx.fillRect(ax, ay, aw, ah); }
      ctx.globalAlpha = 1;
    }
    function grad(ctx, cx, cy, R, o, a) {
      var g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.5);
      g.addColorStop(0, rgba(o, a));
      g.addColorStop(1, rgba(15, 0));
      return g;
    }

    return { desenhar: desenhar };
  }

  window.JarvisVisuais.registrar({
    id: "cerebro",
    nome: "Globo Cognitivo",
    descricao: "Globo de pontos que vira um cérebro com sinapses acendendo.",
    paleta: "aurora",
    hud: true,
    criar: criar,
  });
})();
