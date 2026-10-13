"""Make the pictures narrate's introduction (intro.md) shows of narrate itself, from narrate itself.

- media/studio.png: narrate studio with this script open, the cursor on its
  diagram (so the preview draws it, and the inspector shows); and
  scenes/studio-boxes.css, where the script, preview, timeline and inspector
  are in it, for scenes/studio.html to outline them.
- media/sheet.png: the contact sheet of a silent preview of this video, as an
  agent reviewing its draft would look at it.

Run from a narrate checkout: uv run python examples/intro/make_assets.py
(`--sheet-from VIDEO` takes the contact sheet of a video already built, rather than building a silent
preview first, which takes several minutes: its HTML scenes and overlay are captured frame by frame.)
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "intro.md"
STUDIO = HERE / "media" / "studio.png"
SHEET = HERE / "media" / "sheet.png"
BOXES = HERE / "scenes" / "studio-boxes.css"
VIEW, SCALE = (1440, 810), 4 / 3  # the studio laid out at 1440×810, captured at the video's 1920×1080
PARTS = {"editor": "section.editor", "preview": ".preview .screen", "timeline": "[aria-label=timeline]",
         "inspector": "section.inspector"}


def stand_in(path: Path, label: str) -> None:
    """A card for a picture not made yet, so the script builds the first time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    picture = Image.new("RGB", (1920, 1080), "#161b22")
    ImageDraw.Draw(picture).text((80, 80), label, fill="#8b949e")
    picture.save(path)


def narrate(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "narrate", *args], check=True, cwd=HERE)


def studio_screenshot() -> None:
    from playwright.sync_api import expect, sync_playwright

    from narrate.studio.server import create_app, server

    app = create_app(SCRIPT, "silent")
    running = server(app, "127.0.0.1", 0)
    thread = threading.Thread(target=running.run, daemon=True)
    thread.start()
    while not running.started:
        time.sleep(0.05)
    url = f"http://127.0.0.1:{running.servers[0].sockets[0].getsockname()[1]}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": VIEW[0], "height": VIEW[1]}, device_scale_factor=SCALE,
                                    color_scheme="dark")
            page.goto(url)
            # The outline takes the cursor to the diagram's scene; its first line is a step or two down
            page.locator("nav.outline button", has_text="render:mermaid").click()
            for _ in range(5):
                if "render:mermaid" in page.locator(".cm-activeLine").first.inner_text():
                    break
                page.keyboard.press("ArrowDown")
            # Drawn live, or the drawing a build already made
            expect(page.frame_locator("iframe[title=frame]").locator("#diagram-box svg, img.media").first).to_be_visible(
                timeout=30000)
            expect(page.get_by_test_id("inspector")).to_be_visible()
            page.mouse.move(VIEW[0] - 5, 5)  # no hover highlights
            time.sleep(0.5)
            boxes = {name: page.locator(selector).first.bounding_box() for name, selector in PARTS.items()}
            page.screenshot(path=str(STUDIO))
            browser.close()
    finally:
        running.end_streams()
        running.should_exit = True
        thread.join(5)
    lines = [f"  --{name}-{key}: {round(box[axis] * SCALE)}px;" for name, box in boxes.items()
             for key, axis in (("x", "x"), ("y", "y"), ("w", "width"), ("h", "height"))]
    BOXES.write_text("/* Where each part of narrate studio is in media/studio.png: written by make_assets.py */\n"
                     ":root {\n" + "\n".join(lines) + "\n}\n")


def contact_sheet(video: Path | None = None, engine: str = "silent") -> None:
    with tempfile.TemporaryDirectory() as tmp:
        if video is None:
            video = Path(tmp) / "preview.mp4"
            narrate("build", str(SCRIPT), "--tts", "silent", "-q", "-o", str(video))
        narrate("frames", str(video), "--script", str(SCRIPT), "--tts", engine, "--width", "400", "-o", str(SHEET))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sheet-from", metavar="VIDEO", help="a build of intro.md to take the contact sheet of")
    parser.add_argument("--tts", default="silent", help="the engine that video was built with (default silent)")
    args = parser.parse_args()
    for path, label in ((STUDIO, "narrate studio: run make_assets.py"), (SHEET, "contact sheet: run make_assets.py")):
        if not path.exists():
            stand_in(path, label)
    if not BOXES.exists():
        BOXES.write_text(":root {}\n")
    studio_screenshot()
    contact_sheet(Path(args.sheet_from).resolve() if args.sheet_from else None, args.tts)
    print(STUDIO, SHEET, BOXES)
