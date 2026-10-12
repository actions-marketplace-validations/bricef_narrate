# narrate as a service

**Status:** decided 2026-10-12 (narrate #23). The first version is an
**internal API**, a building block for your own tools:
- no authentication;
- no hostname of its own: it listens on a port;
- the service's own ElevenLabs key;
- no limits on what it's given.

Every request's cost is recorded, and reported on. Offering it to other
people is separate work ([Later](#later-a-public-service)).

narrate runs on the machine that has it: the CLI, the studio, the Docker image
and the GitHub Action all build locally. The service offers the same
capabilities over HTTP, so other programs can make, check and review videos by
calling it: agents, CI jobs, other apps.

## What it offers

| Capability | narrate today | In the API |
| --- | --- | --- |
| Check a script: problems with their lines, scene lengths, what speech would cost | `narrate check --timing --json` | `POST /v1/check`, answered at once |
| Build a video, or some scenes of it | `narrate build [--scenes]` | a `build` job |
| Narration only | `narrate audio` | an `audio` job |
| Subtitle files, transcript | `--subtitles`, `--transcript` | build options; more outputs |
| Review the frames | `narrate frames` | a `frames` job |
| Hear what was said | `narrate hear --json` | a `hear` job |
| Voices, and hearing one | `narrate voices`, the studio's audition | `GET /v1/voices`, `POST /v1/auditions` |
| Web captures | `render:web`, `--regenerate` | captures returned with the outputs; the `regenerate` option |
| What it cost | — | every job's usage and price; `GET /v1/usage` |

## Principles

- **The CLI is the unit of work.** A job runs `narrate build`, `audio`,
  `frames` or `hear` in a child process, as the studio runs builds (studio
  D6). There's one engine and one behaviour. The service adds transport,
  storage and accounting, not a second renderer.
- **A project is a script plus files, addressed by content.** Files are
  uploaded once, by SHA-256. Rebuilding after an edit uploads only the files
  that changed, just as the speech cache synthesises only the paragraphs that
  changed.
- **Jobs for anything that renders, answers for anything quick.** Builds take
  seconds to minutes, so they're jobs, followed by polling or as a stream of
  events. A check takes well under a second, so it's answered at once.
- **Every request's cost is visible.** A job records what it spent: characters
  sent to ElevenLabs and what they cost, speech served from the cache, compute
  time. It also records the prices used, so a report means the same later.

## Running it

```sh
narrate serve                           # http://127.0.0.1:8788/
narrate serve --host 0.0.0.0 --port 8788 --workers 2 --data /srv/narrate
docker run -p 8788:8788 -v narrate-data:/data -v narrate-cache:/cache \
  -e ELEVENLABS_API_KEY ghcr.io/bricef/narrate serve --host 0.0.0.0 --data /data
```

- **No authentication:** keep it on localhost or a private network. Anything
  that can reach the port can spend the service's ElevenLabs credits.
- **Workers:** how many jobs run at once (default 1). A build uses all its
  machine's cores, so more than one helps only on a big machine. As a guide,
  the factor-q intro (83 s, Kokoro, HTML scenes) built in 57 s.
- **Speech:** jobs use the service's `ELEVENLABS_API_KEY`. The default engine
  is Kokoro, as in the studio (studio D10); a job asks for ElevenLabs with
  `"tts": "elevenlabs"`. The speech and render caches are narrate's usual
  ones, shared by every job.
- **The data folder** holds everything the service keeps:
  - `files/` holds uploaded files by hash;
  - `jobs/<id>/` holds each job's project and outputs;
  - `narrate.db` (SQLite) holds the job records and their usage.

  Nothing expires on its own.

## The API, v1

JSON over HTTP, with an OpenAPI document. Job options are described from the
same definitions as the CLI's flags, so the two can't drift.

| Request | Does |
| --- | --- |
| `POST /v1/files/missing` | `{hashes}`: which of these files the service doesn't have yet |
| `PUT /v1/files/{sha256}` | upload one file; refused if its content doesn't match the hash |
| `POST /v1/check` | `{project, tts}`: problems with their lines, scenes with times, the characters each engine would be sent |
| `POST /v1/jobs` | start a job, `{kind, project, options}`; 202 with the job |
| `GET /v1/jobs` | recent jobs, newest first |
| `GET /v1/jobs/{id}` | the job: state, progress, outputs, notes, errors, usage and cost |
| `GET /v1/jobs/{id}/events` | the job's progress as it happens (server-sent events) |
| `POST /v1/jobs/{id}/cancel` | stop it |
| `GET /v1/jobs/{id}/outputs/{name}` | an output file |
| `GET /v1/voices` | every voice: Kokoro's, ElevenLabs' defaults and Narakeet's names |
| `POST /v1/auditions` | `{voice, text}`: a short sample, read as a script would read it |
| `GET /v1/usage` | usage and cost, by job or by day, as JSON or CSV |

**A project** is a manifest of relative paths and hashes:

```json
{"script": "intro.md",
 "files": {"intro.md": "9f2c…", "team.jpg": "41ab…", "scenes/numbers.html": "c0de…",
           "scenes/common.css": "77e1…"}}
```

- **The whole folder:** a client sends the whole project folder, not only the
  files the script names. HTML scenes load their own CSS, scripts and
  pictures, which narrate's parser can't see.
- **Paths are checked:** no `..`, no absolute paths.
- **Two shortcuts:** a project of just a script can send it inline,
  `{"script": "intro.md", "text": "…"}`; and a ZIP is accepted, as
  `narrate build` accepts one.

**A build job:**

```json
POST /v1/jobs
{"kind": "build",
 "project": {"script": "intro.md", "files": {"intro.md": "9f2c…", "team.jpg": "41ab…"}},
 "options": {"tts": "elevenlabs", "subtitles": "external", "transcript": true, "scenes": "2-3"}}
```

While it runs:

```json
{"id": "j_01J…", "kind": "build", "state": "running",
 "progress": {"scene": 2, "of": 3},
 "outputs": {}, "notes": [], "errors": [], "usage": null}
```

- **When it's done:** `outputs` holds `video`, `poster`, `srt`, `vtt` and
  `transcript`, and `usage` what it spent ([Costs](#costs)).
- **Web captures:** a `render:web` capture taken during the build is an output
  too (`captures/…`). The client can keep it in its project, as committing
  `.narrate/generated/` does locally.
- **States:** `queued`, `running`, `done`, `failed` and `cancelled`.
- **Restarts:** a restart puts running jobs down as failed (interrupted), and
  queued ones go on.

## Costs

A job's usage comes from the CLI itself (#81). `narrate build`, `audio`,
`frames` and `hear` take `--usage FILE`, a JSON report of what the run spent,
which is useful locally too. The service prices it.

```json
"usage": {
  "speech": {"engine": "elevenlabs",
             "models": {"eleven_multilingual_v2": {"characters": 1412, "requests": 9, "cached_characters": 380,
                                                   "credits": 1412.0, "estimated_requests": 0}}},
  "rendered": {"web": 1}, "video_seconds": 83.4, "wall_seconds": 61.2, "cpu_seconds": 402.7,
  "cost": {"currency": "USD", "speech": 0.4236, "compute": 0.0056, "total": 0.4292,
           "prices": {"currency": "USD", "elevenlabs_per_1000_credits": 0.30, "cpu_per_hour": 0.05}}}
```

- **Characters:** those actually sent, in requests that succeeded: the
  ElevenLabs engine counts them as it sends them, phonetic markup included.
- **Credits:** as ElevenLabs bills them (its `character-cost` header). Where
  it doesn't say, they're estimated at the model's rate: half a credit a
  character for flash and turbo, one for the others.
  `estimated_requests` counts the estimated ones.
- **Cached characters:** distinct requests the cache answered. A paragraph
  said twice in one run is sent once, and isn't counted as saved.
- **CPU time:** the command's own, and that of its finished child processes
  (ffmpeg, Chromium).
- **Prices:** set when starting the service (`--prices prices.yaml`), and
  stored with each job. A later change of price doesn't rewrite what earlier
  jobs cost.
- **Reporting:** `GET /v1/usage?since=2026-10-01&by=day` (or `by=job`, and
  `.csv`) gives totals for any period. Usage records are kept indefinitely.
- **Checks:** a check costs nothing, but says what a build would send, so a
  caller can see the price before starting it.

## Isolation

The callers are your own programs, so jobs run as child processes of the
service, as the studio's builds do. To contain the service as a whole, run it
from the Docker image. A public service would need much more: each job in its
own container, behind an egress proxy ([Later](#later-a-public-service)).

## Narakeet compatibility

Not planned. Narakeet's flow maps onto this API, so a small adapter could be
added if it's ever wanted:
- the upload request and the ZIP upload become a ZIP project;
- `POST /video/build` becomes a build job;
- the status document is a view of the job.

## Later: a public service

Separate work, sketched here so the internal version doesn't close it off:

- **Keys:** bearer tokens, scoped, stored hashed, each with limits:
  concurrent jobs, minutes per day, longest video, largest project.
- **Isolation:** every job in its own container (not root, read-only image,
  scratch on tmpfs). The only way out is an egress proxy that refuses
  private, link-local and metadata addresses, so `render:web` can't reach
  internal services. For untrusted users, gVisor or a microVM per job.
- **Captured pages:** only project files may load, enforced in `pages.py`.
- **Paying for speech:** keys brought per job, or the service's key with
  quotas per user.
- **Running it bigger:** Postgres for the queue, an object store (R2) for
  files and outputs, retention rules, signed URLs, webhooks and idempotency
  keys.
- **Clients:** `narrate remote` (the CLI's commands, run by the service), a
  `service-url` input for the GitHub Action, and an MCP server for agents.
