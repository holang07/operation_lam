"""Task / to-do theo nhóm KH hoặc từng KH, theo dõi đến khi Xong."""
from __future__ import annotations

from datetime import date

from . import db

STATUSES = ["Chưa làm", "Đang làm", "Chờ KH", "Xong"]
PRIORITIES = ["Cao", "Thường", "Thấp"]
_PRI = {"Cao": 0, "Thường": 1, "Thấp": 2}


def add(title: str, scope: str = "Chung", target: str = "", priority: str = "Thường",
        due: str = "", note: str = "", status: str = "Chưa làm") -> int:
    ts = db.now()
    with db.conn() as c:
        cur = c.execute(
            "INSERT INTO tasks(title,note,scope,target,priority,due,status,created_at,updated_at,done_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (title.strip(), note, scope, target, priority, due or "", status, ts, ts, ts if status == "Xong" else None))
        return cur.lastrowid


def update(task_id: int, **fields) -> None:
    if not fields:
        return
    if "status" in fields:
        fields["done_at"] = db.now() if fields["status"] == "Xong" else None
    fields["updated_at"] = db.now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with db.conn() as c:
        c.execute(f"UPDATE tasks SET {cols} WHERE id=?", [*fields.values(), task_id])


def delete(task_id: int) -> None:
    with db.conn() as c:
        c.execute("DELETE FROM tasks WHERE id=?", (task_id,))


def is_overdue(t: dict) -> bool:
    return bool(t["due"]) and t["status"] != "Xong" and t["due"] < date.today().isoformat()


def list_tasks(include_done: bool = False) -> list[dict]:
    with db.conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM tasks")]
    if not include_done:
        rows = [r for r in rows if r["status"] != "Xong"]
    # quá hạn trước, rồi ưu tiên, rồi hạn gần, rồi mới tạo
    rows.sort(key=lambda r: (r["status"] == "Xong", not is_overdue(r), _PRI.get(r["priority"], 1),
                             r["due"] or "9999-99-99", -r["id"]))
    return rows


def counts() -> dict:
    rows = list_tasks(include_done=False)
    return {"open": len(rows), "overdue": sum(is_overdue(r) for r in rows)}


def groups() -> dict[str, list[str]]:
    """{tên nhóm: [tên KH]} theo cột group_name của khách hàng."""
    out: dict[str, list[str]] = {}
    with db.conn() as c:
        for r in c.execute("SELECT name, group_name FROM customers WHERE group_name!='' ORDER BY name"):
            out.setdefault(r["group_name"], []).append(r["name"])
    return out


def set_group(customer_id: int, group: str) -> None:
    with db.conn() as c:
        c.execute("UPDATE customers SET group_name=? WHERE id=?", (group.strip(), customer_id))


def customer_groups() -> list[dict]:
    with db.conn() as c:
        return [dict(r) for r in c.execute("SELECT id, name, account_no, group_name FROM customers ORDER BY name")]
