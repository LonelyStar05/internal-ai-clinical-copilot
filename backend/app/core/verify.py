"""Kiểm chứng bằng code: mọi câu phải có dẫn chứng, mọi con số phải có trong nguồn được dẫn."""
from __future__ import annotations

import json

from .models import Line
from .vn_text import numbers_in


def source_numbers(text_or_obj) -> set[str]:
    text = text_or_obj if isinstance(text_or_obj, str) else json.dumps(text_or_obj, ensure_ascii=False)
    nums = numbers_in(text)
    # thêm dạng rút gọn: 7.10 -> 7.1, 05 -> 5
    extra = set()
    for n in nums:
        try:
            f = float(n)
            extra.add(str(int(f)) if f.is_integer() else f"{f:g}")
        except ValueError:
            pass
    return nums | extra


def _canon(n: str) -> str:
    try:
        f = float(n)
        return str(int(f)) if f.is_integer() else f"{f:g}"
    except ValueError:
        return n


# Tên chỉ số / đơn vị có chứa chữ số, không phải giá trị lâm sàng
LABEL_TOKENS = ["ICD-10", "SpO2", "SpO₂", "HbA1c", "1,73m²", "1.73m²", "PaO2", "PaCO2"]


def _strip_labels(text: str) -> str:
    for t in LABEL_TOKENS:
        text = text.replace(t, " ")
    return text


def verify_line(line: Line, sources: dict[str, str | dict]) -> tuple[bool, str]:
    """sources: mã dẫn chứng -> nội dung nguồn. Trả (hợp lệ, lý do nếu bị loại)."""
    if line.kind in ("missing", "info"):
        return True, ""
    if not line.citations:
        return False, "không có dẫn chứng"
    unknown = [c.ref for c in line.citations if c.ref not in sources]
    if unknown:
        return False, f"dẫn chứng không tồn tại: {', '.join(unknown)}"
    allowed: set[str] = set()
    for c in line.citations:
        allowed |= source_numbers(sources[c.ref])
    allowed = {_canon(n) for n in allowed}
    missing = sorted({n for n in numbers_in(_strip_labels(line.text)) if _canon(n) not in allowed})
    if missing:
        return False, f"con số không có trong nguồn được dẫn: {', '.join(missing)}"
    return True, ""
