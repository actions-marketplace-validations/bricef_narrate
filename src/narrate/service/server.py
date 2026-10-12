"""`narrate serve`: narrate as an internal HTTP API (#79, docs/design/service.md).

Starlette, as the studio is. There's no authentication: it's for your own
programs, on localhost or a private network.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import secrets
import shutil
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from ..child import Child
from . import openapi
from .jobs import Runner, view
from .options import ENGINES, OptionError
from .projects import ProjectError, lay_out
from .projects import parse as parse_project
from .store import FINAL, HashMismatch, Store, is_sha256

AUDITION_WAIT = 120  # seconds an audition is waited for before it's answered as a job still running


def check_options(body: dict, engine: str) -> list[str]:
    """The engine a check times and prices with, as flags: the service's own unless it names one."""
    tts, model = body.get("tts", engine), body.get("tts_model")
    if tts is not None and tts not in ENGINES:
        raise OptionError(f"tts must be one of {', '.join(ENGINES)}, not {tts!r}")
    if model is not None and not (isinstance(model, str) and model.strip()):
        raise OptionError("tts_model must be a string")
    return [*(["--tts", tts] if tts else []), *(["--tts-model", model] if model else [])]


def _error(message: str, status: int = 400, **more) -> JSONResponse:
    return JSONResponse({"error": message, **more}, status_code=status)


async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise ValueError("the body must be a JSON object")
    return body


def create_app(root: Path, engine: str = "kokoro", workers: int = 1) -> Starlette:
    store = Store(root)
    runner = Runner(store, engine, workers)

    async def index(request: Request) -> Response:
        return JSONResponse({"service": "narrate", "api": "/v1", "openapi": "/v1/openapi.json",
                             "engine": engine, "workers": runner.workers})

    async def document(request: Request) -> Response:
        return JSONResponse(openapi.document())

    async def missing(request: Request) -> Response:
        try:
            hashes = (await _body(request)).get("hashes")
        except ValueError as e:
            return _error(str(e))
        if not isinstance(hashes, list) or not all(isinstance(h, str) and is_sha256(h) for h in hashes):
            return _error("hashes must be a list of SHA-256 hashes, in lowercase hex")
        return JSONResponse({"missing": store.missing(hashes)})

    async def upload(request: Request) -> Response:
        sha256 = request.path_params["sha256"]
        if not is_sha256(sha256):
            return _error("files are named by their SHA-256, in lowercase hex")
        part, digest = store.incoming(), hashlib.sha256()
        with part.open("wb") as out:
            async for chunk in request.stream():
                digest.update(chunk)
                out.write(chunk)
        try:
            kept = store.keep(sha256, part, digest.hexdigest())
        except HashMismatch as e:
            return _error(str(e))
        return JSONResponse({"sha256": sha256}, status_code=201 if kept else 200)

    async def start(request: Request) -> Response:
        try:
            body = await _body(request)
            job = runner.submit(str(body.get("kind", "build")), body.get("project"), body.get("options") or {},
                                body.get("media"))
        except ProjectError as e:
            return _error(str(e), **({"missing": e.missing} if e.missing else {}))
        except (OptionError, ValueError) as e:
            return _error(str(e))
        return JSONResponse(view(job), status_code=202)

    async def check(request: Request) -> Response:
        """`narrate check --timing --json` on the project, laid out in a folder of its own for the purpose."""
        try:
            body = await _body(request)
            project = parse_project(body.get("project"))
            args = check_options(body, engine)
        except (ProjectError, OptionError, ValueError) as e:
            return _error(str(e), **({"missing": e.missing} if getattr(e, "missing", None) else {}))
        folder = store.root / "checks" / secrets.token_hex(8)
        try:
            script = lay_out(project, store, folder)
            outcome = await Child(["check", str(script), "--timing", "--json", *args], cwd=folder).run()
        except ProjectError as e:
            return _error(str(e), **({"missing": e.missing} if e.missing else {}))
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        try:
            report = json.loads(outcome.stdout)
        except ValueError:
            return _error("; ".join(e["message"] for e in outcome.errors) or "the check didn't finish", 500)
        return JSONResponse(report)

    async def voices(request: Request) -> Response:
        from ..studio.voices import catalogue
        from ..tts import make_synth

        tts = request.query_params.get("tts", engine)
        if tts not in ENGINES:
            return _error(f"tts must be one of {', '.join(ENGINES)}")
        return JSONResponse(await run_in_threadpool(catalogue, make_synth(tts, planning=True), store.root))

    async def audition(request: Request) -> Response:
        """A voice heard: an audio job of a one-paragraph script, waited for, since it's short."""
        from ..studio.voices import sample_script

        try:
            body = await _body(request)
            text = sample_script("", str(body.get("voice", "")), str(body.get("text", "")))
            options = {"format": "wav", **({"tts": body["tts"]} if body.get("tts") else {})}
            job = runner.submit("audio", {"script": "audition.md", "text": text}, options)
        except (ProjectError, OptionError, ValueError) as e:
            return _error(str(e))
        queue = runner.listen(job["id"])
        try:
            deadline = asyncio.get_running_loop().time() + AUDITION_WAIT
            while (job := store.job(job["id"]))["state"] not in FINAL:
                left = deadline - asyncio.get_running_loop().time()
                if left <= 0:
                    return JSONResponse(view(job), status_code=202)
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(queue.get(), timeout=left)
        finally:
            runner.unlisten(job["id"], queue)
        return JSONResponse(view(job))

    async def listing(request: Request) -> Response:
        try:
            limit = max(1, min(1000, int(request.query_params.get("limit", 50))))
        except ValueError:
            return _error("limit must be a number")
        return JSONResponse({"jobs": [view(j) for j in store.jobs(limit, request.query_params.get("state"))]})

    def found(request: Request) -> dict | None:
        return store.job(request.path_params["id"])

    async def one(request: Request) -> Response:
        job = found(request)
        return JSONResponse(view(job)) if job else _error("no such job", 404)

    async def cancel(request: Request) -> Response:
        job = runner.cancel(request.path_params["id"])
        return JSONResponse(view(job)) if job else _error("no such job", 404)

    async def events(request: Request) -> Response:
        job_id = request.path_params["id"]
        if store.job(job_id) is None:
            return _error("no such job", 404)
        queue = runner.listen(job_id)

        async def stream():
            try:
                current = view(store.job(job_id))
                while True:
                    if current is None:  # the service is stopping
                        return
                    yield f"event: job\ndata: {json.dumps(current)}\n\n"
                    if current["state"] in FINAL:
                        return
                    try:
                        current = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": still here\n\n"
                        current = view(store.job(job_id))
            finally:
                runner.unlisten(job_id, queue)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    async def output(request: Request) -> Response:
        job_id = request.path_params["id"]
        path = runner.output(job_id, request.path_params["name"]) if store.job(job_id) else None
        return FileResponse(path) if path else _error("no such output", 404)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette):
        app.state.loop = asyncio.get_running_loop()
        await runner.start()
        try:
            yield
        finally:
            await runner.stop()

    app = Starlette(routes=[
        Route("/", index),
        Route("/v1", index),
        Route("/v1/openapi.json", document),
        Route("/v1/files/missing", missing, methods=["POST"]),
        Route("/v1/files/{sha256}", upload, methods=["PUT"]),
        Route("/v1/check", check, methods=["POST"]),
        Route("/v1/voices", voices),
        Route("/v1/auditions", audition, methods=["POST"]),
        Route("/v1/jobs", start, methods=["POST"]),
        Route("/v1/jobs", listing, methods=["GET"]),
        Route("/v1/jobs/{id}", one),
        Route("/v1/jobs/{id}/events", events),
        Route("/v1/jobs/{id}/cancel", cancel, methods=["POST"]),
        Route("/v1/jobs/{id}/outputs/{name:path}", output),
    ], lifespan=lifespan)
    app.state.runner = runner
    app.state.store = store
    return app


def server(app: Starlette, host: str, port: int):
    """A uvicorn server that ends the jobs' event streams when asked to stop, so shutdown doesn't wait on them."""
    import uvicorn

    class ServiceServer(uvicorn.Server):
        def handle_exit(self, sig, frame) -> None:
            self.end_streams()
            super().handle_exit(sig, frame)

        def end_streams(self) -> None:
            loop = getattr(app.state, "loop", None)
            if loop is not None and not loop.is_closed():
                loop.call_soon_threadsafe(app.state.runner.end_streams)

    return ServiceServer(uvicorn.Config(app, host=host, port=port, log_level="warning", timeout_graceful_shutdown=2))


def serve(root: Path, host: str, port: int, engine: str = "kokoro", workers: int = 1) -> None:
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}/v1"
    print(f"narrate service at {url}, keeping its data in {root} (Ctrl-C to stop)", flush=True)
    server(create_app(root, engine, workers), host, port).run()
