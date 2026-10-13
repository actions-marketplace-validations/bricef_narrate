# narrate's introduction

A video about narrate, written in narrate. It shows what it describes as it
goes: each scene uses the feature its words are about.

- `intro.md`: the script.
- `scenes/`: its animated HTML scenes, timed to the narration by marks, with
  `common.css` shared between them.
- `overlays/progress.html`: the progress bar along the bottom, an overlay on
  the whole video's clock.
- `media/`: pictures of narrate itself, made by `make_assets.py`:
  - narrate studio with this script open;
  - the contact sheet of a build of this video.

To build it, from a narrate checkout:

```sh
uv run python examples/intro/make_assets.py   # only when the studio or the script has changed
cd examples/intro
narrate check intro.md --timing --tts kokoro
narrate build intro.md --tts kokoro -o /tmp/intro.mp4
```

The overlay and several scenes animate throughout, so they're captured frame
by frame: a build takes several minutes, even with `--tts silent`.
