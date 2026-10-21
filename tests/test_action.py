import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent


def action():
    return yaml.safe_load((ROOT / "action.yml").read_text())


def image_workflow():
    return yaml.safe_load((ROOT / ".github/workflows/image.yml").read_text())


def test_action_mirrors_narakeets_outputs():
    a = action()
    assert a["runs"]["using"] == "composite"
    assert a["inputs"]["source-path"]["required"] is True
    assert set(a["outputs"]) == {"video-file", "poster-file", "srt-file", "vtt-file", "transcript-file"}


def test_action_chooses_subtitles_and_a_transcript(tmp_path):
    """The inputs become narrate's own options, and the transcript comes back as an output (#58)."""
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
    assert a["inputs"]["image"]["default"] == ""  # its own release's, as below
    build = next(step for step in a["runs"]["steps"] if step.get("id") == "build")
    assert "docker run" in build["run"] and '"$IMAGE" build' in build["run"]
    pull = next(step for step in a["runs"]["steps"] if step.get("name") == "Pull the image")
    assert pull["env"]["IMAGE"] == build["env"]["IMAGE"] == "${{ steps.image.outputs.image }}"


LATEST = "ghcr.io/bricef/narrate:latest"


@pytest.mark.parametrize("ref, image", [
    ("v0.1.0", "ghcr.io/bricef/narrate:0.1.0"),
    ("v0", "ghcr.io/bricef/narrate:0"),  # the major tag, which follows the newest 0.x release
    ("v0.1", "ghcr.io/bricef/narrate:0.1"),
    ("v12.3.45", "ghcr.io/bricef/narrate:12.3.45"),
    ("v0.3.0-rc.1", "ghcr.io/bricef/narrate:0.3.0-rc.1"),  # pre-releases publish their own image
    ("", LATEST),  # uses: ./
    ("main", LATEST),
    ("728fcbd116d3fca6fa10c3752273ca874db40374", LATEST),
    ("v1-beta", LATEST),
    ("v0.1.0.1", LATEST),
    ("v0.1.0+build.5", LATEST),
    ("release/v1", LATEST),
])
def test_action_runs_the_image_of_its_own_release(tmp_path, ref, image):
    """@v0.1.0 runs the image 0.1.0 and @v0 runs 0, without an image input."""
    step = next(step for step in action()["runs"]["steps"] if step.get("id") == "image")
    assert step["env"] == {"IMAGE": "${{ inputs.image }}", "REF": "${{ github.action_ref }}"}

    def chosen(given):
        outputs = tmp_path / "outputs"
        outputs.write_text("")
        env = {"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(outputs), "IMAGE": given, "REF": ref}
        subprocess.run(["bash", "-e", "-c", step["run"]], env=env, check=True)
        return outputs.read_text()

    assert chosen("") == f"image={image}\n"
    assert chosen("narrate:ci") == "image=narrate:ci\n"  # the image input still decides


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


def test_only_release_tags_build_images():
    """v0.2.0 and v0.3.0-rc.1 run the workflow; the major tags it moves, such as v0, don't."""
    patterns = image_workflow()[True]["push"]["tags"]  # YAML reads the key on as True
    assert patterns == ["v[0-9]+.[0-9]+.[0-9]+", "v[0-9]+.[0-9]+.[0-9]+-*"]

    def runs(tag):  # GitHub's filter syntax: + is one or more, * anything but /, the rest as written
        return any(re.fullmatch(p.replace(".", r"\.").replace("*", "[^/]*"), tag) for p in patterns)

    assert all(map(runs, ["v0.1.0", "v1.10.2", "v0.3.0-rc.1"]))
    assert not any(map(runs, ["v0", "v1", "v0.1", "latest", "0.1.0"]))


def test_only_the_newest_release_of_a_series_moves_its_image_tags():
    """v0.2.0 publishes 0.2.0, 0.2 and 0; a re-run of v0.1.0 then publishes only 0.1.0 and 0.1."""
    steps = image_workflow()["jobs"]["publish"]["steps"]
    release = next(s for s in steps if s.get("id") == "release")
    meta = next(s for s in steps if s.get("id") == "meta")
    assert steps.index(release) < steps.index(meta)
    assert release["run"] == 'python3 scripts/release_tags.py newest "$GITHUB_REF_NAME" >> "$GITHUB_OUTPUT"'
    assert meta["with"]["tags"].splitlines() == [
        "type=raw,value=latest,enable={{is_default_branch}}",
        "type=semver,pattern={{version}}",
        "type=semver,pattern={{major}}.{{minor}},enable=${{ steps.release.outputs.newest-minor }}",
        "type=semver,pattern={{major}},enable=${{ steps.release.outputs.newest-major }}",
        "type=sha",
    ]


def test_a_release_moves_its_major_tag_once_its_image_has_passed():
    """The only job that can write to the repository, and only after the published image's checks."""
    workflow = image_workflow()
    job = workflow["jobs"]["major-tag"]
    assert job["needs"] == "published" and job["if"] == "startsWith(github.ref, 'refs/tags/v')"
    assert job["permissions"] == {"contents": "write"}
    assert "permissions" not in workflow
    assert [name for name, j in workflow["jobs"].items() if j["permissions"].get("contents") != "read"] == ["major-tag"]
    assert job["concurrency"] == "major-tag"  # one release at a time, so two can't race it backwards
    assert job["steps"][-1]["run"] == 'python3 scripts/release_tags.py move "$GITHUB_REF_NAME" "$GITHUB_SHA"'


# scripts/release_tags.py, against a bare repository standing in for GitHub
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
           "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com"}


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True, capture_output=True,
                          text=True).stdout.strip()


def release_tags(work, *args, check=True):
    result = subprocess.run([sys.executable, ROOT / "scripts/release_tags.py", *args], cwd=work, env=GIT_ENV,
                            capture_output=True, text=True)
    assert result.returncode == 0 or not check, result.stderr
    return result


@pytest.fixture
def repo(tmp_path):
    """A checkout, its origin, four commits, and v0.1.0 released on the first, with v0 on it."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", origin)
    git(tmp_path, "init", "-q", "-b", "main", work)
    git(work, "remote", "add", "origin", origin)
    commits = []
    for n in range(4):
        git(work, "commit", "-q", "--allow-empty", "-m", f"commit {n}")
        commits.append(git(work, "rev-parse", "HEAD"))
    tag(work, "v0.1.0", commits[0])
    tag(work, "v0", commits[0])
    return work, origin, commits


def tag(work, name, commit):
    git(work, "tag", "-f", "-a", name, "-m", name, commit)
    git(work, "push", "-q", "-f", "origin", f"refs/tags/{name}")


def at(origin, name):
    return git(origin, "rev-parse", f"{name}^{{commit}}")


def test_the_major_tag_moves_to_the_newest_release_only(repo):
    work, origin, (c0, c1, c2, c3) = repo
    tag(work, "v0.2.0", c1)
    assert "v0 moved to v0.2.0" in release_tags(work, "move", "v0.2.0", c1).stdout
    assert at(origin, "v0") == c1
    assert git(origin, "cat-file", "-t", "v0") == "tag"  # annotated, as made by hand
    assert "now v0.2.0" in git(origin, "tag", "-l", "--format=%(contents)", "v0")
    assert "already at v0.2.0" in release_tags(work, "move", "v0.2.0", c1).stdout  # a re-run

    # Never backwards: a re-run of an older release, a fix for an older series, a pre-release
    assert "v0.2.0 is newer than v0.1.0: v0 stays" in release_tags(work, "move", "v0.1.0", c0).stdout
    tag(work, "v0.1.1", c2)
    assert "v0.2.0 is newer than v0.1.1" in release_tags(work, "move", "v0.1.1", c2).stdout
    tag(work, "v0.3.0-rc.1", c3)
    assert "isn't a release" in release_tags(work, "move", "v0.3.0-rc.1", c3).stdout
    assert at(origin, "v0") == c1

    # A release re-tagged since its run started: the run for the new commit moves v0
    tag(work, "v0.2.0", c3)
    assert "no longer points at" in release_tags(work, "move", "v0.2.0", c1).stdout
    assert at(origin, "v0") == c1

    # A new major version starts its own tag
    tag(work, "v1.0.0", c2)
    release_tags(work, "move", "v1.0.0", c2)
    assert at(origin, "v1") == c2 and at(origin, "v0") == c1


def test_the_major_tag_move_can_be_tried_without_pushing(repo):
    work, origin, (c0, c1, *_) = repo
    tag(work, "v0.2.0", c1)
    out = release_tags(work, "move", "v0.2.0", "v0.2.0", "--dry-run").stdout  # the commit as a tag, by hand
    assert f"+ git tag --force --annotate v0 {c1}" in out and "+ git push --force origin refs/tags/v0" in out
    assert "v0 would move to v0.2.0" in out
    assert at(origin, "v0") == c0


def test_a_refused_push_fails_with_the_way_to_move_it_by_hand(repo):
    work, origin, (c0, c1, *_) = repo
    tag(work, "v0.2.0", c1)
    hook = origin / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    result = release_tags(work, "move", "v0.2.0", c1, check=False)
    assert result.returncode == 1
    assert "python3 scripts/release_tags.py move v0.2.0 v0.2.0" in result.stderr
    assert at(origin, "v0") == c0


def test_newest_says_which_image_tags_a_release_moves(repo):
    work, _, (c0, c1, c2, c3) = repo
    tag(work, "v0.2.0", c1)
    tag(work, "v0.1.1", c2)
    tag(work, "v0.3.0-rc.1", c3)

    def newest(ref):
        return release_tags(work, "newest", ref).stdout.split()

    assert newest("v0.2.0") == ["newest-major=true", "newest-minor=true"]
    assert newest("v0.1.1") == ["newest-major=false", "newest-minor=true"]  # 0.1, not 0
    assert newest("v0.1.0") == ["newest-major=false", "newest-minor=false"]
    assert newest("v0.3.0-rc.1") == newest("main") == ["newest-major=false", "newest-minor=false"]
