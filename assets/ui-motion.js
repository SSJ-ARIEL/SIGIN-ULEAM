/**
 * DOM adaptations of React Bits AnimatedContent, Magnet and AnimatedList.
 * Copyright (c) 2026 David Haz; see ./vendor/licenses/react-bits.md.
 * https://github.com/DavidHDev/react-bits/tree/main/src/content
 * Native Web Animations replace React/GSAP; application buttons retain their
 * semantics, handlers and stationary hit areas.
 */
export function createUiMotion(root, { paused = false } = {}) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const fine = matchMedia("(hover: hover) and (pointer: fine)");
  const animations = new Set();
  let observer = null, listObserver = null, frame = 0, interactionFrame = 0, magnets = [], activeMagnet = null;
  let pointerPressed = false;
  const heldAnimations = new Set();
  let lastKind = null, lastKey = null, destroyed = false;
  const allowed = () => !destroyed && !paused && !reduced.matches && !document.hidden;
  const resetMagnet = () => {
    if (activeMagnet) {
      activeMagnet.style.setProperty("--magnet-x", "0px");
      activeMagnet.style.setProperty("--magnet-y", "0px");
      activeMagnet = null;
    }
  };
  const cancelMotion = () => {
    observer?.disconnect();
    observer = null;
    listObserver?.disconnect();
    listObserver = null;
    cancelAnimationFrame(frame);
    frame = 0;
    cancelAnimationFrame(interactionFrame);
    interactionFrame = 0;
    pointerPressed = false;
    heldAnimations.clear();
    resetMagnet();
    for (const animation of animations) animation.cancel();
    animations.clear();
  };
  const sync = () => {
    document.documentElement.dataset.motion = reduced.matches ? "reduced" : paused ? "paused" : "enabled";
    if (!allowed()) cancelMotion();
  };
  const animate = (element, frames, options) => {
    if (!allowed() || !element.isConnected || !element.animate) return;
    const animation = element.animate(frames, options);
    animations.add(animation);
    const remove = () => animations.delete(animation);
    animation.addEventListener("finish", remove, { once: true });
    animation.addEventListener("cancel", remove, { once: true });
  };
  const prepareMagnet = (button) => {
    button.classList.add("magnet-target");
    button.style.setProperty("--magnet-x", "0px");
    button.style.setProperty("--magnet-y", "0px");
    if (!button.querySelector(":scope > .magnet-content")) {
      const content = document.createElement("span");
      content.className = "magnet-content";
      content.append(...button.childNodes);
      button.append(content);
    }
  };
  const prepareButtons = () => {
    magnets = [...root.querySelectorAll("button.primary, a.button.primary, .welcome-actions > button, .course-content > button, .week-actions > button, .actions > button")]
      .filter((button) => !button.closest(".sidebar, .role-switch, .tabs, #quiz-answer, .order-item, .matching-board, .password-field, .appearance-dialog, .table-wrap"));
    magnets.forEach(prepareMagnet);
  };
  const prepareSidebar = () => {
    root.querySelectorAll(".sidebar .side-nav button").forEach((button) => {
      button.classList.add("animated-list-item");
      if (button.classList.contains("active")) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
  };
  const popSidebar = () => {
    prepareSidebar();
    if (!allowed()) return;
    const sidebar = root.querySelector(".sidebar");
    if (!sidebar) return;
    listObserver?.disconnect();
    const buttons = [...sidebar.querySelectorAll(".side-nav button")];
    const pop = (button, index = 0) => animate(button, [
      { opacity: 0, transform: "translateY(12px) scale(0.8)" },
      { opacity: 1, transform: "translateY(0) scale(1)" },
    ], { duration: 520, delay: Math.min(index, 8) * 50, easing: "cubic-bezier(0.34, 1.4, 0.64, 1)", fill: "backwards" });
    if (!globalThis.IntersectionObserver) {
      buttons.filter((button) => button.getClientRects().length).forEach(pop);
      return;
    }
    // Animate the real navigation items as they enter the sidebar's own scroll
    // viewport; never replace application options with demo list contents.
    listObserver = new IntersectionObserver((entries) => {
      entries.filter((entry) => entry.isIntersecting).forEach((entry, index) => pop(entry.target, index));
    }, { root: sidebar, threshold: 0.1 });
    buttons.forEach((button) => listObserver.observe(button));
  };
  const enterContent = (kind) => {
    if (!allowed()) return;
    const elements = [...root.querySelectorAll(kind === "login" ? ".landing-copy, .landing-login" : "main > :not(.footer-note)")];
    const positions = new Map(elements.map((element, index) => [element, index]));
    const reveal = (element) => {
      element.classList.add("screen-enter");
      animate(element, [
        { opacity: 0, transform: "translateY(100px)" },
        { opacity: 1, transform: "translateY(0)" },
      ], { duration: 800, delay: Math.min(positions.get(element), 5) * 80, easing: "cubic-bezier(0.215, 0.61, 0.355, 1)", fill: "backwards" });
    };
    if (!globalThis.IntersectionObserver) {
      elements.forEach(reveal);
      return;
    }
    observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer?.unobserve(entry.target);
        reveal(entry.target);
      }
    }, { threshold: 0.1 });
    elements.forEach((element) => observer.observe(element));
  };
  const onMove = (event) => {
    if (!allowed() || !fine.matches || event.pointerType !== "mouse" || event.buttons) return resetMagnet();
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (!allowed()) return;
      let nearest = null, distance = Infinity, offset = null;
      for (const button of magnets) {
        if (!button.isConnected || button.matches(":disabled, :focus-visible") || !button.getClientRects().length) continue;
        const r = button.getBoundingClientRect();
        const dx = event.clientX - r.left - r.width / 2;
        const dy = event.clientY - r.top - r.height / 2;
        const outside = Math.hypot(Math.max(0, Math.abs(dx) - r.width / 2), Math.max(0, Math.abs(dy) - r.height / 2));
        const center = Math.hypot(dx, dy);
        // Preserve the supplied 100px field/strength 2, with at most 8px of
        // visual displacement inside an unchanged button hit target.
        if (outside > 100 || center >= distance) continue;
        nearest = button;
        distance = center;
        const pull = 1 - Math.min(1, outside / 100) ** 2;
        const x = dx / 2 * pull, y = dy / 2 * pull;
        const scale = Math.min(1, 8 / Math.max(0.01, Math.hypot(x, y)));
        offset = [x * scale, y * scale];
      }
      if (nearest !== activeMagnet) resetMagnet();
      if (!nearest) return;
      activeMagnet = nearest;
      nearest.style.setProperty("--magnet-x", `${offset[0].toFixed(2)}px`);
      nearest.style.setProperty("--magnet-y", `${offset[1].toFixed(2)}px`);
    });
  };
  const settleTarget = (event) => {
    resetMagnet();
    if (pointerPressed) return;
    for (const animation of [...animations]) {
      const target = animation.effect?.target;
      if (target?.contains(event.target)) animation.finish();
    }
  };
  const onPointerDown = (event) => {
    pointerPressed = true;
    resetMagnet();
    // Freeze the current visual position through the click. Finishing an
    // entrance here would move a label between pointerdown and pointerup.
    for (const animation of animations) {
      if (animation.effect?.target?.contains(event.target)) {
        animation.pause();
        heldAnimations.add(animation);
      }
    }
  };
  const onPointerUp = () => {
    pointerPressed = false;
    if (!heldAnimations.size) return;
    cancelAnimationFrame(interactionFrame);
    interactionFrame = requestAnimationFrame(() => {
      interactionFrame = 0;
      for (const animation of heldAnimations) {
        if (allowed() && animations.has(animation)) animation.play();
      }
      heldAnimations.clear();
    });
  };
  const onKey = (event) => {
    resetMagnet();
    const nav = event.target.closest?.(".sidebar .side-nav");
    if (!nav || !["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
    const buttons = [...nav.querySelectorAll("button:not(:disabled)")].filter((button) => button.getClientRects().length);
    if (!buttons.length) return;
    event.preventDefault();
    const index = buttons.indexOf(event.target.closest("button"));
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : Math.max(0, Math.min(buttons.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)));
    buttons[next].focus();
  };
  document.addEventListener("pointermove", onMove, { passive: true });
  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("pointerup", onPointerUp, true);
  document.addEventListener("pointercancel", onPointerUp, true);
  document.addEventListener("focusin", settleTarget);
  document.addEventListener("keydown", onKey);
  document.documentElement.addEventListener("pointerleave", resetMagnet);
  window.addEventListener("blur", resetMagnet);
  window.addEventListener("scroll", resetMagnet, { passive: true, capture: true });
  document.addEventListener("visibilitychange", sync);
  reduced.addEventListener("change", sync);
  fine.addEventListener("change", resetMagnet);
  sync();
  return {
    clearScreen() {
      cancelMotion();
      magnets = [];
    },
    screenChanged(kind, key) {
      cancelMotion();
      const main = root.querySelector("main");
      if (main) main.dataset.uiScreen = key;
      prepareButtons();
      prepareSidebar();
      if (key !== lastKey) enterContent(kind);
      if (kind === "workspace" && lastKind !== "workspace") popSidebar();
      else if (kind === "workspace" && key !== lastKey) {
        root.querySelectorAll(".sidebar .side-nav button.active").forEach((button) => animate(button,
          [{ transform: "scale(0.96)" }, { transform: "scale(1)" }], { duration: 260, easing: "ease-out" }));
      }
      lastKind = kind;
      lastKey = key;
    },
    openSidebar() { popSidebar(); },
    setPaused(value) {
      paused = Boolean(value);
      sync();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      cancelMotion();
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerdown", onPointerDown, true);
      document.removeEventListener("pointerup", onPointerUp, true);
      document.removeEventListener("pointercancel", onPointerUp, true);
      document.removeEventListener("focusin", settleTarget);
      document.removeEventListener("keydown", onKey);
      document.documentElement.removeEventListener("pointerleave", resetMagnet);
      window.removeEventListener("blur", resetMagnet);
      window.removeEventListener("scroll", resetMagnet, true);
      document.removeEventListener("visibilitychange", sync);
      reduced.removeEventListener("change", sync);
      fine.removeEventListener("change", resetMagnet);
    },
  };
}
