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
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from ..script import ANIMATED_SIZES, POSITIONS, SIZES, SYNCS, media_kind

_IMAGE = re.compile(r'^(?P<indent>\s*)!\[(?P<alt>[^\]]*)\]\((?P<target>\s*(?:<[^>]*>|[^)\s]+)(?:\s+"[^"]*")?\s*)\)(?P<tail>\s*)$')
_FENCE = re.compile(r"^(?P<lead>\s{0,3}(?:`{3,}|~{3,})\s*render:\S+)(?P<tokens>[^\n]*)$", re.I)
_DIRECTIVE = re.compile(r"^(?P<indent>\s*)\(\s*(?P<key>image|video|html)\s*:", re.I)
_SEGMENT = re.compile(r"^(start|end|\d+(?::\d{1,2}){0,2}(?:\.\d+)?)(?:-(start|end|\d+(?::\d{1,2}){0,2}(?:\.\d+)?))?$")
_PLAIN = re.compile(r"^[A-Za-z0-9_./@+-]+$")

# The properties an edit can set, and None to remove one (the default applies again)
PROPERTIES = ("fit", "motion", "position", "zoom", "sync", "segment", "volume")
_TOKEN_SLOTS = ("size", "position", "sync", "mute", "segment")


class EditError(Exception):
    """The edit can't be made: no such block, or a value the format doesn't have."""


def _check(changes: dict[str, Any]) -> dict[str, Any]:
    unknown = set(changes) - set(PROPERTIES)
    if unknown:
        raise EditError(f"unknown properties: {', '.join(sorted(unknown))}")
    rules = {"fit": SIZES, "motion": ANIMATED_SIZES, "position": POSITIONS, "sync": SYNCS}
    for key, allowed in rules.items():
        if changes.get(key) is not None and changes[key] not in allowed:
            raise EditError(f"{key} must be one of {', '.join(sorted(allowed))}, not {changes[key]!r}")
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
    if changes.get("zoom") is not None:
        return True
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
    for key in ("position", "sync", "segment", "volume"):
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


def edit_block(text: str, line: int, changes: dict[str, Any]) -> dict:
    """The change that sets `changes` on the media block at `line`: {"from", "to", "insert"} in characters."""
    _check(changes)
    lines = text.split("\n")
    if not 1 <= line <= len(lines):
        raise EditError(f"there is no line {line}")
    i = line - 1
    offsets = [0]
    for ln in lines:
        offsets.append(offsets[-1] + len(ln) + 1)

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

    if m := _DIRECTIVE.match(lines[i]):
        last = _directive_lines(lines, i)
        raw = "\n".join(lines[i:last + 1])
        inner = raw.strip()[1:-1]
        try:
            data = yaml.load(inner, Loader=yaml.BaseLoader)
        except yaml.YAMLError as e:
            raise EditError(f"line {line}: can't read the direction: {e}") from None
        if not isinstance(data, dict) or len(data) != 1:
            raise EditError(f"line {line}: can't read the direction")
        (key, value), = data.items()
        props = {"file": value} if isinstance(value, str) else {str(k).lower(): str(v) for k, v in value.items()}
        props = _edit_props(props, changes)
        indent = m.group("indent")
        if last == i:  # one line: a flow map, or just the file when nothing else is left
            body = props["file"] if list(props) == ["file"] and isinstance(value, str) else _flow(props)
            new = f"{indent}({key}: {body})"
        else:  # several lines: one key per line, indented as the first one was
            pad = re.match(r"\s*", lines[i + 1]).group(0) or indent + "  "
            entries = [f"{pad}{k}: {_quote(v)}" for k, v in props.items()]
            new = f"{indent}({key}:\n" + "\n".join(entries) + ")"
        return {"from": offsets[i], "to": offsets[last] + len(lines[last]), "insert": new}

    raise EditError(f"line {line} isn't a picture, clip, page or render block")


def apply(text: str, change: dict) -> str:
    """`text` with an edit's change made (as the editor does)."""
    return text[:change["from"]] + change["insert"] + text[change["to"]:]
