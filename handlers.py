import random

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from data import CARDS, CARDS_BY_ID, SECTION_REPLIES
from keyboards import MENU_KEYBOARD

async def random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    card = random.choice(CARDS)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(option, callback_data=f"{card['id']}:{i}")]
        for i, option in enumerate(card["options"])
    ])
    await update.message.reply_audio(
        audio=card["audio_file_id"],
        caption=card["question"],
        reply_markup=keyboard,
        title="🎵 Фрагмент",
        performer=card["recording"]["performer"],
    )

async def quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    card_id, chosen = query.data.split(":")
    card = CARDS_BY_ID[card_id]
    correct = card["correct_index"]

    if int(chosen) == correct:
        result = "✅ Верно!"
    else:
        result = "❌ Неправильно."

    fact = random.choice(card["facts"])

    recording = card["recording"]

    await query.edit_message_caption(
        f"{result}\n\nЭто {card['options'][correct]}.\n"
        f"Фрагмент: «{card['fragment']}».\n\n"
        f"💡 {fact}\n\n"
        f"🎧 Запись: {recording['performer']} — {recording['source']}"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello! I'm your bot. How can I help you today?", reply_markup=MENU_KEYBOARD)

async def section_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(SECTION_REPLIES[update.message.text])

async def audio_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"file_id: {update.message.audio.file_id}")