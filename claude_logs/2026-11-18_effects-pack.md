# 2026-11-17/18 — Effects pack: Pong, rain, binary rain, wave text, collider events, runner

## Goal / clarifications
- User picked: Pong, rain, wave text, and a collision animation with example events (H→γγ, Z→μμ);
  explicitly no real CMS Open Data. Later requests: binary (Matrix 0/1) rain; fewer digit flips plus an
  on/off option; a Chrome-dino-style runner; then remove the runner's cloud.

## Changes
- `src/ledbadge/animations.py` (new):
  - `pong()`: one simulated point (serve, N returns, scripted miss, paddles recentre). Paddles predict the
    ball's arrival row including wall bounces; rally auto-sized to fit (each return = 41 frames; default 113).
  - `rain()`: drops on per-column rings moving an integer number of laps per loop (seamless).
  - `binary_rain()`: 3x5 "0"/"1" glyph streams (11 columns) on looping tapes; ~15% of digits flip once each
    way per loop (`flip=False` disables; same seed gives the same pattern either way).
  - `wave_text()`: whole letters bob on a moving sine wave; text wider than 44 px scrolls.
  - `runner()`: 6x6 dino, three cactus shapes, scrolling ground with gaps; world is a ring of `frames` px;
    jumps planned per cactus so the dino clears it (`_plan_jump`). Cloud removed at the user's request.
- `src/ledbadge/collider.py` (new): beams → flash → tracks grow (arcs with charge-signed curvature; muons
  long/straight; photons dotted ending in 2x2 calorimeter blocks; jets as sprays) → hold → pile-up blinks
  to highlight the signal → label. Events: hgg, zmumu, h4mu, dijet; seeded.
- `font.py`: added γ, μ, → glyphs for the labels.
- CLI: `pong`, `runner`, `rain [--binary --no-flip]`, `wave`, `collide`; shared `_animate()` with a clear
  error above 123 frames; `main()` turns ValueError into a clean exit message.
- GUI: server endpoints `generate/{pong,runner,rain,wave,collide}` returning frames + default speed; new
  generator tabs/forms; JS `generate()` generalised.
- Tests: `tests/test_animations.py` (new) + server endpoint tests; 53 tests total.
- README and `.claude/CLAUDE.md` updated.

## Verification
- `uv run pytest`: 53 passed (seamless loops for rain/binary rain/runner, pong rally lengths and loop
  state, wave letter integrity, collider labels/determinism/limits, runner never touches a cactus over 8
  seeds, server endpoints incl. the too-long collide error).
- Visual: contact sheets (scratchpad PNGs) reviewed for every effect; fixes made from them — Pong paddles
  missing (now predictive), wave text shearing letters (now per-letter), dense pile-up/jets thinned, dino
  sprite redrawn.
- Headless Chrome harness: all new GUI tabs generate correctly; too-long/no-event collide errors shown.
- Hardware (user confirmed): rain + wave + H→γγ combo looked good; Pong uploaded; binary rain uploaded,
  user noticed flips → made rarer + switchable; runner uploaded (with and without cloud).
- Not confirmed by the user: final Pong verdict, the rarer-flip binary rain, the cloudless runner.

## Notes / open
- Pong (7.5 KB) and runner (8 KB) each fill the badge on their own; shorter loops (`-n`) leave room.
- Bugs hit during development: an infinite loop in Pong's arrival prediction once the ball passed the
  paddle (fixed with a direction-aware loop condition).
