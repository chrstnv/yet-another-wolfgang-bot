from pathlib import Path

from tools.dev_library import (
    find_audio, playable_card, silent_card, sound_files, words,
)

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

def test_a_number_in_the_name_is_not_a_detail():
    """У пятой симфонии и девятой общего два слова из двух."""
    files = [
        (words("Beethoven - Ode to Joy - Symphony No. 9, Op. 125"), Path("/звуки/девятая.mp3")),
        (words("Beethoven – Symphony no. 5 in Cm, Op. 67"), Path("/звуки/пятая.flac")),
    ]

    assert find_audio("beethoven-symphony-5", files) == Path("/звуки/пятая.flac")

def test_a_card_with_a_number_skips_files_without_it():
    files = [(words("Beethoven - Ode to Joy - Symphony No. 9"), Path("/звуки/девятая.mp3"))]

    assert find_audio("beethoven-symphony-5", files) is None

def test_a_roman_movement_number_counts_as_a_number():
    """Часть пишут то «No. 3», то «III» — это одно и то же."""
    files = [
        (words("Beethoven - Moonlight Sonata Op. 27 No. 2 - III. Presto"),
         Path("/звуки/престо.mp3")),
        (words("Beethoven - Moonlight Sonata Op. 27 No. 2 - I. Adagio sostenuto"),
         Path("/звуки/адажио.mp3")),
    ]

    assert find_audio("beethoven-moonlight-3", files) == Path("/звуки/престо.mp3")
    assert find_audio("beethoven-moonlight-1", files) == Path("/звуки/адажио.mp3")

def test_sources_are_not_only_mp3(tmp_path):
    """Половина библиотеки лежит во flac; чужой кодек cut_fragment перекодирует."""
    for name in ("раз.mp3", "два.flac", "три.m4a", "четыре.txt"):
        (tmp_path / name).touch()

    assert sorted(path.suffix for path in sound_files(tmp_path)) == [".flac", ".m4a", ".mp3"]

def test_a_generic_pair_of_words_is_not_a_match():
    """«Скрипичный концерт» есть у половины композиторов."""
    files = [(words("Vivaldi – Violin Concerto in F minor, RV 297 'Winter'"),
              Path("/звуки/вивальди.mp3"))]

    assert find_audio("beethoven-violin-concerto", files) is None

def test_the_composer_must_be_in_the_file_name():
    files = [
        (words("Vivaldi – Violin Concerto in F minor"), Path("/звуки/вивальди.mp3")),
        (words("Beethoven - Violin Concerto in D major"), Path("/звуки/бетховен.mp3")),
    ]

    assert find_audio("beethoven-violin-concerto", files) == Path("/звуки/бетховен.mp3")

def test_accents_do_not_split_a_surname():
    """«Dvořák» разложился бы на «dvor» и «ak», не совпав ни с чем."""
    assert "dvorak" in words("Antonín_Dvořák_Symphony_no._9")
    assert "faure" in words("Fauré – Élégie")

def test_articles_do_not_count_as_a_match():
    """«mozart» и «the» — уже два общих слова, а опознано ничего не было."""
    files = [(words("Mozart – Overture to The marriage of Figaro, K. 492"),
              Path("/звуки/фигаро.mp3"))]

    assert find_audio("mozart-queen-of-the-night", files) is None
