import random

QUIZ_LENGTH = 10

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
    """Десять случайных карточек, выстроенных от лёгких к трудным.

    Набор случайный, а порядок нет: начинать с «Полёта валькирий» и заканчивать
    сонатой Скарлатти приятнее, чем наоборот. Карточки без проставленной
    сложности уходят в конец, а не притворяются самыми лёгкими.
    """
    selected = random.sample(cards, k=min(length, len(cards)))
    selected.sort(key=lambda card: (card.get("difficulty") is None, card.get("difficulty") or 0))

    return session_for([card["id"] for card in selected])

STREAK_STEP = 5

def streak_queue(cards: list[dict], step: int = STREAK_STEP) -> list[str]:
    """Очередь для серии: по несколько карточек каждой сложности, от лёгких
    к трудным, а следом всё оставшееся вперемешку.

    Проверять «ответил ли пользователь пять подряд» не нужно: серия обрывается
    первой же ошибкой, поэтому до шестого вопроса доходит только тот, кто взял
    предыдущие пять. Порядок очереди и есть правило подъёма сложности.
    """
    by_level: dict[int, list[dict]] = {}
    for card in cards:
        level = card.get("difficulty")
        if level is not None:
            by_level.setdefault(level, []).append(card)

    queue = []
    for level in sorted(by_level):
        block = by_level[level]
        queue += [card["id"] for card in random.sample(block, k=min(step, len(block)))]

    # хвост: и то, что не поместилось в блоки, и карточки без проставленной сложности
    graded = set(queue)
    rest = [card["id"] for card in cards if card["id"] not in graded]
    random.shuffle(rest)

    return queue + rest

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
