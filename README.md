# narrate

A local tool that turns a Markdown script and its assets into a narrated video.
It aims to accept the same input format as Narakeet's "Markdown to Video"
service.

Status: specification only; no code yet.

- `docs/spec/narakeet-markdown.md`: the input format. Covers the header,
  scenes, media, narration markup, stage directions, subtitles, slides,
  transitions, the timing model and the outputs. §16 lists the gaps a
  reimplementation has to decide.
- `scripts/fetch-narakeet-reference.sh`: refreshes the local, git-ignored
  snapshot of Narakeet's docs and example scripts in `reference/`. See
  `reference/SOURCES.md`.
