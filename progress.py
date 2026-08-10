import quiz
from data import (
    QUESTION_COUNTER, QUESTION_VARIANTS, STREAK_COUNTER, STREAK_FRESH, STREAK_NEW_RECORD_PLUS,
    STREAK_RECORD, STREAK_RESULTS, STREAK_TITLE, STREAK_TITLE_ZERO, VERDICTS,
)

def question_caption(session: dict) -> str:
    """Подпись к вопросу: сама формулировка и место в квизе.

    В серии считать «сколько осталось» бессмысленно — очередь во всю
    библиотеку. Показываем обратное: сколько уже взято подряд. На первом
    вопросе счёт нулевой, и строчка только мешала бы.
    """
    # реплику выбирает send_question и кладёт в сессию: подпись рисуется заново,
    # когда открывают спрятанные варианты, и текст не должен при этом меняться
    question = session.get("question") or QUESTION_VARIANTS[0]

    if session.get("mode") == quiz.STREAK:
        taken = session["position"]
        return f"{STREAK_COUNTER.format(length=taken)}\n\n{question}" if taken else question

    return "{}\n\n{}".format(
        QUESTION_COUNTER.format(number=session["position"] + 1, total=len(session["queue"])),
        question,
    )

DECADE = 10
# ниже двадцати рекорды переписываются почти каждой серией, и особая реплика
# на них обесценилась бы; десятки — первый рубеж, который берут не случайно
FIRST_MILESTONE = 20

def jumped_a_decade(length: int, best: int) -> bool:
    """Рекорд не просто побит, а перешагнул очередной десяток.

    Разница между 21 и 22 игроку не заметна, между 19 и 21 — заметна: сменилась
    первая цифра. На это и смотрим, а не на размер прибавки.
    """
    return length >= FIRST_MILESTONE and length // DECADE > best // DECADE

def streak_message(length: int, best: int, fresh: list[str] = ()) -> str:
    """Итог серии: счёт крупно, следом чем она кончилась, рекорд и находки.

    Когда серия сама стала рекордом, строчка о прежнем не нужна: она повторяла
    бы только что сказанное. Нулевому рекорду тоже нечего сообщать.
    """
    if not length:
        key = "zero"
    elif length > best:
        key = "record"
    else:
        key = "some"

    verdict_line = STREAK_RESULTS[key]
    if key == "record" and jumped_a_decade(length, best):
        verdict_line = STREAK_NEW_RECORD_PLUS

    blocks = [
        STREAK_TITLE.format(length=length) if length else STREAK_TITLE_ZERO,
        verdict_line.format(length=length),
    ]

    if key != "record" and best:
        blocks.append(STREAK_RECORD.format(record=best))

    if fresh:
        listed = "\n".join(f"• {title}" for title in fresh)
        blocks.append(f"{STREAK_FRESH.format(count=len(fresh))}\n{listed}")

    return "\n\n".join(blocks)

def first_time(session: dict) -> list[str]:
    """Произведения, которые в этой сессии услышаны впервые.

    Что человек слышал раньше, session узнаёт на старте: к концу квиза
    ответы уже лежат в базе, и отличить новое от старого по ней нельзя.
    """
    seen = session.get("seen") or set()

    fresh = []
    for answer in session["answers"]:
        card_id = answer["card_id"]
        if card_id not in seen and card_id not in fresh:
            fresh.append(card_id)

    return fresh

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
