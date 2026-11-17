"""Phân công bác sĩ phụ trách hồ sơ.

- Nguồn sự thật là bảng patient_assignments. Chưa có dòng nào thì dùng patient.attending trong JSON (coi như đã tiếp nhận,
  version 0). JSON nguồn không bao giờ bị sửa.
- Trạng thái: unassigned (Chưa phân công) -> pending (Chờ tiếp nhận) -> accepted (Đã phân công, bác sĩ đã tiếp nhận).
- Mọi thay đổi chạy trong một transaction BEGIN IMMEDIATE và so khớp `expected_version`: hai admin cùng sửa thì người sau
  nhận 409 thay vì ghi đè. Mỗi thay đổi ghi một dòng assignment_history.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from typing import Literal

from . import store
from .core import kb as KB

Status = Literal["unassigned", "pending", "accepted"]
STATUS_LABEL = {"unassigned": "Chưa phân công", "pending": "Chờ tiếp nhận", "accepted": "Đã phân công"}
ACTION_LABEL = {"assign": "Phân công", "transfer": "Chuyển hồ sơ", "accept": "Bác sĩ tiếp nhận", "intake": "Tạo hồ sơ từ bàn giao"}
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class AssignError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@contextmanager
def tx():
    """Transaction ghi độc quyền: SQLite chỉ cho một writer giữ BEGIN IMMEDIATE tại một thời điểm."""
    store.conn().close()  # bảo đảm schema đã có
    c = sqlite3.connect(store.DB_PATH, timeout=15, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    finally:
        c.close()


def _default(pid: str, patient: dict) -> dict:
    doc = patient.get("attending")
    return {"patient_id": pid, "doctor": doc, "status": "accepted" if doc else "unassigned", "assigned_by": None,
            "assigned_at": None, "accepted_by": doc, "accepted_at": None, "note": None, "version": 0, "source": "json"}


def _row(c: sqlite3.Connection, pid: str) -> dict | None:
    r = c.execute("SELECT * FROM patient_assignments WHERE patient_id=?", (pid,)).fetchone()
    return {**dict(r), "source": "db"} if r else None


def current(pid: str, c: sqlite3.Connection | None = None) -> dict:
    rec = KB.load_patient(pid)
    if rec is None:
        raise AssignError(404, "Không có người bệnh")
    if c is None:
        with store.conn() as cc:
            row = _row(cc, pid)
    else:
        row = _row(c, pid)
    return row or _default(pid, rec["patient"])


def all_current() -> dict[str, dict]:
    with store.conn() as c:
        rows = {r["patient_id"]: {**dict(r), "source": "db"} for r in c.execute("SELECT * FROM patient_assignments")}
    return {p["id"]: rows.get(p["id"]) or _default(p["id"], p) for p in KB.list_patients()}


def doctor_of(pid: str) -> str | None:
    return current(pid)["doctor"]


def check_doctor(username: object) -> dict:
    """Chỉ nhận tài khoản có thật và đúng role doctor; không bao giờ nhận username tùy ý."""
    from . import auth

    if not isinstance(username, str) or not username.strip():
        raise AssignError(422, "Cần chọn bác sĩ nhận hồ sơ")
    u = auth.USERS.get(username)
    if u is None:
        raise AssignError(422, f"Không có tài khoản “{username[:40]}”")
    if u["role"] == "admin":
        raise AssignError(422, "Không thể phân công hồ sơ cho tài khoản quản trị")
    if u["role"] != "doctor":
        raise AssignError(422, "Tài khoản nhận hồ sơ phải là bác sĩ")
    return {"username": username, **u}


def clean_text(v: object, label: str, required: bool = False, min_len: int = 5, max_len: int = 500) -> str:
    if v is None:
        v = ""
    if not isinstance(v, str):
        raise AssignError(422, f"{label} phải là văn bản")
    v = v.strip()
    if CTRL.search(v):
        raise AssignError(422, f"{label} có ký tự không hợp lệ")
    if len(v) > max_len:
        raise AssignError(422, f"{label} dài quá {max_len} ký tự")
    if required and len(v) < min_len:
        raise AssignError(422, f"Cần nhập {label.lower()} (ít nhất {min_len} ký tự)")
    return v


def _history(c, pid: str, action: str, frm: str | None, to: str | None, by: dict, reason: str, version: int) -> None:
    c.execute("INSERT INTO assignment_history (patient_id, ts, action, from_doctor, to_doctor, by_user, by_role, reason, version) "
              "VALUES (?,?,?,?,?,?,?,?,?)", (pid, store.now(), action, frm, to, by["username"], by["role"], reason, version))


def _set(c, pid: str, cur: dict, doctor: str, by: dict, note: str, status: Status = "pending") -> int:
    new_v = cur["version"] + 1
    ts = store.now()
    accepted = (by["username"], ts) if status == "accepted" else (None, None)
    if cur["source"] == "json":
        c.execute("INSERT INTO patient_assignments VALUES (?,?,?,?,?,?,?,?,?)",
                  (pid, doctor, status, by["username"], ts, *accepted, note, new_v))
    else:
        n = c.execute("UPDATE patient_assignments SET doctor=?, status=?, assigned_by=?, assigned_at=?, accepted_by=?, "
                      "accepted_at=?, note=?, version=? WHERE patient_id=? AND version=?",
                      (doctor, status, by["username"], ts, *accepted, note, new_v, pid, cur["version"])).rowcount
        if n != 1:
            raise AssignError(409, "Hồ sơ vừa được người khác cập nhật. Tải lại danh sách rồi thử lại.")
    return new_v


def _change(c, admin: dict, pid: str, doctor: str, reason: str, expected_version: object, kind: str) -> dict:
    cur = current(pid, c)
    if not isinstance(expected_version, int) or isinstance(expected_version, bool):
        raise AssignError(422, "Thiếu phiên bản hồ sơ (expected_version)")
    if cur["version"] != expected_version:
        raise AssignError(409, f"Hồ sơ {pid} vừa được người khác cập nhật (phiên bản {cur['version']}, bạn đang xem {expected_version}). "
                               "Tải lại danh sách rồi thử lại.")
    if kind == "assign" and cur["doctor"]:
        raise AssignError(409, f"Hồ sơ {pid} đã có bác sĩ phụ trách ({cur['doctor']}). Dùng “Chuyển hồ sơ” và nhập lý do.")
    if kind == "transfer":
        if not cur["doctor"]:
            raise AssignError(409, f"Hồ sơ {pid} chưa có bác sĩ phụ trách. Dùng “Phân công”.")
        if cur["doctor"] == doctor:
            raise AssignError(422, f"Bác sĩ {doctor} đang phụ trách hồ sơ {pid}")
        if len(reason) < 5:
            raise AssignError(422, "Chuyển hồ sơ sang bác sĩ khác bắt buộc nhập lý do (ít nhất 5 ký tự)")
    v = _set(c, pid, cur, doctor, admin, reason)
    _history(c, pid, kind, cur["doctor"], doctor, admin, reason, v)
    return {"patient_id": pid, "from": cur["doctor"], "to": doctor, "version": v, "action": kind}


def assign(admin: dict, pid: str, doctor: str, note: str, expected_version: object) -> dict:
    check_doctor(doctor)
    note = clean_text(note, "Ghi chú bàn giao")
    with tx() as c:
        return _change(c, admin, pid, doctor, note, expected_version, "assign")


def transfer(admin: dict, pid: str, doctor: str, reason: str, expected_version: object) -> dict:
    check_doctor(doctor)
    reason = clean_text(reason, "Lý do chuyển", required=True)
    with tx() as c:
        return _change(c, admin, pid, doctor, reason, expected_version, "transfer")


def bulk(admin: dict, items: object, doctor: str, note: str) -> list[dict]:
    """Tất cả hoặc không: một hồ sơ lỗi thì không hồ sơ nào bị đổi."""
    check_doctor(doctor)
    note = clean_text(note, "Lý do / ghi chú")
    if not isinstance(items, list) or not items:
        raise AssignError(422, "Chưa chọn hồ sơ nào")
    if len(items) > 200:
        raise AssignError(422, "Mỗi lần phân công tối đa 200 hồ sơ")
    pids = [i.get("patient_id") if isinstance(i, dict) else None for i in items]
    if any(not isinstance(p, str) for p in pids) or len(set(pids)) != len(pids):
        raise AssignError(422, "Danh sách hồ sơ không hợp lệ hoặc bị trùng")
    out = []
    with tx() as c:
        for item in items:
            pid = item["patient_id"]
            cur = current(pid, c)
            if cur["doctor"] == doctor:
                if cur["version"] != item.get("expected_version"):
                    raise AssignError(409, f"Hồ sơ {pid} vừa được người khác cập nhật. Tải lại danh sách rồi thử lại.")
                out.append({"patient_id": pid, "from": doctor, "to": doctor, "version": cur["version"], "action": "unchanged"})
                continue
            kind = "transfer" if cur["doctor"] else "assign"
            if kind == "transfer" and len(note) < 5:
                raise AssignError(422, f"Hồ sơ {pid} đang do {cur['doctor']} phụ trách: chuyển sang bác sĩ khác bắt buộc nhập lý do")
            out.append(_change(c, admin, pid, doctor, note, item.get("expected_version"), kind))
    return out


def accept(user: dict, pid: str) -> dict:
    with tx() as c:
        cur = current(pid, c)
        if cur["doctor"] != user["username"]:
            raise AssignError(403, "Chỉ bác sĩ được phân công mới tiếp nhận được hồ sơ này")
        if cur["status"] != "pending":
            raise AssignError(409, "Hồ sơ đã được tiếp nhận trước đó")
        ts = store.now()
        n = c.execute("UPDATE patient_assignments SET status='accepted', accepted_by=?, accepted_at=?, version=version+1 "
                      "WHERE patient_id=? AND version=? AND doctor=?",
                      (user["username"], ts, pid, cur["version"], user["username"])).rowcount
        if n != 1:
            raise AssignError(409, "Hồ sơ vừa thay đổi phân công. Tải lại trang.")
        _history(c, pid, "accept", cur["doctor"], cur["doctor"], user, "", cur["version"] + 1)
    return {"patient_id": pid, "status": "accepted", "accepted_by": user["username"], "accepted_at": ts}


def record_intake(user: dict, pid: str) -> None:
    """Hồ sơ mới từ bàn giao. Bác sĩ tự nhập thì giao luôn cho chính bác sĩ đó (đã tiếp nhận); admin nhập thì để Chưa phân công."""
    with tx() as c:
        cur = current(pid, c)
        if user["role"] == "doctor":
            v = _set(c, pid, cur, user["username"], user, "Bác sĩ tự tiếp nhận bàn giao", status="accepted")
            _history(c, pid, "intake", None, user["username"], user, "Bác sĩ tự tiếp nhận bàn giao", v)
        else:
            _history(c, pid, "intake", None, None, user, "Quản trị tạo hồ sơ; chờ phân công", cur["version"])


def history(pid: str) -> list[dict]:
    current(pid)  # 404 nếu không có hồ sơ
    with store.conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM assignment_history WHERE patient_id=? ORDER BY id DESC", (pid,))]
    for r in rows:
        r["action_label"] = ACTION_LABEL.get(r["action"], r["action"])
    return rows


def doctors(current_map: dict[str, dict] | None = None) -> list[dict]:
    from . import auth

    cm = current_map if current_map is not None else all_current()
    out = []
    for username, u in auth.USERS.items():
        if u["role"] == "doctor":
            mine = [a for a in cm.values() if a["doctor"] == username]
            out.append({"username": username, "name": u["name"], "active": len(mine),
                        "pending": sum(a["status"] == "pending" for a in mine)})
    return out
