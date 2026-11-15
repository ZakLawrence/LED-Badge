# LED Badge

0RWX level: 3

Desktop control for a Badge Magic LED name badge (11x44 px, https://badgemagic.fossasia.org).

- Hardware: WCH CH583-based badge, USB HID `0416:5020` ("wch.cn CH583"); BLE name `LSLED`, service 0xFEE0, char 0xFEE1.
- Observed (stock firmware): no display while on USB (charging screen; shows content after unplug). BLE: one upload per
  button press, badge disconnects once data is complete, ~1 s per 16-byte write -> 8 KB takes ~2 min.
- Do NOT suggest flashing fossasia/badgemagic-firmware: it targets CH582M only, irreversible (stock fw read-protected).
- Env: `uv` project, Python 3.12, deps `hidapi`, `bleak`, `Pillow` (dev: `pytest`). Run with `uv run badge ...`, tests with `uv run pytest`.
- Layout: `src/ledbadge/` — `protocol.py` (payload format), `device.py` (USB HID), `ble.py` (Bluetooth), `font.py` (hand-drawn pixel fonts),
  `render.py` (images/animation strips/previews), `effects.py` (Game of Life, clock, test patterns), `design.py` (JSON designs in `designs/`),
  `gui/` (stdlib HTTP server + static HTML/JS editor, `badge gui`), `cli.py`.
- Protocol reference: fossasia/led-name-badge-ls32 `lednamebadge.py` (GPL — don't copy code, and don't execute it).
- Use `-p/--preview` to see output in the terminal without uploading; uploads overwrite all 8 badge slots.
- GUI checks: no node here; verify JS with headless Chrome (`--headless=new --dump-dom/--screenshot`, temp
  `--user-data-dir`). The user declined the Claude-in-Chrome extension.
