from argparse import Namespace


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
        "fade": None,
        "as_is": False,
        "license": None,
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

def test_fade_is_recorded_only_when_chosen_by_hand():
    automatic = build_card(arguments(replace_fragment=1), "новый", CARD)
    by_hand = build_card(arguments(replace_fragment=1, fade=0.5), "новый", CARD)

    assert "fade" not in automatic["fragments"][1]
    assert by_hand["fragments"][1]["fade"] == 0.5

def test_fade_length_follows_the_offset_when_not_given():
    from tools.add_card import FADE_IN, fade_length

    assert fade_length(arguments(start="200")) == FADE_IN
    assert fade_length(arguments(start="2.1")) == 0.0

def test_fade_length_obeys_a_hand_picked_value():
    from tools.add_card import fade_length

    assert fade_length(arguments(start="200", fade=0.5)) == 0.5
    assert fade_length(arguments(start="200", fade=0.0)) == 0.0

def test_as_is_fragment_records_no_offset():
    card = build_card(arguments(as_is=True, fragment="Интермеццо"), "новый", None)
    fragment = card["fragments"][0]

    assert fragment["as_is"] is True
    assert "start" not in fragment and "duration" not in fragment

def test_licence_goes_onto_the_recording_when_given():
    card = build_card(arguments(license="CC BY-NC-ND 4.0"), "новый", None)

    assert card["recording"]["license"] == "CC BY-NC-ND 4.0"

def test_recording_has_no_licence_field_by_default():
    assert "license" not in build_card(arguments(), "новый", None)["recording"]
