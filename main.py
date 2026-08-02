import os

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

from handlers import start, section_placeholder, random_quiz, quiz_answer
from data import SECTION_REPLIES
from keyboards import RANDOM_QUIZ_LABEL

load_dotenv() 

def main() -> None:
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    app.add_handler(CommandHandler("start", start))
    
    app.add_handler(MessageHandler(filters.Text(list(SECTION_REPLIES)), section_placeholder))

    app.add_handler(MessageHandler(filters.Text([RANDOM_QUIZ_LABEL]), random_quiz))
    app.add_handler(CallbackQueryHandler(quiz_answer))

    app.run_polling()

if __name__ == "__main__":
    main()