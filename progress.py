import quiz
from data import (
    ANSWER_CORRECT, ANSWER_CORRECT_STREAK, ANSWER_DESCRIPTION, ANSWER_FACT, ANSWER_FRAGMENT,
    ANSWER_RECORDING, ANSWER_WRONG, QUESTION_COUNTER, QUESTION_VARIANTS, STREAK_COUNTER,
    STREAK_FRESH, STREAK_NEW_RECORD_PLUS, STREAK_RECORD, STREAK_RESULTS, STREAK_TITLE,
    STREAK_TITLE_ZERO, VERDICTS,
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

# насколько рекорд должен подрасти, чтобы прибавку стоило отмечать отдельно
BIG_JUMP = 10

def beat_the_record_by_far(length: int, best: int) -> bool:
    """Рекорд побит не на единицу, а с запасом.

    Смотрим на саму прибавку. Рекорд обычно растёт по чуть-чуть, и каждая такая
    серия — формально рекордная; отдельной реплики заслуживает та, где прежний
    результат не подвинули, а оставили далеко позади.
    """
    return length - best >= BIG_JUMP

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
    if key == "record" and beat_the_record_by_far(length, best):
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

def answer_caption(
    naming: str,
    description: str,
    fragment: str,
    fact: str,
    recording: dict,
    reply: str,
    correct: bool,
    chosen: str = "",
    streak: int = 0,
) -> str:
    """Подпись к отвеченному вопросу.

    Порядок продиктован тем, что видно до разворачивания: сначала итог и что
    это было — ради этого кнопку и нажимали. Реплика, факт и кредит записи
    уезжают ниже, их можно прочитать и потом.

    Название с описанием стоят вплотную, без пустой строки: вместе они
    читаются как одна фраза, а каждая пустая строка — это строка экрана.
    """
    if not correct:
        head = ANSWER_WRONG.format(naming=naming, chosen=chosen)
    elif streak:
        head = ANSWER_CORRECT_STREAK.format(naming=naming, length=streak)
    else:
        head = ANSWER_CORRECT.format(naming=naming)

    opening = [head]
    if description:
        opening.append(ANSWER_DESCRIPTION.format(description=description))
    # у отдельной пьесы имя фрагмента совпадает с названием — повторять его незачем
    if fragment:
        opening.append(ANSWER_FRAGMENT.format(fragment=fragment))

    return "\n\n".join([
        "\n".join(opening),
        reply,
        ANSWER_FACT.format(fact=fact),
        ANSWER_RECORDING.format(**recording),
    ])
