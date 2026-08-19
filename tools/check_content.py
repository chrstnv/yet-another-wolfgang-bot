"""Проверяет библиотеку карточек, не запуская бота.

    python -m tools.check_content            проверить
    python -m tools.check_content --record   принять текущие числа за норму

Изъяны не чинятся одним днём: лицензий не записано полторы сотни, засечек — под
сотню. Поэтому проверка не требует нуля, а держит храповик: числа записаны в
tools/flaws_baseline.json, и падение наступает, когда какое-то из них выросло.
Долг зафиксирован, новый копиться не может.
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

import content

# сколько примеров показывать на каждый изъян: список нужен для правки,
# а не для чтения целиком
EXAMPLES = 5

BASELINE = Path(__file__).with_name("flaws_baseline.json")

def read_baseline() -> dict:
    if not BASELINE.exists():
        return {}

    return json.loads(BASELINE.read_text(encoding="utf-8"))

def write_baseline(counts: dict) -> None:
    BASELINE.write_text(
        json.dumps(counts, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

def grown(counts: dict, baseline: dict) -> list[str]:
    """Изъяны, которых стало больше, чем записано в эталоне."""
    return [
        f"{name}: было {baseline[name]}, стало {count}"
        for name, count in sorted(counts.items())
        if name in baseline and count > baseline[name]
    ]

def main(record: bool = False) -> int:
    load_dotenv()

    try:
        directory = content.cards_directory()
        cards = sorted(
            (content.read_card(path) for path in directory.glob("*.json")),
            key=lambda card: card["id"],
        )
    except (RuntimeError, ValueError) as error:
        print(f"Не удалось прочитать библиотеку: {error}")
        return 1

    problems = content.find_problems(cards)
    playable = [card for card in cards if card.get("fragments")]
    silent = [card for card in cards if not card.get("fragments")]

    print(f"Карточек: {len(cards)}")
    print(f"  с записью: {len(playable)}")
    print(f"  без записи: {len(silent)}")

    if silent:
        print("\nЖдут записи:")
        for card in silent:
            print(f"  {card['id']:<32} {card.get('title', '')}")

    if problems:
        print(f"\nПроблемы ({len(problems)}):")
        for problem in problems:
            print(f"  {problem}")

    flaws = content.find_flaws(cards)
    counts = {name: len(items) for name, items in flaws.items()}

    if any(flaws.values()):
        print("\nИзъяны:")
        for name, items in flaws.items():
            if not items:
                continue
            print(f"\n  {name} — {len(items)}")
            for item in items[:EXAMPLES]:
                print(f"    {item}")
            if len(items) > EXAMPLES:
                print(f"    … и ещё {len(items) - EXAMPLES}")

    if record:
        write_baseline(counts)
        print("\nЭталон записан.")
        return 1 if problems else 0

    regressions = grown(counts, read_baseline())
    if regressions:
        print("\nИзъянов стало больше:")
        for line in regressions:
            print(f"  {line}")
        print("\nЛибо поправьте, либо примите новое число: --record")

    if problems or regressions:
        return 1

    print("\nПоломок нет, новых изъянов нет.")
    return 0

if __name__ == "__main__":
    sys.exit(main(record="--record" in sys.argv))
