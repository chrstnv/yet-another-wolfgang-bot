import logging
import os

from dotenv import load_dotenv
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, MessageHandler,
    PersistenceInput, PicklePersistence, filters,
)

import content
import storage
from handlers import (
    on_error, start, random_quiz, quiz_answer, audio_file_id, next_question,
    restart_quiz, show_progress, effect_id, chat_id, review_quiz,
    streak_quiz, reveal_options, settings_screen, toggle_hide_options, close_screen,
)
from keyboards import RANDOM_QUIZ_LABEL, PROGRESS_LABEL, REVIEW_LABEL, SETTINGS_LABEL, STREAK_LABEL

load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
# httpx печатает строчку на каждый запрос к Телеграму, включая опрос раз в секунду
logging.getLogger("httpx").setLevel(logging.WARNING)

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

    app = (
        Application.builder()
        .token(os.getenv("BOT_TOKEN"))
        .persistence(persistence)
        # соединение либо устанавливается за пару секунд, либо не установится:
        # ждать его дольше бессмысленно, дешевле оборвать и попробовать заново.
        # Весь бюджет попыток должен уложиться в те примерно пятнадцать секунд,
        # что Телеграм держит нажатие живым, — дальше индикатор гаснет сам
        .connect_timeout(5)
        .read_timeout(15)
        .write_timeout(15)
        .pool_timeout(3)
        # загрузка аудио — единственное, что бывает по-настоящему долгим
        .media_write_timeout(60)
        .build()
    )

    db = storage.connect(os.getenv("DB_PATH", "bot.db"))
    storage.init_schema(db)
    app.bot_data["db"] = db

    app.bot_data["library"] = content.load_library()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CommandHandler("chatid", chat_id))

    app.add_handler(MessageHandler(filters.Text([PROGRESS_LABEL]), show_progress))

    app.add_handler(MessageHandler(filters.Text([SETTINGS_LABEL]), settings_screen))

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
