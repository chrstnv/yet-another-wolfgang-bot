import random

QUIZ_LENGTH = 5

def start_session(cards: list[dict], length: int = QUIZ_LENGTH) -> dict:
    selected = random.sample(cards, k=min(length, len(cards)))
    return {
        "queue": [card["id"] for card in selected],
        "position": 0,
        "answers": [],
    }

def current_card_id(session: dict) -> str:
    return session["queue"][session["position"]]

def is_answered(session: dict) -> bool:
    return len(session["answers"]) > session["position"]

def record_answer(session: dict, card_id: str, chosen: int) -> None:
    session["answers"].append({"card_id": card_id, "chosen": chosen})

def advance(session: dict) -> None:
    session["position"] += 1

def is_finished(session: dict) -> bool:
    return session["position"] >= len(session["queue"])

def is_correct(answer: dict, cards_by_id: dict) -> bool:
    card = cards_by_id[answer["card_id"]]

    return answer["chosen"] == card["correct_index"]

def score(session: dict, cards_by_id: dict) -> int:
    return sum(1 for answer in session["answers"] if is_correct(answer, cards_by_id))

def breakdown(session: dict, cards_by_id: dict) -> list[tuple[str, bool]]:
    lines = []
    for answer in session["answers"]:
        card = cards_by_id[answer["card_id"]]
        lines.append((card["options"][card["correct_index"]], is_correct(answer, cards_by_id)))
    return lines

def shuffled_options(card: dict) -> list[tuple[int, str]]:
    options = list(enumerate(card["options"]))
    random.shuffle(options)
    return options
