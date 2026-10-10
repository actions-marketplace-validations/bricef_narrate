"""Contact sheets (#67): a built video's frames side by side, for reviewing it without watching it.

An LLM agent can't play a video, but it can look at a picture: one frame per
scene, labelled with its time and scene, shows layout, framing, slides,
callouts and subtitles at a glance. Frames come from narrate's own ffmpeg, so
this works wherever narrate does.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import media
from .doctor import find_font

COLUMNS = 4
LABEL_HEIGHT = 24


def evenly(duration: float, count: int) -> list[float]:
    """`count` moments spread across the video, each in the middle of its share."""
    return [duration * (k + 0.5) / count for k in range(count)]


def every(duration: float, seconds: float) -> list[float]:
    """A moment in the middle of each `seconds` of the video."""
    count = max(1, math.ceil(duration / seconds))
    return [min(duration, (k + 0.5) * seconds) for k in range(count)]


def clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def contact_sheet(video: Path, moments: list[tuple[float, str]], out: Path, width: int = 480) -> Path:
    """The frames at `moments` (time, label) in a grid, each `width` wide and labelled, written to `out`."""
    duration = media.probe(video).duration
    font_path = find_font("DejaVuSans.ttf")
    font = ImageFont.truetype(str(font_path), 14) if font_path else ImageFont.load_default()
    cells: list[Image.Image] = []
    with tempfile.TemporaryDirectory(prefix="narrate-frames-") as tmp:
        for k, (at, label) in enumerate(moments):
            png = media.extract_frame(video, min(max(0.0, at), max(0.0, duration - 1 / 30)), Path(tmp) / f"{k}.png")
            with Image.open(png) as im:
                frame = im.convert("RGB")
            frame = frame.resize((width, max(1, round(frame.height * width / frame.width))), Image.LANCZOS)
            cell = Image.new("RGB", (width, frame.height + LABEL_HEIGHT), (24, 26, 30))
            cell.paste(frame, (0, 0))
            ImageDraw.Draw(cell).text((8, frame.height + 4), f"{clock(at)}  {label}".strip(), fill=(230, 230, 230),
                                      font=font)
            cells.append(cell)
    columns = min(COLUMNS, len(cells))
    rows = math.ceil(len(cells) / columns)
    cw, ch = cells[0].size
    sheet = Image.new("RGB", (columns * cw + (columns - 1) * 4, rows * ch + (rows - 1) * 4), (0, 0, 0))
    for k, cell in enumerate(cells):
        sheet.paste(cell, ((k % columns) * (cw + 4), (k // columns) * (ch + 4)))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


# -- hearing it (#70) ----------------------------------------------------------------------
#
# A reviewer who can't listen can still read what speech-to-text hears. `hear` lines the heard
# words up with the script's narration and reports only where they differ, leniently: case and
# punctuation don't count, a word heard joined or split still matches ("QuietTube" for
# "quietube"), and numbers match their spoken form ("531" and "five hundred and thirty-one").

import difflib  # noqa: E402
import re  # noqa: E402
from dataclasses import dataclass  # noqa: E402

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
        "seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> list[str]:
    """An integer as spoken words, without "and": 531 -> five hundred thirty one."""
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    for size, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand"), (100, "hundred")):
        if n >= size:
            head, rest = divmod(n, size)
            return number_words(head) + [name] + (number_words(rest) if rest else [])
    return [str(n)]


def tokens(word: str) -> list[str]:
    """A written or heard word as comparable tokens: lower case, no punctuation, numbers as words."""
    text = word.lower().replace("%", " percent ").replace("&", " and ")
    out: list[str] = []
    for part in re.findall(r"[\d][\d,]*(?:\.\d+)?|[^\W\d_]+(?:['’][^\W\d_]+)?", text):
        if part[0].isdigit():
            whole, _, fraction = part.replace(",", "").partition(".")
            out += number_words(int(whole)) if len(whole) < 10 else [whole]
            if fraction:
                out += ["point"] + [_ONES[int(d)] for d in fraction]
        else:
            out.append(part.replace("’", "'"))
    return [t for t in out if t != "and"]  # "five hundred and thirty-one" says no more than "531"


@dataclass
class Word:
    text: str  # as written or heard
    tokens: list[str]
    where: tuple[int, int] | None = None  # (scene, line) for a written word
    at: float | None = None  # seconds into the media, for a heard word
    paragraph: list[str] | None = None  # a written word's paragraph, word by word, to quote from
    pos: int = 0  # its place in that paragraph


def written_words(script: Path) -> list[Word]:
    """The script's narration, word by word, with the scene and line each comes from."""
    from .script import Narration, parse_file
    from .text import ssml_text, subtitle_text

    words = []
    for scene in parse_file(script).scenes:
        for block in scene.blocks:
            if isinstance(block, Narration):
                text = subtitle_text(ssml_text(block.text) if block.ssml else block.text).split()
                words += [Word(w, tokens(w), where=(scene.index, block.line), paragraph=text, pos=k)
                          for k, w in enumerate(text)]
    return [w for w in words if w.tokens]


def heard_words(media_path: Path, language: str | None = None) -> list[Word]:
    from . import stt

    raw: list[tuple[float, str]] = []
    for phrase in stt.transcribe(media_path, language):
        for start, _, w in phrase:
            # Speech-to-text sometimes splits a number at its separator: "1 ,000" is 1,000
            if raw and re.match(r"^[,.]\d", w) and raw[-1][1][-1:].isdigit():
                raw[-1] = (raw[-1][0], raw[-1][1] + w)
            else:
                raw.append((start, w))
    return [Word(w, tokens(w), at=start) for start, w in raw if tokens(w)]


def _join(words: list[Word]) -> str:
    return "".join(t for w in words for t in w.tokens)


def _same(written: list[Word], heard: list[Word]) -> bool:
    """The same words, joined or split differently, or spelled almost alike ("QuietTube" for "quietube")."""
    a, b = _join(written), _join(heard)
    return a == b or (min(len(a), len(b)) >= 5 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.85)


def compare(written: list[Word], heard: list[Word]) -> dict:
    """Where the heard words differ from the written ones: a list of differences, and a summary.

    Tokens are aligned first; then each written word is judged whole: it was heard as written
    if all its tokens lined up. Neighbouring differences are reported together."""
    a = [(i, t) for i, w in enumerate(written) for t in w.tokens]
    b = [(i, t) for i, w in enumerate(heard) for t in w.tokens]
    matcher = difflib.SequenceMatcher(None, [t for _, t in a], [t for _, t in b], autojunk=False)
    exact: set[int] = set()  # a-token positions that lined up exactly
    heard_for: dict[int, set[int]] = {}  # written word -> heard words aligned with its tokens
    used: set[int] = set()  # heard words aligned with some written word
    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        if op == "equal":
            for k in range(a1 - a0):
                exact.add(a0 + k)
                heard_for.setdefault(a[a0 + k][0], set()).add(b[b0 + k][0])
                used.add(b[b0 + k][0])
        elif op == "replace":
            words = {b[k][0] for k in range(b0, b1)}
            for k in range(a0, a1):
                heard_for.setdefault(a[k][0], set()).update(words)
            used.update(words)
    wrong = {i for i, w in enumerate(written)
             if not all(k in exact for k, (j, _) in enumerate(a) if j == i)}
    # Each word on its own first ("today" heard as "to day"), so a fine word doesn't dilute a wrong one
    wrong = {i for i in wrong if not (heard_for.get(i) and _same([written[i]], [heard[k] for k in sorted(heard_for[i])]))}
    differences = []
    i = 0
    while i < len(written):
        if i not in wrong:
            i += 1
            continue
        group = [i]
        while group[-1] + 1 in wrong:
            group.append(group[-1] + 1)
        i = group[-1] + 1
        hs = sorted(set().union(*(heard_for.get(k, set()) for k in group)))
        ws, said = [written[k] for k in group], [heard[k] for k in hs]
        if said and _same(ws, said):
            wrong -= set(group)
            continue
        # Quote the script itself, words without tokens ("and") included
        wrote = " ".join(ws[0].paragraph[ws[0].pos:ws[-1].pos + 1]) if ws[0].paragraph is ws[-1].paragraph \
            else " ".join(w.text for w in ws)
        differences.append({"kind": "different" if said else "not heard", "wrote": wrote,
                            "heard": " ".join(h.text for h in said), "scene": ws[0].where[0], "line": ws[0].where[1],
                            "at": said[0].at if said else None})
    # Heard words that line up with nothing written: a recording, or noise
    extra = [k for k in range(len(heard)) if k not in used]
    while extra:
        run = [extra.pop(0)]
        while extra and extra[0] == run[-1] + 1:
            run.append(extra.pop(0))
        differences.append({"kind": "not in the script", "wrote": "", "heard": " ".join(heard[k].text for k in run),
                            "scene": None, "line": None, "at": heard[run[0]].at})
    differences.sort(key=lambda d: (d["at"] if d["at"] is not None else float("inf")))
    return {"words": len(written), "heard_as_written": len(written) - len(wrong), "differences": differences}
