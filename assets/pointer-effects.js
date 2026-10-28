/**
 * Lightweight Canvas2D adaptation of ClickSpark from React Bits.
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
  const BURST_MS = 500;
  const bursts = [];
  let raf = 0, destroyed = false, ratio = 1;

  const disabled = () => !ctx || paused || reduced.matches || document.hidden;
  const clearCanvas = () => ctx?.clearRect(0, 0, innerWidth, innerHeight);
  const stop = () => {
    cancelAnimationFrame(raf);
    raf = 0;
    bursts.length = 0;
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
    ctx.strokeStyle = dark || burst.filled ? "#fff" : "#a60321";
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
    while (bursts.length && now - bursts[0].at >= BURST_MS) bursts.shift();
    clearCanvas();
    if (!bursts.length) {
      canvas.dataset.state = "idle";
      return;
    }
    const dark = document.documentElement.dataset.theme === "dark";
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
  const onClick = (event) => {
    if (disabled() || event.button > 0) return;
    const target = event.target instanceof Element ? event.target : null;
    if (!target || target.closest('input,textarea,select,label,[contenteditable="true"]')) return;
    const control = target.closest('button,a.button');
    if (!control || control.matches(':disabled,[aria-disabled="true"],[data-action="toggleMotion"]')) return;
    const rect = control?.getBoundingClientRect();
    if (rect && (!rect.width || !rect.height)) return;
    const x = event.detail === 0 && rect ? rect.left + rect.width / 2 : event.clientX;
    const y = event.detail === 0 && rect ? rect.top + rect.height / 2 : event.clientY;
    bursts.push({
      x, y, at: performance.now(),
      filled: Boolean(control?.matches('.primary,.dark,.logo-mark')),
    });
    if (bursts.length > 12) bursts.shift();
    wake();
  };
  const onPreferenceChange = () => stop();
  // Capture before page handlers disable/replace the clicked button.
  document.addEventListener("click", onClick, true);
  document.addEventListener("visibilitychange", onPreferenceChange);
  reduced.addEventListener("change", onPreferenceChange);
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
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("visibilitychange", onPreferenceChange);
      reduced.removeEventListener("change", onPreferenceChange);
      window.removeEventListener("resize", resize);
      canvas.remove();
    },
  };
}
