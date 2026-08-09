from argparse import Namespace

import pytest

from tools.add_card import build_card

CARD = {
    "title": "Сен-Санс — Интродукция и рондо",
    "facts": ["Первый факт."],
    "fragments": [
        {"name": "Интродукция", "start": "10", "duration": "35", "audio_file_id": "первый"},
        {"name": "Рондо", "start": "233", "duration": "35", "audio_file_id": "второй"},
    ],
    "recording": {"performer": "Jonathan Vered", "source": "Musopen"},
}

def arguments(**overrides) -> Namespace:
    defaults = {
        "title": CARD["title"],
        "start": "231",
        "duration": "35",
        "fragment": None,
        "fact": [],
        "description": None,
        "performer": "Jonathan Vered",
        "source": "Musopen",
        "distractor": [],
        "append": False,
        "replace_fragment": None,
    }

    return Namespace(**{**defaults, **overrides})

def test_replace_fragment_keeps_the_neighbours():
    card = build_card(arguments(replace_fragment=1), "новый", CARD)

    assert [fragment["audio_file_id"] for fragment in card["fragments"]] == ["первый", "новый"]

def test_replace_fragment_writes_the_new_offset():
    card = build_card(arguments(replace_fragment=1), "новый", CARD)

    assert card["fragments"][1]["start"] == "231"

def test_replace_fragment_keeps_the_old_name():
    card = build_card(arguments(replace_fragment=1), "новый", CARD)

    assert card["fragments"][1]["name"] == "Рондо"

def test_replace_fragment_renames_when_asked():
    card = build_card(arguments(replace_fragment=1, fragment="Рондо каприччиозо"), "новый", CARD)

    assert card["fragments"][1]["name"] == "Рондо каприччиозо"

def test_replace_counts_from_the_end_too():
    card = build_card(arguments(replace_fragment=-2), "новый", CARD)

    assert [fragment["audio_file_id"] for fragment in card["fragments"]] == ["новый", "второй"]

def test_replace_fragment_leaves_the_facts_alone():
    card = build_card(arguments(replace_fragment=1), "новый", CARD)

    assert card["facts"] == ["Первый факт."]

def test_replace_keeps_the_credit_on_a_fragment_that_had_its_own():
    card = dict(CARD)
    card["fragments"] = [
        CARD["fragments"][0],
        {**CARD["fragments"][1], "recording": {"performer": "Другой", "source": "IMSLP"}},
    ]

    rebuilt = build_card(arguments(replace_fragment=1, performer="Третий"), "новый", card)

    assert rebuilt["fragments"][1]["recording"] == {"performer": "Третий", "source": "Musopen"}
    assert rebuilt["recording"] == CARD["recording"]

def test_append_still_adds_a_fragment():
    card = build_card(arguments(append=True, fragment="Кода"), "новый", CARD)

    assert len(card["fragments"]) == 3
    assert card["fragments"][-1]["name"] == "Кода"

def test_without_append_the_new_fragment_replaces_them_all():
    card = build_card(arguments(fragment="Рондо"), "новый", CARD)

    assert [fragment["audio_file_id"] for fragment in card["fragments"]] == ["новый"]
