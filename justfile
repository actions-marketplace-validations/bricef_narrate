# Headless Chromium needs its shared libraries. Machines without root keep them
# extracted under ~/.cache/chromium-libs (docs/building.md, Troubleshoot); elsewhere this is empty.
chromium_libs := home_directory() / ".cache/chromium-libs/root/usr/lib/x86_64-linux-gnu"
export LD_LIBRARY_PATH := if path_exists(chromium_libs) == "true" { chromium_libs } else { env("LD_LIBRARY_PATH", "") }

default:
    @just --list

# Run the test suite (add -m "not kokoro" to skip the Kokoro model test)
test *args:
    uv run pytest -q {{args}}

# Render a script: just build examples/demo/demo.md [--tts kokoro|elevenlabs|silent]
build script *args:
    uv run narrate build {{script}} {{args}}

# Edit a script in narrate studio, opened in a browser: just studio examples/demo/demo.md [--tts elevenlabs]
studio script *args:
    uv run narrate studio {{script}} --open {{args}}

# Render the demo with each speech engine into out/
demo:
    mkdir -p out
    uv run narrate build examples/demo/demo.md --tts kokoro -o out/demo-kokoro.mp4
    uv run narrate build examples/demo/demo.md --tts elevenlabs -o out/demo-elevenlabs.mp4

# Build the container image as narrate:local
image:
    docker build -t narrate:local .

# Run the test suite inside the container image
image-test:
    docker build --target test .

# Download the Narakeet reference snapshot (docs, example scripts and their media)
reference:
    ./scripts/fetch-narakeet-reference.sh --media

# Link the narrate skill into ~/.claude/skills, so AI agents on this machine can make videos with narrate
install-skill:
    mkdir -p ~/.claude/skills
    ln -sfn "{{justfile_directory()}}/skills/narrate" ~/.claude/skills/narrate
    @echo "linked ~/.claude/skills/narrate -> {{justfile_directory()}}/skills/narrate"

