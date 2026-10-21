from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def action():
    return yaml.safe_load((ROOT / "action.yml").read_text())


def test_action_mirrors_narakeets_outputs():
    a = action()
    assert a["runs"]["using"] == "composite"
    assert a["inputs"]["source-path"]["required"] is True
    assert set(a["outputs"]) == {"video-file", "poster-file", "srt-file", "vtt-file", "transcript-file"}


def test_action_chooses_subtitles_and_a_transcript(tmp_path):
    """The inputs become narrate's own options, and the transcript comes back as an output (#58)."""
    import subprocess

    a = action()
    assert a["inputs"]["subtitles"]["default"] == "" and a["inputs"]["transcript"]["default"] == "false"
    build = next(step for step in a["runs"]["steps"] if step.get("id") == "build")
    assert build["env"]["SUBTITLES"] == "${{ inputs.subtitles }}" and build["env"]["TRANSCRIPT"] == "${{ inputs.transcript }}"
    # Run the step's script with a stand-in docker that records its arguments and makes the files
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text('#!/bin/bash\necho "$@" > "$RECORD"\nbase="${OUTPUT%.*}"\n'
                                    'touch "$OUTPUT" "$base.jpg" "$base.srt" "$base.vtt" "$base.transcript.txt"\n')
    (bin_dir / "docker").chmod(0o755)

    def run(subtitles, transcript):
        outputs = tmp_path / "outputs"
        outputs.write_text("")
        env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path), "GITHUB_WORKSPACE": str(tmp_path),
               "GITHUB_OUTPUT": str(outputs), "RECORD": str(tmp_path / "args"), "IMAGE": "narrate:test",
               "SOURCE": "s.md", "OUTPUT": str(tmp_path / "out/video.mp4"), "TTS": "silent",
               "SUBTITLES": subtitles, "TRANSCRIPT": transcript}
        subprocess.run(["bash", "-e", "-c", build["run"]], env=env, cwd=tmp_path, check=True)
        return (tmp_path / "args").read_text().split(), outputs.read_text()

    args, outputs = run("external", "true")
    assert args[args.index("build"):] == ["build", "s.md", "-o", str(tmp_path / "out/video.mp4"), "--tts", "silent",
                                          "--subtitles", "external", "--transcript"]
    assert f"transcript-file={tmp_path}/out/video.transcript.txt" in outputs
    args, _ = run("", "false")
    assert "--subtitles" not in args and "--transcript" not in args  # the script decides


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


def test_published_image_is_checked_through_the_action():
    workflow = yaml.safe_load((ROOT / ".github/workflows/image.yml").read_text())
    job = workflow["jobs"]["published"]
    assert job["needs"] == "image" and job["permissions"]["packages"] == "read"
    step = next(s for s in job["steps"] if s.get("uses") == "./")
    assert step["with"]["image"].startswith("ghcr.io/") and "needs.image.outputs.digest" in step["with"]["image"]


def test_image_built_and_published_is_the_runtime_stage():
    """Not the Dockerfile's last stage, test, which starts in /src (#88)."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/image.yml").read_text())
    steps = workflow["jobs"]["image"]["steps"]
    built = next(s for s in steps if s.get("with", {}).get("load"))
    published = next(s for s in steps if s.get("with", {}).get("push"))
    assert built["with"]["target"] == published["with"]["target"] == "runtime"
