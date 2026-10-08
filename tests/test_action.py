from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def test_action_mirrors_narakeets_outputs():
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    assert action["runs"]["using"] == "composite"
    assert action["inputs"]["source-path"]["required"] is True
    assert set(action["outputs"]) == {"video-file", "poster-file", "srt-file", "vtt-file"}


def test_secrets_reach_the_build_through_the_environment():
    """No ${{ inputs.* }} inside a run script: inputs go through env, never into shell text."""
    for step in yaml.safe_load((ROOT / "action.yml").read_text())["runs"]["steps"]:
        assert "${{" not in step.get("run", "")


def test_demo_workflow_uses_the_local_action():
    workflow = yaml.safe_load((ROOT / ".github/workflows/demo.yml").read_text())
    steps = workflow["jobs"]["demo"]["steps"]
    assert any(step.get("uses") == "./" and step["with"]["source-path"] == "examples/demo/demo.md" for step in steps)
