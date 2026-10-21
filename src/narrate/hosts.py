"""Which requests the studio and the service answer (#93).

Neither has a login: they're meant to be reached only from this machine, or a
network you trust. A web page open in your browser runs on this machine too,
so both refuse what such a page could send them:
- a request addressed to a host name they don't answer to, as when a site
  points its own name at 127.0.0.1 to read their answers;
- a request that changes something, sent from another site's page.
Programs, curl and narrate's own CLI send no Origin header, so only the first
applies to them.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

LOCAL = ("localhost", "127.0.0.1", "[::1]")
ANY_ADDRESS = ("", "0.0.0.0", "::")
SAFE = ("GET", "HEAD")  # no route changes anything on these


def split(host: str) -> tuple[str, str]:
    """A Host header's name and port ('' without one). The name is in lower case, an IPv6 address
    in brackets, as a browser sends it; the same goes for a name given to --host or --allow-host."""
    host = host.strip().lower()
    if host.startswith("["):
        name, _, port = host[1:].partition("]")
        port = port.removeprefix(":")
    elif host.count(":") == 1:
        name, _, port = host.partition(":")
    else:  # no port, or an IPv6 address without brackets, as given to --host
        name, port = host, ""
    try:
        return f"[{ipaddress.IPv6Address(name)}]", port
    except ValueError:
        return name, port


def name_of(host: str) -> str:
    return split(host)[0]


def allowed(bind: str, more: Iterable[str] = ()) -> list[str]:
    """The names a server listening on `bind` answers to: this machine's own, the address it
    listens on when that's a particular one, and any more it's told to allow."""
    names = [*LOCAL, *([] if bind in ANY_ADDRESS else [bind]), *more]
    return list(dict.fromkeys(n for n in map(name_of, names) if n))


class OwnOrigin:
    """ASGI middleware: 403 for a request to a host name not in `hosts`, and for one that changes
    something from a page that isn't this server's own."""

    def __init__(self, app, hosts: Iterable[str]):
        self.app, self.hosts = app, frozenset(map(name_of, hosts))

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and (refusal := self.refusal(Headers(scope=scope), scope["method"])):
            await JSONResponse({"error": refusal}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def refusal(self, headers: Headers, method: str) -> str | None:
        name, port = split(headers.get("host", ""))
        if name not in self.hosts:
            return "narrate doesn't answer to this host name: start it with --allow-host to allow it"
        # Browsers send an Origin with every request that can change something; programs don't
        origin = headers.get("origin")
        if method not in SAFE and origin is not None and not self.own(origin, port):
            return "narrate refuses changes sent from another site's page"
        return None

    def own(self, origin: str, port: str) -> bool:
        """Whether a page at `origin` is this server's: one of its names, on the port the request
        was sent to. https too, for a proxy in front that ends TLS. A sandboxed page's is "null"."""
        scheme, _, address = origin.strip().lower().partition("://")
        name, origin_port = split(address)
        return scheme in ("http", "https") and name in self.hosts and origin_port == port
