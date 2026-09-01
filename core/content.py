import itertools
import json
import os
import re
from pathlib import Path

# поля, без которых карточку нельзя задать вопросом
REQUIRED_FOR_PLAYABLE = ("facts",)

def cards_directory() -> Path:
    raw = os.getenv("CONTENT_PATH")
    if not raw:
        raise RuntimeError(
            "Не задан CONTENT_PATH — путь к репозиторию с карточками. "
            "Добавьте его в .env, например: CONTENT_PATH=../yet-another-wolfgang-content"
        )

    return Path(raw).expanduser() / "cards"

def read_card(path: Path) -> dict:
    card = json.loads(path.read_text(encoding="utf-8"))
    # идентификатор берётся из имени файла: один источник правды
    card["id"] = path.stem

    return card

def find_problems(cards: list[dict]) -> list[str]:
    problems = []
    known = {card["id"] for card in cards}

    for card in sorted(cards, key=lambda card: card["id"]):
        card_id = card["id"]

        if not card.get("title"):
            problems.append(f"{card_id}: нет title")

        for distractor_id in card.get("distractors", []):
            if distractor_id == card_id:
                problems.append(f"{card_id}: карточка указана ловушкой сама себе")
            elif distractor_id not in known:
                problems.append(f"{card_id}: ловушка «{distractor_id}» не существует")

        fragments = card.get("fragments") or []
        if not fragments:
            continue

        for number, fragment in enumerate(fragments, start=1):
            if not fragment.get("name"):
                problems.append(f"{card_id}: у фрагмента {number} нет name")
            if not fragment.get("audio_file_id"):
                problems.append(f"{card_id}: у фрагмента {number} нет audio_file_id")

            # у фрагмента может быть своя атрибуция: части одного произведения
            # нередко берутся у разных исполнителей
            recording = fragment.get("recording") or card.get("recording") or {}
            for field in ("performer", "source"):
                if not recording.get(field):
                    problems.append(f"{card_id}: у фрагмента {number} в recording нет {field}")

        # куски для режима «наугад»: имени у них нет намеренно — назвать место
        # значило бы выдать ответ, — а вот засечка и звук обязательны
        for number, piece in enumerate(card.get("roulette") or [], start=1):
            if not piece.get("audio_file_id"):
                problems.append(f"{card_id}: у случайного куска {number} нет audio_file_id")
            if not piece.get("start"):
                problems.append(f"{card_id}: у случайного куска {number} нет start")

        for field in REQUIRED_FOR_PLAYABLE:
            if not card.get(field):
                problems.append(f"{card_id}: есть запись, но нет {field}")

    return problems

def load_library(directory: Path | None = None) -> dict:
    directory = directory or cards_directory()

    if not directory.is_dir():
        raise RuntimeError(f"Каталог с карточками не найден: {directory}")

    cards = sorted(
        (read_card(path) for path in directory.glob("*.json")),
        key=lambda card: card["id"],
    )

    if not cards:
        raise RuntimeError(f"В каталоге нет ни одной карточки: {directory}")

    problems = find_problems(cards)
    if problems:
        raise RuntimeError("Библиотека карточек повреждена:\n  " + "\n  ".join(problems))

    return {
        "cards": cards,
        "by_id": {card["id"]: card for card in cards},
        "playable": [card for card in cards if card.get("fragments")],
        # карточки, у которых есть что играть в режиме «наугад»
        "roulette": [card for card in cards if card.get("roulette")],
    }

# Ниже — проверки не поломки, а качества. Поломка не даёт боту запуститься,
# а изъян лишь портит подпись, поэтому find_flaws никого не роняет: его
# показывает tools.check_content, а библиотека грузится и с изъянами.

# слова, по которым нельзя судить о пересказе: они встречаются везде
COMMON = {
    "который", "которая", "которое", "которые", "написан", "написана", "написано",
    "написал", "первый", "первая", "первое", "вторая", "второй", "части", "часть",
    "музыка", "музыки", "композитор", "сочинение", "произведение", "оркестр",
    "фортепиано", "премьера", "оркестровые", "оркестровой",
}

def meaningful(text: str) -> set[str]:
    """Содержательные слова текста: от пяти букв и не из общего словаря."""
    return {word for word in re.findall(r"[а-яёa-z]{5,}", text.lower()) if word not in COMMON}

def bare(text: str) -> str:
    """Текст без кавычек, регистра и краевых знаков."""
    return text.lower().strip("«»\"" + " .,:;—-")

# доля общих слов, начиная с которой описание считается пересказом факта
RETELLING = 0.5
# доля слов названия, попавших в описание: «Скрипичный концерт» с описанием
# «единственный скрипичный концерт Бетховена» читается как заикание. Порог выше,
# чем у пересказа: описание объясняет название, и одно-два общих слова законны
REPEATING = 0.6
# доля общих слов у двух фактов одной карточки, при которой это один факт дважды
TWINS = 0.5
# сколько символов названия видно на узкой кнопке, прежде чем начнётся многоточие
VISIBLE = 30

def overlap(one: set, other: set) -> float:
    """Какая доля меньшего множества сидит в большем."""
    if not one or not other:
        return 0.0

    return len(one & other) / min(len(one), len(other))

# отсылка в первом слове факта: он показывается один и опереться ему не на что
LEANING = re.compile(
    r"^(Посвящение|Название|Заголовок|Прозвище|Подзаголовок)\s+(здесь|это|тут)"
    r"|^(Той же|Тем же|В этом же|В том же|На том|Тот самый|Та самая|Те самые)\b"
    r"|^(Он|Она|Они|Его|Её|Ему|Ей)\s+(же|тоже|потом|позже|затем)\b",
)

# факт читают с телефона, под ответом, где уже стоят название, описание
# и подпись к записи: одного предложения хватает, двух — предел
SENTENCES = 2
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")

# зачин, который обещает интересное вместо того, чтобы его рассказать
THROAT_CLEARING = re.compile(
    r"^(Интересно|Любопытно|Примечательно|Мало кто|Не все|Стоит отметить|Известно),?\s",
)

# на своих карточках Вольфганг говорит от первого лица, но в чужой прямой речи
# фамилия законна: «оркестр заорал „Виват, великий Моцарт!“»
# поля, по которым мы отбираем и считаем библиотеку. Бот их не читает, карточка
# без них работает — и заметить пропажу нечем, пока кто-нибудь не соберёт статистику
REFERENCE_FIELDS = ("composer", "era", "genre", "instrument", "difficulty", "year")

MOZART = "Моцарт"
QUOTED = re.compile(r"«[^»]*»")
THIRD_PERSON_MOZART = re.compile(r"\bМоцарт[а-яё]*\b")

def find_flaws(cards: list[dict]) -> dict[str, list[str]]:
    """Изъяны текстов и учёта: то, что портит подпись, но не ломает бота."""
    flaws: dict[str, list[str]] = {name: [] for name in (
        "описание повторяет название",
        "описание повторяет имя фрагмента",
        "описание пересказывает факт",
        "факты повторяют друг друга",
        "факт опирается на соседний",
        "факт длиннее двух предложений",
        "факт начинается с обещания",
        "Моцарт говорит о себе в третьем лице",
        "названия сливаются при обрезке",
        "справочные поля не заполнены",
        "у фрагмента не записана засечка",
        "лицензия записи не указана",
    )}

    seen_short: dict[str, str] = {}

    for card in sorted(cards, key=lambda card: card["id"]):
        card_id, title = card["id"], card.get("title", "")

        short = title[:VISIBLE]
        if short in seen_short:
            flaws["названия сливаются при обрезке"].append(f"{card_id} и {seen_short[short]}: «{short}…»")
        seen_short[short] = card_id

        missing = [field for field in REFERENCE_FIELDS if not card.get(field)]
        if missing:
            flaws["справочные поля не заполнены"].append(f"{card_id}: {', '.join(missing)}")

        fragments = card.get("fragments") or []
        if not fragments:
            continue

        for number, fragment in enumerate(fragments, start=1):
            if "start" not in fragment and not fragment.get("as_is"):
                flaws["у фрагмента не записана засечка"].append(f"{card_id}: фрагмент {number}")

            recording = fragment.get("recording") or card.get("recording") or {}
            if not recording.get("license"):
                flaws["лицензия записи не указана"].append(f"{card_id}: {recording.get('source', '?')}")

        # изъяны самого факта — описание тут ни при чём
        for number, fact in enumerate(card.get("facts") or [], start=1):
            if LEANING.match(fact):
                flaws["факт опирается на соседний"].append(f"{card_id}: факт {number}")

            # цитату считаем одним куском текста: восклицание внутри неё —
            # знак чужой речи, а не конец нашего предложения
            if len(SENTENCE_END.findall(QUOTED.sub("", fact))) > SENTENCES:
                flaws["факт длиннее двух предложений"].append(f"{card_id}: факт {number}")

            if THROAT_CLEARING.match(fact):
                flaws["факт начинается с обещания"].append(f"{card_id}: «{fact[:40]}…»")

            if card.get("composer") == MOZART and THIRD_PERSON_MOZART.search(QUOTED.sub("", fact)):
                flaws["Моцарт говорит о себе в третьем лице"].append(f"{card_id}: факт {number}")

        # пользователю показывается один факт, но за несколько вопросов подряд он
        # увидит и соседние: одна история дважды на карточке выглядит как сбой
        facts = card.get("facts") or []
        for first, second in itertools.combinations(range(len(facts)), 2):
            if overlap(meaningful(facts[first]), meaningful(facts[second])) >= TWINS:
                flaws["факты повторяют друг друга"].append(
                    f"{card_id}: факты {first + 1} и {second + 1}"
                )

        description = card.get("description") or ""
        if not description:
            continue

        opening = bare(description.split()[0])
        repeats_opening = len(opening) > 4 and opening in {bare(word) for word in title.split()}
        if repeats_opening or overlap(meaningful(title), meaningful(description)) >= REPEATING:
            flaws["описание повторяет название"].append(f"{card_id}: «{description[:50]}…»")

        for fragment in fragments:
            name = bare(fragment["name"])
            if len(name) > 4 and name in description.lower() and not bare(title).endswith(name):
                flaws["описание повторяет имя фрагмента"].append(f"{card_id}: «{fragment['name']}»")
                break

        words = meaningful(description)
        for number, fact in enumerate(card.get("facts") or [], start=1):
            if words and len(words & meaningful(fact)) / len(words) >= RETELLING:
                flaws["описание пересказывает факт"].append(f"{card_id}: факт {number}")

    return flaws
