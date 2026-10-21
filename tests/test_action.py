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
    main_or_tags = "github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')"
    steps = workflow["jobs"]["image"]["steps"]
    push = next(s for s in steps if s.get("id") == "push")
    meta = next(s for s in steps if s.get("id") == "meta")
    assert push["if"] == "steps.meta.outcome == 'success'"
    assert meta["if"] == main_or_tags
    assert workflow["jobs"]["publish"]["if"] == main_or_tags
    tags = next(s for s in workflow["jobs"]["publish"]["steps"] if s.get("id") == "meta")
    assert tags["with"]["flavor"] == "latest=false"  # only main moves latest, not v* tags


def test_image_is_built_and_published_for_amd64_and_arm64():
    """Each natively on its own runner, with its own cache, then tagged together as one image (#91)."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/image.yml").read_text())
    job = workflow["jobs"]["image"]
    assert job["strategy"]["matrix"]["include"] == [{"arch": "amd64", "runner": "ubuntu-latest"},
                                                    {"arch": "arm64", "runner": "ubuntu-24.04-arm"}]
    assert job["runs-on"] == "${{ matrix.runner }}"
    builds = [s for s in job["steps"] if s.get("uses", "").startswith("docker/build-push-action")]
    assert len(builds) == 3
    for build in builds:
        assert build["with"]["platforms"] == "linux/${{ matrix.arch }}"
        assert build["with"]["cache-from"] == "type=gha,scope=${{ matrix.arch }}"
    # Only main writes the cache, from the test stage's build, which covers every stage
    [writes] = [b for b in builds if "cache-to" in b["with"]]
    assert writes["with"]["target"] == "test"
    assert writes["with"]["cache-to"] == ("${{ github.ref == 'refs/heads/main' && "
                                          "format('type=gha,mode=max,scope={0}', matrix.arch) || '' }}")
    push = next(s for s in builds if s.get("id") == "push")
    assert "push-by-digest=true" in push["with"]["outputs"]
    publish = workflow["jobs"]["publish"]
    assert publish["needs"] == "image"
    assert "docker buildx imagetools create" in next(s for s in publish["steps"] if s.get("id") == "index")["run"]


def test_published_image_is_checked_through_the_action():
    """On both platforms, by the digest of the image published for both."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/image.yml").read_text())
    job = workflow["jobs"]["published"]
    assert job["needs"] == "publish" and job["permissions"]["packages"] == "read"
    platforms = workflow["jobs"]["image"]["strategy"]["matrix"]["include"]
    assert job["strategy"]["matrix"]["runner"] == [p["runner"] for p in platforms]
    step = next(s for s in job["steps"] if s.get("uses") == "./")
    assert step["with"]["image"].startswith("ghcr.io/") and "needs.publish.outputs.digest" in step["with"]["image"]


def test_image_built_and_published_is_the_runtime_stage():
    """Not the Dockerfile's last stage, test, which starts in /src (#88)."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/image.yml").read_text())
    steps = workflow["jobs"]["image"]["steps"]
    built = next(s for s in steps if s.get("with", {}).get("load"))
    published = next(s for s in steps if s.get("id") == "push")
    assert built["with"]["target"] == published["with"]["target"] == "runtime"
