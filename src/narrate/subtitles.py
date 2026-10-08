"""Subtitle cues (spec §8): timing, SRT/VTT files and an ASS script for burning in."""

from __future__ import annotations

from dataclasses import dataclass

from .config import SubtitleConfig


@dataclass
class Cue:
    start: float
    end: float
    text: str


def split_text(text: str, limit: int) -> list[str]:
    """Greedy word wrap into chunks of at most `limit` characters (a long word stays whole)."""
    chunks: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > limit:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def spread(start: float, end: float, texts: list[str]) -> list[Cue]:
    """Share [start, end) between texts in proportion to their length."""
    total = sum(max(1, len(t)) for t in texts)
    cues, t = [], start
    for text in texts:
        span = (end - start) * max(1, len(text)) / total
        cues.append(Cue(t, t + span, text))
        t += span
    return cues


def narration_cues(start: float, end: float, text: str, limit: int) -> list[Cue]:
    return spread(start, end, split_text(text, limit)) if text else []


def _clock(seconds: float, sep: str) -> str:
    ms = max(0, round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    return "".join(
        f"{i}\n{_clock(c.start, ',')} --> {_clock(c.end, ',')}\n{c.text}\n\n"
        for i, c in enumerate(cues, 1)
    )


def to_vtt(cues: list[Cue]) -> str:
    return "WEBVTT\n\n" + "".join(
        f"{_clock(c.start, '.')} --> {_clock(c.end, '.')}\n{c.text}\n\n" for c in cues
    )


def _ass_time(seconds: float) -> str:
    cs = max(0, round(seconds * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(hex_color: str) -> str:
    """#rrggbb[aa] -> &HAABBGGRR, where ASS alpha 00 is opaque."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    alpha = 255 - int(h[6:8], 16) if len(h) == 8 else 0
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def to_ass(cues: list[Cue], cfg: SubtitleConfig, width: int, height: int, font: str) -> str:
    base = min(width, height) * 0.052
    size = cfg.size or round(base * cfg.scale)
    alignment = {"bottom": 2, "middle": 5, "top": 8}[cfg.position]
    bold = -1 if cfg.mode == "tiktok" else 0
    if cfg.background:
        # BorderStyle 3 draws an opaque box in OutlineColour behind the text
        border, outline, outline_color = 3, max(2, round(size * 0.2)), _ass_color(cfg.background)
    else:
        border, outline, outline_color = 1, max(2, round(size * 0.07)), _ass_color(cfg.outline or "#000000")
    style = (
        f"Style: Default,{font},{size},{_ass_color(cfg.color)},{_ass_color(cfg.color)},"
        f"{outline_color},&H00000000,{bold},0,0,0,100,100,0,0,{border},{outline},0,"
        f"{alignment},{round(width * 0.05)},{round(width * 0.05)},{round(height * 0.06)},1"
    )
    events = "".join(
        f"Dialogue: 0,{_ass_time(c.start)},{_ass_time(c.end)},Default,,0,0,0,,"
        + c.text.replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N") + "\n"
        for c in cues
    )
    return (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 0\nScaledBorderAndShadow: yes\n"
        f"PlayResX: {width}\nPlayResY: {height}\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, "
        "Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style}\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        f"MarginV, Effect, Text\n{events}"
    )
