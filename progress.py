import quiz
from data import VERDICTS

def verdict(correct: int, total: int) -> str:
    if correct == total:
        key = "perfect"
    elif correct * 2 >= total:
        key = "good"
    else:
        key = "weak"

    return VERDICTS[key].format(correct=correct, total=total)

def known_answers(answers: list[dict], cards_by_id: dict) -> list[dict]:
    return [answer for answer in answers if answer["card_id"] in cards_by_id]

def summary(answers: list[dict], cards_by_id: dict) -> dict:
    known = known_answers(answers, cards_by_id)
    correct = sum(1 for answer in known if quiz.is_correct(answer))
    total = len(known)

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100) if total else 0,
        "cards_seen": len({answer["card_id"] for answer in known}),
    }

def per_card(answers: list[dict], cards_by_id: dict) -> list[dict]:
    stats: dict[str, dict] = {}

    for answer in known_answers(answers, cards_by_id):
        card_id = answer["card_id"]
        entry = stats.setdefault(card_id, {"card_id": card_id, "attempts": 0, "correct": 0})
        entry["attempts"] += 1
        if quiz.is_correct(answer):
            entry["correct"] += 1

    return list(stats.values())

def weakest(answers: list[dict], cards_by_id: dict, limit: int = 3) -> list[dict]:
    missed = [card for card in per_card(answers, cards_by_id) if card["correct"] < card["attempts"]]
    missed.sort(key=lambda card: (card["correct"] / card["attempts"], -card["attempts"]))

    return missed[:limit]

def streaks(answers: list[dict], cards_by_id: dict) -> dict:
    """Считает серии верных ответов подряд.

    Порядок ответов здесь значим — он хронологический, из базы.
    """
    current = 0
    best = 0

    for answer in known_answers(answers, cards_by_id):
        if quiz.is_correct(answer):
            current += 1
            best = max(best, current)
        else:
            current = 0

    return {"current": current, "best": best}

def to_review(answers: list[dict], cards_by_id: dict, playable_ids: set, limit: int = 5) -> list[str]:
    """Отбирает карточки для работы над ошибками: те, где ошибались хоть раз.

    Сначала идут те, где доля верных ниже; при равной доле — где попыток больше,
    потому что там ошибка устойчивее, а не случайна.
    """
    missed = [
        card for card in per_card(answers, cards_by_id)
        if card["correct"] < card["attempts"] and card["card_id"] in playable_ids
    ]
    missed.sort(key=lambda card: (card["correct"] / card["attempts"], -card["attempts"]))

    return [card["card_id"] for card in missed[:limit]]
