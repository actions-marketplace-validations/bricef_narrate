"""The service's OpenAPI document (#79), served at /v1/openapi.json.

Written out here rather than generated from the routes, which are few. The
jobs' options come from options.OPTIONS, the table the service itself checks
requests against.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from . import options

_ERROR = {"description": "the request can't be met; `error` says why",
          "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}}


def _json(schema: dict, description: str = "") -> dict:
    return {"description": description, "content": {"application/json": {"schema": schema}}}


def _ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def _version() -> str:
    try:
        return version("narrate")
    except PackageNotFoundError:
        return "0"


def document() -> dict:
    job_id = {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}
    sha = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    return {
        "openapi": "3.1.0",
        "info": {"title": "narrate", "version": _version(),
                 "description": "narrate's capabilities over HTTP, for your own programs: no authentication. "
                                "See docs/design/service.md."},
        "paths": {
            "/v1/files/missing": {"post": {
                "summary": "Which of these files the service doesn't have yet",
                "requestBody": {"content": {"application/json": {"schema": {
                    "type": "object", "required": ["hashes"],
                    "properties": {"hashes": {"type": "array", "items": sha}}}}}},
                "responses": {"200": _json({"type": "object", "properties": {"missing": {"type": "array", "items": sha}}},
                                           "the hashes to upload"), "400": _ERROR}}},
            "/v1/files/{sha256}": {"put": {
                "summary": "Upload one file; refused if its content doesn't have this SHA-256",
                "parameters": [{"name": "sha256", "in": "path", "required": True, "schema": sha}],
                "requestBody": {"content": {"application/octet-stream": {"schema": {"type": "string",
                                                                                    "format": "binary"}}}},
                "responses": {"201": {"description": "kept"}, "200": {"description": "already kept"},
                              "400": _ERROR}}},
            "/v1/check": {"post": {
                "summary": "Check a project: problems with their lines, scenes with times, what speech would cost",
                "requestBody": {"content": {"application/json": {"schema": {
                    "type": "object", "required": ["project"],
                    "properties": {"project": _ref("Project"), "tts": {"type": "string", "enum": list(options.ENGINES)},
                                   "tts_model": {"type": "string"}}}}}},
                "responses": {"200": _json(_ref("Check")), "400": _ERROR}}},
            "/v1/voices": {"get": {
                "summary": "Every voice, grouped, with what each becomes on an engine",
                "parameters": [{"name": "tts", "in": "query", "schema": {"type": "string", "enum": list(options.ENGINES)}}],
                "responses": {"200": _json({"type": "object"})}}},
            "/v1/auditions": {"post": {
                "summary": "Hear a voice: a short sample, read as a script would read it (an audio job)",
                "requestBody": {"content": {"application/json": {"schema": {
                    "type": "object", "required": ["voice"],
                    "properties": {"voice": {"type": "string"}, "text": {"type": "string"},
                                   "tts": {"type": "string", "enum": list(options.ENGINES)}}}}}},
                "responses": {"200": _json(_ref("Job"), "done: its audio is an output"),
                              "202": _json(_ref("Job"), "still running"), "400": _ERROR}}},
            "/v1/jobs": {
                "post": {"summary": "Start a job: build a video or narration, or review one (frames, hear)",
                         "requestBody": {"content": {"application/json": {"schema": _ref("JobRequest")}}},
                         "responses": {"202": _json(_ref("Job"), "queued"), "400": _ERROR}},
                "get": {"summary": "Recent jobs, newest first",
                        "parameters": [{"name": "limit", "in": "query", "schema": {"type": "integer", "default": 50}},
                                       {"name": "state", "in": "query", "schema": _ref("State")}],
                        "responses": {"200": _json({"type": "object", "properties": {
                            "jobs": {"type": "array", "items": _ref("Job")}}})}}},
            "/v1/jobs/{id}": {"get": {"summary": "A job", "parameters": [job_id],
                                      "responses": {"200": _json(_ref("Job")), "404": _ERROR}}},
            "/v1/jobs/{id}/events": {"get": {
                "summary": "A job as it changes: server-sent `job` events, ending when it does",
                "parameters": [job_id],
                "responses": {"200": {"description": "an event stream",
                                      "content": {"text/event-stream": {"schema": {"type": "string"}}}}}}},
            "/v1/jobs/{id}/cancel": {"post": {"summary": "Stop a job", "parameters": [job_id],
                                              "responses": {"200": _json(_ref("Job")), "404": _ERROR}}},
            "/v1/jobs/{id}/outputs/{name}": {"get": {
                "summary": "One of a job's outputs, by the name in its address",
                "parameters": [job_id, {"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}],
                "responses": {"200": {"description": "the file"}, "404": _ERROR}}},
        },
        "components": {"schemas": {
            "Error": {"type": "object", "properties": {
                "error": {"type": "string"},
                "missing": {"type": "array", "items": sha, "description": "files to upload first"}}},
            "State": {"type": "string", "enum": ["queued", "running", "done", "failed", "cancelled"]},
            "Project": {"oneOf": [
                {"type": "object", "required": ["script"], "description": "files by content, a script sent inline, "
                                                                           "or both",
                 "properties": {"script": {"type": "string", "description": "the script's path in the project"},
                                "files": {"type": "object", "additionalProperties": sha,
                                          "description": "every file of the project folder, by relative path"},
                                "text": {"type": "string", "description": "the script itself"}}},
                {"type": "object", "required": ["zip"], "description": "an uploaded ZIP",
                 "properties": {"zip": sha, "source": {"type": "string",
                                                       "description": "the script inside it, if it has several"}}}]},
            "JobRequest": {"oneOf": [
                *({"type": "object", "required": ["kind", "project"], "title": kind,
                   "properties": {"kind": {"const": kind}, "project": _ref("Project"), "options": options.schema(kind)}}
                  for kind in options.RENDERS),
                *({"type": "object", "required": ["kind", "media"], "title": kind,
                   "properties": {"kind": {"const": kind}, "media": _ref("Media"),
                                  "project": {**_ref("Project"), "description": "a script to compare with, if "
                                                                                "media isn't a job's"},
                                  "options": options.schema(kind)}}
                  for kind in options.REVIEWS)]},
            "Media": {"oneOf": [
                {"type": "object", "required": ["job"], "description": "what a finished build or audio job made; "
                                                                       "its script and engine come with it",
                 "properties": {"job": {"type": "string"}}},
                {"type": "object", "required": ["file"], "description": "an uploaded video or audio file",
                 "properties": {"file": sha, "name": {"type": "string"}}}]},
            "Check": {"type": "object", "description": "what `narrate check --timing --json` reports",
                      "properties": {"problems": {"type": "array", "items": {"type": "object"}},
                                     "scenes": {"type": "array", "items": {"type": "object"}},
                                     "duration": {"type": ["number", "null"]},
                                     "missing": {"type": ["object", "null"],
                                                 "description": "paragraphs and characters the engine would be sent"},
                                     "engine": {"type": "string"}}},
            "Job": {"type": "object", "properties": {
                "id": {"type": "string"}, "kind": {"type": "string", "enum": list(options.KINDS)},
                "state": _ref("State"),
                "created": {"type": "string", "format": "date-time"},
                "started": {"type": ["string", "null"], "format": "date-time"},
                "finished": {"type": ["string", "null"], "format": "date-time"},
                "request": {"type": "object", "description": "the project and options asked for"},
                "progress": {"type": ["object", "null"], "properties": {
                    "scene": {"type": ["integer", "null"]}, "of": {"type": ["integer", "null"]},
                    "message": {"type": "string"}}},
                "outputs": {"type": "object", "description": "addresses by name: video, audio, poster, srt, vtt, "
                                                             "transcript; captures by their path in the project"},
                "notes": {"type": "array", "items": {"type": "string"}},
                "errors": {"type": "array", "items": {"type": "object", "properties": {
                    "line": {"type": ["integer", "null"]}, "message": {"type": "string"}}}},
                "summary": {"type": "string"},
                "usage": {"type": ["object", "null"]}}},
        }},
    }
