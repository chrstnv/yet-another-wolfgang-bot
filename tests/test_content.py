import json
from pathlib import Path

import pytest

import content

RECORDING = {"performer": "Кто-то", "source": "Откуда-то"}

def playable(**overrides) -> dict:
    card = {
        "title": "Название",
        "fragments": [{"name": "Фрагмент", "audio_file_id": "x" * 50}],
        "facts": ["Факт"],
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

@pytest.mark.parametrize("field", ["facts", "recording"])
def test_playable_card_without_required_field_is_a_problem(field):
    card = playable(id="one")
    card[field] = None

    problems = content.find_problems([card])

    assert any(field in problem for problem in problems)

def test_incomplete_recording_is_a_problem():
    card = playable(id="one", recording={"performer": "Кто-то"})

    assert content.find_problems([card]) == ["one: у фрагмента 1 в recording нет source"]

def test_card_without_audio_needs_nothing_but_a_title():
    assert content.find_problems([{"id": "one", "title": "Название"}]) == []

def test_fragment_recording_satisfies_the_check():
    card = playable(id="one")
    del card["recording"]
    card["fragments"][0]["recording"] = dict(RECORDING)

    assert content.find_problems([card]) == []

def test_fragment_without_any_recording_is_a_problem():
    card = playable(id="one")
    del card["recording"]

    problems = content.find_problems([card])

    assert any("recording" in problem for problem in problems)

def flaws_of(**card):
    return content.find_flaws([{"id": "card", **card}])

def test_flaws_catch_a_description_that_starts_with_a_word_from_the_title():
    found = flaws_of(
        title="Бетховен — увертюра «Кориолан»",
        description="Увертюра к трагедии о римском полководце.",
        fragments=[{"name": "Увертюра", "start": "0", "audio_file_id": "x"}],
        facts=["Факт."],
    )

    assert found["описание повторяет название"]

def test_flaws_leave_a_description_that_continues_the_title():
    found = flaws_of(
        title="Бетховен — увертюра «Кориолан»",
        description="Написана к трагедии о римском полководце.",
        fragments=[{"name": "Увертюра", "start": "0", "audio_file_id": "x"}],
        facts=["Факт."],
    )

    assert not found["описание повторяет название"]

def test_flaws_catch_a_description_retelling_its_fact():
    found = flaws_of(
        title="Дворжак — Симфония №9",
        description="Написана в Нью-Йорке, где Дворжак руководил консерваторией.",
        fragments=[{"name": "Финал", "start": "0", "audio_file_id": "x"}],
        facts=["Симфонию Дворжак написал в Нью-Йорке, где руководил консерваторией."],
    )

    assert found["описание пересказывает факт"]

def test_flaws_catch_a_fact_leaning_on_its_neighbour():
    found = flaws_of(
        title="Глинка — «Жаворонок»",
        fragments=[{"name": "Начало", "start": "0", "audio_file_id": "x"}],
        facts=["Той же весной он сочинил ещё один романс."],
    )

    assert found["факт опирается на соседний"]

def test_flaws_catch_titles_that_collide_when_cut_short():
    found = content.find_flaws([
        {"id": "one", "title": "Рахманинов — Концерт для фортепиано №2"},
        {"id": "two", "title": "Рахманинов — Концерт для фортепиано №3"},
    ])

    assert found["названия сливаются при обрезке"]

def test_flaws_leave_titles_that_differ_within_the_visible_part():
    found = content.find_flaws([
        {"id": "one", "title": "Рахманинов — Концерт №2 для фортепиано"},
        {"id": "two", "title": "Рахманинов — Концерт №3 для фортепиано"},
    ])

    assert not found["названия сливаются при обрезке"]

def test_flaws_count_a_fragment_without_a_recorded_offset():
    found = flaws_of(
        title="Гендель — «Музыка на воде»",
        fragments=[{"name": "Алла хорнпайп", "audio_file_id": "x"}],
        facts=["Факт."],
        recording={"performer": "Кто-то", "source": "Musopen", "license": "CC0"},
    )

    assert found["у фрагмента не записана засечка"]

def test_flaws_spare_a_whole_recording_that_has_no_offset_to_record():
    found = flaws_of(
        title="Масканьи — интермеццо",
        fragments=[{"name": "Интермеццо", "as_is": True, "audio_file_id": "x"}],
        facts=["Факт."],
        recording={"performer": "Кто-то", "source": "IMSLP", "license": "CC BY-NC-ND 4.0"},
    )

    assert not found["у фрагмента не записана засечка"]

def test_flaws_count_a_recording_without_a_licence():
    found = flaws_of(
        title="Бах — Прелюдия",
        fragments=[{"name": "Прелюдия", "start": "0", "audio_file_id": "x"}],
        facts=["Факт."],
        recording={"performer": "Кто-то", "source": "Musopen"},
    )

    assert found["лицензия записи не указана"]

def test_flaws_catch_a_fact_that_runs_past_two_sentences():
    found = flaws_of(
        title="Бах — Токката и фуга ре минор",
        fragments=[{"name": "Начало", "start": "0", "audio_file_id": "x"}],
        facts=["Первое. Второе. Третье."],
    )

    assert found["факт длиннее двух предложений"]

def test_flaws_leave_a_fact_of_two_sentences():
    found = flaws_of(
        title="Бах — Токката и фуга ре минор",
        fragments=[{"name": "Начало", "start": "0", "audio_file_id": "x"}],
        facts=["Первое. Второе."],
    )

    assert not found["факт длиннее двух предложений"]

def test_flaws_catch_a_fact_that_promises_instead_of_telling():
    found = flaws_of(
        title="Гайдн — «Времена года»",
        fragments=[{"name": "Весна", "start": "0", "audio_file_id": "x"}],
        facts=["Интересно, что оратория начинается с зимы."],
    )

    assert found["факт начинается с обещания"]

def test_flaws_catch_mozart_speaking_of_himself_in_the_third_person():
    found = flaws_of(
        title="Моцарт — Симфония №40",
        composer="Моцарт",
        fragments=[{"name": "Начало", "start": "0", "audio_file_id": "x"}],
        facts=["Моцарт внёс симфонию в каталог 25 июля 1788 года."],
    )

    assert found["Моцарт говорит о себе в третьем лице"]

def test_flaws_allow_mozart_to_be_named_inside_someone_elses_words():
    found = flaws_of(
        title="Моцарт — «Свадьба Фигаро», увертюра",
        composer="Моцарт",
        fragments=[{"name": "Увертюра", "start": "0", "audio_file_id": "x"}],
        facts=["Оркестр заорал «Виват, великий Моцарт!», и я едва устоял."],
    )

    assert not found["Моцарт говорит о себе в третьем лице"]

def test_flaws_leave_another_composer_named_in_the_third_person():
    found = flaws_of(
        title="Бетховен — «К Элизе»",
        composer="Бетховен",
        fragments=[{"name": "Начало", "start": "0", "audio_file_id": "x"}],
        facts=["Моцарт в его годы уже объехал пол-Европы."],
    )

    assert not found["Моцарт говорит о себе в третьем лице"]
