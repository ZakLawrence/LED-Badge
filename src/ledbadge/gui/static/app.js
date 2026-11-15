// Badge Studio — pixel editor + design library for the LED badge.
// Frames are kept as arrays of 11 Uint8Array rows; converted to ".#" strings for the API.
"use strict";

const H = 11, W = 44, FRAME_W = 48, MAX_BYTES = 8192;
const FPS = [1.2, 1.3, 2.0, 2.4, 2.8, 4.5, 7.5, 15];   // animation mode (measured by fossasia)
const SCROLL = [6, 8, 12, 16, 20, 28, 38, 50];          // px/s, rough guess for scroll modes
const BLE_BYTES_PER_S = 66;                              // measured: 8192 B in 123 s
const CELL = 16;                                         // editor cell size (px)

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

// ---------------------------------------------------------------- frame helpers
const blankFrame = (w = W) => Array.from({ length: H }, () => new Uint8Array(w));
const frameW = (f) => f[0].length;
const cloneFrame = (f) => f.map((r) => r.slice());
const rowsToFrame = (rows) => rows.map((r) => Uint8Array.from(r, (c) => (c === "#" ? 1 : 0)));
const frameToRows = (f) => f.map((r) => Array.from(r, (v) => (v ? "#" : ".")).join(""));

function resizeFrame(f, w, center = false) {
  const out = blankFrame(w);
  const off = center ? Math.floor((w - frameW(f)) / 2) : 0;
  for (let y = 0; y < H; y++)
    for (let x = 0; x < frameW(f); x++) {
      const nx = x + off;
      if (nx >= 0 && nx < w) out[y][nx] = f[y][x];
    }
  return out;
}

/** Join frames left-to-right (what non-animation modes upload). */
function joinFrames(frames) {
  const w = frames.reduce((s, f) => s + frameW(f), 0);
  const out = blankFrame(w);
  let x0 = 0;
  for (const f of frames) {
    for (let y = 0; y < H; y++) out[y].set(f[y], x0);
    x0 += frameW(f);
  }
  return out;
}

/** Split a wide bitmap into 44-px screens (used when switching to animation mode). */
function splitFrames(f) {
  const out = [];
  for (let x0 = 0; x0 < frameW(f); x0 += W) {
    const g = blankFrame();
    for (let y = 0; y < H; y++) g[y].set(f[y].subarray(x0, x0 + W));
    out.push(g);
  }
  return out.length ? out : [blankFrame()];
}

// ---------------------------------------------------------------- state
const newMessage = () => ({ mode: "fixed", speed: 4, blink: false, marquee: false, frames: [blankFrame()] });
const newDesign = () => ({ name: "untitled", brightness: 100, messages: [newMessage()] });

let design = newDesign();
let cur = { msg: 0, frame: 0 };
let tool = "draw";
let undoStack = [], redoStack = [];
let savedSnapshot = "";
let loadedName = null;     // name of the design file currently open (null = never saved)
let knownDesigns = [];

const msg = () => design.messages[cur.msg];
const frame = () => msg().frames[cur.frame];

function toJSON(d = design) {
  return {
    version: 1, name: d.name, brightness: d.brightness,
    messages: d.messages.map((m) => ({
      mode: m.mode, speed: m.speed, blink: m.blink, marquee: m.marquee, frames: m.frames.map(frameToRows),
    })),
  };
}
function fromJSON(j) {
  return {
    name: j.name, brightness: j.brightness ?? 100,
    messages: j.messages.map((m) => ({
      mode: m.mode, speed: m.speed, blink: !!m.blink, marquee: !!m.marquee, frames: m.frames.map(rowsToFrame),
    })),
  };
}
const serialize = () => JSON.stringify(toJSON());

function clampCursor() {
  cur.msg = Math.max(0, Math.min(cur.msg, design.messages.length - 1));
  cur.frame = Math.max(0, Math.min(cur.frame, msg().frames.length - 1));
}

// ---------------------------------------------------------------- undo
function checkpoint() {
  undoStack.push({ json: serialize(), cur: { ...cur } });
  if (undoStack.length > 200) undoStack.shift();
  redoStack = [];
}
function restore(snap) {
  design = fromJSON(JSON.parse(snap.json));
  cur = { ...snap.cur };
  clampCursor();
  renderAll();
}
function undo() {
  if (!undoStack.length) return;
  redoStack.push({ json: serialize(), cur: { ...cur } });
  restore(undoStack.pop());
}
function redo() {
  if (!redoStack.length) return;
  undoStack.push({ json: serialize(), cur: { ...cur } });
  restore(redoStack.pop());
}

// ---------------------------------------------------------------- API
async function api(method, path, body) {
  const res = await fetch("/api/" + path, {
    method, headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

let toastTimer;
function toast(text, kind = "", ms = 3500) {
  const t = $("#toast");
  t.textContent = text;
  t.className = "toast " + kind;
  t.hidden = false;
  clearTimeout(toastTimer);
  if (ms) toastTimer = setTimeout(() => (t.hidden = true), ms);
}

// ---------------------------------------------------------------- payload size
function payloadBytes() {
  let n = 64;
  for (const m of design.messages) {
    const w = m.mode === "animation" ? FRAME_W * m.frames.length : m.frames.reduce((s, f) => s + frameW(f), 0);
    n += 11 * Math.ceil(w / 8);
  }
  return Math.ceil(n / 64) * 64;
}
function renderMeter() {
  const n = payloadBytes();
  const fill = $("#meter-fill");
  fill.style.width = Math.min(100, (100 * n) / MAX_BYTES) + "%";
  fill.className = n > MAX_BYTES ? "over" : n > 0.8 * MAX_BYTES ? "warn" : "";
  $("#meter-text").textContent =
    `${n} / ${MAX_BYTES} bytes` + (n > MAX_BYTES ? " — too big for the badge!" : "") +
    ` · Bluetooth ≈ ${Math.ceil(n / BLE_BYTES_PER_S)} s`;
}

// ---------------------------------------------------------------- rendering: chrome
function markChanged() {
  renderAll();
}

function renderAll() {
  clampCursor();
  $("#design-name").value = design.name;
  $("#brightness").value = String(design.brightness);
  renderTabs();
  renderSettings();
  renderEditor();
  renderStrip();
  renderMeter();
  renderLibrary();
  $("#dirty").hidden = serialize() === savedSnapshot;
}

function renderTabs() {
  const tabs = $("#msg-tabs");
  tabs.innerHTML = "";
  design.messages.forEach((m, i) => {
    const b = document.createElement("button");
    b.textContent = `${i + 1} · ${m.mode}`;
    b.className = i === cur.msg ? "active" : "";
    b.onclick = () => { cur = { msg: i, frame: 0 }; previewStart = performance.now(); renderAll(); };
    tabs.append(b);
  });
  if (design.messages.length < 8) {
    const add = document.createElement("button");
    add.textContent = "+ message";
    add.title = "Add a message slot (the badge cycles through them)";
    add.onclick = () => {
      checkpoint();
      design.messages.push(newMessage());
      cur = { msg: design.messages.length - 1, frame: 0 };
      markChanged();
    };
    tabs.append(add);
  }
}

function renderSettings() {
  const m = msg();
  $("#mode").value = m.mode;
  $("#speed").value = m.speed;
  $("#speed-out").textContent =
    m.speed + (m.mode === "animation" ? ` (~${FPS[m.speed - 1]} fps)` : "");
  $("#blink").checked = m.blink;
  $("#marquee").checked = m.marquee;
  $("#btn-del-msg").disabled = design.messages.length < 2;
  const anim = m.mode === "animation";
  $("#width-ctl").hidden = anim;
  $("#frame-width").value = frameW(frame());
  $("#frames-hint").textContent = anim
    ? "Animation: each frame is one 44×11 screen, played in order and looped."
    : "This mode joins all frames left-to-right into one bitmap. Widen a frame for long scrolling text.";
}

// ---------------------------------------------------------------- rendering: editor
const editor = $("#editor");
const ectx = editor.getContext("2d");
const css = getComputedStyle(document.documentElement);
const LED_ON = css.getPropertyValue("--led-on").trim();
const LED_OFF = css.getPropertyValue("--led-off").trim();

function renderEditor() {
  const f = frame();
  const w = frameW(f);
  const dpr = window.devicePixelRatio || 1;
  editor.width = w * CELL * dpr;
  editor.height = H * CELL * dpr;
  editor.style.width = w * CELL + "px";
  editor.style.height = H * CELL + "px";
  ectx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ectx.fillStyle = "#0b0b0c";
  ectx.fillRect(0, 0, w * CELL, H * CELL);
  const prev = $("#onion").checked && cur.frame > 0 && msg().mode === "animation" ? msg().frames[cur.frame - 1] : null;
  const r = CELL * 0.38;
  for (let y = 0; y < H; y++)
    for (let x = 0; x < w; x++) {
      const on = f[y][x];
      ectx.fillStyle = on ? LED_ON : prev && prev[y]?.[x] ? "#7a4a1c" : LED_OFF;
      ectx.beginPath();
      ectx.arc(x * CELL + CELL / 2, y * CELL + CELL / 2, r, 0, 2 * Math.PI);
      ectx.fill();
    }
  // guides: every 8 columns (byte boundaries) faintly, and the 44-px screen edge
  ectx.strokeStyle = "#ffffff14";
  ectx.lineWidth = 1;
  for (let x = 8; x < w; x += 8) {
    ectx.beginPath(); ectx.moveTo(x * CELL + 0.5, 0); ectx.lineTo(x * CELL + 0.5, H * CELL); ectx.stroke();
  }
  if (w > W) {
    ectx.strokeStyle = "#3a7bffaa";
    ectx.setLineDash([4, 4]);
    for (let x = W; x < w; x += W) {
      ectx.beginPath(); ectx.moveTo(x * CELL + 0.5, 0); ectx.lineTo(x * CELL + 0.5, H * CELL); ectx.stroke();
    }
    ectx.setLineDash([]);
  }
}

function drawThumb(canvas, f, scale = 3) {
  const w = frameW(f);
  canvas.width = w * scale;
  canvas.height = H * scale;
  const c = canvas.getContext("2d");
  c.fillStyle = "#0b0b0c";
  c.fillRect(0, 0, canvas.width, canvas.height);
  c.fillStyle = LED_ON;
  for (let y = 0; y < H; y++)
    for (let x = 0; x < w; x++) if (f[y][x]) c.fillRect(x * scale, y * scale, scale - 0.5, scale - 0.5);
}

function renderStrip() {
  const strip = $("#frame-strip");
  strip.innerHTML = "";
  msg().frames.forEach((f, i) => {
    const c = document.createElement("canvas");
    drawThumb(c, f);
    c.className = i === cur.frame ? "current" : "";
    c.title = `frame ${i + 1}`;
    c.onclick = () => { cur.frame = i; renderAll(); };
    strip.append(c);
  });
  const cnt = msg().frames.length;
  $("#frame-count").textContent = `${cur.frame + 1} / ${cnt}`;
  strip.children[cur.frame]?.scrollIntoView({ block: "nearest", inline: "nearest" });
  $("#btn-del-frame").disabled = cnt < 2;
}

function updateCurrentThumb() {
  const c = $("#frame-strip").children[cur.frame];
  if (c) drawThumb(c, frame());
}

// ---------------------------------------------------------------- editor input
let stroke = null; // {value, last:[x,y]}

function cellAt(ev) {
  const r = editor.getBoundingClientRect();
  return [Math.floor((ev.clientX - r.left) / CELL), Math.floor((ev.clientY - r.top) / CELL)];
}
function setPixel(x, y, v) {
  const f = frame();
  if (x >= 0 && y >= 0 && x < frameW(f) && y < H) f[y][x] = v;
}
function line(x0, y0, x1, y1, v) {  // Bresenham so fast drags don't leave gaps
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    setPixel(x0, y0, v);
    if (x0 === x1 && y0 === y1) break;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}

editor.addEventListener("contextmenu", (e) => e.preventDefault());
editor.addEventListener("pointerdown", (ev) => {
  const [x, y] = cellAt(ev);
  if (x < 0 || y < 0 || x >= frameW(frame()) || y >= H) return;
  checkpoint();
  let value;
  if (ev.button === 2 || tool === "erase") value = 0;
  else value = frame()[y][x] ? 0 : 1; // starting on a lit pixel erases
  stroke = { value, last: [x, y] };
  setPixel(x, y, value);
  editor.setPointerCapture(ev.pointerId);
  renderEditor();
  updateCurrentThumb();
});
editor.addEventListener("pointermove", (ev) => {
  if (!stroke) return;
  const [x, y] = cellAt(ev);
  line(stroke.last[0], stroke.last[1], x, y, stroke.value);
  stroke.last = [x, y];
  renderEditor();
  updateCurrentThumb();
});
const endStroke = () => { if (stroke) { stroke = null; markChanged(); } };
editor.addEventListener("pointerup", endStroke);
editor.addEventListener("pointercancel", endStroke);

// frame operations
const OPS = {
  clear: (f) => f.forEach((r) => r.fill(0)),
  fill: (f) => f.forEach((r) => r.fill(1)),
  invert: (f) => f.forEach((r) => r.forEach((v, i) => (r[i] = v ? 0 : 1))),
  flip: (f) => f.forEach((r) => r.reverse()),
  left: (f) => f.forEach((r) => { r.copyWithin(0, 1); r[r.length - 1] = 0; }),
  right: (f) => f.forEach((r) => { r.copyWithin(1, 0); r[0] = 0; }),
  up: (f) => { for (let y = 0; y < H - 1; y++) f[y].set(f[y + 1]); f[H - 1].fill(0); },
  down: (f) => { for (let y = H - 1; y > 0; y--) f[y].set(f[y - 1]); f[0].fill(0); },
};
$$("[data-op]").forEach((b) => (b.onclick = () => { checkpoint(); OPS[b.dataset.op](frame()); markChanged(); }));
$$("[data-tool]").forEach((b) => (b.onclick = () => setTool(b.dataset.tool)));
function setTool(t) {
  tool = t;
  $$("[data-tool]").forEach((b) => b.classList.toggle("active", b.dataset.tool === t));
}
$("#onion").onchange = renderEditor;
$("#btn-undo").onclick = undo;
$("#btn-redo").onclick = redo;

// frames
$("#btn-add-frame").onclick = () => {
  checkpoint();
  msg().frames.splice(cur.frame + 1, 0, blankFrame(msg().mode === "animation" ? W : frameW(frame())));
  cur.frame++;
  markChanged();
};
$("#btn-dup-frame").onclick = () => {
  checkpoint();
  msg().frames.splice(cur.frame + 1, 0, cloneFrame(frame()));
  cur.frame++;
  markChanged();
};
$("#btn-del-frame").onclick = () => {
  if (msg().frames.length < 2) return;
  checkpoint();
  msg().frames.splice(cur.frame, 1);
  markChanged();
};
function moveFrame(d) {
  const fs = msg().frames, j = cur.frame + d;
  if (j < 0 || j >= fs.length) return;
  checkpoint();
  [fs[cur.frame], fs[j]] = [fs[j], fs[cur.frame]];
  cur.frame = j;
  markChanged();
}
$("#btn-move-l").onclick = () => moveFrame(-1);
$("#btn-move-r").onclick = () => moveFrame(1);
$("#frame-width").onchange = (e) => {
  const w = Math.max(1, Math.min(2000, parseInt(e.target.value, 10) || W));
  if (w === frameW(frame())) return;
  checkpoint();
  msg().frames[cur.frame] = resizeFrame(frame(), w);
  markChanged();
};

// message settings
$("#mode").onchange = (e) => {
  checkpoint();
  const m = msg(), mode = e.target.value;
  if (mode === "animation" && m.mode !== "animation") {
    // one wide banner -> 44-px screens; otherwise fit each frame to 44 px
    m.frames = m.frames.length === 1 && frameW(m.frames[0]) > W
      ? splitFrames(m.frames[0])
      : m.frames.map((f) => (frameW(f) === W ? f : resizeFrame(f, W, frameW(f) < W)));
    cur.frame = 0;
  }
  m.mode = mode;
  previewStart = performance.now();
  markChanged();
};
$("#speed").onpointerdown = checkpoint;
$("#speed").oninput = (e) => { msg().speed = +e.target.value; renderSettings(); };
$("#speed").onchange = () => markChanged();
$("#blink").onchange = (e) => { checkpoint(); msg().blink = e.target.checked; markChanged(); };
$("#marquee").onchange = (e) => { checkpoint(); msg().marquee = e.target.checked; markChanged(); };
$("#btn-del-msg").onclick = () => {
  if (design.messages.length < 2 || !confirm(`Delete message ${cur.msg + 1}?`)) return;
  checkpoint();
  design.messages.splice(cur.msg, 1);
  cur = { msg: Math.max(0, cur.msg - 1), frame: 0 };
  markChanged();
};
$("#design-name").oninput = (e) => { design.name = e.target.value.trim() || "untitled"; $("#dirty").hidden = serialize() === savedSnapshot; };
$("#brightness").onchange = (e) => { checkpoint(); design.brightness = +e.target.value; markChanged(); };

// ---------------------------------------------------------------- preview
const preview = $("#preview");
const pctx = preview.getContext("2d");
let previewStart = performance.now();
let playing = true;
let pausedAt = 0;
let perimeter = null;

function perimeterCells() {
  if (perimeter) return perimeter;
  perimeter = [];
  for (let x = 0; x < W; x++) perimeter.push([x, 0]);
  for (let y = 1; y < H; y++) perimeter.push([W - 1, y]);
  for (let x = W - 2; x >= 0; x--) perimeter.push([x, H - 1]);
  for (let y = H - 2; y > 0; y--) perimeter.push([0, y]);
  return perimeter;
}

/** Approximate what the badge shows for message m at time t (seconds). */
function displayAt(m, t) {
  const buf = blankFrame();
  const strip = m.mode === "animation" ? null : joinFrames(m.frames);
  const sw = strip ? frameW(strip) : W;
  const get = (x, y) => (x >= 0 && x < sw && y >= 0 && y < H ? strip[y][x] : 0);
  const v = SCROLL[m.speed - 1];
  const fill = (fn) => { for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) buf[y][x] = fn(x, y) ? 1 : 0; };
  const centreOff = sw < W ? -Math.floor((W - sw) / 2) : 0;

  switch (m.mode) {
    case "animation": {
      const f = m.frames[Math.floor(t * FPS[m.speed - 1]) % m.frames.length];
      for (let y = 0; y < H; y++) buf[y].set(f[y].subarray(0, W));
      break;
    }
    case "left": { const off = Math.floor(t * v) % (sw + W); fill((x, y) => get(x + off - W, y)); break; }
    case "right": { const off = Math.floor(t * v) % (sw + W); fill((x, y) => get(x + sw - off, y)); break; }
    case "up": case "down": {
      const pages = Math.max(1, Math.ceil(sw / W)), rows = v / 2, slide = H / rows, hold = 1.5;
      const per = 2 * slide + hold, pt = t % (pages * per), page = Math.floor(pt / per), p = pt % per;
      let off = p < slide ? H - Math.floor(p * rows) : p < slide + hold ? 0 : -Math.floor((p - slide - hold) * rows);
      if (m.mode === "down") off = -off;
      fill((x, y) => get(page * W + x + (sw < W ? centreOff : 0), y - off));
      break;
    }
    case "fixed": fill((x, y) => get(x + centreOff, y)); break;
    case "laser": case "picture": case "snowflake": {
      const dur = W / v + 0.2, hold = 2, p = t % (dur + hold), k = Math.min(1, p / dur);
      if (m.mode === "laser") {
        const col = Math.floor(k * W);
        fill((x, y) => (x < col ? get(x + centreOff, y) : x === col && k < 1));
      } else if (m.mode === "picture") {
        const half = k * (W / 2);
        fill((x, y) => Math.abs(x + 0.5 - W / 2) <= half && get(x + centreOff, y));
      } else {
        for (let y = 0; y < H; y++)
          for (let x = 0; x < W; x++)
            if (get(x + centreOff, y)) {
              const yy = Math.round(y - (1 - k) * (H + ((x * 7 + y * 3) % H)));
              if (yy >= 0 && yy < H) buf[yy][x] = 1;
            }
      }
      break;
    }
  }
  if (m.blink && Math.floor(t * 2) % 2 === 1) buf.forEach((r) => r.fill(0));
  if (m.marquee) {
    const s = Math.floor(t * 8);
    perimeterCells().forEach(([x, y], i) => { if ((i + s) % 4 < 2) buf[y][x] = 1; });
  }
  return buf;
}

function drawPreview(now) {
  const t = ((playing ? now : pausedAt) - previewStart) / 1000;
  const buf = displayAt(msg(), Math.max(0, t));
  const cw = preview.width / W, ch = preview.height / H, r = Math.min(cw, ch) * 0.36;
  pctx.fillStyle = "#0b0b0c";
  pctx.fillRect(0, 0, preview.width, preview.height);
  for (const pass of [0, 1]) {
    pctx.fillStyle = pass ? LED_ON : LED_OFF;
    pctx.shadowColor = LED_ON;
    pctx.shadowBlur = pass ? r * 1.4 : 0;
    pctx.beginPath();
    for (let y = 0; y < H; y++)
      for (let x = 0; x < W; x++)
        if ((buf[y][x] ? 1 : 0) === pass) {
          pctx.moveTo(x * cw + cw / 2 + r, y * ch + ch / 2);
          pctx.arc(x * cw + cw / 2, y * ch + ch / 2, r, 0, 2 * Math.PI);
        }
    pctx.fill();
  }
  pctx.shadowBlur = 0;
  requestAnimationFrame(drawPreview);
}
$("#btn-play").onclick = (e) => {
  playing = !playing;
  if (!playing) pausedAt = performance.now();
  else previewStart += performance.now() - pausedAt;
  e.target.textContent = playing ? "Pause" : "Play";
};

// ---------------------------------------------------------------- generators
let genKind = "text";
$$("#gen-tabs button").forEach((b) => (b.onclick = () => {
  genKind = b.dataset.gen;
  $$("#gen-tabs button").forEach((x) => x.classList.toggle("active", x === b));
  $$("form.gen").forEach((f) => (f.hidden = f.dataset.gen !== genKind));
}));
$$("form.gen").forEach((f) => f.addEventListener("submit", (e) => { e.preventDefault(); applyGenerated("replace"); }));

const readFile = (file) => new Promise((res, rej) => {
  const r = new FileReader();
  r.onload = () => res(r.result);
  r.onerror = () => rej(r.error);
  r.readAsDataURL(file);
});

/** Ask the server to generate frames. Returns {frames, mode, speed}. */
async function generate() {
  const form = $(`form.gen[data-gen="${genKind}"]`);
  const val = (n) => form.elements[n].value;
  const chk = (n) => form.elements[n].checked;
  if (genKind === "text") {
    const r = await api("POST", "generate/text", { text: val("text"), font: val("font"), width: chk("pad") ? W : 0 });
    const f = r.frames.map(rowsToFrame);
    return { frames: f, mode: frameW(f[0]) > W ? "left" : "fixed" };
  }
  if (genKind === "image") {
    const file = form.elements.file.files[0];
    if (!file) throw new Error("choose an image file first");
    const r = await api("POST", "generate/image", {
      data: await readFile(file), width: val("width") || null, dither: chk("dither"), invert: chk("invert"),
      threshold: +val("threshold"), max_frames: +val("max_frames"),
    });
    const f = r.frames.map(rowsToFrame);
    return { frames: f, mode: r.animated ? "animation" : frameW(f[0]) > W ? "left" : "fixed" };
  }
  if (genKind === "life") {
    const r = await api("POST", "generate/life", {
      frames: +val("frames"), density: +val("density"), seed: val("seed"), wrap: chk("wrap"),
    });
    $("#life-seed").textContent = `seed ${r.seed}: ${r.frames.length} generations` +
      (r.frames.length < +val("frames") ? " (died out or repeated early)" : "");
    return { frames: r.frames.map(rowsToFrame), mode: "animation", speed: 6 };
  }
  const r = await api("POST", "generate/clock", { format: val("format") });
  return { frames: r.frames.map(rowsToFrame), mode: "animation", speed: 3 };
}

async function applyGenerated(how) {
  let g;
  try { g = await generate(); } catch (e) { return toast(e.message, "error"); }
  checkpoint();
  if (how === "new") {
    if (design.messages.length >= 8) return toast("the badge holds at most 8 messages", "error");
    design.messages.push({ ...newMessage(), mode: g.mode, speed: g.speed ?? 4, frames: g.frames });
    cur = { msg: design.messages.length - 1, frame: 0 };
  } else if (how === "replace") {
    Object.assign(msg(), { frames: g.frames, mode: g.mode, ...(g.speed ? { speed: g.speed } : {}) });
    cur.frame = 0;
  } else {
    let frames = g.frames;
    if (msg().mode === "animation") frames = frames.flatMap((f) => (frameW(f) > W ? splitFrames(f) : [resizeFrame(f, W, true)]));
    msg().frames.splice(cur.frame + 1, 0, ...frames);
    cur.frame += 1;
  }
  previewStart = performance.now();
  markChanged();
}
$("#gen-replace").onclick = () => applyGenerated("replace");
$("#gen-append").onclick = () => applyGenerated("append");
$("#gen-new-msg").onclick = () => applyGenerated("new");

// ---------------------------------------------------------------- library
async function refreshLibrary() {
  try {
    const r = await api("GET", "designs");
    knownDesigns = r.designs;
    $("#design-folder").textContent = r.folder;
  } catch (e) { toast("could not list designs: " + e.message, "error"); }
  renderLibrary();
}
function renderLibrary() {
  const ul = $("#design-list");
  ul.innerHTML = "";
  if (!knownDesigns.length) ul.innerHTML = '<li class="hint">nothing saved yet</li>';
  for (const name of knownDesigns) {
    const li = document.createElement("li");
    li.className = name === loadedName ? "current" : "";
    li.textContent = name;
    li.onclick = () => openDesign(name);
    const del = document.createElement("button");
    del.className = "del";
    del.textContent = "×";
    del.title = "Delete design";
    del.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(`Delete design "${name}"? This removes the file.`)) return;
      await api("DELETE", "designs/" + encodeURIComponent(name)).catch((err) => toast(err.message, "error"));
      if (loadedName === name) loadedName = null;
      refreshLibrary();
    };
    li.append(del);
    ul.append(li);
  }
}
const isDirty = () => serialize() !== savedSnapshot;
async function openDesign(name) {
  if (isDirty() && !confirm("Discard unsaved changes?")) return;
  try {
    design = fromJSON(await api("GET", "designs/" + encodeURIComponent(name)));
  } catch (e) { return toast(e.message, "error"); }
  loadedName = name;
  cur = { msg: 0, frame: 0 };
  undoStack = []; redoStack = [];
  savedSnapshot = serialize();
  previewStart = performance.now();
  renderAll();
}
async function saveDesign() {
  const name = design.name.trim();
  if (name !== loadedName && knownDesigns.includes(name) && !confirm(`Overwrite existing design "${name}"?`)) return;
  try {
    await api("PUT", "designs/" + encodeURIComponent(name), toJSON());
  } catch (e) { return toast("save failed: " + e.message, "error"); }
  loadedName = name;
  savedSnapshot = serialize();
  toast(`saved "${name}"`);
  await refreshLibrary();
  renderAll();
}
$("#btn-save").onclick = saveDesign;
$("#btn-new").onclick = () => {
  if (isDirty() && !confirm("Discard unsaved changes?")) return;
  design = newDesign();
  loadedName = null;
  cur = { msg: 0, frame: 0 };
  undoStack = []; redoStack = [];
  savedSnapshot = serialize();
  renderAll();
};

// ---------------------------------------------------------------- upload + status
$("#btn-upload").onclick = async () => {
  const n = payloadBytes();
  if (n > MAX_BYTES) return toast(`design is ${n} bytes; the badge holds ${MAX_BYTES}`, "error");
  const transport = $("#transport").value;
  const btn = $("#btn-upload");
  btn.disabled = true;
  const viaBle = transport === "ble" || (transport === "auto" && !usbPresent);
  toast(viaBle
    ? `Uploading over Bluetooth (~${Math.ceil(n / BLE_BYTES_PER_S)} s). Make sure the badge is in Bluetooth mode…`
    : "Uploading over USB…", "busy", 0);
  try {
    const r = await api("POST", "upload", { design: toJSON(), transport });
    toast(`Uploaded ${r.bytes} bytes via ${r.transport} in ${r.seconds.toFixed(1)} s` +
      (r.transport === "usb" ? " — unplug the badge to see it." : ""), "", 6000);
  } catch (e) {
    toast("Upload failed: " + e.message, "error", 8000);
  } finally {
    btn.disabled = false;
  }
};

let usbPresent = false;
async function pollStatus() {
  try {
    usbPresent = (await api("GET", "status")).usb;
    const pill = $("#usb-status");
    pill.textContent = usbPresent ? "USB: connected" : "USB: not connected";
    pill.classList.toggle("ok", usbPresent);
  } catch { /* server gone; keep last state */ }
}
setInterval(pollStatus, 3000);

// ---------------------------------------------------------------- keyboard
document.addEventListener("keydown", (e) => {
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); saveDesign(); return; }
  if (e.target.matches("input, select, textarea")) return;
  if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
  if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); return; }
  if (e.key === "[" && cur.frame > 0) { cur.frame--; renderAll(); }
  if (e.key === "]" && cur.frame < msg().frames.length - 1) { cur.frame++; renderAll(); }
  if (e.key === "d") setTool("draw");
  if (e.key === "e") setTool("erase");
});
window.addEventListener("beforeunload", (e) => { if (isDirty()) e.preventDefault(); });

// ---------------------------------------------------------------- start
savedSnapshot = serialize();
renderAll();
refreshLibrary();
pollStatus();
const initial = new URLSearchParams(location.search).get("design");
if (initial) openDesign(initial);
requestAnimationFrame(drawPreview);
