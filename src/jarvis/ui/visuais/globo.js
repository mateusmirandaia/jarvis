// Globo: o orb original do Jarvis (esfera de particulas em espiral de Fibonacci),
// portado para o contrato dos visuais. Mesmo comportamento e mesmas cores do orb antigo.
JarvisVisuais.registrar({
  id: "globo",
  nome: "Globo",
  descricao: "O orb original: esfera de partículas que gira e pulsa com a voz.",
  paleta: "petroleo",
  hud: false,

  criar() {
    // Parametros por estado (iguais ao orb antigo): velocidade de giro, brilho e mistura
    // de cor (o orb antigo ja mistura um pouco de limao ao ouvir, por isso usa a propria
    // tabela em vez de q.mistura).
    const ESTADOS = {
      idle: { giro: 0.15, brilho: 0.25, mistura: 0 },
      listening: { giro: 0.25, brilho: 0.45, mistura: 0.25 },
      thinking: { giro: 1.1, brilho: 0.55, mistura: 0.55 },
      speaking: { giro: 0.45, brilho: 0.9, mistura: 1 },
      offline: { giro: 0.05, brilho: 0.2, mistura: 0 },
    };

    // Pontos distribuidos de forma uniforme numa esfera (espiral de Fibonacci).
    const N = 900;
    const px = new Float32Array(N);
    const py = new Float32Array(N);
    const pz = new Float32Array(N);
    const fase = new Float32Array(N);
    const angDourado = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const a = angDourado * i;
      px[i] = Math.cos(a) * r;
      py[i] = y;
      pz[i] = Math.sin(a) * r;
      fase[i] = Math.random() * Math.PI * 2;
    }

    // Cache de cores (a paleta so muda se o shell trocar de visual; por via das duvidas,
    // reconverte quando a string muda).
    const cache = { chave: "", escura: [14, 94, 90], destaque: [198, 240, 0], erro: [226, 72, 59] };
    function hexParaRgb(hex, padrao) {
      const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ""));
      if (!m) return padrao;
      const n = parseInt(m[1], 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }
    function atualizarCores(cores) {
      const chave = cores ? cores.escura + cores.destaque + cores.erro : "";
      if (chave === cache.chave) return;
      cache.chave = chave;
      cache.escura = hexParaRgb(cores && cores.escura, [14, 94, 90]);
      cache.destaque = hexParaRgb(cores && cores.destaque, [198, 240, 0]);
      cache.erro = hexParaRgb(cores && cores.erro, [226, 72, 59]);
    }

    let rotacao = 0;
    let giroAtual = ESTADOS.idle.giro;
    let brilhoAtual = ESTADOS.idle.brilho;
    let misturaAtual = 0;

    return {
      desenhar(ctx, q) {
        atualizarCores(q.cores);
        const cfg = ESTADOS[q.estado] || ESTADOS.idle;
        const offline = q.estado === "offline";
        const nivel = q.nivel;

        // Suavizacao igual a do orb antigo (0.05 por quadro a 60 fps), independente do fps.
        const k = 1 - Math.pow(0.95, q.dt * 60);
        giroAtual += (cfg.giro - giroAtual) * k;
        brilhoAtual += (cfg.brilho - brilhoAtual) * k;
        misturaAtual += (cfg.mistura - misturaAtual) * k;
        const mistura = misturaAtual;
        rotacao += giroAtual * q.dt;

        const cx = q.x + q.w / 2;
        const cy = q.y + q.h / 2;
        const respiracao = Math.sin(q.t * 1.6) * 0.02;
        const raio = Math.min(q.w, q.h) * 0.27 * (1 + respiracao + nivel * 0.28);

        const E = cache.escura, L = cache.destaque;
        const base = offline
          ? cache.erro
          : [
              Math.round(E[0] + (L[0] - E[0]) * mistura),
              Math.round(E[1] + (L[1] - E[1]) * mistura),
              Math.round(E[2] + (L[2] - E[2]) * mistura),
            ];
        // Cor dos pontos da frente: base puxada para o destaque.
        const mf = Math.min(1, 0.35 + nivel * 0.5);
        const frente = offline
          ? base
          : [
              Math.round(base[0] + (L[0] - base[0]) * mf),
              Math.round(base[1] + (L[1] - base[1]) * mf),
              Math.round(base[2] + (L[2] - base[2]) * mf),
            ];
        const rgbBase = base[0] + "," + base[1] + "," + base[2];
        const rgbFrente = frente[0] + "," + frente[1] + "," + frente[2];

        // Brilho atras da esfera.
        const halo = ctx.createRadialGradient(cx, cy, raio * 0.2, cx, cy, raio * 2.1);
        const alfaHalo = Math.min(1, 0.1 + brilhoAtual * 0.18 + nivel * 0.35);
        halo.addColorStop(0, "rgba(" + rgbBase + "," + alfaHalo.toFixed(3) + ")");
        halo.addColorStop(1, "rgba(" + rgbBase + ",0)");
        ctx.fillStyle = halo;
        ctx.fillRect(q.x, q.y, q.w, q.h);

        // Particulas: gira, ondula (pensando/falando) e projeta em perspectiva.
        const cosR = Math.cos(rotacao), sinR = Math.sin(rotacao);
        const incl = 0.35, cosI = Math.cos(incl), sinI = Math.sin(incl);
        const onda = (q.estado === "thinking" ? 0.08 : 0) + nivel * 0.18;
        const escalaPonto = q.previa ? 0.7 : 1;
        const tau = Math.PI * 2;

        for (let i = 0; i < N; i++) {
          const d = 1 + Math.sin(q.t * 3 + fase[i] + py[i] * 4) * onda;
          const x = px[i] * d, y = py[i] * d, z = pz[i] * d;
          const x1 = x * cosR - z * sinR;
          const z1 = x * sinR + z * cosR;
          const y1 = y * cosI - z1 * sinI;
          const z2 = y * sinI + z1 * cosI;
          const persp = 2.6 / (2.6 + z2);
          const sx = cx + x1 * raio * persp;
          const sy = cy + y1 * raio * persp;
          const prof = (1 - z2) / 2; // 0 = fundo, 1 = frente
          const alfa = 0.15 + prof * (0.55 + brilhoAtual * 0.4);
          const tam = (0.6 + prof * 1.4) * (1 + nivel * 0.6) * escalaPonto;
          ctx.fillStyle = "rgba(" + (prof > 0.7 ? rgbFrente : rgbBase) + "," + alfa.toFixed(3) + ")";
          ctx.beginPath();
          ctx.arc(sx, sy, tam, 0, tau);
          ctx.fill();
        }

        // Anel fino ao redor, que acende quando ele fala.
        ctx.strokeStyle = "rgba(" + L[0] + "," + L[1] + "," + L[2] + "," + (0.05 + nivel * 0.5).toFixed(3) + ")";
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, cy, raio * 1.25, 0, tau);
        ctx.stroke();
      },
    };
  },
});
