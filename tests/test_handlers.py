import asyncio
import pathlib
from types import SimpleNamespace

import pytest
from telegram.constants import KeyboardButtonStyle
from telegram.error import BadRequest, TimedOut

from bot import handlers
from bot.handlers import (
    acknowledge, answered_keyboard, expire, one_at_a_time, progress_view, telegram_call,
)
from core import storage
from core.texts import CLOSE_BUTTON, NEXT_BUTTON, QUIZ_EXPIRED, RESET_BUTTON

def run(coroutine):
    return asyncio.run(coroutine)

def failing(times, error, result="готово"):
    """Вызов, который падает первые times раз, а потом отдаёт результат."""
    calls = {"count": 0}

    async def call():
        calls["count"] += 1
        if calls["count"] <= times:
            raise error
        return result

    call.calls = calls

    return call

def test_telegram_call_returns_the_result_of_a_healthy_call():
    assert run(telegram_call(failing(0, TimedOut()), pause=0)) == "готово"

def test_telegram_call_retries_a_network_failure():
    call = failing(2, TimedOut())

    assert run(telegram_call(call, pause=0)) == "готово"
    assert call.calls["count"] == 3

def test_telegram_call_gives_up_after_the_last_attempt():
    call = failing(5, TimedOut())

    with pytest.raises(TimedOut):
        run(telegram_call(call, attempts=3, pause=0))

    assert call.calls["count"] == 3

def test_telegram_call_swallows_an_edit_that_changes_nothing():
    call = failing(1, BadRequest("Message is not modified: specified new message content"))

    assert run(telegram_call(call, pause=0)) is None
    assert call.calls["count"] == 1

def test_telegram_call_swallows_an_edit_of_a_deleted_message():
    # сообщение удалили из чата, а кнопки под ним у клиента остались рабочими
    call = failing(1, BadRequest("Message to edit not found"))

    assert run(telegram_call(call, pause=0)) is None
    assert call.calls["count"] == 1

def test_telegram_call_does_not_retry_other_bad_requests():
    call = failing(1, BadRequest("Chat not found"))

    with pytest.raises(BadRequest):
        run(telegram_call(call, pause=0))

    assert call.calls["count"] == 1

class Query:
    """Кнопка, которая на любое подтверждение отвечает ошибкой."""

    def __init__(self, error):
        self.error = error
        self.answered = 0

    async def answer(self, text=None, show_alert=False):
        self.answered += 1
        raise self.error

@pytest.mark.parametrize("error", [
    TimedOut(),
    BadRequest("Query is too old and response timeout expired or query id is invalid"),
])
def test_acknowledge_survives_a_button_that_cannot_be_answered(error):
    query = Query(error)

    run(acknowledge(query))

    assert query.answered == 1

class ExpiredQuery:
    """Нажатие под вопросом, от которого не осталось сессии."""

    def __init__(self, error=None):
        self.error = error
        self.answers = []

    async def edit_message_reply_markup(self, reply_markup=None):
        if self.error:
            raise self.error

        return "сообщение без кнопок"

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))

def test_expire_explains_itself_while_the_question_is_on_screen():
    query = ExpiredQuery()

    run(expire(SimpleNamespace(callback_query=query), None))

    assert query.answers == [(QUIZ_EXPIRED, True)]

def test_expire_says_nothing_over_a_message_that_is_gone():
    """Сообщение удалили из чата — окно всплыло бы поверх пустого места."""
    query = ExpiredQuery(BadRequest("Message to edit not found"))

    run(expire(SimpleNamespace(callback_query=query), None))

    assert query.answers == [(None, False)]

def make_update(user_id=1):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id), callback_query=None)

def test_one_at_a_time_lets_a_lone_tap_through():
    seen = []

    @one_at_a_time
    async def handler(update, context):
        seen.append("работал")

    run(handler(make_update(), None))

    assert seen == ["работал"]

def test_one_at_a_time_drops_a_tap_while_the_previous_one_works():
    seen = []

    @one_at_a_time
    async def handler(update, context):
        seen.append("начал")
        await asyncio.sleep(0.05)
        seen.append("кончил")

    async def both():
        await asyncio.gather(
            handler(make_update(), None),
            handler(make_update(), None),
        )

    run(both())

    assert seen == ["начал", "кончил"]

def test_one_at_a_time_keeps_users_apart():
    seen = []

    @one_at_a_time
    async def handler(update, context):
        seen.append(update.effective_user.id)
        await asyncio.sleep(0.05)

    async def two_people():
        await asyncio.gather(handler(make_update(1), None), handler(make_update(2), None))

    run(two_people())

    assert sorted(seen) == [1, 2]

def test_one_at_a_time_lets_a_handler_call_another():
    seen = []

    @one_at_a_time
    async def inner(update, context):
        seen.append("внутренний")

    @one_at_a_time
    async def outer(update, context):
        seen.append("внешний")
        await inner(update, context)

    run(outer(make_update(), None))

    assert seen == ["внешний", "внутренний"]

def test_one_at_a_time_releases_the_lock_after_a_failure():
    @one_at_a_time
    async def handler(update, context):
        raise ValueError("сломалось")

    for _ in range(2):
        with pytest.raises(ValueError):
            run(handler(make_update(), None))

def option_cards():
    return {
        "verdi": {"title": "Верди — «Аида»"},
        "bizet": {"title": "Бизе — «Кармен»"},
        "grieg": {"title": "Григ — «Утро»"},
    }

def styles_of(markup):
    return [button.style for row in markup.inline_keyboard for button in row]

def test_answered_keyboard_paints_the_right_answer_green():
    markup = answered_keyboard(["verdi", "bizet", "grieg"], option_cards(), "bizet", "bizet")

    assert styles_of(markup) == [None, KeyboardButtonStyle.SUCCESS, None, None]

def test_answered_keyboard_paints_a_miss_red_and_still_shows_the_answer():
    markup = answered_keyboard(["verdi", "bizet", "grieg"], option_cards(), "bizet", "grieg")

    assert styles_of(markup) == [None, KeyboardButtonStyle.SUCCESS, KeyboardButtonStyle.DANGER, None]

def test_answered_keyboard_keeps_the_options_and_adds_a_way_on():
    markup = answered_keyboard(["verdi", "bizet", "grieg"], option_cards(), "bizet", "bizet")
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert labels == ["Верди — «Аида»", "Бизе — «Кармен»", "Григ — «Утро»", NEXT_BUTTON]

def test_module_names_are_not_used_as_attributes():
    """Слепое переименование модуля не должно трогать чужие атрибуты.

    Когда data.py стал texts.py, замена по всему файлу превратила заодно
    query.data — данные нажатой кнопки — в query.texts, и ответ на вопрос
    падал с AttributeError. Тесты этого не заметили: quiz_answer живёт целиком
    внутри Telegram и в них не заходит.
    """
    source = pathlib.Path(__file__).parent.parent / "bot" / "handlers.py"
    lines = [
        line for line in source.read_text(encoding="utf-8").splitlines()
        if ".texts" in line and "core.texts" not in line
    ]

    assert lines == []

def context_with(answers: list[tuple[str, str]]):
    """Бот с базой в памяти и библиотекой из одной карточки."""
    db = storage.connect(":memory:")
    storage.init_schema(db)
    for card_id, chosen in answers:
        storage.save_answer(db, 1, card_id, chosen)

    return SimpleNamespace(bot_data={
        "db": db,
        "library": {"by_id": {"bizet": {"title": "Бизе — «Кармен»"}}},
    })

def labels_of(markup):
    return [button.text for row in markup.inline_keyboard for button in row]

def test_progress_view_offers_a_reset_when_there_is_something_to_lose():
    _, markup = progress_view(context_with([("bizet", "bizet")]), 1)

    assert RESET_BUTTON in labels_of(markup)

def test_progress_view_offers_no_reset_on_an_empty_screen():
    """Сбрасывать нечего — и кнопка была бы издевательством не по адресу."""
    _, markup = progress_view(context_with([]), 1)

    assert labels_of(markup) == [CLOSE_BUTTON]

class Listener:
    """Чат владельца, который запоминает всё присланное."""

    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))

def complain(bot, error=ValueError("сломалось")):
    return run(handlers.tell_the_admin(SimpleNamespace(bot=bot), error))

def test_admin_hears_about_a_breakage(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")
    handlers.LAST_COMPLAINT = 0
    bot = Listener()

    complain(bot)

    assert bot.sent == [("42", "Бот споткнулся:\n\nValueError: сломалось")]

def test_admin_is_not_flooded_with_the_same_breakage(monkeypatch):
    """Одна поломка приходит на каждое нажатие — жаловаться на каждое нельзя."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")
    handlers.LAST_COMPLAINT = 0
    bot = Listener()

    for _ in range(5):
        complain(bot)

    assert len(bot.sent) == 1

def test_nobody_is_bothered_when_there_is_no_admin(monkeypatch):
    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)
    handlers.LAST_COMPLAINT = 0
    bot = Listener()

    complain(bot)

    assert bot.sent == []
