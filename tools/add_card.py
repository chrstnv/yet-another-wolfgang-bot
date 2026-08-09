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
from telegram.error import TelegramError

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
    parser.add_argument("--gain", type=float, help="подъём громкости в дБ вместо автоматического")
    parser.add_argument("--update", action="store_true", help="перезаписать существующую карточку")
    parser.add_argument("--append", action="store_true", help="добавить ещё один фрагмент, не заменяя прежние")

    return parser.parse_args()

def audio_codec(source: Path) -> str:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name",
            "-of", "default=nw=1:nk=1",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return result.stdout.strip()

# Open Audio License прямо запрещает менять теги с атрибуцией, так что
# переносим их все, а не только artist: у части записей солист, дирижёр
# и оркестр расписаны по отдельным полям. Тег composer не берём: лицензия
# защищает исполнителя, а фамилия автора в файле — это подсказка к ответу
ATTRIBUTION_TAGS = (
    "artist", "album_artist", "performer", "conductor", "ensemble",
    "comment", "copyright", "license",
)

def attribution(source: Path) -> dict[str, str]:
    """Достаёт теги с атрибуцией, где бы они ни лежали.

    В mp3 теги хранятся на контейнере, а в ogg и opus — на аудиопотоке.
    ffmpeg по умолчанию переносит только первые, поэтому при перекодировании
    ogg строчка вроде «(O) EFF Open Audio License» пропадала молча.
    """
    found: dict[str, str] = {}

    for entries in ("stream_tags", "format_tags"):
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", entries,
                "-of", "default=nw=1",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            name, _, value = line.removeprefix("TAG:").partition("=")
            # теги контейнера идут вторыми и перекрывают потоковые:
            # для mp3 они и есть единственный источник правды
            if name.lower() in ATTRIBUTION_TAGS and value.strip():
                found[name.lower()] = value.strip()

    return found

def cut_fragment(source: Path, target: Path, start: str, duration: str, gain: float = 0.0) -> None:
    """Вырезает кусок, снимает обложку и главы, ставит нейтральный заголовок.

    Метаданные не стираются целиком: artist, comment и copyright несут атрибуцию
    записи, а её удаление нарушило бы условия лицензии.

    Часть исходников только называются mp3, а внутри лежит другой кодек — такие
    приходится перекодировать, потоковое копирование на них не работает.
    Подъём громкости — тоже: фильтр применить к скопированному потоку нельзя.
    """
    codec = audio_codec(source)
    reencode = codec != "mp3" or gain
    encoding = ["-codec:a", "libmp3lame", "-q:a", "2"] if reencode else ["-codec", "copy"]

    if codec != "mp3":
        print(f"Исходник в формате {codec}, перекодирую в mp3")

    credits = attribution(source)
    if credits:
        print(f"Атрибуция в файле: {', '.join(f'{k}={v}' for k, v in credits.items())}")

    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", start, "-t", duration,
            "-i", str(source),
            "-vn", "-map_chapters", "-1",
            *(["-af", f"volume={gain:.1f}dB"] if gain else []),
            *[arg for name, value in credits.items() for arg in ("-metadata", f"{name}={value}")],
            "-metadata", "title=Фрагмент",
            "-metadata", "album=",
            *encoding,
            str(target),
        ],
        check=True,
    )

# ниже этого пика фрагмент на телефоне звучит заметно тише соседей по библиотеке
QUIET_PEAK = -12.0
# оставляем запас, чтобы подъём ничего не срезал
TARGET_PEAK = -4.0
# выше этого не поднимаем: усилитель не отличает музыку от шума, и на тихой
# записи вместе с оркестром вырастает зал, лента и всё остальное. Тихий
# фрагмент лучше оставить тихим, чем превратить в шипение
MAX_GAIN = 10.0

def peak_level(path: Path) -> float:
    """Самый громкий отсчёт фрагмента, в децибелах относительно максимума."""
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-af", "volumedetect", "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )

    for line in result.stderr.splitlines():
        if "max_volume:" in line:
            return float(line.split("max_volume:")[1].replace("dB", "").strip())

    return 0.0

def leading_silence(path: Path) -> float:
    """Сколько секунд тишины в начале фрагмента.

    Записи нередко начинаются с паузы, и фрагмент открывается пустотой —
    на слух это ловилось только после заливки.
    """
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-af", "silencedetect=noise=-50dB:d=0.3",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )

    for line in result.stderr.splitlines():
        if "silence_start: 0" in line:
            for following in result.stderr.splitlines():
                if "silence_end" in following:
                    return float(following.split("silence_end:")[1].split("|")[0])
    return 0.0

async def upload_once(path: Path, performer: str | None) -> str:
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
                # значения по умолчанию рассчитаны на короткие запросы,
                # а здесь уходит файл на несколько мегабайт
                connect_timeout=30,
                write_timeout=180,
                read_timeout=60,
            )

    return message.audio.file_id

async def upload(path: Path, performer: str | None, attempts: int = 4) -> str:
    """Загружает файл, переживая сетевые сбои.

    Обрывы соединения при заливке — обычное дело, а на десятках карточек подряд
    почти неизбежное. Ошибку отдаём наружу только если не помогла ни одна попытка.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await upload_once(path, performer)
        except TelegramError as error:
            if attempt == attempts:
                raise
            pause = 2 ** attempt
            print(f"  попытка {attempt} не удалась ({type(error).__name__}), жду {pause}с")
            await asyncio.sleep(pause)

def build_card(args: argparse.Namespace, file_id: str | None, existing: dict | None = None) -> dict:
    """Собирает карточку. При обновлении сохраняет то, что не передано явно:
    заменить запись, не потеряв уже написанные факты, — обычное дело.
    """
    card = dict(existing or {})
    card.pop("id", None)

    card["title"] = args.title

    if args.distractor:
        card["distractors"] = args.distractor

    # факты и название фрагмента можно править отдельно от записи
    if args.fact:
        card["facts"] = args.fact

    if file_id:
        # засечку и длительность храним рядом с фрагментом: без них перерезать
        # его потом можно только по памяти, а память — плохое место для секунд
        fragment = {
            "name": args.fragment or args.title,
            "start": args.start,
            "duration": args.duration,
            "audio_file_id": file_id,
        }
        # подъём, выставленный на слух, автоматика заново не угадает
        if args.gain is not None:
            fragment["gain"] = args.gain
        recording = {"performer": args.performer, "source": args.source}

        existing_recording = card.get("recording")
        if args.append and existing_recording and existing_recording != recording:
            # части одного произведения бывают у разных исполнителей —
            # тогда атрибуция принадлежит фрагменту, а не карточке.
            # Без --append прежние фрагменты стираются, и держать на карточке
            # кредит исчезнувшей записи нельзя: это была бы ложная атрибуция
            fragment["recording"] = recording
        else:
            card["recording"] = recording

        # --append добавляет к карточке ещё один фрагмент того же произведения,
        # без него новая запись заменяет прежние
        card["fragments"] = (card.get("fragments", []) if args.append else []) + [fragment]
        card.setdefault("facts", [])

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
    if path.exists() and not (args.update or args.append):
        print(f"Карточка уже существует: {path}. Для перезаписи добавьте --update.")
        return 1

    if args.audio:
        for field in ("performer", "source"):
            if not getattr(args, field):
                print(f"Для карточки с записью нужен --{field}: это условие лицензии.")
                return 1

        if not args.fact and not (path.exists() and content.read_card(path).get("facts")):
            print("Предупреждение: фактов нет, после ответа боту будет нечего показать.")

        source = Path(args.audio).expanduser()
        if not source.is_file():
            print(f"Файл не найден: {source}")
            return 1

        with tempfile.TemporaryDirectory() as tmp:
            fragment = Path(tmp) / "fragment.mp3"
            cut_fragment(source, fragment, args.start, args.duration)
            print(f"Фрагмент вырезан: {args.start}s + {args.duration}s")

            # записи приходят с очень разным уровнем, и тихие тонут на телефоне
            # рядом с громкими; поднимаем по пику, чтобы не трогать динамику внутри
            if args.gain is not None:
                # автоматика ровняет по пику и не слышит, что вместе с музыкой
                # растёт зал; на таких записях уровень выставляется на слух
                print(f"Подъём задан вручную: {args.gain:+.1f} дБ")
                cut_fragment(source, fragment, args.start, args.duration, gain=args.gain)
            else:
                peak = peak_level(fragment)
                if peak < QUIET_PEAK:
                    gain = min(TARGET_PEAK - peak, MAX_GAIN)
                    print(f"Запись тихая (пик {peak:.1f} дБ), поднимаю на {gain:.1f} дБ")
                    if TARGET_PEAK - peak > MAX_GAIN:
                        print(
                            f"  до уровня библиотеки не хватает {TARGET_PEAK - peak - MAX_GAIN:.1f} дБ, "
                            f"но выше поднимать нельзя: вылезет шум. Возможно, стоит взять "
                            f"фрагмент из более громкого места"
                        )
                    cut_fragment(source, fragment, args.start, args.duration, gain=gain)

            pause = leading_silence(fragment)
            if pause >= 1.0:
                start = float(args.start) + pause
                print(
                    f"Предупреждение: фрагмент открывается тишиной ({pause:.1f}с). "
                    f"Возможно, стоит перерезать с --start {start:.0f}"
                )
            file_id = asyncio.run(upload(fragment, args.performer))
            print(f"Загружено в Telegram: {file_id}")
    else:
        file_id = None

    existing = content.read_card(path) if path.exists() else None

    path.write_text(
        json.dumps(build_card(args, file_id, existing), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{'Обновлено' if existing else 'Записано'}: {path}")

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
