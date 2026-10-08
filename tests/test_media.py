import hashlib
import io
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
    monkeypatch.setenv("NARRATE_CACHE", str(tmp_path))
    return tmp_path


def test_download_is_verified_and_extracted(cache):
    exe = media.ensure_ffmpeg(log=lambda _: None, opener=fake_release(b"#!/bin/sh\necho ok\n"))
    assert exe == media.managed_ffmpeg() and exe.read_bytes().startswith(b"#!/bin/sh")
    assert exe.stat().st_mode & 0o111


def test_checksum_mismatch_is_rejected(cache):
    with pytest.raises(media.MediaError, match="checksum mismatch"):
        media.ensure_ffmpeg(log=lambda _: None, opener=fake_release(b"binary", checksum="0" * 64))
    assert not media.managed_ffmpeg().exists()
