from pathlib import Path

from tools.dev_library import find_audio, playable_card, silent_card, words

FILES = [
    (words("Bach – Toccata and Fugue in Dm, BWV 565"), Path("/звуки/toccata.mp3")),
    (words("Grieg - In the Hall Of The Mountain King"), Path("/звуки/grieg.mp3")),
]

CARD = {
    "id": "bach-toccata-and-fugue",
    "title": "Бах — Токката и фуга ре минор",
    "composer": "Бах",
    "difficulty": 2,
    "facts": ["Факт."],
    "distractors": ["verdi-aida"],
    "fragments": [{"name": "Токката", "audio_file_id": "старый"}],
    "recording": {"performer": "Кто-то", "source": "Откуда-то"},
}

def test_the_file_is_found_by_the_words_in_common():
    assert find_audio("bach-toccata-and-fugue", FILES) == Path("/звуки/toccata.mp3")

def test_one_word_in_common_is_not_enough():
    """Одна фамилия композитора совпадает у половины библиотеки."""
    assert find_audio("bach-badinerie", FILES) is None

def test_a_card_without_a_source_is_left_alone():
    assert find_audio("verdi-aida", FILES) is None

def test_only_the_audio_identity_changes():
    copy = playable_card(CARD, "новый")

    assert copy["fragments"][0]["audio_file_id"] == "новый"
    assert copy["fragments"][0]["name"] == "Токката"
    assert copy["facts"] == ["Факт."]
    assert copy["recording"] == {"performer": "Кто-то", "source": "Откуда-то"}

def test_the_identifier_is_not_written_into_the_card():
    """Он берётся из имени файла — один источник правды."""
    assert "id" not in playable_card(CARD, "новый")

def test_a_card_keeps_only_one_fragment():
    many = {**CARD, "fragments": [
        {"name": "Первый", "audio_file_id": "раз"},
        {"name": "Второй", "audio_file_id": "два"},
    ]}

    assert len(playable_card(many, "новый")["fragments"]) == 1

def test_a_trap_needs_nothing_but_a_name():
    assert silent_card(CARD) == {"title": "Бах — Токката и фуга ре минор", "composer": "Бах"}
