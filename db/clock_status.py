from .connection import get_conn
from models.clock_status import ClockStatus


def set_clocked_in(user_id: int, value: bool) -> None:
    con = get_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO clock_status (user_id, clocked_in, breaks_taken, breaks_missed)
        VALUES (%s, %s, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET clocked_in=EXCLUDED.clocked_in
    """, (user_id, value))
    con.commit()
    cur.close()
    con.close()


def reset_breaks(user_id: int) -> None:
    con = get_conn()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO clock_status (user_id, clocked_in, breaks_taken, breaks_missed)
        VALUES (%s, TRUE, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET breaks_taken=0, breaks_missed=0
    """, (user_id,))
    con.commit()
    cur.close()
    con.close()


def record_break(user_id: int, took: bool) -> None:
    col = "breaks_taken" if took else "breaks_missed"
    con = get_conn()
    cur = con.cursor()
    cur.execute(f"""
        INSERT INTO clock_status (user_id, clocked_in, breaks_taken, breaks_missed)
        VALUES (%s, TRUE, 0, 0)
        ON CONFLICT(user_id) DO UPDATE SET {col}=clock_status.{col}+1
    """, (user_id,))
    con.commit()
    cur.close()
    con.close()


def get(user_id: int) -> ClockStatus:
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "SELECT clocked_in, breaks_taken, breaks_missed FROM clock_status WHERE user_id=%s",
        (user_id,)
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    if row:
        return ClockStatus(user_id=user_id, clocked_in=row[0], breaks_taken=row[1], breaks_missed=row[2])
    return ClockStatus(user_id=user_id, clocked_in=False, breaks_taken=0, breaks_missed=0)


def get_clocked_in_users() -> list[int]:
    con = get_conn()
    cur = con.cursor()
    cur.execute("SELECT user_id FROM clock_status WHERE clocked_in=TRUE")
    rows = cur.fetchall()
    cur.close()
    con.close()
    return [r[0] for r in rows]
