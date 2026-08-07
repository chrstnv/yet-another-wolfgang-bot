import json
from pathlib import Path

import pytest

import content

RECORDING = {"performer": "Кто-то", "source": "Откуда-то"}

def playable(**overrides) -> dict:
    card = {
        "title": "Название",
        "fragment": "Фрагмент",
        "facts": ["Факт"],
        "audio_file_id": "x" * 50,
        "recording": dict(RECORDING),
    }
    card.update(overrides)

    return card

def write_library(directory: Path, cards: dict) -> Path:
    cards_dir = directory / "cards"
    cards_dir.mkdir()

    for card_id, body in cards.items():
        path = cards_dir / f"{card_id}.json"
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")

    return cards_dir

def test_id_comes_from_the_file_name(tmp_path):
    cards_dir = write_library(tmp_path, {"bach-badinerie": playable()})

    library = content.load_library(cards_dir)

    assert library["cards"][0]["id"] == "bach-badinerie"

def test_only_cards_with_audio_are_playable(tmp_path):
    cards_dir = write_library(tmp_path, {
        "with-audio": playable(),
        "without-audio": {"title": "Только вариант ответа"},
    })

    library = content.load_library(cards_dir)

    assert len(library["cards"]) == 2
    assert [card["id"] for card in library["playable"]] == ["with-audio"]

def test_cards_are_indexed_by_id(tmp_path):
    cards_dir = write_library(tmp_path, {"one": playable(), "two": playable()})

    library = content.load_library(cards_dir)

    assert set(library["by_id"]) == {"one", "two"}

def test_missing_directory_is_reported(tmp_path):
    with pytest.raises(RuntimeError, match="не найден"):
        content.load_library(tmp_path / "nope")

def test_empty_directory_is_reported(tmp_path):
    cards_dir = write_library(tmp_path, {})

    with pytest.raises(RuntimeError, match="ни одной карточки"):
        content.load_library(cards_dir)

def test_broken_card_stops_loading(tmp_path):
    cards_dir = write_library(tmp_path, {"no-title": {"fragment": "Фрагмент"}})

    with pytest.raises(RuntimeError, match="нет title"):
        content.load_library(cards_dir)

def test_cards_directory_needs_the_env_variable(monkeypatch):
    monkeypatch.delenv("CONTENT_PATH", raising=False)

    with pytest.raises(RuntimeError, match="CONTENT_PATH"):
        content.cards_directory()

def test_no_problems_in_a_healthy_library():
    cards = [
        dict(playable(), id="one", distractors=["two"]),
        {"id": "two", "title": "Второй"},
    ]

    assert content.find_problems(cards) == []

def test_unknown_distractor_is_a_problem():
    cards = [dict(playable(), id="one", distractors=["ghost"])]

    assert content.find_problems(cards) == ["one: ловушка «ghost» не существует"]

def test_self_distractor_is_a_problem():
    cards = [dict(playable(), id="one", distractors=["one"])]

    assert content.find_problems(cards) == ["one: карточка указана ловушкой сама себе"]

@pytest.mark.parametrize("field", ["fragment", "facts", "recording"])
def test_playable_card_without_required_field_is_a_problem(field):
    card = playable(id="one")
    card[field] = None

    problems = content.find_problems([card])

    assert any(field in problem for problem in problems)

def test_incomplete_recording_is_a_problem():
    card = playable(id="one", recording={"performer": "Кто-то"})

    assert content.find_problems([card]) == ["one: в recording нет source"]

def test_card_without_audio_needs_nothing_but_a_title():
    assert content.find_problems([{"id": "one", "title": "Название"}]) == []
