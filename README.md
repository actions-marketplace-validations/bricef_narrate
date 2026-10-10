# narrate

narrate turns a Markdown script and a folder of pictures and clips into a
narrated video, on your own computer. You write the scenes and the words; it
generates the voice-over, lays out the pictures, slides and subtitles, and
times every scene to its narration.

It reads the script format of Narakeet's "Markdown to Video" service, so
Narakeet projects build unchanged, without uploading anything.

- **Speech:** Kokoro, free and running on your computer, or ElevenLabs with
  your own account.
- **Visuals:** pictures with pan and zoom, video clips, text and code slides,
  themes, callouts and 24 kinds of transition.
- **Generated pictures:** Mermaid diagrams, captures of live web pages and
  placeholder cards, written as code blocks in the script (a narrate
  extension).
- **Animated HTML scenes:** web pages animated with CSS or JavaScript, captured
  frame by frame so every build is identical (a narrate extension).
- **Sound and text:** recorded audio, background music, and subtitles, burned
  in or as files.
- **Ways to run it:** a command line, a web studio for writing scripts
  (`narrate studio script.md`), a Docker image and a GitHub Action.

## Install

### With Docker

Docker is the only requirement. The image holds narrate, ffmpeg, Chromium and
fonts:

```sh
docker pull ghcr.io/bricef/narrate
```

While the image is private, log in to `ghcr.io` first
([Build in Docker](docs/building.md#build-in-docker)).

### From source

On Linux (tested on Ubuntu 24.04 and Debian 13), with
[uv](https://docs.astral.sh/uv/getting-started/installation/) installed. The
repository is private, so cloning needs a GitHub account with access to it:

```sh
git clone git@github.com:bricef/narrate.git
cd narrate
uv sync                                          # Python and narrate's packages
uv run playwright install --with-deps chromium   # headless Chromium; asks for sudo for its libraries
sudo apt-get install -y fonts-dejavu-core        # the subtitle font
uv run narrate doctor                            # checks the setup
```

Without sudo, see [Troubleshoot](docs/building.md#troubleshoot) for Chromium's
libraries. narrate downloads its own ffmpeg and the Kokoro voice model on the
first build.

narrate runs inside the checkout's environment. To use it in your own folders,
as the rest of the docs do, add aliases to your shell profile (`~/.bashrc` or
`~/.zshrc`), with the path to your checkout:

```sh
alias narrate='uv run --project ~/path/to/narrate narrate'
alias narakeet-api-client='uv run --project ~/path/to/narrate narakeet-api-client'
```

### Update

- **Docker:** `docker pull ghcr.io/bricef/narrate`.
- **From source:** `git pull && uv sync` in the checkout, then
  `uv run narrate doctor`. If it reports that Chromium is missing, run
  `uv run playwright install chromium` again.

## Make your first video

1. Make a folder with a picture in it, named `photo.jpg`.
2. Save this next to it as `script.md`:

   ````markdown
   ---
   voice: Amy
   subtitles: overlay
   ---

   ![](photo.jpg)

   Hello! This video was made from a short Markdown file.

   ---

   ```md
   # How it works
   * three dashes start a new scene
   * paragraphs are read aloud
   ```

   (pause: 1)
   ````

3. Build it, in that folder:

   ```sh
   narrate build script.md
   ```

   With Docker:

   ```sh
   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" -v narrate-cache:/cache \
       ghcr.io/bricef/narrate build script.md
   ```

   The first build downloads the voice model (about 350 MB).
4. Open `script.mp4`. narrate also wrote `script.jpg`, a poster frame.

For a longer example, build the demo in a checkout:
`uv run narrate build examples/demo/demo.md -o out/demo.mp4`. Its script
shows voices, pauses, slides, a clip with a callout, and code.

## Documentation

- **[Writing scripts](docs/writing-scripts.md):** how to narrate, show
  pictures and clips, add slides, subtitles, music, transitions and callouts.
- **[Building videos](docs/building.md):** speech engines and voices,
  ElevenLabs, Docker, GitHub Actions, Narakeet's command line, caches and
  troubleshooting.
- **[Format specification](docs/spec/narakeet-markdown.md):** every rule and
  default of the script format, and how narrate settles what Narakeet leaves
  open.
- **[Development](docs/development.md):** tests, the container image, CI and
  the code's layout.

## Make videos with an AI agent

[`skills/narrate/`](skills/narrate/SKILL.md) is a skill that teaches AI agents
(Claude Code and others that read the Agent Skills layout) to make videos with
narrate. It covers:
- writing a script from a brief, or from a README, post or outline;
- timing it and pricing its speech before building (`narrate check --timing`);
- reviewing the result as a contact sheet of frames (`narrate frames`);
- animated HTML scenes timed to the narration.

Agents draft with free voices, and ask before spending ElevenLabs credits.
Link it into Claude Code with `just install-skill`. It lives here, so it
changes with the tool; a test checks it covers every stage direction and
header key.

## Status

narrate covers the whole Markdown format: every header property, stage
direction, media option, narration markup, subtitle style and transition.
Built from Narakeet's own example projects, its videos match Narakeet's
renders within 0.1 s in length, for the examples without narration (the voices
themselves differ;
[Development](docs/development.md#conformance-with-narakeet)).

It does not take PowerPoint, Google Slides or Keynote input, or offer
Narakeet's REST API or web editor. It runs on Linux; elsewhere, use Docker.
The image is built for x86-64, so on Apple Silicon Docker runs it under
emulation, more slowly.
