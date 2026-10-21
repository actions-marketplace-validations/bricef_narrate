import hashlib
import io
import sys
import tarfile

import pytest

from narrate import media


def test_asset_per_platform():
    assert media.ffmpeg_asset("x86_64", "linux") == "ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz"
    assert media.ffmpeg_asset("aarch64", "linux") == "ffmpeg-n9.0-latest-linuxarm64-gpl-9.0.tar.xz"
    assert media.ffmpeg_asset("x86_64", "darwin") is None


def fake_release(binary: bytes, checksum: str | None = None):
    asset = media.ffmpeg_asset()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as tar:
        info = tarfile.TarInfo(f"{asset[:-7]}/bin/ffmpeg")
        info.size = len(binary)
        tar.addfile(info, io.BytesIO(binary))
    archive = buffer.getvalue()
    digest = checksum or hashlib.sha256(archive).hexdigest()
    files = {"checksums.sha256": f"{digest}  {asset}\n".encode(), asset: archive}
    return lambda url: io.BytesIO(files[url.rsplit("/", 1)[1]])


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_TOOLS", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")  # one with a managed ffmpeg, wherever the tests run
    monkeypatch.setattr(media.platform, "machine", lambda: "x86_64")
    return tmp_path


def test_download_is_verified_and_extracted(cache):
    exe = media.ensure_ffmpeg(log=lambda _: None, opener=fake_release(b"#!/bin/sh\necho ok\n"))
    assert exe == media.managed_ffmpeg() and exe.read_bytes().startswith(b"#!/bin/sh")
    assert exe.stat().st_mode & 0o111


def test_checksum_mismatch_is_rejected(cache):
    with pytest.raises(media.MediaError, match="checksum mismatch"):
        media.ensure_ffmpeg(log=lambda _: None, opener=fake_release(b"binary", checksum="0" * 64))
    assert not media.managed_ffmpeg().exists()


def executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def mac(tmp_path, monkeypatch):
    """A Mac with nothing installed: no NARRATE_FFMPEG, no managed ffmpeg, no Homebrew ffmpeg-full,
    and an empty PATH. Yields where Homebrew would keep ffmpeg-full, and the PATH folder."""
    monkeypatch.delenv("NARRATE_FFMPEG", raising=False)
    monkeypatch.setenv("NARRATE_TOOLS", str(tmp_path / "tools"))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    brewed = tmp_path / "homebrew" / "opt" / "ffmpeg-full" / "bin" / "ffmpeg"
    monkeypatch.setattr(media, "HOMEBREW_FFMPEG", (str(tmp_path / "elsewhere"), str(brewed)))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(media.platform, "machine", lambda: "arm64")
    media.ffmpeg.cache_clear()
    yield brewed, tmp_path / "bin"
    media.ffmpeg.cache_clear()


def test_no_ffmpeg_says_how_to_get_one(mac):
    with pytest.raises(media.MediaError) as e:
        media.ffmpeg()
    message = str(e.value)
    assert "no ffmpeg on PATH" in message and "darwin/arm64" in message
    assert message.endswith("Fix: brew install ffmpeg-full")


def test_elsewhere_the_fix_names_narrate_ffmpeg_once(mac, monkeypatch):
    monkeypatch.setattr(sys, "platform", "freebsd14")
    with pytest.raises(media.MediaError) as e:
        media.ffmpeg()
    assert str(e.value).count("NARRATE_FFMPEG") == 1


def test_uses_the_ffmpeg_on_path_where_narrate_has_none(mac, capsys):
    _, path = mac
    exe = executable(path / "ffmpeg")
    assert media.ffmpeg() == exe
    assert capsys.readouterr().err == ""  # the expected choice here, not a fallback worth a warning


def test_homebrews_ffmpeg_full_comes_before_path(mac):
    brewed, path = mac
    executable(path / "ffmpeg")
    exe = executable(brewed)
    assert media.find_ffmpeg() == ("Homebrew", exe)


def test_only_on_macos(mac, monkeypatch):
    brewed, path = mac
    executable(brewed)
    exe = executable(path / "ffmpeg")
    monkeypatch.setattr(sys, "platform", "freebsd14")
    assert media.find_ffmpeg() == ("PATH", exe)


def test_narrate_ffmpeg_comes_before_homebrew(mac, monkeypatch):
    executable(mac[0])
    monkeypatch.setenv("NARRATE_FFMPEG", "/somewhere/ffmpeg")
    assert media.find_ffmpeg() == ("NARRATE_FFMPEG", "/somewhere/ffmpeg")
