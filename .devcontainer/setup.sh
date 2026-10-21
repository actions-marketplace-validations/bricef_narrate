#!/usr/bin/env bash
# Sets up a new dev container: uv and just, then the README's install from
# source. It runs once, after the container is created.
set -euo pipefail

# Docker creates the cache volume as root: hand it to the container's user
sudo chown "$(id -u):$(id -g)" ~/.cache ~/.cache/narrate

pipx install uv
sudo apt-get update
sudo apt-get install -y --no-install-recommends just fonts-dejavu-core

uv sync                                          # Python and narrate's packages
uv run playwright install --with-deps chromium   # headless Chromium and its libraries
uv run narrate doctor                            # checks the setup
