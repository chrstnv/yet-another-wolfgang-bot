import os

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from handlers import start, section_placeholder, random_quiz, quiz_answer, audio_file_id, next_question, restart_quiz
from data import SECTION_REPLIES
from keyboards import RANDOM_QUIZ_LABEL

load_dotenv() 

def main() -> None:
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    app.add_handler(CommandHandler("start", start))
    
    app.add_handler(MessageHandler(filters.Text(list(SECTION_REPLIES)), section_placeholder))

    app.add_handler(MessageHandler(filters.Text([RANDOM_QUIZ_LABEL]), random_quiz))

    app.add_handler(CallbackQueryHandler(quiz_answer, pattern=r"^answer:"))
    
    app.add_handler(CallbackQueryHandler(next_question, pattern=r"^next$"))

    app.add_handler(CallbackQueryHandler(restart_quiz, pattern=r"^restart$"))

    app.add_handler(MessageHandler(filters.AUDIO, audio_file_id))

    app.run_polling()

if __name__ == "__main__":
    main()