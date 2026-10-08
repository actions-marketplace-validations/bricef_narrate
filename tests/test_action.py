from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def action():
    return yaml.safe_load((ROOT / "action.yml").read_text())


def test_action_mirrors_narakeets_outputs():
    a = action()
    assert a["runs"]["using"] == "composite"
    assert a["inputs"]["source-path"]["required"] is True
    assert set(a["outputs"]) == {"video-file", "poster-file", "srt-file", "vtt-file"}


def test_action_builds_in_the_published_image():
    a = action()
    assert a["inputs"]["image"]["default"] == "ghcr.io/bricef/narrate:latest"
    build = next(step for step in a["runs"]["steps"] if step.get("id") == "build")
    assert "docker run" in build["run"] and '"$IMAGE" build' in build["run"]


def test_secrets_reach_the_build_through_the_environment():
    """No ${{ inputs.* }} inside a run script: inputs go through env, never into shell text."""
    for step in action()["runs"]["steps"]:
        assert "${{" not in step.get("run", "")


def test_image_workflow_renders_the_demo_with_the_image_it_built():
    workflow = yaml.safe_load((ROOT / ".github/workflows/image.yml").read_text())
    steps = workflow["jobs"]["image"]["steps"]
    built = next(s for s in steps if s.get("with", {}).get("load"))["with"]["tags"]
    demo = next(s for s in steps if s.get("uses") == "./")
    assert demo["with"] == {"image": built, "source-path": "examples/demo/demo.md",
                            "output": "out/demo.mp4", "tts": "kokoro"}


def test_image_is_published_only_from_main_and_tags():
    workflow = yaml.safe_load((ROOT / ".github/workflows/image.yml").read_text())
    steps = workflow["jobs"]["image"]["steps"]
    publish = next(s for s in steps if s.get("with", {}).get("push"))
    meta = next(s for s in steps if s.get("id") == "meta")
    assert publish["if"] == "steps.meta.outcome == 'success'"
    assert meta["if"] == "github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')"
