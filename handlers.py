import random

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from telegram.ext import ContextTypes

import progress
import quiz
import storage
from data import QUESTION, SECTION_REPLIES
from keyboards import MENU_KEYBOARD

# Эффект «конфетти» 🎉. Идентификаторы стандартных эффектов одинаковы у всех,
# получить их можно хендлером effect_id: отправить боту сообщение с эффектом.
CONFETTI_EFFECT = "5046509860389126442"

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

    session = quiz.start_session(context.bot_data["library"]["playable"])
    session["message_id"] = None
    context.user_data["quiz"] = session

    await send_question(update, context)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = context.user_data["quiz"]
    library = context.bot_data["library"]
    card = library["by_id"][quiz.current_card_id(session)]

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(option["title"], callback_data=f"answer:{option['id']}")]
        for option in quiz.build_options(card, library["cards"])
    ])

    message = await context.bot.send_audio(
        chat_id=update.effective_chat.id,
        audio=card["audio_file_id"],
        caption=QUESTION,
        reply_markup=keyboard,
        title="🎵 Фрагмент",
        performer=card["recording"]["performer"],
    )
    session["message_id"] = message.message_id

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    session = context.user_data.get("quiz")
    if not session or query.message.message_id != session["message_id"]:
        return

    await delete_screen(update, context, session["message_id"])
    session["message_id"] = None

    quiz.advance(session)

    if quiz.is_finished(session):
        await finish_quiz(update, context)
    else:
        await send_question(update, context)

async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = context.user_data["quiz"]

    if session["message_id"]:
        await delete_screen(update, context, session["message_id"])

    correct_count = quiz.score(session)
    total = len(session["queue"])

    answers_list = [
        f"{title} — {'✅ Верно!' if is_correct else '❌ Неправильно.'}"
        for title, is_correct in quiz.breakdown(session, context.bot_data["library"]["by_id"])
    ]

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"{progress.verdict(correct_count, total)}\n\n"
            f"{"\n".join(answers_list)}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Ещё квиз", callback_data="restart")]
        ]),
        message_effect_id=CONFETTI_EFFECT if correct_count == total else None,
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

    session = context.user_data.get("quiz")
    if not session or quiz.is_answered(session):
        return

    _, chosen_id = query.data.split(":")
    card_id = quiz.current_card_id(session)
    card = context.bot_data["library"]["by_id"][card_id]

    quiz.record_answer(session, card_id, chosen_id)
    storage.save_answer(context.bot_data["db"], update.effective_user.id, card_id, chosen_id)

    if chosen_id == card_id:
        result = "✅ Верно!"
    else:
        result = "❌ Неправильно."

    fact = random.choice(card["facts"])

    recording = card["recording"]

    await query.edit_message_caption(
        caption=(
            f"{result}\n\nЭто {card['title']}.\n"
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

async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    library = context.bot_data["library"]
    answers = storage.get_answers(context.bot_data["db"], update.effective_user.id)
    stats = progress.summary(answers, library["by_id"])

    if not stats["total"]:
        await update.message.reply_text(
            "📈 Пока пусто. Пройдите первый квиз — и здесь появится статистика."
        )
        return

    lines = [
        "📈 Ваш прогресс",
        "",
        f"Ответов: {stats['total']}",
        f"Верно: {stats['correct']} — это {stats['accuracy']}%",
        f"Произведений услышано: {stats['cards_seen']} из {len(library['playable'])}",
    ]

    missed = progress.weakest(answers, library["by_id"])
    if missed:
        lines.append("")
        lines.append("Пока даются хуже всего:")
        for card in missed:
            title = library["by_id"][card["card_id"]]["title"]
            lines.append(f"• {title} — {card['correct']} из {card['attempts']}")

    await update.message.reply_text("\n".join(lines))

async def audio_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"file_id: {update.message.audio.file_id}")

async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")

async def effect_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.effect_id:
        await update.message.reply_text(f"effect_id: {update.message.effect_id}")