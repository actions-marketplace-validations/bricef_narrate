"""Every script example in the docs builds, without warnings.

Examples are the ````markdown blocks in README.md and docs/*.md (````md
blocks, which need the network, are left out). They name
placeholder files (photo.jpg, clip.mp4, …), which the fixture makes; theme.css
and the pages (scene.html, ticker.html, …) are the CSS and HTML examples from
docs/writing-scripts.md itself.
"""

import re
import shutil
import textwrap
from pathlib import Path

import pytest
from PIL import Image

from narrate import media
from narrate.build import Builder
from narrate.doctor import check_fonts, find_font
from narrate.script import parse_file
from narrate.tts import SilentSynth

ROOT = Path(__file__).parent.parent
DOCS = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
FENCE = re.compile(r"^( *)````markdown\n(.*?)^\1````$", re.M | re.S)


def examples():
    for doc in DOCS:
        text = doc.read_text()
        for m in FENCE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            yield pytest.param(textwrap.dedent(m.group(2)), id=f"{doc.relative_to(ROOT)}:{line}")


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    font = find_font("DejaVuSans.ttf")
    if font is None:  # one failure with the fix, not one per example
        pytest.skip("DejaVu Sans isn't installed: test_the_font_is_installed fails, with the fix")
    d = tmp_path_factory.mktemp("assets")
    for name, colour in (("photo.jpg", "steelblue"), ("forest.jpg", "darkgreen")):
        Image.linear_gradient("L").resize((1920, 1080)).convert("RGB").save(d / name)
        Image.blend(Image.open(d / name), Image.new("RGB", (1920, 1080), colour), 0.6).save(d / name)
    media.run(["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-f", "lavfi", "-i", "sine=frequency=330",
               "-t", "5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(d / "clip.mp4")])
    for name, seconds in (("talk.mp3", 1.5), ("music.mp3", 4)):
        media.run(["-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}", "-c:a", "libmp3lame", str(d / name)])
    guide = (ROOT / "docs/writing-scripts.md").read_text()
    (d / "theme.css").write_text(re.search(r"```css\n(.*?)```", guide, re.S).group(1))
    # Each page the guide shows ("`scene.html`, next to the script:"), under its own name
    for name, page in re.findall(r"`([\w-]+\.html)`, next to the script:\n\n```html\n(.*?)```", guide, re.S):
        (d / name).write_text(page)
    shutil.copy(font, d / "font.ttf")
    return d


@pytest.fixture(autouse=True)
def own_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path / "cache"))  # render blocks draw into it


def test_the_font_is_installed():
    """The examples' font.ttf is DejaVu Sans, part of the documented setup."""
    check = check_fonts()
    assert check.ok, f"{check.detail}. Fix: {check.fix}"


def test_the_docs_have_examples():
    assert len(list(examples())) >= 15


@pytest.mark.parametrize("script", list(examples()))
def test_example_builds(assets, tmp_path, script):
    project = tmp_path / "project"
    shutil.copytree(assets, project)
    (project / "script.md").write_text(script)
    parsed = parse_file(project / "script.md")
    result = Builder(parsed, SilentSynth(), log=lambda _: None).build(tmp_path / "out.mp4")
    assert result.video.stat().st_size > 0
    assert parsed.warnings == []


def prose(text: str) -> str:
    """The text outside fenced code blocks."""
    out, fence = [], None
    for line in text.splitlines():
        m = re.match(r"\s*(`{3,}|~{3,})", line)
        if m and (fence is None or m.group(1).startswith(fence)):
            fence = None if fence else m.group(1)
            continue
        if fence is None:
            out.append(line)
    return "\n".join(out)


def anchors(path: Path) -> set[str]:
    """GitHub's heading anchors: lower case, punctuation dropped, spaces as hyphens."""
    headings = re.findall(r"^#+\s+(.*?)\s*$", prose(path.read_text()), re.M)
    return {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}


@pytest.mark.parametrize("doc", [*DOCS, *sorted((ROOT / "docs").rglob("*/*.md"))], ids=lambda p: p.name)
def test_links_resolve(doc):
    text = re.sub(r"``.*?``|`[^`\n]*`", "", prose(doc.read_text()))  # inline code isn't a link
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if re.match(r"[a-z]+:", target):
            continue  # an external URL
        name, _, anchor = target.partition("#")
        path = (doc.parent / name).resolve() if name else doc
        assert path.exists(), f"{doc.name}: {target}"
        if anchor:
            assert anchor in anchors(path), f"{doc.name}: {target}"
