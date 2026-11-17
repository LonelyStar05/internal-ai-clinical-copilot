"""Lưu trữ: bản nháp, bản duyệt, diff và audit log.

Prototype dùng SQLite cho dễ chạy. Bản triển khai dùng Postgres (cùng schema), đặt DATABASE_PATH hoặc thay kết nối.
"""
from __future__ import annotations

import difflib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", Path(__file__).resolve().parent / "data" / "runtime.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
  id TEXT PRIMARY KEY, patient_id TEXT, transcript_id TEXT, created_by TEXT, created_at TEXT,
  ai_json TEXT, ai_text TEXT, final_text TEXT, status TEXT, approved_by TEXT, approved_at TEXT, diff_json TEXT
);
CREATE TABLE IF NOT EXISTS summary_reviews (
  id TEXT PRIMARY KEY, patient_id TEXT, reviewed_by TEXT, reviewed_at TEXT, decision TEXT, comment TEXT, summary_json TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, username TEXT, role TEXT, action TEXT, patient_id TEXT, detail TEXT
);
-- Phân công hiện hành; ưu tiên hơn patient.attending trong JSON nguồn (JSON không bao giờ bị sửa).
CREATE TABLE IF NOT EXISTS patient_assignments (
  patient_id TEXT PRIMARY KEY, doctor TEXT, status TEXT NOT NULL, assigned_by TEXT, assigned_at TEXT,
  accepted_by TEXT, accepted_at TEXT, note TEXT, version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS assignment_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id TEXT NOT NULL, ts TEXT NOT NULL, action TEXT NOT NULL,
  from_doctor TEXT, to_doctor TEXT, by_user TEXT NOT NULL, by_role TEXT NOT NULL, reason TEXT, version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_assignment_history_patient ON assignment_history(patient_id, id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def audit(username: str, role: str, action: str, patient_id: str | None = None, detail: str = "") -> None:
    with conn() as c:
        c.execute("INSERT INTO audit (ts, username, role, action, patient_id, detail) VALUES (?,?,?,?,?,?)",
                  (now(), username, role, action, patient_id, detail))


def list_audit(limit: int = 200) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]


def save_draft(patient_id: str, transcript_id: str, user: str, ai_json: dict, ai_text: str) -> str:
    nid = uuid.uuid4().hex[:12]
    with conn() as c:
        c.execute("INSERT INTO notes (id, patient_id, transcript_id, created_by, created_at, ai_json, ai_text, status) "
                  "VALUES (?,?,?,?,?,?,?, 'draft')",
                  (nid, patient_id, transcript_id, user, now(), json.dumps(ai_json, ensure_ascii=False), ai_text))
    return nid


def get_note(nid: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM notes WHERE id=?", (nid,)).fetchone()
        return dict(r) if r else None


def list_notes(patient_id: str) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, transcript_id, created_by, created_at, status, approved_by, approved_at, diff_json "
            "FROM notes WHERE patient_id=? ORDER BY created_at DESC", (patient_id,))]


def edit_stats(ai_text: str, final_text: str) -> dict:
    """Thống kê sửa theo mục: dòng AI bị xóa / dòng bác sĩ thêm. Dùng để đo chất lượng bản nháp."""
    def by_section(text: str) -> dict[str, list[str]]:
        out, cur = {}, "(đầu)"
        for line in text.splitlines():
            if line.startswith("## "):
                cur = line[3:].strip()
                out.setdefault(cur, [])
            elif line.strip():
                out.setdefault(cur, []).append(line.strip())
        return out

    a, b = by_section(ai_text), by_section(final_text)
    sections = {}
    for sec in sorted(set(a) | set(b)):
        sa, sb = a.get(sec, []), b.get(sec, [])
        sm = difflib.SequenceMatcher(None, sa, sb)
        removed = sum(i2 - i1 for tag, i1, i2, _, _ in sm.get_opcodes() if tag in ("delete", "replace"))
        added = sum(j2 - j1 for tag, _, _, j1, j2 in sm.get_opcodes() if tag in ("insert", "replace"))
        sections[sec] = {"ai_lines": len(sa), "removed": removed, "added": added}
    total_ai = sum(s["ai_lines"] for s in sections.values()) or 1
    kept = total_ai - sum(s["removed"] for s in sections.values())
    unified = list(difflib.unified_diff(ai_text.splitlines(), final_text.splitlines(), "ban_AI", "ban_duyet", lineterm=""))
    return {"sections": sections, "ai_lines_kept_ratio": round(kept / total_ai, 3), "unified": unified}


def approve(nid: str, user: str, final_text: str) -> dict:
    note = get_note(nid)
    stats = edit_stats(note["ai_text"], final_text)
    with conn() as c:
        c.execute("UPDATE notes SET final_text=?, status='approved', approved_by=?, approved_at=?, diff_json=? WHERE id=?",
                  (final_text, user, now(), json.dumps(stats, ensure_ascii=False), nid))
    return stats


def save_summary_review(patient_id: str, user: str, decision: str, comment: str, summary_json: dict) -> str:
    rid = uuid.uuid4().hex[:12]
    with conn() as c:
        c.execute("INSERT INTO summary_reviews VALUES (?,?,?,?,?,?,?)",
                  (rid, patient_id, user, now(), decision, comment, json.dumps(summary_json, ensure_ascii=False)))
    return rid


def last_summary_review(patient_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT id, reviewed_by, reviewed_at, decision, comment FROM summary_reviews "
                      "WHERE patient_id=? ORDER BY reviewed_at DESC LIMIT 1", (patient_id,)).fetchone()
        return dict(r) if r else None
