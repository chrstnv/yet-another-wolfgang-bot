"""Проверяет библиотеку карточек, не запуская бота.

    python -m tools.check_content
"""

import sys

from dotenv import load_dotenv

import content

# сколько примеров показывать на каждый изъян: список нужен для правки,
# а не для чтения целиком
EXAMPLES = 5

def main() -> int:
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

    # изъяны не мешают боту работать, поэтому показываются всегда и на код
    # возврата не влияют: это список для правки, а не отказ собирать библиотеку
    flaws = content.find_flaws(cards)
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

    if problems:
        return 1

    print("\nПоломок нет.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
