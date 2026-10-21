import stat
import zipfile

import pytest
from PIL import Image

from narrate import media, project
from narrate.cli import main


def make_project(tmp_path, files: dict[str, bytes], name="project.zip"):
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w") as zf:
        for path, data in files.items():
            zf.writestr(path, data)
    return archive


def png_bytes(tmp_path):
    Image.new("RGB", (64, 36), "purple").save(tmp_path / "p.png")
    return (tmp_path / "p.png").read_bytes()


def test_builds_a_zip_project(tmp_path, monkeypatch):
    archive = make_project(tmp_path, {
        "script.md": b"---\nsize: 320x180\n---\n\n![](img/pic.png)\n\n(duration: 1)\n",
        "img/pic.png": png_bytes(tmp_path),
    })
    monkeypatch.chdir(tmp_path)
    assert main(["build", str(archive), "--tts", "silent", "-q"]) == 0
    assert media.probe(tmp_path / "script.mp4").duration == pytest.approx(1.0, abs=0.05)


def test_source_picks_between_several_scripts(tmp_path, monkeypatch, capsys):
    archive = make_project(tmp_path, {"a.md": b"```\nA\n```\n", "b/b.txt": b"```\nB\n```\n"})
    monkeypatch.chdir(tmp_path)
    assert main(["build", str(archive), "--tts", "silent", "-q"]) == 2
    assert "a.md, b/b.txt" in capsys.readouterr().err
    assert main(["build", str(archive), "--source", "b/b.txt", "--tts", "silent", "-q"]) == 0
    assert (tmp_path / "b.mp4").exists()


@pytest.mark.parametrize("bad", ["../escape.md", "/abs.md"])
def test_unsafe_paths_are_rejected(tmp_path, bad):
    archive = make_project(tmp_path, {bad: b"x"})
    with pytest.raises(project.ProjectError, match="unsafe path"):
        with project.unpacked(archive):
            pass


def test_symlinks_are_rejected(tmp_path):
    archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        info = zipfile.ZipInfo("script.md")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(project.ProjectError, match="symbolic links"):
        with project.unpacked(archive):
            pass


def test_hidden_files_are_left_out(tmp_path):
    """A project's .env, .git and the like aren't unpacked (#93); narrate's own .narrate/ folders are."""
    archive = make_project(tmp_path, {
        "p/script.md": b"Hello there.\n", ".env": b"NARRATE_FFMPEG=planted\n", "p/.env": b"NODE_OPTIONS=planted\n",
        "p/.git/config": b"[core]\n", "p/.DS_Store": b"x", "__MACOSX/p/._script.md": b"x",
        "p/.narrate/generated/web/kept.png": b"png", "p/.narrate/.env": b"LD_PRELOAD=planted\n",
    })
    folder = tmp_path / "unpacked"
    assert project.extract(archive, folder) == folder / "p" / "script.md"
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) == [
        "p/.narrate/generated/web/kept.png", "p/script.md"]


def test_source_must_be_inside_the_archive(tmp_path):
    archive = make_project(tmp_path, {"script.md": b"x"})
    with pytest.raises(project.ProjectError, match="not in the archive"):
        with project.unpacked(archive, "../outside.md"):
            pass
