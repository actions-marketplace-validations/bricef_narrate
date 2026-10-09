"""render:web: a web page captured as a picture at build time (#50).

A page changes over time, so a capture can't be reproduced later. It is
stored in the project (.narrate/generated/web/, see render.py) and reused by
later builds, offline too, until `narrate build --regenerate` takes it again.

The page loads in a fresh browser context: no cookies or stored logins, the
requested viewport, pixel density and colour scheme, and Basic-auth
credentials only from an environment variable named in the script, never the
secret itself.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

from .config import ConfigError, parse_size
from .render import Context, Renderer, RenderError, register
from .script import Render

SCHEMES = {"light", "dark", "no-preference"}
WAITS = {"load", "networkidle"}
TIMEOUT = 60_000  # ms to load a page


def url_of(block: Render) -> str:
    """`url`, or the body when it is just a URL (```render:web then https://…)."""
    url = str(block.settings.get("url") or "").strip()
    body = block.body.strip()
    return url or (body if re.fullmatch(r"https?://\S+", body) else "")


def _selectors(value) -> str:
    return ", ".join(str(v) for v in value) if isinstance(value, list) else str(value)


@register
class Web(Renderer):
    name = "web"
    stored = True
    context_keys = ("width", "height")  # a theme or canvas change doesn't touch a screenshot
    settings = frozenset({"url", "viewport", "scale", "color-scheme", "hide", "css", "scroll-to", "selector",
                          "wait", "auth"})

    def check(self, block: Render) -> list[str]:
        problems = super().check(block)
        s = block.settings
        url = url_of(block)
        if not url:
            problems.append("render:web needs a url")
        elif urlparse(url).scheme not in ("http", "https") or not urlparse(url).netloc:
            problems.append(f"render:web: url must be an http or https address, not {url!r}")
        if "viewport" in s:
            try:
                parse_size(s["viewport"])
            except ConfigError as e:
                problems.append(f"render:web: viewport: {e}")
        try:
            if not 0 < float(s.get("scale", 2)) <= 4:
                raise ValueError
        except (TypeError, ValueError):
            problems.append(f"render:web: scale must be a number from 0 to 4, not {s['scale']!r}")
        if str(s.get("color-scheme", "light")).lower() not in SCHEMES:
            problems.append(f"render:web: color-scheme must be {', '.join(sorted(SCHEMES))}")
        wait = str(s.get("wait", "load")).lower()
        if wait not in WAITS and not re.fullmatch(r"\d+(\.\d+)?", wait):
            problems.append("render:web: wait must be load, networkidle or a number of milliseconds")
        if "auth" in s and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(s["auth"])):
            problems.append("render:web: auth names an environment variable holding user:password")
        return problems

    def render(self, block: Render, ctx: Context, out: Path) -> None:
        from playwright.sync_api import Error

        s = block.settings
        url = url_of(block)
        viewport = parse_size(s["viewport"]) if "viewport" in s else (ctx.width, ctx.height)
        credentials = None
        if "auth" in s:
            secret = os.environ.get(str(s["auth"]), "")
            if ":" not in secret:
                raise RenderError(f"render:web: set {s['auth']} to user:password for {url}")
            user, _, password = secret.partition(":")
            credentials = {"username": user, "password": password}
        wait = str(s.get("wait", "load")).lower()
        try:
            with ctx.frames.web(viewport, float(s.get("scale", 2)), str(s.get("color-scheme", "light")).lower(),
                                credentials) as page:
                response = page.goto(url, wait_until="networkidle" if wait == "networkidle" else "load",
                                     timeout=TIMEOUT)
                if response is not None and response.status >= 400:
                    raise RenderError(f"render:web: {url} answered {response.status}")
                if wait not in WAITS:
                    page.wait_for_timeout(float(wait))
                css = ""
                if "hide" in s:
                    css += f"{_selectors(s['hide'])} {{ display: none !important; }}\n"
                css += str(s.get("css", ""))
                if css.strip():
                    page.add_style_tag(content=css)
                if "scroll-to" in s:
                    try:
                        page.get_by_text(str(s["scroll-to"])).last.scroll_into_view_if_needed(timeout=10_000)
                    except Error:
                        raise RenderError(f"render:web: no text {s['scroll-to']!r} to scroll to on {url}") from None
                page.evaluate("document.fonts.ready.then(() => true)")
                if "selector" in s:
                    target = page.locator(str(s["selector"])).first
                    if not target.count():
                        raise RenderError(f"render:web: nothing matches {s['selector']!r} on {url}")
                    target.screenshot(path=str(out), timeout=10_000)
                else:
                    page.screenshot(path=str(out))
        except Error as e:
            raise RenderError(f"render:web: couldn't capture {url}: {str(e).splitlines()[0]}") from None
