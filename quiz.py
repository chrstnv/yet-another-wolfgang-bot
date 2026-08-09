import random

QUIZ_LENGTH = 5

STREAK = "streak"

def session_for(card_ids: list[str], mode: str = "quiz") -> dict:
    return {
        "queue": list(card_ids),
        "position": 0,
        "answers": [],
        "mode": mode,
    }

def last_answer_was_wrong(session: dict) -> bool:
    answers = session["answers"]

    return bool(answers) and not is_correct(answers[-1])

def start_session(cards: list[dict], length: int = QUIZ_LENGTH) -> dict:
    selected = random.sample(cards, k=min(length, len(cards)))

    return session_for([card["id"] for card in selected])

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

def is_correct(answer: dict) -> bool:
    return answer["chosen"] == answer["card_id"]

def score(session: dict) -> int:
    return sum(1 for answer in session["answers"] if is_correct(answer))

def breakdown(session: dict, cards_by_id: dict) -> list[tuple[str, bool]]:
    lines = []
    for answer in session["answers"]:
        card = cards_by_id[answer["card_id"]]
        lines.append((card["title"], is_correct(answer)))
    return lines

RANDOM_SLOTS = 1

def pick_fragment(card: dict) -> dict:
    return random.choice(card["fragments"])

def recording_of(card: dict, fragment: dict) -> dict:
    return fragment.get("recording") or card["recording"]

def build_options(card: dict, cards: list[dict], count: int = 4) -> list[dict]:
    others = [other for other in cards if other["id"] != card["id"]]
    listed = set(card.get("distractors", []))

    preferred = [other for other in others if other["id"] in listed]
    rest = [other for other in others if other["id"] not in listed]
    random.shuffle(preferred)
    random.shuffle(rest)

    wrong_count = count - 1
    # часть мест отдаём подготовленным ловушкам, остальные — случайным карточкам;
    # если одних не хватило, добираем другими
    picked = preferred[:max(0, wrong_count - RANDOM_SLOTS)] + rest + preferred

    options = [card] + picked[:wrong_count]
    random.shuffle(options)

    return options
