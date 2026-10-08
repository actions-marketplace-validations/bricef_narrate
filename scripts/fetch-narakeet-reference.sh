#!/usr/bin/env bash
# Refresh the git-ignored Narakeet reference snapshot that
# docs/spec/narakeet-markdown.md was written from:
#   reference/narakeet-docs/  doc pages and news posts, converted to Markdown
#   reference/examples/       scripts and CSS from github.com/narakeet/examples
#                             (--media also fetches their media and Narakeet's rendered result.mp4, ~136 MB)
# Neither source is licensed for redistribution, so the snapshot stays local.
set -euo pipefail

with_media=0
[[ "${1:-}" == "--media" ]] && with_media=1

root="$(cd "$(dirname "$0")/.." && pwd)"
ref="$root/reference"
html="$(mktemp -d)"
trap 'rm -rf "$html"' EXIT

docs=(
  docs/ docs/script/ docs/format/ docs/background-music/ docs/best-size-for-video/
  docs/narration-styles/ docs/improve-video-visuals/ docs/add-subtitles-to-video/
  docs/add-voice-to-video/ docs/text-to-voice-over/ docs/faq/ docs/presentation-resizing/
  docs/pricing/
  docs/scripting/designing-callouts.html docs/scripting/pan-zoom-image-animations.html
  docs/scripting/subtitle-font-size-color.html
  docs/how-to/add-pauses-to-text-to-speech-voiceovers.html
  docs/how-to/change-text-to-speech-reading-speed.html docs/how-to/control-pronunciation.html
  docs/how-to/control-voice-pitch.html docs/how-to/create-closed-captions-and-subtitles.html
  docs/how-to/create-multilingual-content.html docs/how-to/normalize-voiceover.html
  docs/how-to/optimize-video-compression.html docs/how-to/pause-voiceover-narration.html
  docs/how-to/use-multiple-voices-in-text-to-speech.html docs/how-to/use-pinyin-phonemes.html
  docs/how-to/use-your-own-voice.html docs/how-to/voiceover-dialog-video.html
  docs/how-to/voice-over-video-language.html docs/how-to/estimate-text-to-speech-duration.html
  docs/how-to/convert-subtitles-to-audio.html docs/how-to/presentation-transitions.html
  docs/how-to/kenburns-powerpoint.html docs/howto/text-to-speech-video-maker.html
  docs/automating/ docs/automating/cli/ docs/automating/cli/video/ docs/automating/video-api/
  docs/automating/github/ docs/automating/listing-voices-api/
  news/2020/09/15/narration-mode.html news/2020/12/08/russian-stress-voices.html
  news/2021/03/16/new-video-transitions.html news/2022/05/12/easier-slideshows.html
  news/2023/01/09/create-video-poster-images.html
  news/2023/05/10/synchronize-text-to-speech-with-timecodes-pause-until.html
  news/2023/07/22/tiktok-style-captions.html news/2024/05/28/easier-inline-pauses.html
  news/2026/04/14/new-robotic-alien-voices.html
)

for p in "${docs[@]}"; do
  name="$(echo "${p%/}" | sed -e 's#\.html$##' -e 's#/#__#g')"
  curl -sSfL -o "$html/$name.html" "https://www.narakeet.com/$p"
done
rm -rf "$ref/narakeet-docs"
uv run -q --no-project --with markdownify --with beautifulsoup4 \
  python -I "$root/scripts/narakeet_html_to_md.py" "$html" "$ref/narakeet-docs" >/dev/null

rm -rf "$ref/examples"
gh api 'repos/narakeet/examples/git/trees/master?recursive=1' \
  --jq '.tree[] | select(.type=="blob") | .path' |
  if ((with_media)); then
    # Everything but repo furniture, including each project's result.mp4: the
    # video Narakeet rendered from that script, a reference to compare against
    grep -v -E '(^|/)(README\.md|\.gitignore|\.github/|credits/)'
  else
    grep -E '(script/[^/]+\.(md|txt|css)|/video\.md|/theme\.css)$' | grep -v '/credits/'
  fi |
  while read -r p; do
    mkdir -p "$ref/examples/$(dirname "$p")"
    curl -sSf -o "$ref/examples/$p" "https://raw.githubusercontent.com/narakeet/examples/master/$p"
  done

echo "docs: $(ls "$ref/narakeet-docs" | wc -l) pages, examples: $(find "$ref/examples" -type f | wc -l) files"
