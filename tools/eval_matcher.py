"""Меряет, как часто сопоставление файла с карточкой право, молчит и ошибается.

    python -m tools.eval_matcher

Разметка берётся из самой библиотеки: у каждого куска «наугад» записано имя
файла, из которого он вырезан, и все эти куски человек прослушал. Значит, для
таких карточек верный ответ известен, и точность можно посчитать, а не оценить
на глаз.

Отказ и ошибка считаются порознь: отказ стоит человеку минуты, а ошибка
попадает в библиотеку молча. Число ошибок и есть то, что мы держим на нуле.
"""

import argparse
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from core import content
from tools.audio_folders import audio_folders
from tools.dev_library import MATCH, find_audio, same_surname, sound_files, words

def candidates(card_id: str, files: list[tuple[set, Path]]) -> list[Path]:
    """Файлы, набравшие высший балл. Их и не смог различить find_audio.

    Отказ бывает двух разных сортов: подходящих файлов не нашлось вовсе или их
    нашлось несколько. Первое значит, что правила отбора слишком строги,
    второе — что различающего слова нет в самом названии карточки. Чинятся
    они по-разному, поэтому и считать их надо порознь.
    """
    wanted = words(card_id)
    numbers = {word for word in wanted if word.isdigit()}
    surname = card_id.split("-")[0]

    scored = []
    for name, path in files:
        if not same_surname(surname, name) or numbers - name:
            continue
        common = (wanted & name) - numbers
        weight = len(common) + (surname not in common)
        if weight >= MATCH:
            scored.append((weight, path))

    if not scored:
        return []

    best = max(weight for weight, _ in scored)

    return [path for weight, path in scored if weight == best]

def known_source(card: dict) -> str | None:
    """Имя файла, из которого нарезаны куски карточки.

    Карточку режут из одного файла, но правки накапливались, и куски могли
    остаться от разных. Такая карточка в разметку не годится: верный ответ
    у неё не один.
    """
    named = {piece["source"] for piece in card.get("roulette") or [] if piece.get("source")}

    return named.pop() if len(named) == 1 else None

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", action="append",
                        help="папка с исходниками вместо AUDIO_PATH, можно повторять")

    return parser.parse_args()

def main() -> int:
    load_dotenv()
    args = parse_args()

    files = []
    for folder in audio_folders(args.audio):
        files += sound_files(folder)
    named = [(words(path.name), path) for path in files]

    library = content.load_library()
    marked = {
        card["id"]: source
        for card in library["cards"]
        if (source := known_source(card))
    }

    tally = Counter()
    refused = []
    mistakes = []
    for card_id, source in sorted(marked.items()):
        found = find_audio(card_id, named)
        if found is not None:
            tally["верно" if found.name == source else "ошибка"] += 1
            if found.name != source:
                mistakes.append((card_id, found.name, source))
            continue

        tied = candidates(card_id, named)
        tally["ничья" if tied else "не нашёл"] += 1
        # ничья, в которой верный файл среди кандидатов, стоит человеку одного
        # взгляда; всё остальное — поисков по папке
        if tied and any(path.name == source for path in tied):
            tally["верный среди кандидатов"] += 1
        refused.append((card_id, tied, source))

    total = tally["верно"] + tally["ошибка"] + tally["ничья"] + tally["не нашёл"]
    print(f"Карточек с известным ответом: {total}, файлов в папках: {len(files)}")
    for outcome in ("верно", "ошибка", "ничья", "не нашёл"):
        share = tally[outcome] / total * 100 if total else 0
        print(f"  {outcome:9} {tally[outcome]:4}  {share:5.1f}%")
    print(f"  из ничьих верный файл среди кандидатов: {tally['верный среди кандидатов']}")

    for card_id, found, source in mistakes:
        print(f"\nОШИБКА {card_id}\n  выбрано: {found}\n  верно:   {source}")

    for card_id, tied, source in refused:
        names = ", ".join(path.name for path in tied) or "ни одного кандидата"
        print(f"\n{card_id}\n  кандидаты: {names}\n  верно:     {source}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
