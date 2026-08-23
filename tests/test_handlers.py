import asyncio
import pathlib
from types import SimpleNamespace

import pytest
from telegram.constants import KeyboardButtonStyle
from telegram.error import BadRequest, TimedOut

from bot import handlers
from bot.handlers import (
    acknowledge, answered_keyboard, expire, favourite_title, favourites_view,
    fragment_keyboard, fragment_number, one_at_a_time, progress_view,
    telegram_call, PAGE,
)
from core import storage
from core.texts import (
    CLOSE_BUTTON, FAVOURITE_ADD, FAVOURITE_DROP, FAVOURITE_REMOVE,
    FAVOURITE_RETURN, FAVOURITES_BACK,
    FAVOURITES_MORE, NEXT_BUTTON, QUIZ_EXPIRED, RESET_BUTTON,
)

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
    handlers.LAST_COMPLAINT = None
    bot = Listener()

    complain(bot)

    assert bot.sent == [("42", "Бот споткнулся:\n\nValueError: сломалось")]

def test_admin_is_not_flooded_with_the_same_breakage(monkeypatch):
    """Одна поломка приходит на каждое нажатие — жаловаться на каждое нельзя."""
    monkeypatch.setenv("ADMIN_CHAT_ID", "42")
    handlers.LAST_COMPLAINT = None
    bot = Listener()

    for _ in range(5):
        complain(bot)

    assert len(bot.sent) == 1

def test_nobody_is_bothered_when_there_is_no_admin(monkeypatch):
    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)
    handlers.LAST_COMPLAINT = None
    bot = Listener()

    complain(bot)

    assert bot.sent == []

def card(card_id: str, title: str, *fragments: str) -> dict:
    return {
        "id": card_id,
        "title": title,
        "fragments": [{"name": name, "audio_file_id": "звук"} for name in fragments],
        "recording": {"performer": "Кто-то", "source": "Откуда-то"},
    }

MORNING = card("grieg-morning", "Григ — «Пер Гюнт», «Утро»", "Утро")
CARNIVAL = card("saint-saens-carnival", "Сен-Санс — «Карнавал животных»", "Лебедь", "Аквариум")

def library_with(*cards) -> dict:
    return {"by_id": {item["id"]: item for item in cards}}

def context_of(cards, marked=()):
    db = storage.connect(":memory:")
    storage.init_schema(db)
    for card_id, fragment in marked:
        storage.add_favourite(db, 1, card_id, fragment)

    return SimpleNamespace(bot_data={"db": db, "library": library_with(*cards)})

def test_fragment_is_found_by_its_name():
    assert fragment_number(CARNIVAL, "Аквариум") == 1

def test_a_fragment_that_is_gone_has_no_number():
    """Библиотека живёт своей жизнью: фрагмент могли переименовать."""
    assert fragment_number(CARNIVAL, "Слон") == -1

def test_a_single_fragment_needs_no_naming_of_its_own():
    assert favourite_title(MORNING, "Утро") == "Григ — «Пер Гюнт», «Утро»"

def test_a_many_part_work_says_what_exactly_played():
    assert favourite_title(CARNIVAL, "Лебедь") == "Сен-Санс — «Карнавал животных», Лебедь"

def test_an_empty_collection_says_so():
    text, markup = favourites_view(context_of([MORNING]), 1)

    assert "Пока пусто" in text
    assert labels_of(markup) == [CLOSE_BUTTON]

def test_a_marked_fragment_shows_up_in_the_list():
    context = context_of([MORNING], marked=[("grieg-morning", "Утро")])

    _, markup = favourites_view(context, 1)

    assert "Григ — «Пер Гюнт», «Утро»" in labels_of(markup)

def test_the_list_itself_offers_no_parting():
    """Расстаются с отмеченным, переслушав, — под самим фрагментом."""
    context = context_of([MORNING], marked=[("grieg-morning", "Утро")])

    _, markup = favourites_view(context, 1)

    assert FAVOURITE_DROP not in labels_of(markup)

def test_a_replayed_fragment_can_be_parted_with_and_put_away():
    markup = fragment_keyboard("grieg-morning", 0, favourite=True)

    assert labels_of(markup) == [FAVOURITE_DROP, CLOSE_BUTTON]

def test_what_was_parted_with_can_be_taken_back():
    markup = fragment_keyboard("grieg-morning", 0, favourite=False)

    assert labels_of(markup) == [FAVOURITE_RETURN, CLOSE_BUTTON]

def test_what_is_gone_from_the_library_is_not_shown():
    """Кнопка, которая ничего не сыграет, хуже отсутствующей."""
    context = context_of([MORNING], marked=[("забытая-карточка", "Что-то")])

    text, markup = favourites_view(context, 1)

    assert "Пока пусто" in text

def test_a_long_collection_offers_the_next_page():
    many = [card(f"карточка-{number}", f"Название {number}", "Ф") for number in range(PAGE + 2)]
    context = context_of(many, marked=[(item["id"], "Ф") for item in many])

    _, markup = favourites_view(context, 1)

    assert FAVOURITES_MORE in labels_of(markup)
    assert FAVOURITES_BACK not in labels_of(markup)

def test_the_second_page_offers_the_way_back():
    many = [card(f"карточка-{number}", f"Название {number}", "Ф") for number in range(PAGE + 2)]
    context = context_of(many, marked=[(item["id"], "Ф") for item in many])

    _, markup = favourites_view(context, 1, offset=PAGE)

    assert FAVOURITES_BACK in labels_of(markup)
    assert FAVOURITES_MORE not in labels_of(markup)

def test_an_offset_past_the_end_lands_on_the_last_page():
    """Список мог укоротиться, пока страница висела на экране."""
    context = context_of([MORNING], marked=[("grieg-morning", "Утро")])

    _, markup = favourites_view(context, 1, offset=500)

    assert "Григ — «Пер Гюнт», «Утро»" in labels_of(markup)

def test_the_answer_offers_to_keep_what_played():
    markup = answered_keyboard(["bizet"], option_cards(), "bizet", "bizet", fragment=0)

    assert FAVOURITE_ADD in labels_of(markup)

def test_what_is_kept_can_be_given_back():
    markup = answered_keyboard(
        ["bizet"], option_cards(), "bizet", "bizet", fragment=0, favourite=True
    )

    assert FAVOURITE_REMOVE in labels_of(markup)

def test_a_card_without_a_fragment_is_not_offered_to_keep():
    markup = answered_keyboard(["bizet"], option_cards(), "bizet", "bizet")

    assert FAVOURITE_ADD not in labels_of(markup)

class Editor:
    """Бот, который запоминает, что и где правил."""

    def __init__(self):
        self.edits = []

    async def edit_message_text(self, text, chat_id=None, message_id=None,
                                reply_markup=None, parse_mode=None):
        self.edits.append((message_id, text))

def redraw(context, chat=1, user=1):
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user), effective_chat=SimpleNamespace(id=chat)
    )

    return run(handlers.redraw_favourites(update, context))

def test_the_open_list_follows_what_happened_under_the_music():
    bot = Editor()
    context = context_of([MORNING], marked=[("grieg-morning", "Утро")])
    context.bot = bot
    context.user_data = {"favourites": {"message_id": 77, "offset": 0}}

    redraw(context)

    assert [message_id for message_id, _ in bot.edits] == [77]

def test_a_list_nobody_opened_is_not_redrawn():
    bot = Editor()
    context = context_of([MORNING])
    context.bot = bot
    context.user_data = {}

    redraw(context)

    assert bot.edits == []
