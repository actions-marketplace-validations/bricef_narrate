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
import shutil
import tempfile
from collections import OrderedDict
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

STATIC = Path(__file__).parent / "static"
ENGINES = ("auto", "kokoro", "elevenlabs", "silent")
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
    """The script being edited, the engine it's previewed with, and everyone listening for changes."""

    def __init__(self, script: Path, engine: str = "kokoro"):
        self.script = script.resolve()
        self.project = self.script.parent
        self.version = version_of(self.script)
        self.engine = engine
        self._synth = None
        self._listeners: set[asyncio.Queue] = set()
        self.analyses: OrderedDict = OrderedDict()  # the last few analyses by text id, for previews
        self.peaks: OrderedDict = OrderedDict()  # waveforms by sound id (#60)
        self.build = None  # the latest BuildRun (#55)
        self.scene_build = None  # the latest scene render (#61)
        self.scene_renders: dict = {}  # fingerprint -> (summary, notes) of renders still in scratch
        self.scratch = Path(tempfile.mkdtemp(prefix="narrate-studio-"))  # clip stills, copies of renders

    def remember(self, analysis) -> None:
        self.analyses[analysis.report["id"]] = analysis
        self.analyses.move_to_end(analysis.report["id"])
        while len(self.analyses) > 4:
            self.analyses.popitem(last=False)

    def synth(self):
        """The session's speech engine (Kokoro by default, D10), made on first use."""
        if self._synth is None:
            from ..tts import make_synth

            self._synth = make_synth(self.engine)
        return self._synth

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


def create_app(script: Path, engine: str = "kokoro") -> Starlette:
    session = Session(script, engine)

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

    async def analyse(request: Request) -> Response:
        from .analysis import run

        body = await request.json()
        try:
            synth = session.synth()
        except RuntimeError as e:  # e.g. ElevenLabs without a key
            return JSONResponse({"error": str(e)}, status_code=503)
        analysis = await run_in_threadpool(run, str(body.get("text", "")), session.script, synth)
        session.remember(analysis)
        return JSONResponse({**analysis.report, "engine": session.engine})

    async def preview(request: Request) -> Response:
        from .preview import Files, frame

        body = await request.json()
        analysis = session.analyses.get(str(body.get("id")))
        if analysis is None:
            return JSONResponse({"error": "analyse the script again"}, status_code=409)
        plan = analysis.plans.get(int(body.get("scene", 0)))
        if plan is None:
            return JSONResponse({"error": "that scene can't be shown"}, status_code=404)
        try:
            shown = await run_in_threadpool(frame, plan, float(body.get("time", 0)), analysis.settings,
                                            Files(session.project, session.scratch), analysis.plans)
        except Exception as e:  # noqa: BLE001 - a preview never takes the studio down
            return JSONResponse({"error": f"couldn't preview this moment: {e}"}, status_code=500)
        return JSONResponse(shown)

    async def waveform(request: Request) -> Response:
        from .analysis import PEAK_RATE, peaks

        key = request.path_params["sound"]
        if key not in session.peaks:
            sound = next((a.sounds[key] for a in reversed(session.analyses.values()) if key in a.sounds), None)
            if sound is None:
                return JSONResponse({"error": "no such sound: analyse the script again"}, status_code=404)
            session.peaks[key] = await run_in_threadpool(peaks, sound)
            while len(session.peaks) > 256:
                session.peaks.popitem(last=False)
        # A sound id names its samples, so the answer never changes
        return JSONResponse({"rate": PEAK_RATE, "peaks": session.peaks[key]},
                            headers={"Cache-Control": "max-age=86400, immutable"})

    async def edit(request: Request) -> Response:
        from .edits import (EditError, delete_block, edit_block, edit_callout, for_editor, index_of, insert_callout,
                            insert_mark, set_header, set_voice)

        body = await request.json()
        text, line, changes = str(body.get("text", "")), int(body.get("line", 0)), dict(body.get("set") or {})
        op = body.get("op", "media")
        try:
            if op == "media":
                change = edit_block(text, line, changes)
            elif op == "callout":
                change = edit_callout(text, line, changes)
            elif op == "insert-callout":
                change = insert_callout(text, int(body.get("after", 0)), dict(body.get("callout") or {}))
            elif op == "delete":
                change = delete_block(text, line)
            elif op == "header":
                change = set_header(text, str(body.get("key", "")), str(body.get("value", "")))
            elif op == "voice":
                change = set_voice(text, line, str(body.get("voice", "")))
            elif op == "mark":
                name = body.get("name")
                change = insert_mark(text, index_of(text, int(body.get("at", 0))), str(name) if name else None)
            else:
                return JSONResponse({"error": f"no such edit: {op!r}"}, status_code=400)
        except EditError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return JSONResponse(for_editor(text, change))

    async def voices(request: Request) -> Response:
        from .voices import catalogue

        try:
            synth = session.synth()
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=503)
        return JSONResponse(await run_in_threadpool(catalogue, synth, session.project))

    async def audition(request: Request) -> Response:
        from .audio import scene_audio as synthesise
        from .voices import characters, sample_script

        body = await request.json()
        try:
            text = sample_script(str(body.get("text", "")), str(body.get("voice", "")), str(body.get("sample", "")))
            synth = session.synth()
            if body.get("dry"):  # what it would send, before asking to spend it
                return JSONResponse(await run_in_threadpool(characters, text, session.script, synth))
            result = await run_in_threadpool(synthesise, text, session.script, synth, 1, session.scratch)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except Exception as e:  # noqa: BLE001 - the engine's own message (no key, a refused request) is the answer
            return JSONResponse({"error": str(e)}, status_code=502)
        return JSONResponse(result)

    async def put_pins(request: Request) -> Response:
        from ..voicemap import VoiceMapError
        from .voices import write_pins

        pins = (await request.json()).get("pins") or {}
        if not isinstance(pins, dict) or not all(isinstance(v, dict) for v in pins.values()):
            return JSONResponse({"error": "pins are a map of name -> {engine: voice}"}, status_code=400)
        try:
            await run_in_threadpool(write_pins, session.project, pins)
        except VoiceMapError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        session.publish({"type": "voices-changed"})  # timing may change with the voice
        return JSONResponse({"saved": True})

    async def set_engine(request: Request) -> Response:
        from ..tts import make_synth

        engine = str((await request.json()).get("engine", ""))
        if engine not in ENGINES:
            return JSONResponse({"error": f"no engine {engine!r}"}, status_code=400)
        try:
            synth = make_synth(engine)  # check it can start before switching (an ElevenLabs key, say)
        except RuntimeError as e:
            return JSONResponse({"error": str(e), "engine": session.engine}, status_code=400)
        session.engine, session._synth = engine, synth
        return JSONResponse({"engine": engine})

    async def scene_audio(request: Request) -> Response:
        from .audio import scene_audio as synthesise

        analysis = session.analyses.get(str((await request.json()).get("id")))
        if analysis is None:
            return JSONResponse({"error": "analyse the script again"}, status_code=409)
        try:
            synth = session.synth()
            result = await run_in_threadpool(synthesise, analysis.text, session.script, synth,
                                             int(request.path_params["index"]), session.scratch)
        except Exception as e:  # noqa: BLE001 - the engine's own message (no key, a refused request) is the answer
            return JSONResponse({"error": str(e)}, status_code=502)
        return JSONResponse(result)

    async def start_build(request: Request) -> Response:
        from .builds import BuildRun

        if session.build is not None and session.build.running:
            return JSONResponse({"error": "a build is already running"}, status_code=409)
        session.build = BuildRun(session)
        app.state.build_task = asyncio.create_task(session.build.run())
        return JSONResponse(session.build.status, status_code=202)

    async def build_status(request: Request) -> Response:
        return JSONResponse(session.build.status if session.build else {"state": "idle"})

    async def cancel_build(request: Request) -> Response:
        if session.build is None or not session.build.running:
            return JSONResponse({"error": "no build is running"}, status_code=409)
        session.build.cancel()
        return JSONResponse({"state": "cancelling"})

    async def render_scene(request: Request) -> Response:
        from .builds import BuildRun, fingerprint

        index = int(request.path_params["index"])
        if session.scene_build is not None and session.scene_build.running:
            return JSONResponse({"error": "a scene is already being rendered"}, status_code=409)
        # The file on disk, as for a build: the page saves first
        key = fingerprint(session.script, session.read()["text"], session.engine, index)
        out = session.scratch / f"scene-{index}-{key}.mp4"
        run = BuildRun(session, out=out, args=["--scenes", str(index)], event="scene-build", label={"scene": index})
        session.scene_build = run
        if key in session.scene_renders and out.exists():  # rendered already: the same text, engine and files
            run.done(*session.scene_renders[key])
            return JSONResponse(run.status)

        async def render() -> None:
            await run.run()
            if run.status["state"] == "done":
                session.scene_renders[key] = (run.status["summary"], run.status["notes"])

        app.state.scene_task = asyncio.create_task(render())
        return JSONResponse(run.status, status_code=202)

    async def scene_render_status(request: Request) -> Response:
        return JSONResponse(session.scene_build.status if session.scene_build else {"state": "idle"})

    async def cancel_scene_render(request: Request) -> Response:
        if session.scene_build is None or not session.scene_build.running:
            return JSONResponse({"error": "no scene is being rendered"}, status_code=409)
        session.scene_build.cancel()
        return JSONResponse({"state": "cancelling"})

    async def scratch_file(request: Request) -> Response:
        path = (session.scratch / request.path_params["name"]).resolve()
        if not path.is_relative_to(session.scratch) or not path.is_file():
            return Response("not found", status_code=404)
        return FileResponse(path)

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

    async def scene_page(request: Request) -> Response:
        """A project file for an HTML scene (#73): the page itself, set up to be scrubbed
        (preview.page_html, with the narration from its address), and its files as they are."""
        from .preview import page_html

        path = session.project_file(request.path_params["path"])
        if path is None:
            return Response("not found", status_code=404)
        if path.suffix.lower() not in (".html", ".htm"):
            return FileResponse(path, headers={"Cache-Control": "no-cache"})
        try:
            narrate = json.loads(request.query_params.get("narrate") or "{}")
            text = page_html(path.read_bytes().decode("utf-8", errors="replace"), narrate)
        except (ValueError, TypeError, AttributeError) as e:
            return Response(f"bad narration for the page: {e}", status_code=400)
        return HTMLResponse(text, headers={"Cache-Control": "no-cache"})

    async def mermaid_js(request: Request) -> Response:
        """narrate's own pinned mermaid.js (#76), downloaded and checked on first use as for a build."""
        from .. import mermaid
        from ..render import RenderError

        if request.path_params["version"] != mermaid.MERMAID_VERSION:
            return Response("not found", status_code=404)
        try:
            path = await run_in_threadpool(mermaid.ensure, lambda _: None)
        except (RenderError, OSError) as e:
            return Response(f"mermaid.js isn't available: {e}", status_code=503)
        return FileResponse(path, media_type="text/javascript", headers={"Cache-Control": "max-age=86400"})

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.loop = asyncio.get_running_loop()
        watcher = asyncio.create_task(session.watch())
        try:
            yield
        finally:
            watcher.cancel()
            for run in (session.build, session.scene_build):
                if run is not None:
                    run.cancel()  # don't leave a build running after the studio stops
            shutil.rmtree(session.scratch, ignore_errors=True)

    app = Starlette(routes=[
        Route("/", index),
        Route("/api/script", get_script, methods=["GET"]),
        Route("/api/script", put_script, methods=["PUT"]),
        Route("/api/analyse", analyse, methods=["POST"]),
        Route("/api/frame", preview, methods=["POST"]),
        Route("/api/engine", set_engine, methods=["POST"]),
        Route("/api/edit", edit, methods=["POST"]),
        Route("/api/voices", voices, methods=["GET"]),
        Route("/api/voices/audition", audition, methods=["POST"]),
        Route("/api/voices/pins", put_pins, methods=["PUT"]),
        Route("/api/peaks/{sound}", waveform),
        Route("/api/scenes/{index:int}/audio", scene_audio, methods=["POST"]),
        Route("/api/build", start_build, methods=["POST"]),
        Route("/api/build", build_status, methods=["GET"]),
        Route("/api/build/cancel", cancel_build, methods=["POST"]),
        Route("/api/scenes/{index:int}/render", render_scene, methods=["POST"]),
        Route("/api/scenes/render", scene_render_status, methods=["GET"]),
        Route("/api/scenes/render/cancel", cancel_scene_render, methods=["POST"]),
        Route("/scratch/{name}", scratch_file),
        Route("/api/events", events),
        Route("/files/{path:path}", project_file),
        Route("/pages/{path:path}", scene_page),
        Route("/mermaid/{version}/mermaid.min.js", mermaid_js),
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


def serve(script: Path, host: str, port: int, open_browser: bool = False, engine: str = "kokoro") -> None:
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}/"
    print(f"narrate studio: {script} at {url} (Ctrl-C to stop)", flush=True)
    if open_browser:
        import webbrowser

        webbrowser.open(url)
    server(create_app(script, engine), host, port).run()
