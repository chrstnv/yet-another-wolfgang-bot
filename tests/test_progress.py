from core import progress
import pytest
from core import quiz
from core.texts import QUESTION_VARIANTS, STREAK_NEW_RECORD_PLUS, STREAK_RESULTS, VERDICTS
from core.progress import card_naming, visible_fragment

CARDS = [
    {"id": "france-capital", "title": "Париж"},
    {"id": "germany-capital", "title": "Берлин"},
    {"id": "italy-capital", "title": "Рим"},
]

CARDS_BY_ID = {card["id"]: card for card in CARDS}

def answer(card_id: str, correct: bool) -> dict:
    chosen = card_id if correct else "some-other-card"

    return {"card_id": card_id, "chosen": chosen}

def test_summary_of_no_answers_is_empty():
    assert progress.summary([], CARDS_BY_ID) == {
        "total": 0,
        "correct": 0,
        "accuracy": 0,
        "cards_seen": 0,
    }

def test_summary_counts_accuracy():
    answers = [
        answer("france-capital", True),
        answer("france-capital", False),
        answer("germany-capital", True),
        answer("germany-capital", False),
    ]

    stats = progress.summary(answers, CARDS_BY_ID)

    assert stats["total"] == 4
    assert stats["correct"] == 2
    assert stats["accuracy"] == 50

def test_cards_seen_counts_unique_cards_not_answers():
    answers = [
        answer("france-capital", True),
        answer("france-capital", False),
        answer("france-capital", True),
    ]

    assert progress.summary(answers, CARDS_BY_ID)["cards_seen"] == 1

def test_summary_ignores_answers_to_unknown_cards():
    answers = [
        answer("france-capital", True),
        {"card_id": "deleted-card", "chosen": "deleted-card"},
    ]

    stats = progress.summary(answers, CARDS_BY_ID)

    assert stats["total"] == 1
    assert stats["cards_seen"] == 1

def test_per_card_ignores_answers_to_unknown_cards():
    answers = [
        answer("france-capital", True),
        {"card_id": "deleted-card", "chosen": "deleted-card"},
    ]

    assert progress.per_card(answers, CARDS_BY_ID) == [
        {"card_id": "france-capital", "attempts": 1, "correct": 1},
    ]

def test_per_card_counts_attempts_and_hits_separately():
    answers = [
        answer("france-capital", True),
        answer("france-capital", False),
        answer("france-capital", False),
        answer("germany-capital", True),
    ]

    by_id = {card["card_id"]: card for card in progress.per_card(answers, CARDS_BY_ID)}

    assert by_id["france-capital"] == {"card_id": "france-capital", "attempts": 3, "correct": 1}
    assert by_id["germany-capital"] == {"card_id": "germany-capital", "attempts": 1, "correct": 1}

def test_weakest_skips_cards_answered_without_mistakes():
    answers = [
        answer("france-capital", True),
        answer("france-capital", True),
        answer("germany-capital", False),
    ]

    weakest = progress.weakest(answers, CARDS_BY_ID)

    assert [card["card_id"] for card in weakest] == ["germany-capital"]

def test_weakest_is_empty_when_everything_is_answered_correctly():
    answers = [
        answer("france-capital", True),
        answer("germany-capital", True),
    ]

    assert progress.weakest(answers, CARDS_BY_ID) == []

def test_weakest_puts_the_worst_ratio_first():
    answers = [
        # франция: 1 из 2
        answer("france-capital", True),
        answer("france-capital", False),
        # германия: 0 из 2
        answer("germany-capital", False),
        answer("germany-capital", False),
        # италия: 2 из 3
        answer("italy-capital", True),
        answer("italy-capital", True),
        answer("italy-capital", False),
    ]

    weakest = progress.weakest(answers, CARDS_BY_ID)

    assert [card["card_id"] for card in weakest] == [
        "germany-capital",
        "france-capital",
        "italy-capital",
    ]

def test_weakest_respects_the_limit():
    answers = [
        answer("france-capital", False),
        answer("germany-capital", False),
        answer("italy-capital", False),
    ]

    assert len(progress.weakest(answers, CARDS_BY_ID, limit=2)) == 2

def test_verdict_celebrates_a_perfect_run():
    assert progress.verdict(4, 4) == VERDICTS["perfect"].format(correct=4, total=4)

def test_verdict_is_encouraging_from_half_and_up():
    assert progress.verdict(2, 4) == VERDICTS["good"].format(correct=2, total=4)
    assert progress.verdict(3, 4) == VERDICTS["good"].format(correct=3, total=4)

def test_verdict_softens_a_weak_run():
    assert progress.verdict(1, 4) == VERDICTS["weak"].format(correct=1, total=4)
    assert progress.verdict(0, 4) == VERDICTS["weak"].format(correct=0, total=4)

def test_verdict_shows_the_numbers():
    assert "3 из 5" in progress.verdict(3, 5)

def test_to_review_takes_only_cards_with_mistakes():
    answers = [
        answer("france-capital", True),
        answer("germany-capital", False),
    ]

    assert progress.to_review(answers, CARDS_BY_ID, set(CARDS_BY_ID)) == ["germany-capital"]

def test_to_review_puts_the_worst_first():
    answers = [
        # франция: 1 из 2
        answer("france-capital", True),
        answer("france-capital", False),
        # германия: 0 из 2
        answer("germany-capital", False),
        answer("germany-capital", False),
    ]

    assert progress.to_review(answers, CARDS_BY_ID, set(CARDS_BY_ID)) == [
        "germany-capital",
        "france-capital",
    ]

def test_to_review_skips_cards_that_cannot_be_played():
    answers = [answer("germany-capital", False), answer("italy-capital", False)]

    playable = {"italy-capital"}

    assert progress.to_review(answers, CARDS_BY_ID, playable) == ["italy-capital"]

def test_to_review_respects_the_limit():
    answers = [
        answer("france-capital", False),
        answer("germany-capital", False),
        answer("italy-capital", False),
    ]

    assert len(progress.to_review(answers, CARDS_BY_ID, set(CARDS_BY_ID), limit=2)) == 2

def test_streak_message_adds_the_previous_record():
    text = progress.streak_message(3, best=7)

    assert "3 подряд" in text
    assert "7" in text

def test_streak_message_says_nothing_about_the_previous_record_when_it_is_beaten():
    text = progress.streak_message(9, best=7)

    assert STREAK_RESULTS["record"].format(length=9) in text
    assert "7" not in text

def test_streak_message_skips_the_record_line_for_the_first_ever_run():
    text = progress.streak_message(0, best=0)

    assert "рекорд" not in text

def test_streak_message_lists_what_was_heard_for_the_first_time():
    text = progress.streak_message(2, best=7, fresh=["Глинка — «Жаворонок»", "Балакирев — Тарантелла"])

    assert "Впервые услышано" in text
    assert "• Глинка — «Жаворонок»" in text
    assert "• Балакирев — Тарантелла" in text

def test_streak_message_says_nothing_about_findings_when_there_are_none():
    assert "Впервые" not in progress.streak_message(2, best=7)

def test_streak_message_puts_the_count_in_the_headline():
    assert "<b>🔥 Серия: 5</b>" in progress.streak_message(5, best=7)

def test_streak_message_counts_a_run_of_nothing_as_zero():
    text = progress.streak_message(0, best=7)

    assert text.startswith("<b>🔥 Серия: 0</b>")

def test_streak_message_shows_the_record_after_a_zero_run():
    text = progress.streak_message(0, best=4)

    assert STREAK_RESULTS["zero"] in text
    assert "4" in text

def test_question_caption_counts_questions_in_a_quiz():
    session = quiz.session_for(["a", "b", "c"])
    session["position"] = 1

    assert "Вопрос 2 из 3" in progress.question_caption(session)

def test_question_caption_counts_the_streak_instead():
    session = quiz.session_for(["a", "b", "c"], mode=quiz.STREAK)
    session["position"] = 2

    caption = progress.question_caption(session)

    assert "🔥\u00a02\u00a0подряд" in caption
    assert "из 3" not in caption

def test_question_caption_says_nothing_on_the_first_streak_question():
    session = quiz.session_for(["a", "b", "c"], mode=quiz.STREAK)

    assert "\n" not in progress.question_caption(session)

def test_first_time_lists_only_unheard_cards():
    session = quiz.session_for(["a", "b"])
    session["seen"] = {"a"}
    quiz.record_answer(session, "a", "a")
    quiz.record_answer(session, "b", "b")

    assert progress.first_time(session) == ["b"]

def test_first_time_does_not_repeat_a_card_answered_twice():
    session = quiz.session_for(["b", "b"])
    session["seen"] = set()
    quiz.record_answer(session, "b", "b")
    quiz.record_answer(session, "b", "b")

    assert progress.first_time(session) == ["b"]

def test_first_time_keeps_the_order_of_the_quiz():
    session = quiz.session_for(["c", "a"])
    session["seen"] = set()
    quiz.record_answer(session, "c", "c")
    quiz.record_answer(session, "a", "a")

    assert progress.first_time(session) == ["c", "a"]


def test_question_caption_uses_the_line_chosen_for_this_card():
    session = quiz.session_for(["a", "b"])
    session["question"] = "🎵 Не благодарите."

    assert "🎵 Не благодарите." in progress.question_caption(session)

def test_question_caption_survives_a_session_without_a_chosen_line():
    # сессии, пережившие перезапуск бота, лежат в pickle без этого поля
    session = quiz.session_for(["a", "b"])

    assert progress.question_caption(session).endswith(QUESTION_VARIANTS[0])

def test_question_caption_keeps_the_line_in_a_streak():
    session = quiz.session_for(["a", "b"], mode=quiz.STREAK)
    session["question"] = "🎵 Красивый выбор. Мой."
    session["position"] = 3

    caption = progress.question_caption(session)

    assert "🔥\u00a03\u00a0подряд" in caption
    assert caption.endswith("🎵 Красивый выбор. Мой.")

@pytest.mark.parametrize("length, best, by_far", [
    (28, 18, True),    # прибавка ровно в порог
    (30, 18, True),
    (21, 18, False),   # рекорд, но подвинутый на три
    (25, 21, False),
    (31, 25, False),
    (12, 0, True),     # с нуля сразу далеко
    (9, 0, False),
])
def test_beat_the_record_by_far(length, best, by_far):
    assert progress.beat_the_record_by_far(length, best) is by_far

def test_streak_message_marks_a_record_beaten_by_far():
    text = progress.streak_message(30, best=18)

    assert STREAK_NEW_RECORD_PLUS.format(length=30) in text
    assert STREAK_RESULTS["record"].format(length=30) not in text

def test_streak_message_keeps_the_plain_record_line_for_a_small_gain():
    text = progress.streak_message(21, best=18)

    assert STREAK_RESULTS["record"].format(length=21) in text
    assert STREAK_NEW_RECORD_PLUS.format(length=21) not in text

RECORDING = {"performer": "Кто-то", "source": "Откуда-то"}

def caption(**overrides):
    defaults = {
        "naming": "Бизе — Хабанера из «Кармен»",
        "description": "Выходная ария Кармен в первом акте.",
        "fragment": "",
        "fact": "Факт.",
        "recording": RECORDING,
        "reply": "Реплика.",
        "correct": True,
    }

    return progress.answer_caption(**{**defaults, **overrides})

def test_answer_caption_opens_with_wolfgang_speaking():
    assert caption().startswith("✅ Реплика.\n\n🎼 Это Бизе — Хабанера из «Кармен», выходная ария")

def test_answer_caption_names_the_work_before_the_mistake():
    text = caption(correct=False, chosen="Верди — «Аида»")

    assert text.startswith("❌ Реплика.\n\n🎼 Это Бизе — Хабанера из «Кармен», выходная ария Кармен в первом акте. Вы же выбрали Верди — «Аида».")

def test_answer_caption_counts_the_streak_beside_the_reply():
    assert caption(streak=7).startswith("✅ Реплика.\n\n🔥\u00a07\u00a0подряд.\n\n🎼 Это Бизе")

def test_answer_caption_runs_the_description_on_from_the_name():
    # одной строкой: вместе они читаются как одна фраза
    text = caption()

    assert "Кармен», выходная ария Кармен в первом акте." in text

def test_answer_caption_skips_the_description_when_there_is_none():
    assert caption(description="").startswith("✅ Реплика.\n\n🎼 Это Бизе — Хабанера из «Кармен».")

def test_answer_caption_puts_the_fragment_right_after_the_title():
    assert "из «Кармен», Адажио, выходная ария" in caption(fragment="Адажио")

def test_answer_caption_names_no_fragment_when_there_is_none():
    assert caption(fragment="").startswith("✅ Реплика.\n\n🎼 Это Бизе — Хабанера из «Кармен», выходная")

def test_answer_caption_ends_with_the_credit():
    assert caption().endswith("🎧 Кто-то — Откуда-то")

def test_answer_caption_says_the_reply_once():
    assert caption().count("Реплика.") == 1

def test_answer_caption_names_the_licence_when_the_recording_carries_one():
    licensed = {**RECORDING, "license": "CC BY-NC-ND 4.0"}

    assert caption(recording=licensed).endswith("🎧 Кто-то — Откуда-то, CC BY-NC-ND 4.0")

def test_answer_caption_leaves_the_credit_alone_without_a_licence():
    assert caption().endswith("🎧 Кто-то — Откуда-то")

def test_answer_caption_lets_mozart_own_his_music():
    assert "Это, разумеется, я — Хабанера, выходная ария" in caption(naming="Хабанера", mozart=True)

def test_answer_caption_mozart_owns_it_even_when_missed():
    text = caption(naming="Симфония №40", mozart=True, correct=False, chosen="Гайдн — «Времена года»")

    assert "А это был я — Симфония №40, выходная ария Кармен в первом акте. Вы же выбрали Гайдн — «Времена года»." in text

def test_answer_caption_introduces_everyone_else_in_the_third_person():
    assert caption().count("Это Бизе") == 1

def test_answer_caption_keeps_the_fragment_with_the_right_work_after_a_miss():
    text = caption(correct=False, chosen="Верди — «Аида»", fragment="Рондо")

    # «Рондо» — часть того, что звучало, а не того, что выбрали
    assert "из «Кармен», Рондо, выходная ария Кармен в первом акте. Вы же выбрали Верди — «Аида»." in text

def test_card_naming_prints_a_foreign_original_in_brackets():
    card = {"title": "Делиб — «Лакме», дуэт цветов", "original_title": "Sous le dôme épais"}
    assert card_naming(card) == "Делиб — «Лакме», дуэт цветов (Sous le dôme épais)"

def test_card_naming_drops_an_original_that_repeats_the_title():
    card = {"title": "Чайковский — увертюра «1812 год»", "original_title": "Увертюра «1812 год»"}
    assert card_naming(card) == "Чайковский — увертюра «1812 год»"

def test_card_naming_leaves_the_composer_out_when_mozart_speaks():
    card = {"title": "Моцарт — Реквием, «Лакримоза»"}
    assert card_naming(card, mozart=True) == "Реквием, «Лакримоза»"

def one_fragment(title, fragment, original=None):
    card = {"title": title, "fragments": [{"name": fragment}]}
    if original:
        card["original_title"] = original

    return card

def test_visible_fragment_keeps_a_name_that_adds_something():
    card = one_fragment("Григ — «Пер Гюнт»", "Танец Анитры")

    assert visible_fragment(card, "Танец Анитры", "Григ — «Пер Гюнт»") == "Танец Анитры"

def test_visible_fragment_drops_a_name_already_in_the_title():
    card = one_fragment("Шопен — Ноктюрн №2, Op. 9", "Ноктюрн")

    assert visible_fragment(card, "Ноктюрн", "Шопен — Ноктюрн №2, Op. 9") == ""

def test_visible_fragment_drops_a_name_already_in_the_brackets():
    card = one_fragment("Россини — ария Фигаро", "Largo al factotum",
                        original="Largo al factotum, Il barbiere di Siviglia")
    naming = card_naming(card)

    assert visible_fragment(card, "Largo al factotum", naming) == ""

def test_visible_fragment_keeps_a_name_that_tells_two_parts_apart():
    card = {
        "title": "Сен-Санс — Интродукция и рондо каприччиозо",
        "fragments": [{"name": "Интродукция"}, {"name": "Рондо"}],
    }
    naming = card["title"]

    assert visible_fragment(card, "Интродукция", naming) == "Интродукция"
