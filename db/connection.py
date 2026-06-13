import os
import psycopg2
import psycopg2.extensions


def get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(os.environ["DATABASE_URL"])


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
    con.commit()
    cur.close()
    con.close()
