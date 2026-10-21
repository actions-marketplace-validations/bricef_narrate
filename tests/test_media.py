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


@pytest.fixture
def no_managed_ffmpeg(tmp_path, monkeypatch):
    """A Mac with nothing installed: no NARRATE_FFMPEG, no managed ffmpeg, and an empty PATH."""
    monkeypatch.delenv("NARRATE_FFMPEG", raising=False)
    monkeypatch.setenv("NARRATE_TOOLS", str(tmp_path / "tools"))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(media.platform, "machine", lambda: "arm64")
    media.ffmpeg.cache_clear()
    yield tmp_path / "bin"
    media.ffmpeg.cache_clear()


def test_no_ffmpeg_says_how_to_get_one(no_managed_ffmpeg):
    with pytest.raises(media.MediaError) as e:
        media.ffmpeg()
    message = str(e.value)
    assert "no ffmpeg on PATH" in message and "darwin/arm64" in message
    assert "brew install ffmpeg-full" in message and message.count("NARRATE_FFMPEG") == 1


def test_uses_the_ffmpeg_on_path_where_narrate_has_none(no_managed_ffmpeg, capsys):
    no_managed_ffmpeg.mkdir()
    exe = no_managed_ffmpeg / "ffmpeg"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    assert media.ffmpeg() == str(exe)
    assert capsys.readouterr().err == ""  # the expected choice here, not a fallback worth a warning
