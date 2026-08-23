from collections import Counter

from core import quiz
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

def test_session_carries_its_mode():
    assert quiz.session_for(["france-capital"])["mode"] == "quiz"
    assert quiz.session_for(["france-capital"], mode=quiz.STREAK)["mode"] == quiz.STREAK

def test_last_answer_was_wrong_needs_an_answer():
    session = quiz.session_for(["france-capital"])

    assert not quiz.last_answer_was_wrong(session)

def test_last_answer_was_wrong_looks_only_at_the_last():
    session = quiz.session_for(["france-capital", "germany-capital"])
    quiz.record_answer(session, "france-capital", "italy-capital")
    quiz.record_answer(session, "germany-capital", "germany-capital")

    assert not quiz.last_answer_was_wrong(session)

    quiz.record_answer(session, "italy-capital", "france-capital")

    assert quiz.last_answer_was_wrong(session)

# трудные стоят первыми нарочно: если из streak_queue пропадёт сортировка,
# порядок вставки протащит их в начало очереди и тест это поймает
GRADED = [
    {"id": "hard-1", "difficulty": 5},
    {"id": "hard-2", "difficulty": 5},
    {"id": "unlabelled"},
    {"id": "easy-1", "difficulty": 1},
    {"id": "easy-2", "difficulty": 1},
    {"id": "easy-3", "difficulty": 1},
]

def test_streak_queue_goes_from_easy_to_hard():
    queue = quiz.streak_queue(GRADED, step=2)

    assert queue[0].startswith("easy")
    assert queue[1].startswith("easy")
    assert queue[2].startswith("hard")
    assert queue[3].startswith("hard")

def test_streak_queue_takes_no_more_than_step_per_level():
    queue = quiz.streak_queue(GRADED, step=2)

    assert sum(1 for card_id in queue[:2] if card_id.startswith("easy")) == 2

def test_streak_queue_keeps_every_card_once():
    queue = quiz.streak_queue(GRADED, step=2)

    assert Counter(queue) == Counter(card["id"] for card in GRADED)

def test_streak_queue_leaves_cards_without_difficulty_to_the_tail():
    queue = quiz.streak_queue(GRADED, step=2)

    assert "unlabelled" in queue[4:]

def test_start_session_orders_by_difficulty():
    queue = quiz.start_session(GRADED, length=len(GRADED))["queue"]
    graded = [card_id for card_id in queue if card_id != "unlabelled"]

    assert graded == sorted(graded, key=lambda card_id: 1 if card_id.startswith("easy") else 5)

def test_start_session_puts_unlabelled_cards_last():
    queue = quiz.start_session(GRADED, length=len(GRADED))["queue"]

    assert queue[-1] == "unlabelled"

VARIANTS = ["первая", "вторая", "третья", "четвёртая"]

def test_next_line_spends_every_variant_before_repeating():
    session = quiz.session_for(["a"])

    drawn = [quiz.next_line(session, "реплики", VARIANTS) for _ in range(len(VARIANTS))]

    assert sorted(drawn) == sorted(VARIANTS)

def test_next_line_refills_the_bag_when_it_runs_out():
    session = quiz.session_for(["a"])

    drawn = [quiz.next_line(session, "реплики", VARIANTS) for _ in range(len(VARIANTS) * 3)]

    assert Counter(drawn) == Counter({variant: 3 for variant in VARIANTS})

def test_next_line_does_not_repeat_across_a_refill():
    for _ in range(50):
        session = quiz.session_for(["a"])
        drawn = []
        for _ in range(len(VARIANTS) * 2):
            drawn.append(quiz.next_line(session, "реплики", VARIANTS))

        assert all(a != b for a, b in zip(drawn, drawn[1:]))

def test_next_line_shuffles_the_bag():
    orders = set()
    for _ in range(50):
        session = quiz.session_for(["a"])
        orders.add(tuple(quiz.next_line(session, "реплики", VARIANTS) for _ in range(len(VARIANTS))))

    assert len(orders) > 1

def test_next_line_copes_with_a_single_variant():
    session = quiz.session_for(["a"])

    assert quiz.next_line(session, "реплики", ["одна"]) == "одна"
    assert quiz.next_line(session, "реплики", ["одна"]) == "одна"

def test_next_line_keeps_a_separate_deck_per_name():
    session = quiz.session_for(["a"])

    first = [quiz.next_line(session, "похвала", VARIANTS) for _ in range(2)]
    quiz.next_line(session, "попрёки", VARIANTS)
    first += [quiz.next_line(session, "похвала", VARIANTS) for _ in range(2)]

    # чужая колода не должна расходовать эту
    assert sorted(first) == sorted(VARIANTS)

def test_reply_deck_praises_mozart_separately():
    assert quiz.reply_deck({"composer": "Моцарт"}, correct=True) == "correct-mozart"
    assert quiz.reply_deck({"composer": "Сальери"}, correct=True) == "correct"

def test_reply_deck_scolds_the_same_whoever_wrote_it():
    assert quiz.reply_deck({"composer": "Моцарт"}, correct=False) == "wrong"
    assert quiz.reply_deck({"composer": "Сальери"}, correct=False) == "wrong"

def test_chosen_id_returns_the_answer_to_the_current_question():
    session = quiz.session_for(["a", "b"])
    quiz.record_answer(session, "a", "b")

    assert quiz.chosen_id(session) == "b"

def test_chosen_id_follows_the_position(session=None):
    session = quiz.session_for(["a", "b"])
    quiz.record_answer(session, "a", "a")
    quiz.advance(session)
    quiz.record_answer(session, "b", "a")

    assert quiz.chosen_id(session) == "a"

def test_a_miss_from_a_random_place_is_answered_more_gently():
    """Не узнать вещь по середине разработки — не позор."""
    assert quiz.reply_deck({}, correct=False, naugad=True) == "wrong-roulette"

def test_a_miss_elsewhere_is_answered_as_before():
    assert quiz.reply_deck({}, correct=False) == "wrong"

def test_a_random_place_is_praised_like_any_other():
    assert quiz.reply_deck({}, correct=True, naugad=True) == "correct"
