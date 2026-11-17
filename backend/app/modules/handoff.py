"""Tiếp nhận bàn giao bằng lời: transcript -> bản nháp có cấu trúc -> bác sĩ sửa, xác nhận -> tạo hồ sơ runtime.

Nguyên tắc:
- Bản nháp KHÔNG được lưu. Chỉ /confirm (người dùng bấm "Xác nhận tiếp nhận") mới tạo hồ sơ.
- Mọi giá trị trong bản nháp (quy tắc hay LLM) phải có trích dẫn nguyên văn từ một lượt nói và qua bộ kiểm chứng:
  trường có cấu trúc phải suy ra lại được từ trích dẫn bằng quy tắc; trường văn bản chỉ được dùng từ có trong trích dẫn;
  thuốc và con số phải xuất hiện trong trích dẫn. Không qua được thì bị loại, kèm lý do.
- patient_id do server sinh; client không chỉ định được. Tên bác sĩ nghe được trong lời bàn giao chỉ để tham khảo,
  không bao giờ dùng để phân công.
"""
from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator, model_validator

from ..core import kb as KB
from ..core import llm
from ..core.verify import _canon
from ..core.vn_text import normalize, numbers_in

DISCLAIMER = ("BẢN NHÁP TRÍCH TỪ LỜI BÀN GIAO – CHƯA LƯU. AI không chẩn đoán, không kê thuốc. "
              "Kiểm tra từng trường với transcript trước khi xác nhận tiếp nhận.")
MAX_CHARS, MAX_TURNS, MAX_LINE = 20000, 300, 1500

FIELD_KEYS = ("name", "birth_year", "gender", "ward", "room", "bed", "attending_spoken", "admitted_date",
              "admitted_time", "reason", "pulse", "temp", "bp", "resp_rate", "spo2", "weight")
LIST_KEYS = ("diagnoses", "comorbidities", "allergies", "meds", "labs", "pending")
REQUIRED = ("name", "birth_year", "gender", "ward", "room", "bed", "admitted_date", "admitted_time", "reason")
LABELS = {
    "name": "Họ tên", "birth_year": "Năm sinh", "gender": "Giới tính", "ward": "Khoa", "room": "Buồng", "bed": "Giường",
    "attending_spoken": "Bác sĩ được nhắc trong bàn giao", "admitted_date": "Ngày vào viện", "admitted_time": "Giờ vào viện",
    "admitted_at": "Thời điểm vào viện", "reason": "Lý do vào viện", "pulse": "Mạch", "temp": "Nhiệt độ", "bp": "Huyết áp",
    "resp_rate": "Nhịp thở", "spo2": "SpO2", "weight": "Cân nặng", "vitals": "Sinh hiệu", "diagnoses": "Chẩn đoán / vấn đề chính",
    "comorbidities": "Bệnh nền", "allergies": "Dị ứng", "allergy_status": "Tình trạng dị ứng", "meds": "Thuốc đang dùng",
    "labs": "Xét nghiệm / hình ảnh", "pending": "Việc chờ xử lý / cần theo dõi", "transcript_text": "Transcript",
    "acknowledged_warnings": "Xác nhận đã kiểm tra cảnh báo",
}
SPEAKERS = {"bg": "BG", "tn": "TN", "dd": "DD", "bs": "BS", "bn": "BN", "nn": "NN", "ban giao": "BG",
            "nguoi ban giao": "BG", "tiep nhan": "TN", "nguoi tiep nhan": "TN", "nguoi nhan": "TN",
            "dieu duong": "DD", "bac si": "BS"}
VITAL_RANGE = {"pulse": (30, 220), "temp": (34, 42.5), "resp_rate": (6, 60), "spo2": (60, 100), "weight": (2, 250)}


def today() -> date:  # tách riêng để test cố định ngày
    return date.today()


# ---------------------------------------------------------------- văn bản
def fold1(s: str) -> str:
    """Bỏ dấu, chữ thường, GIỮ NGUYÊN ĐỘ DÀI để vị trí regex trên bản bỏ dấu khớp với bản gốc."""
    out = []
    for c in s:
        if c in "đĐ":
            out.append("d")
            continue
        b = unicodedata.normalize("NFD", c)[0].lower()
        out.append(b if len(b) == 1 else c)
    return "".join(out)


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w/%.,]+", " ", fold1(s))).strip(" .,")


def toks(s: str) -> list[str]:
    return [t for t in re.findall(r"\w+", fold1(s)) if len(t) > 1 or t.isdigit()]


UNCERTAIN = re.compile(r"\b(?:hình như|có lẽ|chắc là|khoảng|tầm|không rõ|chưa rõ|nghi|nghĩ|có thể|chưa chắc|ước chừng|hoặc là|hay là)\b", re.I)


def uncertain_words(s: str) -> list[str]:
    return sorted({m.group(0).lower() for m in UNCERTAIN.finditer(s)})


def parse_turns(raw: str) -> list[dict]:
    """Mỗi dòng một lượt. Nhãn người nói tùy chọn (BG:, TN:, ĐD:, BS: ...); dòng không nhãn coi là người bàn giao."""
    if not isinstance(raw, str):
        raise ValueError("Transcript phải là văn bản")
    if len(raw) > MAX_CHARS:
        raise ValueError(f"Transcript dài quá {MAX_CHARS} ký tự")
    turns: list[dict] = []
    for line in raw.splitlines():
        line = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", line).strip()
        if not line:
            continue
        speaker, text = "BG", line
        bare = re.match(r"^([^\W\d_][^:]{0,24}?)\s*:\s*$", line)
        if bare and fold1(bare.group(1)).strip() in SPEAKERS:
            continue  # chỉ có nhãn người nói, không có nội dung
        m = re.match(r"^([^\W\d_][^:]{0,24}?)\s*:\s*(.+)$", line)
        if m and fold1(m.group(1)).strip() in SPEAKERS:
            speaker, text = SPEAKERS[fold1(m.group(1)).strip()], m.group(2).strip()
        if not re.search(r"\w", text):
            continue
        if len(text) > MAX_LINE:
            raise ValueError(f"Lượt nói {len(turns) + 1} dài quá {MAX_LINE} ký tự")
        turns.append({"n": len(turns) + 1, "speaker": speaker, "text": text,
                      "norm": normalize(text.replace("₂", "2")).text})
        if len(turns) > MAX_TURNS:
            raise ValueError(f"Transcript nhiều quá {MAX_TURNS} lượt nói")
    if not turns:
        raise ValueError("Transcript trống: chưa có lượt nói nào")
    return turns


def sentences(turns: list[dict], key: str = "norm"):
    for t in turns:
        for s in re.split(r"(?<=[.;!?])\s+|\n+", t[key]):
            s = s.strip().rstrip(".;").strip()
            if s and not s.endswith("?"):  # câu hỏi không phải thông tin bàn giao
                yield t["n"], s


def clauses(s: str, split_and: bool = True) -> list[str]:
    pat = r",\s+(?=\D)|;\s*" + (r"|\s+và\s+|\s+va\s+" if split_and else "")
    return [c.strip(" .;:") for c in re.split(pat, s) if c.strip(" .;:")]


# ---------------------------------------------------------------- quy tắc cho từng trường (dùng cả để kiểm chứng)
@dataclass
class Hit:
    value: str
    note: str = ""
    uncertain: bool = False


def cap_words(orig: str, start: int, lo: int = 2, hi: int = 5) -> str | None:
    words = []
    for m in re.finditer(r"\S+", orig[start:]):
        w = m.group(0)
        core = w.rstrip(",.;:!?)")
        if not core or not core[0].isupper() or not all(ch.isalpha() or ch in "-'" for ch in core):
            break
        words.append(core)
        if core != w or len(words) >= hi:
            break
    return " ".join(words) if len(words) >= lo else None


HONORIFIC = r"(?:cu ong|cu ba|ong|ba|anh|chi|co|chu|bac|em)"
NAME_LEAD = re.compile(rf"\b(?:benh nhan|nguoi benh|bn|ho va ten|ho ten|ten)\s*(?:(?:ten|la|:)\s*)*(?:{HONORIFIC}\s+)?")


def p_name(s: str) -> list[Hit]:
    f, out = fold1(s), []
    for m in NAME_LEAD.finditer(f):
        v = cap_words(s, m.end())
        if v:
            out.append(Hit(v))
    for m in re.finditer(r"(?:^|[,:]\s*|\blà\s+)(cụ ông|cụ bà|ông|bà|anh|chị|cô|chú|bác)\s+(?=[^\W\d_])", s.lower()):
        v = cap_words(s, m.end())
        if v and not any(h.value == v for h in out):
            out.append(Hit(v))
    if not out:  # trích dẫn chỉ gồm tên (LLM)
        v = cap_words(s, 0)
        if v and len(v) == len(s.strip(" ,.")):
            out.append(Hit(v))
    return out


MALE, FEMALE = {"ông", "anh", "chú", "cụ ông", "bác trai"}, {"bà", "chị", "cô", "cụ bà", "bác gái"}


def p_gender(s: str) -> list[Hit]:
    low, f, out = s.lower(), fold1(s), []
    for m in re.finditer(r"\bgioi tinh\s*(?:la|:)?\s*(nam|nu)\b", f):
        word = low[m.start(1):m.end(1)]
        if word in ("nam", "nữ", "nu"):
            out.append(Hit("Nam" if word == "nam" else "Nữ"))
    for m in re.finditer(r"(?:^|[,(:]\s*|\b(?:bệnh nhân|người bệnh|bn)\s+(?:là\s+)?)(nam|nữ)\b(?=\s*(?:[,.;)]|$|\d|sinh|tuổi))", low):
        out.append(Hit("Nam" if m.group(1) == "nam" else "Nữ"))
    for m in re.finditer(r"(?:^|\b(?:bệnh nhân|người bệnh|bn|là)\s+)(cụ ông|cụ bà|bác trai|bác gái|ông|bà|anh|chị|cô|chú)\s+(?=[^\W\d_])", low):
        if s[m.end():m.end() + 1].isupper():
            g = "Nam" if m.group(1) in MALE else "Nữ"
            out.append(Hit(g, f"Suy ra từ cách xưng hô “{m.group(1)}”", uncertain=True))
    return out


def p_birth_year(s: str) -> list[Hit]:
    f, out, y0 = fold1(s), [], today().year
    for m in re.finditer(r"\bsinh\s*(?:nam)?\s*(?:la|:)?\s*(\d{4})\b", f):
        out.append(Hit(m.group(1)))
    for m in re.finditer(r"\bsinh\s*(?:nam)?\s*(\d{2})\b(?!\s*(?:tuoi|ngay|thang|\d))", f):
        yy = int(m.group(1))
        out.append(Hit(str(2000 + yy if 2000 + yy <= y0 else 1900 + yy), f"Năm sinh nói tắt “{m.group(1)}”", uncertain=True))
    for m in re.finditer(r"\b(\d{1,3})\s*tuoi\b", f):
        age = int(m.group(1))
        if 0 < age < 120:
            out.append(Hit(str(y0 - age), f"Tính từ tuổi ({age}), có thể lệch 1 năm", uncertain=True))
    return out


def p_ward(s: str) -> list[Hit]:
    f, out = fold1(s), []
    for m in re.finditer(r"\bkhoa\s+(.+?)(?=\s*(?:,|\.|;|$|\bbuong\b|\bphong\b|\bgiuong\b|\bluc\b|\bvao\b|\bngay\b|\btu\b))", f):
        before = f[max(0, m.start() - 6):m.start()]
        if re.search(r"\b(?:tu|chuyen)\s*$", before):  # "chuyển từ khoa X", "chuyên khoa"
            continue
        words = s[m.start(1):m.end(1)].split()
        if 1 <= len(words) <= 5:
            out.append(Hit("Khoa " + " ".join(words)))
    return out


def _numbered(pattern: str):
    def p(s: str) -> list[Hit]:
        return [Hit(m.group(1).upper()) for m in re.finditer(pattern, fold1(s))]
    return p


p_room = _numbered(r"\b(?:buong|phong)\s*(?:so\s*)?(\d{1,4}[a-z]?)\b")
p_bed = _numbered(r"\bgiuong\s*(?:so\s*)?(\d{1,4}[a-z]?)\b")


def p_attending(s: str) -> list[Hit]:
    f, out = fold1(s), []
    for m in re.finditer(r"\b(?:bac si|bs)\.?\s+(?:dieu tri|phu trach)\s*(?:la|:)?\s*(?:(?:bac si|bs)\.?\s+)?", f):
        v = cap_words(s, m.end(), lo=1, hi=4)
        if v:
            out.append(Hit(v))
    for m in re.finditer(r"\b(?:bac si|bs)\.?\s+(?=[^\W\d_])", f):
        v = cap_words(s, m.end(), lo=1, hi=4)
        if v and re.match(r"\s+(?:nhan|dieu tri|phu trach)\b", f[m.end() + len(v):]):
            out.append(Hit(v))
    return out


ADMIT = re.compile(r"\b(?:vao vien|nhap vien|vao khoa|vao cap cuu|chuyen len|tiep nhan)\b")
REL_DAY = {"hom nay": 0, "sang nay": 0, "trua nay": 0, "chieu nay": 0, "toi nay": 0, "dem nay": 0,
           "hom qua": -1, "dem qua": -1, "toi qua": -1, "chieu qua": -1, "sang qua": -1}


def p_date(s: str) -> list[Hit]:
    f, out, t = fold1(s), [], today()
    pats = [r"\b(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{4}))?\b", r"\bngay\s*(\d{1,2})\s*thang\s*(\d{1,2})(?:\s*(?:nam\s*)?(\d{4}))?"]
    for pat in pats:
        for m in re.finditer(pat, f):
            d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
            if not y and re.search(r"\b(?:huyet ap|ha)\s*(?:la|:)?\s*$", f[:m.start()]):
                continue  # 150/90 là huyết áp
            try:
                v = date(int(y) if y else t.year, mo, d)
            except ValueError:
                continue
            out.append(Hit(v.isoformat(), "" if y else "Năm suy ra theo năm hiện tại"))
    for k, off in REL_DAY.items():
        if re.search(rf"\b{k}\b", f):
            out.append(Hit((t + timedelta(days=off)).isoformat(), f"Suy ra từ “{k}”"))
    return out


def p_time(s: str) -> list[Hit]:
    f, out = fold1(s), []
    for m in re.finditer(r"\b(\d{1,2})\s*(?:gio|h|:)\s*(ruoi|\d{1,2})?\s*(?:phut)?\s*(sang|trua|chieu|toi|dem)?\b", f):
        h = int(m.group(1))
        mi = 30 if m.group(2) == "ruoi" else int(m.group(2) or 0)
        part = m.group(3) or next((k.split()[0] for k in REL_DAY if re.search(rf"\b{k}\b", f)), None)
        if part in ("chieu", "toi") and h < 12:
            h += 12
        if part == "dem" and 7 <= h < 12:
            h += 12
        if h < 24 and mi < 60:
            out.append(Hit(f"{h:02d}:{mi:02d}"))
    return out


def p_reason(s: str) -> list[Hit]:
    f, out = fold1(s), []
    for pat in (r"\b(?:vao vien|nhap vien|vao khoa|vao cap cuu|chuyen len)\b[^.;]*?\b(?:voi ly do|ly do la|ly do|vi|do)\s+",
                r"\bly do (?:vao vien|nhap vien)\s*(?:la|:)?\s*"):
        for m in re.finditer(pat, f):
            rest = s[m.end():]
            cut = re.search(r"\s+(?:lúc|luc|vào lúc|vao luc)\s+\d|\s*,\s*(?:vào|vao)\s+(?:khoa|viện|vien)", rest)
            v = (rest[:cut.start()] if cut else rest).strip(" ,.;")
            if len(v) >= 3:
                out.append(Hit(v[0].upper() + v[1:]))
    return out


def _vital(pattern: str, build):
    def p(s: str) -> list[Hit]:
        return [Hit(v) for m in re.finditer(pattern, fold1(s)) if (v := build(m))]
    return p


NOT_DURATION = r"(?!\s*(?:ngay|hom|tuan|thang|nam|gio|lit|l/p|l\b))"
# Tối đa 4 từ đệm không phải số, trong cùng mệnh đề: "mạch là 96", "mạch lúc nãy em đo 120", "nặng khoảng 60 kg"
LINK = r"\s*:?(?:\s+[^\d\s,.;:/]+){0,4}?\s*"
p_pulse = _vital(rf"\b(?:mach|nhip tim|tan so tim){LINK}(\d{{2,3}})\b{NOT_DURATION}", lambda m: m.group(1))
p_temp = _vital(rf"\b(?:nhiet do|than nhiet|nhiet|sot){LINK}(\d{{2}})(?:[.,](\d))?(?:\s*do(?:\s+(\d)\b)?)?{NOT_DURATION}",
                lambda m: _canon(f"{m.group(1)}.{m.group(2) or m.group(3) or 0}"))
p_bp = _vital(rf"\b(?:huyet ap|ha){LINK}(\d{{2,3}})\s*/\s*(\d{{2,3}})\b", lambda m: f"{m.group(1)}/{m.group(2)}")
p_resp = _vital(rf"\b(?:nhip tho|tan so tho|tho){LINK}(\d{{1,2}})\b{NOT_DURATION}", lambda m: m.group(1))
p_spo2 = _vital(rf"\b(?:spo2|sp02|spo 2|sao2|do bao hoa(?: oxy)?|bao hoa oxy){LINK}(\d{{2,3}})\b", lambda m: m.group(1))
p_weight = _vital(rf"\b(?:can nang|nang){LINK}(\d{{1,3}}(?:[.,]\d)?)\s*(?:kg|ky|kilo|can)\b", lambda m: _canon(m.group(1).replace(",", ".")))

PARSERS = {"name": p_name, "birth_year": p_birth_year, "gender": p_gender, "ward": p_ward, "room": p_room, "bed": p_bed,
           "attending_spoken": p_attending, "admitted_date": p_date, "admitted_time": p_time, "reason": p_reason,
           "pulse": p_pulse, "temp": p_temp, "bp": p_bp, "resp_rate": p_resp, "spo2": p_spo2, "weight": p_weight}
# Các trường này kiểm chứng bằng cách chạy lại quy tắc trên trích dẫn; còn lại kiểm chứng theo từ ngữ.
STRUCTURED = {"birth_year", "gender", "room", "bed", "admitted_date", "admitted_time", "pulse", "temp", "bp", "resp_rate", "spo2", "weight"}
ADMIT_ONLY = {"admitted_date", "admitted_time"}  # chế độ quy tắc chỉ lấy ngày giờ trong câu nói về nhập viện
TEXT_ONLY = {"name", "attending_spoken"}

ALLERGY_NONE = re.compile(r"\b(?:khong|chua ghi nhan|khong ghi nhan|chua phat hien|phu nhan)\s+(?:co\s+)?(?:tien su\s+)?di ung\b")
ALLERGY_UNKNOWN = re.compile(r"\b(?:chua ro|khong ro|chua hoi duoc|chua khai thac duoc|chua khai thac)\s+(?:(?:tien su|co)\s+)?di ung\b")
ALLERGY_LEAD = re.compile(r"\bdi ung\s*(?:voi|thuoc)?\s*(?:la|:)?\s*")
DX_LEAD = re.compile(r"\bchan doan(?:\s+(?:ban dau|so bo|vao vien|tai cap cuu|cap cuu|luc vao|hien tai|tuyen truoc))?\s*(?:la|:)?\s*")
THINK_LEAD = re.compile(r"\bnghi (?:nhieu\s+)?(?:den|toi)?\s*")
COMORB_LEAD = re.compile(r"\b(?:tien su|tien can|benh nen|co benh)\s*(?:benh\s+)?(?:la|gom|co|:)?\s*")
LAB_RE = re.compile(r"\b(?:xet nghiem|x-quang|x quang|xquang|ct|chup|cat lop|sieu am|dien tim|ecg|troponin|bach cau|crp|kali|natri|"
                    r"creatinin|ure|glucose|duong mau|hba1c|hemoglobin|hb|tieu cau|men gan|ast|alt|bnp|d-dimer|khi mau|cay mau|"
                    r"cay dom|egfr|procalcitonin|lactat|inr|nuoc tieu)\b")
PENDING_RE = re.compile(r"\b(?:chờ|đợi|cần theo dõi|theo dõi sát|theo dõi tiếp|hẹn|chưa có kết quả|cần làm|cần hội chẩn|dặn|lưu ý|"
                        r"cần lấy|cần kiểm tra|cần đánh giá|kế hoạch|cần xin|cần chuyển)\b", re.I)
PENDING_FOLD = re.compile(r"\b(?:can theo doi|theo doi sat|theo doi tiep|chua co ket qua|can lam|can hoi chan|luu y|can lay|can kiem tra|"
                          r"can danh gia|ke hoach|dang cho|cho ket qua)\b")
MED_TRIGGER = re.compile(r"\b(?:dang dung|dang uong|thuoc|ke|tiem|truyen|duy tri)\b")
DOSE_RE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:mg|mcg|g|ml|ui|don vi)\b")
MED_LEAD = re.compile(r"^(?:(?:dang|van|da)\s+)?(?:dung|uong|tiem|truyen|duy tri)\s+|^thuoc(?:\s+(?:dang dung|nha|gom))?\s*:?\s*|^(?:gom|co)\s+")


def p_allergy_status(s: str) -> list[Hit]:
    f = fold1(s)
    if ALLERGY_NONE.search(f):
        return [Hit("none")]
    if ALLERGY_UNKNOWN.search(f):
        return [Hit("unknown", "Chưa khai thác được tiền sử dị ứng", uncertain=True)]
    if ALLERGY_LEAD.search(f) and len(s[ALLERGY_LEAD.search(f).end():].strip()) >= 2:
        return [Hit("has")]
    return []


PARSERS["allergy_status"] = p_allergy_status
STRUCTURED.add("allergy_status")


# ---------------------------------------------------------------- bản nháp
@dataclass
class Cand:
    value: str
    turns: list[int]
    quote: str
    source: str = "quy tắc"
    notes: list[str] = field(default_factory=list)
    uncertain: bool = False


Status = Literal["ok", "uncertain", "conflict", "missing"]


class Alternative(BaseModel):
    value: str
    turns: list[int]


class FieldDraft(BaseModel):
    value: str | None = None
    turns: list[int] = Field(default_factory=list)
    status: Status = "missing"
    notes: list[str] = Field(default_factory=list)
    alternatives: list[Alternative] = Field(default_factory=list)


class ItemDraft(BaseModel):
    text: str
    turns: list[int]
    status: Status = "ok"
    notes: list[str] = Field(default_factory=list)


class HandoffDraft(BaseModel):
    mode: Literal["llm", "offline"]
    turns: list[dict]
    fields: dict[str, FieldDraft]
    lists: dict[str, list[ItemDraft]]
    allergy_status: FieldDraft
    required: list[str]
    missing_required: list[str]
    flag_count: int
    dropped: list[dict]
    warnings: list[str]
    labels: dict[str, str]
    disclaimer: str


def _item_text(raw: str) -> str:
    t = raw.strip(" ,.;:-")
    return t[0].upper() + t[1:] if t else t


def extract_offline(turns: list[dict]) -> tuple[dict[str, list[Cand]], dict[str, list[Cand]]]:
    fields: dict[str, list[Cand]] = {k: [] for k in (*FIELD_KEYS, "allergy_status")}
    lists: dict[str, list[Cand]] = {k: [] for k in LIST_KEYS}
    for n, s in sentences(turns, "text"):  # tên người lấy từ văn bản gốc: "Lê Văn Tám" không được thành "Lê Văn 8"
        for key in TEXT_ONLY:
            fields[key] += [Cand(h.value, [n], s) for h in PARSERS[key](s)]
    for n, s in sentences(turns):
        f = fold1(s)
        for key, parse in PARSERS.items():
            if key in TEXT_ONLY or (key in ADMIT_ONLY and not ADMIT.search(f)):
                continue
            for h in parse(s):
                fields[key].append(Cand(h.value, [n], s, notes=[h.note] if h.note else [], uncertain=h.uncertain))

        if (m := DX_LEAD.search(f)) or (m := THINK_LEAD.search(f)):
            think = not DX_LEAD.search(f)
            for c in clauses(s[m.end():]):
                unsure = think or bool(re.match(r"(?:theo doi|nghi|td)\b", fold1(c)))
                lists["diagnoses"].append(Cand(_item_text(c), [n], c, uncertain=unsure,
                                               notes=["Lời bàn giao chỉ nêu nghi ngờ / theo dõi"] if unsure else []))
            continue
        if ALLERGY_NONE.search(f) or ALLERGY_UNKNOWN.search(f):
            continue
        if m := ALLERGY_LEAD.search(f):
            for c in re.split(r"\s+(?:và|va)\s+|;\s*", s[m.end():]):
                if len(c.strip(" ,.")) >= 2:
                    lists["allergies"].append(Cand(_item_text(c), [n], c))
            continue  # tình trạng "có dị ứng" đã do p_allergy_status lấy từ cả câu
        if m := COMORB_LEAD.search(f):
            for c in clauses(s[m.end():]):
                lists["comorbidities"].append(Cand(_item_text(c), [n], c))
            continue
        trigger = bool(MED_TRIGGER.search(f))
        for c in clauses(s, split_and=False):  # "theo dõi SpO2 và nước tiểu" là một việc
            fc = fold1(c)
            if PENDING_RE.search(c) or PENDING_FOLD.search(fc):
                lists["pending"].append(Cand(_item_text(c), [n], c))
            elif KB.drugs_mentioned(c):
                lists["meds"].append(Cand(_item_text(c[MED_LEAD.match(fc).end():] if MED_LEAD.match(fc) else c), [n], c))
            elif trigger and DOSE_RE.search(fc):
                lists["meds"].append(Cand(_item_text(c[MED_LEAD.match(fc).end():] if MED_LEAD.match(fc) else c), [n], c,
                                          uncertain=True, notes=["Không có trong danh mục thuốc của hệ thống"]))
            elif LAB_RE.search(fc):
                lists["labs"].append(Cand(_item_text(c), [n], c))
    return fields, lists


# ---------------------------------------------------------------- kiểm chứng
def canon_value(key: str, v: str) -> str:
    v = str(v).strip()
    if key in ("pulse", "temp", "resp_rate", "spo2", "weight", "birth_year"):
        return _canon(v.replace(",", "."))
    if key == "admitted_time" and re.fullmatch(r"\d{1,2}:\d{2}", v):
        h, m = v.split(":")
        return f"{int(h):02d}:{m}"
    if key in TEXT_ONLY:  # giữ dấu: "Tám" và "Tâm" là hai người khác nhau
        return re.sub(r"\s+", " ", unicodedata.normalize("NFC", v).lower()).strip(" .,")
    return squash(v)


def ground(key: str, c: Cand, tmap: dict[int, dict]) -> str | None:
    """None nếu giá trị có căn cứ trong transcript; ngược lại là lý do bị loại."""
    if not c.turns or any(n not in tmap for n in c.turns):
        return "dẫn chứng tới lượt nói không tồn tại"
    q = squash(c.quote)
    if not q:
        return "thiếu trích dẫn nguyên văn"
    texts = [squash(tmap[n][k]) for n in c.turns for k in ("norm", "text")]
    if not any(q in t for t in texts) and q not in squash(" ".join(tmap[n]["norm"] for n in c.turns)):
        return "trích dẫn không có trong transcript"
    if key in STRUCTURED:
        if canon_value(key, c.value) not in {canon_value(key, h.value) for h in PARSERS[key](c.quote)}:
            return "giá trị không suy ra được từ trích dẫn"
        return None
    if key in TEXT_ONLY and canon_value(key, c.value) not in canon_value(key, c.quote):
        return "tên không có nguyên văn (kể cả dấu) trong lời bàn giao"
    vt, qt = toks(c.value), set(toks(c.quote))
    if not vt:
        return "giá trị rỗng"
    miss = [t for t in vt if t not in qt]
    if (key == "name" and miss) or len(miss) > len(vt) // 5:
        return "có từ không xuất hiện trong lời bàn giao: " + ", ".join(miss[:5])
    if {_canon(x) for x in numbers_in(c.value)} - {_canon(x) for x in numbers_in(c.quote)}:
        return "con số không có trong lời bàn giao"
    if key in ("meds", "diagnoses", "labs", "allergies", "comorbidities", "pending") and \
            set(KB.drugs_mentioned(c.value)) - set(KB.drugs_mentioned(c.quote)):
        return "tên thuốc không có trong lời bàn giao"
    return None


def resolve_field(key: str, cands: list[Cand]) -> FieldDraft:
    if not cands:
        return FieldDraft()
    if key == "birth_year":  # năm sinh nói rõ thắng năm tính từ tuổi nếu lệch tối đa 1
        exact = [c for c in cands if not c.uncertain]
        if exact:
            cands = exact + [c for c in cands if c.uncertain and all(abs(int(c.value) - int(e.value)) > 1 for e in exact)]
    groups: dict[str, list[Cand]] = {}
    for c in cands:
        groups.setdefault(canon_value(key, c.value), []).append(c)
    latest = max(cands, key=lambda c: max(c.turns))
    turns = sorted({n for c in cands for n in c.turns})
    notes = sorted({x for c in cands for x in c.notes})
    for c in cands:
        words = uncertain_words(c.quote)
        if words and key != "attending_spoken":
            notes.append("Lời bàn giao có từ không chắc chắn: " + ", ".join(f"“{w}”" for w in words))
    if len(groups) > 1:
        alts = [Alternative(value=g[0].value, turns=sorted({n for c in g for n in c.turns})) for g in groups.values()]
        return FieldDraft(value=latest.value, turns=turns, status="conflict", alternatives=alts,
                          notes=sorted(set(notes)) + ["Các lượt nói đưa ra giá trị khác nhau; hiện điền giá trị nói sau cùng"])
    value = cands[0].value
    status: Status = "uncertain" if any(c.uncertain for c in cands) or any(uncertain_words(c.quote) for c in cands) else "ok"
    if key in VITAL_RANGE:
        lo, hi = VITAL_RANGE[key]
        if not lo <= float(value) <= hi:
            status, notes = "uncertain", notes + [f"Ngoài khoảng thường gặp ({lo}–{hi}), kiểm tra lại"]
    if key == "bp":
        sys_, dia = map(int, value.split("/"))
        if not (60 <= sys_ <= 260 and 30 <= dia <= 160 and dia < sys_):
            status, notes = "uncertain", notes + ["Huyết áp không hợp lý, kiểm tra lại"]
    if key == "birth_year" and not 1900 <= int(value) <= today().year:
        status, notes = "uncertain", notes + ["Năm sinh không hợp lý"]
    return FieldDraft(value=value, turns=turns, status=status, notes=sorted(set(notes)))


def resolve_list(cands: list[Cand]) -> list[ItemDraft]:
    out: list[ItemDraft] = []
    seen: list[set[str]] = []
    for c in cands:
        t = set(toks(c.value))
        dup = next((i for i, s in enumerate(seen) if t and (t <= s or s <= t)), None)
        unsure = c.uncertain or bool(uncertain_words(c.value))
        notes = list(c.notes) + (["Lời bàn giao có từ không chắc chắn"] if uncertain_words(c.value) and not c.notes else [])
        if dup is not None:
            item = out[dup]
            item.turns = sorted(set(item.turns) | set(c.turns))
            continue
        seen.append(t)
        out.append(ItemDraft(text=c.value, turns=c.turns, status="uncertain" if unsure else "ok", notes=notes))
    return out


# ---------------------------------------------------------------- LLM (tùy chọn)
FieldKey = Literal[FIELD_KEYS]  # type: ignore[valid-type]
ListKey = Literal[LIST_KEYS]  # type: ignore[valid-type]


class LLMCand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(min_length=1, max_length=300)
    quote: str = Field(min_length=1, max_length=500)
    turn: int = Field(ge=1, le=MAX_TURNS)


class LLMOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: dict[FieldKey, list[LLMCand]] = Field(default_factory=dict)
    lists: dict[ListKey, list[LLMCand]] = Field(default_factory=dict)
    allergy_status: list[LLMCand] = Field(default_factory=list)


LLM_SYSTEM = f"""Bạn trích xuất thông tin bàn giao người bệnh từ transcript tiếng Việt.
Chỉ lấy điều được nói rõ trong transcript. Không suy luận, không thêm chẩn đoán, thuốc, xét nghiệm hay con số không được nói.
Mỗi giá trị kèm "quote" là đoạn chép NGUYÊN VĂN từ trường "text" của đúng một lượt nói, và "turn" là số "n" của lượt đó.
Không có thông tin thì để mảng rỗng. Nếu các lượt nói mâu thuẫn, liệt kê tất cả giá trị.
Định dạng: birth_year 4 chữ số; gender "Nam" hoặc "Nữ"; admitted_date YYYY-MM-DD; admitted_time HH:MM (24 giờ);
bp "160/90"; số thập phân dùng dấu chấm; allergy_status "has" | "none" | "unknown".
Trả về đúng JSON, không thêm khóa khác:
{{"fields": {{{", ".join(f'"{k}": []' for k in FIELD_KEYS)}}},
 "lists": {{{", ".join(f'"{k}": []' for k in LIST_KEYS)}}},
 "allergy_status": []}}
Mỗi phần tử: {{"value": "...", "quote": "...", "turn": 3}}"""


def extract_llm(turns: list[dict]) -> LLMOut | None:
    payload = json.dumps({"today": today().isoformat(),
                          "turns": [{"n": t["n"], "speaker": t["speaker"], "text": t["norm"]} for t in turns]}, ensure_ascii=False)
    out = llm.complete_json(LLM_SYSTEM, payload)
    if out is None:
        return None
    return LLMOut.model_validate(out)  # sai cấu trúc -> ValidationError, phía gọi rơi về quy tắc


def build_draft(turns: list[dict], use_llm: bool = True) -> HandoffDraft:
    tmap = {t["n"]: t for t in turns}
    fields, lists = extract_offline(turns)
    mode: Literal["llm", "offline"] = "offline"
    warnings: list[str] = []
    if use_llm and llm.available():
        try:
            got = extract_llm(turns)
        except ValidationError as e:
            got = None
            warnings.append(f"LLM trả về sai cấu trúc ({e.error_count()} lỗi); dùng chế độ quy tắc.")
        if got is not None:
            mode = "llm"
            for k, cs in got.fields.items():
                fields[k] = [Cand(c.value, [c.turn], c.quote, "LLM") for c in cs] + fields[k]
            for k, cs in got.lists.items():
                lists[k] = [Cand(c.value, [c.turn], c.quote, "LLM") for c in cs] + lists[k]
            fields["allergy_status"] = [Cand(c.value, [c.turn], c.quote, "LLM") for c in got.allergy_status] + fields["allergy_status"]
        elif not warnings:
            warnings.append("Không gọi được LLM; dùng chế độ quy tắc.")

    dropped: list[dict] = []

    def keep(key: str, cs: list[Cand]) -> list[Cand]:
        ok = []
        for c in cs:
            why = ground(key, c, tmap)
            if why:
                dropped.append({"field": LABELS.get(key, key), "value": c.value, "source": c.source, "reason": why})
            else:
                ok.append(c)
        return ok

    fdraft = {k: resolve_field(k, keep(k, fields[k])) for k in FIELD_KEYS}
    ldraft = {k: resolve_list(keep(k, lists[k])) for k in LIST_KEYS}
    allergy = resolve_field("allergy_status", keep("allergy_status", fields["allergy_status"]))
    if allergy.status == "conflict":
        allergy.notes.append("Có lượt nói nêu dị ứng và có lượt nói phủ nhận dị ứng; cần hỏi lại người bệnh")
    if allergy.status == "missing":
        allergy.notes.append("Lời bàn giao chưa nhắc tới dị ứng")
    if fdraft["attending_spoken"].value:
        fdraft["attending_spoken"].notes.append("Chỉ để tham khảo: hệ thống không phân công theo tên nghe được trong bàn giao")
    missing = [k for k in REQUIRED if fdraft[k].status == "missing"]
    flags = sum(f.status in ("uncertain", "conflict") for k, f in fdraft.items() if k != "attending_spoken") \
        + sum(i.status != "ok" for items in ldraft.values() for i in items) + (allergy.status in ("uncertain", "conflict"))
    return HandoffDraft(mode=mode, turns=turns, fields=fdraft, lists=ldraft, allergy_status=allergy, required=list(REQUIRED),
                        missing_required=missing, flag_count=flags, dropped=dropped, warnings=warnings, labels=LABELS,
                        disclaimer=DISCLAIMER)


def parse(raw: str) -> HandoffDraft:
    return build_draft(parse_turns(raw))


# ---------------------------------------------------------------- xác nhận & tạo hồ sơ
Item = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)+$")
CODE_RE = r"^[0-9A-Za-z\-]{1,10}$"


class VitalsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pulse: int | None = Field(None, ge=20, le=250)
    temp: float | None = Field(None, ge=30, le=45)
    bp: str | None = Field(None, pattern=r"^\d{2,3}/\d{2,3}$")
    resp_rate: int | None = Field(None, ge=4, le=80)
    spo2: int | None = Field(None, ge=50, le=100)
    weight: float | None = Field(None, gt=0, le=350)

    @field_validator("bp")
    @classmethod
    def _bp(cls, v):
        if v is not None:
            s, d = map(int, v.split("/"))
            if not (50 <= s <= 300 and 20 <= d <= 200 and d < s):
                raise ValueError("huyết áp không hợp lệ (tâm thu phải lớn hơn tâm trương)")
        return v


class HandoffConfirm(BaseModel):
    """Dữ liệu cuối do bác sĩ / quản trị xác nhận. extra=forbid: client không gửi được patient_id hay attending."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    transcript_text: str = Field(min_length=1, max_length=MAX_CHARS)
    name: str = Field(min_length=3, max_length=80)
    birth_year: int
    gender: Literal["Nam", "Nữ"]
    ward: str = Field(min_length=2, max_length=80)
    room: str = Field(pattern=CODE_RE)
    bed: str = Field(pattern=CODE_RE)
    admitted_at: datetime
    reason: str = Field(min_length=3, max_length=500)
    vitals: VitalsIn = Field(default_factory=VitalsIn)
    diagnoses: list[Item] = Field(default_factory=list, max_length=30)
    comorbidities: list[Item] = Field(default_factory=list, max_length=30)
    allergies: list[Item] = Field(default_factory=list, max_length=30)
    allergy_status: Literal["has", "none", "unknown"]
    meds: list[Item] = Field(default_factory=list, max_length=40)
    labs: list[Item] = Field(default_factory=list, max_length=40)
    pending: list[Item] = Field(default_factory=list, max_length=40)
    acknowledged_warnings: bool = False

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        if not NAME_RE.match(v):
            raise ValueError("họ tên chỉ gồm chữ, ít nhất 2 từ")
        return v

    @field_validator("birth_year")
    @classmethod
    def _by(cls, v):
        if not 1900 <= v <= today().year:
            raise ValueError(f"năm sinh phải trong khoảng 1900–{today().year}")
        return v

    @field_validator("admitted_at")
    @classmethod
    def _at(cls, v: datetime):
        if v.tzinfo is not None:
            raise ValueError("gửi giờ địa phương, không kèm múi giờ")
        if v > datetime.now() + timedelta(minutes=15):
            raise ValueError("thời điểm vào viện ở tương lai")
        return v

    @model_validator(mode="after")
    def _cross(self):
        texts = [self.name, self.ward, self.reason, *self.diagnoses, *self.comorbidities, *self.allergies, *self.meds,
                 *self.labs, *self.pending]
        if any(CTRL.search(t) for t in texts):
            raise ValueError("có ký tự điều khiển không hợp lệ")
        if self.admitted_at.year < self.birth_year:
            raise ValueError("thời điểm vào viện trước năm sinh")
        if self.allergy_status == "has" and not self.allergies:
            raise ValueError("đã chọn có dị ứng nhưng chưa ghi dị nguyên")
        if self.allergy_status != "has" and self.allergies:
            raise ValueError("có ghi dị nguyên nhưng tình trạng dị ứng không phải 'có dị ứng'")
        return self


class InvalidHandoff(ValueError):
    """Lỗi hiển thị cho người dùng; `audit` là bản rút gọn không chứa nội dung lâm sàng."""

    def __init__(self, message: str, audit: str):
        super().__init__(message)
        self.audit = audit


VI_ERRORS = {
    "missing": "còn thiếu", "string_too_short": "không được để trống / quá ngắn", "string_too_long": "dài quá giới hạn",
    "string_pattern_mismatch": "sai định dạng", "string_type": "phải là văn bản", "int_parsing": "phải là số nguyên",
    "int_type": "phải là số nguyên", "float_parsing": "phải là số", "int_from_float": "phải là số nguyên",
    "greater_than_equal": "nhỏ hơn mức cho phép", "less_than_equal": "lớn hơn mức cho phép", "greater_than": "phải lớn hơn",
    "less_than": "phải nhỏ hơn", "literal_error": "giá trị không hợp lệ", "datetime_parsing": "sai định dạng ngày giờ",
    "datetime_from_date_parsing": "sai định dạng ngày giờ", "datetime_type": "sai định dạng ngày giờ",
    "list_type": "phải là danh sách", "too_long": "quá nhiều mục", "bool_parsing": "phải là đúng/sai", "model_type": "sai cấu trúc",
}


def _validation_message(e: ValidationError) -> tuple[str, str]:
    parts, keys = [], []
    for err in e.errors():
        loc = [str(x) for x in err["loc"] if not isinstance(x, int)]
        key = loc[-1] if loc else "dữ liệu"
        keys.append(key)
        if err["type"] == "extra_forbidden":
            parts.append(f"Không được gửi trường “{key}” (mã hồ sơ và bác sĩ phụ trách do hệ thống quyết định)")
        else:
            msg = VI_ERRORS.get(err["type"], err["msg"].removeprefix("Value error, "))
            if err["type"] in ("greater_than_equal", "less_than_equal", "greater_than", "less_than"):
                msg += f" ({next(iter(err.get('ctx', {}).values()), '')})"
            parts.append(f"{LABELS.get(key, key)}: {msg}")
    return "Dữ liệu chưa hợp lệ. " + "; ".join(parts[:8]), "trường lỗi: " + ", ".join(sorted(set(keys)))


_LOCK = threading.Lock()


def _next_number() -> int:
    nums = []
    for d in (KB.DATA / "patients", KB.DATA / "gold", KB.RUNTIME_PATIENTS):
        if d.exists():
            nums += [int(m.group(1)) for p in d.glob("p*") if (m := re.match(r"p(\d+)\.", p.name))]
    return max(nums, default=0) + 1


def _reserve_pid() -> tuple[str, "os.PathLike"]:
    """Giữ chỗ patient_id bằng file .lock tạo độc quyền (mode 'x'): hai yêu cầu song song không lấy trùng mã."""
    KB.RUNTIME_PATIENTS.mkdir(parents=True, exist_ok=True)
    n = _next_number()
    for _ in range(1000):
        pid = f"p{n:03d}"
        lock = KB.RUNTIME_PATIENTS / f"{pid}.lock"
        if KB.load_patient(pid) is None:
            try:
                with open(lock, "x", encoding="utf-8") as fh:
                    fh.write(datetime.now().isoformat())
                if KB.load_patient(pid) is None:
                    return pid, lock
                lock.unlink(missing_ok=True)
            except FileExistsError:
                pass
        n += 1
    raise RuntimeError("Không cấp được mã hồ sơ mới")


def _write_new(path, data: dict) -> None:
    """Ghi file mới, không bao giờ ghi đè: ghi ra file tạm rồi đổi tên, kiểm tra trước khi đổi."""
    tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex[:6]}.tmp")
    with open(tmp, "x", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    if path.exists():
        tmp.unlink(missing_ok=True)
        raise FileExistsError(path.name)
    os.replace(tmp, path)


def confirm(body: dict, user: dict) -> dict:
    try:
        data = HandoffConfirm.model_validate(body)
    except ValidationError as e:
        msg, audit = _validation_message(e)
        raise InvalidHandoff(msg, audit) from None
    try:
        turns = parse_turns(data.transcript_text)
    except ValueError as e:
        raise InvalidHandoff(str(e), "transcript không hợp lệ") from None
    check = build_draft(turns, use_llm=False)  # quy tắc cố định chạy lại phía server, không tin cờ do client gửi
    if check.flag_count and not data.acknowledged_warnings:
        raise InvalidHandoff(f"Bản bàn giao còn {check.flag_count} mục mâu thuẫn hoặc không chắc chắn. "
                             "Cần xác nhận đã kiểm tra trước khi tiếp nhận.", f"chưa xác nhận {check.flag_count} cảnh báo")

    now = datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        pid, lock = _reserve_pid()
        try:
            tid = f"TS-BG-{pid}-{uuid.uuid4().hex[:6]}"
            KB.RUNTIME_TS.mkdir(parents=True, exist_ok=True)
            transcript = {"id": tid, "patient_id": pid, "date": data.admitted_at.isoformat(timespec="minutes"), "kind": "handoff",
                          "turns": [{"n": t["n"], "speaker": t["speaker"], "text": t["text"]} for t in turns],
                          "_note": "Transcript bàn giao do người dùng nhập (dữ liệu giả lập)"}
            record = _patient_record(pid, tid, data, user, now, check)
            _write_new(KB.RUNTIME_TS / f"{tid}.json", transcript)
            try:
                _write_new(KB.RUNTIME_PATIENTS / f"{pid}.json", record)
            except Exception:
                (KB.RUNTIME_TS / f"{tid}.json").unlink(missing_ok=True)
                raise
        finally:
            lock.unlink(missing_ok=True)
    return {"patient_id": pid, "transcript_id": tid}


def _patient_record(pid: str, tid: str, d: HandoffConfirm, user: dict, now: str, check: HandoffDraft) -> dict:
    at = d.admitted_at.isoformat(timespec="minutes")
    day = at[:10]
    ho_id = f"BG-{pid}"
    src = "Bàn giao tiếp nhận (đã xác nhận)"
    allergies = None if d.allergy_status == "unknown" else [] if d.allergy_status == "none" else \
        [{"substance": a, "reaction": "ghi theo bàn giao"} for a in d.allergies]
    resources = [{
        "id": ho_id, "type": "Handoff", "date": day, "source": src, "practitioner": user["name"], "transcript_id": tid,
        "problems": d.diagnoses, "comorbidities": d.comorbidities, "medications": d.meds, "labs_imaging": d.labs,
        "pending": d.pending, "allergies_recorded": allergies,
        "text": "Nội dung bàn giao khi tiếp nhận người bệnh, đã được người dùng kiểm tra và xác nhận.",
    }]
    for i, m in enumerate(d.meds, 1):
        resources.append({"id": f"RX-{pid}-{i}", "type": "MedicationRequest", "date": day, "source": src, "encounter": ho_id,
                          "practitioner": "theo bàn giao", "drug_name": m, "dose": "theo lời bàn giao", "status": "active"})
    final = {"name": d.name, "birth_year": str(d.birth_year), "gender": d.gender, "ward": d.ward, "room": d.room, "bed": d.bed,
             "admitted_date": day, "admitted_time": at[11:16], "reason": d.reason,
             **{k: (None if v is None else _canon(str(v)) if k != "bp" else v) for k, v in d.vitals.model_dump().items()}}
    edited = [LABELS[k] for k, v in final.items()
              if canon_value(k, check.fields[k].value or "") != canon_value(k, "" if v is None else str(v))]
    return {
        "patient": {
            "id": pid, "name": d.name, "birth_year": d.birth_year, "gender": d.gender, "ward": d.ward,
            "bed": f"Buồng {d.room} - Giường {d.bed}", "attending": None, "origin": "handoff",
            "admission": {"id": f"BA-{pid}", "admitted_at": at, "ward_at": at, "reason": d.reason,
                          "kkb_diagnosis": " / ".join(d.diagnoses) or None, "vitals": d.vitals.model_dump()},
        },
        "resources": resources,
        "handoff": {"transcript_id": tid, "confirmed_by": user["username"], "confirmed_role": user["role"], "confirmed_at": now,
                    "fields_edited_vs_rules": edited, "warnings_acknowledged": d.acknowledged_warnings,
                    "rule_flags_at_confirm": check.flag_count},
    }
