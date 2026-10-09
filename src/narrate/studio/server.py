"""narrate studio's server: one script, its project's files, and an event stream.

Design record: docs/design/studio.md. The script file is the source of truth
(D8): the editor saves the whole file with the version it last loaded, and a
save over a newer version on disk is refused. A watcher polls the file and
announces outside changes over server-sent events (D5).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

STATIC = Path(__file__).parent / "static"
POLL_SECONDS = 0.5
KEEPALIVE_SECONDS = 15.0


def version_of(path: Path) -> str:
    """A token for the file's current contents: modification time and size."""
    try:
        stat = path.stat()
    except FileNotFoundError:
        return "missing"
    return f"{stat.st_mtime_ns}-{stat.st_size}"


class Conflict(Exception):
    """The file changed on disk since the editor loaded it."""


class Session:
    """The script being edited, and everyone listening for changes to it."""

    def __init__(self, script: Path):
        self.script = script.resolve()
        self.project = self.script.parent
        self.version = version_of(self.script)
        self._listeners: set[asyncio.Queue] = set()

    def read(self) -> dict:
        # The version is taken from the file now, not remembered: whoever loads it has this version
        self.version = version_of(self.script)
        text = self.script.read_bytes().decode("utf-8-sig") if self.script.exists() else ""
        return {"name": self.script.name, "text": text.replace("\r\n", "\n"), "version": self.version}

    def save(self, text: str, base: str) -> str:
        """Write the whole script, unless it changed on disk since `base`."""
        if version_of(self.script) != base:
            raise Conflict
        crlf = self.script.exists() and b"\r\n" in self.script.read_bytes()
        data = (text.replace("\n", "\r\n") if crlf else text).encode("utf-8")
        mode = self.script.stat().st_mode & 0o777 if self.script.exists() else 0o644
        fd, tmp = tempfile.mkstemp(dir=self.project, prefix=f".{self.script.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.chmod(tmp, mode)
            os.replace(tmp, self.script)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        self.version = version_of(self.script)  # our own write isn't an outside change
        return self.version

    def poll(self) -> dict | None:
        """An event if the script changed on disk since we last looked."""
        current = version_of(self.script)
        if current == self.version:
            return None
        self.version = current
        return {"type": "script-changed", "version": current}

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._listeners.discard(queue)

    def publish(self, event: dict) -> None:
        for queue in self._listeners:
            queue.put_nowait(event)

    def end_streams(self) -> None:
        """Tell every open event stream to finish, so the server can stop without cutting them off."""
        for queue in self._listeners:
            queue.put_nowait(None)

    async def watch(self) -> None:
        while True:
            await asyncio.sleep(POLL_SECONDS)
            if event := self.poll():
                self.publish(event)

    def project_file(self, relative: str) -> Path | None:
        """A file inside the project folder, or None. Hidden files are refused, since
        the folder may hold secrets such as .env, except narrate's own .narrate/."""
        path = (self.project / relative).resolve()
        if not path.is_relative_to(self.project) or not path.is_file():
            return None
        parts = path.relative_to(self.project).parts
        if any(p.startswith(".") for p in parts) and parts[0] != ".narrate":
            return None
        return path


def create_app(script: Path) -> Starlette:
    session = Session(script)

    async def index(request: Request) -> Response:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    async def get_script(request: Request) -> Response:
        return JSONResponse(session.read())

    async def put_script(request: Request) -> Response:
        body = await request.json()
        try:
            version = session.save(str(body["text"]), str(body["version"]))
        except Conflict:
            return JSONResponse({"error": "the script changed on disk", "version": version_of(session.script)},
                                status_code=409)
        return JSONResponse({"version": version})

    async def events(request: Request) -> Response:
        queue = session.subscribe()

        async def stream():
            try:
                yield f"event: hello\ndata: {json.dumps({'version': session.version})}\n\n"
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    if event is None:  # the server is stopping
                        return
                    yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            finally:
                session.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def project_file(request: Request) -> Response:
        path = session.project_file(request.path_params["path"])
        if path is None:
            return Response("not found", status_code=404)
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.loop = asyncio.get_running_loop()
        watcher = asyncio.create_task(session.watch())
        try:
            yield
        finally:
            watcher.cancel()

    app = Starlette(routes=[
        Route("/", index),
        Route("/api/script", get_script, methods=["GET"]),
        Route("/api/script", put_script, methods=["PUT"]),
        Route("/api/events", events),
        Route("/files/{path:path}", project_file),
        Mount("/static", StaticFiles(directory=STATIC), name="static"),
    ], lifespan=lifespan)
    app.state.session = session
    return app


def server(app: Starlette, host: str, port: int):
    """A uvicorn server for the studio that ends its event streams when asked to stop.

    Event streams never finish by themselves, so on Ctrl-C (or should_exit) they are
    told to end first; graceful shutdown then completes at once instead of timing out."""
    import uvicorn

    class StudioServer(uvicorn.Server):
        def handle_exit(self, sig, frame) -> None:
            self.end_streams()
            super().handle_exit(sig, frame)

        def end_streams(self) -> None:
            loop = getattr(app.state, "loop", None)
            if loop is not None and not loop.is_closed():
                loop.call_soon_threadsafe(app.state.session.end_streams)

    return StudioServer(uvicorn.Config(app, host=host, port=port, log_level="warning",
                                       timeout_graceful_shutdown=2))


def serve(script: Path, host: str, port: int, open_browser: bool = False) -> None:
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}/"
    print(f"narrate studio: {script} at {url} (Ctrl-C to stop)", flush=True)
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    server(create_app(script), host, port).run()
