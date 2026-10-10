"""The narrate skill for LLM agents (#68) stays true to the tool it describes.

skills/narrate/ ships in this repository so that a change to the format updates the skill in the
same commit; these tests notice when it doesn't.
"""

import re
from pathlib import Path

import pytest
import yaml

from narrate.config import HEADER_KEYS, settings_from_header
from narrate.script import DIRECTIVES, parse

SKILL = Path(__file__).resolve().parents[1] / "skills" / "narrate"
FORMAT = (SKILL / "references" / "format.md").read_text()
FILES = sorted(SKILL.rglob("*.md"))


def frontmatter() -> dict:
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n")[1])


def test_the_frontmatter_names_and_describes_the_skill():
    meta = frontmatter()
    assert meta["name"] == "narrate" == SKILL.name
    assert 200 < len(meta["description"]) <= 1024  # long enough to trigger on, within the limit
    assert len((SKILL / "SKILL.md").read_text().splitlines()) < 500  # the body stays lean


@pytest.mark.parametrize("key", sorted(DIRECTIVES))
def test_every_stage_direction_is_described(key):
    assert re.search(rf"\({re.escape(key)}:", FORMAT), f"({key}: …) isn't in references/format.md"


@pytest.mark.parametrize("key", HEADER_KEYS)
def test_every_header_key_is_described(key):
    first_cells = [line.split("|")[1] for line in FORMAT.splitlines() if line.startswith("| `")]
    assert any(f"`{key}`" in cell for cell in first_cells), f"header key {key} isn't in format.md's table"


def test_every_reference_the_skill_points_to_exists():
    named = set(re.findall(r"`?(references/[\w.-]+\.md)`?", (SKILL / "SKILL.md").read_text()))
    assert named, "SKILL.md should point to its references"
    for path in named:
        assert (SKILL / path).is_file(), path
    for path in (SKILL / "references").glob("*.md"):
        assert f"references/{path.name}" in (SKILL / "SKILL.md").read_text() or path.name in FORMAT, path


def examples() -> list:
    found = []
    for path in FILES:
        for block in re.findall(r"^````markdown\n(.*?)^````$", path.read_text(), re.S | re.M):
            found.append(pytest.param(block, id=f"{path.relative_to(SKILL)}:{block.splitlines()[0][:30]}"))
    return found


@pytest.mark.parametrize("text", examples())
def test_every_example_script_reads_without_warnings(text):
    script = parse(text)
    settings_from_header(script.header, script.warnings)
    assert script.warnings == []
