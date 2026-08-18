import asyncio
import functools
import html
import logging
import random

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest, NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

import progress
import quiz
import storage
from data import (
    CLOSE_BUTTON, GREETING, PROGRESS_CORRECT, PROGRESS_EMPTY, PROGRESS_HEARD, PROGRESS_RECORD,
    PROGRESS_TITLE, PROGRESS_WEAKEST, QUESTION_VARIANTS, QUIZ_EXPIRED, REPLY_DECKS,
    STREAK_FRESH,
    REVEAL_ANSWERS, SETTINGS,
    SETTINGS_OFF, SETTINGS_ON, SETTINGS_TOAST, STREAK_START,
)
from keyboards import MENU_KEYBOARD

# Идентификаторы стандартных эффектов одинаковы у всех, получить их можно
# хендлером effect_id: отправить боту сообщение с эффектом.
# Конфетти достаётся безошибочному квизу, огонёк — рекорду серии:
# достижения разные, и ощущаться должны по-разному.
LOGGER = logging.getLogger(__name__)

CONFETTI_EFFECT = "5046509860389126442"
FIRE_EFFECT = "5104841245755180586"

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сетевые сбои — строчкой в лог, всё остальное — со стеком.

    До Телеграма не всегда получается достучаться, и на это нечего ответить:
    обновление придёт заново или не придёт вовсе. Полотно на сорок строк такое
    событие не заслуживает и только прячет настоящие ошибки.

    BadRequest в этой библиотеке тоже наследник NetworkError, хотя сбой это
    наш, а не сетевой, — поэтому исключаем его отдельно.
    """
    error = context.error

    if isinstance(error, (TimedOut, NetworkError)) and not isinstance(error, BadRequest):
        LOGGER.warning("Телеграм не отозвался: %s", error)
        return

    LOGGER.error("Необработанная ошибка", exc_info=error)

async def acknowledge(query, text: str | None = None, show_alert: bool = False) -> None:
    """Гасит «часики» на нажатой кнопке — последним делом, а не первым.

    Пока нажатие не подтверждено, Телеграм крутит на кнопке индикатор. Это
    и есть честный ответ пользователю на время, пока мы пробиваемся сквозь
    сеть: подтвердив сразу, мы бы погасили индикатор и оставили человека
    смотреть на молчащий экран.

    Ошибки тут глотаются любые. Ответить на нажатие Телеграм разрешает лишь
    несколько секунд: если мы столько провозились или бот перезапускался,
    подтверждать уже нечего — индикатор погаснет сам. Повторять тоже незачем,
    к третьей попытке нажатие протухнет наверняка.
    """
    try:
        await query.answer(text=text, show_alert=show_alert)
    except TelegramError:
        pass

# сколько раз пробовать достучаться до Телеграма и сколько ждать между попытками.
# Короткие заходы лучше долгих: обрыв соединения — событие мгновенное, и второй
# набор через двести миллисекунд имеет столько же шансов, сколько первый.
# Пауза постоянная, а не растущая: с растущей пять попыток не уложились бы
# в пятнадцать секунд, которые Телеграм держит нажатие живым
ATTEMPTS = 5
PAUSE = 0.2

async def telegram_call(call, attempts: int = ATTEMPTS, pause: float = PAUSE):
    """Обращение к Телеграму с повтором на сетевых сбоях.

    Принимает функцию, а не готовую корутину: корутину нельзя ждать дважды,
    а повтору нужен свежий вызов.

    Соединение обрывается на установке — до Телеграма запрос не доходит,
    и повторить его безопасно. Правка, которая ничего не меняет, тоже
    считается ошибкой: так бывает на двойном нажатии, когда кнопки уже
    сняты, и делать после неё нечего.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except BadRequest as error:
            if "not modified" in str(error).lower():
                return None
            raise
        except (TimedOut, NetworkError) as error:
            if attempt == attempts:
                raise
            LOGGER.warning("Телеграм не отозвался (%s), попытка %d", error, attempt + 1)
            await asyncio.sleep(pause)

# кого мы сейчас обслуживаем. Библиотека и так берёт обновления по одному, но
# очередь не спасает: пока нажатие десять секунд пробивается сквозь сеть, нажатия
# нетерпеливого пользователя копятся, и каждое заводит собственную цепочку попыток
WORKING: dict[int, asyncio.Task] = {}

def one_at_a_time(handler):
    """Пока нажатие этого пользователя в работе, следующие гасим и забываем.

    Держим не флаг, а саму задачу: обработчики зовут друг друга — «ещё квиз»
    ведёт в случайный квиз, — и на флаге такой вызов заблокировал бы сам себя.
    Своей же задаче замок открыт.
    """

    @functools.wraps(handler)
    async def guarded(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        holder = WORKING.get(user_id)

        if holder is not None and holder is not asyncio.current_task():
            LOGGER.info("Нажатие пропущено: предыдущее ещё в работе")
            if update.callback_query:
                await acknowledge(update.callback_query)
            return

        if holder is not None:
            await handler(update, context)
            return

        WORKING[user_id] = asyncio.current_task()
        try:
            await handler(update, context)
        finally:
            WORKING.pop(user_id, None)

    return guarded

async def remove_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int) -> None:
    """Убирает сообщение, не сдаваясь на первом сетевом сбое.

    Удаление идёт перед отправкой следующего вопроса, и если оно тихо не
    случится, в чате останутся два аудио разом. Повторить его безопасно:
    удалить уже удалённое — ошибка, которую мы и так проглатываем.
    """
    try:
        await telegram_call(lambda: context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=message_id,
        ))
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
        await acknowledge(query)
        await telegram_call(lambda: query.edit_message_reply_markup(reply_markup=None))

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

@one_at_a_time
async def random_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await remove_message(update, context, update.message.message_id)

    await clear_audio(update, context)

    session = quiz.start_session(context.bot_data["library"]["playable"])
    session["message_id"] = None
    remember_seen(update, context, session)
    context.user_data["quiz"] = session

    await send_question(update, context)

def bare(text: str) -> str:
    """Название без кавычек и регистра — для сравнения с именем фрагмента.

    В названии эпизод бывает в кавычках («Выход гладиаторов»), а во фрагменте
    без них, и посимвольное сравнение таких двойников не узнаёт.
    """
    return text.lower().strip("«»\"" + " .,:;")

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
    session["question"] = quiz.next_line(session, "question", QUESTION_VARIANTS)

    # варианты выбираются один раз: если открывать их кнопкой, набор должен
    # остаться тем же, а не перетасоваться заново
    session["options"] = [option["id"] for option in quiz.build_options(card, library["cards"])]

    hidden = storage.hide_options(context.bot_data["db"], update.effective_user.id)
    keyboard = (
        InlineKeyboardMarkup([[InlineKeyboardButton(REVEAL_ANSWERS, callback_data="reveal")]])
        if hidden
        else options_keyboard(session["options"], library["by_id"])
    )

    message = await telegram_call(lambda: context.bot.send_audio(
        chat_id=update.effective_chat.id,
        audio=fragment["audio_file_id"],
        caption=progress.question_caption(session),
        parse_mode="HTML",
        reply_markup=keyboard,
        title="🎵 Фрагмент",
        performer=quiz.recording_of(card, fragment)["performer"],
    ))
    session["message_id"] = message.message_id
    storage.save_sent_audio(
        context.bot_data["db"], update.effective_user.id, message.message_id
    )

async def expire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Гасит кнопки под вопросом, от которого не осталось сессии.

    Бывает, когда квиз бросили очень давно или состояние потерялось: молча
    ничего не делать хуже всего — кнопки выглядят сломанными.
    """
    query = update.callback_query
    await acknowledge(query, QUIZ_EXPIRED, show_alert=True)
    await telegram_call(lambda: query.edit_message_reply_markup(reply_markup=None))

@one_at_a_time
async def reveal_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    session = context.user_data.get("quiz")
    if not session:
        await expire(update, context)
        return
    if query.message.message_id != session["message_id"]:
        await acknowledge(query)
        return

    await telegram_call(lambda: query.edit_message_reply_markup(
        reply_markup=options_keyboard(session["options"], context.bot_data["library"]["by_id"])
    ))
    await acknowledge(query)

def settings_view(hidden: bool) -> tuple[str, InlineKeyboardMarkup]:
    return (
        SETTINGS.format(state=SETTINGS_ON if hidden else SETTINGS_OFF),
        InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "Выключить" if hidden else "Включить", callback_data="toggle-hide"
            )],
            [InlineKeyboardButton(CLOSE_BUTTON, callback_data="close")],
        ]),
    )

@one_at_a_time
async def close_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    await remove_message(update, context, query.message.message_id)
    await acknowledge(query)

async def settings_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await remove_message(update, context, update.message.message_id)

    hidden = storage.hide_options(context.bot_data["db"], update.effective_user.id)
    text, keyboard = settings_view(hidden)

    await update.message.reply_text(text, reply_markup=keyboard)

@one_at_a_time
async def toggle_hide_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    db = context.bot_data["db"]
    user_id = update.effective_user.id

    hidden = not storage.hide_options(db, user_id)
    storage.set_hide_options(db, user_id, hidden)

    # всплывающая подсказка: смена слова в тексте сама по себе незаметна
    await acknowledge(query, SETTINGS_TOAST[hidden])

    text, keyboard = settings_view(hidden)
    await telegram_call(lambda: query.edit_message_text(text, reply_markup=keyboard))

@one_at_a_time
async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    session = context.user_data.get("quiz")
    if not session:
        await expire(update, context)
        return
    if query.message.message_id != session["message_id"]:
        await acknowledge(query)
        return

    await delete_screen(update, context, session["message_id"])
    session["message_id"] = None

    broken = session.get("mode") == quiz.STREAK and quiz.last_answer_was_wrong(session)
    quiz.advance(session)

    if broken or quiz.is_finished(session):
        await finish_quiz(update, context)
    else:
        await send_question(update, context)

    await acknowledge(query)

async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = context.user_data["quiz"]

    if session["message_id"]:
        await delete_screen(update, context, session["message_id"])

    correct_count = quiz.score(session)
    total = len(session["queue"])

    if session.get("mode") == quiz.STREAK:
        await finish_streak(update, context, correct_count)
        return

    # названия идут в разметку, а в них живут кавычки и амперсанды
    answers_list = [
        f"• {html.escape(title)} — {'✅ Верно!' if is_correct else '❌ Неправильно.'}"
        for title, is_correct in quiz.breakdown(session, context.bot_data["library"]["by_id"])
    ]

    fresh = [
        html.escape(context.bot_data["library"]["by_id"][card_id]["title"])
        for card_id in progress.first_time(session)
    ]
    if fresh:
        answers_list += ["", STREAK_FRESH.format(count=len(fresh))]
        answers_list += [f"• {title}" for title in fresh]

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"{progress.verdict(correct_count, total)}\n\n"
            f"{"\n".join(answers_list)}"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 Ещё квиз", callback_data="restart")],
            [InlineKeyboardButton(CLOSE_BUTTON, callback_data="close")],
        ]),
        message_effect_id=CONFETTI_EFFECT if correct_count == total else None,
    )

    context.user_data.pop("quiz")

@one_at_a_time
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

    library = context.bot_data["library"]
    # названия идут в разметку, а в них живут кавычки и амперсанды
    fresh = [
        html.escape(library["by_id"][card_id]["title"])
        for card_id in progress.first_time(context.user_data["quiz"])
    ]

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=progress.streak_message(length, was_best, fresh),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Ещё серия", callback_data="streak")],
            [InlineKeyboardButton("🎲 Случайный квиз", callback_data="restart")],
            [InlineKeyboardButton(CLOSE_BUTTON, callback_data="close")],
        ]),
        message_effect_id=FIRE_EFFECT if length > was_best else None,
    )

    context.user_data.pop("quiz")

@one_at_a_time
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

@one_at_a_time
async def restart_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await dismiss_tap(update, context)

    await random_quiz(update, context)

@one_at_a_time
async def quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    session = context.user_data.get("quiz")
    if not session:
        await expire(update, context)
        return
    if quiz.is_answered(session):
        await acknowledge(query)
        return

    _, chosen_id = query.data.split(":")
    card_id = quiz.current_card_id(session)
    card = context.bot_data["library"]["by_id"][card_id]

    quiz.record_answer(session, card_id, chosen_id)
    storage.save_answer(context.bot_data["db"], update.effective_user.id, card_id, chosen_id)

    correct = chosen_id == card_id
    deck = quiz.reply_deck(card, correct)
    reply = quiz.next_line(session, deck, REPLY_DECKS[deck])

    original = card.get("original_title")
    naming = f"{card['title']} ({original})" if original else card["title"]

    # о себе Вольфганг говорит в первом лице, и фамилия в начале названия
    # становится лишней: «это я — Моцарт — Лакримоза» звучит как заикание
    mozart = card.get("composer") == quiz.MOZART
    if mozart:
        naming = naming.split(" — ", 1)[-1]

    # имя фрагмента печатается, только если что-то добавляет к названию.
    # У карточки с одним фрагментом различать нечего, поэтому достаточно, чтобы
    # имя просто входило в название: «Ноктюрн» при «Ноктюрн №2, Op. 9» — пустой звук.
    # Там, где фрагментов несколько, вхождения мало: у «Интродукции и рондо
    # каприччиозо» слово «рондо» сидит внутри названия, но именно оно и различает части
    fragment = session["fragment"]
    alone = len(card["fragments"]) == 1
    inside = bare(fragment) in bare(card["title"])
    if inside if alone else bare(card["title"]).endswith(bare(fragment)):
        fragment = ""

    await telegram_call(lambda: query.edit_message_caption(
        caption=progress.answer_caption(
            naming=naming,
            description=card.get("description", ""),
            fragment=fragment,
            fact=random.choice(card["facts"]),
            recording=session["recording"],
            reply=reply,
            correct=correct,
            chosen=context.bot_data["library"]["by_id"][chosen_id]["title"],
            streak=quiz.score(session) if session.get("mode") == quiz.STREAK else 0,
            mozart=mozart,
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Дальше →", callback_data="next")]
        ]),
    ))
    await acknowledge(query)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(GREETING, reply_markup=MENU_KEYBOARD)

async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await remove_message(update, context, update.message.message_id)

    library = context.bot_data["library"]
    answers = storage.get_answers(context.bot_data["db"], update.effective_user.id)
    stats = progress.summary(answers, library["by_id"])

    if not stats["total"]:
        await update.message.reply_text(
            PROGRESS_EMPTY,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(CLOSE_BUTTON, callback_data="close")]
            ]),
        )
        return

    record = storage.best_streak(context.bot_data["db"], update.effective_user.id)

    # каждая строчка сводки — про своё, и вплотную они читаются как список
    counters = [
        PROGRESS_HEARD.format(seen=stats["cards_seen"]),
        PROGRESS_CORRECT.format(
            correct=stats["correct"], answered=stats["total"], accuracy=stats["accuracy"]
        ),
    ]

    if record:
        counters.append(PROGRESS_RECORD.format(record=record))

    lines = [PROGRESS_TITLE, "", "\n\n".join(counters)]

    missed = progress.weakest(answers, library["by_id"])
    if missed:
        lines += ["", PROGRESS_WEAKEST]
        for card in missed:
            # названия идут в разметку, а в них живут кавычки и амперсанды
            title = html.escape(library["by_id"][card["card_id"]]["title"])
            lines.append(f"• {title} — {card['correct']} из {card['attempts']}")

    buttons = []
    if missed:
        buttons.append([InlineKeyboardButton("🔁 Работа над ошибками", callback_data="review")])
    buttons.append([InlineKeyboardButton(CLOSE_BUTTON, callback_data="close")])

    await update.message.reply_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML"
    )

async def audio_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"file_id: {update.message.audio.file_id}")

async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")

async def effect_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.effect_id:
        await update.message.reply_text(f"effect_id: {update.message.effect_id}")