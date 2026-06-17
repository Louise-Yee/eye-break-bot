import os
import psycopg2
import psycopg2.extensions


def get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "postgres"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def init_db() -> None:
    con = get_conn()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            user_id BIGINT PRIMARY KEY,
            timezone TEXT,
            start_time TEXT,
            end_time TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clock_status (
            user_id BIGINT PRIMARY KEY,
            clocked_in BOOLEAN DEFAULT FALSE,
            breaks_taken INTEGER DEFAULT 0,
            breaks_missed INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS checklists (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(user_id, name)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS checklist_items (
            id SERIAL PRIMARY KEY,
            checklist_id INTEGER NOT NULL REFERENCES checklists(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            checked BOOLEAN DEFAULT FALSE,
            position INTEGER NOT NULL DEFAULT 0
        )
    """)
    con.commit()
    cur.close()
    con.close()
