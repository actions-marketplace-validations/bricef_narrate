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

[Unreleased]: https://github.com/bricef/narrate/commits/main
