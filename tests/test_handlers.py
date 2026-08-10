import asyncio

import pytest
from telegram.error import BadRequest, TimedOut

from handlers import telegram_call

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
