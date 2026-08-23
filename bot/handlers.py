import asyncio
import functools
import html
import logging
import os
import random
import time

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import KeyboardButtonStyle
from telegram.error import BadRequest, NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from core import progress
from core import quiz
from core import storage
from core.texts import (
    CLOSE_BUTTON, GREETING, MENU_UPDATED, NEXT_BUTTON, PROGRESS_CORRECT, PROGRESS_EMPTY, PROGRESS_HEARD,
    QUIZ_TITLE,
    PROGRESS_RECORD,
    PROGRESS_TITLE, PROGRESS_WEAKEST, PROGRESS_WEAKEST_ITEM, QUESTION_VARIANTS,
    FAVOURITE_ADD, FAVOURITE_DECKS, FAVOURITE_GONE, FAVOURITE_REMOVE,
    FAVOURITE_DROP, FAVOURITE_RETURN,
    FAVOURITES_BACK, FAVOURITES_COUNT, FAVOURITES_EMPTY,
    FAVOURITES_MORE, FAVOURITES_TITLE,
    QUIZ_EXPIRED, REPLY_DECKS, RESET_BUTTON, RESET_CONFIRM, RESET_DONE,
    RESET_NO, RESET_YES,
    STREAK_FRESH,
    REVEAL_ANSWERS, SETTINGS,
    SETTINGS_OFF, SETTINGS_ON, SETTINGS_TOAST, STREAK_START,
)
from bot.keyboards import MENU_KEYBOARD, MENU_VERSION

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
    await tell_the_admin(context, error)

# кому жаловаться и как часто. Ошибки приходят пачками — одна поломка на каждое
# нажатие, — и без паузы бот завалил бы чат сообщениями о самом себе
COMPLAINT_PAUSE = 300
# None, а не ноль: monotonic отсчитывается от загрузки машины, и на только что
# поднятой ноль означал бы «жаловались только что», а не «не жаловались ни разу»
LAST_COMPLAINT: float | None = None

async def tell_the_admin(context: ContextTypes.DEFAULT_TYPE, error: BaseException) -> None:
    """Сообщает о поломке в чат владельца.

    На сервере логи никто не читает по своей воле, а узнавать о поломке от
    пользователей — поздно. Само сообщение короткое: подробности со стеком
    остаются в логах.
    """
    global LAST_COMPLAINT

    chat_id = os.getenv("ADMIN_CHAT_ID")
    if not chat_id:
        return

    now = time.monotonic()
    if LAST_COMPLAINT is not None and now - LAST_COMPLAINT < COMPLAINT_PAUSE:
        return
    LAST_COMPLAINT = now

    # текст ошибки идёт как есть: в нём попадаются угловые скобки, и разметку
    # тут включать нельзя. Токен в сообщение не попадает — PTB прячет его в
    # тексте исключений, но не в адресах внутри трейсбека, а трейсбек мы не шлём
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Бот споткнулся:\n\n{type(error).__name__}: {error}"[:400],
        )
    except TelegramError as failure:
        LOGGER.warning("Не получилось пожаловаться админу: %s", failure)

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
# На замедленном канале коротких заходов не хватает, поэтому оба числа можно
# поднять переменными окружения, не трогая код: сервер и ноутбук живут в разных
# сетевых условиях
ATTEMPTS = int(os.getenv("TELEGRAM_ATTEMPTS", "5"))
PAUSE = float(os.getenv("TELEGRAM_PAUSE", "0.2"))

# правки, после которых делать нечего. Сообщение не изменилось — так бывает на
# двойном нажатии; сообщения нет вовсе — его удалили из чата, а кнопки под ним
# у клиента остались живыми, и нажатие всё равно доходит до бота
NOTHING_TO_EDIT = ("not modified", "message to edit not found")

async def telegram_call(call, attempts: int = ATTEMPTS, pause: float = PAUSE):
    """Обращение к Телеграму с повтором на сетевых сбоях.

    Принимает функцию, а не готовую корутину: корутину нельзя ждать дважды,
    а повтору нужен свежий вызов.

    Соединение обрывается на установке — до Телеграма запрос не доходит,
    и повторить его безопасно. Правка, которой некуда лечь, ошибкой считается,
    но нашей — нет: ни повторять её, ни падать незачем, сообщения либо и так
    в нужном виде, либо больше нет.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except BadRequest as error:
            if any(reason in str(error).lower() for reason in NOTHING_TO_EDIT):
                LOGGER.info("Правка пропущена: %s", error)
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

async def send_fragment(
    update: Update, context: ContextTypes.DEFAULT_TYPE, fragment: dict, **extra
):
    """Единственная дверь, через которую бот присылает музыку.

    Отправленное здесь же и запоминается. Аудио в чате складывается в плейлист,
    и любой забытый кусок возвращает то самое перескакивание плеера, от которого
    заведён clear_audio. Держать это на внимательности нельзя: мест, откуда
    шлют фрагменты, со временем становится больше — пусть дверь будет одна.
    """
    message = await telegram_call(lambda: context.bot.send_audio(
        chat_id=update.effective_chat.id,
        audio=fragment["audio_file_id"],
        **extra,
    ))
    storage.save_sent_audio(
        context.bot_data["db"], update.effective_user.id, message.message_id
    )

    return message

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

def options_keyboard(option_ids: list[str], by_id: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(by_id[option_id]["title"], callback_data=f"answer:{option_id}")]
        for option_id in option_ids
    ])

def answered_keyboard(
    option_ids: list[str], by_id: dict, card_id: str, chosen_id: str,
    fragment: int | None = None, favourite: bool = False,
) -> InlineKeyboardMarkup:
    """Те же варианты, но с раскраской: верный зелёный, промах красный.

    Кнопки остаются на месте, а не исчезают: видно не только что было верно, но
    и что вы выбрали, — без перечитывания подписи. Нажатия по ним игнорируются,
    quiz_answer отсекает отвеченный вопрос сам.

    Цвет появился в Bot API 9.4, февраль 2026 года. В клиентах постарше он
    просто не показывается, и кнопки выглядят как раньше.
    """
    rows = []
    for option_id in option_ids:
        style = None
        if option_id == card_id:
            style = KeyboardButtonStyle.SUCCESS
        elif option_id == chosen_id:
            style = KeyboardButtonStyle.DANGER

        rows.append([InlineKeyboardButton(
            by_id[option_id]["title"],
            callback_data=f"answer:{option_id}",
            style=style,
        )])

    # сердце и «дальше» в одном ряду: одно необязательное, другое — то, ради чего
    # сюда пришли, и разводить их по строкам значило бы уравнять в важности
    onward = [InlineKeyboardButton(NEXT_BUTTON, callback_data="next")]
    if fragment is not None:
        onward.insert(0, InlineKeyboardButton(
            FAVOURITE_REMOVE if favourite else FAVOURITE_ADD,
            callback_data=f"fav:{card_id}:{fragment}",
        ))

    rows.append(onward)

    return InlineKeyboardMarkup(rows)

# сколько отмеченного показывать за раз. Пять строк — это пять пар кнопок,
# дальше экран перестаёт охватываться взглядом
PAGE = 5

def fragment_number(card: dict, name: str) -> int:
    """Место фрагмента в карточке. В базе он записан именем — оно не сдвигается,
    когда фрагменты переставляют, — а в кнопку короче положить номер."""
    for number, fragment in enumerate(card.get("fragments") or []):
        if fragment["name"] == name:
            return number

    return -1

def favourite_title(card: dict, name: str) -> str:
    """Композитор и полное название, а у многочастных — ещё и что именно играло."""
    naming = progress.card_naming(card)
    fragment = progress.visible_fragment(card, name, naming)

    return f"{naming}, {fragment}" if fragment else naming

def favourites_view(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, offset: int = 0
) -> tuple[str, InlineKeyboardMarkup]:
    """Экран избранного: страница списка и кнопки под ним.

    Отмеченное, чьей карточки или фрагмента больше нет, пропускается: библиотека
    живёт своей жизнью, а показывать кнопку, которая ничего не сыграет, незачем.
    """
    by_id = context.bot_data["library"]["by_id"]
    closing = [InlineKeyboardButton(CLOSE_BUTTON, callback_data="close")]

    entries = []
    for row in storage.favourites(context.bot_data["db"], user_id):
        card = by_id.get(row["card_id"])
        if not card:
            continue
        number = fragment_number(card, row["fragment"])
        if number >= 0:
            entries.append((card, row["fragment"], number))

    if not entries:
        return FAVOURITES_EMPTY, InlineKeyboardMarkup([closing])

    offset = max(0, min(offset, (len(entries) - 1) // PAGE * PAGE))

    # ряд на строку, без кнопок «убрать»: решение расстаться созревает после
    # прослушивания, поэтому оно и живёт под присланным фрагментом
    rows = [
        [InlineKeyboardButton(
            favourite_title(card, name),
            callback_data=f"favplay:{card['id']}:{number}",
        )]
        for card, name, number in entries[offset:offset + PAGE]
    ]

    moving = []
    if offset:
        moving.append(InlineKeyboardButton(
            FAVOURITES_BACK, callback_data=f"favs:{offset - PAGE}"
        ))
    if offset + PAGE < len(entries):
        moving.append(InlineKeyboardButton(
            FAVOURITES_MORE, callback_data=f"favs:{offset + PAGE}"
        ))
    if moving:
        rows.append(moving)

    rows.append(closing)

    text = f"{FAVOURITES_TITLE}\n\n{FAVOURITES_COUNT.format(count=len(entries))}"

    return text, InlineKeyboardMarkup(rows)

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

    message = await send_fragment(
        update, context, fragment,
        caption=progress.question_caption(session),
        title="🎵 Фрагмент",
        performer=quiz.recording_of(card, fragment)["performer"],
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    session["message_id"] = message.message_id

async def expire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Гасит кнопки под вопросом, от которого не осталось сессии.

    Бывает, когда квиз бросили очень давно или состояние потерялось: молча
    ничего не делать хуже всего — кнопки выглядят сломанными.

    Сначала кнопки, потом слова. Сообщения может уже не быть — его удалили
    из чата, а кнопки под ним у клиента остались нажимаемыми; тогда правка
    ни к чему не приводит, и объяснять нечего: окно всплыло бы посреди чата
    поверх пустого места. Нажатие всё равно подтверждаем, чтобы погас
    индикатор на кнопке.
    """
    query = update.callback_query
    on_screen = await telegram_call(lambda: query.edit_message_reply_markup(reply_markup=None))

    if on_screen is None:
        await acknowledge(query)
        return

    await acknowledge(query, QUIZ_EXPIRED, show_alert=True)

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

    await delete_screen(update, context, query.message.message_id)
    await acknowledge(query)

async def settings_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await remove_message(update, context, update.message.message_id)

    hidden = storage.hide_options(context.bot_data["db"], update.effective_user.id)
    text, keyboard = settings_view(hidden)

    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

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
    await telegram_call(lambda: query.edit_message_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    ))

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
        f"{'✅' if is_correct else '❌'} {html.escape(title)}"
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
            f"{QUIZ_TITLE.format(correct=correct_count, total=total)}\n\n"
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

    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=STREAK_START, parse_mode="HTML"
    )
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

    mozart = card.get("composer") == quiz.MOZART
    naming = progress.card_naming(card, mozart)

    fragment = progress.visible_fragment(card, session["fragment"], naming)

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
        reply_markup=answered_keyboard(
            session["options"], context.bot_data["library"]["by_id"], card_id, chosen_id,
            fragment=fragment_number(card, session["fragment"]),
            favourite=storage.is_favourite(
                context.bot_data["db"], update.effective_user.id,
                card_id, session["fragment"],
            ),
        ),
        # в подписи живут кастомные эмодзи Вольфганга, а они — разметка
        parse_mode="HTML",
    ))
    await acknowledge(query)

def named_fragment(context: ContextTypes.DEFAULT_TYPE, card_id: str, number: str):
    """Карточка и имя фрагмента по тому, что пришло в кнопке."""
    card = context.bot_data["library"]["by_id"].get(card_id)
    if not card:
        return None, ""

    fragments = card.get("fragments") or []
    position = int(number)

    return card, fragments[position]["name"] if position < len(fragments) else ""

def flip_favourite(
    context: ContextTypes.DEFAULT_TYPE, user_id: int, card: dict, name: str
) -> tuple[bool, str]:
    """Отмечает или снимает отметку и подбирает, что Вольфганг на это скажет.

    Своя музыка и чужая — для него события разной приятности, поэтому колоды
    две. Снятие обходится одной строчкой: расстаются с отмеченным редко.
    """
    db = context.bot_data["db"]
    deck = "mine" if card.get("composer") == quiz.MOZART else "other"
    card_id = card["id"]

    if storage.is_favourite(db, user_id, card_id, name):
        storage.remove_favourite(db, user_id, card_id, name)

        return False, FAVOURITE_GONE[deck]

    storage.add_favourite(db, user_id, card_id, name)

    return True, quiz.next_line(context.user_data, f"favourite-{deck}", FAVOURITE_DECKS[deck])

def fragment_keyboard(card_id: str, number: int, favourite: bool) -> InlineKeyboardMarkup:
    """Кнопки под переслушанным: расстаться и убрать с глаз.

    «Закрыть» здесь не украшение: аудио в чате складывается в плейлист, и
    прибранное сразу не заставит плеер перескакивать на него потом.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            FAVOURITE_DROP if favourite else FAVOURITE_RETURN,
            callback_data=f"favmark:{card_id}:{number}",
        )],
        [InlineKeyboardButton(CLOSE_BUTTON, callback_data="close")],
    ])

@one_at_a_time
async def toggle_favourite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмечает прозвучавшее или снимает отметку, а Вольфганг это комментирует.

    Реплика уходит всплывающим окошком: экран ответа и так длинный, а отклик
    нужен немедленный. Разметки там нет, поэтому лицо остаётся обычным эмодзи.
    """
    query = update.callback_query
    _, card_id, number = query.data.split(":")

    card, name = named_fragment(context, card_id, number)
    if not name:
        await acknowledge(query)
        return

    favourite, said = flip_favourite(context, update.effective_user.id, card, name)

    session = context.user_data.get("quiz")
    if session and quiz.is_answered(session):
        await telegram_call(lambda: query.edit_message_reply_markup(
            reply_markup=answered_keyboard(
                session["options"], context.bot_data["library"]["by_id"],
                quiz.current_card_id(session), quiz.chosen_id(session),
                fragment=int(number), favourite=favourite,
            )
        ))

    await redraw_favourites(update, context)
    await acknowledge(query, said, show_alert=False)

async def redraw_favourites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перерисовывает список избранного, если он открыт.

    Список и присланный фрагмент — разные сообщения. Расстаться с вещью под
    музыкой и увидеть её же в списке выше — значит не поверить ни одному экрану.
    Если список уже закрыли, правка не найдёт сообщения и тихо пропустится.
    """
    screen = context.user_data.get("favourites")
    if not screen:
        return

    text, keyboard = favourites_view(context, update.effective_user.id, screen["offset"])

    await telegram_call(lambda: context.bot.edit_message_text(
        text,
        chat_id=update.effective_chat.id,
        message_id=screen["message_id"],
        reply_markup=keyboard,
        parse_mode="HTML",
    ))

async def show_favourites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await remove_message(update, context, update.message.message_id)

    text, keyboard = favourites_view(context, update.effective_user.id)
    message = await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

    # запоминаем, где висит список: его придётся править, когда вещь уберут
    # из-под присланного фрагмента
    context.user_data["favourites"] = {"message_id": message.message_id, "offset": 0}

@one_at_a_time
async def favourites_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    offset = int(query.data.split(":")[1])
    text, keyboard = favourites_view(context, update.effective_user.id, offset)

    context.user_data["favourites"] = {
        "message_id": query.message.message_id, "offset": offset
    }

    await telegram_call(lambda: query.edit_message_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    ))
    await acknowledge(query)

@one_at_a_time
async def mark_fragment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Снимает отметку с переслушанного — или возвращает её обратно.

    Кнопка остаётся переключателем: расстались сгоряча, передумали — вернули,
    не разыскивая вещь заново.
    """
    query = update.callback_query
    _, card_id, number = query.data.split(":")

    card, name = named_fragment(context, card_id, number)
    if not name:
        await acknowledge(query)
        return

    favourite, said = flip_favourite(context, update.effective_user.id, card, name)

    await telegram_call(lambda: query.edit_message_reply_markup(
        reply_markup=fragment_keyboard(card_id, int(number), favourite)
    ))
    await redraw_favourites(update, context)
    await acknowledge(query, said)

@one_at_a_time
async def play_favourite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Присылает отмеченный фрагмент заново.

    Присланное записывается в отправленное аудио, как и вопросы: иначе оно
    останется в чате и следующий квиз начнётся с плейлиста из чужих кусков.
    """
    query = update.callback_query
    _, card_id, number = query.data.split(":")

    card, name = named_fragment(context, card_id, number)
    if not name:
        await acknowledge(query)
        return

    fragment = card["fragments"][int(number)]
    recording = quiz.recording_of(card, fragment)

    await send_fragment(
        update, context, fragment,
        caption=favourite_title(card, name),
        title=name,
        performer=recording["performer"],
        reply_markup=fragment_keyboard(card_id, int(number), favourite=True),
    )
    await acknowledge(query)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # приветствие и так несёт свежую клавиатуру, так что отмечаем её показанной:
    # иначе refresh_menu следом сообщит о перестановке тому, кто меню видит впервые
    context.user_data["menu"] = MENU_VERSION

    await update.message.reply_text(
        GREETING, reply_markup=MENU_KEYBOARD, parse_mode="HTML"
    )

async def refresh_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Присылает меню тем, кто видит устаревшее.

    Клиент показывает ту клавиатуру, что пришла последней, и сам её не обновляет.
    Без этого новый пункт достался бы только нажавшим «Старт» заново — то есть
    почти никому.

    Обработчик стоит в группе после основных: сначала человек получает ответ на
    своё действие, и только потом — сообщение о перестановке. Хранится отметка
    в user_data, который и так переживает перезапуск: заводить ради номера
    таблицу в базе не за что.
    """
    if context.user_data.get("menu") == MENU_VERSION or not update.effective_chat:
        return

    context.user_data["menu"] = MENU_VERSION

    try:
        await update.effective_chat.send_message(
            MENU_UPDATED, reply_markup=MENU_KEYBOARD, parse_mode="HTML"
        )
    except TelegramError as error:
        # не доехало — покажем в следующий раз, отметку вернём обратно
        context.user_data.pop("menu", None)
        LOGGER.warning("Не получилось обновить меню: %s", error)

def progress_view(
    context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Экран прогресса: текст и кнопки под ним.

    Отдельно от отправки, потому что показывается он дважды: по кнопке меню и
    когда человек передумал сбрасывать прогресс, — а во втором случае экран
    надо вернуть на место правкой сообщения.
    """
    library = context.bot_data["library"]
    answers = storage.get_answers(context.bot_data["db"], user_id)
    stats = progress.summary(answers, library["by_id"])

    closing = [InlineKeyboardButton(CLOSE_BUTTON, callback_data="close")]

    if not stats["total"]:
        return PROGRESS_EMPTY, InlineKeyboardMarkup([closing])

    record = storage.best_streak(context.bot_data["db"], user_id)

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
            lines.append(PROGRESS_WEAKEST_ITEM.format(
                title=title, correct=card["correct"], attempts=card["attempts"],
            ))

    buttons = []
    if missed:
        buttons.append([InlineKeyboardButton("🔁 Работа над ошибками", callback_data="review")])
    buttons.append([InlineKeyboardButton(RESET_BUTTON, callback_data="reset")])
    buttons.append(closing)

    return "\n".join(lines), InlineKeyboardMarkup(buttons)

async def show_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await remove_message(update, context, update.message.message_id)

    text, keyboard = progress_view(context, update.effective_user.id)

    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")

@one_at_a_time
async def ask_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Спрашивает, точно ли стирать. Стёртое не вернуть, а кнопка одна."""
    query = update.callback_query

    await telegram_call(lambda: query.edit_message_text(
        RESET_CONFIRM,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                RESET_YES, callback_data="reset-yes", style=KeyboardButtonStyle.DANGER
            )],
            [InlineKeyboardButton(RESET_NO, callback_data="reset-no")],
        ]),
        parse_mode="HTML",
    ))
    await acknowledge(query)

@one_at_a_time
async def confirm_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage.forget_progress(context.bot_data["db"], update.effective_user.id)

    query = update.callback_query

    await telegram_call(lambda: query.edit_message_text(
        RESET_DONE,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(CLOSE_BUTTON, callback_data="close")]
        ]),
        parse_mode="HTML",
    ))
    await acknowledge(query)

@one_at_a_time
async def cancel_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    text, keyboard = progress_view(context, update.effective_user.id)

    await telegram_call(lambda: query.edit_message_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    ))
    await acknowledge(query)

async def audio_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"file_id: {update.message.audio.file_id}")

async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"chat_id: {update.effective_chat.id}")

async def effect_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.effect_id:
        await update.message.reply_text(f"effect_id: {update.message.effect_id}")