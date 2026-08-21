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

def words(text: str) -> set:
    text = unicodedata.normalize("NFKD", text.lower())

    return {word for word in re.split(r"[^a-z0-9]+", text) if len(word) > 2}

def find_audio(card_id: str, files: list[tuple[set, Path]]) -> Path | None:
    """Файл, из которого резать. Имена файлов и идентификаторы карточек писал
    один человек, поэтому общие слова в них — достаточно надёжный признак."""
    best, score = None, 0
    for name, path in files:
        common = len(words(card_id) & name)
        if common > score:
            best, score = path, common

    return best if score >= MATCH else None

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
        files += [(words(path.stem), path) for path in folder.glob("*.mp3")]

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
