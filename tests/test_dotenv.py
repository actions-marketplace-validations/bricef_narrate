"""A .env sets only ELEVENLABS_API_KEY (#93): it comes with its folder, which may not be yours."""

import os

import pytest

from narrate.cli import DOTENV, load_dotenv, main

KEY = "ELEVENLABS_API_KEY"
OTHERS = ("NARRATE_FFMPEG", "NODE_OPTIONS", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "NARRATE_ALLOW_LOCAL_NETWORK")


@pytest.fixture(autouse=True)
def unset(monkeypatch):
    """None of them set, and each put back as it was afterwards, whatever a test sets."""
    for name in (KEY, *OTHERS, DOTENV):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


def dotenv(folder, **values) -> None:
    folder.mkdir(exist_ok=True)
    (folder / ".env").write_text("".join(f"{name}={value}\n" for name, value in values.items()))


def test_only_the_elevenlabs_key_is_read(tmp_path, capsys):
    dotenv(tmp_path, **dict.fromkeys(OTHERS, "planted"), ELEVENLABS_API_KEY="'sk_folder'")
    load_dotenv(tmp_path)
    assert os.environ[KEY] == "sk_folder"
    assert not [name for name in OTHERS if name in os.environ]
    [warning] = capsys.readouterr().err.splitlines()
    assert warning.startswith(f"warning: {tmp_path.resolve() / '.env'}: ignoring ")
    assert all(name in warning for name in OTHERS) and ".env only sets ELEVENLABS_API_KEY" in warning
    assert "planted" not in warning  # names, never values


def test_variables_already_set_win(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(KEY, "sk_mine")
    (tmp_path / ".env").write_text("# a comment\n\nELEVENLABS_API_KEY=sk_folder\n")
    load_dotenv(tmp_path, tmp_path)
    assert os.environ[KEY] == "sk_mine" and capsys.readouterr().err == ""


def test_narrate_dotenv_0_reads_none(tmp_path, monkeypatch):
    monkeypatch.setenv(DOTENV, "0")
    dotenv(tmp_path, ELEVENLABS_API_KEY="sk_folder")
    load_dotenv(tmp_path)
    assert KEY not in os.environ


def test_narrate_reads_the_env_where_it_runs_and_beside_the_script(tmp_path, monkeypatch, capsys):
    here, project = tmp_path / "here", tmp_path / "project"
    dotenv(here, ELEVENLABS_API_KEY="sk_here", NODE_OPTIONS="planted")
    dotenv(project, ELEVENLABS_API_KEY="sk_project", NARRATE_FFMPEG="planted", LD_PRELOAD="planted")
    (project / "script.md").write_text("Hello there.\n")
    monkeypatch.chdir(here)
    assert main(["check", str(project / "script.md")]) == 0
    assert os.environ[KEY] == "sk_here"  # the folder it runs from is read first
    assert not [name for name in OTHERS if name in os.environ]
    assert capsys.readouterr().err.count(".env only sets ELEVENLABS_API_KEY") == 2
