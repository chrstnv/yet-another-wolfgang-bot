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