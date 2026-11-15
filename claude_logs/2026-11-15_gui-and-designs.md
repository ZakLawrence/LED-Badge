# 2026-11-15 — Saved designs + Badge Studio GUI

## Goal / clarifications
- User asked whether the CLI could loop to push HH:MM each minute. Answer: it already can (`badge clock --live`),
  but stock firmware blocks it — no display while on USB, one BLE upload per button press. Suggested a test once
  the battery is full (the badge might show content on USB when not charging): `uv run badge clock --live -t usb`.
- Agreed plan: designs as JSON files + `badge show/save/designs`, then a local web GUI (user chose web app).

## Changes
- `src/ledbadge/design.py` (new): `Design`, `DesignMessage`, `DesignStore`; frames as `.#` row strings;
  animation = 44-px screens, other modes = frames joined horizontally; name validation (path-safe);
  `save()` refuses designs that exceed the 8 KB payload.
- `src/ledbadge/cli.py`: `--save NAME` on all generator commands (with `-p` = save only), new `designs`,
  `show NAME`, `gui` commands, global `--designs-dir` (default `./designs`); upload code split into `_send()`.
- `src/ledbadge/gui/server.py` (new): stdlib `ThreadingHTTPServer` on 127.0.0.1:8044; static files + JSON API
  (design CRUD, payload size, upload USB/BLE with a lock, BLE scan, generators text/life/clock/image).
- `src/ledbadge/gui/static/{index.html,style.css,app.js}` (new): Badge Studio — pixel editor (draw/erase,
  Bresenham drag, onion skin, undo/redo, clear/fill/invert/mirror/shift), frame strip, message tabs (≤8),
  mode/speed/blink/border, LED preview approximating each mode, generators, library, upload, size meter with
  BLE time estimate, keyboard shortcuts, `?design=NAME` deep link, unsaved-changes guard.
- `tests/test_design_gui.py` (new): 11 tests (round trip produces identical packed bitmaps, joins, bad names,
  invalid designs, server static/path traversal, generators, CRUD).
- `designs/hello.json`, `designs/life.json`: starter designs. README and `.claude/CLAUDE.md` updated.

## Verification
- `uv run pytest`: 18 passed.
- Headless Chrome (installed app, temp profile in scratchpad; Chrome extension declined by user):
  screenshots of the page empty and with `?design=hello`; scripted harness (scratchpad, not committed) running
  inside the real page: 14/14 checks pass — open design, payload size equals server's, text replace,
  long text → scroll + new message, switch to animation splits into screens, undo, life/clock generators,
  pointer-event drawing, all 9 preview modes render with blink+border, save/list/reload equality.
  Found and fixed: generator forms all visible (`[hidden]` overridden by CSS), long folder path overflow.
- Upload via GUI API over USB: 192 B in 0.04 s (not visually confirmed on the badge this time).
- Not verified: image/GIF upload through the browser file picker (server path is tested by unit tests only for
  text/life/clock; image generator exercised only via code path shared with CLI `image`, which also isn't
  hardware-tested), BLE upload from the GUI, real-mouse feel of the editor, preview timing vs the real badge.

## Open issues / next ideas
- Preview scroll speeds are guesses; could calibrate by timing the real badge.
- Ideas: playlists of designs, more on-badge effects (rain, spinner, snake demo), sprite/icon library for text.
