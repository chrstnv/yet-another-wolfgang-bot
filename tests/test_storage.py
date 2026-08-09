import storage
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
