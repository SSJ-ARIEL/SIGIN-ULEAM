"""Exercise the real SwarmCursor shader with local account fixtures only.

The wave shader is disabled here so SwiftShader can isolate the cursor. Instrument
WebGL uploads/draws without replacing physics, shaders, or the rendering context.
"""
import os
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = os.environ.get("SIGIN_TEST_URL", "http://127.0.0.1:4173/")
CONFIG = (ROOT / "assets/config.js").read_text()
AUDIT = """(() => {
  const audit = window.__swarmAudit = {
    draws: 0, instances: 0, capturePixels: false, painted: 0,
    color: [], center: [0, 0], radius: 0, length: 0, history: [],
    captureContent: false, contentRects: [], beforeContent: 0,
    afterContent: 0, outsideContent: 0
  };
  const original = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
    const webgl = /^(webgl2?|experimental-webgl)$/.test(kind);
    if (webgl && !this.classList.contains('swarm-cursor-canvas')) return null;
    const gl = original.call(this, kind, ...args);
    if (!gl || !webgl || gl.__swarmInstrumented) return gl;
    gl.__swarmInstrumented = true;
    const attributes = new Map(), buffers = new Map(), uniforms = new Map();
    let bound = null;
    const bind = gl.bindBuffer.bind(gl);
    gl.bindBuffer = (target, buffer) => {
      if (target === gl.ARRAY_BUFFER) bound = buffer;
      return bind(target, buffer);
    };
    const attribute = gl.vertexAttribPointer.bind(gl);
    gl.vertexAttribPointer = (slot, ...values) => {
      attributes.set(slot, bound);
      return attribute(slot, ...values);
    };
    const upload = gl.bufferSubData.bind(gl);
    gl.bufferSubData = (target, offset, data, start = 0, length) => {
      if (target === gl.ARRAY_BUFFER) {
        buffers.set(bound, data.slice(start, length === undefined ? undefined : start + length));
      }
      return upload(target, offset, data, start, length);
    };
    const location = gl.getUniformLocation.bind(gl);
    gl.getUniformLocation = (program, name) => {
      const result = location(program, name);
      uniforms.set(result, name);
      return result;
    };
    const uniform = gl.uniform3fv.bind(gl);
    gl.uniform3fv = (handle, value, ...rest) => {
      if (uniforms.get(handle) === 'uColor') audit.color = Array.from(value);
      return uniform(handle, value, ...rest);
    };
    const contentPixels = () => {
      const width = gl.drawingBufferWidth, height = gl.drawingBufferHeight;
      const pixels = new Uint8Array(width * height * 4);
      gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      const ratioX = width / innerWidth, ratioY = height / innerHeight;
      const protectedPixels = new Uint8Array(width * height);
      for (const rect of audit.contentRects) {
        const left = Math.max(0, Math.ceil(rect.left * ratioX));
        const right = Math.min(width, Math.floor(rect.right * ratioX));
        const top = Math.max(0, Math.ceil(rect.top * ratioY));
        const bottom = Math.min(height, Math.floor(rect.bottom * ratioY));
        for (let y = top; y < bottom; y++) {
          for (let x = left; x < right; x++) protectedPixels[(height - 1 - y) * width + x] = 1;
        }
      }
      let inside = 0, outside = 0;
      for (let i = 0; i < protectedPixels.length; i++) {
        if (pixels[i * 4 + 3] > 0) protectedPixels[i] ? inside++ : outside++;
      }
      return {inside, outside};
    };
    const disable = gl.disable.bind(gl);
    gl.disable = capability => {
      const result = disable(capability);
      if (capability === gl.SCISSOR_TEST && audit.captureContent) {
        const pixels = contentPixels();
        audit.afterContent = pixels.inside;
        audit.outsideContent = pixels.outside;
        audit.captureContent = false;
      }
      return result;
    };
    const draw = gl.drawArraysInstanced.bind(gl);
    gl.drawArraysInstanced = (mode, first, count, instances) => {
      const result = draw(mode, first, count, instances);
      audit.draws++;
      audit.instances = instances;
      const agents = buffers.get(attributes.get(1));
      const looks = buffers.get(attributes.get(2));
      if (agents && looks && instances) {
        let x = 0, y = 0, length = 0;
        for (let i = 0; i < instances; i++) {
          x += agents[i * 4]; y += agents[i * 4 + 1];
          length += looks[i * 4];
        }
        audit.center = [x / instances, y / instances];
        let radius = 0;
        for (let i = 0; i < instances; i++) {
          radius += Math.hypot(agents[i * 4] - audit.center[0], agents[i * 4 + 1] - audit.center[1]);
        }
        audit.radius = radius / instances;
        audit.length = length / instances;
        audit.history.push({draw: audit.draws, radius: audit.radius, length: audit.length});
        if (audit.history.length > 180) audit.history.shift();
      }
      if (audit.capturePixels) {
        const pixels = new Uint8Array(gl.drawingBufferWidth * gl.drawingBufferHeight * 4);
        gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
        audit.painted = 0;
        for (let i = 3; i < pixels.length; i += 4) if (pixels[i] > 0) audit.painted++;
        audit.capturePixels = false;
      }
      if (audit.captureContent) audit.beforeContent = contentPixels().inside;
      return result;
    };
    return gl;
  };
})();"""
SPARKS = """() => {
  const canvas = document.querySelector('canvas.pointer-effects');
  const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
  for (let i = 3; i < pixels.length; i += 4) if (pixels[i] > 0) return true;
  return false;
}"""


def open_page(browser, *, reduced=False, touch=False):
    context = browser.new_context(
        viewport={"width": 390 if touch else 800, "height": 650},
        device_scale_factor=0.5, has_touch=touch, is_mobile=touch,
        reduced_motion="reduce" if reduced else "no-preference",
    )
    context.add_init_script(AUDIT)
    assert "previewEnabled: false" in CONFIG
    context.route("**/assets/config.js", lambda route: route.fulfill(
        content_type="text/javascript", body=CONFIG.replace("previewEnabled: false", "previewEnabled: true")))
    requests = []
    def reject_account(route):
        requests.append(route.request.url)
        route.fulfill(status=401, content_type="application/json", body='{"message":"Local fixture"}')
    context.route("https://*.supabase.co/**", reject_account)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL)
    expect(page.locator("#login-form")).to_be_visible()
    expect(page.locator("canvas.swarm-cursor-canvas")).to_have_count(1)
    return context, page, errors, requests


def frames(page, count=6):
    target = page.evaluate("window.__swarmAudit.draws") + count
    page.wait_for_function("target => window.__swarmAudit.draws >= target", arg=target)


def painted(page):
    page.evaluate("window.__swarmAudit.capturePixels = true")
    page.wait_for_function("!window.__swarmAudit.capturePixels")
    assert page.evaluate("window.__swarmAudit.painted") > 80, "Swarm shader did not paint visible particles"


def readable_content(page):
    # Sample the actual framebuffer before and after composition, while the
    # original simulation deliberately crosses the headline. This proves the
    # protection removes real overlapping particles and preserves those nearby.
    page.evaluate("""() => {
      const rects = [];
      const title = document.querySelector('#landing-title');
      const range = document.createRange();
      range.selectNodeContents(title);
      for (const rect of range.getClientRects()) rects.push(rect.toJSON());
      for (const field of document.querySelectorAll('#login-form input')) {
        rects.push(field.getBoundingClientRect().toJSON());
      }
      __swarmAudit.contentRects = rects;
      __swarmAudit.captureContent = true;
    }""")
    page.wait_for_function("!window.__swarmAudit.captureContent")
    sample = page.evaluate("({before: __swarmAudit.beforeContent, after: __swarmAudit.afterContent, outside: __swarmAudit.outsideContent})")
    assert sample["before"] > 20, ("No particles crossed the headline during the readability check", sample)
    assert sample["after"] == 0, ("Particles obscured headings or login fields", sample)
    assert sample["outside"] > 80, ("Content protection hid the surrounding swarm", sample)


def stopped(page):
    expect(page.locator("canvas.swarm-cursor-canvas")).to_have_attribute(
        "data-state", re.compile(r"^(idle|disabled|fallback)$"))
    before = page.evaluate("window.__swarmAudit.draws")
    page.wait_for_timeout(180)
    assert page.evaluate("window.__swarmAudit.draws") == before, "Inactive swarm kept drawing"


def leave(page):
    page.locator("html").dispatch_event("pointerleave", {"pointerType": "mouse"})
    stopped(page)


def choose_theme(page, theme):
    page.locator('[data-action="settings"]').first.click()
    page.locator(f'[name="theme-choice"][value="{theme}"]').locator("..").click()
    close = page.locator('[data-action="closeSettings"]')
    if close.count(): close.click()
    expect(page.locator("html")).to_have_attribute("data-theme", theme)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True, executable_path="/usr/bin/chromium",
        args=["--no-sandbox", "--enable-unsafe-swiftshader"],
    )
    context, page, errors, requests = open_page(browser)
    canvas = page.locator("canvas.swarm-cursor-canvas")
    expect(canvas).to_have_attribute("aria-hidden", "true")
    assert canvas.evaluate("element => getComputedStyle(element).pointerEvents") == "none"
    assert page.locator(".swarm-cursor-hidden").count() == 0, "Swarm replaced the normal cursor"
    stopped(page)

    # A real mouse wakes the supplied 800-particle shader and moves its center.
    page.mouse.move(160, 250)
    expect(canvas).to_have_attribute("data-state", "running")
    frames(page, 65)  # Allow the original 1.4-second introduction to settle.
    painted(page)
    assert page.evaluate("window.__swarmAudit.instances") == 800
    first = page.evaluate("window.__swarmAudit.center")
    page.mouse.move(620, 250, steps=10)
    frames(page, 65)
    second = page.evaluate("window.__swarmAudit.center")
    assert second[0] > first[0] + 160, (first, second)
    painted(page)

    # Click on text/background, away from hover targets. The real burst increases
    # particle speed/dispersion; this is independent of button ClickSpark.
    page.mouse.move(300, 250, steps=8)
    frames(page, 65)
    baseline = page.evaluate("({draw: __swarmAudit.draws, radius: __swarmAudit.radius, length: __swarmAudit.length})")
    page.mouse.click(300, 250)
    frames(page, 12)
    burst = page.evaluate("draw => __swarmAudit.history.filter(frame => frame.draw > draw)", baseline["draw"])
    assert max(frame["length"] for frame in burst) > baseline["length"] + 1, (baseline, burst)
    assert max(frame["radius"] for frame in burst) > baseline["radius"] + 1, (baseline, burst)

    # Themes update the same rendering context, retaining original white/dark ink.
    page.evaluate("window.__originalSwarmCanvas = document.querySelector('.swarm-cursor-canvas')")
    for theme, ink in [("dark", [1, 1, 1]), ("light", [24 / 255, 24 / 255, 27 / 255])]:
        choose_theme(page, theme)
        page.mouse.move(300, 250)
        frames(page)
        painted(page)
        actual = page.evaluate("window.__swarmAudit.color")
        assert all(abs(a - b) < 0.001 for a, b in zip(actual, ink)), (theme, actual)
        assert page.evaluate("document.querySelector('.swarm-cursor-canvas') === window.__originalSwarmCanvas")
        readable_content(page)
        page.screenshot(path=f"/tmp/sigin-swarm-{theme}.png")

    # Native input, button click sparks, and route changes remain usable.
    page.locator("#username").fill("0000000002")
    page.locator("#password").fill("fixture-not-submitted")
    expect(page.locator("#password")).to_have_attribute("type", "password")
    role = page.locator('[data-action="loginRole"][data-role="teacher"]')
    role.click()
    page.wait_for_function(SPARKS)
    expect(page.locator("#username")).to_have_value("DocenteULEAM")
    leave(page)
    page.mouse.move(300, 250)
    frames(page)
    page.evaluate("window.dispatchEvent(new Event('blur'))")
    stopped(page)
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    page.mouse.move(310, 250)
    frames(page)
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, value: true}); document.dispatchEvent(new Event('visibilitychange'))")
    stopped(page)
    page.evaluate("delete document.hidden; document.dispatchEvent(new Event('visibilitychange'))")
    page.mouse.move(320, 250)
    frames(page)

    toggle = page.locator('[data-action="toggleMotion"]').first
    toggle.click()
    expect(toggle).to_have_attribute("aria-pressed", "true")
    stopped(page)
    page.mouse.move(600, 250)
    stopped(page)
    toggle.click()
    page.mouse.move(310, 250)
    frames(page)
    page.emulate_media(reduced_motion="reduce")
    stopped(page)
    page.mouse.move(600, 250)
    stopped(page)
    page.emulate_media(reduced_motion="no-preference")
    page.mouse.move(320, 250)
    frames(page)
    page.get_by_role("button", name="Explorar las tres materias").click()
    expect(page.locator(".course-card")).to_have_count(3)
    expect(page.locator("canvas.swarm-cursor-canvas")).to_have_count(1)
    assert page.evaluate("document.querySelector('.swarm-cursor-canvas') === window.__originalSwarmCanvas")
    leave(page)
    assert not errors, errors
    assert not requests, "The cursor test attempted a real account request"
    context.close()

    for reduced, touch in [(True, False), (False, True)]:
        context, page, errors, requests = open_page(browser, reduced=reduced, touch=touch)
        page.mouse.move(120, 160)
        page.mouse.move(280, 160, steps=6)
        stopped(page)
        assert page.evaluate("window.__swarmAudit.draws") == 0, "Reduced/coarse pointer drew a swarm"
        if touch:
            role = page.locator('[data-action="loginRole"][data-role="teacher"]')
            role.scroll_into_view_if_needed()
            box = role.bounding_box()
            page.touchscreen.tap(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_function(SPARKS)
            expect(page.locator("#username")).to_have_value("DocenteULEAM")
            stopped(page)
        assert not errors, errors
        assert not requests, requests
        context.close()
    browser.close()
    print("PASS: real SwarmCursor shader with 800 particles, mouse following and burst; both themes; protected headings/fields with visible surrounding swarm; click sparks and native inputs; single canvas across routes; leave/blur/hidden/pause/reduced/touch cleanup; no real account requests")
