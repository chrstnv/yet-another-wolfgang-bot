import progress

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
    assert progress.verdict(4, 4).startswith("Идеально")

def test_verdict_is_encouraging_from_half_and_up():
    assert "Ухо уже кое-что помнит" in progress.verdict(2, 4)
    assert "Ухо уже кое-что помнит" in progress.verdict(3, 4)

def test_verdict_softens_a_weak_run():
    assert "дело наживное" in progress.verdict(1, 4)
    assert "дело наживное" in progress.verdict(0, 4)

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
