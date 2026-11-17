"""Nạp dữ liệu giả lập và bộ tri thức (thuốc, tương tác, ICD, cờ đỏ, mục bắt buộc)."""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache
def kb() -> dict:
    return _load(DATA / "kb.json")


import os
RUNTIME_TS = Path(os.getenv("RUNTIME_TRANSCRIPTS", DATA / "runtime_transcripts"))
# Hồ sơ tạo từ luồng tiếp nhận bàn giao: vùng riêng, không trộn với bộ dữ liệu đánh giá (patients/ + gold/).
RUNTIME_PATIENTS = Path(os.getenv("RUNTIME_PATIENTS", DATA / "runtime_patients"))
PID_RE = re.compile(r"[A-Za-z0-9_-]{1,40}")


def _patient_files() -> list[Path]:
    files = sorted((DATA / "patients").glob("*.json"))
    if RUNTIME_PATIENTS.exists():
        files += sorted(RUNTIME_PATIENTS.glob("p*.json"))
    return files


def list_patients() -> list[dict]:
    return [_load(p)["patient"] for p in _patient_files()]


def load_patient(pid: str) -> dict | None:
    if not isinstance(pid, str) or not PID_RE.fullmatch(pid):  # chặn đường dẫn kiểu ../
        return None
    for folder in (DATA / "patients", RUNTIME_PATIENTS):
        path = folder / f"{pid}.json"
        if path.exists():
            return _load(path)
    return None


def load_transcript(tid: str) -> dict | None:
    for folder in (DATA / "transcripts", RUNTIME_TS):
        path = folder / f"{tid}.json"
        if path.exists():
            return _load(path)
    return None


def save_transcript(pid: str, raw: str) -> dict:
    """Nhận transcript dán vào dạng 'BS: ...' / 'BN: ...' / 'NN: ...' mỗi dòng một lượt."""
    import uuid
    from datetime import datetime

    turns = []
    for line in raw.splitlines():
        m = re.match(r"\s*(BS|BN|NN)\s*[:\-]\s*(.+)", line, flags=re.I)
        if m:
            turns.append({"n": len(turns) + 1, "speaker": m.group(1).upper(), "text": m.group(2).strip()})
    if not turns:
        raise ValueError("Không đọc được lượt nói nào. Mỗi dòng cần bắt đầu bằng BS:, BN: hoặc NN:")
    tid = f"TS-UP-{uuid.uuid4().hex[:8]}"
    t = {"id": tid, "patient_id": pid, "date": datetime.now().isoformat(timespec="minutes"), "turns": turns,
         "_note": "Transcript do người dùng nhập"}
    RUNTIME_TS.mkdir(exist_ok=True)
    (RUNTIME_TS / f"{tid}.json").write_text(json.dumps(t, ensure_ascii=False, indent=2), encoding="utf-8")
    return t


def list_transcripts(pid: str) -> list[dict]:
    out = []
    RUNTIME_TS.mkdir(exist_ok=True)
    for p in sorted((DATA / "transcripts").glob("*.json")) + sorted(RUNTIME_TS.glob("*.json"), reverse=True):
        t = _load(p)
        if t["patient_id"] == pid:
            out.append({"id": t["id"], "date": t["date"], "turns": len(t["turns"])})
    return out


def fold(s: str) -> str:
    """Chữ thường, bỏ dấu, để so khớp tên thuốc."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")


def ingredient_of(drug_name: str) -> str | None:
    """Quy tên biệt dược / tên thuốc về mã hoạt chất trong kb (vd 'Amlor 5 mg' -> 'amlodipine')."""
    name = fold(drug_name)
    best = None
    for key, d in kb()["drugs"].items():
        for brand in d["brands"]:
            if re.search(rf"\b{re.escape(fold(brand))}\b", name):
                if best is None or len(brand) > best[1]:
                    best = (key, len(brand))
    return best[0] if best else None


def drugs_mentioned(text: str) -> list[str]:
    found = []
    t = fold(text)
    for key, d in kb()["drugs"].items():
        if any(re.search(rf"\b{re.escape(fold(b))}\b", t) for b in d["brands"]):
            found.append(key)
    return found


def drug_display(key: str) -> str:
    return kb()["drugs"][key]["display"]


def drug_class(key: str) -> str:
    return kb()["drugs"][key]["class"]
