import pytest

from narrate import doctor
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


def test_doctor_passes_here(capsys):
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "ok   chromium" in out and "ok   ffmpeg libx264 encoder" in out
