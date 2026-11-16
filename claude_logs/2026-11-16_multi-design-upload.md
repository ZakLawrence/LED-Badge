# 2026-11-16 — Send several designs to the badge at once

## Goal
Uploading a design replaced everything on the badge; the user wanted several designs cycling.
The badge already supports up to 8 messages per upload; the tools only sent one design at a time.

## Changes
- `design.py`: `combine(designs, name, brightness)` concatenates messages; errors on >8 messages or >8 KB
  (error lists each design's size). Brightness is per upload: first design's unless overridden.
- `cli.py`: `badge show NAME [NAME ...]` combines designs in the given order; `--save NAME` stores the result.
- GUI (`app.js`, `style.css`, `index.html`): green "+" next to each saved design appends its messages to the
  open design (`appendDesign`), with undo, 8-message cap and over-size warning; tip added to help.
- `tests/test_design_gui.py::test_combine_designs`; README and `.claude/CLAUDE.md` updated.

## Verification
- `uv run pytest`: 20 passed.
- Headless Chrome harness (scratchpad) on copies of the real designs: 8/8 checks (button present, append via
  button and function, size equals server's, tab count, over-size meter, undo, 8-message cap).
- CLI: preview of the 3-design combination; over-limit error with life (8384 B) as expected.
- Hardware: uploaded CMS Colide + Coffee Time + Hello Claude over USB (1984 B, 0.13 s). User confirmed the badge
  cycles through them, and that the badge button selects one message to loop on repeat.

## Open
- Message order can't be rearranged in the GUI yet (only by deleting/re-adding).
- Time spent per message before cycling wasn't measured.
