# quietube

A quiet, curated, ad-free web interface over your YouTube subscriptions.
No recommendation engine, no feed algorithm, no shorts, no comments, no ads —
just a strictly reverse-chronological list of recent videos from the channels
*you* choose, played in a self-hosted HTML5 player.

## How it works

- **Channels** are a hand-curated list. Import them once by running a console
  script on YouTube (no OAuth, no API key, no quota).
- **Video listing** comes from `yt-dlp`'s long-form *Videos* tab (durations +
  automatic shorts exclusion). Exact publish dates come from the **YouTube Data
  API** (a public, key-only call — no OAuth) so the feed interleaves correctly
  by date. Without a key, dates fall back to each channel's RSS feed (accurate
  but only the latest ~15 uploads), and if `yt-dlp` is blocked, RSS keeps the
  feed alive.
- **Playback** resolves a progressive stream with `yt-dlp` and proxies it
  through the backend, so the browser never talks to YouTube and sees no ads.

## Quick start (local)

```bash
cd quietube
uv venv && uv pip install -e .
uv run uvicorn quietube.main:app --reload
# open http://localhost:8000
```

### 1. Import your subscriptions

1. Open <https://www.youtube.com/feed/channels> while logged in.
2. Open the DevTools console and paste `scripts/scrape_subscriptions.js`.
3. It auto-scrolls, collects every subscription, and copies JSON to your
   clipboard.
4. In quietube, go to **Channels → Import from clipboard JSON**, paste, Import.

(You can also add single channels by URL/handle on the Channels page.)

### 2. (Recommended) Add a YouTube Data API key

For the feed to sort correctly by *upload date* (not fetch order), set a free,
public API key — no OAuth, no billing:

1. <https://console.cloud.google.com/> → create/select a project.
2. **APIs & Services → Enable APIs → "YouTube Data API v3"**.
3. **Credentials → Create credentials → API key** (then "Restrict key" to the
   YouTube Data API).
4. Put it in your env: `QUIETUBE_YT_API_KEY=...`

Quota is 10,000 units/day; a full refresh costs ~1 unit per 50 videos, so even
hourly refreshes of hundreds of channels stay well under the limit. Without a
key, dates fall back to RSS (only each channel's latest ~15 uploads have dates).

### 3. Refresh

Hit **Refresh feed** on the Channels page (or wait for the background
scheduler). Then open the **Feed**.

## Deploy

```bash
cp .env.example .env       # set QUIETUBE_PASSWORD at minimum
docker compose up -d --build
```

### ⚠️ Datacenter IPs get bot-checked

YouTube aggressively challenges requests from datacenter IPs (the kind your VPS
has). Without cookies you'll likely see *"Sign in to confirm you're not a bot."*
Fix: export a `cookies.txt` (Netscape format) from a logged-in browser session
(e.g. the "Get cookies.txt" extension), mount it into the container, and set
`QUIETUBE_COOKIES=/cookies.txt`. See the commented volume in `docker-compose.yml`.

## Configuration

All via env vars — see `.env.example`.

## Known limitations / roadmap

- **Playback quality** is capped at progressive formats (≤720p, single muxed
  stream). Higher quality needs separate audio/video via DASH/MSE
  (dash.js/shaka) or server-side `ffmpeg` muxing — planned.
- `yt-dlp` breaks when YouTube changes things; keep it updated
  (`uv pip install -U yt-dlp`).
- Single-user only. Multi-user accounts are out of scope.
- Using this against YouTube's interests may violate their Terms of Service;
  it's intended for personal use.
```
