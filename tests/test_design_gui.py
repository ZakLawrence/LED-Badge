"""Design storage and GUI server API tests (no badge needed; uploads are not exercised)."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from ledbadge.design import Design, DesignMessage, DesignStore, combine, image_to_rows, rows_to_image
from ledbadge.effects import game_of_life
from ledbadge.font import render_text
from ledbadge.gui.server import make_handler
from ledbadge.protocol import Message, Mode, pack_bitmap
from ledbadge.render import animation_strip


def test_rows_roundtrip():
    img = render_text("Hi!", min_width=44)
    assert rows_to_image(image_to_rows(img)).tobytes() == img.tobytes()


def test_design_save_load_and_payload_identical(tmp_path):
    frames, _ = game_of_life(10, seed=3)
    text = render_text("Hello", min_width=44)
    msgs = [Message(animation_strip(frames), Mode.ANIMATION, 6),
            Message(text, Mode.FIXED, 3, blink=True)]
    design = Design("demo", [DesignMessage.from_message(m) for m in msgs], brightness=50)
    store = DesignStore(tmp_path)
    store.save(design)
    loaded = store.load("demo")
    assert store.names() == ["demo"]
    assert loaded.to_json() == design.to_json()
    # the round-tripped design must upload exactly the same bitmaps
    for orig, new in zip(msgs, loaded.to_messages()):
        assert pack_bitmap(orig.bitmap) == pack_bitmap(new.bitmap)
        assert (orig.mode, orig.speed, orig.blink) == (new.mode, new.speed, new.blink)


def test_non_animation_frames_are_joined():
    a, b = image_to_rows(render_text("AB")), image_to_rows(render_text("CD"))
    m = DesignMessage([a, b], Mode.LEFT)
    assert m.bitmap().width == len(a[0]) + len(b[0])


@pytest.mark.parametrize("bad", ["../evil", "", "a/b", ".hidden", "x" * 65])
def test_bad_names_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        DesignStore(tmp_path).path(bad)


def test_invalid_design_rejected():
    with pytest.raises(ValueError):
        Design.from_json({"name": "x", "messages": [{"frames": [["#"] * 10]}]})  # 10 rows
    with pytest.raises(ValueError):
        Design.from_json({"name": "x", "messages": []})


@pytest.fixture
def server(tmp_path):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(DesignStore(tmp_path)))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def call(base, method, path, body=None):
    req = urllib.request.Request(base + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_server_static_and_generators(server):
    with urllib.request.urlopen(server + "/") as r:
        assert b"Badge Studio" in r.read()
    status, _ = call(server, "GET", "/../pyproject.toml")
    assert status == 404
    s, r = call(server, "POST", "/api/generate/text", {"text": "Hi", "width": 44})
    assert s == 200 and len(r["frames"][0]) == 11 and len(r["frames"][0][0]) == 44
    s, r = call(server, "POST", "/api/generate/life", {"frames": 20, "seed": 5})
    assert s == 200 and 0 < len(r["frames"]) <= 20 and r["seed"] == 5
    s, r = call(server, "POST", "/api/generate/clock", {})
    assert s == 200 and len(r["frames"]) == 2


def test_server_design_crud(server):
    d = {"name": "ignored", "brightness": 75,
         "messages": [{"mode": "fixed", "speed": 2, "frames": [["." * 44] * 11]}]}
    s, r = call(server, "PUT", "/api/designs/my%20design", d)
    assert s == 200, r
    s, r = call(server, "GET", "/api/designs")
    assert r["designs"] == ["my design"]
    s, r = call(server, "GET", "/api/designs/my%20design")
    assert r["brightness"] == 75 and r["name"] == "my design"
    s, r = call(server, "POST", "/api/payload", d)
    assert r["bytes"] == 192
    s, r = call(server, "PUT", "/api/designs/..%2Fescape", d)
    assert s == 400
    s, _ = call(server, "DELETE", "/api/designs/my%20design")
    assert call(server, "GET", "/api/designs")[1]["designs"] == []


def test_combine_designs(tmp_path):
    one = lambda name, mode: Design(name, [DesignMessage([image_to_rows(render_text(name, min_width=44))], mode)])
    a, b = one("A", Mode.FIXED), one("B", Mode.LEFT)
    c = combine([a, b], "ab")
    assert [m.mode for m in c.messages] == [Mode.FIXED, Mode.LEFT]
    assert len(c.payload()) == 64 + 2 * 66 + 60  # 196 -> padded to 256
    with pytest.raises(ValueError, match="at most 8"):
        combine([a] * 9)
    big_frames, _ = game_of_life(100, seed=1)
    big = Design("big", [DesignMessage.from_message(Message(animation_strip(big_frames), Mode.ANIMATION))])
    with pytest.raises(ValueError, match="big"):
        combine([big, big])
