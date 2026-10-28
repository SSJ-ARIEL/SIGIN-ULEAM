/**
 * Lightweight Canvas2D adaptations of GlowCursor and ClickSpark from React Bits.
 * Original components: https://github.com/DavidHDev/react-bits/tree/main/src/content/Animations
 * Copyright (c) 2026 David Haz; license: ./vendor/licenses/react-bits.md.
 * No fluid simulation, cursor replacement, UI interception or external dependencies.
 */
export function createPointerEffects({ paused = false } = {}) {
  const canvas = document.createElement("canvas");
  canvas.className = "pointer-effects";
  canvas.setAttribute("aria-hidden", "true");
  Object.assign(canvas.style, {
    position: "fixed", inset: "0", width: "100%", height: "100%",
    pointerEvents: "none", zIndex: "50",
  });
  document.body.append(canvas);
  const ctx = canvas.getContext("2d");
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const fine = matchMedia("(hover: hover) and (pointer: fine)");
  const LINGER = 1400;
  const BURST_MS = 500;
  const GLOW_RGB = "95,139,255"; // Requested #5f8bff.
  const points = [], bursts = [];
  let raf = 0, destroyed = false, ratio = 1;
  let lastSample = 0, lastPoint = null;

  const disabled = () => !ctx || paused || reduced.matches || document.hidden;
  const clearCanvas = () => ctx?.clearRect(0, 0, innerWidth, innerHeight);
  const stop = () => {
    cancelAnimationFrame(raf);
    raf = 0;
    points.length = bursts.length = 0;
    lastPoint = null;
    clearCanvas();
    canvas.dataset.state = disabled() ? "disabled" : "idle";
  };
  const resize = () => {
    ratio = Math.min(devicePixelRatio || 1, 1.5);
    canvas.width = Math.max(1, Math.round(innerWidth * ratio));
    canvas.height = Math.max(1, Math.round(innerHeight * ratio));
    ctx?.setTransform(ratio, 0, 0, ratio, 0, 0);
    stop();
  };
  const easeOut = (t) => 1 - (1 - t) ** 3;
  const smoothstep = (a, b, t) => {
    const v = Math.max(0, Math.min(1, (t - a) / (b - a)));
    return v * v * (3 - 2 * v);
  };
  const drawTrail = (now, dark) => {
    if (points.length < 2) return;
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    // A narrow luminous core with a soft blue halo: visible without washing out text.
    const intensity = 1.3, glow = 1.2;
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1], b = points[i];
      const life = Math.max(0, 1 - (now - b.at) / LINGER);
      const opacity = life ** 2 * intensity * (dark ? 0.6 : 0.46);
      if (opacity <= 0.005) continue;
      ctx.strokeStyle = `rgba(${GLOW_RGB},${opacity})`;
      ctx.shadowColor = `rgba(${GLOW_RGB},${opacity * 0.85})`;
      ctx.shadowBlur = 15 * glow;
      ctx.lineWidth = 3 * (0.4 + 0.6 * life);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      const next = points[i + 1];
      if (next) ctx.quadraticCurveTo(b.x, b.y, (b.x + next.x) / 2, (b.y + next.y) / 2);
      else ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.restore();
  };
  const drawBurst = (burst, now, dark) => {
    const progress = Math.min(1, (now - burst.at) / BURST_MS);
    const distance = 30 * easeOut(progress);
    const length = 14 * (1 - progress) ** 1.6;
    const alpha = 1 - smoothstep(0.55, 1, progress);
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineWidth = 2;
    ctx.globalAlpha = alpha;
    // Keep the supplied white sparks on dark/filled actions; burgundy is legible
    // on the pale surfaces of light mode.
    ctx.strokeStyle = burst.kind === "cursor" ? "#5f8bff" : dark || burst.filled ? "#fff" : "#a60321";
    if (burst.kind === "cursor") {
      ctx.shadowColor = "#5f8bff";
      ctx.shadowBlur = 10;
    }
    for (let i = 0; i < 8; i++) {
      const angle = (i * Math.PI * 2) / 8;
      const x = Math.cos(angle), y = Math.sin(angle);
      ctx.beginPath();
      ctx.moveTo(burst.x + x * distance, burst.y + y * distance);
      ctx.lineTo(burst.x + x * (distance + length), burst.y + y * (distance + length));
      ctx.stroke();
    }
    ctx.restore();
  };
  const tick = (now) => {
    raf = 0;
    if (destroyed || disabled()) return stop();
    while (points.length && now - points[0].at >= LINGER) points.shift();
    while (bursts.length && now - bursts[0].at >= BURST_MS) bursts.shift();
    clearCanvas();
    if (!points.length && !bursts.length) {
      canvas.dataset.state = "idle";
      return;
    }
    const dark = document.documentElement.dataset.theme === "dark";
    drawTrail(now, dark);
    bursts.forEach((burst) => drawBurst(burst, now, dark));
    canvas.dataset.state = "running";
    raf = requestAnimationFrame(tick);
  };
  const wake = () => {
    if (!destroyed && !disabled() && !raf) {
      canvas.dataset.state = "running";
      raf = requestAnimationFrame(tick);
    }
  };
  const onMove = (event) => {
    if (disabled() || !fine.matches || event.pointerType !== "mouse") return;
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest('input,textarea,select,[contenteditable="true"]')) {
      points.length = 0;
      lastPoint = null;
      if (!bursts.length) stop();
      return;
    }
    const now = performance.now();
    // Bound sampling/memory on high-refresh mice, while retaining smooth curves.
    if (now - lastSample < 8) return;
    if (lastPoint && Math.hypot(event.clientX - lastPoint.x, event.clientY - lastPoint.y) < 1) return;
    if (!lastPoint || now - lastSample > 120) points.length = 0;
    const point = { x: event.clientX, y: event.clientY, at: now };
    points.push(point);
    if (points.length > 160) points.shift();
    lastPoint = point;
    lastSample = now;
    wake();
  };
  const onLeave = () => { lastPoint = null; };
  const onClick = (event) => {
    if (disabled() || event.button > 0) return;
    const target = event.target instanceof Element ? event.target : null;
    if (!target || target.closest('input,textarea,select,label,[contenteditable="true"]')) return;
    const control = target.closest('button,a.button');
    if (control?.matches(':disabled,[aria-disabled="true"],[data-action="toggleMotion"]')) return;
    if (!control) {
      // The cursor's own click burst belongs to empty decorative space, never text.
      if (!fine.matches || event.detail === 0 || target.closest('a,p,h1,h2,h3,h4,h5,h6,span,small,li,td,th,summary,[role="button"]')) return;
    }
    const rect = control?.getBoundingClientRect();
    if (rect && (!rect.width || !rect.height)) return;
    const x = event.detail === 0 && rect ? rect.left + rect.width / 2 : event.clientX;
    const y = event.detail === 0 && rect ? rect.top + rect.height / 2 : event.clientY;
    bursts.push({
      x, y, at: performance.now(), kind: control ? "button" : "cursor",
      filled: Boolean(control?.matches('.primary,.dark,.logo-mark')),
    });
    if (bursts.length > 12) bursts.shift();
    wake();
  };
  const onPreferenceChange = () => stop();
  document.addEventListener("pointermove", onMove, { passive: true });
  document.documentElement.addEventListener("pointerleave", onLeave);
  // Capture before page handlers disable/replace the clicked button.
  document.addEventListener("click", onClick, true);
  document.addEventListener("visibilitychange", onPreferenceChange);
  reduced.addEventListener("change", onPreferenceChange);
  fine.addEventListener("change", onPreferenceChange);
  window.addEventListener("resize", resize, { passive: true });
  resize();
  return {
    setPaused(value) {
      paused = Boolean(value);
      stop();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      stop();
      document.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("visibilitychange", onPreferenceChange);
      reduced.removeEventListener("change", onPreferenceChange);
      fine.removeEventListener("change", onPreferenceChange);
      window.removeEventListener("resize", resize);
      canvas.remove();
    },
  };
}
