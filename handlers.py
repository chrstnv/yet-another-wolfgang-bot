import random

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from data import QUIZ_QUESTION, SECTION_REPLIES
from keyboards import MENU_KEYBOARD

async def random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(option, callback_data=str(i))]
        for i, option in enumerate(QUIZ_QUESTION["options"])
    ])
    await update.message.reply_text(QUIZ_QUESTION["question"], reply_markup=keyboard)

async def quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chosen = int(query.data)
    correct = QUIZ_QUESTION["correct_index"]

    if chosen == correct:
        result = "✅ Верно!"
    else:
        result = "❌ Неправильно."

    fact = random.choice(QUIZ_QUESTION["facts"])
    await query.edit_message_text(
        f"{result}\n\nЭто {QUIZ_QUESTION['options'][correct]}.\n"
        f"Фрагмент: «{QUIZ_QUESTION['fragment']}».\n\n"
        f"💡 {fact}"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello! I'm your bot. How can I help you today?", reply_markup=MENU_KEYBOARD)

async def section_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(SECTION_REPLIES[update.message.text])