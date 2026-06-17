from .connection import get_conn
from models.checklist import Checklist, ChecklistItem


def create(user_id: int, name: str) -> Checklist:
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO checklists (user_id, name) VALUES (%s, %s) RETURNING id",
        (user_id, name),
    )
    row = cur.fetchone()
    con.commit()
    cur.close()
    con.close()
    return Checklist(id=row[0], user_id=user_id, name=name)


def get_by_name(user_id: int, name: str) -> Checklist | None:
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "SELECT id, user_id, name FROM checklists WHERE user_id = %s AND name = %s",
        (user_id, name),
    )
    row = cur.fetchone()
    cur.close()
    con.close()
    return Checklist(id=row[0], user_id=row[1], name=row[2]) if row else None


def get_all(user_id: int) -> list[Checklist]:
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "SELECT id, user_id, name FROM checklists WHERE user_id = %s ORDER BY id",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    con.close()
    return [Checklist(id=r[0], user_id=r[1], name=r[2]) for r in rows]


def delete(checklist_id: int) -> None:
    con = get_conn()
    cur = con.cursor()
    cur.execute("DELETE FROM checklists WHERE id = %s", (checklist_id,))
    con.commit()
    cur.close()
    con.close()


def add_item(checklist_id: int, text: str) -> ChecklistItem:
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO checklist_items (checklist_id, text, checked, position)
        VALUES (%s, %s, FALSE,
            (SELECT COALESCE(MAX(position) + 1, 0) FROM checklist_items WHERE checklist_id = %s))
        RETURNING id, checklist_id, text, checked, position
        """,
        (checklist_id, text, checklist_id),
    )
    row = cur.fetchone()
    con.commit()
    cur.close()
    con.close()
    return ChecklistItem(id=row[0], checklist_id=row[1], text=row[2], checked=row[3], position=row[4])


def get_items(checklist_id: int) -> list[ChecklistItem]:
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        "SELECT id, checklist_id, text, checked, position FROM checklist_items WHERE checklist_id = %s ORDER BY position",
        (checklist_id,),
    )
    rows = cur.fetchall()
    cur.close()
    con.close()
    return [ChecklistItem(id=r[0], checklist_id=r[1], text=r[2], checked=r[3], position=r[4]) for r in rows]


def toggle_item(item_id: int, checked: bool) -> None:
    con = get_conn()
    cur = con.cursor()
    cur.execute("UPDATE checklist_items SET checked = %s WHERE id = %s", (checked, item_id))
    con.commit()
    cur.close()
    con.close()


def reset_items(checklist_id: int) -> None:
    con = get_conn()
    cur = con.cursor()
    cur.execute("UPDATE checklist_items SET checked = FALSE WHERE checklist_id = %s", (checklist_id,))
    con.commit()
    cur.close()
    con.close()
