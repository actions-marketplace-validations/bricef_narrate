"""Turn narration markup (spec §6.2) into speakable text and subtitle text."""

from __future__ import annotations

import re

ELLIPSIS_PAUSE = 0.5

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


def speech_parts(text: str, lang: str, notes: set[str]) -> list[str]:
    """Speakable chunks of one narration paragraph; an inline pause separates each chunk.

    `notes` collects the names of markup features that were approximated, so the
    caller can warn once per feature.
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
    stripped = _strip_emphasis(text)
    if stripped != text:
        notes.add("emphasis markup (read without emphasis)")
    text = _TAG_RE.sub(" ", stripped).replace("^", "")
    parts = [" ".join(p.split()) for p in _ELLIPSIS_RE.split(text)]
    return [p for p in parts if any(ch.isalnum() for ch in p)]


def ssml_text(ssml: str) -> str:
    return " ".join(_TAG_RE.sub(" ", ssml).split())


def subtitle_text(text: str) -> str:
    text = _SPAN_RE.sub(r"\1", text)
    text = _LINK_RE.sub(r"\1", text)
    text = _CODE_RE.sub(r"\1", text)
    text = _TAG_RE.sub(" ", _strip_emphasis(text)).replace("^", "")
    return " ".join(text.split())
