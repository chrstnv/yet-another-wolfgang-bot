import random

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from data import CARDS, CARDS_BY_ID, QUESTION, SECTION_REPLIES
from keyboards import MENU_KEYBOARD

async def delete_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=message_id,
        )
    except TelegramError:
        pass

async def random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    previous = context.user_data.get("quiz")
    if previous and previous["message_id"]:
        await delete_screen(update, context, previous["message_id"])

    context.user_data["quiz"] = {
        "queue": [card["id"] for card in random.sample(CARDS, k=min(5, len(CARDS)))],
        "position": 0,
        "answers": [],
        "message_id": None,
    }

    await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    quiz = context.user_data["quiz"]
    card = CARDS_BY_ID[quiz["queue"][quiz["position"]]]

    options = list(enumerate(card["options"]))
    random.shuffle(options)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(option, callback_data=f"answer:{card['id']}:{i}")]
        for i, option in options
    ])

    message = await context.bot.send_audio(
        chat_id=update.effective_chat.id,
        audio=card["audio_file_id"],
        caption=QUESTION,
        reply_markup=keyboard,
        title="🎵 Фрагмент",
        performer=card["recording"]["performer"],
    )
    quiz["message_id"] = message.message_id

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    quiz = context.user_data["quiz"]

    if quiz["message_id"]:
        await delete_screen(update, context, quiz["message_id"])
        quiz["message_id"] = None

    quiz["position"] += 1

    if quiz["position"] < len(quiz["queue"]):
        await send_question(update, context)
    else:
        await finish_quiz(update, context)

async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    quiz = context.user_data["quiz"]

    if quiz["message_id"]:
        await delete_screen(update, context, quiz["message_id"])

    score = sum(1 for answer in quiz["answers"] if answer["chosen"] == answer["correct"])
    total = len(quiz["queue"])

    answers_list = [
        f"{CARDS_BY_ID[answer['card_id']]['options'][answer['correct']]} — {'✅ Верно!' if answer['chosen'] == answer['correct'] else '❌ Неправильно.'}"
        for answer in quiz["answers"]
    ]

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"🎉 Поздравляем! Вы успешно прошли тест! Вы ответили на {score} из {total} вопросов.\n\n"
            f"{"\n".join(answers_list)}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Ещё квиз", callback_data="restart")]
        ]),
    )

    context.user_data.pop("quiz")

async def restart_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)

    await random_quiz(update, context)

async def quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    _, card_id, chosen = query.data.split(":") 
    card = CARDS_BY_ID[card_id]
    correct = card["correct_index"]

    if int(chosen) == correct:
        result = "✅ Верно!"
    else:
        result = "❌ Неправильно."
        
    quiz = context.user_data["quiz"]
    quiz["answers"].append({"card_id": card_id, "chosen": int(chosen), "correct": correct})

    fact = random.choice(card["facts"])

    recording = card["recording"]

    await query.edit_message_caption(
        caption=(
            f"{result}\n\nЭто {card['options'][correct]}.\n"
            f"Фрагмент: «{card['fragment']}».\n\n"
            f"💡 {fact}\n\n"
            f"🎧 Запись: {recording['performer']} — {recording['source']}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Дальше →", callback_data="next")]
        ]),
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Hello! I'm your bot. How can I help you today?", reply_markup=MENU_KEYBOARD)

async def section_placeholder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(SECTION_REPLIES[update.message.text])

async def audio_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"file_id: {update.message.audio.file_id}")