import random

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from telegram.ext import ContextTypes

import progress
import quiz
import storage
from data import (
    GREETING, REVEAL_ANSWERS, SETTINGS, SETTINGS_OFF,
    SETTINGS_ON, SETTINGS_TOAST, STREAK_START,
)
from keyboards import MENU_KEYBOARD

# Идентификаторы стандартных эффектов одинаковы у всех, получить их можно
# хендлером effect_id: отправить боту сообщение с эффектом.
# Конфетти достаётся безошибочному квизу, огонёк — рекорду серии:
# достижения разные, и ощущаться должны по-разному.
CONFETTI_EFFECT = "5046509860389126442"
FIRE_EFFECT = "5104841245755180586"

async def remove_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=message_id,
        )
    except TelegramError:
        pass

async def delete_screen(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    await remove_message(update, context, message_id)
    storage.forget_sent_audio(context.bot_data["db"], update.effective_user.id, message_id)

async def dismiss_tap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Убирает след нажатия: у кнопки меню — само сообщение, у кнопки под
    сообщением — клавиатуру. Ответ бота говорит сам за себя, а нажатое
    только засоряет переписку.
    """
    if update.message:
        await remove_message(update, context, update.message.message_id)
        return

    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_reply_markup(reply_markup=None)

async def clear_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Убирает из чата все аудиосообщения, что бот успел прислать.

    Аудио в чате складывается в плейлист: стоит удалить играющее сообщение,
    и клиент перескакивает на соседнее. Если от брошенной сессии остались
    фрагменты, новый квиз начинается с чужой музыки.

    Список берётся из базы, а не из памяти: сессию бросают и после
    перезапуска бота, а сообщения в чате остаются.
    """
    db = context.bot_data["db"]
    user_id = update.effective_user.id

    for message_id in storage.sent_audio(db, user_id):
        await delete_screen(update, context, message_id)

    # что не удалилось, то старше двух суток и уже неудаляемо: держать не за чем
    storage.forget_sent_audio(db, user_id)

def remember_seen(update: Update, context: ContextTypes.DEFAULT_TYPE, session: dict) -> None:
    answers = storage.get_answers(context.bot_data["db"], update.effective_user.id)
    session["seen"] = {answer["card_id"] for answer in answers}

async def random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await remove_message(update, context, update.message.message_id)

    await clear_audio(update, context)

    session = quiz.start_session(context.bot_data["library"]["playable"])
    session["message_id"] = None
    remember_seen(update, context, session)
    context.user_data["quiz"] = session

    await send_question(update, context)

def options_keyboard(option_ids: list[str], by_id: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(by_id[option_id]["title"], callback_data=f"answer:{option_id}")]
        for option_id in option_ids
    ])

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = context.user_data["quiz"]
    library = context.bot_data["library"]
    card = library["by_id"][quiz.current_card_id(session)]
    fragment = quiz.pick_fragment(card)
    session["fragment"] = fragment["name"]
    session["recording"] = quiz.recording_of(card, fragment)

    # варианты выбираются один раз: если открывать их кнопкой, набор должен
    # остаться тем же, а не перетасоваться заново
    session["options"] = [option["id"] for option in quiz.build_options(card, library["cards"])]

    hidden = storage.hide_options(context.bot_data["db"], update.effective_user.id)
    keyboard = (
        InlineKeyboardMarkup([[InlineKeyboardButton(REVEAL_ANSWERS, callback_data="reveal")]])
        if hidden
        else options_keyboard(session["options"], library["by_id"])
    )

    message = await context.bot.send_audio(
        chat_id=update.effective_chat.id,
        audio=fragment["audio_file_id"],
        caption=progress.question_caption(session),
        reply_markup=keyboard,
        title="🎵 Фрагмент",
        performer=quiz.recording_of(card, fragment)["performer"],
    )
    session["message_id"] = message.message_id
    storage.save_sent_audio(
        context.bot_data["db"], update.effective_user.id, message.message_id
    )

async def reveal_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    session = context.user_data.get("quiz")
    if not session or query.message.message_id != session["message_id"]:
        return

    await query.edit_message_reply_markup(
        reply_markup=options_keyboard(session["options"], context.bot_data["library"]["by_id"])
    )

def settings_view(hidden: bool) -> tuple[str, InlineKeyboardMarkup]:
    return (
        SETTINGS.format(state=SETTINGS_ON if hidden else SETTINGS_OFF),
        InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "Выключить" if hidden else "Включить", callback_data="toggle-hide"
            )]
        ]),
    )

async def settings_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await remove_message(update, context, update.message.message_id)

    hidden = storage.hide_options(context.bot_data["db"], update.effective_user.id)
    text, keyboard = settings_view(hidden)

    await update.message.reply_text(text, reply_markup=keyboard)

async def toggle_hide_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    db = context.bot_data["db"]
    user_id = update.effective_user.id

    hidden = not storage.hide_options(db, user_id)
    storage.set_hide_options(db, user_id, hidden)

    # всплывающая подсказка: смена слова в тексте сама по себе незаметна
    await query.answer(SETTINGS_TOAST[hidden])

    text, keyboard = settings_view(hidden)
    await query.edit_message_text(text, reply_markup=keyboard)

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    session = context.user_data.get("quiz")
    if not session or query.message.message_id != session["message_id"]:
        return

    await delete_screen(update, context, session["message_id"])
    session["message_id"] = None

    broken = session.get("mode") == quiz.STREAK and quiz.last_answer_was_wrong(session)
    quiz.advance(session)

    if broken or quiz.is_finished(session):
        await finish_quiz(update, context)
    else:
        await send_question(update, context)

async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = context.user_data["quiz"]

    if session["message_id"]:
        await delete_screen(update, context, session["message_id"])

    correct_count = quiz.score(session)
    total = len(session["queue"])

    if session.get("mode") == quiz.STREAK:
        await finish_streak(update, context, correct_count)
        return

    answers_list = [
        f"{title} — {'✅ Верно!' if is_correct else '❌ Неправильно.'}"
        for title, is_correct in quiz.breakdown(session, context.bot_data["library"]["by_id"])
    ]

    fresh = [
        context.bot_data["library"]["by_id"][card_id]["title"]
        for card_id in progress.first_time(session)
    ]
    if fresh:
        answers_list += ["", f"Впервые услышано: {len(fresh)}"]
        answers_list += [f"• {title}" for title in fresh]

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

async def review_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await dismiss_tap(update, context)

    library = context.bot_data["library"]
    answers = storage.get_answers(context.bot_data["db"], update.effective_user.id)
    card_ids = progress.to_review(
        answers,
        library["by_id"],
        {card["id"] for card in library["playable"]},
    )

    if not card_ids:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Пока не на чем тренироваться — ошибок нет.",
        )
        return

    await clear_audio(update, context)

    session = quiz.session_for(card_ids)
    session["message_id"] = None
    remember_seen(update, context, session)
    context.user_data["quiz"] = session

    await send_question(update, context)

async def finish_streak(update: Update, context: ContextTypes.DEFAULT_TYPE, length: int) -> None:
    db = context.bot_data["db"]
    user_id = update.effective_user.id

    was_best = storage.best_streak(db, user_id)
    storage.save_streak_run(db, user_id, length)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=progress.streak_message(length, was_best),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Ещё серия", callback_data="streak")],
            [InlineKeyboardButton("🎲 Случайный квиз", callback_data="restart")],
        ]),
        message_effect_id=FIRE_EFFECT if length > was_best else None,
    )

    context.user_data.pop("quiz")

async def streak_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await dismiss_tap(update, context)

    await clear_audio(update, context)

    # очередь во всю библиотеку: серия обрывается ошибкой, а не концом списка,
    # а порядок в ней идёт от лёгких карточек к трудным
    playable = context.bot_data["library"]["playable"]
    session = quiz.session_for(quiz.streak_queue(playable), mode=quiz.STREAK)
    session["message_id"] = None
    remember_seen(update, context, session)
    context.user_data["quiz"] = session

    await context.bot.send_message(chat_id=update.effective_chat.id, text=STREAK_START)
    await send_question(update, context)

async def restart_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await dismiss_tap(update, context)

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
        if session.get("mode") == quiz.STREAK:
            result += f" 🔥 {quiz.score(session)} подряд."
    else:
        chosen = context.bot_data["library"]["by_id"][chosen_id]["title"]
        result = f"❌ Неправильно. Вы выбрали «{chosen}»."

    fact = random.choice(card["facts"])

    recording = session["recording"]

    original = card.get("original_title")
    naming = f"{card['title']} ({original})" if original else card["title"]

    # у отдельной пьесы имя фрагмента совпадает с названием — повторять его незачем
    fragment_line = ""
    if session["fragment"] not in card["title"]:
        fragment_line = f"Фрагмент: «{session['fragment']}».\n"

    await query.edit_message_caption(
        caption=(
            f"{result}\n\nЭто {naming}.\n"
            f"{fragment_line}\n"
            f"💡 {fact}\n\n"
            f"🎧 Запись: {recording['performer']} — {recording['source']}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Дальше →", callback_data="next")]
        ]),
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(GREETING, reply_markup=MENU_KEYBOARD)

async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await remove_message(update, context, update.message.message_id)

    library = context.bot_data["library"]
    answers = storage.get_answers(context.bot_data["db"], update.effective_user.id)
    stats = progress.summary(answers, library["by_id"])

    if not stats["total"]:
        await update.message.reply_text(
            "📈 Пока пусто. Пройдите первый квиз — и здесь появится статистика."
        )
        return

    record = storage.best_streak(context.bot_data["db"], update.effective_user.id)

    lines = [
        "📈 Ваш прогресс",
        "",
        f"Ответов: {stats['total']}",
        f"Верно: {stats['correct']} — это {stats['accuracy']}%",
        f"Произведений услышано: {stats['cards_seen']} из {len(library['playable'])}",
    ]

    if record:
        lines.append(f"Лучшая серия: {record} подряд")

    missed = progress.weakest(answers, library["by_id"])
    if missed:
        lines.append("")
        lines.append("Пока даются хуже всего:")
        for card in missed:
            title = library["by_id"][card["card_id"]]["title"]
            lines.append(f"• {title} — {card['correct']} из {card['attempts']}")

    keyboard = None
    if missed:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔁 Работа над ошибками", callback_data="review")]
        ])

    await update.message.reply_text("\n".join(lines), reply_markup=keyboard)

async def audio_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"file_id: {update.message.audio.file_id}")

async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")

async def effect_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.effect_id:
        await update.message.reply_text(f"effect_id: {update.message.effect_id}")