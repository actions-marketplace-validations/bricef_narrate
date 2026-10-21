# narrate with everything it needs: Python, headless Chromium, ffmpeg and fonts.
#
#   docker build -t narrate .
#   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" -v narrate-cache:/cache narrate build video.md
#
# The Kokoro model, music and synthesised speech are fetched or made on first
# use under /cache, so a volume there keeps them between runs.
# `docker build --target test .` runs the test suite against the image.

ARG PYTHON=3.12
ARG DEBIAN=trixie
# Docker's official images, from Google's mirror of Docker Hub: no sign-in or pull
# limits, which GitHub's runners keep hitting on Docker Hub itself (429s, 504s from
# auth.docker.io). `--build-arg REGISTRY=docker.io/library` pulls from Docker Hub.
ARG REGISTRY=mirror.gcr.io/library

# ffmpeg with every native decoder, demuxer and filter, but only the external
# libraries narrate uses: x264 (video), libass (burned-in subtitles), rubberband
# (pitch), LAME and Opus (audio exports) and dav1d (AV1 input). Linked against
# Debian's libraries, it is a fraction of the size of a static build.
FROM ${REGISTRY}/debian:${DEBIAN}-slim AS ffmpeg
ARG FFMPEG_VERSION=9.0.2
ARG FFMPEG_SHA256=8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl nasm pkg-config xz-utils \
        libass-dev libdav1d-dev libfontconfig-dev libfreetype-dev libfribidi-dev libharfbuzz-dev \
        libmp3lame-dev libopus-dev librubberband-dev libx264-dev zlib1g-dev
WORKDIR /src
RUN curl -fsSLo ffmpeg.tar.xz "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" \
 && echo "${FFMPEG_SHA256}  ffmpeg.tar.xz" | sha256sum -c - \
 && tar xf ffmpeg.tar.xz --strip-components=1
RUN ./configure --prefix=/opt/ffmpeg --enable-gpl \
        --disable-autodetect --disable-network --disable-doc --disable-debug --disable-ffplay --disable-ffprobe \
        --enable-iconv --enable-zlib --enable-libass --enable-libdav1d --enable-libfontconfig --enable-libfreetype \
        --enable-libfribidi --enable-libharfbuzz --enable-libmp3lame --enable-libopus --enable-librubberband \
        --enable-libx264 \
 && make -j"$(nproc)" && make install
# The Debian packages that provide the libraries ffmpeg links to, for the final image
RUN ldd /opt/ffmpeg/bin/ffmpeg | awk '$3 ~ /^\// {print $3}' | xargs readlink -f | xargs dpkg -S \
        | cut -d: -f1 | sort -u > /opt/ffmpeg/packages

# narrate and its Python dependencies in /opt/narrate, and Playwright's headless Chromium
FROM ${REGISTRY}/python:${PYTHON}-slim-${DEBIAN} AS python
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/narrate
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable
RUN PLAYWRIGHT_BROWSERS_PATH=/opt/playwright /opt/narrate/bin/playwright install --only-shell chromium
# mermaid.js for render:mermaid, checked against narrate's pinned SHA-256
RUN NARRATE_TOOLS=/tmp/tools /opt/narrate/bin/python -c \
        "import shutil; from narrate import mermaid; shutil.copy(mermaid.ensure(), '/opt/mermaid.min.js')"

FROM ${REGISTRY}/python:${PYTHON}-slim-${DEBIAN} AS runtime
# Headless Chromium's libraries (Playwright's list for Debian 13), fonts that
# stand in for Helvetica, Times and Courier, and ffmpeg's libraries.
# libgbm comes without its package: libgbm1 depends on Mesa's GPU drivers
# (LLVM and all, about 200 MB), which libgbm only loads when it opens a GPU,
# and headless Chromium renders in software.
WORKDIR /tmp
RUN --mount=type=bind,from=ffmpeg,source=/opt/ffmpeg/packages,target=/tmp/ffmpeg-packages \
    apt-get update && apt-get install -y --no-install-recommends \
        fontconfig fonts-dejavu-core fonts-liberation fonts-noto-color-emoji \
        libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 libatspi2.0-0t64 libcairo2 libcups2t64 libdbus-1-3 \
        libdrm2 libexpat1 libglib2.0-0t64 libnspr4 libnss3 libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 \
        libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 \
        $(cat /tmp/ffmpeg-packages) \
 && apt-get download libgbm1 \
 && dpkg-deb --fsys-tarfile libgbm1_*.deb | tar -x -C / --wildcards './usr/lib/*/libgbm.so.1*' \
 && rm libgbm1_*.deb && rm -rf /var/lib/apt/lists/*
COPY --from=ffmpeg /opt/ffmpeg/bin/ffmpeg /usr/local/bin/ffmpeg
COPY --from=python /opt/playwright /opt/playwright
COPY --from=python /opt/narrate /opt/narrate
COPY --from=python /opt/mermaid.min.js /opt/mermaid.min.js
# Everything narrate writes at run time goes under /cache (or /tmp), so any
# user id works: pass --user to own the files it writes in /work
ENV PATH=/opt/narrate/bin:$PATH \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    NARRATE_FFMPEG=/usr/local/bin/ffmpeg \
    NARRATE_MERMAID_JS=/opt/mermaid.min.js \
    NARRATE_CACHE=/cache \
    NARRATE_TOOLS=/cache/tools \
    XDG_CACHE_HOME=/cache/xdg \
    HF_HOME=/cache/huggingface
RUN useradd --uid 1000 --create-home narrate && mkdir -m 1777 /cache /work
USER narrate
WORKDIR /work
ENTRYPOINT ["narrate"]
CMD ["--help"]

# The test suite (without the tests that download models or call ElevenLabs)
FROM runtime AS test
USER root
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /bin/uv
COPY pyproject.toml uv.lock /src/
RUN uv export --project /src --frozen --only-group dev --no-hashes > /tmp/dev.txt \
 && uv pip install --python /opt/narrate/bin/python --no-cache -r /tmp/dev.txt
COPY tests /src/tests
COPY skills /src/skills
COPY examples /src/examples
USER narrate
WORKDIR /src
# test_action.py and test_docs.py check the repository's CI files and docs,
# which aren't in the image
RUN python -m pytest -q -p no:cacheprovider --ignore=tests/test_action.py --ignore=tests/test_docs.py \
        -m "not kokoro and not elevenlabs and not conformance and not stt"
