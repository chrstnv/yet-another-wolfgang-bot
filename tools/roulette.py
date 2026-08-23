"""Режет из записи случайные куски — для режима «наугад».

    python -m tools.roulette --card grieg-morning --count 3 \\
        --audio ~/Desktop/YAWolfgang --audio "~/Desktop/YAWolfgang v2"

    python -m tools.roulette --all --count 3 --audio ~/Desktop/YAWolfgang

Обычный фрагмент отбирается руками: это тема, по которой вещь узнают. Здесь
наоборот — место должно быть незнакомым, поэтому засечка случайная, а имени у
куска нет: назвать его значило бы выдать ответ.

Куски дописываются в карточку полем `roulette` рядом с `fragments`. Идентификаторы
привязаны к боту, поэтому для тестового бота режьте своим токеном:

    ENV_FILE=.env.dev python -m tools.roulette --all --count 3 --audio ...

Случайное окно легко попадает в паузу между частями, в аплодисменты или в
затихание. Поэтому кандидат проверяется на слух машины: измеряется громкость и
тишина в начале, а края записи не трогаются вовсе.
"""

import argparse
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError

from core import content
from tools.add_card import (
    MAX_GAIN, TARGET_PEAK, attribution, cut_fragment, leading_silence, upload,
)
from tools.dev_library import find_audio, sound_files, words

# Сколько записи не трогать с начала и с конца. В начале — вступления, настройка
# оркестра и тишина перед первой нотой; в конце — затихания и аплодисменты
HEAD = 0.15
TAIL = 0.10

# Длина куска. Короче обычного фрагмента: с незнакомого места и двадцати пяти
# секунд достаточно, чтобы услышать фактуру, а дольше слушать мучительно
LENGTH = 25

# Насколько кусок должен отстоять от уже занятых мест, в секундах
APART = 20

# Куда подтягивать громкость. Средний уровень, а не пик: у куска с одним щелчком
# пик высокий, а звучит он тихо, — и рядом с соседями по квизу это слышно сразу
TARGET_MEAN = -18.0

# Тише этого — уже не музыка, а затихание, пауза между частями или шорох зала.
# Порог низкий намеренно: adagio sostenuto держится на тридцати пяти децибелах,
# и строгая мерка выгнала бы из режима все ноктюрны, сарабанды и адажио разом,
# оставив одну громкую музыку
QUIET_MEAN = -45.0

# насколько кусок может остаться тише цели после выравнивания. Тихую запись
# до общего уровня не дотянуть — усилитель поднимет вместе с музыкой шипение,
# — и это честная разница, а не брак. А вот когда средний уровень низкий при
# пике у потолка, поднимать нечем вовсе: обычно это щелчок, и место мы меняем
TOLERANCE = 10.0

# тишина в начале слышна как заминка
SILENT_START = 0.3

# Аплодисменты громкие и не тишина, поэтому прежние проверки их пропускали.
# Отличает их широкополосность: у шума знак меняется впятеро чаще, чем у музыки.
# Замеры по библиотеке: музыка 0.019–0.047, аплодисменты 0.165–0.175
NOISY = 0.10

# Сколько раз пытаться найти годное окно, прежде чем сдаться
TRIES = 40

def duration_of(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        check=True, capture_output=True, text=True,
    )

    return float(result.stdout.strip())

def fits(start: float, total: float, busy: list[tuple[float, float]], gap: float = APART) -> bool:
    """Годится ли засечка: не на краях записи и не поверх уже занятого.

    Занятое — это отобранный руками фрагмент (его-то как раз узнают) и куски,
    выбранные раньше. Между ними держится зазор, иначе два «случайных» места
    окажутся почти одним и тем же.

    На короткой записи зазор — роскошь: у семидесятитрёхсекундной темы он
    съедает всё свободное место, и кусок не находится вовсе. Тогда его
    отбрасывают и довольствуются тем, что куски просто не перекрываются.
    """
    if start < total * HEAD or start + LENGTH > total * (1 - TAIL):
        return False

    return all(
        start + LENGTH + gap <= taken or start >= taken + length + gap
        for taken, length in busy
    )

def taken_places(card: dict) -> list[tuple[float, float]]:
    """Места, которые уже заняты: отобранный фрагмент и прежние куски."""
    places = []

    for fragment in card.get("fragments") or []:
        if fragment.get("start"):
            places.append((float(fragment["start"]), float(fragment.get("duration", LENGTH))))

    for piece in card.get("roulette") or []:
        places.append((float(piece["start"]), float(piece.get("duration", LENGTH))))

    return places

def levels(path: Path) -> tuple[float, float, float]:
    """Средний уровень, пик и частота переходов через ноль.

    Три числа одним проходом ffmpeg: два про громкость, третье про то,
    музыка это вообще или шум зала.
    """
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(path),
            "-af", "volumedetect,astats=metadata=1", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )

    mean = peak = crossings = 0.0
    for line in result.stderr.splitlines():
        if "mean_volume:" in line:
            mean = float(line.split("mean_volume:")[1].replace("dB", "").strip())
        elif "max_volume:" in line:
            peak = float(line.split("max_volume:")[1].replace("dB", "").strip())
        elif "Zero crossings rate:" in line and not crossings:
            crossings = float(line.split("Zero crossings rate:")[1].strip())

    return mean, peak, crossings

def gain_for(mean: float, peak: float) -> float:
    """На сколько поднять или опустить кусок, чтобы он звучал как соседи.

    Тянем средний уровень к цели, но не дальше, чем позволяет запас до максимума:
    иначе подъём срежет верхушки. И не больше, чем можно вообще, — усилитель не
    отличает музыку от шума, и на тихой записи вместе с оркестром растёт зал.
    """
    return round(min(TARGET_MEAN - mean, TARGET_PEAK - peak, MAX_GAIN), 1)

def evens_out(mean: float, peak: float) -> bool:
    """Удастся ли довести кусок до общей громкости."""
    return mean + gain_for(mean, peak) >= TARGET_MEAN - TOLERANCE

def good_enough(piece: Path) -> str:
    """Пустая строка, если кусок годен, иначе — чем именно плох."""
    if leading_silence(piece) > SILENT_START:
        return "начинается с тишины"

    return ""

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Случайные куски для режима «наугад»")
    parser.add_argument("--card", help="идентификатор карточки")
    parser.add_argument("--all", action="store_true", help="все карточки с записью")
    parser.add_argument("--count", type=int, default=3, help="сколько кусков на карточку")
    parser.add_argument("--audio", action="append", required=True, type=Path,
                        help="папка с исходниками, можно повторять")
    parser.add_argument("--source", type=Path,
                        help="назвать файл прямо, если по имени он не находится")
    parser.add_argument("--check", action="store_true",
                        help="ничего не резать, только показать состояние библиотеки")

    return parser.parse_args()

def credit(card: dict, source: Path) -> dict:
    """Чем подписать кусок — или пустота, если честно подписать нечем.

    Кусок может быть вырезан не из той записи, которой подписана карточка, и
    тогда наследовать её подпись значит соврать в титрах: лицензии требуют
    называть исполнителя той записи, которая звучит.

    Выдумывать подпись из тегов не годится — там мешанина из композитора,
    солиста и оркестра, а источника нет вовсе. Зато в карточке уже есть
    выверенные человеком подписи: если теги файла называют кого-то из них,
    берём готовую.
    """
    artist = attribution(source).get("artist", "")
    if not artist:
        return {}

    known = [fragment.get("recording") for fragment in card.get("fragments") or []]
    known.append(card.get("recording"))

    for recording in known:
        if not recording:
            continue
        names = [word for word in re.split(r"[\s,]+", recording["performer"]) if len(word) > 2]
        if any(name in artist for name in names):
            return {} if recording is card.get("recording") else dict(recording)

    print(f"   в файле «{artist[:52]}» — подписи для него в карточке нет")

    return {}

async def cut_pieces(card: dict, source: Path, count: int, workspace: Path) -> list[dict]:
    """Нарезает и заливает куски одной карточки — до нужного числа.

    Считается общее количество, а не добавленное: повторный запуск добирает
    недостающее, а не наваливает сверху ещё столько же.
    """
    count -= len(card.get("roulette") or [])
    if count <= 0:
        return []

    total = duration_of(source)
    busy = taken_places(card)
    dice = random.Random()

    pieces = []
    gap = APART
    for attempt in range(TRIES * 2):
        if len(pieces) == count:
            break

        # первую половину попыток ищем с зазором, дальше — вплотную:
        # на короткой записи иначе не найдётся ничего
        if attempt == TRIES and not pieces:
            print("   зазор мешает, ищу вплотную")
            gap = 0.0

        start = round(dice.uniform(0, total), 1)
        if not fits(start, total, busy, gap):
            continue

        piece = workspace / f"{card['id']}-{start}.mp3"
        cut_fragment(source, piece, str(start), str(LENGTH))

        mean, peak, crossings = levels(piece)
        if crossings > NOISY:
            print(f"   {start:>7.1f}с — похоже на аплодисменты, ищу дальше")
            busy.append((start, LENGTH))
            continue

        if mean < QUIET_MEAN or not evens_out(mean, peak):
            print(f"   {start:>7.1f}с — тихое место ({mean:.1f} дБ), ищу дальше")
            busy.append((start, LENGTH))
            continue

        complaint = good_enough(piece)
        if complaint:
            print(f"   {start:>7.1f}с — {complaint}, ищу дальше")
            busy.append((start, LENGTH))
            continue

        # выравниваем, чтобы куски не прыгали по громкости от вопроса к вопросу
        gain = gain_for(mean, peak)
        if abs(gain) >= 1:
            cut_fragment(source, piece, str(start), str(LENGTH), gain=gain)

        file_id = await upload(piece, card.get("recording", {}).get("performer"))
        piece_entry = {
            "start": f"{start:.1f}",
            "duration": str(LENGTH),
            "source": source.name,
            "audio_file_id": file_id,
        }
        own = credit(card, source)
        if own:
            piece_entry["recording"] = own
        pieces.append(piece_entry)
        busy.append((start, LENGTH))
        print(f"   {start:>7.1f}с — взят (было {mean:.1f} дБ, поправка {gain:+.1f})")

    if len(pieces) < count:
        print(f"   нашлось только {len(pieces)} из {count}")

    return pieces

async def whoami() -> str:
    """Имя бота, от которого пойдёт заливка.

    С повторами: сеть до Телеграма отваливается, и обидно потерять всю нарезку
    на первом же приветствии, не начав резать.
    """
    for attempt in range(1, 5):
        try:
            async with Bot(os.environ["BOT_TOKEN"]) as bot:
                return (await bot.get_me()).username
        except TelegramError:
            if attempt == 4:
                raise
            await asyncio.sleep(2 ** attempt)

def survey(library: dict, files: list) -> int:
    """Показывает, где чего не хватает, ничего не трогая.

    Нужна потому, что сопоставление по именам файлов однажды молча подсунуло
    Вивальди вместо Бетховена: проверять его надо целиком и в любой момент,
    а не выборочно и не по логам.
    """
    from collections import defaultdict

    without_source, short, ready = [], [], 0
    used = defaultdict(set)
    nameless = []

    for card in library["playable"]:
        pieces = len(card.get("roulette") or [])
        source = find_audio(card["id"], files)

        for piece in card.get("roulette") or []:
            if piece.get("source"):
                used[piece["source"]].add(card["id"])
            else:
                nameless.append(card["id"])

        if not source:
            without_source.append((card["id"], pieces))
        elif pieces < 3:
            short.append((card["id"], pieces, source.name))
        else:
            ready += 1

    print(f"Карточек с записью: {len(library['playable'])}")
    print(f"  нарезаны полностью: {ready}")
    print(f"  нарезаны частично:  {len(short)}")
    print(f"  без исходника:      {len(without_source)}")

    if without_source:
        print("\nИсходник не найден — назовите файл через --source:")
        for card_id, pieces in without_source:
            print(f"  {card_id:34} кусков: {pieces}")

    if short:
        print("\nМожно добрать (запись коротка или места тихие):")
        for card_id, pieces, name in short:
            print(f"  {card_id:34} кусков: {pieces}   ← {name[:44]}")

    # Один файл на две карточки почти всегда значит ошибку сопоставления:
    # так вскрылось, что четыре вещи Рахманинова нарезаны из одной прелюдии
    shared = {name: ids for name, ids in used.items() if len(ids) > 1}
    if shared:
        print("\nОдин файл на несколько карточек — почти наверняка ошибка:")
        for name, ids in sorted(shared.items()):
            print(f"  {name[:64]}")
            for card_id in sorted(ids):
                print(f"      {card_id}")

    if nameless:
        print(f"\nБез записанного источника: {len(set(nameless))} — проверить нечем")
        for card_id in sorted(set(nameless)):
            print(f"  {card_id}")

    return 0

async def build(args: argparse.Namespace) -> int:
    if not args.check:
        print(f"Заливаю от имени @{await whoami()}\n")

    directory = content.cards_directory()
    library = content.load_library()

    if args.check:
        files = []
        for folder in args.audio:
            files += [(words(path.stem), path) for path in sound_files(folder.expanduser())]

        return survey(library, files)

    if args.card:
        chosen = [card for card in library["playable"] if card["id"] == args.card]
        if not chosen:
            print(f"Карточки {args.card} нет или у неё нет записи")
            return 1
    elif args.all:
        chosen = library["playable"]
    else:
        print("Назовите карточку через --card или возьмите все через --all")
        return 1

    files = []
    for folder in args.audio:
        folder = folder.expanduser()
        if not folder.is_dir():
            print(f"Нет такой папки: {folder}")
            return 1
        files += [(words(path.stem), path) for path in sound_files(folder)]

    with tempfile.TemporaryDirectory() as workspace:
        for card in chosen:
            # лицензии с NoDerivatives запрещают производные: такую запись
            # заливают целиком и не режут ни на что
            if any(fragment.get("as_is") for fragment in card.get("fragments") or []):
                print(f"{card['id']}: залито как есть, резать нельзя — пропускаю")
                continue

            source = args.source.expanduser() if args.source else find_audio(card["id"], files)
            if not source or not source.exists():
                print(f"{card['id']}: исходник не найден — пропускаю")
                continue

            print(f"{card['id']} ← {source.name}")
            pieces = await cut_pieces(card, source, args.count, Path(workspace))
            if not pieces:
                continue

            path = directory / f"{card['id']}.json"
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored["roulette"] = (stored.get("roulette") or []) + pieces
            path.write_text(
                json.dumps(stored, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

    return 0

def main() -> int:
    load_dotenv(os.getenv("ENV_FILE", ".env"))

    return asyncio.run(build(parse_args()))

if __name__ == "__main__":
    sys.exit(main())
