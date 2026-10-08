import io
import json
import zipfile

import pytest
from PIL import Image

from narrate import media
from narrate.narakeet_cli import main

SCRIPT = b"---\nsize: 320x180\n---\n\n![](pic.png)\n\n(duration: 1)\n"


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "proj" / "script"
    folder.mkdir(parents=True)
    (folder / "source.md").write_bytes(SCRIPT)
    Image.new("RGB", (64, 36), "teal").save(folder / "pic.png")
    return folder


def zipped(folder):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for f in folder.iterdir():
            zf.write(f, f.name)
    return buffer.getvalue()


def built(path):
    return media.probe(path).duration == pytest.approx(1.0, abs=0.05)


def test_local_dir(project, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["--repository-type", "local-dir", "--repository", str(project.parent),
                 "--source", "script/source.md", "--tts", "silent"]) == 0
    assert built(tmp_path / "result.mp4")  # Narakeet's default output name


def test_local_zip(project, tmp_path):
    (tmp_path / "p.zip").write_bytes(zipped(project))
    out = tmp_path / "out.mp4"
    assert main(["--repository-type", "local-zip", "--repository", str(tmp_path / "p.zip"), "--source", "source.md",
                 "--output", str(out), "--api-key", "ignored", "--tts", "silent"]) == 0
    assert built(out)


def test_zip_url(project, tmp_path):
    archive = zipped(project)
    out = tmp_path / "out.mp4"
    assert main(["--repository-type", "zip-url", "--repository", "https://example.com/v1.zip", "--source", "source.md",
                 "--output", str(out), "--tts", "silent"], get=lambda url, *a: archive) == 0
    assert built(out)


def test_github_fetches_only_the_script_folder(project, tmp_path):
    files = {"script/source.md": SCRIPT, "script/pic.png": (project / "pic.png").read_bytes()}
    requested = []

    def fake_get(url, token=None, accept=None):
        requested.append(url)
        if url.endswith("/repos/owner/repo"):
            return json.dumps({"default_branch": "main"}).encode()
        if "/git/trees/" in url:
            tree = [{"path": p, "type": "blob"} for p in [*files, "other/huge.mp4"]]
            return json.dumps({"tree": tree}).encode()
        path = url.split("/contents/")[1].split("?")[0]
        assert token == "tok" and accept == "application/vnd.github.raw"
        return files[path]

    out = tmp_path / "out.mp4"
    assert main(["--repository-type", "github", "--repository", "owner/repo", "--source", "script/source.md",
                 "--github-token", "tok", "--output", str(out), "--tts", "silent"], get=fake_get) == 0
    assert built(out)
    assert not any("huge.mp4" in u for u in requested)
