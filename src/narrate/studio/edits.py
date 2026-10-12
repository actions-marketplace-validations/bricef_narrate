"""Edits the studio makes to the script for direct manipulation (#62): a block, and properties to set.

The server owns the format (design D4), so the browser asks for an edit and
gets back the text to put in place of the block, applied in the editor as one
undoable change. A block keeps the form it's written in, and everything an
edit doesn't touch, byte for byte:

- a picture written `![tokens](file)` keeps that form, with its tokens
  updated in place, unless a property needs the map form (`zoom`, a volume
  other than mute), which only `(image: {…})` can hold;
- `(image: …)`, `(video: …)` and `(html: …)`, on one line or several, keep
  their keys in order, with new ones added at the end;
- a render block's ```` ```render:NAME tokens ```` line takes the same tokens
  as a picture.

Callouts (#64) are `(callout: …)` directions: one can be inserted after a
line (in the multi-line form the docs use), have its properties set the same
way, or be deleted with the blank line that separated it.

A timing mark (#75) is a `<mark name="…"/>` put before a word of narration,
plain or SSML, named after the word.

Positions are characters here; the editor counts UTF-16 units, so the server
converts at its edge (for_editor, index_of).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml

from ..script import (ANIMATED_SIZES, POSITIONS, SIZES, SYNCS, Narration, ScriptError, media_kind, parse,
                      parse_focus, parse_window)
from ..text import MARK_NAME, MARK_RE

_IMAGE = re.compile(r'^(?P<indent>\s*)!\[(?P<alt>[^\]]*)\]\((?P<target>\s*(?:<[^>]*>|[^)\s]+)(?:\s+"[^"]*")?\s*)\)(?P<tail>\s*)$')
_FENCE = re.compile(r"^(?P<lead>\s{0,3}(?:`{3,}|~{3,})\s*render:\S+)(?P<tokens>[^\n]*)$", re.I)
_DIRECTIVE = re.compile(r"^(?P<indent>\s*)\(\s*(?P<key>image|video|html)\s*:", re.I)
_SEGMENT = re.compile(r"^(start|end|\d+(?::\d{1,2}){0,2}(?:\.\d+)?)(?:-(start|end|\d+(?::\d{1,2}){0,2}(?:\.\d+)?))?$")
_PLAIN = re.compile(r"^(?:[A-Za-z0-9_./@+-]+|[\d.%][\d.% ]*)$")  # names, or numbers such as 70% 25% 2

# The properties an edit can set, and None to remove one (the default applies again)
PROPERTIES = ("fit", "motion", "position", "zoom", "sync", "segment", "volume", "from", "to")
_TOKEN_SLOTS = ("size", "position", "sync", "mute", "segment")


class EditError(Exception):
    """The edit can't be made: no such block, or a value the format doesn't have."""


def _check(changes: dict[str, Any]) -> dict[str, Any]:
    unknown = set(changes) - set(PROPERTIES)
    if unknown:
        raise EditError(f"unknown properties: {', '.join(sorted(unknown))}")
    rules = {"fit": SIZES, "motion": ANIMATED_SIZES, "sync": SYNCS}
    for key, allowed in rules.items():
        if changes.get(key) is not None and changes[key] not in allowed:
            raise EditError(f"{key} must be one of {', '.join(sorted(allowed))}, not {changes[key]!r}")
    position = changes.get("position")
    if position is not None and position not in POSITIONS and not parse_focus(str(position)):
        raise EditError(f"position must be one of {', '.join(sorted(POSITIONS))} or a point such as 70% 25%, "
                        f"not {position!r}")
    for key in ("from", "to"):
        if changes.get(key) is not None and not parse_window(str(changes[key])):
            raise EditError(f"{key} is a window such as 72% 30% 2.5 (its centre, then its zoom), not {changes[key]!r}")
    if changes.get("zoom") is not None:
        try:
            if float(changes["zoom"]) <= 1:
                raise ValueError
        except (TypeError, ValueError):
            raise EditError(f"zoom must be a number above 1, not {changes['zoom']!r}") from None
    if changes.get("segment") is not None and not _SEGMENT.match(str(changes["segment"]).replace(" ", "")):
        raise EditError(f"a segment is written start-end, as in 2-7.5, not {changes['segment']!r}")
    if changes.get("volume") is not None and changes["volume"] != "mute":
        try:
            float(changes["volume"])
        except (TypeError, ValueError):
            raise EditError(f"volume must be a number or mute, not {changes['volume']!r}") from None
    return changes


def _size_value(changes: dict[str, Any], current: str | None) -> tuple[bool, str | None]:
    """The size slot (which holds a fit or a motion) after the changes: (changed, value)."""
    if "motion" not in changes and "fit" not in changes:
        return False, current
    motion = changes.get("motion", current if current in ANIMATED_SIZES else None)
    if motion:
        return True, motion  # a motion implies cover
    fit = changes.get("fit", current if current in SIZES else None)
    return True, fit


def _volume_token(changes: dict[str, Any]) -> tuple[bool, bool]:
    """(changed, muted) for the token form, which can only say mute."""
    if "volume" not in changes:
        return False, False
    value = changes["volume"]
    return True, value == "mute" or (value is not None and float(value) == 0)


def _needs_map(changes: dict[str, Any]) -> bool:
    if changes.get("zoom") is not None or changes.get("from") is not None or changes.get("to") is not None:
        return True
    if changes.get("position") is not None and changes["position"] not in POSITIONS:
        return True  # a focal point
    value = changes.get("volume")
    return value is not None and value != "mute" and float(value) not in (0.0, 1.0)


def _slot(token: str) -> str | None:
    t = token.lower()
    if t in SIZES or t in ANIMATED_SIZES:
        return "size"
    if t in POSITIONS:
        return "position"
    if t in SYNCS:
        return "sync"
    if t == "mute":
        return "mute"
    if _SEGMENT.match(t):
        return "segment"
    return None


def _edit_tokens(tokens: list[str], changes: dict[str, Any]) -> list[str]:
    """Words such as `cover top 2-5 mute`, with the changes made in place."""
    current = {_slot(t): t.lower() for t in tokens if _slot(t)}
    wanted: dict[str, str | None] = {}
    changed, size = _size_value(changes, current.get("size"))
    if changed:
        wanted["size"] = size
    for key in ("position", "sync", "segment"):
        if key in changes:
            wanted[key] = None if changes[key] is None else str(changes[key]).replace(" ", "")
    changed, muted = _volume_token(changes)
    if changed:
        wanted["mute"] = "mute" if muted else None
    out: list[str] = []
    for token in tokens:
        slot = _slot(token)
        if slot in wanted:
            value = wanted.pop(slot)
            if value is not None:
                out.append(value)
        else:
            out.append(token)
    out += [wanted[slot] for slot in _TOKEN_SLOTS if wanted.get(slot) is not None]
    return out


def _quote(value: str) -> str:
    return value if _PLAIN.match(value) else '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _edit_props(props: dict[str, str], changes: dict[str, Any]) -> dict[str, str]:
    """A directive's map of properties, with the changes made; new keys go at the end."""
    props = dict(props)
    changed, size = _size_value(changes, props.get("size", "").lower() or None)
    updates: dict[str, str | None] = {}
    if changed:
        updates["size"] = size
    for key in ("position", "sync", "segment", "volume", "from", "to"):
        if key in changes:
            updates[key] = None if changes[key] is None else str(changes[key]).replace(" ", "") if key == "segment" \
                else str(changes[key])
    if "zoom" in changes:
        updates["zoom"] = None if changes["zoom"] is None else f"{float(changes['zoom']):g}"
    for key, value in updates.items():
        if value is None or (key == "volume" and value != "mute" and float(value) == 1.0):
            props.pop(key, None)
        else:
            props[key] = value
    return props


def _flow(props: dict[str, str]) -> str:
    return "{" + ", ".join(f"{k}: {_quote(v)}" for k, v in props.items()) + "}"


CALLOUT_KEYS = ("type", "cx", "cy", "size", "left", "top", "right", "bottom", "alpha", "style")
_CALLOUT = re.compile(r"^(?P<indent>\s*)\(\s*callout\s*:", re.I)


def _directive_lines(lines: list[str], start: int) -> int:
    """The index of the last line of the directive starting at `start` (the parser's own rule)."""
    if lines[start].rstrip().endswith(")"):
        return start
    for k in range(start + 1, len(lines)):
        if not lines[k].strip():
            break
        if lines[k].rstrip().endswith(")"):
            return k
    raise EditError(f"line {start + 1}: the direction is never closed with )")


def _offsets(lines: list[str]) -> list[int]:
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln) + 1)
    return offsets


def _read_directive(lines: list[str], i: int, line: int) -> tuple[str, Any, int]:
    """The direction starting on line index i: its key, its value (text or a map) and its last line index."""
    last = _directive_lines(lines, i)
    inner = "\n".join(lines[i:last + 1]).strip()[1:-1]
    try:
        data = yaml.load(inner, Loader=yaml.BaseLoader)
    except yaml.YAMLError as e:
        raise EditError(f"line {line}: can't read the direction: {e}") from None
    if not isinstance(data, dict) or len(data) != 1:
        raise EditError(f"line {line}: can't read the direction")
    (key, value), = data.items()
    return str(key), value, last


def _write_directive(lines: list[str], i: int, last: int, key: str, props: dict[str, str], as_text: str | None) -> str:
    """A direction rewritten in the form it had: one line (a flow map, or `as_text` when that's all there is)
    or one key per line, indented as before."""
    indent = re.match(r"\s*", lines[i]).group(0)
    if last == i:
        return f"{indent}({key}: {as_text if as_text is not None else _flow(props)})"
    pad = re.match(r"\s*", lines[i + 1]).group(0) or indent + "  "
    return f"{indent}({key}:\n" + "\n".join(f"{pad}{k}: {_quote(v)}" for k, v in props.items()) + ")"


def _callout_changes(changes: dict[str, Any]) -> dict[str, str | None]:
    unknown = set(changes) - set(CALLOUT_KEYS)
    if unknown:
        raise EditError(f"unknown callout properties: {', '.join(sorted(unknown))}")
    out: dict[str, str | None] = {}
    for key, value in changes.items():
        if value is None:
            out[key] = None
        elif key == "type":
            if value not in ("circle", "rectangle"):
                raise EditError(f"a callout is a circle or a rectangle, not {value!r}")
            out[key] = value
        elif key == "style":
            if value != "mask":
                raise EditError(f"a callout's style is mask, not {value!r}")
            out[key] = value
        else:
            try:
                number = float(value)
            except (TypeError, ValueError):
                raise EditError(f"callout {key} must be a number, not {value!r}") from None
            if key == "alpha":
                if not 0 <= number <= 1:
                    raise EditError("callout alpha is from 0 to 1")
                out[key] = f"{round(number, 2):g}"
            else:
                out[key] = str(round(number))  # frame pixels
    return out


def _callout_props(changes: dict[str, str | None], props: dict[str, str]) -> dict[str, str]:
    """A callout's properties with the changes made: written keys stay where they are, new ones follow in
    the usual order."""
    props = dict(props)
    # Switching shape drops the other shape's geometry
    if changes.get("type") == "rectangle":
        for key in ("cx", "cy", "size"):
            props.pop(key, None)
    elif changes.get("type") == "circle":
        for key in ("left", "top", "right", "bottom"):
            props.pop(key, None)
    for key in CALLOUT_KEYS:
        if key not in changes:
            continue
        value = changes[key]
        if value is None or (key == "type" and value == "circle"):
            props.pop(key, None)  # circle is the default type
        else:
            props[key] = value
    return props


def edit_callout(text: str, line: int, changes: dict[str, Any]) -> dict:
    """The change that sets properties of the callout at `line` (None removes one)."""
    wanted = _callout_changes(changes)
    lines = text.split("\n")
    if not 1 <= line <= len(lines) or not _CALLOUT.match(lines[line - 1]):
        raise EditError(f"line {line} isn't a callout")
    i = line - 1
    key, value, last = _read_directive(lines, i, line)
    if not isinstance(value, dict):
        raise EditError(f"line {line}: a callout needs properties such as cx and cy")
    old = {str(k).lower(): str(v) for k, v in value.items()}
    props = _callout_props(wanted, old)
    offsets = _offsets(lines)
    return {"from": offsets[i], "to": offsets[last] + len(lines[last]),
            "insert": _write_directive(lines, i, last, key, props, None)}


def insert_callout(text: str, after: int, callout: dict[str, Any]) -> dict:
    """The change that adds a callout after line `after` (0: at the very start), with blank lines around it."""
    props = _callout_props(_callout_changes(callout), {})
    lines = text.split("\n")
    if not 0 <= after <= len(lines):
        raise EditError(f"there is no line {after}")
    block = "(callout:\n" + "\n".join(f"  {k}: {v}" for k, v in props.items()) + ")"
    offsets = _offsets(lines)
    if after == 0:
        return {"from": 0, "to": 0, "insert": block + "\n\n"}
    at = offsets[after - 1] + len(lines[after - 1])
    following = lines[after] if after < len(lines) else ""
    return {"from": at, "to": at, "insert": "\n\n" + block + ("\n" if following.strip() else "")}


def _smallest(old: str, new: str) -> dict:
    """The one change that turns `old` into `new`, trimmed to what differs."""
    head = 0
    while head < min(len(old), len(new)) and old[head] == new[head]:
        head += 1
    tail = 0
    while tail < min(len(old), len(new)) - head and old[-1 - tail] == new[-1 - tail]:
        tail += 1
    return {"from": head, "to": len(old) - tail, "insert": new[head:len(new) - tail]}


def delete_block(text: str, line: int) -> dict:
    """The change that removes the direction at `line`, and one of the blank lines that separated it."""
    lines = text.split("\n")
    if not 1 <= line <= len(lines) or not lines[line - 1].lstrip().startswith("("):
        raise EditError(f"line {line} isn't a direction")
    i = line - 1
    last = _directive_lines(lines, i)
    kept = lines[:i] + lines[last + 1:]
    # Where it was, two blank lines now meet (or one starts the file): one of them goes too
    if i < len(kept) and not kept[i].strip() and (i == 0 or not kept[i - 1].strip()):
        del kept[i]
    elif i == len(kept) and i > 0 and not kept[i - 1].strip():
        del kept[i - 1]
    return _smallest(text, "\n".join(kept))


_SEPARATOR = re.compile(r"^ {0,3}-{3,}\s*$")
_VOICE = re.compile(r"^(?P<indent>\s*)\(\s*voice\s*:\s*(?P<value>[^)]*)\)\s*$", re.I)
_NAME = re.compile(r"^[\w .'/-]+$")


def _voice_name(value: str) -> str:
    value = str(value).strip()
    if not value or not _NAME.match(value):
        raise EditError(f"not a voice name: {value!r}")
    return value


def set_header(text: str, key: str, value: str) -> dict:
    """The change that sets `key: value` in the header, adding the header if the script has none (#65)."""
    if key != "voice":
        raise EditError(f"the studio doesn't set {key!r} in the header")
    value = _voice_name(value)
    lines = text.split("\n")
    end = None
    if lines and _SEPARATOR.match(lines[0]):
        end = next((k for k in range(1, len(lines)) if _SEPARATOR.match(lines[k])), None)
    if end is None:
        return {"from": 0, "to": 0, "insert": f"---\n{key}: {value}\n---\n\n"}
    offsets = _offsets(lines)
    for k in range(1, end):
        if re.match(rf"^\s*{key}\s*:", lines[k], re.I):
            indent = re.match(r"\s*", lines[k]).group(0)
            return {"from": offsets[k], "to": offsets[k] + len(lines[k]), "insert": f"{indent}{key}: {value}"}
    return {"from": offsets[end], "to": offsets[end], "insert": f"{key}: {value}\n"}


def set_voice(text: str, line: int, voice: str) -> dict:
    """The change that makes narration from `line` on use `voice`: the (voice: …) on that line rewritten,
    or a new one before the paragraph `line` is in (#65)."""
    voice = _voice_name(voice)
    lines = text.split("\n")
    if not 1 <= line <= len(lines):
        raise EditError(f"there is no line {line}")
    offsets = _offsets(lines)
    i = line - 1
    if m := _VOICE.match(lines[i]):
        return {"from": offsets[i], "to": offsets[i] + len(lines[i]), "insert": f"{m.group('indent')}(voice: {voice})"}
    if _SEPARATOR.match(lines[i]):
        raise EditError(f"line {line} is a scene break: put the cursor in the scene")
    while i > 0 and lines[i - 1].strip() and not _SEPARATOR.match(lines[i - 1]):
        i -= 1  # back to the start of the paragraph
    return {"from": offsets[i], "to": offsets[i], "insert": f"(voice: {voice})\n\n"}


def edit_block(text: str, line: int, changes: dict[str, Any]) -> dict:
    """The change that sets `changes` on the media block at `line`: {"from", "to", "insert"} in characters."""
    _check(changes)
    lines = text.split("\n")
    if not 1 <= line <= len(lines):
        raise EditError(f"there is no line {line}")
    i = line - 1
    offsets = _offsets(lines)

    if m := _IMAGE.match(lines[i]):
        target = m.group("target").strip()
        path = target.split('"')[0].strip().strip("<>").strip()
        if _needs_map(changes):
            kind = media_kind(path)
            if kind not in ("image", "video", "html"):
                raise EditError(f"line {line}: {path} isn't a picture, clip or page")
            props = {"file": path}
            for token in m.group("alt").split():
                slot = _slot(token)
                if slot == "mute":
                    props["volume"] = "mute"
                elif slot:
                    props[slot] = token.lower()
            new = f"{m.group('indent')}({kind}: {_flow(_edit_props(props, changes))})"
        else:
            tokens = _edit_tokens(m.group("alt").split(), changes)
            new = f"{m.group('indent')}![{' '.join(tokens)}]({m.group('target')}){m.group('tail')}"
        return {"from": offsets[i], "to": offsets[i] + len(lines[i]), "insert": new}

    if m := _FENCE.match(lines[i]):
        if _needs_map(changes):
            raise EditError(f"line {line}: write zoom and volume in the render block's frontmatter")
        tokens = _edit_tokens(m.group("tokens").split(), changes)
        new = m.group("lead") + "".join(f" {t}" for t in tokens)
        return {"from": offsets[i], "to": offsets[i] + len(lines[i]), "insert": new}

    if _DIRECTIVE.match(lines[i]):
        key, value, last = _read_directive(lines, i, line)
        props = {"file": value} if isinstance(value, str) else {str(k).lower(): str(v) for k, v in value.items()}
        props = _edit_props(props, changes)
        # Written as just the file, it stays so while there's nothing else to say
        as_text = props["file"] if list(props) == ["file"] and isinstance(value, str) else None
        return {"from": offsets[i], "to": offsets[last] + len(lines[last]),
                "insert": _write_directive(lines, i, last, key, props, as_text)}

    raise EditError(f"line {line} isn't a picture, clip, page or render block")


# A word: letters and digits, with apostrophes or hyphens inside it
_WORD = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*")
_TAG = re.compile(r"<[^>]*>?")
_TOKEN = re.compile(r"[^\s<>]+")  # what the voice reads as one: no spaces, and tags break it as spaces do
# Plain markup a mark can't go inside, as it would be spelled or read as phonetics: it goes before it
_WHOLE_PLAIN = re.compile(r"`[^`]+`|\[[^\]]+\]\{[^}]+\}|\[[^\]]+\]\([^)]*\)")
_WHOLE_SSML = re.compile(r"<(say-as|phoneme|sub)\b[^>]*>.*?</\1\s*>", re.I)
# What the words in it aren't: a span's style or language, a link's address
_UNSPOKEN = re.compile(r"(?<=\])\{[^}]+\}|(?<=\])\([^)]*\)")


def _mark_name(word: str, taken: set[str]) -> str:
    """A mark name from a word: plain lowercase ASCII, unique among `taken` (fleet, fleet-2, …)."""
    ascii_ = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9_]+", "-", ascii_).strip("-") or "mark"
    if not base[0].isalpha():
        base = f"mark-{base}"
    name, n = base, 1
    while name in taken:
        n += 1
        name = f"{base}-{n}"
    return name


def insert_mark(text: str, at: int, name: str | None = None) -> dict:
    """The change that puts a timing mark before the word at character `at` (#75): the word the cursor is in
    or touches, else the next on its line. An HTML scene or overlay times something to it with --cue-NAME.

    The paragraph stays as written, plain or SSML: plain narration takes marks too. A mark goes before any
    markup it can't go inside (code, a phonetic or language span, a link; SSML's say-as, phoneme, sub). It's
    named after the word, unless `name` is given, and unique in its scene. `select` is the name, in the new
    text, so it can be renamed by typing."""
    try:
        script = parse(text, Path("script.md"))
    except ScriptError as e:
        raise EditError(str(e)) from None
    lines = text.split("\n")
    offsets = _offsets(lines)
    if not 0 <= at <= len(text):
        raise EditError(f"there is no position {at}")
    i = max(k for k, o in enumerate(offsets) if o <= at)
    line = lines[i]
    starts = sorted((b.line, b, scene) for scene in script.scenes for b in scene.blocks)
    holder = next(((b, scene) for start, b, scene in reversed(starts) if start <= i + 1), None)
    if not line.strip() or holder is None or not isinstance(holder[0], Narration):
        raise EditError("put the cursor in narration: a mark goes before one of its words")
    block, scene = holder

    hidden = [(m.start(), m.end()) for m in _TAG.finditer(line)]
    if not block.ssml:
        hidden += [(m.start(), m.end()) for m in _UNSPOKEN.finditer(line)]
    words = [w for w in _WORD.finditer(line) if not any(a < w.end() and w.start() < b for a, b in hidden)]
    if not words:
        raise EditError("there's no word on this line to mark")
    column = at - offsets[i]
    word = next((w for w in words if w.end() >= column), words[-1])
    # Before the whole token it's in (A&B, *this*): the voice reads a token as one, so a mark can't split it
    pos = next(t.start() for t in _TOKEN.finditer(line) if t.start() <= word.start() < t.end())
    for m in (_WHOLE_SSML if block.ssml else _WHOLE_PLAIN).finditer(line):
        if m.start() < pos < m.end():
            pos = m.start()
    named = "-".join(w.group(0) for w in words if pos <= w.start() <= word.start())

    later = [s.line for s in script.scenes if s.line > scene.line]
    end = (later[0] - 1) if later else len(lines)
    taken = {m["name"] for row in lines[scene.line - 1:end] for m in MARK_RE.finditer(row)}
    if name is None:
        name = _mark_name(named, taken)
    elif not MARK_NAME.fullmatch(name):
        raise EditError(f"not a mark name: {name!r} (letters, digits, - and _, starting with a letter)")
    tag = f'<mark name="{name}"/>'
    where = offsets[i] + pos
    first = where + len('<mark name="')
    return {"from": where, "to": where, "insert": tag, "select": {"anchor": first, "head": first + len(name)}}


def units(text: str, index: int) -> int:
    """Where character `index` of `text` is for the editor, which counts UTF-16 units (an emoji is two)."""
    return index + sum(1 for ch in text[:index] if ord(ch) > 0xFFFF)


def index_of(text: str, unit: int) -> int:
    """The character of `text` at the editor's position `unit`."""
    count = 0
    for i, ch in enumerate(text):
        if count >= unit:
            return i
        count += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def for_editor(text: str, change: dict) -> dict:
    """A change in the editor's units: `from` and `to` in `text`, and a selection in the text after it."""
    out = {**change, "from": units(text, change["from"]), "to": units(text, change["to"])}
    if "select" in change:
        after = apply(text, change)
        out["select"] = {k: units(after, v) for k, v in change["select"].items()}
    return out


def apply(text: str, change: dict) -> str:
    """`text` with an edit's change made (as the editor does)."""
    return text[:change["from"]] + change["insert"] + text[change["to"]:]
