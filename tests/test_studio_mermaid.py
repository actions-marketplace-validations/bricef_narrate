"""Mermaid diagrams drawn live in the studio's preview (#76), by the page a build draws them with."""

import pytest
from playwright.sync_api import expect
from starlette.testclient import TestClient

from narrate import mermaid, render
from narrate.script import Render
from narrate.studio.server import create_app

from test_studio_e2e import page, running  # noqa: F401 - the browser fixture

SCRIPT = "---\nsize: 640x360\n---\n\n```render:mermaid\nflowchart LR\n  A[Alpha] --> B[Beta]\n```\n\nA diagram.\n"


def test_the_live_page_is_the_builds_with_mermaid_from_the_studio():
    block = Render("mermaid", 'flowchart LR\n  A["</script><b>"] --> B', {"background": "#101010"})
    page_html = mermaid.live_page(block, render.Context(640, 360, "default", None), "/mermaid/x/mermaid.min.js")
    assert '<script src="/mermaid/x/mermaid.min.js">' in page_html
    assert "background: #101010" in page_html and '"theme": "dark"' in page_html  # dark background, dark theme
    assert page_html.count("</script>") == 2  # the diagram's text can't end the drawing script early


def test_the_studio_serves_narrates_own_mermaid(tmp_path):
    (tmp_path / "s.md").write_text("Hi.\n")
    client = TestClient(create_app(tmp_path / "s.md", "silent", hosts=["testserver"]))
    served = client.get(f"/mermaid/{mermaid.MERMAID_VERSION}/mermaid.min.js")
    assert served.status_code == 200 and served.headers["content-type"].startswith("text/javascript")
    assert served.content == mermaid.ensure().read_bytes()
    assert client.get("/mermaid/1.0.0/mermaid.min.js").status_code == 404


def test_a_diagram_is_drawn_as_it_is_typed(tmp_path, page):  # noqa: F811
    script = tmp_path / "s.md"
    script.write_text(SCRIPT)
    with running(script) as url:
        page.goto(url)
        page.locator(".cm-line", has_text="render:mermaid").click()
        frame = page.frame_locator("iframe[title=frame]")
        expect(frame.locator("html")).to_have_attribute("data-drawn", "diagram", timeout=15000)
        expect(frame.locator("svg")).to_contain_text("Alpha")
        # Fitted as a build fits it: 90% of the frame's width or height, centred
        box = frame.locator("#diagram-box svg").evaluate(
            "el => { const r = el.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }")
        assert max(box[2] / 640, box[3] / 360) == pytest.approx(0.9, abs=0.01)
        assert box[0] + box[2] / 2 == pytest.approx(320, abs=1)

        # Edited, it's drawn again
        page.locator(".cm-line", has_text="A[Alpha]").click()
        page.keyboard.press("End")
        page.keyboard.type(" --> C[Gamma]")
        expect(frame.locator("svg")).to_contain_text("Gamma", timeout=15000)

        # Broken, Mermaid says what's wrong instead
        page.keyboard.type(" --> -->")
        expect(frame.locator("html")).to_have_attribute("data-drawn", "error", timeout=15000)
        expect(frame.locator("#diagram-box")).to_contain_text("error", ignore_case=True)
        expect(frame.locator("svg")).to_have_count(0)
