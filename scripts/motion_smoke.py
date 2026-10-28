"""Exercise click sparks and navigation motion using only local account fixtures.

The wave shader has its own background_smoke.py suite. Here WebGL is unavailable
on purpose, so the 2D pointer/UI checks also cover the static-background fallback.
"""
import os
import re
from pathlib import Path
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = os.environ.get("SIGIN_TEST_URL", "http://127.0.0.1:4173/")
CONFIG = (ROOT / "assets/config.js").read_text()
INIT = """(() => {
  const getContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
    if (/^(webgl2?|experimental-webgl)$/.test(kind)) return null;
    return getContext.call(this, kind, ...args);
  };
  const request = window.requestAnimationFrame.bind(window);
  const cancel = window.cancelAnimationFrame.bind(window);
  const pending = new Set();
  window.__motionAudit = {pending, frames: 0};
  window.requestAnimationFrame = callback => {
    const id = request(time => {
      pending.delete(id);
      window.__motionAudit.frames++;
      callback(time);
    });
    pending.add(id);
    return id;
  };
  window.cancelAnimationFrame = id => {pending.delete(id); cancel(id);};
})();"""
PAINTED = """() => {
  const canvas = document.querySelector('canvas.pointer-effects');
  if (!canvas || !canvas.width || !canvas.height) return false;
  const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
  for (let i = 3; i < pixels.length; i += 4) if (pixels[i] > 0) return true;
  return false;
}"""

def open_page(browser, *, reduced=False, touch=False):
    context = browser.new_context(
        viewport={"width": 390 if touch else 1440, "height": 900},
        reduced_motion="reduce" if reduced else "no-preference",
        device_scale_factor=0.5, has_touch=touch, is_mobile=touch,
    )
    context.add_init_script(INIT)
    assert "previewEnabled: false" in CONFIG
    context.route("**/assets/config.js", lambda route: route.fulfill(
        content_type="text/javascript", body=CONFIG.replace("previewEnabled: false", "previewEnabled: true")))
    requests = []
    def reject_account(route):
        requests.append(route.request.url)
        route.fulfill(status=401, content_type="application/json", body='{"message":"Test fixture"}')
    context.route("https://*.supabase.co/**", reject_account)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL)
    expect(page.locator("#login-form")).to_be_visible()
    expect(page.locator("canvas.pointer-effects")).to_have_count(1)
    return context, page, errors, requests

def finished(page):
    page.wait_for_function("""() => document.getAnimations().every(
      animation => animation.playState !== 'running' && animation.playState !== 'pending')""")

def no_pointer_pixels(page):
    # A just-scheduled burst may not have painted its first frame yet. Wait for
    # idle as well as transparency so prior clicks cannot leak into the next check.
    expect(page.locator("canvas.pointer-effects")).to_have_attribute("data-state", re.compile(r"^(idle|disabled)$"))
    page.wait_for_function("(" + PAINTED + ")() === false")

def no_pending_frames(page):
    page.wait_for_function("window.__motionAudit.pending.size === 0")
    before = page.evaluate("window.__motionAudit.frames")
    page.wait_for_timeout(150)
    assert page.evaluate("window.__motionAudit.frames") == before, "Idle effects kept requesting frames"

def choose_theme(page, theme):
    page.locator('[data-action="settings"]').first.click()
    page.locator(f'[name="theme-choice"][value="{theme}"]').locator("..").click()
    close = page.locator('[data-action="closeSettings"]')
    if close.count(): close.click()
    expect(page.locator("html")).to_have_attribute("data-theme", theme)

def magnet_offset(button):
    return button.evaluate("""element => {
      const style = getComputedStyle(element);
      return [parseFloat(style.getPropertyValue('--magnet-x')) || 0,
              parseFloat(style.getPropertyValue('--magnet-y')) || 0];
    }""")

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    context, page, errors, requests = open_page(browser)
    finished(page)
    expect(page.locator("canvas.pointer-effects")).to_have_attribute("aria-hidden", "true")
    assert page.locator("canvas.pointer-effects").evaluate("element => getComputedStyle(element).pointerEvents") == "none"

    # Moving the ordinary cursor must never paint a trail or keep an effect loop.
    page.mouse.move(680, 160)
    page.mouse.move(860, 180, steps=8)
    page.evaluate("""() => new Promise(resolve => requestAnimationFrame(
      () => requestAnimationFrame(resolve)))""")
    assert not page.evaluate(PAINTED), "Mouse movement still painted a cursor trail"
    no_pointer_pixels(page)
    no_pending_frames(page)

    # Clicks still produce the existing visible button sparks.
    role = page.locator('[data-action="loginRole"][data-role="teacher"]')
    box = role.bounding_box()
    role.dispatch_event("click", {"clientX": box["x"]+box["width"]/2, "clientY": box["y"]+box["height"]/2, "detail": 1})
    page.wait_for_function(PAINTED)
    expect(page.locator("#username")).to_have_value("DocenteULEAM")
    finished(page)
    no_pointer_pixels(page)
    no_pending_frames(page)
    page.locator('[data-action="loginRole"][data-role="student"]').click()
    finished(page)
    no_pointer_pixels(page)

    # Text fields do not emit click sparks; passwords remain ordinary inputs.
    field = page.locator("#username")
    field.dispatch_event("click", {"clientX": 100, "clientY": 100, "detail": 1})
    assert not page.evaluate(PAINTED), "A text input emitted decorative click sparks"
    page.locator("#password").fill("fixture-not-submitted")
    expect(page.locator("#password")).to_have_attribute("type", "password")
    page.locator("#password").clear()

    primary = page.locator('#login-form button.primary')
    expect(primary).to_have_class(re.compile(r"\bmagnet-target\b"))
    box = primary.bounding_box()
    page.mouse.move(box["x"]-28, box["y"]+box["height"]/2)
    page.wait_for_function("""() => {
      const element=document.querySelector('#login-form button.primary');
      const style=getComputedStyle(element);
      return Math.abs(parseFloat(style.getPropertyValue('--magnet-x')) || 0)>0;
    }""")
    offset = magnet_offset(primary)
    assert 0 < max(map(abs, offset)) <= 8.1, offset
    page.mouse.move(5, 5)
    page.keyboard.press("Tab")
    primary.focus()
    page.mouse.move(box["x"]-28, box["y"]+box["height"]/2)
    assert all(abs(value)<0.1 for value in magnet_offset(primary)), "Keyboard focus moved magnetically"
    page.mouse.move(5, 5)
    no_pointer_pixels(page)

    # The same global toggle stops pointer effects and screen/list transitions.
    page.locator('[data-action="toggleMotion"]').first.click()
    expect(page.locator('[data-action="toggleMotion"]').first).to_have_attribute("aria-pressed", "true")
    no_pointer_pixels(page)
    page.mouse.move(700, 150)
    page.mouse.move(900, 160, steps=6)
    assert not page.evaluate(PAINTED), "Paused pointer effects still painted"
    page.locator('[data-action="loginRole"][data-role="teacher"]').click()
    finished(page)
    assert not page.evaluate("document.getAnimations().some(animation=>animation.playState==='running')")
    no_pending_frames(page)
    page.locator('[data-action="toggleMotion"]').first.click()
    page.get_by_role("button", name="Explorar las tres materias").click()
    expect(page.locator(".course-card")).to_have_count(3)
    page.wait_for_function("""() => document.getAnimations().some(animation =>
      animation.playState==='running' && animation.effect?.target?.closest('.sidebar .side-nav'))""")
    finished(page)
    expect(page.locator("main[data-ui-screen]")).to_be_visible()
    assert page.locator(".sidebar .side-nav button").count() >= 7
    assert page.locator(".sidebar .side-nav .magnet-target").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    # A real keyboard activation navigates to grades while retaining visible
    # active navigation and readable content after the entrance settles.
    grades = page.locator('.sidebar [data-action="grades"]')
    grades.focus()
    page.keyboard.press("Enter")
    expect(page.locator('.sidebar [data-action="grades"]')).to_have_class(re.compile(r"\bactive\b"))
    page.wait_for_function("""() => document.getAnimations().some(animation =>
      animation.playState==='running' && animation.effect?.target?.closest('main'))""")
    finished(page)
    expect(page.get_by_role("heading", name="Resultados con contexto.")).to_be_visible()
    assert page.locator("main").evaluate("element=>Number(getComputedStyle(element).opacity)") == 1
    # Regression: a label clicked while its card is partway through an entrance
    # must not jump out from under pointerdown/up and lose the radio selection.
    page.locator('.sidebar [data-action="settings"]').click()
    page.wait_for_function("""() => document.getAnimations().some(animation =>
      animation.playState==='running' && animation.effect?.target===document.querySelector('.settings-card'))""")
    page.evaluate("""() => {
      for (const animation of document.getAnimations()) {
        if (animation.effect?.target===document.querySelector('.settings-card')) {
          animation.pause();
          animation.currentTime=180;
        }
      }
    }""")
    page.locator('[name="theme-choice"][value="dark"]').locator("..").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    finished(page)
    page.locator('.sidebar [data-action="home"]').click()
    finished(page)
    for theme in ["dark", "light"]:
        choose_theme(page, theme)
        finished(page)
        page.locator('.sidebar [data-action="home"]').click()
        finished(page)
        expect(page.locator(".course-card")).to_have_count(3)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.emulate_media(reduced_motion="reduce")
    no_pointer_pixels(page)
    page.locator('.sidebar [data-action="grades"]').click()
    expect(page.get_by_role("heading", name="Resultados con contexto.")).to_be_visible()
    assert not page.evaluate("document.getAnimations().some(animation=>animation.playState==='running')")
    no_pending_frames(page)
    assert not errors, errors
    assert not requests, "The visual test attempted a live account request"
    context.close()

    context, page, errors, requests = open_page(browser, reduced=True)
    page.mouse.move(700,150)
    page.mouse.move(850,170,steps=6)
    page.locator('[data-action="loginRole"][data-role="teacher"]').click()
    assert not page.evaluate(PAINTED), "Reduced motion still showed pointer effects"
    assert not page.evaluate("document.getAnimations().some(animation=>animation.playState==='running')")
    no_pending_frames(page)
    assert not errors, errors
    assert not requests, requests
    context.close()
    context, page, errors, requests = open_page(browser, touch=True)
    finished(page)
    page.mouse.move(150,150)
    page.mouse.move(280,170,steps=6)
    assert not page.evaluate(PAINTED), "Pointer movement painted an unwanted trail on touch"
    role=page.locator('[data-action="loginRole"][data-role="teacher"]')
    box=role.bounding_box()
    page.touchscreen.tap(box["x"]+box["width"]/2,box["y"]+box["height"]/2)
    page.wait_for_function(PAINTED)
    expect(page.locator("#username")).to_have_value("DocenteULEAM")
    finished(page)
    no_pointer_pixels(page)
    assert all(abs(value)<0.1 for value in magnet_offset(page.locator('#login-form button.primary'))), "A touch device moved a magnetic target"
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert not errors, errors
    assert not requests, requests
    context.close()
    browser.close()
    print("PASS: standard cursor without a trail; click sparks and idle cleanup; bounded mouse-only magnets; keyboard navigation; page/list entrances; pause and reduced motion; both themes; no real account requests")
