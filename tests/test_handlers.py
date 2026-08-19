import asyncio
from types import SimpleNamespace

import pytest
from telegram.constants import KeyboardButtonStyle
from telegram.error import BadRequest, TimedOut

from bot.handlers import acknowledge, answered_keyboard, one_at_a_time, telegram_call
from core.texts import NEXT_BUTTON

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
