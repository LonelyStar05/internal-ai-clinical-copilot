from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """Một dẫn chứng: mã bản ghi trong hồ sơ (vd XN-2026-03-12) hoặc lượt nói trong transcript (vd L9)."""
    ref: str
    quote: str | None = None


class Line(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)
    kind: Literal["fact", "missing", "info", "suggestion"] = "fact"


class Section(BaseModel):
    key: str
    title: str
    lines: list[Line] = Field(default_factory=list)


class Flag(BaseModel):
    id: str
    kind: str
    severity: Literal["đỏ", "cao", "trung bình", "thông tin"]
    title: str
    detail: str
    citations: list[Citation] = Field(default_factory=list)
    data: dict = Field(default_factory=dict)


class TrendPoint(BaseModel):
    date: str
    value: float
    ref: str


class Trend(BaseModel):
    analyte: str
    display: str
    unit: str
    loinc: str | None
    points: list[TrendPoint]
    direction: Literal["tăng", "giảm", "ổn định"]
    abnormal_latest: bool


class ActiveMed(BaseModel):
    ingredient: str
    display: str
    entries: list[dict]  # mỗi đơn kê: tên thuốc, liều, bác sĩ, ngày, mã nguồn


class Summary(BaseModel):
    patient_id: str
    mode: Literal["llm", "offline"]
    sections: list[Section]
    flags: list[Flag]
    trends: list[Trend]
    active_meds: list[ActiveMed]
    allergies: list[dict]
    narrative: list[Line] = Field(default_factory=list)
    dropped: list[dict] = Field(default_factory=list)  # câu bị verifier loại, kèm lý do
    disclaimer: str


class Fact(BaseModel):
    section: Literal["S", "O", "A", "P"]
    field: str
    text: str
    turns: list[int]
    speaker: str
    numbers: list[str] = Field(default_factory=list)


class NoteDraft(BaseModel):
    patient_id: str
    transcript_id: str
    mode: Literal["llm", "offline"]
    sections: list[Section]
    flags: list[Flag]
    missing: list[dict]
    icd_suggestions: list[dict]
    facts: list[Fact]
    dropped: list[dict] = Field(default_factory=list)
    normalized_turns: list[dict]
    disclaimer: str
