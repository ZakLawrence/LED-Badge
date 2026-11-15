"""Local web GUI: a stdlib HTTP server exposing a small JSON API + the static editor.

API (all JSON):
    GET    /api/designs                 -> {"designs": [names]}
    GET    /api/designs/<name>          -> design JSON
    PUT    /api/designs/<name>          <- design JSON          -> {"saved": path}
    DELETE /api/designs/<name>          -> {"deleted": name}
    GET    /api/status                  -> {"usb": bool}
    POST   /api/ble/scan                -> {"badges": [{name, address, rssi}]}
    POST   /api/payload                 <- design JSON          -> {"bytes": n, "max": 8192}
    POST   /api/upload                  <- {"design", "transport"} -> {"transport", "bytes", "seconds"}
    POST   /api/generate/text           <- {"text", "font", "width"}       -> {"frames": [...]}
    POST   /api/generate/life           <- {"frames", "seed", "density", "wrap"} -> {"frames", "seed"}
    POST   /api/generate/clock          <- {"format", "seconds_bar"}       -> {"frames"}
    POST   /api/generate/image          <- {"data" (data URL), "width", "dither", "invert", "threshold",
                                            "max_frames"} -> {"frames", "animated"}
"""

from __future__ import annotations

import base64
import io
import json
import threading
import traceback
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import unquote

from PIL import Image

from .. import device, effects
from ..design import Design, DesignStore, image_to_rows
from ..font import render_text
from ..protocol import MAX_PAYLOAD, WIDTH, max_animation_frames
from ..render import fit_frame, gif_frames, image_to_bitmap

STATIC = resources.files("ledbadge.gui") / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
_upload_lock = threading.Lock()


class ApiError(Exception):
    """An error reported to the browser with an HTTP status."""

    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


def _send_payload(payload: bytes, transport: str) -> tuple[str, float]:
    """Upload over USB or BLE (serialised: one upload at a time)."""
    if not _upload_lock.acquire(blocking=False):
        raise ApiError("an upload is already in progress", HTTPStatus.CONFLICT)
    try:
        if transport == "auto":
            transport = "usb" if device.list_devices() else "ble"
        if transport == "usb":
            return transport, device.send(payload)
        from .. import ble
        return transport, ble.send(payload)
    except (device.BadgeNotFound, RuntimeError) as e:
        raise ApiError(str(e), HTTPStatus.SERVICE_UNAVAILABLE) from e
    finally:
        _upload_lock.release()


def make_handler(store: DesignStore) -> type[BaseHTTPRequestHandler]:
    """Build a request handler class bound to a design store."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "ledbadge-gui"

        # --- plumbing ---------------------------------------------------------
        def log_message(self, fmt: str, *args) -> None:  # quieter console
            if not self.path.startswith("/api/status"):
                super().log_message(fmt, *args)

        def _json(self, obj: object, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 20_000_000:
                raise ApiError("request too large")
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError as e:
                raise ApiError(f"bad JSON: {e}") from e

        def _dispatch(self, method: str) -> None:
            try:
                if self.path.startswith("/api/"):
                    self._api(method, unquote(self.path[5:].split("?")[0]))
                elif method == "GET":
                    self._static()
                else:
                    raise ApiError("not found", HTTPStatus.NOT_FOUND)
            except ApiError as e:
                self._json({"error": str(e)}, e.status)
            except (ValueError, KeyError, TypeError, OSError) as e:
                self._json({"error": f"{type(e).__name__}: {e}"}, HTTPStatus.BAD_REQUEST)
            except Exception as e:  # keep the server alive, report to the page
                traceback.print_exc()
                self._json({"error": f"internal error: {e}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_PUT(self) -> None:
            self._dispatch("PUT")

        def do_DELETE(self) -> None:
            self._dispatch("DELETE")

        def _static(self) -> None:
            name = self.path.split("?")[0].lstrip("/") or "index.html"
            if "/" in name or name.startswith("."):
                raise ApiError("not found", HTTPStatus.NOT_FOUND)
            f = STATIC / name
            if not f.is_file():
                raise ApiError("not found", HTTPStatus.NOT_FOUND)
            body = f.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", CONTENT_TYPES.get("." + name.rsplit(".", 1)[-1],
                                                               "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        # --- API --------------------------------------------------------------
        def _api(self, method: str, route: str) -> None:
            parts = route.split("/", 1)
            head, arg = parts[0], (parts[1] if len(parts) > 1 else "")

            if head == "designs":
                if method == "GET" and not arg:
                    return self._json({"designs": store.names(), "folder": str(store.folder.resolve())})
                if method == "GET":
                    try:
                        return self._json(store.load(arg).to_json())
                    except FileNotFoundError as e:
                        raise ApiError(str(e), HTTPStatus.NOT_FOUND) from e
                if method == "PUT":
                    data = self._body()
                    data["name"] = arg
                    return self._json({"saved": str(store.save(Design.from_json(data)))})
                if method == "DELETE":
                    store.delete(arg)
                    return self._json({"deleted": arg})

            if route == "status" and method == "GET":
                return self._json({"usb": bool(device.list_devices())})

            if method != "POST":
                raise ApiError("not found", HTTPStatus.NOT_FOUND)
            body = self._body()

            if route == "ble/scan":
                import asyncio
                from .. import ble
                found = asyncio.run(ble.scan(float(body.get("timeout", 4))))
                return self._json({"badges": [{"name": d.name, "address": d.address, "rssi": r}
                                              for d, r in found]})

            if route == "payload":
                body.setdefault("name", "untitled")
                n = len(Design.from_json(body).payload())
                return self._json({"bytes": n, "max": MAX_PAYLOAD})

            if route == "upload":
                design_json = body["design"]
                design_json.setdefault("name", "untitled")
                payload = Design.from_json(design_json).payload()
                transport, dt = _send_payload(payload, body.get("transport", "auto"))
                return self._json({"transport": transport, "bytes": len(payload), "seconds": dt})

            if route == "generate/text":
                img = render_text(str(body.get("text", "")), font=body.get("font", "small"),
                                  min_width=int(body.get("width", 0)))
                return self._json({"frames": [image_to_rows(img)]})

            if route == "generate/life":
                n = min(int(body.get("frames", 60)), max_animation_frames())
                seed = body.get("seed")
                frames, used = effects.game_of_life(
                    n, seed=None if seed in (None, "") else int(seed),
                    density=float(body.get("density", 0.35)), wrap=bool(body.get("wrap", True)))
                return self._json({"frames": [image_to_rows(f) for f in frames], "seed": used})

            if route == "generate/clock":
                frames = effects.clock_frames(fmt=body.get("format", "%H:%M"),
                                              seconds_bar=int(body.get("seconds_bar", 0)))
                return self._json({"frames": [image_to_rows(f) for f in frames]})

            if route == "generate/image":
                data = body["data"]
                raw = base64.b64decode(data.split(",", 1)[1] if "," in data else data)
                img = Image.open(io.BytesIO(raw))
                dither = bool(body.get("dither", True))
                invert = bool(body.get("invert", False))
                if getattr(img, "n_frames", 1) > 1:
                    max_frames = min(int(body.get("max_frames", 60)), max_animation_frames())
                    frames = gif_frames(img, dither=dither, invert=invert, max_frames=max_frames)
                    return self._json({"frames": [image_to_rows(f) for f in frames], "animated": True})
                width = body.get("width")
                bmp = image_to_bitmap(img, width=int(width) if width else None, dither=dither,
                                      invert=invert, threshold=int(body.get("threshold", 128)))
                if bmp.width < WIDTH:
                    bmp = fit_frame(bmp)
                return self._json({"frames": [image_to_rows(bmp)], "animated": False})

            raise ApiError("not found", HTTPStatus.NOT_FOUND)

    return Handler


def serve(designs_dir: str = "designs", host: str = "127.0.0.1", port: int = 8044,
          open_browser: bool = True) -> None:
    """Run the GUI server until Ctrl-C."""
    store = DesignStore(designs_dir)
    httpd = ThreadingHTTPServer((host, port), make_handler(store))
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"
    print(f"badge GUI on {url}  (designs in {store.folder.resolve()}/)  Ctrl-C to stop")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        httpd.server_close()
