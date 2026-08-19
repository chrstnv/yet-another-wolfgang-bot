"""Собирает набор кастомных эмодзи бота и печатает их идентификаторы.

    python -m tools.add_emoji --name mozart --title "Вольфганг" \
        --emoji 🎹 --image ~/Desktop/happy.webp \
        --emoji 🎻 --image ~/Desktop/grumpy.webp

Существующий набор дополняется, а не создаётся заново, — и это главное, ради
чего стоит звать этот инструмент, а не собирать набор руками. При пересборке
Телеграм выдаёт новые идентификаторы, и все, что уже стоят в текстах бота,
разом перестают работать; дописанному эмодзи выдаётся один новый.

Набор создаётся от имени бота, поэтому его имя обязано кончаться на
`_by_<имя_бота>` — суффикс дописывается сам. Владельцу бота нужен Telegram
Premium: без него кастомные эмодзи не отправляются.

Идентификаторы из вывода вставляются в тексты тегом
`<tg-emoji emoji-id="…">🎹</tg-emoji>`. Эмодзи внутри тега — запасной, его
увидят там, где кастомный не отрисуется.

Картинки нужны готовые: ровно 100×100, webp или png. Обрезать лицо всё равно
приходится глазами, а не программой, — вот рецепт, которым резался Моцарт:

    from PIL import Image, ImageEnhance
    face = Image.open("портрет.jpg").convert("RGBA").crop((470, 360, 900, 790))
    face = face.resize((100, 100), Image.LANCZOS)
    face = ImageEnhance.Contrast(face).enhance(1.5)
    face = ImageEnhance.Color(face).enhance(1.3)
    face = ImageEnhance.Sharpness(face).enhance(2.0)
    face.save("лицо.webp", "WEBP", lossless=True)

Контраст и резкость подняты не для красоты: в строке значок занимает около
двадцати пикселей, и на этом размере выживают только крупные пятна.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Bot, InputSticker
from telegram.error import BadRequest, TelegramError

SIZE = 100

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Набор кастомных эмодзи для бота")
    parser.add_argument("--name", required=True, help="короткое имя набора, без суффикса")
    parser.add_argument("--title", required=True, help="название набора, видно в Телеграме")
    parser.add_argument("--image", action="append", required=True, type=Path,
                        help="картинка 100×100; можно повторять")
    parser.add_argument("--emoji", action="append", required=True,
                        help="запасной эмодзи для каждой картинки, в том же порядке")

    return parser.parse_args()

async def exists(bot: Bot, name: str) -> bool:
    """Есть ли уже такой набор.

    Отсутствие набора Телеграм сообщает тем же BadRequest, что и опечатку
    в имени, — но опечатка тут невозможна: имя собрано из аргумента и
    имени бота.
    """
    try:
        await bot.get_sticker_set(name)
    except BadRequest:
        return False

    return True

async def build(args: argparse.Namespace) -> int:
    token, owner = os.getenv("BOT_TOKEN"), os.getenv("ADMIN_CHAT_ID")
    if not token or not owner:
        print("Нужны BOT_TOKEN и ADMIN_CHAT_ID в .env")
        return 1

    if len(args.image) != len(args.emoji):
        print(f"Картинок {len(args.image)}, а запасных эмодзи {len(args.emoji)} — должно совпадать")
        return 1

    bot = Bot(token)
    name = f"{args.name}_by_{(await bot.get_me()).username}"

    stickers = []
    for path, emoji in zip(args.image, args.emoji):
        path = path.expanduser()
        if not path.exists():
            print(f"Не найдено: {path}")
            return 1
        stickers.append(InputSticker(
            sticker=path.read_bytes(), emoji_list=[emoji], format="static",
        ))

    try:
        if await exists(bot, name):
            for sticker in stickers:
                await bot.add_sticker_to_set(user_id=int(owner), name=name, sticker=sticker)
            print(f"В набор {name} добавлено: {len(stickers)}.\n")
        else:
            await bot.create_new_sticker_set(
                user_id=int(owner), name=name, title=args.title,
                stickers=stickers, sticker_type="custom_emoji",
            )
            print(f"Набор {name} создан.\n")
    except TelegramError as error:
        print(f"Не получилось: {error}")
        return 1

    for sticker in (await bot.get_sticker_set(name)).stickers:
        print(f'  {sticker.emoji}  <tg-emoji emoji-id="{sticker.custom_emoji_id}">{sticker.emoji}</tg-emoji>')

    return 0

def main() -> int:
    load_dotenv()

    return asyncio.run(build(parse_args()))

if __name__ == "__main__":
    sys.exit(main())
