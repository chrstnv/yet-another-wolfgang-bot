from pathlib import Path

import pytest

from tools.audio_folders import audio_folders

def test_the_flag_names_the_folders(monkeypatch):
    monkeypatch.setenv("AUDIO_PATH", "/переменная")

    assert audio_folders([Path("/флаг"), Path("/ещё")]) == [Path("/флаг"), Path("/ещё")]

def test_the_variable_is_taken_when_the_flag_is_silent(monkeypatch):
    monkeypatch.setenv("AUDIO_PATH", "/переменная")

    assert audio_folders(None) == [Path("/переменная")]

def test_the_home_sign_is_expanded(monkeypatch):
    monkeypatch.setenv("AUDIO_PATH", "~/звуки")

    assert audio_folders(None) == [Path.home() / "звуки"]

def test_nothing_named_at_all(monkeypatch):
    monkeypatch.delenv("AUDIO_PATH", raising=False)

    with pytest.raises(RuntimeError, match="AUDIO_PATH"):
        audio_folders(None)
