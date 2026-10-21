import sys

import pytest

from narrate import doctor, media
from narrate.cli import main
from narrate.doctor import SetupError, explain_browser_error
from narrate.frames import FrameRenderer


def test_explains_a_missing_browser():
    msg = "BrowserType.launch: Executable doesn't exist at /x/chrome-headless-shell\nLooks like Playwright was just installed"
    assert "playwright install chromium" in explain_browser_error(msg)


def test_explains_missing_libraries_and_names_them():
    msg = ("BrowserType.launch: Target page, context or browser has been closed\n"
           "/x/chrome-headless-shell: error while loading shared libraries: libatk-1.0.so.0: cannot open shared object file")
    text = explain_browser_error(msg)
    assert "system libraries are missing" in text and "install-deps" in text


def test_renderer_turns_launch_failures_into_setup_errors(monkeypatch, tmp_path):
    from playwright.sync_api import Error

    def broken_launch(playwright, args):
        raise SetupError(explain_browser_error("error while loading shared libraries: libgbm.so.1: x"))

    monkeypatch.setattr(doctor, "launch_chromium", broken_launch)
    with pytest.raises(SetupError, match="install-deps"):
        with FrameRenderer(64, 64, tmp_path):
            pass
    assert Error  # the real exception type the helper wraps


@pytest.mark.kokoro  # a fully set-up machine, models included
def test_doctor_passes_here(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "ok   chromium" in out and "ok   ffmpeg libx264 encoder" in out


def test_models_skips_ffmpeg_when_one_is_configured(monkeypatch, tmp_path):
    """The container image sets NARRATE_FFMPEG; `narrate models` mustn't fetch another 150 MB."""
    from narrate import cli, stt

    monkeypatch.setenv("NARRATE_FFMPEG", "/usr/local/bin/ffmpeg")
    monkeypatch.setattr(cli, "ensure_models", lambda: tmp_path)
    monkeypatch.setattr(stt, "ensure_model", lambda: tmp_path)
    monkeypatch.setattr(media, "ensure_ffmpeg", lambda: pytest.fail("downloaded ffmpeg"))
    assert main(["models"]) == 0


def test_files_still_to_download_are_not_faults(monkeypatch, tmp_path):
    """A fresh install passes: ffmpeg and the Kokoro model download on the first build."""
    monkeypatch.delenv("NARRATE_FFMPEG", raising=False)
    monkeypatch.setenv("NARRATE_TOOLS", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")  # one with a managed ffmpeg
    monkeypatch.setattr(media.platform, "machine", lambda: "x86_64")
    ffmpeg, = doctor.check_ffmpeg()
    kokoro = doctor.check_kokoro()
    assert ffmpeg.ok and "first build" in ffmpeg.detail
    assert kokoro.ok and "first Kokoro build" in kokoro.detail


# -- the ffmpeg a build will use (#93) ------------------------------------------

FULL = ("subtitles", "xfade", "rubberband")


def fake_ffmpeg(folder, version="9.0.2", filters=FULL, encoders=("libx264",)):
    """A script that answers doctor's three questions the way ffmpeg does."""
    folder.mkdir(parents=True, exist_ok=True)

    def listing(names):
        return "; ".join(f"echo ' ... {name}  V->V  about it'" for name in names) or ":"

    exe = folder / "ffmpeg"
    exe.write_text(f"""#!/bin/sh
case "$2" in
  -version) echo 'ffmpeg version {version} Copyright (c) 2000-2026 the FFmpeg developers' ;;
  -filters) {listing(filters)} ;;
  -encoders) {listing(encoders)} ;;
esac
""")
    exe.chmod(0o755)
    return exe


@pytest.fixture
def mac(tmp_path, monkeypatch):
    """A Mac, where narrate has no ffmpeg of its own; PATH is an empty folder to put one in."""
    monkeypatch.delenv("NARRATE_FFMPEG", raising=False)
    monkeypatch.setenv("NARRATE_TOOLS", str(tmp_path / "tools"))
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(media.platform, "machine", lambda: "arm64")
    return tmp_path / "bin"


def test_no_ffmpeg_for_this_platform_is_a_fault(mac):
    """It used to say ffmpeg would download on the first build, which then failed."""
    ffmpeg, = doctor.check_ffmpeg()
    assert not ffmpeg.ok and "darwin/arm64" in ffmpeg.detail
    assert "brew install ffmpeg-full" in ffmpeg.fix and "NARRATE_FFMPEG" in ffmpeg.fix


def test_elsewhere_the_fix_is_narrate_ffmpeg(mac, monkeypatch):
    monkeypatch.setattr(sys, "platform", "freebsd14")
    ffmpeg, = doctor.check_ffmpeg()
    assert not ffmpeg.ok and ffmpeg.fix.startswith("set NARRATE_FFMPEG")


def test_checks_the_ffmpeg_on_path_where_narrate_has_none(mac):
    exe = fake_ffmpeg(mac)
    checks = doctor.check_ffmpeg()
    assert all(c.ok for c in checks) and len(checks) == 5
    assert checks[0].detail == f"ffmpeg version 9.0.2 Copyright (c) 2000-2026 the FFmpeg developers ({exe})"


def test_homebrews_plain_ffmpeg_lacks_libass_and_rubberband(mac):
    fake_ffmpeg(mac, filters=("xfade",))
    failed = {c.name: c.fix for c in doctor.check_ffmpeg() if not c.ok}
    assert set(failed) == {"ffmpeg subtitles filter (libass)", "ffmpeg rubberband filter (pitch)"}
    assert all("brew install ffmpeg-full" in fix for fix in failed.values())


def test_an_ffmpeg_older_than_narrates_fails(mac):
    fake_ffmpeg(mac, version="7.0.2")
    ffmpeg, *features = doctor.check_ffmpeg()
    assert not ffmpeg.ok and "older than 9.0" in ffmpeg.detail and "crashes" in ffmpeg.detail
    assert all(c.ok for c in features)


def test_a_build_from_git_has_no_version_to_compare(mac):
    fake_ffmpeg(mac, version="N-121000-g0123456789")
    assert all(c.ok for c in doctor.check_ffmpeg())


def test_narrate_ffmpeg_comes_first(mac, tmp_path, monkeypatch):
    fake_ffmpeg(mac, version="7.0.2")
    chosen = fake_ffmpeg(tmp_path / "chosen")
    monkeypatch.setenv("NARRATE_FFMPEG", str(chosen))
    ffmpeg, *_ = doctor.check_ffmpeg()
    assert ffmpeg.ok and str(chosen) in ffmpeg.detail


def test_where_narrate_has_its_own_the_fix_is_to_use_it(mac, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("NARRATE_FFMPEG", str(fake_ffmpeg(tmp_path / "chosen", filters=("xfade", "subtitles"))))
    failed = [c for c in doctor.check_ffmpeg() if not c.ok]
    assert [c.name for c in failed] == ["ffmpeg rubberband filter (pitch)"]
    assert failed[0].fix.startswith("unset NARRATE_FFMPEG")


def test_a_missing_narrate_ffmpeg_is_a_fault(mac, tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATE_FFMPEG", str(tmp_path / "nowhere" / "ffmpeg"))
    ffmpeg, = doctor.check_ffmpeg()
    assert not ffmpeg.ok and "nowhere" in ffmpeg.detail and "NARRATE_FFMPEG" in ffmpeg.fix
