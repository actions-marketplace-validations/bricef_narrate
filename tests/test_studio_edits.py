"""The studio's script edits (#62): a block's properties changed, everything else left as it was."""

import pytest

from narrate.script import parse
from narrate.studio.edits import EditError, apply, edit_block

SCRIPT = """---
size: 720p
---

![cover top](photo.jpg)

Narration stays as it is.

---

(video: {file: clip.mp4, sync: loop, volume: 0.5})

(image:
  file: forest.jpg
  size: contain
  position: left)

```render:placeholder top
A product shot
```

(html: scene.html)
"""


def edited(line, text=SCRIPT, **changes):
    change = edit_block(text, line, changes)
    after = apply(text, change)
    before_lines, after_lines = text.split("\n"), after.split("\n")
    return after, change, before_lines, after_lines


def only_line_changed(before, after, line, new):
    """Every other line is byte for byte the same; `line` became `new`."""
    assert after[:line - 1] == before[:line - 1] and after[line:] == before[line:]
    assert after[line - 1] == new


def media(text, line):
    return next(b for scene in parse(text).scenes for b in scene.blocks if getattr(b, "line", None) == line)


def test_tokens_change_in_place():
    after, _, before, lines = edited(5, position="bottom")
    only_line_changed(before, lines, 5, "![cover bottom](photo.jpg)")
    after, _, before, lines = edited(5, motion="zoom")
    only_line_changed(before, lines, 5, "![zoom top](photo.jpg)")  # a motion takes the size's place
    after, _, before, lines = edited(5, fit=None, position=None)
    only_line_changed(before, lines, 5, "![](photo.jpg)")
    m = media(edited(5, fit="contain", position="left")[0], 5)
    assert (m.size, m.position) == ("contain", "left")


def test_a_fit_replaces_a_motion():
    text = SCRIPT.replace("![cover top]", "![panzoom top]")
    assert edited(5, text, fit="contain")[3][4] == "![panzoom top](photo.jpg)"  # the motion still decides
    assert edited(5, text, fit="contain", motion=None)[3][4] == "![contain top](photo.jpg)"


def test_zoom_moves_a_picture_to_the_map_form():
    after, _, before, lines = edited(5, motion="zoom", zoom=1.6)
    only_line_changed(before, lines, 5, "(image: {file: photo.jpg, size: zoom, position: top, zoom: 1.6})")
    m = media(after, 5)
    assert (m.kind, m.size, m.position, m.zoom) == ("image", "zoom", "top", 1.6)


def test_a_one_line_direction_keeps_its_keys_in_order():
    after, _, before, lines = edited(11, sync="freeze", segment="2-7.5")
    only_line_changed(before, lines, 11, "(video: {file: clip.mp4, sync: freeze, volume: 0.5, segment: 2-7.5})")
    assert edited(11, volume=1)[3][10] == "(video: {file: clip.mp4, sync: loop})"  # the default: no key
    assert media(edited(11, volume="mute")[0], 11).volume == 0.0


def test_a_multi_line_direction_stays_multi_line():
    after, change, before, lines = edited(13, position="top-left", motion="pan")
    assert after.split("\n")[12:17] == ["(image:", "  file: forest.jpg", "  size: pan", "  position: top-left)", ""]
    assert after.replace("(image:\n  file: forest.jpg\n  size: pan\n  position: top-left)", "X") == \
        SCRIPT.replace("(image:\n  file: forest.jpg\n  size: contain\n  position: left)", "X")
    m = media(after, 13)
    assert (m.size, m.position) == ("pan", "top-left")


def test_render_blocks_take_tokens():
    after, _, before, lines = edited(18, fit="contain", position=None)
    only_line_changed(before, lines, 18, "```render:placeholder contain")
    with pytest.raises(EditError, match="frontmatter"):
        edit_block(SCRIPT, 18, {"zoom": 2})


def test_a_page_written_as_a_file_gains_a_map():
    after, _, before, lines = edited(22, fit="contain")
    only_line_changed(before, lines, 22, "(html: {file: scene.html, size: contain})")
    assert edited(22, fit=None)[3][21] == "(html: scene.html)"  # nothing to add: unchanged


def test_names_with_spaces_are_quoted():
    text = "![](my photo.jpg)\n".replace("my photo.jpg", "<my photo.jpg>")
    after = edited(1, text, zoom=2, motion="zoom")[0]
    assert after == '(image: {file: "my photo.jpg", size: zoom, zoom: 2})\n'
    assert media(after, 1).path == "my photo.jpg"


@pytest.mark.parametrize("line, changes, message", [
    (7, {"fit": "cover"}, "isn't a picture"),
    (99, {"fit": "cover"}, "no line 99"),
    (5, {"fit": "stretch"}, "fit must be one of"),
    (5, {"zoom": 0.5}, "above 1"),
    (5, {"segment": "soon"}, "start-end"),
    (5, {"colour": "red"}, "unknown properties"),
])
def test_bad_edits_are_refused(line, changes, message):
    with pytest.raises(EditError, match=message):
        edit_block(SCRIPT, line, changes)


# -- what the inspector is told, and the endpoint ------------------------------------------

def test_the_analysis_describes_each_picture_and_clip(tmp_path):
    from PIL import Image

    from narrate import media as media_tools
    from narrate.studio.analysis import run
    from narrate.tts import SilentSynth

    Image.new("RGB", (640, 360), "red").save(tmp_path / "photo.jpg")
    media_tools.run(["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30", "-t", "3", "-pix_fmt", "yuv420p",
                     str(tmp_path / "clip.mp4")])
    text = ("---\nsize: 320x180\n---\n\n(image: {file: photo.jpg, size: zoom, position: left, zoom: 2})\n\nWords.\n\n"
            "---\n\n![loop mute 1-2](clip.mp4)\n\nMore words.\n")
    report = run(text, tmp_path / "s.md", SilentSynth()).report
    picture, clip = report["media"]["5"], report["media"]["11"]
    assert (picture["kind"], picture["file"], picture["size"]) == ("picture", "photo.jpg", (640, 360))
    assert picture["options"] == {"fit": None, "motion": "zoom", "position": "left", "zoom": 2.0, "sync": None,
                                  "segment": None, "volume": None, "from": None, "to": None}
    first, last = picture["windows"]
    assert first == [0, 0, 640, 360] and last[2] == pytest.approx(320) and last[0] == 0  # zoomed in twice, at the left
    assert (clip["kind"], clip["size"], clip["length"]) == ("clip", [320, 240], pytest.approx(3.0, abs=0.05))
    assert clip["options"]["sync"] == "loop" and clip["options"]["segment"] == "1-2" and clip["options"]["volume"] == "mute"
    assert report["defaults"] == {"fit": "cover", "zoom": None}


def test_the_edit_endpoint(tmp_path):
    from starlette.testclient import TestClient

    from narrate.studio.server import create_app

    (tmp_path / "s.md").write_text(SCRIPT)
    with TestClient(create_app(tmp_path / "s.md", "silent")) as client:
        change = client.post("/api/edit", json={"text": SCRIPT, "line": 5, "set": {"position": "bottom"}}).json()
        assert apply(SCRIPT, change).split("\n")[4] == "![cover bottom](photo.jpg)"
        refused = client.post("/api/edit", json={"text": SCRIPT, "line": 7, "set": {"fit": "cover"}})
        assert refused.status_code == 400 and "isn't a picture" in refused.json()["error"]


# -- free framing (#63) ----------------------------------------------------------------------

def test_focal_points_and_windows_move_a_picture_to_the_map_form():
    after, _, before, lines = edited(5, position="70% 25%")
    only_line_changed(before, lines, 5, "(image: {file: photo.jpg, size: cover, position: 70% 25%})")
    assert media(after, 5).focus == (0.7, 0.25)
    after = edited(13, **{"from": "20% 50%", "to": "80% 40% 2", "fit": None})[0]
    assert "  from: 20% 50%\n  to: 80% 40% 2)" in after
    assert media(after, 13).windows == ((0.2, 0.5, 1.0), (0.8, 0.4, 2.0))
    with pytest.raises(EditError, match="a window such as"):
        edit_block(SCRIPT, 5, {"to": "far away"})
    with pytest.raises(EditError, match="or a point such as"):
        edit_block(SCRIPT, 5, {"position": "150% 2%"})


def test_the_inspector_is_told_the_crop_and_the_focal_point(tmp_path):
    from PIL import Image

    from narrate.studio.analysis import run
    from narrate.tts import SilentSynth

    Image.new("RGB", (4000, 1000), "red").save(tmp_path / "wide.png")
    text = ("---\nsize: 320x180\n---\n\n(image: {file: wide.png, position: 60% 50%})\n\nWords.\n\n"
            "---\n\n(image: {file: wide.png, from: 30% 50%, to: 80% 50% 2})\n\nMore.\n")
    media_entries = run(text, tmp_path / "s.md", SilentSynth()).report["media"]
    still, moving = media_entries["5"], media_entries["11"]
    x, y, w, h = still["crop"]
    assert x + w / 2 == pytest.approx(2400, abs=0.2) and still["focus"] == [0.6, 0.5]
    assert still["options"]["position"] == "60% 50%" and still["windows"] is None
    assert moving["options"]["from"] == "30% 50%" and moving["options"]["to"] == "80% 50% 2"
    first, last = moving["windows"]
    assert first[0] + first[2] / 2 == pytest.approx(1200, abs=0.2) and last[2] == pytest.approx(first[2] / 2, abs=0.2)


# -- callouts (#64) ----------------------------------------------------------------------------

CALLOUTS = """![](photo.jpg)

(callout:
  cx: 640
  cy: 360
  size: 150)

(callout: {type: rectangle, left: 10, top: 20, right: 110, bottom: 220, style: mask})

Narration.
"""


def callouts_of(text):
    return [b.value for scene in parse(text).scenes for b in scene.blocks if getattr(b, "key", None) == "callout"]


def test_a_callout_is_inserted_after_a_line():
    from narrate.studio.edits import insert_callout

    after = apply(CALLOUTS, insert_callout(CALLOUTS, 1, {"cx": 100.4, "cy": 200, "size": 50.6}))
    assert after.startswith("![](photo.jpg)\n\n(callout:\n  cx: 100\n  cy: 200\n  size: 51)\n\n(callout:\n  cx: 640")
    assert callouts_of(after)[0] == {"cx": "100", "cy": "200", "size": "51"}
    rect = apply(CALLOUTS, insert_callout(CALLOUTS, 10, {"type": "rectangle", "left": 1, "top": 2, "right": 3,
                                                         "bottom": 4, "alpha": 0.7}))
    assert rect.endswith("Narration.\n\n(callout:\n  type: rectangle\n  left: 1\n  top: 2\n  right: 3\n  bottom: 4\n  alpha: 0.7)\n")
    assert len(callouts_of(rect)) == 3


def test_a_callout_keeps_its_form_when_moved():
    from narrate.studio.edits import edit_callout

    after = apply(CALLOUTS, edit_callout(CALLOUTS, 3, {"cx": 700, "cy": 300}))
    assert after == CALLOUTS.replace("cx: 640\n  cy: 360", "cx: 700\n  cy: 300")
    after = apply(CALLOUTS, edit_callout(CALLOUTS, 8, {"left": 15, "style": None, "alpha": 0.3}))
    assert after.split("\n")[7] == "(callout: {type: rectangle, left: 15, top: 20, right: 110, bottom: 220, alpha: 0.3})"
    # Changing shape drops the old shape's geometry
    after = apply(CALLOUTS, edit_callout(CALLOUTS, 3, {"type": "rectangle", "left": 1, "top": 2, "right": 3, "bottom": 4}))
    assert callouts_of(after)[0] == {"type": "rectangle", "left": "1", "top": "2", "right": "3", "bottom": "4"}
    with pytest.raises(EditError, match="from 0 to 1"):
        edit_callout(CALLOUTS, 3, {"alpha": 2})
    with pytest.raises(EditError, match="isn't a callout"):
        edit_callout(CALLOUTS, 1, {"cx": 1})


@pytest.mark.parametrize("line, left", [
    (3, "![](photo.jpg)\n\n(callout: {type: rectangle"),  # the first: its blank line goes with it
    (8, "  size: 150)\n\nNarration.\n"),                   # the second
])
def test_a_callout_is_deleted_with_its_blank_line(line, left):
    from narrate.studio.edits import delete_block

    after = apply(CALLOUTS, delete_block(CALLOUTS, line))
    assert left in after and "\n\n\n" not in after and len(callouts_of(after)) == 1


def test_deleting_the_last_block_leaves_no_trailing_blank():
    from narrate.studio.edits import delete_block

    text = "Words.\n\n(callout: {cx: 1, cy: 2})\n"
    assert apply(text, delete_block(text, 3)) == "Words.\n"
