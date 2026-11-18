"""Command-line interface: ``badge <command> ...``."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta

from PIL import Image

from . import animations, collider, device, effects
from .design import Design, DesignMessage, DesignStore, combine
from .font import render_text
from .protocol import (ANIM_OFFSET, FRAME_WIDTH, MAX_MESSAGES, WIDTH, Message, Mode,
                       build_payload, max_animation_frames)
from .render import (animation_strip, ascii_preview, fit_frame, gif_frames, image_to_bitmap,
                     upscale_preview)

MODE_NAMES = {m.name.lower(): m for m in Mode}


def _mode(value: str) -> Mode:
    if value.isdigit():
        return Mode(int(value))
    try:
        return MODE_NAMES[value.lower()]
    except KeyError:
        raise argparse.ArgumentTypeError(f"unknown mode {value!r}; choose from {', '.join(MODE_NAMES)}")


def _common(p: argparse.ArgumentParser, mode: bool = True) -> None:
    """Options shared by every command that uploads something."""
    if mode:
        p.add_argument("-m", "--mode", type=_mode, default=None,
                       help=f"display mode: {', '.join(MODE_NAMES)} (or 0-8)")
    p.add_argument("-s", "--speed", type=int, default=None, choices=range(1, 9), metavar="1-8")
    p.add_argument("-b", "--blink", action="store_true", help="blink the message")
    p.add_argument("-a", "--marquee", action="store_true", help="animated border")
    p.add_argument("-B", "--brightness", type=int, default=100, choices=(25, 50, 75, 100))
    p.add_argument("-p", "--preview", action="store_true",
                   help="print an ASCII preview and do not upload")
    p.add_argument("--png", metavar="FILE", help="also save an LED-style preview PNG")
    p.add_argument("--save", metavar="NAME",
                   help="save the result as a design (combine with -p to save without uploading)")
    p.add_argument("-t", "--transport", choices=("auto", "usb", "ble"), default="auto",
                   help="auto = USB if plugged in, else Bluetooth (default)")
    p.add_argument("--frame-offset", type=int, default=ANIM_OFFSET,
                   help=f"visible window start inside 48-px animation frames (default {ANIM_OFFSET})")


def _upload(args: argparse.Namespace, messages: list[Message], quiet: bool = False) -> None:
    """Preview and/or send messages according to the common options."""
    if args.preview or args.png:
        for i, m in enumerate(messages):
            if args.preview:
                n_frames = m.bitmap.width // FRAME_WIDTH if m.mode == Mode.ANIMATION else 0
                print(f"[message {i}] mode={m.mode.name.lower()} speed={m.speed} "
                      f"size={m.bitmap.width}x{m.bitmap.height}"
                      + (f" frames={n_frames}" if n_frames else ""))
                if m.mode == Mode.ANIMATION:  # show first frames stacked, not one long strip
                    show_frames = [m.bitmap.crop((k * FRAME_WIDTH, 0, (k + 1) * FRAME_WIDTH, 11))
                                   for k in range(min(n_frames, 4))]
                    print("\n\n".join(ascii_preview(f) for f in show_frames))
                    if n_frames > 4:
                        print(f"... ({n_frames - 4} more frames)")
                else:
                    print(ascii_preview(m.bitmap))
        if args.png:
            strip = messages[0].bitmap
            upscale_preview(strip).save(args.png)
            print(f"saved preview of message 0 to {args.png}")
    if getattr(args, "save", None):
        design = Design(args.save, [DesignMessage.from_message(m, frame_offset=args.frame_offset)
                                    for m in messages], args.brightness)
        path = DesignStore(args.designs_dir).save(design)
        print(f"saved design to {path}")
    if args.preview:
        return
    _send(args, build_payload(messages, brightness=args.brightness), len(messages), quiet)


def _send(args: argparse.Namespace, payload: bytes, n_messages: int, quiet: bool = False) -> None:
    """Send a payload over the transport chosen by ``args.transport``."""
    transport = args.transport
    if transport == "auto":
        transport = "usb" if device.list_devices() else "ble"
    try:
        if transport == "usb":
            dt = device.send(payload)
        else:
            from . import ble  # imported lazily: bleak is slow to import
            if not quiet:
                print("connecting over Bluetooth (press the badge button if it isn't advertising)...")
            dt = ble.send(payload)
    except (device.BadgeNotFound, RuntimeError) as e:
        sys.exit(str(e))
    if not quiet:
        print(f"uploaded {n_messages} message(s), {len(payload)} bytes via {transport} in {dt:.2f} s")


def _msg(args: argparse.Namespace, bitmap: Image.Image, mode: Mode, speed: int) -> Message:
    return Message(bitmap=bitmap, mode=args.mode if args.mode is not None else mode,
                   speed=args.speed or speed, blink=args.blink, marquee=args.marquee)


# --- commands -------------------------------------------------------------------
def cmd_list(args: argparse.Namespace) -> None:
    devs = device.list_devices()
    if not devs:
        print("no badge found (USB 0416:5020)")
    for d in devs:
        print(f"{d['manufacturer_string']} {d['product_string']}  path={d['path'].decode()}")


def cmd_designs(args: argparse.Namespace) -> None:
    store = DesignStore(args.designs_dir)
    names = store.names()
    if not names:
        print(f"no designs in {store.folder}/")
    for name in names:
        try:
            d = store.load(name)
            info = ", ".join(f"{m.mode.name.lower()}x{len(m.frames)}" for m in d.messages)
            print(f"{name:24s} {len(d.payload()):5d} B  [{info}]")
        except (ValueError, KeyError) as e:
            print(f"{name:24s} INVALID: {e}")


def cmd_show(args: argparse.Namespace) -> None:
    store = DesignStore(args.designs_dir)
    try:
        designs = [store.load(n) for n in args.names]
        design = designs[0] if len(designs) == 1 else combine(designs, args.save or "combined")
    except (FileNotFoundError, ValueError) as e:
        sys.exit(str(e))
    if args.brightness is not None:
        design.brightness = args.brightness
    if args.save:
        design.name = args.save
        print(f"saved design to {store.save(design)}")
    if args.preview:
        args.save = None
        args.png = None
        _upload(args, design.to_messages(args.frame_offset))
        return
    _send(args, design.payload(args.frame_offset), len(design.messages))


def cmd_gui(args: argparse.Namespace) -> None:
    from .gui.server import serve
    serve(args.designs_dir, host=args.host, port=args.port, open_browser=not args.no_browser)


def cmd_scan(args: argparse.Namespace) -> None:
    import asyncio
    from . import ble
    found = asyncio.run(ble.scan(args.timeout))
    if not found:
        print("no BLE badge advertising (press the badge button to enable Bluetooth)")
    for dev, rssi in found:
        print(f"{dev.name}  address={dev.address}  rssi={rssi}")


def cmd_text(args: argparse.Namespace) -> None:
    if len(args.message) > MAX_MESSAGES:
        sys.exit(f"at most {MAX_MESSAGES} messages")
    msgs = []
    for text in args.message:
        mode = args.mode if args.mode is not None else Mode.LEFT
        min_w = WIDTH if mode in (Mode.FIXED, Mode.SNOWFLAKE, Mode.PICTURE, Mode.LASER) else 0
        msgs.append(_msg(args, render_text(text, font=args.font, min_width=min_w), mode, 5))
    _upload(args, msgs)


def cmd_image(args: argparse.Namespace) -> None:
    img = Image.open(args.path)
    n = getattr(img, "n_frames", 1)
    if n > 1 and not args.still:
        frames = gif_frames(img, dither=not args.no_dither, invert=args.invert,
                            max_frames=min(max_animation_frames(), args.max_frames))
        bitmap = animation_strip(frames, args.frame_offset)
        msg = _msg(args, bitmap, Mode.ANIMATION, 4)
    else:
        bitmap = image_to_bitmap(img, width=args.width, dither=not args.no_dither,
                                 invert=args.invert, threshold=args.threshold)
        default = Mode.FIXED if bitmap.width <= WIDTH else Mode.LEFT
        if default == Mode.FIXED:
            bitmap = fit_frame(bitmap)
        msg = _msg(args, bitmap, default, 4)
    _upload(args, [msg])


def cmd_life(args: argparse.Namespace) -> None:
    n = min(args.frames, max_animation_frames())
    frames, seed = effects.game_of_life(n, seed=args.seed, density=args.density,
                                        wrap=not args.no_wrap)
    print(f"seed={seed}: {len(frames)} generations (max {n})")
    if not frames:
        sys.exit("soup died immediately; try another seed/density")
    _upload(args, [_msg(args, animation_strip(frames, args.frame_offset), Mode.ANIMATION, 6)])


def _animate(args: argparse.Namespace, frames: list[Image.Image], speed: int) -> None:
    """Upload generated frames as one animation-mode message."""
    limit = max_animation_frames()
    if len(frames) > limit:
        sys.exit(f"{len(frames)} frames, but one upload holds at most {limit}")
    print(f"{len(frames)} frames")
    _upload(args, [_msg(args, animation_strip(frames, args.frame_offset), Mode.ANIMATION, speed)])


def cmd_pong(args: argparse.Namespace) -> None:
    frames, seed = animations.pong(seed=args.seed, rally=args.rally, net=not args.no_net)
    print(f"seed={seed}")
    _animate(args, frames, 8)


def cmd_rain(args: argparse.Namespace) -> None:
    if args.binary:
        frames, seed = animations.binary_rain(args.frames, density=args.density, seed=args.seed,
                                              flip=not args.no_flip)
    else:
        frames, seed = animations.rain(args.frames, density=args.density, tail=args.tail, seed=args.seed)
    print(f"seed={seed}")
    _animate(args, frames, 7)


def cmd_runner(args: argparse.Namespace) -> None:
    frames, seed = animations.runner(args.frames, seed=args.seed)
    print(f"seed={seed}")
    _animate(args, frames, 8)


def cmd_wave(args: argparse.Namespace) -> None:
    _animate(args, animations.wave_text(args.text, amplitude=args.amplitude,
                                        wavelength=args.wavelength, frames=args.frames), 7)


def cmd_collide(args: argparse.Namespace) -> None:
    frames, seed = collider.collision(args.events or None, seed=args.seed, label=not args.no_label)
    print(f"seed={seed}")
    _animate(args, frames, 7)


def cmd_clock(args: argparse.Namespace) -> None:
    def build(now: datetime) -> list[Message]:
        frames = effects.clock_frames(now, fmt=args.format, seconds_bar=args.seconds_bar,
                                      start_second=now.second if args.seconds_bar else 0)
        # speed 3 ~ 2 fps -> 2-frame colon blink at ~1 Hz (see protocol notes)
        return [_msg(args, animation_strip(frames, args.frame_offset), Mode.ANIMATION, 3)]

    if not args.live:
        _upload(args, build(datetime.now()))
        return
    print("live clock: re-uploading every minute, Ctrl-C to stop")
    try:
        while True:
            now = datetime.now()
            _upload(args, build(now), quiet=True)
            print(f"{now:%H:%M:%S} updated")
            if args.preview:
                return
            nxt = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
            time.sleep(max(0.0, (nxt - datetime.now()).total_seconds()))
    except KeyboardInterrupt:
        print()


def cmd_test(args: argparse.Namespace) -> None:
    if args.pattern == "border":
        msgs = [_msg(args, effects.test_border(), Mode.FIXED, 4)]
    elif args.pattern == "frame":
        # raw 48-px frame, no offset handling: shows which columns are visible
        msgs = [_msg(args, effects.test_frame_ruler(), Mode.ANIMATION, 1)]
    else:  # modes: one slot per mode so you can watch the badge cycle through them
        names = ["left", "right", "up", "down", "fixed", "snow", "pict", "laser"]
        modes = [Mode.LEFT, Mode.RIGHT, Mode.UP, Mode.DOWN, Mode.FIXED,
                 Mode.SNOWFLAKE, Mode.PICTURE, Mode.LASER]
        msgs = [Message(render_text(f"{i}:{n}", min_width=WIDTH), m, args.speed or 5)
                for i, (n, m) in enumerate(zip(names, modes))]
    _upload(args, msgs)


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``badge`` command."""
    ap = argparse.ArgumentParser(prog="badge", description="Control a Badge Magic LED badge over USB or BLE.")
    ap.add_argument("--designs-dir", default="designs", help="folder of saved designs (default ./designs)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="list badges attached over USB").set_defaults(func=cmd_list)

    p = sub.add_parser("scan", help="scan for badges advertising over Bluetooth")
    p.add_argument("--timeout", type=float, default=5.0)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("text", help="upload up to 8 text messages")
    p.add_argument("message", nargs="+")
    p.add_argument("-f", "--font", choices=("small", "big"), default="small")
    _common(p)
    p.set_defaults(func=cmd_text)

    p = sub.add_parser("image", help="upload an image (animated GIFs become animations)")
    p.add_argument("path")
    p.add_argument("-w", "--width", type=int, help="target width in px (default: keep aspect)")
    p.add_argument("--no-dither", action="store_true", help="threshold instead of dithering")
    p.add_argument("--threshold", type=int, default=128)
    p.add_argument("--invert", action="store_true")
    p.add_argument("--still", action="store_true", help="use only the first frame of a GIF")
    p.add_argument("--max-frames", type=int, default=999)
    _common(p)
    p.set_defaults(func=cmd_image)

    p = sub.add_parser("life", help="Conway's Game of Life as an on-badge animation")
    p.add_argument("-n", "--frames", type=int, default=999, help="max generations (capped by memory)")
    p.add_argument("--seed", type=int)
    p.add_argument("--density", type=float, default=0.35)
    p.add_argument("--no-wrap", action="store_true", help="dead edges instead of a torus")
    _common(p, mode=False)
    p.set_defaults(func=cmd_life, mode=None)

    p = sub.add_parser("pong", help="self-playing Pong (one point, loops)")
    p.add_argument("--seed", type=int)
    p.add_argument("--rally", type=int, help="returns before the miss (default: as many as fit)")
    p.add_argument("--no-net", action="store_true")
    _common(p, mode=False)
    p.set_defaults(func=cmd_pong, mode=None)

    p = sub.add_parser("rain", help="digital rain (seamless loop)")
    p.add_argument("-n", "--frames", type=int, default=60, help="loop length in frames")
    p.add_argument("--density", type=float, default=0.7, help="fraction of columns with a drop/stream")
    p.add_argument("--tail", type=int, default=3, help="max tail length (drops only)")
    p.add_argument("--binary", action="store_true", help="Matrix-style falling 0s and 1s instead of drops")
    p.add_argument("--no-flip", action="store_true", help="binary: digits never change between 0 and 1")
    p.add_argument("--seed", type=int)
    _common(p, mode=False)
    p.set_defaults(func=cmd_rain, mode=None)

    p = sub.add_parser("runner", help="endless runner: a dino jumps over scrolling cacti")
    p.add_argument("-n", "--frames", type=int, default=120, help="loop length (multiple of 4, max 120)")
    p.add_argument("--seed", type=int)
    _common(p, mode=False)
    p.set_defaults(func=cmd_runner, mode=None)

    p = sub.add_parser("wave", help="text bobbing on a sine wave (scrolls if wider than the badge)")
    p.add_argument("text")
    p.add_argument("--amplitude", type=float, default=2.0, help="rows up/down")
    p.add_argument("--wavelength", type=float, default=24.0, help="px per wave")
    p.add_argument("-n", "--frames", type=int, help="frames per wave cycle for text that fits (default 20)")
    _common(p, mode=False)
    p.set_defaults(func=cmd_wave, mode=None)

    p = sub.add_parser("collide", help="collider event display (beams, tracks, highlighted signal, label)")
    p.add_argument("events", nargs="*", choices=list(collider.EVENTS),
                   help="events in order (default: hgg zmumu); ~45-60 frames each")
    p.add_argument("--seed", type=int)
    p.add_argument("--no-label", action="store_true", help="skip the H→γγ-style label")
    _common(p, mode=False)
    p.set_defaults(func=cmd_collide, mode=None)

    p = sub.add_parser("clock", help="show the time (big digits, blinking colon)")
    p.add_argument("--live", action="store_true", help="keep running and update every minute")
    p.add_argument("--format", default="%H:%M", help="strftime format (digits, ':', '-' only)")
    p.add_argument("--seconds-bar", type=int, default=0, metavar="N",
                   help="experimental: N frames/minute with a seconds bar (e.g. 120 at speed 3)")
    _common(p, mode=False)
    p.set_defaults(func=cmd_clock, mode=None)

    sub.add_parser("designs", help="list saved designs").set_defaults(func=cmd_designs)

    p = sub.add_parser("show", help="upload saved design(s); several are combined and cycled on the badge")
    p.add_argument("names", nargs="+", metavar="NAME")
    p.add_argument("--save", metavar="NAME", help="also save the (combined) result as a design")
    p.add_argument("-B", "--brightness", type=int, choices=(25, 50, 75, 100),
                   help="override the design's brightness")
    p.add_argument("-p", "--preview", action="store_true", help="print the design instead of uploading")
    p.add_argument("-t", "--transport", choices=("auto", "usb", "ble"), default="auto")
    p.add_argument("--frame-offset", type=int, default=ANIM_OFFSET)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("gui", help="open the design editor in your browser")
    p.add_argument("--port", type=int, default=8044)
    p.add_argument("--host", default="127.0.0.1", help="bind address (default: this machine only)")
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("test", help="hardware test patterns")
    p.add_argument("pattern", choices=("border", "frame", "modes"))
    _common(p, mode=False)
    p.set_defaults(func=cmd_test, mode=None)

    args = ap.parse_args(argv)
    try:
        args.func(args)
    except ValueError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
