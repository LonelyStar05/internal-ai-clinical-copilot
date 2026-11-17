"""Chuẩn hóa văn bản tiếng Việt từ transcript: sửa lỗi ASR thường gặp, đổi số đọc bằng chữ sang chữ số.

Ví dụ:
    "SpO2 đang chín mươi mốt"                    -> "SpO2 đang 91"
    "một trăm hai mươi tám trên bảy mươi sáu"    -> "128/76"
    "mười lăm phẩy hai"                          -> "15.2"
    "sốt trên ba mươi tám rưỡi"                  -> "sốt trên 38.5"
    "ngày hai ba viên"                           -> "ngày 2-3 viên"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Lỗi ASR hay gặp (mất dấu) -> từ đúng. Chỉ sửa khi đứng cạnh từ chỉ số để tránh sửa nhầm.
ASR_FIXES = {"chin": "chín", "bay": "bảy", "tam": "tám", "muoi": "mươi", "tram": "trăm"}

# "không" cố ý không đưa vào: trong hội thoại nó gần như luôn là phủ định ("không chướng").
DIGITS = {
    "một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5,
    "sáu": 6, "bảy": 7, "bẩy": 7, "tám": 8, "chín": 9,
}
# Biến thể chỉ là số khi đứng sau "mươi"/"mười"
AFTER_TENS = {"mốt": 1, "tư": 4, "lăm": 5, "nhăm": 5}
STRUCT = {"mười", "mươi", "trăm", "nghìn", "ngàn", "linh", "lẻ"}
NUMBER_WORDS = set(DIGITS) | set(AFTER_TENS) | STRUCT | {"phẩy", "rưỡi"}


@dataclass
class Normalized:
    text: str
    asr_fixes: list[tuple[str, str]] = field(default_factory=list)


def _parse_int(words: list[str]) -> int:
    total, seg, last = 0, 0, None
    for w in words:
        if w in DIGITS:
            last = DIGITS[w]
        elif w in AFTER_TENS:
            last = AFTER_TENS[w]
        elif w == "mười":
            seg += 10
            last = None
        elif w == "mươi":
            seg += (last if last is not None else 1) * 10
            last = None
        elif w == "trăm":
            seg += (last if last is not None else 1) * 100
            last = None
        elif w in ("linh", "lẻ"):
            continue
        elif w in ("nghìn", "ngàn"):
            seg += last or 0
            total += (seg or 1) * 1000
            seg, last = 0, None
    return total + seg + (last or 0)


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def _run_to_number(words: list[str]) -> str:
    """Đổi một chuỗi từ chỉ số sang chữ số."""
    half = False
    if words and words[-1] == "rưỡi":
        half, words = True, words[:-1]
    if "phẩy" in words:
        i = words.index("phẩy")
        int_part = _parse_int(words[:i]) if words[:i] else 0
        frac = "".join(str(DIGITS.get(w, AFTER_TENS.get(w, ""))) for w in words[i + 1:])
        return f"{int_part},{frac}" if frac else str(int_part)  # dấu phẩy thập phân kiểu Việt Nam
    # Hai từ số trơn liền nhau, không có từ cấu trúc: là khoảng ("hai ba viên" = 2-3 viên)
    if len(words) >= 2 and all(w in DIGITS for w in words):
        return "-".join(str(DIGITS[w]) for w in words)
    value = _parse_int(words)
    return _fmt(value + 0.5).replace(".", ",") if half else str(value)


def _valid_run(words: list[str]) -> bool:
    # "mốt", "tư", "lăm" chỉ là số khi đứng sau mươi/mười
    for i, w in enumerate(words):
        if w in AFTER_TENS and (i == 0 or words[i - 1] not in ("mươi", "mười")):
            return False
    return any(w in DIGITS or w in ("mười", "trăm") or w in AFTER_TENS for w in words)


YEAR_NEXT = {"rồi", "nay", "trước", "sau", "qua", "ngoái", "trời"}


def _is_year_noun(run: list[str], tokens: list[str], k: int) -> bool:
    """'năm' sau một con số là danh từ 'năm' (year) khi: đứng sau mười/mươi (số 5 lúc đó đọc là 'lăm'),
    hoặc theo sau là rồi/nay/trước... ('hai năm rồi' = 2 năm, còn 'bốn năm lần' = 4-5 lần)."""
    if run and run[-1] in ("mười", "mươi"):
        return True
    nxt = next((tokens[m].lower() for m in range(k + 1, len(tokens)) if not tokens[m].isspace()), "")
    return nxt in YEAR_NEXT or nxt in {",", ".", ";"}


def normalize(text: str) -> Normalized:
    """Trả về văn bản đã đổi số chữ sang chữ số và danh sách lỗi ASR đã sửa."""
    tokens = re.findall(r"\w+|[^\w\s]|\s+", text, flags=re.UNICODE)
    fixes: list[tuple[str, str]] = []

    # 1) Sửa lỗi ASR khi từ sai đứng cạnh một từ chỉ số
    words_idx = [i for i, t in enumerate(tokens) if re.match(r"\w", t)]
    for k, i in enumerate(words_idx):
        low = tokens[i].lower()
        if low in ASR_FIXES:
            neighbors = [tokens[words_idx[j]].lower() for j in (k - 1, k + 1) if 0 <= j < len(words_idx)]
            if any(n in NUMBER_WORDS for n in neighbors):
                fixes.append((tokens[i], ASR_FIXES[low]))
                tokens[i] = ASR_FIXES[low]

    # 2) Gom các chuỗi từ chỉ số liên tiếp (cách nhau bởi khoảng trắng) và đổi sang chữ số
    out: list[str] = []
    year_idx: set[int] = set()
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if i in year_idx or (t.lower() == "năm" and _is_year_noun([], tokens, i)):
            out.append(t)
            i += 1
            continue
        if t.lower() in NUMBER_WORDS:
            run, j = [t.lower()], i + 1
            while j + 1 < len(tokens) and tokens[j].isspace() and tokens[j + 1].lower() in NUMBER_WORDS:
                if tokens[j + 1].lower() == "năm" and _is_year_noun(run, tokens, j + 1):
                    year_idx.add(j + 1)
                    break
                run.append(tokens[j + 1].lower())
                j += 2
            if _valid_run(run):
                out.append(_run_to_number(run))
                i = j
                continue
        out.append(t)
        i += 1
    joined = "".join(out)
    # 3) "128 trên 76" -> "128/76" (huyết áp)
    joined = re.sub(r"(\d+) trên (\d+)", r"\1/\2", joined)
    return Normalized(joined, fixes)


NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def numbers_in(text: str) -> set[str]:
    """Các con số trong văn bản, chuẩn hóa dấu thập phân về dấu chấm."""
    return {n.replace(",", ".") for n in NUM_RE.findall(text)}
