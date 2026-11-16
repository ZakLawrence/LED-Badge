# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

0RWX level: 3

Desktop control for a Badge Magic LED name badge (11x44 px, https://badgemagic.fossasia.org): a `badge` CLI
and a local web editor ("Badge Studio") for designing, saving and uploading content over USB or Bluetooth LE.

## Commands

```sh
uv sync                                   # create .venv (Python 3.12; deps hidapi, bleak, Pillow; dev pytest)
uv run pytest                             # all tests (no badge needed)
uv run pytest tests/test_protocol.py::test_header_fields   # single test
uv run badge <cmd> -p                     # any generator: ASCII preview, no upload
uv run badge gui                          # web editor on http://localhost:8044 (127.0.0.1 only)
uv run badge list | scan                  # find badge on USB / BLE
```

No linter is configured. There is no node in this environment: check the GUI's JS with headless Chrome
(`"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --user-data-dir=<scratch>
--virtual-time-budget=5000 --screenshot=... | --dump-dom <url>`). Scripted checks can be injected as an extra
`<script>` after `app.js` (classic scripts share its globals). The user declined the Claude-in-Chrome extension.
The GUI server must be restarted after Python changes; static files are re-read on every request.

## Architecture

Everything funnels into one pipeline:

    generators (font / render / effects / GUI editor)  ->  1-bit PIL images, 11 px high
      -> protocol.Message(bitmap, mode, speed, blink, marquee)   (max 8 per upload)
      -> protocol.build_payload()   64-byte "wang" header + packed bitmaps, padded to 64, <= 8192 bytes
      -> device.send() (USB HID, 64-byte reports + report-ID 0)  or  ble.send() (0xFEE1, 16-byte chunks)

- **Animation mode** consumes 48-px frames but the badge shows only columns 0-43 of each.
  `render.animation_strip` places 44-px frames at `protocol.ANIM_OFFSET` (= 0, confirmed on hardware; an earlier
  centred offset of 2 clipped designs). Max ~123 animation frames per payload (`max_animation_frames`).
- **Designs** (`design.py`, files in `designs/*.json`) store frames as 11 strings of `.`/`#`. In animation mode
  each frame is one 44-px screen; in every other mode the frames are joined left-to-right into one bitmap.
  `Design.payload()` is the single conversion to bytes and `DesignStore.save()` refuses designs over 8 KB.
  Names are validated because they are file names (path traversal is tested).
- **CLI** (`cli.py`): generator commands share `_common()` options and go through `_upload()` (preview / `--save`
  as design / send); `show` sends a saved design via `_send()`. `-t auto` = USB if attached, else BLE.
- **GUI** (`gui/server.py` + `gui/static/`): stdlib `ThreadingHTTPServer`, JSON API documented in the module
  docstring; generators run server-side, uploads serialised by a lock. `app.js` keeps its own frame model
  (`Uint8Array` rows), undo stack, and **duplicates** two pieces of Python logic that must stay in sync:
  payload size (`payloadBytes` vs `build_payload`) and the 44-px split/join rules. Its preview (`displayAt`)
  only approximates badge timing (`FPS` from fossasia docs; scroll speeds are guesses).
- **Fonts** (`font.py`) are hand-drawn glyph strings because TrueType fonts at 11 px rendered badly; unknown
  characters fall back to `?`.

## Hardware facts (stock firmware, CH583 badge — observed, not from docs)

- USB HID `0416:5020` ("wch.cn CH583"); BLE name `LSLED`, service 0xFEE0, char 0xFEE1 (write/read/notify), MTU 23.
- While plugged in the badge shows only a charging screen; uploaded content appears after unplugging.
  So `badge clock --live` cannot be seen over USB (untested once the battery is full).
- BLE: one upload per button press — the badge disconnects once the header-announced data has arrived (padding
  writes then fail; `ble.py` tolerates this) and stops advertising. ~1 s per 16-byte write, ~2 min for 8 KB.
- Uploads overwrite all 8 message slots.
- Do NOT suggest flashing fossasia/badgemagic-firmware: it targets CH582M only and is irreversible.
- Protocol reference: fossasia/led-name-badge-ls32 `lednamebadge.py` (GPL — reimplement, don't copy or execute it).

## Project conventions

- `designs/` holds the user's own designs (created/deleted through the GUI); commit them with related work but
  don't modify or delete them unasked.
- Session logs go in `claude_logs/YYYY-MM-DD_<task>.md`.
