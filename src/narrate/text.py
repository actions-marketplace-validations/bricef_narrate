"""Turn narration markup (spec §6.2) into speakable text and subtitle text."""

from __future__ import annotations

import re
from dataclasses import dataclass

ELLIPSIS_PAUSE = 0.5
SENTENCE_PAUSE = 0.25  # between runs split by emphasis, after a sentence ends
JOIN_PAUSE = 0.06  # between runs split mid-sentence

_SPAN_RE = re.compile(r"\[([^\]]+)\]\{([^}]+)\}")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_CODE_RE = re.compile(r"`([^`]+)`")
_EMPHASIS_RES = [
    re.compile(r"\*\*(.+?)\*\*"),
    re.compile(r"(?<!\w)__(.+?)__(?!\w)"),
    re.compile(r"~~(.+?)~~"),
    re.compile(r"\*(.+?)\*"),
    re.compile(r"(?<!\w)_(.+?)_(?!\w)"),
]
_TAG_RE = re.compile(r"<[^>]+>")
# Outermost emphasis, longest delimiters first: ** __ ~~ then * _
_EMPHASIS_RE = re.compile(
    r"\*\*(?P<strong>.+?)\*\*|(?<!\w)__(?P<strong2>.+?)__(?!\w)|~~(?P<reduced>.+?)~~"
    r"|\*(?P<moderate>.+?)\*|(?<!\w)_(?P<moderate2>.+?)_(?!\w)"
)
_ELLIPSIS_RE = re.compile(r"…|\.{3}")

_LETTERS = {
    "a": "ay", "b": "bee", "c": "see", "d": "dee", "e": "ee", "f": "eff", "g": "jee",
    "h": "aitch", "i": "eye", "j": "jay", "k": "kay", "l": "el", "m": "em", "n": "en",
    "o": "oh", "p": "pee", "q": "cue", "r": "ar", "s": "ess", "t": "tee", "u": "you",
    "v": "vee", "w": "double you", "x": "ex", "y": "why", "z": "zee",
}
_SYMBOLS = {
    "?": "question mark", "!": "exclamation mark", ".": "dot", ",": "comma",
    "-": "dash", "_": "underscore", "/": "slash", "\\": "backslash", ":": "colon",
    ";": "semicolon", "@": "at", "#": "hash", "&": "ampersand", "+": "plus",
    "=": "equals", "*": "star", "%": "percent", "$": "dollar", "'": "apostrophe",
    '"': "quote", "(": "open bracket", ")": "close bracket",
}


def spell(text: str, lang: str) -> str:
    """Letter-by-letter reading; letter names are English-only for now."""
    if not lang.startswith("en"):
        return ", ".join(ch for ch in text if not ch.isspace())
    words = []
    for ch in text:
        low = ch.lower()
        if ch.isspace():
            continue
        words.append(_LETTERS.get(low) or _SYMBOLS.get(ch) or ch)
    return ", ".join(words)


def _strip_emphasis(text: str) -> str:
    for pattern in _EMPHASIS_RES:
        text = pattern.sub(r"\1", text)
    return text


@dataclass
class Run:
    """A stretch of narration synthesised in one call."""

    text: str
    emphasis: str = "none"  # none | moderate | strong | reduced
    pause: float = 0.0  # silence before it


def speech_runs(text: str, lang: str, notes: set[str]) -> list[Run]:
    """Speakable runs of one narration paragraph.

    Emphasis markup (`*x*`/`_x_` moderate, `**x**`/`__x__` strong, `~~x~~`
    reduced) and inline pauses (an ellipsis) split the paragraph; each run is
    synthesised separately. `notes` collects markup that was approximated.
    """

    def span(m: re.Match[str]) -> str:
        inner, opts = m.group(1), m.group(2).strip().lower()
        if opts == "literal":
            return spell(inner, lang)
        if opts != "normal":
            notes.add(f"narration span {{{opts}}} (read as plain text)")
        return inner

    text = _SPAN_RE.sub(span, text)
    text = _LINK_RE.sub(r"\1", text)
    text = _CODE_RE.sub(lambda m: spell(m.group(1), lang), text)

    pieces: list[tuple[str, str]] = []
    at = 0
    for m in _EMPHASIS_RE.finditer(text):
        pieces.append((text[at:m.start()], "none"))
        kind = next(k for k, v in m.groupdict().items() if v is not None)
        pieces.append((_strip_emphasis(m.group(kind)), kind.rstrip("2")))
        at = m.end()
    pieces.append((text[at:], "none"))

    runs: list[Run] = []
    for chunk, emphasis in pieces:
        for i, part in enumerate(_ELLIPSIS_RE.split(_TAG_RE.sub(" ", chunk).replace("^", ""))):
            part = " ".join(part.split())
            if not any(ch.isalnum() for ch in part):
                continue
            if i:
                pause = ELLIPSIS_PAUSE
            elif runs:
                pause = SENTENCE_PAUSE if runs[-1].text.rstrip()[-1:] in ".!?:;" else JOIN_PAUSE
            else:
                pause = 0.0
            runs.append(Run(part, emphasis, pause))
    return runs


def ssml_text(ssml: str) -> str:
    return " ".join(_TAG_RE.sub(" ", ssml).split())


def subtitle_text(text: str) -> str:
    text = _SPAN_RE.sub(r"\1", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _CODE_RE.sub(r"\1", text)
    text = _TAG_RE.sub(" ", _strip_emphasis(text)).replace("^", "")
    return " ".join(text.split())
