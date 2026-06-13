from .connection import get_conn
from models.schedule import Schedule


def save(schedule: Schedule) -> None:
    con = get_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO schedules (user_id, timezone, start_time, end_time)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT(user_id) DO UPDATE SET
            timezone=EXCLUDED.timezone,
            start_time=EXCLUDED.start_time,
            end_time=EXCLUDED.end_time
    """, (schedule.user_id, schedule.timezone, schedule.start_time, schedule.end_time))
    con.commit()
    cur.close()
    con.close()


def delete(user_id: int) -> None:
    con = get_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM schedules WHERE user_id = %s", (user_id,))
    con.commit()
    cur.close()
    con.close()


def get_all() -> list[Schedule]:
    con = get_conn()
    cur = con.cursor()
    cur.execute("SELECT user_id, timezone, start_time, end_time FROM schedules")
    rows = cur.fetchall()
    cur.close()
    con.close()
    return [Schedule(user_id=r[0], timezone=r[1], start_time=r[2], end_time=r[3]) for r in rows]
