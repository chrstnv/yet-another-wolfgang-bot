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