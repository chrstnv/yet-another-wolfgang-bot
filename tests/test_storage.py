from core import storage
import pytest

@pytest.fixture
def conn():
    connection = storage.connect(":memory:")
    storage.init_schema(connection)
    return connection

def test_init_schema_twice(conn):
    storage.init_schema(conn)
    storage.init_schema(conn)

def test_circular_journey(conn):
    storage.save_answer(conn, 1, "card1", "card2")
    answers = storage.get_answers(conn, 1)
    assert answers == [{"card_id": "card1", "chosen": "card2"}]

def test_isolation_by_user(conn):
    storage.save_answer(conn, 1, "card1", "card2")
    answers = storage.get_answers(conn, 2)
    assert answers == []

def test_time_is_set_automatically(conn):
    storage.save_answer(conn, 1, "card1", "card2")
    row = conn.execute("SELECT answered_at FROM answers WHERE user_id = 1 AND card_id = 'card1'").fetchone()

    assert row["answered_at"] is not None

def test_data_survives_connection_close(tmp_path):
    db_path = tmp_path / "test.db"

    conn = storage.connect(str(db_path))
    storage.init_schema(conn)
    storage.save_answer(conn, 42, "bach-badinerie", "bach-badinerie")
    conn.close()

    conn = storage.connect(str(db_path))
    assert storage.get_answers(conn, 42) == [{"card_id": "bach-badinerie", "chosen": "bach-badinerie"}]
def test_best_streak_is_zero_without_runs(conn):
    assert storage.best_streak(conn, 1) == 0

def test_best_streak_takes_the_longest_run(conn):
    storage.save_streak_run(conn, 1, 3)
    storage.save_streak_run(conn, 1, 7)
    storage.save_streak_run(conn, 1, 5)

    assert storage.best_streak(conn, 1) == 7

def test_streak_runs_are_kept_per_user(conn):
    storage.save_streak_run(conn, 1, 9)

    assert storage.best_streak(conn, 2) == 0

def test_sent_audio_is_remembered_and_ordered(conn):
    storage.save_sent_audio(conn, 1, 100)
    storage.save_sent_audio(conn, 1, 101)

    assert storage.sent_audio(conn, 1) == [100, 101]

def test_sent_audio_is_isolated_by_user(conn):
    storage.save_sent_audio(conn, 1, 100)

    assert storage.sent_audio(conn, 2) == []

def test_forget_sent_audio_removes_one_message(conn):
    storage.save_sent_audio(conn, 1, 100)
    storage.save_sent_audio(conn, 1, 101)

    storage.forget_sent_audio(conn, 1, 100)

    assert storage.sent_audio(conn, 1) == [101]

def test_forget_sent_audio_without_a_message_clears_the_user(conn):
    storage.save_sent_audio(conn, 1, 100)
    storage.save_sent_audio(conn, 2, 200)

    storage.forget_sent_audio(conn, 1)

    assert storage.sent_audio(conn, 1) == []
    assert storage.sent_audio(conn, 2) == [200]

def test_sent_audio_survives_a_restart(tmp_path):
    path = str(tmp_path / "bot.db")
    first = storage.connect(path)
    storage.init_schema(first)
    storage.save_sent_audio(first, 1, 100)
    first.close()

    second = storage.connect(path)
    storage.init_schema(second)

    assert storage.sent_audio(second, 1) == [100]

def test_hide_options_is_off_until_it_is_set(conn):
    assert storage.hide_options(conn, 1) is False

def test_hide_options_can_be_switched_both_ways(conn):
    storage.set_hide_options(conn, 1, True)
    assert storage.hide_options(conn, 1) is True

    storage.set_hide_options(conn, 1, False)
    assert storage.hide_options(conn, 1) is False

def test_hide_options_is_isolated_by_user(conn):
    storage.set_hide_options(conn, 1, True)

    assert storage.hide_options(conn, 2) is False

def test_hide_options_keeps_one_row_per_user(conn):
    storage.set_hide_options(conn, 1, True)
    storage.set_hide_options(conn, 1, False)
    storage.set_hide_options(conn, 1, True)

    rows = conn.execute("SELECT COUNT(*) AS n FROM settings WHERE user_id = 1").fetchone()
    assert rows["n"] == 1

def test_forget_progress_wipes_answers_and_streaks(conn):
    storage.save_answer(conn, 1, "card1", "card1")
    storage.save_streak_run(conn, 1, 5)

    storage.forget_progress(conn, 1)

    assert storage.get_answers(conn, 1) == []
    assert storage.best_streak(conn, 1) == 0

def test_forget_progress_touches_no_one_else(conn):
    storage.save_answer(conn, 1, "card1", "card1")
    storage.save_answer(conn, 2, "card2", "card2")
    storage.save_streak_run(conn, 2, 7)

    storage.forget_progress(conn, 1)

    assert storage.get_answers(conn, 2) == [{"card_id": "card2", "chosen": "card2"}]
    assert storage.best_streak(conn, 2) == 7

def test_forget_progress_keeps_the_settings(conn):
    """Спрятанные варианты — привычка, а не достижение: сбрасывать их не просили."""
    storage.set_hide_options(conn, 1, True)
    storage.save_answer(conn, 1, "card1", "card1")

    storage.forget_progress(conn, 1)

    assert storage.hide_options(conn, 1) is True

def test_a_favourite_is_remembered(conn):
    storage.add_favourite(conn, 1, "grieg-morning", "Утро")

    assert storage.is_favourite(conn, 1, "grieg-morning", "Утро")
    assert storage.favourites(conn, 1) == [{"card_id": "grieg-morning", "fragment": "Утро"}]

def test_marking_twice_changes_nothing(conn):
    """Кнопка-переключатель может прийти дважды — сеть и нетерпеливые пальцы."""
    storage.add_favourite(conn, 1, "grieg-morning", "Утро")
    storage.add_favourite(conn, 1, "grieg-morning", "Утро")

    assert len(storage.favourites(conn, 1)) == 1

def test_fragments_of_one_card_are_counted_apart(conn):
    storage.add_favourite(conn, 1, "saint-saens-carnival", "Лебедь")
    storage.add_favourite(conn, 1, "saint-saens-carnival", "Аквариум")

    assert len(storage.favourites(conn, 1)) == 2

def test_a_favourite_can_be_taken_back(conn):
    storage.add_favourite(conn, 1, "grieg-morning", "Утро")
    storage.remove_favourite(conn, 1, "grieg-morning", "Утро")

    assert storage.favourites(conn, 1) == []
    assert not storage.is_favourite(conn, 1, "grieg-morning", "Утро")

def test_favourites_are_kept_per_user(conn):
    storage.add_favourite(conn, 1, "grieg-morning", "Утро")

    assert storage.favourites(conn, 2) == []

def test_the_newest_favourite_comes_first(conn):
    for card_id in ("первая", "вторая", "третья"):
        storage.add_favourite(conn, 1, card_id, "Ф")

    assert [row["card_id"] for row in storage.favourites(conn, 1)] == ["третья", "вторая", "первая"]

def test_resetting_progress_keeps_the_collection(conn):
    """Избранное — не достижение, а коллекция: стирать её не просили."""
    storage.add_favourite(conn, 1, "grieg-morning", "Утро")
    storage.save_answer(conn, 1, "grieg-morning", "grieg-morning")

    storage.forget_progress(conn, 1)

    assert len(storage.favourites(conn, 1)) == 1

def test_playing_from_random_places_is_off_until_asked(conn):
    assert storage.roulette(conn, 1) is False

def test_the_random_places_switch_goes_both_ways(conn):
    storage.set_roulette(conn, 1, True)
    assert storage.roulette(conn, 1) is True

    storage.set_roulette(conn, 1, False)
    assert storage.roulette(conn, 1) is False

def test_two_switches_do_not_overwrite_each_other(conn):
    """Обе настройки живут в одной строке — легко затереть соседнюю."""
    storage.set_hide_options(conn, 1, True)
    storage.set_roulette(conn, 1, True)

    assert storage.hide_options(conn, 1) is True
    assert storage.roulette(conn, 1) is True

def test_a_switch_added_later_reaches_the_old(conn):
    """База у людей заполнена, а CREATE TABLE новых колонок не заводит."""
    conn.execute("DROP TABLE settings")
    conn.execute("CREATE TABLE settings (user_id INTEGER PRIMARY KEY, hide_options INTEGER NOT NULL DEFAULT 0)")
    conn.execute("INSERT INTO settings (user_id, hide_options) VALUES (1, 1)")

    storage.init_settings(conn)

    assert storage.hide_options(conn, 1) is True
    assert storage.roulette(conn, 1) is False
