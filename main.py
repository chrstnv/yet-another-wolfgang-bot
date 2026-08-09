import os

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

import content
import storage
from handlers import (
    start, section_placeholder, random_quiz, quiz_answer, audio_file_id, next_question,
    restart_quiz, show_progress, effect_id, chat_id, review_quiz, show_quiz_modes,
    streak_quiz, reveal_options, settings_screen, toggle_hide_options,
)
from data import SECTION_REPLIES
from keyboards import RANDOM_QUIZ_LABEL, PROGRESS_LABEL, ALL_QUIZZES_LABEL, SETTINGS_LABEL

load_dotenv()

def main() -> None:
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    db = storage.connect(os.getenv("DB_PATH", "bot.db"))
    storage.init_schema(db)
    app.bot_data["db"] = db

    app.bot_data["library"] = content.load_library()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CommandHandler("chatid", chat_id))

    app.add_handler(MessageHandler(filters.Text(list(SECTION_REPLIES)), section_placeholder))

    app.add_handler(MessageHandler(filters.Text([PROGRESS_LABEL]), show_progress))

    app.add_handler(MessageHandler(filters.Text([SETTINGS_LABEL]), settings_screen))

    app.add_handler(MessageHandler(filters.Text([ALL_QUIZZES_LABEL]), show_quiz_modes))

    app.add_handler(MessageHandler(filters.Text([RANDOM_QUIZ_LABEL]), random_quiz))

    app.add_handler(CallbackQueryHandler(quiz_answer, pattern=r"^answer:"))
    
    app.add_handler(CallbackQueryHandler(next_question, pattern=r"^next$"))

    app.add_handler(CallbackQueryHandler(restart_quiz, pattern=r"^restart$"))

    app.add_handler(CallbackQueryHandler(review_quiz, pattern=r"^review$"))

    app.add_handler(CallbackQueryHandler(streak_quiz, pattern=r"^streak$"))

    app.add_handler(CallbackQueryHandler(reveal_options, pattern=r"^reveal$"))

    app.add_handler(CallbackQueryHandler(toggle_hide_options, pattern=r"^toggle-hide$"))

    app.add_handler(MessageHandler(filters.AUDIO, audio_file_id))

    app.add_handler(MessageHandler(filters.TEXT, effect_id))

    app.run_polling()

if __name__ == "__main__":
    main()