import json
import os
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
    }
