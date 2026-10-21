# Changelog

Notable changes to narrate, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

This file starts here, before narrate's first release. Earlier changes are in
the git history.

### Added

- **Scripts:** builds narrated videos from Narakeet's "Markdown to Video"
  script format: narration, pictures with pan and zoom, video clips, text and
  code slides, themes, callouts, transitions, recorded audio, background music
  and subtitles.
- **Speech:** Kokoro, free and running locally, or ElevenLabs with your own
  key.
- **narrate's extensions:** Mermaid diagrams, web page captures and
  placeholder cards as code blocks; animated HTML scenes; and HTML overlays.
- **Checking and reviewing:** `narrate check` reports problems, timing and
  what speech would cost; `narrate frames` and `narrate hear` review a built
  video without watching it.
- **Ways to run it:** the command line, `narrate studio` for writing scripts in
  a browser, `narrate serve` for your own programs over HTTP,
  `narakeet-api-client` for Narakeet's command line, a Docker image and a
  GitHub Action.
- **An agent skill** (`skills/narrate/`) that teaches AI agents to make videos
  with narrate.

### Security

- **The studio and the service keep web pages out:** they answer only to
  `localhost`, `127.0.0.1`, `[::1]` and their `--host` address, and refuse
  changes sent from another site's page. A page open in your browser can no
  longer read your project or start builds through them.
- **`--allow-host`:** `narrate studio` and `narrate serve` answer to more host
  names with it. A service on `0.0.0.0` whose clients call it by its
  machine's name or address needs it.
- **Captured pages reach only public addresses:** `render:web` pages, HTML
  scenes, overlays and slides, and everything they load, can't reach this
  machine, a private network or a link-local address, such as a studio, a
  service, a router or a cloud's metadata address. A host name that resolves
  to a local address is refused too. A refused `render:web` capture stops the
  build, naming the address; anything else refused is noted.
- **`--allow-local-network`:** `narrate build` lets pages reach local
  addresses with it, or with `NARRATE_ALLOW_LOCAL_NETWORK=1`, to capture your
  own dev server. `narrate serve` takes it for all its build jobs; a job can't
  turn it on itself.
- **The studio's preview sandboxes a project's pages:** HTML scenes, overlays
  and slides run in origins of their own. A page in a project from someone
  else can no longer save over the script, switch the engine, start builds or
  read what the studio answers. Its own files still load as in a build, but it
  has no storage, such as `localStorage`.
- **No framing by other sites:** the studio and the service send
  `frame-ancestors 'self'` and `X-Frame-Options`. Project files and the
  service's outputs are served sandboxed.

[Unreleased]: https://github.com/bricef/narrate/commits/main
