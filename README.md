# ledbadge

Desktop control for Badge Magic LED name badges (11x44) over USB or Bluetooth LE.

```sh
uv sync
uv run badge list                         # find the badge on USB
uv run badge scan                         # ...or over Bluetooth (badge must be in BLE mode)
uv run badge text "Hello" "World" -m fixed
uv run badge image cat.png                # still image (dithered), or animated GIF -> animation
uv run badge life                         # Game of Life, pre-computed and played on the badge
uv run badge clock --live                 # big-digit clock, re-uploaded every minute
uv run badge test border|frame|modes      # hardware test patterns

uv run badge gui                          # Badge Studio editor in your browser (http://localhost:8044)
uv run badge life --save mylife -p        # save any generated content as a design (no upload with -p)
uv run badge designs                      # list saved designs
uv run badge show mylife                  # upload a saved design
uv run badge show a b c                   # combine designs into one upload; the badge cycles through them
```

## Badge Studio (GUI)

`badge gui` serves a local editor (bound to 127.0.0.1 only, no extra dependencies):
pixel editor with onion skin and undo, frame strip, up to 8 messages with mode/speed/blink/border,
an LED-style preview (approximate timing), generators (text, image/GIF, Game of Life, clock),
a design library and an Upload button (USB or Bluetooth) with an 8 KB size meter.
Open a design directly with `http://localhost:8044/?design=NAME`.

Designs are JSON files in `designs/` (frames stored as `.`/`#` rows, so they are readable and diffable).
In animation mode each frame is one 44x11 screen; in other modes frames are joined left-to-right.

Add `-p` to any command to preview in the terminal without uploading, `--png out.png` for an LED-style image.
Common options: `-m/--mode` (left, right, up, down, fixed, animation, snowflake, picture, laser),
`-s/--speed 1-8`, `-b` blink, `-a` marquee border, `-B` brightness 25/50/75/100.

`-t usb|ble|auto` picks the transport (auto = USB when plugged in, otherwise Bluetooth).

Notes:
- Stock firmware (CH583 badge): **nothing is displayed while plugged in** (charging screen); the
  uploaded content appears after unplugging. USB uploads take ~0.05 s.
- Bluetooth: the badge accepts **one upload per button press** (it disconnects and stops advertising
  after receiving the data), and it is slow: ~65 B/s, i.e. ~2 min for a full 8 KB animation.
  Fastest workflow for big content: plug in, upload over USB, unplug.
- The badge holds up to 8 messages and ~8 KB of bitmap data (~123 animation frames). It cycles through the
  messages; pressing the badge button selects a single message to loop.
- Animation mode plays 48-px-wide frames, of which 44 columns are visible (`badge test frame` checks the offset).
