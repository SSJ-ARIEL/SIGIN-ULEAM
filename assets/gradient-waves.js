/**
 * Gradient Waves shaders adapted from React Bits by David Haz (2026).
 * https://github.com/DavidHDev/react-bits/tree/main/src/content/Backgrounds/GradientWaves
 * License: assets/vendor/licenses/react-bits.md (MIT + Commons Clause).
 * Local vanilla-JS lifecycle: no React, CDN requests, mouse steering or click waves.
 */
const MAX_SWELLS = 4;
const CAMERA_HEIGHT = 30;

const VERTEX = `#version 300 es
in vec2 aPosition;
void main() {
  gl_Position = vec4(aPosition, 0.0, 1.0);
}`;

const FRAGMENT = `#version 300 es
precision highp float;
uniform vec2 uResolution;
uniform float uTime;
uniform float uClock;
uniform float uAmplitude;
uniform float uWaveScale;
uniform float uWaveRatio;
uniform float uSwell;
uniform float uTurbulence;
uniform float uHeight;
uniform float uTilt;
uniform float uZoom;
uniform vec2 uLook;
uniform float uFogDepth;
uniform float uBrightness;
uniform float uOpacity;
uniform float uGrain;
uniform vec3 uHorizon;
uniform vec3 uWave;
uniform vec3 uCrest;
uniform vec3 uBackground;
uniform float uOpaque;
uniform float uLight;
uniform vec3 uSun;
uniform float uRelief;
uniform float uSheen;
uniform float uSteps;
uniform float uStride;
uniform vec3 uIntro;
uniform vec3 uSwells[${MAX_SWELLS}];
uniform float uSwellWidth;
out vec4 outColor;

const float FAR = 4000.0;

float hash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

vec3 surface(vec2 xy) {
  vec2 freq = vec2(uWaveScale / 7.0, (uWaveScale * uWaveRatio) / 3.0);
  vec4 tc = vec4(uTime / 0.130, uTime / 0.810, uTime / 0.200, uTime / 0.710);
  float a = xy.x + tc.x;
  float swellPhase = (xy.y + a) / 20.0 + tc.y;
  float bend = uSwell * cos(swellPhase) / 20.0;
  float mx = a + uSwell * sin(swellPhase);
  float crossPhase = xy.x / 23.0 + tc.w;
  float my = xy.y - tc.z + uTurbulence * cos(crossPhase);
  float twist = -uTurbulence * sin(crossPhase) / 23.0;
  float cx = cos(mx * freq.x);
  float cy = cos(my * freq.y);
  float rise = 1.0;
  if (uIntro.z > 0.0) rise = mix(1.0, smoothstep(uIntro.y * 0.45, uIntro.y * 1.6, xy.x), uIntro.z);
  float amp = uAmplitude * rise;
  float h = (sin(mx * freq.x) + sin(my * freq.y)) * amp + uHeight;
  float dx = amp * (freq.x * cx * (1.0 + bend) + freq.y * cy * twist);
  float dy = amp * (freq.x * cx * bend + freq.y * cy);
  for (int k = 0; k < ${MAX_SWELLS}; k++) {
    vec3 sw = uSwells[k];
    if (sw.z <= 0.0) continue;
    float u = (xy.x - sw.x) / uSwellWidth;
    float v = (xy.y - sw.y) / (uSwellWidth * 3.5);
    float bump = sw.z * exp(-u * u - v * v);
    h += bump;
    dx += bump * (-2.0 * u / uSwellWidth);
    dy += bump * (-2.0 * v / (uSwellWidth * 3.5));
  }
  return vec3(h, dx, dy);
}

float march(vec3 origin, vec3 dir) {
  float dist = 0.0;
  for (int i = 0; i < 128; i++) {
    if (float(i) >= uSteps) break;
    float gap = origin.z + dist * dir.z - surface(origin.xy + dist * dir.xy).x;
    if (abs(gap) < 0.002 * dist + 0.01) break;
    dist += uStride * gap;
    if (!(abs(dist) < FAR)) return FAR;
  }
  return dist;
}

void main() {
  float c;
  float s;
  float vfov = (3.14159 / 2.3) / max(uZoom, 0.05);
  vec3 cam = vec3(0.0, 0.0, ${CAMERA_HEIGHT.toFixed(1)});
  vec2 uv = gl_FragCoord.xy / uResolution - 0.5;
  uv.x *= uResolution.x / uResolution.y;
  uv.y *= -1.0;

  vec3 dir = vec3(0.0, 0.0, -1.0);
  float ulen = length(uv);
  float xrot = vfov * ulen;
  c = cos(xrot);
  s = sin(xrot);
  dir = mat3(1.0, 0.0, 0.0, 0.0, c, -s, 0.0, s, c) * dir;
  vec2 nuv = ulen > 1e-5 ? uv / ulen : vec2(1.0, 0.0);
  dir = mat3(nuv.x, -nuv.y, 0.0, nuv.y, nuv.x, 0.0, 0.0, 0.0, 1.0) * dir;
  c = cos(uTilt + uLook.y);
  s = sin(uTilt + uLook.y);
  dir = mat3(c, 0.0, s, 0.0, 1.0, 0.0, -s, 0.0, c) * dir;
  c = cos(uLook.x);
  s = sin(uLook.x);
  dir = mat3(c, s, 0.0, -s, c, 0.0, 0.0, 0.0, 1.0) * dir;

  float dist = march(cam, dir);
  vec3 pos = cam + dist * dir;
  vec3 field = surface(pos.xy);
  vec3 view = -dir;

  float crest = clamp((field.x - uHeight) / max(2.0 * uAmplitude, 0.001) * 0.5 + 0.5, 0.0, 1.0);
  vec3 body = mix(uWave, uCrest, smoothstep(0.45, 1.0, crest) * 0.5);
  vec3 normal = normalize(vec3(-field.yz * (1.0 + 1.5 * uRelief), 1.0));
  float diffuse = clamp(dot(normal, uSun) * 0.5 + 0.5, 0.0, 1.0);
  float lightness = mix(1.0, diffuse * diffuse * (3.0 - 2.0 * diffuse), uRelief);
  float sheen = pow(clamp(dot(normal, normalize(uSun + view)), 0.0, 1.0), 14.0) * uSheen * (0.4 + 0.6 * uRelief);
  float rim = pow(1.0 - clamp(dot(normal, view), 0.0, 1.0), 3.0);

  vec3 col;
  float alpha;
  float haze = 1.0 - exp(-dist / (uFogDepth * 5.0));
  float fade = 1.0 - smoothstep(0.35, 1.0, haze);
  if (uLight < 0.5) {
    vec3 lit = mix(uHorizon * 0.18, body, lightness) + uCrest * sheen;
    lit = mix(lit, uHorizon, rim * 0.15 * uRelief);
    col = mix(lit, uHorizon, smoothstep(0.0, 1.0, haze)) * 0.85 * uBrightness;
    alpha = fade;
  } else {
    vec3 hue = mix(uHorizon, body, 0.35 + 0.65 * lightness);
    float density = mix(0.16, 0.9, 1.0 - lightness);
    density *= 1.0 - clamp(sheen, 0.0, 1.0) * 0.85;
    density *= 1.0 - 0.5 * smoothstep(0.0, 1.0, haze);
    col = hue;
    alpha = fade * clamp(density * uBrightness, 0.0, 1.0);
  }

  float reveal = uIntro.x;
  col = clamp(col, 0.0, 1.0);
  float grain = (hash(gl_FragCoord.xy + fract(uClock) * 64.0) - 0.5) * uGrain;
  alpha = clamp(alpha * (1.0 + grain), 0.0, 1.0) * reveal * uOpacity;
  if (uOpaque > 0.5) {
    outColor = vec4(mix(uBackground, col, alpha), 1.0);
  } else {
    outColor = vec4(col * alpha, alpha);
  }
}`;

const color = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);

export function createGradientWaves(container, { paused = false, onStateChange = () => {} } = {}) {
  const canvas = document.createElement("canvas");
  canvas.className = "gradient-waves-canvas";
  canvas.setAttribute("aria-hidden", "true");
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  let gl, program, buffer, vao, resizeObserver;
  let frame = 0, lastFrame = 0, time = 0, clock = 0;
  let destroyed = false, failed = false;
  let theme = document.documentElement.dataset.theme || "light";

  const notify = () => {
    const state = failed ? "fallback" : reducedMotion.matches ? "reduced" : paused ? "paused" : document.hidden ? "hidden" : "running";
    container.dataset.state = state;
    onStateChange(state);
  };
  const cancel = () => {
    cancelAnimationFrame(frame);
    frame = 0;
    lastFrame = 0;
  };
  const release = () => {
    if (!gl) return;
    if (buffer) gl.deleteBuffer(buffer);
    if (vao) gl.deleteVertexArray(vao);
    if (program) gl.deleteProgram(program);
    buffer = vao = program = null;
  };
  const fallback = () => {
    failed = true;
    cancel();
    release();
    canvas.remove();
    notify();
  };
  const compile = (type, source) => {
    const shader = gl.createShader(type);
    if (!shader) return null;
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      gl.deleteShader(shader);
      return null;
    }
    return shader;
  };
  const u = {};
  const fit = () => {
    // A smooth background needs fewer pixels than UI. Bound GPU cost on phones
    // and large displays rather than blindly multiplying by devicePixelRatio.
    const { width, height } = container.getBoundingClientRect();
    const ratio = Math.min(devicePixelRatio || 1, 1.25, Math.sqrt(300000 / Math.max(1, width * height)));
    const w = Math.max(1, Math.round(width * ratio));
    const h = Math.max(1, Math.round(height * ratio));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
  };
  const draw = () => {
    if (destroyed || failed || !program || gl.isContextLost()) return;
    fit();
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.useProgram(program);
    gl.bindVertexArray(vao);
    gl.uniform2f(u.uResolution, canvas.width, canvas.height);
    gl.uniform1f(u.uTime, time);
    // Freeze grain too when motion is paused or reduced.
    gl.uniform1f(u.uClock, clock);
    gl.uniform1f(u.uLight, theme === "light" ? 1 : 0);
    gl.uniform1f(u.uBrightness, theme === "light" ? 1.8 : 1.35);
    gl.uniform3fv(u.uBackground, color(theme === "dark" ? "#1c1817" : "#f8f4ed"));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  const tick = (now) => {
    frame = 0;
    if (destroyed || failed || paused || reducedMotion.matches || document.hidden) return;
    // Cap rendering at 24 fps. Clamp elapsed time to avoid jumps after a tab resumes.
    if (!lastFrame || now - lastFrame >= 1000 / 24) {
      const dt = lastFrame ? Math.min((now - lastFrame) / 1000, 0.1) : 0;
      lastFrame = now;
      time += dt * 0.4;
      clock += dt;
      draw();
    }
    frame = requestAnimationFrame(tick);
  };
  const sync = () => {
    if (destroyed || failed) return;
    cancel();
    notify();
    if (!document.hidden) {
      draw();
      if (!paused && !reducedMotion.matches) frame = requestAnimationFrame(tick);
    }
  };
  const onContextLost = (event) => {
    event.preventDefault();
    fallback();
  };
  try {
    gl = canvas.getContext("webgl2", {
      alpha: false, antialias: false, depth: false, stencil: false,
      powerPreference: "low-power",
    });
    if (!gl) {
      fallback();
    } else {
      const vertex = compile(gl.VERTEX_SHADER, VERTEX);
      const fragment = compile(gl.FRAGMENT_SHADER, FRAGMENT);
      program = gl.createProgram();
      if (vertex && fragment && program) {
        gl.attachShader(program, vertex);
        gl.attachShader(program, fragment);
        gl.bindAttribLocation(program, 0, "aPosition");
        gl.linkProgram(program);
      }
      if (vertex) gl.deleteShader(vertex);
      if (fragment) gl.deleteShader(fragment);
      if (!vertex || !fragment || !program || !gl.getProgramParameter(program, gl.LINK_STATUS)) {
        fallback();
      } else {
        for (const name of ["uResolution", "uTime", "uClock", "uAmplitude", "uWaveScale", "uWaveRatio", "uSwell", "uTurbulence", "uHeight", "uTilt", "uZoom", "uLook", "uFogDepth", "uBrightness", "uOpacity", "uGrain", "uHorizon", "uWave", "uCrest", "uBackground", "uOpaque", "uLight", "uSun", "uRelief", "uSheen", "uSteps", "uStride", "uIntro", "uSwells", "uSwellWidth"]) {
          u[name] = gl.getUniformLocation(program, name);
        }
        vao = gl.createVertexArray();
        buffer = gl.createBuffer();
        if (!vao || !buffer) throw new Error("Wave buffer unavailable");
        gl.bindVertexArray(vao);
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
        gl.enableVertexAttribArray(0);
        gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
        gl.useProgram(program);
        const values = {
          uAmplitude: 2.5, uWaveScale: 0.77, uWaveRatio: 0.9,
          uSwell: 35, uTurbulence: 20, uHeight: 5.5,
          uTilt: 64 * Math.PI / 180, uZoom: 1, uFogDepth: 15,
          uBrightness: 1, uOpacity: 1, uGrain: 0.08,
          uOpaque: 1, uRelief: 1, uSheen: 0, uSteps: 56,
          uSwellWidth: 8,
          uStride: 0.9 / Math.max(1, 2.5 * ((0.77 / 7) * (1 + 35 / 20) + ((0.77 * 0.9) / 3) * (1 + 20 / 23)) / 1.5),
        };
        for (const [name, value] of Object.entries(values)) gl.uniform1f(u[name], value);
        gl.uniform2f(u.uLook, 0, 0);
        gl.uniform3fv(u.uHorizon, color("#a60321"));
        gl.uniform3fv(u.uWave, color("#d97b66"));
        gl.uniform3fv(u.uCrest, color("#f2e9d8"));
        gl.uniform3f(u.uSun, Math.cos(0.52) * Math.cos(2 * Math.PI / 3), Math.cos(0.52) * Math.sin(2 * Math.PI / 3), Math.sin(0.52));
        gl.uniform3f(u.uIntro, 1, 0, 0);
        gl.uniform3fv(u.uSwells, new Float32Array(MAX_SWELLS * 3));
        container.append(canvas);
        canvas.addEventListener("webglcontextlost", onContextLost);
        resizeObserver = new ResizeObserver(() => {
          if (!document.hidden) draw();
        });
        resizeObserver.observe(container);
        document.addEventListener("visibilitychange", sync);
        reducedMotion.addEventListener("change", sync);
        sync();
      }
    }
  } catch {
    fallback();
  }
  return {
    setTheme(value) {
      theme = value;
      if (!document.hidden) draw();
    },
    setPaused(value) {
      paused = Boolean(value);
      sync();
    },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      cancel();
      resizeObserver?.disconnect();
      document.removeEventListener("visibilitychange", sync);
      reducedMotion.removeEventListener("change", sync);
      canvas.removeEventListener("webglcontextlost", onContextLost);
      release();
      gl?.getExtension("WEBGL_lose_context")?.loseContext();
      canvas.remove();
    },
  };
}
