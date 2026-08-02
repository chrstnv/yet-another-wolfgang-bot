import os

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv() 

RANDOM_QUIZ_LABEL = "🎲 Случайный квиз"
ALL_QUIZZES_LABEL = "🎯 Все квизы"
COLLECTION_LABEL = "❤️ Коллекция"
PROGRESS_LABEL = "📈 Прогресс"
SETTINGS_LABEL = "⚙️ Настройки"

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [RANDOM_QUIZ_LABEL, ALL_QUIZZES_LABEL],
        [COLLECTION_LABEL, PROGRESS_LABEL],
        [SETTINGS_LABEL],
    ],
    resize_keyboard=True,
)

SECTION_REPLIES = {
    RANDOM_QUIZ_LABEL: "🎲 Случайный квиз скоро появится!",
    ALL_QUIZZES_LABEL: "🎯 Все квизы скоро появятся!",
    COLLECTION_LABEL: "❤️ Коллекция скоро появится!",
    PROGRESS_LABEL: "📈 Прогресс скоро появится!",
    SETTINGS_LABEL: "⚙️ Настройки скоро появятся!",
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello! I'm your bot. How can I help you today?", reply_markup=MENU_KEYBOARD)

async def section_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(SECTION_REPLIES[update.message.text])

def main() -> None:
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    app.add_handler(CommandHandler("start", start))
    
    app.add_handler(MessageHandler(filters.Text(list(SECTION_REPLIES)), section_placeholder))

    app.run_polling()

if __name__ == "__main__":
    main()