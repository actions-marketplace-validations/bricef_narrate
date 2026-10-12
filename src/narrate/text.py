"""Turn narration markup (spec §6.2) into speakable text and subtitle text."""

from __future__ import annotations

import re
from dataclasses import dataclass

ELLIPSIS_PAUSE = 0.5
SENTENCE_PAUSE = 0.25  # between runs split by emphasis, after a sentence ends
JOIN_PAUSE = 0.06  # between runs split mid-sentence
EMPHASIS_LEVELS = ("none", "moderate", "strong", "reduced")  # SSML's own; build.EMPHASIS says how each sounds
STYLES = {"normal", "ipa", "x-sampa", "literal", "pinyin", "jyutping"}
_LANG_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$")
# Private-use markers carry language spans through the run splitting:
# OPEN lang SEP text CLOSE
_OPEN, _SEP, _CLOSE = "\ue000", "\ue001", "\ue002"
_SEGMENT_RE = re.compile(f"{_OPEN}([^{_SEP}]*){_SEP}([^{_CLOSE}]*){_CLOSE}")
# A timing mark in plain narration (#75) travels the same way, by its number: MARK n MARK_END
_MARK, _MARK_END = "\ue003", "\ue004"
_MARK_AT_RE = re.compile(f"{_MARK}(\\d+){_MARK_END}")
MARK_RE = re.compile(r"""<mark\s+name\s*=\s*(["'])(?P<name>[^"']*)\1\s*/?>""", re.I)
MARK_NAME = re.compile(r"[A-Za-z_][\w-]*")  # "1", "2", … are the narration blocks' own cues

from .phonetics import PHONETIC_STYLES  # noqa: E402

# A run's text, or (text, tag) segments where part of it is in another language
# (tag = language code) or given phonetically (tag = ipa, x-sampa, pinyin, jyutping)
Speech = str | tuple[tuple[str, str | None], ...]

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
# Narakeet marks Russian stress with a caret before the vowel (гвозд^ики); the
# standard written form is a combining acute accent after it (гвозди́ки)
_STRESS_RE = re.compile(r"\^([аеёиоуыэюяАЕЁИОУЫЭЮЯ])")

def _letters(names: str) -> dict[str, str]:
    """'a b c …' style tables: 26 names for a-z, separated by '|'."""
    return dict(zip("abcdefghijklmnopqrstuvwxyz", (n.strip() for n in names.split("|")), strict=True))


# Letter names by language, for spelling words out (backticks, {literal})
LETTERS = {
    "en": _letters("ay|bee|see|dee|ee|eff|jee|aitch|eye|jay|kay|el|em|en|oh|pee|cue|ar|ess|tee|you|vee|"
                   "double you|ex|why|zee"),
    "es": _letters("a|be|ce|de|e|efe|ge|hache|i|jota|ka|ele|eme|ene|o|pe|cu|erre|ese|te|u|uve|uve doble|"
                   "equis|i griega|zeta") | {"ñ": "eñe"},
    "fr": _letters("a|bé|cé|dé|e|effe|gé|ache|i|ji|ka|elle|emme|enne|o|pé|ku|erre|esse|té|u|vé|"
                   "double vé|ixe|i grec|zède") | {"é": "e accent aigu", "è": "e accent grave", "ç": "cé cédille"},
    "de": _letters("a|be|ce|de|e|ef|ge|ha|i|jot|ka|el|em|en|o|pe|ku|er|es|te|u|fau|we|ix|ypsilon|zett")
          | {"ä": "ä", "ö": "ö", "ü": "ü", "ß": "eszett"},
    "it": _letters("a|bi|ci|di|e|effe|gi|acca|i|i lunga|cappa|elle|emme|enne|o|pi|cu|erre|esse|ti|u|vu|"
                   "doppia vu|ics|ipsilon|zeta"),
    "pt": _letters("á|bê|cê|dê|é|efe|gê|agá|i|jota|cá|ele|eme|ene|ó|pê|quê|erre|esse|tê|u|vê|dáblio|"
                   "xis|ípsilon|zê") | {"ç": "cê cedilha"},
}
SYMBOLS = {
    "en": {"?": "question mark", "!": "exclamation mark", ".": "dot", ",": "comma", "-": "dash",
           "_": "underscore", "/": "slash", "\\": "backslash", ":": "colon", ";": "semicolon", "@": "at",
           "#": "hash", "&": "ampersand", "+": "plus", "=": "equals", "*": "star", "%": "percent",
           "$": "dollar", "'": "apostrophe", '"': "quote", "(": "open bracket", ")": "close bracket"},
    "es": {"?": "signo de interrogación", "!": "signo de exclamación", ".": "punto", ",": "coma",
           "-": "guion", "/": "barra", "@": "arroba", "+": "más", "=": "igual", "%": "por ciento"},
    "fr": {"?": "point d'interrogation", "!": "point d'exclamation", ".": "point", ",": "virgule",
           "-": "tiret", "/": "barre oblique", "@": "arobase", "+": "plus", "=": "égal", "%": "pour cent"},
    "de": {"?": "Fragezeichen", "!": "Ausrufezeichen", ".": "Punkt", ",": "Komma", "-": "Bindestrich",
           "/": "Schrägstrich", "@": "at", "+": "plus", "=": "gleich", "%": "Prozent"},
    "it": {"?": "punto interrogativo", "!": "punto esclamativo", ".": "punto", ",": "virgola",
           "-": "trattino", "/": "barra", "@": "chiocciola", "+": "più", "=": "uguale", "%": "per cento"},
    "pt": {"?": "ponto de interrogação", "!": "ponto de exclamação", ".": "ponto", ",": "vírgula",
           "-": "hífen", "/": "barra", "@": "arroba", "+": "mais", "=": "igual", "%": "por cento"},
}


def spell(text: str, lang: str) -> str:
    """Read text letter by letter, with letter names in the voice's language when known."""
    base = (lang or "en").lower().split("-")[0]
    letters, symbols = LETTERS.get(base), SYMBOLS.get(base, {})
    if letters is None:
        return ", ".join(ch for ch in text if not ch.isspace())
    return ", ".join(letters.get(ch.lower()) or symbols.get(ch) or ch for ch in text if not ch.isspace())


def _strip_emphasis(text: str) -> str:
    for pattern in _EMPHASIS_RES:
        text = pattern.sub(r"\1", text)
    return text


@dataclass
class Run:
    """A stretch of narration synthesised in one call."""

    text: Speech
    emphasis: str = "none"  # one of EMPHASIS_LEVELS
    pause: float = 0.0  # silence before it
    rate: float = 1.0  # SSML prosody on top of the paragraph's voice settings
    pitch: float = 1.0  # frequency ratio
    gain: float = 0.0  # dB
    marks: tuple[str, ...] = ()  # SSML <mark> names at its start, timed for HTML scenes


def speech_runs(text: str, lang: str, notes: set[str]) -> list[Run]:
    """Speakable runs of one narration paragraph.

    Emphasis markup (`*x*`/`_x_` moderate, `**x**`/`__x__` strong, `~~x~~`
    reduced) and inline pauses (an ellipsis) split the paragraph; each run is
    synthesised separately. A `<mark name="x"/>` splits it too, without a pause,
    and times the words after it, as in SSML (#75). `notes` collects markup that
    was approximated.
    """
    names: list[str] = []

    def mark(m: re.Match[str]) -> str:
        name = m["name"].strip()
        if not MARK_NAME.fullmatch(name):
            notes.add(f"<mark name={name!r}> (ignored: use a name such as \"fleet\")")
            return " "
        names.append(name)
        return f"{_MARK}{len(names) - 1}{_MARK_END}"

    def ahead(inner: str) -> tuple[str, str]:
        """Marks inside a span or code, moved ahead of it, which they can't split; and what's left."""
        return "".join(m.group(0) for m in _MARK_AT_RE.finditer(inner)), _MARK_AT_RE.sub("", inner)

    def span(m: re.Match[str]) -> str:
        before, inner = ahead(m.group(1))
        opts = m.group(2).strip().lower()
        if opts == "literal":
            return before + spell(inner, lang)
        if opts in PHONETIC_STYLES or (opts not in STYLES and _LANG_RE.match(opts)):
            return f"{before}{_OPEN}{opts}{_SEP}{inner}{_CLOSE}"
        if opts != "normal":
            notes.add(f"narration span {{{opts}}} (read as plain text)")
        return before + inner

    def code(m: re.Match[str]) -> str:
        before, inner = ahead(m.group(1))
        return before + spell(inner, lang)

    text = MARK_RE.sub(mark, text)
    text = _SPAN_RE.sub(span, text)
    text = _LINK_RE.sub(r"\1", text)
    text = _CODE_RE.sub(code, text)

    pieces: list[tuple[str, str]] = []
    at = 0
    for m in _EMPHASIS_RE.finditer(text):
        pieces.append((text[at:m.start()], "none"))
        kind = next(k for k, v in m.groupdict().items() if v is not None)
        pieces.append((_strip_emphasis(m.group(kind)), kind.rstrip("2")))
        at = m.end()
    pieces.append((text[at:], "none"))

    runs: list[Run] = []
    pending: list[str] = []  # marks waiting for the words after them
    for chunk, emphasis in pieces:
        for i, part in enumerate(_ELLIPSIS_RE.split(stress_marks(_TAG_RE.sub(" ", chunk)))):
            split = _MARK_AT_RE.split(part)  # words, a mark's number, words, …
            stretches = [([], split[0])] + [([names[int(split[k])]], split[k + 1]) for k in range(1, len(split), 2)]
            # Between marks, what has no words (a bracket, a dash) stays with the words next to it, as unsplit
            joined: list[tuple[list[str], str]] = []
            for marks, words in stretches:
                if joined and not _has_words(joined[-1][1]):
                    marks, words = joined[-1][0] + marks, f"{joined.pop()[1]} {words}"
                joined.append((marks, words))
            after: list[str] = []  # marks after the part's last words
            if len(joined) > 1 and not _has_words(joined[-1][1]):
                after, words = joined.pop()
                joined[-1] = (joined[-1][0], f"{joined[-1][1]} {words}")
            first = True  # the part's first run takes the pause before it; a mark adds none
            for marks, words in joined:
                pending += marks
                words = " ".join(words.split())
                if not _has_words(words):
                    continue
                if not first:
                    pause = 0.0
                elif i:
                    pause = ELLIPSIS_PAUSE
                elif runs:
                    pause = SENTENCE_PAUSE if _ends(runs[-1].text)[-1:] in ".!?:;" else JOIN_PAUSE
                else:
                    pause = 0.0
                runs.append(Run(_segments(words), emphasis, pause, marks=tuple(pending)))
                pending, first = [], False
            pending += after
    if pending:  # marks after the last words: a silent run that only carries them
        runs.append(Run("", marks=tuple(pending)))
    return runs


def _has_words(text: str) -> bool:
    return any(ch.isalnum() for ch in text)


def _ends(speech: Speech) -> str:
    """A run's text, without trailing space, for what it ends with."""
    return (speech if isinstance(speech, str) else "".join(part for part, _ in speech)).rstrip()


def _segments(text: str) -> Speech:
    """Plain text, or (text, language) segments where language spans were marked."""
    if _OPEN not in text:
        return text.replace(_SEP, "").replace(_CLOSE, "")
    segments: list[tuple[str, str | None]] = []
    at = 0
    for m in _SEGMENT_RE.finditer(text):
        if text[at:m.start()].strip():
            segments.append((text[at:m.start()].strip(), None))
        segments.append((m.group(2).strip(), m.group(1)))
        at = m.end()
    if text[at:].strip():
        segments.append((text[at:].strip(), None))
    # A span cut by an ellipsis leaves stray markers: drop them
    cleaned = [(t.translate({ord(_OPEN): None, ord(_SEP): " ", ord(_CLOSE): None}).strip(), lg) for t, lg in segments]
    # Punctuation left over after a span (the full stop in "[x]{ipa}.") isn't worth its own request
    return tuple((t, lg) for t, lg in cleaned if any(ch.isalnum() for ch in t))


def speech_text(speech: Speech) -> str:
    return speech if isinstance(speech, str) else " ".join(t for t, _ in speech)


def stress_marks(text: str) -> str:
    """Caret stress marks before Cyrillic vowels become combining acute accents; other carets go."""
    return _STRESS_RE.sub(lambda m: m.group(1) + "\u0301", text).replace("^", "")


def _drop_tags(text: str) -> str:
    """Text without its tags. A tag separates the words either side of it, but leaves no space before
    closing punctuation or after opening punctuation: "<sub>quietube</sub>:" is "quietube:" (#69).
    Spaces the text itself has stay."""
    text = _TAG_RE.sub("\0", text)
    text = re.sub(r"\0+(?=[,.;:!?…%)\]}»”’'\"])", "", text)
    text = re.sub(r"(?<=[(\[{«“‘])\0+", "", text)
    return " ".join(text.replace("\0", " ").split())


def ssml_text(ssml: str) -> str:
    return _drop_tags(ssml)


def subtitle_text(text: str) -> str:
    unmarked = lambda m: MARK_RE.sub("", m.group(1))  # noqa: E731 - a mark inside goes before it when spoken
    text = _SPAN_RE.sub(unmarked, text)
    text = _LINK_RE.sub(unmarked, text)
    text = _CODE_RE.sub(unmarked, text)
    return _drop_tags(_strip_emphasis(text).replace("^", ""))
