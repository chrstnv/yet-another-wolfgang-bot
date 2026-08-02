import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv() 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello! I'm your bot. How can I help you today?")

def main() -> None:
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    app.add_handler(CommandHandler("start", start))

    app.run_polling()

if __name__ == "__main__":
    main()