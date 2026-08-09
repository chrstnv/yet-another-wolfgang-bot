import sqlite3

def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    return conn

def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            card_id     TEXT    NOT NULL,
            chosen      TEXT    NOT NULL,
            answered_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    init_streaks(conn)
    init_sent_audio(conn)

def init_sent_audio(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_audio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            message_id INTEGER NOT NULL
        )
    """)

def save_sent_audio(conn: sqlite3.Connection, user_id: int, message_id: int) -> None:
    """Запоминает отправленное аудио.

    Телеграм не умеет отвечать, какие сообщения бот присылал, а удалять их
    он разрешает только по идентификатору. Держать список в памяти процесса
    мало: после перезапуска бот забывает про чужие фрагменты, оставшиеся
    в чате, и плеер снова начинает на них перескакивать.
    """
    conn.execute(
        "INSERT INTO sent_audio (user_id, message_id) VALUES (?, ?)",
        (user_id, message_id),
    )
    conn.commit()

def sent_audio(conn: sqlite3.Connection, user_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT message_id FROM sent_audio WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()

    return [row["message_id"] for row in rows]

def forget_sent_audio(conn: sqlite3.Connection, user_id: int, message_id: int | None = None) -> None:
    if message_id is None:
        conn.execute("DELETE FROM sent_audio WHERE user_id = ?", (user_id,))
    else:
        conn.execute(
            "DELETE FROM sent_audio WHERE user_id = ? AND message_id = ?",
            (user_id, message_id),
        )
    conn.commit()

def init_streaks(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS streak_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            length      INTEGER NOT NULL,
            finished_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)

def save_streak_run(conn: sqlite3.Connection, user_id: int, length: int) -> None:
    conn.execute(
        "INSERT INTO streak_runs (user_id, length) VALUES (?, ?)",
        (user_id, length),
    )
    conn.commit()

def best_streak(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT MAX(length) AS best FROM streak_runs WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    return row["best"] or 0

def save_answer(conn: sqlite3.Connection, user_id: int, card_id: str, chosen: str) -> None:
    conn.execute("""
        INSERT INTO answers (user_id, card_id, chosen)
        VALUES (?, ?, ?)
    """, (user_id, card_id, chosen))
    conn.commit()

def get_answers(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    # порядок важен: по нему считается серия верных ответов подряд
    rows = conn.execute(
        "SELECT card_id, chosen FROM answers WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()

    return [dict(row) for row in rows]