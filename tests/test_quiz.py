from collections import Counter

import quiz
import pytest

CARDS = [
    {
        "id": "france-capital",
        "title": "Париж",
        "distractors": ["germany-capital", "italy-capital"],
        "fragments": [{"name": "Париж", "audio_file_id": "a"}],
    },
    {
        "id": "germany-capital",
        "title": "Берлин",
        "fragments": [{"name": "Берлин", "audio_file_id": "b"}],
    },
    {
        "id": "italy-capital",
        "title": "Рим",
        "fragments": [{"name": "Рим", "audio_file_id": "c"}, {"name": "Рим-2", "audio_file_id": "d"}],
    },
    # карточки без записи: в квиз не попадают, но годятся в варианты ответа
    {"id": "spain-capital", "title": "Мадрид"},
    {"id": "portugal-capital", "title": "Лиссабон"},
]

CARDS_BY_ID = {card["id"]: card for card in CARDS}

PLAYABLE = [card for card in CARDS if card.get("fragments")]

@pytest.fixture
def session():
    return quiz.start_session(PLAYABLE, length=3)

def test_start_session_returns_default_values(session):
    assert session["position"] == 0
    assert len(session["queue"]) == 3
    assert session["answers"] == []

def test_cards_do_not_repeat(session):
    assert len(set(session["queue"])) == len(session["queue"])

def test_current_card_id_returns_card_at_current_position(session):
    assert quiz.current_card_id(session) == session["queue"][0]

    quiz.advance(session)

    assert quiz.current_card_id(session) == session["queue"][1]

def test_advance_moves_position(session):
    quiz.advance(session)

    assert session["position"] == 1
    assert not quiz.is_answered(session)

def test_is_finished_only_after_the_last_question(session):
    assert not quiz.is_finished(session)
    quiz.advance(session)
    assert not quiz.is_finished(session)
    quiz.advance(session)
    assert not quiz.is_finished(session)
    quiz.advance(session)
    assert quiz.is_finished(session)

def test_record_answer_adds_answer_to_session(session):
    quiz.record_answer(session, "france-capital", "italy-capital")

    assert session["answers"] == [{"card_id": "france-capital", "chosen": "italy-capital"}]
    assert quiz.is_answered(session)

def test_is_correct_compares_chosen_card_with_the_played_one():
    assert quiz.is_correct({"card_id": "france-capital", "chosen": "france-capital"})
    assert not quiz.is_correct({"card_id": "france-capital", "chosen": "italy-capital"})

def test_score_counts_only_correct_answers(session):
    quiz.record_answer(session, "france-capital", "france-capital")
    quiz.record_answer(session, "germany-capital", "italy-capital")

    assert quiz.score(session) == 1

def test_breakdown_returns_titles_and_flags(session):
    quiz.record_answer(session, "france-capital", "italy-capital")
    quiz.record_answer(session, "germany-capital", "germany-capital")

    assert quiz.breakdown(session, CARDS_BY_ID) == [("Париж", False), ("Берлин", True)]

def test_build_options_always_includes_the_right_answer():
    card = CARDS_BY_ID["france-capital"]

    for _ in range(50):
        options = quiz.build_options(card, CARDS)
        assert card in options

def test_build_options_returns_requested_count_without_duplicates():
    card = CARDS_BY_ID["france-capital"]

    options = quiz.build_options(card, CARDS, count=4)
    ids = [option["id"] for option in options]

    assert len(ids) == 4
    assert len(set(ids)) == 4

def test_build_options_leans_towards_the_listed_distractors():
    card = CARDS_BY_ID["france-capital"]
    seen = Counter()

    for _ in range(300):
        seen.update(option["id"] for option in quiz.build_options(card, CARDS))

    # germany и italy перечислены у france как предпочтительные, spain и portugal — нет
    assert seen["germany-capital"] > seen["spain-capital"]
    assert seen["italy-capital"] > seen["portugal-capital"]

def test_build_options_always_leaves_room_for_an_outsider():
    card = CARDS_BY_ID["france-capital"]
    listed = set(card["distractors"])

    for _ in range(100):
        ids = [option["id"] for option in quiz.build_options(card, CARDS)]
        strangers = [i for i in ids if i != card["id"] and i not in listed]
        assert len(strangers) == quiz.RANDOM_SLOTS

def test_build_options_does_not_always_return_the_same_set():
    card = CARDS_BY_ID["france-capital"]

    sets = {
        tuple(sorted(option["id"] for option in quiz.build_options(card, CARDS)))
        for _ in range(100)
    }

    assert len(sets) > 1

def test_build_options_uses_cards_without_audio_as_distractors():
    card = CARDS_BY_ID["germany-capital"]
    seen = set()

    for _ in range(50):
        seen.update(option["id"] for option in quiz.build_options(card, CARDS))

    assert "spain-capital" in seen or "portugal-capital" in seen

def test_build_options_does_not_mutate_the_card_list():
    before = list(CARDS)

    quiz.build_options(CARDS_BY_ID["france-capital"], CARDS)

    assert CARDS == before

def test_pick_fragment_returns_one_of_the_cards_fragments():
    card = CARDS_BY_ID["italy-capital"]

    picked = {quiz.pick_fragment(card)["name"] for _ in range(50)}

    assert picked == {"Рим", "Рим-2"}

def test_pick_fragment_works_for_a_single_fragment():
    card = CARDS_BY_ID["france-capital"]

    assert quiz.pick_fragment(card)["name"] == "Париж"

def test_recording_falls_back_to_the_card():
    card = {"recording": {"performer": "Кто-то", "source": "Откуда-то"}}

    assert quiz.recording_of(card, {"name": "Фрагмент"})["performer"] == "Кто-то"

def test_fragment_may_carry_its_own_recording():
    card = {"recording": {"performer": "Кто-то", "source": "Откуда-то"}}
    fragment = {"name": "Фрагмент", "recording": {"performer": "Другой", "source": "Иное"}}

    assert quiz.recording_of(card, fragment)["performer"] == "Другой"

def test_session_for_keeps_the_given_order():
    session = quiz.session_for(["italy-capital", "france-capital"])

    assert session["queue"] == ["italy-capital", "france-capital"]
    assert session["position"] == 0
    assert session["answers"] == []

def test_session_for_copies_the_list():
    given = ["france-capital"]
    session = quiz.session_for(given)

    given.append("germany-capital")

    assert session["queue"] == ["france-capital"]
