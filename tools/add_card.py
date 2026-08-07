"""Добавляет карточку в библиотеку.

С записью — обрезает фрагмент, чистит теги, загружает в Telegram и забирает file_id:

    python -m tools.add_card --id grieg-mountain-king --title "Григ — «В пещере горного короля»" \\
        --audio "~/Desktop/YAWolfgang/Grieg - In the Hall Of The Mountain King.mp3" \\
        --fragment "В пещере горного короля" \\
        --performer "Kevin MacLeod" --source "Musopen" \\
        --fact "Первый факт." --fact "Второй факт." \\
        --distractor tarrega-recuerdos

Без записи — карточка будет только вариантом ответа:

    python -m tools.add_card --id verdi-aida --title "Верди — «Аида»"
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot

import content

FRAGMENT_TITLE = "🎵 Фрагмент"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Добавляет карточку в библиотеку")
    parser.add_argument("--id", required=True, help="идентификатор, он же имя файла")
    parser.add_argument("--title", required=True, help="правильный ответ, как он будет на кнопке")
    parser.add_argument("--audio", help="исходный аудиофайл")
    parser.add_argument("--start", default="0", help="начало фрагмента, секунды (по умолчанию 0)")
    parser.add_argument("--duration", default="35", help="длительность фрагмента (по умолчанию 35)")
    parser.add_argument("--fragment", help="название звучащего эпизода")
    parser.add_argument("--fact", action="append", default=[], help="факт, можно повторять")
    parser.add_argument("--performer", help="исполнитель записи")
    parser.add_argument("--source", help="источник записи")
    parser.add_argument("--distractor", action="append", default=[], help="предпочтительная ловушка, можно повторять")

    return parser.parse_args()

def cut_fragment(source: Path, target: Path, start: str, duration: str) -> None:
    """Вырезает кусок, снимает обложку и главы, ставит нейтральный заголовок.

    Метаданные не стираются целиком: artist, comment и copyright несут атрибуцию
    записи, а её удаление нарушило бы условия лицензии.
    """
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", start, "-t", duration,
            "-i", str(source),
            "-vn", "-map_chapters", "-1",
            "-metadata", "title=Фрагмент",
            "-metadata", "album=",
            "-codec", "copy",
            str(target),
        ],
        check=True,
    )

async def upload(path: Path, performer: str | None) -> str:
    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("ADMIN_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "Для загрузки нужны BOT_TOKEN и ADMIN_CHAT_ID в .env. "
            "Свой chat_id можно узнать командой /chatid у бота."
        )

    async with Bot(token) as bot:
        with path.open("rb") as audio:
            message = await bot.send_audio(
                chat_id=chat_id,
                audio=audio,
                title=FRAGMENT_TITLE,
                performer=performer or "",
                caption=f"Загружено tools.add_card: {path.name}",
            )

    return message.audio.file_id

def build_card(args: argparse.Namespace, file_id: str | None) -> dict:
    card = {"title": args.title}

    if args.distractor:
        card["distractors"] = args.distractor

    if file_id:
        card["fragment"] = args.fragment or args.title
        card["facts"] = args.fact
        card["audio_file_id"] = file_id
        card["recording"] = {"performer": args.performer, "source": args.source}

    return card

def main() -> int:
    load_dotenv()
    args = parse_args()

    try:
        directory = content.cards_directory()
    except RuntimeError as error:
        print(error)
        return 1

    path = directory / f"{args.id}.json"
    if path.exists():
        print(f"Карточка уже существует: {path}")
        return 1

    if args.audio:
        for field in ("performer", "source"):
            if not getattr(args, field):
                print(f"Для карточки с записью нужен --{field}: это условие лицензии.")
                return 1

        if not args.fact:
            print("Предупреждение: фактов нет, после ответа боту будет нечего показать.")

        source = Path(args.audio).expanduser()
        if not source.is_file():
            print(f"Файл не найден: {source}")
            return 1

        with tempfile.TemporaryDirectory() as tmp:
            fragment = Path(tmp) / "fragment.mp3"
            cut_fragment(source, fragment, args.start, args.duration)
            print(f"Фрагмент вырезан: {args.start}s + {args.duration}s")
            file_id = asyncio.run(upload(fragment, args.performer))
            print(f"Загружено в Telegram: {file_id}")
    else:
        file_id = None

    path.write_text(
        json.dumps(build_card(args, file_id), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Записано: {path}")

    cards = sorted(
        (content.read_card(item) for item in directory.glob("*.json")),
        key=lambda card: card["id"],
    )
    problems = content.find_problems(cards)
    if problems:
        print("\nБиблиотека требует внимания:")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print(f"Библиотека в порядке: {len(cards)} карточек.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
