import quiz
import pytest

CARDS = [
    {
        "id": "france-capital",
        "question": "What is the capital of France?",
        "answer": "Paris",
        "correct_index": 0,
        "options": ["Paris", "Berlin", "Rome"]
    },
    {
        "id": "germany-capital",
        "question": "What is the capital of Germany?",
        "answer": "Berlin",
        "correct_index": 1,
        "options": ["Paris", "Berlin", "Rome"]
    },
    {
        "id": "italy-capital",
        "question": "What is the capital of Italy?",
        "answer": "Rome",
        "correct_index": 2,
        "options": ["Paris", "Berlin", "Rome"]
    }
]

CARDS_BY_ID = {card["id"]: card for card in CARDS}

@pytest.fixture
def session():
    return quiz.start_session(CARDS, length=3)

def test_start_session_returns_default_values(session):
    assert session["position"] == 0
    assert len(session["queue"]) == 3
    assert session["answers"] == []

def test_cards_do_not_repeat(session):
    assert len(set(session["queue"])) == len(session["queue"])

def test_advance_moves_position(session):
    quiz.advance(session)
    assert session["position"] == 1
    assert not quiz.is_answered(session)

def test_is_finished_returns_false_in_the_middle(session):
    assert not quiz.is_finished(session)
    quiz.advance(session)
    assert not quiz.is_finished(session)
    quiz.advance(session)
    assert not quiz.is_finished(session)
    quiz.advance(session)
    assert quiz.is_finished(session)

def test_record_answer_adds_answer_to_session(session):
    assert session["position"] == 0

    quiz.record_answer(session, "france-capital", 0)

    assert session["answers"] == [{"card_id": "france-capital", "chosen": 0}]
    assert quiz.is_answered(session)

def test_score_counts_only_correct_answers(session):
    quiz.record_answer(session, "france-capital", 1)
    quiz.record_answer(session, "germany-capital", 1)
    assert quiz.score(session, CARDS_BY_ID) == 1

def test_breakdown_returns_list_of_cards_and_boolean_values(session):
    quiz.record_answer(session, "france-capital", 1)
    quiz.record_answer(session, "germany-capital", 1)
    assert quiz.breakdown(session, CARDS_BY_ID) == [("Paris", False), ("Berlin", True)]

def test_shuffled_options_returns_same_pairs_as_enumerate_card_options(session):
    card = CARDS_BY_ID["france-capital"]
    assert sorted(quiz.shuffled_options(card)) == sorted(enumerate(card["options"]))

def test_shuffled_options_does_not_mutate_card():
    card = CARDS_BY_ID["france-capital"]
    before = list(card["options"])

    quiz.shuffled_options(card)

    assert card["options"] == before

def test_current_card_id_returns_current_card_id(session):
    assert quiz.current_card_id(session) == session["queue"][0]