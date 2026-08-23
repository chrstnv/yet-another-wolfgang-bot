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
    init_settings(conn)
    init_favourites(conn)

def init_settings(conn: sqlite3.Connection) -> None:
    """Настройки — единственное в базе, что хранит состояние, а не события.

    Ответы и серии копятся как факты, из них считается всё остальное.
    А переключатель — это именно текущее положение тумблера, и накапливать
    его историю незачем.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            user_id      INTEGER PRIMARY KEY,
            hide_options INTEGER NOT NULL DEFAULT 0
        )
    """)
    add_setting(conn, "roulette")

def add_setting(conn: sqlite3.Connection, name: str) -> None:
    """Добавляет тумблер в уже существующую таблицу.

    CREATE TABLE IF NOT EXISTS новых колонок не заводит, а база у людей уже
    заполнена: без этого новый переключатель работал бы только у тех, кто
    пришёл после него.
    """
    known = {row["name"] for row in conn.execute("PRAGMA table_info(settings)")}
    if name not in known:
        conn.execute(f"ALTER TABLE settings ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")

def switch(conn: sqlite3.Connection, name: str, user_id: int) -> bool:
    row = conn.execute(
        f"SELECT {name} FROM settings WHERE user_id = ?", (user_id,)
    ).fetchone()

    return bool(row[name]) if row else False

def set_switch(conn: sqlite3.Connection, name: str, user_id: int, on: bool) -> None:
    conn.execute(f"""
        INSERT INTO settings (user_id, {name}) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET {name} = excluded.{name}
    """, (user_id, int(on)))
    conn.commit()

def roulette(conn: sqlite3.Connection, user_id: int) -> bool:
    """Играть ли со случайных мест записи вместо отобранных фрагментов."""
    return switch(conn, "roulette", user_id)

def set_roulette(conn: sqlite3.Connection, user_id: int, on: bool) -> None:
    set_switch(conn, "roulette", user_id, on)

def hide_options(conn: sqlite3.Connection, user_id: int) -> bool:
    row = conn.execute(
        "SELECT hide_options FROM settings WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    return bool(row["hide_options"]) if row else False

def set_hide_options(conn: sqlite3.Connection, user_id: int, hidden: bool) -> None:
    conn.execute("""
        INSERT INTO settings (user_id, hide_options) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET hide_options = excluded.hide_options
    """, (user_id, int(hidden)))
    conn.commit()

def init_favourites(conn: sqlite3.Connection) -> None:
    """Отмеченное человеком: не достижение, а коллекция.

    Фрагмент запоминается по имени, а не по номеру: номера сдвигаются, стоит
    переставить фрагменты в карточке, и любимая вещь молча стала бы другой.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS favourites (
            user_id  INTEGER NOT NULL,
            card_id  TEXT    NOT NULL,
            fragment TEXT    NOT NULL,
            added_at TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, card_id, fragment)
        )
    """)

def add_favourite(conn: sqlite3.Connection, user_id: int, card_id: str, fragment: str) -> None:
    # повторное нажатие не должно ломаться об уже отмеченное
    conn.execute("""
        INSERT OR IGNORE INTO favourites (user_id, card_id, fragment) VALUES (?, ?, ?)
    """, (user_id, card_id, fragment))
    conn.commit()

def remove_favourite(conn: sqlite3.Connection, user_id: int, card_id: str, fragment: str) -> None:
    conn.execute(
        "DELETE FROM favourites WHERE user_id = ? AND card_id = ? AND fragment = ?",
        (user_id, card_id, fragment),
    )
    conn.commit()

def is_favourite(conn: sqlite3.Connection, user_id: int, card_id: str, fragment: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM favourites WHERE user_id = ? AND card_id = ? AND fragment = ?",
        (user_id, card_id, fragment),
    ).fetchone()

    return row is not None

def favourites(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    """Отмеченное, новое сверху: последнее понравившееся ищут чаще старого."""
    rows = conn.execute("""
        SELECT card_id, fragment FROM favourites WHERE user_id = ?
        ORDER BY added_at DESC, rowid DESC
    """, (user_id,)).fetchall()

    return [dict(row) for row in rows]

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

def forget_progress(conn: sqlite3.Connection, user_id: int) -> None:
    """Стирает всё, что бот помнит о человеке: ответы и серии.

    Настройки и избранное остаются: спрятанные варианты — привычка, а
    коллекция — не достижение. Ни то, ни другое стирать не просили.
    """
    conn.execute("DELETE FROM answers WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM streak_runs WHERE user_id = ?", (user_id,))
    conn.commit()

def get_answers(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    # порядок важен: по нему считается серия верных ответов подряд
    rows = conn.execute(
        "SELECT card_id, chosen FROM answers WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()

    return [dict(row) for row in rows]