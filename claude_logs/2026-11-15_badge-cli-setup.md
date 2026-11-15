# 2026-11-15 — LED badge desktop control: project setup, CLI, USB + BLE

## Goal
Control the Badge Magic LED badge from the Mac beyond plain text: start with a CLI (GUI later), try
"cooler" content such as a clock and Game of Life. Project is 0RWX Level 3 (recorded in `.claude/CLAUDE.md`).

## Hardware findings
- USB: `wch.cn CH583`, VID/PID `0416:5020`, vendor HID page 0xFF00, 64-byte in/out reports, no report IDs.
  Initially invisible because the badge battery was flat / previous cable; appeared after charging + Apple cable.
- BLE: advertises as `LSLED`, service `0xFEE0`, characteristic `0xFEE1` (write, read, notify), MTU 23.
- Stock firmware behaviour (observed, confirmed visually by user):
  - USB upload works (~0.04 s) but the badge shows a charging screen while plugged in; content appears on unplug.
  - BLE upload works; badge disconnects as soon as the header-announced data is received (padding writes fail),
    then stops advertising (polled 40 s, never returned) → one upload per button press.
  - BLE is slow: full 8192-byte payload took 123 s (~1 s per acknowledged 16-byte write).
- Open-source firmware (fossasia/badgemagic-firmware) supports CH582M only and flashing is irreversible →
  not recommended for this CH583 badge.

## Changes (new uv project `ledbadge`, deps hidapi, bleak, pillow; dev pytest)
- `src/ledbadge/protocol.py` — header/bitmap packing, `Message`, `Mode`, payload size checks.
  Format taken from reading fossasia/led-name-badge-ls32 `lednamebadge.py` (GPL; reimplemented, not copied).
- `src/ledbadge/device.py` — USB HID transport via hidapi (64-byte reports, report ID 0 prefix).
- `src/ledbadge/ble.py` — BLE transport via bleak (16-byte chunks, write-with-response, tolerate the
  post-data disconnect), `scan()`, `BleBadge` async class.
- `src/ledbadge/font.py` — hand-drawn 5x7 proportional font (+descenders) and 5x9 "big" digits;
  TrueType fonts at 11 px had bad hinting artefacts (checked Aileron, Menlo, Monaco).
- `src/ledbadge/render.py` — image → dithered 11-px bitmap, GIF → frames, 48-px animation strips, ASCII/PNG previews.
- `src/ledbadge/effects.py` — Game of Life (torus, picks the longest-lived of 200 random soups, ≤123 frames),
  clock frames (blinking colon, optional seconds bar), test patterns.
- `src/ledbadge/cli.py` — `badge list|scan|text|image|life|clock|test`, common options mode/speed/blink/marquee/
  brightness/preview/png/transport/frame-offset. Entry point in `pyproject.toml`.
- `tests/test_protocol.py` — 7 tests (bit order, header fields, padding/limit, fonts, life rules, shapes).
- `README.md`, `.claude/CLAUDE.md`, `.gitignore`.

## Verification
- `uv run pytest`: 7 passed.
- Hardware, confirmed by user looking at the badge:
  - USB `text "HI" -m fixed` → shown after unplugging.
  - BLE fixed text "BLE ok" → shown.
  - BLE `badge life` (123 generations, 8192 bytes) → animates correctly, no visible edge clipping/jumping
    (so the default 2-px frame offset looks right).
- Not verified on hardware: `clock`, `image`/GIF, `test frame`/`test modes`, brightness, blink/marquee,
  multi-message cycling, `--seconds-bar` timing, the reconnect path in `BleBadge`.
- Attempted to cross-check payloads by executing the downloaded reference script; blocked by the permission
  classifier (executing downloaded code), so tests encode expected bytes from reading the reference instead.

## Open issues / next steps
- A minute-by-minute live clock is not feasible with stock firmware: no display while on USB, and BLE needs a
  button press per upload. Animation memory (~123 frames at ≥1.2 fps) covers ≤ ~100 s, so no on-badge clock either.
  Worth checking once fully charged whether the badge displays content on USB when not charging.
- BLE speed: try 20-byte chunks (MTU 23) or write-without-response (characteristic doesn't advertise it) —
  each test costs a button press.
- GUI (next phase): live LED preview, pixel editor, effect gallery, upload over USB/BLE.
