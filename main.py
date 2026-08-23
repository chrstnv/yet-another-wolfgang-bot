import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, MessageHandler,
    PersistenceInput, PicklePersistence, filters,
)

from core import content, storage
from bot.handlers import (
    on_error, start, random_quiz, quiz_answer, audio_file_id, next_question,
    restart_quiz, show_progress, effect_id, chat_id, review_quiz,
    streak_quiz, reveal_options, settings_screen, toggle_hide_options, close_screen,
    ask_reset, confirm_reset, cancel_reset,
    show_favourites, favourites_page, toggle_favourite, drop_favourite,
    play_favourite,
)
from bot.keyboards import (
    RANDOM_QUIZ_LABEL, PROGRESS_LABEL, REVIEW_LABEL, SETTINGS_LABEL,
    STREAK_LABEL, FAVOURITES_LABEL,
)

load_dotenv(os.getenv("ENV_FILE", ".env"))

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
# httpx печатает строчку на каждый запрос к Телеграму, включая опрос раз в секунду
logging.getLogger("httpx").setLevel(logging.WARNING)

# как часто бот отмечается, что жив, и через сколько отметка считается протухшей
# (сверяется с healthcheck в compose.yaml)
HEARTBEAT_PERIOD = 30

async def heartbeat(app: Application) -> None:
    """Отмечает в файле, что опрос работает, и выходит, если он остановился.

    Процесс может быть жив, а обновления не приходить: политика перезапуска
    Docker смотрит только на код возврата и такого не замечает. Поэтому опрос
    проверяется изнутри — и если он умер, бот выходит сам, чтобы его подняли
    заново. На случай, когда встал весь цикл событий и эта задача тоже не
    работает, отметка перестаёт обновляться и healthcheck красит контейнер
    больным; поднимает его тогда сторож на хосте.
    """
    path = Path(os.environ["HEARTBEAT_PATH"])

    while True:
        # отметка ставится первой, а проверка идёт после паузы: задача заводится
        # до старта опроса, и проверка на первом же круге увидела бы его стоящим
        path.touch()
        await asyncio.sleep(HEARTBEAT_PERIOD)

        if app.updater is not None and not app.updater.running:
            logging.error("Опрос остановился — выходим, чтобы перезапуститься")
            app.stop_running()
            return

async def start_heartbeat(app: Application) -> None:
    if os.getenv("HEARTBEAT_PATH"):
        app.create_task(heartbeat(app))

def main() -> None:
    # квиз живёт в user_data, а он по умолчанию гибнет вместе с процессом:
    # после перезапуска у висящего вопроса переставали работать кнопки.
    # bot_data не сохраняем — там соединение с базой и библиотека,
    # их незачем и невозможно складывать в файл
    persistence = PicklePersistence(
        filepath=os.getenv("STATE_PATH", "state.pickle"),
        store_data=PersistenceInput(bot_data=False, chat_data=False, callback_data=False),
        # по умолчанию состояние сбрасывается на диск раз в минуту, и квиз,
        # начатый позже последней записи, перезапуск не переживал: кнопки под
        # вопросом оказывались от сессии, которой уже нет. Файл весит килобайты,
        # так что писать его каждую секунду ничего не стоит
        update_interval=1,
    )

    builder = (
        Application.builder()
        .token(os.getenv("BOT_TOKEN"))
        .persistence(persistence)
        .post_init(start_heartbeat)
        # здоровое соединение с Телеграмом открывается за доли секунды, так что
        # две — это уже приговор: обрываем и набираем заново. Короткий таймаут
        # позволяет сделать шесть заходов там, где раньше хватало на один, а весь
        # бюджет по-прежнему укладывается в те примерно пятнадцать секунд,
        # что Телеграм держит нажатие живым
        .connect_timeout(2)
        .read_timeout(10)
        .write_timeout(10)
        .pool_timeout(2)
        # загрузка аудио — единственное, что бывает по-настоящему долгим
        .media_write_timeout(60)
    )

    # там, где до api.telegram.org не дотянуться напрямую, бот ходит через
    # релей. Здесь это настройка, а не правка кода: переключение не должно
    # требовать новой выкладки
    relay = os.getenv("TELEGRAM_BASE_URL")
    if relay:
        builder = builder.base_url(f"{relay.rstrip('/')}/bot").base_file_url(f"{relay.rstrip('/')}/file/bot")

    # либо через прокси на самой машине — так проще всего пустить в обход
    # только трафик бота, не трогая маршруты: всё остальное (реестр образов,
    # входящий SSH для выкладки) продолжает ходить напрямую.
    # Опрос обновлений живёт в отдельном соединении, поэтому прокси задаётся дважды
    proxy = os.getenv("TELEGRAM_PROXY")
    if proxy:
        builder = builder.proxy(proxy).get_updates_proxy(proxy)

    app = builder.build()

    db = storage.connect(os.getenv("DB_PATH", "bot.db"))
    storage.init_schema(db)
    app.bot_data["db"] = db

    app.bot_data["library"] = content.load_library()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CommandHandler("chatid", chat_id))

    app.add_handler(MessageHandler(filters.Text([PROGRESS_LABEL]), show_progress))

    app.add_handler(MessageHandler(filters.Text([SETTINGS_LABEL]), settings_screen))

    app.add_handler(MessageHandler(filters.Text([FAVOURITES_LABEL]), show_favourites))

    app.add_handler(MessageHandler(filters.Text([STREAK_LABEL]), streak_quiz))

    app.add_handler(MessageHandler(filters.Text([REVIEW_LABEL]), review_quiz))

    app.add_handler(MessageHandler(filters.Text([RANDOM_QUIZ_LABEL]), random_quiz))

    app.add_handler(CallbackQueryHandler(quiz_answer, pattern=r"^answer:"))

    app.add_handler(CallbackQueryHandler(next_question, pattern=r"^next$"))

    app.add_handler(CallbackQueryHandler(restart_quiz, pattern=r"^restart$"))

    app.add_handler(CallbackQueryHandler(review_quiz, pattern=r"^review$"))

    app.add_handler(CallbackQueryHandler(streak_quiz, pattern=r"^streak$"))

    app.add_handler(CallbackQueryHandler(reveal_options, pattern=r"^reveal$"))

    app.add_handler(CallbackQueryHandler(toggle_hide_options, pattern=r"^toggle-hide$"))

    app.add_handler(CallbackQueryHandler(ask_reset, pattern=r"^reset$"))

    app.add_handler(CallbackQueryHandler(confirm_reset, pattern=r"^reset-yes$"))

    app.add_handler(CallbackQueryHandler(cancel_reset, pattern=r"^reset-no$"))

    app.add_handler(CallbackQueryHandler(toggle_favourite, pattern=r"^fav:"))

    app.add_handler(CallbackQueryHandler(favourites_page, pattern=r"^favs:"))

    app.add_handler(CallbackQueryHandler(play_favourite, pattern=r"^favplay:"))

    app.add_handler(CallbackQueryHandler(drop_favourite, pattern=r"^favdrop:"))

    app.add_handler(CallbackQueryHandler(close_screen, pattern=r"^close$"))

    app.add_handler(MessageHandler(filters.AUDIO, audio_file_id))

    app.add_handler(MessageHandler(filters.TEXT, effect_id))

    # без этого первая же неудачная попытка достучаться до Телеграма роняет
    # запуск: «Failed run number 0 of 0. Aborting». Сеть после пробуждения
    # ноутбука поднимается не мгновенно, и ждать её правильнее, чем падать.
    # Неверный токен под это исключение не попадает и по-прежнему прерывает старт
    app.add_error_handler(on_error)

    app.run_polling(bootstrap_retries=-1)

if __name__ == "__main__":
    main()
