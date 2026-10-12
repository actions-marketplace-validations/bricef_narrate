"""SSML narration paragraphs (spec §6.6) as narrate runs.

Engines differ in the SSML they accept, so narrate interprets a practical
subset itself and renders it the same way everywhere:

    <break time="500ms"/> / strength=...    silence
    <prosody rate pitch volume>             per-run speed, pitch and gain
    <emphasis level>                        the emphasis bundles
    <say-as interpret-as="characters">      spelling out
    <phoneme alphabet="ipa|x-sampa" ph>     a phonetic segment
    <lang xml:lang="de-DE">                 a language segment
    <sub alias="...">                       read the alias
    <p>, <s>                                sentence breaks
    <mark name="x"/>                        a timing point for HTML scenes (--cue-x)

Other tags keep their text and are noted once each.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace

from .text import MARK_NAME, SENTENCE_PAUSE, Run, spell

RATES = {"x-slow": 0.6, "slow": 0.8, "medium": 1.0, "default": 1.0, "fast": 1.2, "x-fast": 1.4}
PITCHES = {"x-low": -4.0, "low": -2.0, "medium": 0.0, "default": 0.0, "high": 2.0, "x-high": 4.0}
VOLUMES = {"silent": -60.0, "x-soft": -9.0, "soft": -4.5, "medium": 0.0, "default": 0.0, "loud": 4.5, "x-loud": 9.0}
BREAKS = {"none": 0.0, "x-weak": 0.1, "weak": 0.2, "medium": 0.4, "strong": 0.7, "x-strong": 1.2}
SPELL = {"characters", "spell-out", "verbatim"}


@dataclass(frozen=True)
class Prosody:
    rate: float = 1.0
    pitch: float = 1.0  # frequency ratio
    gain: float = 0.0  # dB
    emphasis: str = "none"


def _rate(value: str) -> float:
    value = value.strip().lower()
    if value in RATES:
        return RATES[value]
    if m := re.fullmatch(r"([+-]?\d+(?:\.\d+)?)%", value):
        number = float(m.group(1))
        return 1 + number / 100 if value[0] in "+-" else number / 100
    return 1.0


def _pitch(value: str) -> float:
    value = value.strip().lower()
    if value in PITCHES:
        return 2 ** (PITCHES[value] / 12)
    if m := re.fullmatch(r"([+-]?\d+(?:\.\d+)?)st", value):
        return 2 ** (float(m.group(1)) / 12)
    if m := re.fullmatch(r"([+-]?\d+(?:\.\d+)?)%", value):
        return max(0.1, 1 + float(m.group(1)) / 100)
    return 1.0


def _volume(value: str) -> float:
    value = value.strip().lower()
    if value in VOLUMES:
        return VOLUMES[value]
    if m := re.fullmatch(r"([+-]?\d+(?:\.\d+)?)db", value):
        return float(m.group(1))
    return 0.0


def _break(element: ET.Element) -> float:
    if time := element.get("time"):
        if m := re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s)\s*", time.lower()):
            return float(m.group(1)) / (1000 if m.group(2) == "ms" else 1)
    return BREAKS.get((element.get("strength") or "medium").lower(), 0.4)


class _Builder:
    def __init__(self, lang: str, notes: set[str]):
        self.lang, self.notes = lang, notes
        self.runs: list[Run] = []
        self.pieces: list[tuple[str, str | None]] = []
        self.prosody = Prosody()
        self.pause = 0.0
        self.marks: list[str] = []

    def flush(self) -> None:
        pieces: list[tuple[str, str | None]] = []
        for t, tag in self.pieces:
            if pieces and pieces[-1][1] == tag:
                pieces[-1] = (f"{pieces[-1][0]} {t}", tag)  # same language: one segment
            else:
                pieces.append((t, tag))
        pieces = [(t, tag) for t, tag in pieces if any(ch.isalnum() for ch in t)]
        self.pieces = []
        if not pieces:
            return
        text = " ".join(t for t, _ in pieces) if all(tag is None for _, tag in pieces) else tuple(pieces)
        p = self.prosody
        self.runs.append(Run(text, p.emphasis, self.pause, rate=p.rate, pitch=p.pitch, gain=p.gain,
                             marks=tuple(self.marks)))
        self.pause = 0.0
        self.marks = []

    def text(self, value: str | None, tag: str | None = None) -> None:
        if value and value.strip():
            self.pieces.append((" ".join(value.split()), tag))

    def visit(self, element: ET.Element, prosody: Prosody, tag: str | None) -> None:
        name = element.tag.split("}")[-1]
        child_prosody, child_tag = prosody, tag
        if name == "break":
            self.flush()
            self.pause += _break(element)
            self.text(element.tail, tag)
            return
        if name == "mark":
            # The speech splits here, so the mark's time is exact
            self.flush()
            mark = (element.get("name") or "").strip()
            if MARK_NAME.fullmatch(mark):
                self.marks.append(mark)
            else:
                self.notes.add(f"SSML <mark name={mark!r}> (ignored: use a name such as \"fleet\")")
            self.text(element.tail, tag)
            return
        if name == "prosody":
            child_prosody = replace(prosody, rate=prosody.rate * _rate(element.get("rate", "medium")),
                                    pitch=prosody.pitch * _pitch(element.get("pitch", "medium")),
                                    gain=prosody.gain + _volume(element.get("volume", "medium")))
        elif name == "emphasis":
            child_prosody = replace(prosody, emphasis=(element.get("level") or "moderate").lower())
        elif name == "lang":
            child_tag = element.get("{http://www.w3.org/XML/1998/namespace}lang", tag)
        elif name in ("p", "s"):
            self.flush()
            self.pause = max(self.pause, SENTENCE_PAUSE)
        elif name not in ("speak", "phoneme", "say-as", "sub"):
            self.notes.add(f"SSML <{name.replace('_', ':', 1)}> (ignored, its text is read)")

        if child_prosody != self.prosody:
            self.flush()
            self.prosody = child_prosody
        if name == "phoneme":
            alphabet = (element.get("alphabet") or "ipa").lower()
            self.text(element.get("ph"), "x-sampa" if alphabet == "x-sampa" else "ipa")
        elif name == "sub":
            self.text(element.get("alias") or "".join(element.itertext()), child_tag)
        elif name == "say-as" and (element.get("interpret-as") or "").lower() in SPELL:
            self.text(spell("".join(element.itertext()), (child_tag or self.lang)), child_tag)
        else:
            self.text(element.text, child_tag)
            for child in element:
                self.visit(child, child_prosody, child_tag)
        if name in ("p", "s"):
            self.flush()
            self.pause = max(self.pause, SENTENCE_PAUSE)
        if child_prosody != prosody:
            self.flush()
            self.prosody = prosody
        self.text(element.tail, tag)


def ssml_runs(ssml: str, lang: str, notes: set[str]) -> list[Run] | None:
    """Runs for an SSML paragraph, or None if it isn't well-formed XML."""
    # Vendor tags such as <amazon:effect> use undeclared namespace prefixes
    cleaned = re.sub(r"<(/?)([A-Za-z]+):(?!lang)", r"<\1\2_", ssml)
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError:
        return None
    builder = _Builder(lang, notes)
    builder.visit(root, Prosody(), None)
    builder.flush()
    if builder.marks:  # marks after the last words: a silent run that only carries them
        builder.runs.append(Run("", pause=builder.pause, marks=tuple(builder.marks)))
    return builder.runs
