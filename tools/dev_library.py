"""Собирает маленькую библиотеку для разработки — под отдельного бота.

Идентификаторы аудио в Телеграме привязаны к боту: на чужой файл бот отвечает
«wrong file identifier». Поэтому тестовому боту не годится боевая библиотека —
ему нужны свои фрагменты, залитые им самим.

    BOT_TOKEN=токен_тестового python -m tools.dev_library \\
        --into ~/PetProjects/wolfgang-dev-content \\
        --audio "~/Desktop/YAWolfgang" --audio "~/Desktop/YAWolfgang v2" --count 12

Токен подменяется в командной строке, а не в .env: карточки-источники берутся
из боевой библиотеки, и CONTENT_PATH должен остаться боевым. Заливка при этом
идёт от тестового бота — иначе получатся идентификаторы боевого и смысл
потеряется.

Карточки берутся из боевой библиотеки как есть — с фактами, описаниями и
атрибуцией, — меняется только идентификатор аудио. Фрагмент режется с тридцатой
секунды: попадать в ту же засечку, что в боевой карточке, незачем.

Ловушки, на которые ссылаются выбранные карточки, тоже переезжают — без записи,
одними названиями. Иначе библиотека не пройдёт проверку: ловушка, которой нет,
считается поломкой.
"""

import argparse
import asyncio
import json
import os
import difflib
import re
import sys
import tempfile
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot

from core import content
from tools.add_card import cut_fragment, upload

# с какой секунды и сколько резать. Для разработки важно только, чтобы звучало
START = "30"
DURATION = "20"

# сколько общих слов между именем файла и идентификатором карточки считать
# совпадением. Одно слово — это обычно просто фамилия композитора, мало
MATCH = 2

# Номер части пишут то цифрой, то римской: «No. 5» и «V. Allegro». Приводим
# к одному виду, иначе пятая симфония не отличается от девятой
# Служебные слова не опознают ничего, но набирают проходной балл: «mozart» и
# «the» — уже два общих слова, и ария Царицы ночи сходится с увертюрой к
# «Свадьбе Фигаро». Короткие отсеиваются длиной, эти приходится назвать
STOP = {
    "the", "and", "for", "from", "with", "der", "die", "das", "den", "und",
    "les", "des", "del", "dei", "della", "aus", "mit", "per", "con", "sur",
    "arr", "arranged", "version", "excerpt", "complete", "solo", "major", "minor",
}

ROMAN = {
    "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5",
    "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
}

def words(text: str) -> set:
    """Значимые слова названия. Числа значимы всегда, даже однозначные.

    Диакритика снимается, а не разделяет: после разложения «Dvořák» — это «d»,
    «v», «o», «r», галочка, «a», ударение, «k», и если галочку считать границей
    слова, фамилия распадается на «dvor» и «ak», ни с чем не совпадая.
    """
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(sign for sign in text if not unicodedata.combining(sign))

    found = set()
    for token in re.split(r"[^a-z0-9]+", text):
        if token in ROMAN:
            found.add(ROMAN[token])
        elif token in STOP:
            continue
        elif token.isdigit() or len(token) > 2:
            # «preludes» и «prelude» — одно слово: без этого вторая прелюдия
            # не становится претендентом, и ничья, которая спасла бы от
            # неверного выбора, не случается
            found.add(token[:-1] if len(token) > 4 and token.endswith("s") else token)

    return found

# Исходники лежат вперемешку: mp3, flac, m4a. cut_fragment чужой кодек
# перекодирует сам, так что искать только mp3 значит не найти половину
SOUNDS = ("*.mp3", "*.flac", "*.m4a", "*.wav", "*.ogg", "*.oga", "*.opus")

def sound_files(folder: Path) -> list[Path]:
    return [path for pattern in SOUNDS for path in folder.glob(pattern)]

# Фамилию пишут по-разному: Rachmaninoff и Rachmaninov, Balakirev и Balakirew.
# Требовать побуквенного совпадения — значит не найти половину записей
SAME_NAME = 0.85

def same_surname(surname: str, name: set) -> bool:
    return any(
        difflib.SequenceMatcher(None, surname, word).ratio() >= SAME_NAME
        for word in name
    )

def find_audio(card_id: str, files: list[tuple[set, Path]]) -> Path | None:
    """Файл, из которого резать.

    Имена файлов и идентификаторы карточек писал один человек, поэтому общие
    слова — достаточно надёжный признак. Но не сами по себе: у «пятой симфонии»
    и «девятой» общего два слова из двух, и без сверки чисел одна молча
    подменяет другую. Число из идентификатора обязано найтись в имени файла.
    """
    wanted = words(card_id)
    numbers = {word for word in wanted if word.isdigit()}
    # первое слово идентификатора — почти всегда фамилия композитора, и оно
    # обязано найтись в имени файла. Без этого «violin» и «concerto» набирают
    # проходной балл сами по себе, и скрипичный концерт Бетховена молча
    # становится вивальдиевским
    surname = card_id.split("-")[0]

    scored = []
    for name, path in files:
        if not same_surname(surname, name) or numbers - name:
            continue
        # цифры отсеивают, но не опознают: «No. 2» в опусе прелюдии — та же
        # двойка, что и во втором концерте, и засчитывать её как слово нельзя
        common = (wanted & name) - numbers
        # фамилия совпала неточно и в пересечение не попала, но она-то и есть
        # главное свидетельство
        weight = len(common) + (surname not in common)
        if weight >= MATCH:
            scored.append((weight, path))

    if not scored:
        return None

    best = max(weight for weight, _ in scored)
    winners = [path for weight, path in scored if weight == best]

    # Ничья значит, что различающего слова в идентификаторе нет: две прелюдии
    # одного композитора неразличимы, если тональность потерялась при разборе.
    # Угадывать тут нельзя — пусть человек назовёт файл сам
    return winners[0] if len(winners) == 1 else None

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Библиотека для разработки")
    parser.add_argument("--into", required=True, type=Path, help="куда сложить карточки")
    parser.add_argument("--audio", action="append", required=True, type=Path,
                        help="папка с исходниками, можно повторять")
    parser.add_argument("--count", type=int, default=12, help="сколько карточек с записью")

    return parser.parse_args()

def playable_card(card: dict, file_id: str) -> dict:
    """Карточка для тестовой библиотеки: всё своё, кроме идентификатора аудио."""
    fragment = card["fragments"][0]

    copy = {key: value for key, value in card.items() if key not in ("id", "fragments")}
    copy["fragments"] = [{
        "name": fragment["name"],
        "audio_file_id": file_id,
        **({"recording": fragment["recording"]} if fragment.get("recording") else {}),
    }]

    return copy

def silent_card(card: dict) -> dict:
    """Ловушка: нужна только чтобы было из чего выбирать на кнопках."""
    return {key: card[key] for key in ("title", "composer") if card.get(key)}

async def build(args: argparse.Namespace) -> int:
    # Первым делом — от чьего имени заливаем. Идентификаторы привязаны к боту,
    # и залить тестовую библиотеку боевым токеном — самая лёгкая из ошибок:
    # всё проходит успешно, а работать не будет
    async with Bot(os.environ["BOT_TOKEN"]) as bot:
        print(f"Заливаю от имени @{(await bot.get_me()).username}\n")

    library = content.load_library()
    by_id = library["by_id"]

    files = []
    for folder in args.audio:
        folder = folder.expanduser()
        if not folder.is_dir():
            print(f"Нет такой папки: {folder}")
            return 1
        files += [(words(path.stem), path) for path in sound_files(folder)]

    print(f"Исходников: {len(files)}")

    chosen = {}
    for card in library["playable"]:
        if len(chosen) == args.count:
            break
        source = find_audio(card["id"], files)
        if source:
            chosen[card["id"]] = (card, source)

    if len(chosen) < args.count:
        print(f"Нашлось только {len(chosen)} карточек с исходниками")

    cards = args.into.expanduser() / "cards"
    cards.mkdir(parents=True, exist_ok=True)

    written = 0
    for card_id, (card, source) in chosen.items():
        print(f"{card_id} ← {source.name}")

        with tempfile.TemporaryDirectory() as workspace:
            piece = Path(workspace) / f"{card_id}.mp3"
            cut_fragment(source, piece, START, DURATION)
            file_id = await upload(piece, card.get("recording", {}).get("performer"))

        (cards / f"{card_id}.json").write_text(
            json.dumps(playable_card(card, file_id), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1

    # ловушки: и те, что названы в карточках, и просто соседи для разнообразия
    wanted = {trap for card, _ in chosen.values() for trap in card.get("distractors", [])}
    for trap_id in sorted(wanted - set(chosen)):
        if trap_id not in by_id:
            continue
        (cards / f"{trap_id}.json").write_text(
            json.dumps(silent_card(by_id[trap_id]), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"\nГотово: {written} с записью, {len(wanted - set(chosen))} ловушками")
    print(f"Положите в .env: CONTENT_PATH={args.into}")

    return 0

def main() -> int:
    load_dotenv(os.getenv("ENV_FILE", ".env"))

    return asyncio.run(build(parse_args()))

if __name__ == "__main__":
    sys.exit(main())
