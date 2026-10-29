"""Validate the landing animation without authenticating or touching live data."""
import os
from pathlib import Path
from playwright.sync_api import expect, sync_playwright
ROOT = Path(__file__).resolve().parents[1]
URL = os.environ.get("SIGIN_TEST_URL", "http://127.0.0.1:4173/")
CONFIG = (ROOT / "assets/config.js").read_text()
RAF_TRACKER = """(() => {
  const request = window.requestAnimationFrame.bind(window);
  const cancel = window.cancelAnimationFrame.bind(window);
  const pending = new Set();
  window.__animationAudit = {pending, frames: 0};
  window.requestAnimationFrame = callback => {
    const id = request(time => {
      pending.delete(id);
      window.__animationAudit.frames++;
      callback(time);
    });
    pending.add(id);
    return id;
  };
  window.cancelAnimationFrame = id => {pending.delete(id); cancel(id);};
})();"""

def create_page(browser, *, reduced=False, no_webgl=False, preview=False):
    # Keep the real shader at a low test DPR for CPU-only cloud Chromium.
    context = browser.new_context(viewport={"width":640,"height":680}, reduced_motion="reduce" if reduced else "no-preference", device_scale_factor=0.25)
    context.add_init_script(RAF_TRACKER)
    if no_webgl:
        context.add_init_script("""(() => {
          const original = HTMLCanvasElement.prototype.getContext;
          HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
            if (/^(webgl2?|experimental-webgl)$/.test(kind)) return null;
            return original.call(this, kind, ...args);
          };
        })();""")
    context.route("https://*.supabase.co/**",lambda route:route.fulfill(status=401,content_type="application/json",body='{"message":"Test fixture"}'))
    if preview:
        assert "previewEnabled: false" in CONFIG
        context.route("**/assets/config.js",lambda route:route.fulfill(content_type="text/javascript",body=CONFIG.replace("previewEnabled: false","previewEnabled: true")))
    page=context.new_page()
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)))
    page.goto(URL)
    expect(page.locator("#login-form")).to_be_visible()
    expect(page.locator(".landing-waves")).to_have_attribute("aria-hidden","true")
    return context,page,errors

def assert_stopped(page):
    # The independent cursor swarm stays animated while the mouse is over the
    # page. Leave the viewport before checking background/UI cleanup.
    page.locator("html").dispatch_event("pointerleave")
    page.wait_for_function("window.__animationAudit.pending.size === 0")
    before=page.evaluate("window.__animationAudit.frames")
    page.wait_for_timeout(180)
    assert page.evaluate("window.__animationAudit.frames")==before,"Animation kept scheduling frames"

def choose_theme(page,theme):
    page.locator('[data-action="settings"]').click()
    page.locator(f'[name="theme-choice"][value="{theme}"]').locator("..").click()
    page.locator('[data-action="closeSettings"]').click()
    expect(page.locator("html")).to_have_attribute("data-theme",theme)

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path="/usr/bin/chromium",args=["--no-sandbox","--enable-unsafe-swiftshader"])
    context,page,errors=create_page(browser,preview=True)
    waves=page.locator(".landing-waves")
    expect(waves).to_have_attribute("data-state","running")
    expect(waves.locator("canvas")).to_have_count(1)
    page.wait_for_function("window.__animationAudit.frames >= 3")
    canvas=waves.locator("canvas")
    first=canvas.screenshot()
    page.wait_for_timeout(250)
    assert canvas.screenshot()!=first,"Wave pixels did not move"
    toggle=page.locator('[data-action="toggleMotion"]')
    toggle.click()
    expect(waves).to_have_attribute("data-state","paused")
    expect(toggle).to_have_attribute("aria-pressed","true")
    assert_stopped(page)
    first=canvas.screenshot()
    page.wait_for_timeout(200)
    assert canvas.screenshot()==first,"Paused waves changed pixels"
    assert page.evaluate("localStorage.getItem('sigin-motion-paused-v1')")=="true"
    page.reload()
    expect(page.locator(".landing-waves")).to_have_attribute("data-state","paused")
    expect(page.locator('[data-action="toggleMotion"]')).to_have_attribute("aria-pressed","true")
    assert_stopped(page)
    page.locator('[data-action="toggleMotion"]').click()
    expect(page.locator(".landing-waves")).to_have_attribute("data-state","running")
    for role in ["teacher","student","teacher","student"]:
        page.locator(f'[data-action="loginRole"][data-role="{role}"]').click()
        expect(page.locator(".landing-waves canvas")).to_have_count(1)
        expect(page.locator(".landing-waves")).to_have_attribute("data-state","running")
    page.evaluate("window.__originalWaveCanvas=document.querySelector('.landing-waves canvas')")
    for theme in ["dark","light"]:
        choose_theme(page,theme)
        assert page.evaluate("document.querySelector('.landing-waves canvas') === window.__originalWaveCanvas"),"Changing appearance remounted the animation"
        expect(page.locator(".landing-waves canvas")).to_have_count(1)
    page.emulate_media(reduced_motion="reduce")
    expect(page.locator(".landing-waves")).to_have_attribute("data-state","reduced")
    expect(page.locator('[data-action="toggleMotion"]')).to_be_hidden()
    assert_stopped(page)
    page.emulate_media(reduced_motion="no-preference")
    expect(page.locator(".landing-waves")).to_have_attribute("data-state","running")
    page.get_by_role("button",name="Explorar las tres materias").click()
    expect(page.locator(".course-card")).to_have_count(3)
    expect(page.locator(".landing-waves")).to_have_count(0)
    assert_stopped(page)
    assert not errors,errors
    context.close()
    context,page,errors=create_page(browser,reduced=True)
    expect(page.locator(".landing-waves")).to_have_attribute("data-state","reduced")
    expect(page.locator('[data-action="toggleMotion"]')).to_be_hidden()
    assert_stopped(page)
    page.locator("#username").fill("0000000002")
    page.locator("#password").fill("fixture-not-submitted")
    expect(page.locator('#login-form [type="submit"]')).to_be_enabled()
    assert not errors,errors
    context.close()
    context,page,errors=create_page(browser,no_webgl=True)
    expect(page.locator(".landing-waves")).to_have_attribute("data-state","fallback")
    assert_stopped(page)
    page.locator("#username").fill("0000000002")
    page.locator("#password").fill("fixture-not-submitted")
    page.locator('[data-action="showPassword"]').click()
    expect(page.locator("#password")).to_have_attribute("type","text")
    expect(page.locator('#login-form [type="submit"]')).to_be_enabled()
    assert not errors,errors
    context.close()
    context,page,errors=create_page(browser)
    expect(page.locator(".landing-waves")).to_have_attribute("data-state","running")
    page.locator(".landing-waves canvas").dispatch_event("webglcontextlost")
    expect(page.locator(".landing-waves")).to_have_attribute("data-state","fallback")
    assert_stopped(page)
    expect(page.locator("#login-form")).to_be_visible()
    assert not errors,errors
    context.close()
    browser.close()
    print("PASS: moving gradient pixels, pause/resume persistence, single canvas, theme updates without remount, navigation cleanup, reduced motion, WebGL failure/context-loss fallback; no real account requests")
