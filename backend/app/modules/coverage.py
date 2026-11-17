"""Bộ luật demo rà soát rủi ro thanh toán trước chỉ định.

Module này chỉ đối chiếu dữ liệu đã có trong hồ sơ giả lập. Kết quả không phải
quyết định chuyên môn hoặc kết luận thanh toán BHYT.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from ..core import kb as KB


RiskLevel = Literal["low", "medium", "high", "unknown"]


class CoverageService(BaseModel):
    code: str
    display: str
    group: str
    short_rule: str


class CoverageCriterion(BaseModel):
    label: str
    status: Literal["met", "not_met", "missing", "info"]
    value: str
    source_ref: str | None = None


class CoverageBasis(BaseModel):
    title: str
    detail: str
    url: str
    kind: Literal["official", "demo"] = "demo"


class RecentTest(BaseModel):
    date: str
    value: str
    source_ref: str


class CoverageResult(BaseModel):
    service: CoverageService
    risk_level: RiskLevel
    risk_label: str
    verdict: str
    clinical_status: Literal["eligible", "not_eligible", "insufficient", "no_special_condition"]
    duplicate_status: Literal["clear", "recent", "unknown"]
    admin_status: Literal["unknown"] = "unknown"
    criteria: list[CoverageCriterion] = Field(default_factory=list)
    recent_tests: list[RecentTest] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    basis: list[CoverageBasis] = Field(default_factory=list)


class CoverageResponse(BaseModel):
    patient_id: str
    as_of: str
    results: list[CoverageResult]
    counts: dict[RiskLevel, int]
    limitations: list[str]
    disclaimer: str


_SERVICES = (
    CoverageService(code="CBC", display="Tổng phân tích tế bào máu", group="Huyết học",
                    short_rule="Đối chiếu dấu hiệu nhiễm trùng và kết quả gần đây"),
    CoverageService(code="CRP", display="Định lượng CRP", group="Hóa sinh",
                    short_rule="Đối chiếu dấu hiệu viêm, nhiễm trùng và xét nghiệm lặp"),
    CoverageService(code="HBA1C", display="Định lượng HbA1c", group="Hóa sinh",
                    short_rule="Đối chiếu bệnh đái tháo đường và kết quả trong 90 ngày"),
    CoverageService(code="CREAT", display="Định lượng Creatinin", group="Hóa sinh",
                    short_rule="Đối chiếu bệnh nền, thuốc và kết quả trong 7 ngày"),
    CoverageService(code="K", display="Định lượng Kali", group="Điện giải",
                    short_rule="Đối chiếu chức năng thận, thuốc và kết quả trong 24 giờ"),
    CoverageService(code="GLU", display="Định lượng Glucose", group="Hóa sinh",
                    short_rule="Đối chiếu rối loạn đường huyết và kết quả trong 24 giờ"),
    CoverageService(code="CXR", display="X-quang ngực thẳng", group="Chẩn đoán hình ảnh",
                    short_rule="Đối chiếu triệu chứng hô hấp và hình ảnh gần đây"),
)

_BY_CODE = {item.code: item for item in _SERVICES}
_ANALYTE = {"CBC": "wbc", "CRP": "crp", "HBA1C": "hba1c", "CREAT": "creatinine", "K": "potassium", "GLU": "glucose"}
_DUPLICATE_DAYS = {"CBC": 1, "CRP": 1, "HBA1C": 90, "CREAT": 7, "K": 1, "GLU": 1, "CXR": 7}
_RISK_LABEL = {"low": "Nguy cơ thấp", "medium": "Cần rà soát", "high": "Nguy cơ cao", "unknown": "Chưa đủ dữ liệu"}


def service_catalog() -> list[CoverageService]:
    return list(_SERVICES)


def _days_between(later: str, earlier: str) -> int | None:
    try:
        return (date.fromisoformat(later[:10]) - date.fromisoformat(earlier[:10])).days
    except (TypeError, ValueError):
        return None


def _facts(record: dict) -> tuple[set[str], str, str]:
    patient = record["patient"]
    resources = record.get("resources", [])
    codes: set[str] = set()
    text_parts = [patient.get("admission", {}).get("reason", ""), patient.get("admission", {}).get("kkb_diagnosis", "")]
    dates = [patient.get("admission", {}).get("admitted_at", "")[:10]]
    for resource in resources:
        dates.append(str(resource.get("date", ""))[:10])
        text_parts.extend([str(resource.get("text", "")), str(resource.get("note", ""))])
        for diagnosis in resource.get("diagnoses", []):
            codes.add(str(diagnosis.get("code", "")).upper())
            text_parts.append(str(diagnosis.get("display", "")))
    as_of = max((value for value in dates if value), default=date.today().isoformat())
    return codes, KB.fold(" ".join(text_parts)), as_of


def _clinical_status(code: str, diagnosis_codes: set[str], folded_text: str) -> tuple[str, CoverageCriterion, list[str]]:
    diabetes = any(value.startswith(("E10", "E11", "E13")) for value in diagnosis_codes) or "dai thao duong" in folded_text
    respiratory = any(word in folded_text for word in ("viem phoi", "sot", "ho dom", "kho tho", "nhiem trung"))
    renal_or_monitoring = any(word in folded_text for word in ("than", "tang huyet ap", "dai thao duong", "rung nhi"))

    if code == "HBA1C":
        ok, value = diabetes, "Có chẩn đoán đái tháo đường trong hồ sơ" if diabetes else "Chưa thấy chẩn đoán đái tháo đường"
    elif code in {"CBC", "CRP", "CXR"}:
        ok, value = respiratory, "Có triệu chứng hoặc chẩn đoán hô hấp/nhiễm trùng" if respiratory else "Chưa thấy triệu chứng hoặc chẩn đoán liên quan"
    elif code in {"CREAT", "K", "GLU"}:
        ok, value = renal_or_monitoring or diabetes, "Có bệnh nền cần bác sĩ đối chiếu khi theo dõi" if (renal_or_monitoring or diabetes) else "Chưa thấy căn cứ theo dõi rõ trong dữ liệu hiện có"
    else:
        return "insufficient", CoverageCriterion(label="Căn cứ lâm sàng", status="missing", value="Chưa có luật demo"), ["Luật đánh giá dịch vụ"]

    status = "eligible" if ok else "insufficient"
    criterion = CoverageCriterion(label="Căn cứ trong hồ sơ", status="met" if ok else "missing", value=value,
                                  source_ref="BA-2026-11-08" if ok else None)
    return status, criterion, [] if ok else ["Căn cứ lâm sàng hoặc mục đích chỉ định"]


def _recent_tests(record: dict, code: str, as_of: str) -> tuple[list[RecentTest], str]:
    resources = record.get("resources", [])
    found: list[RecentTest] = []
    if code == "CXR":
        for resource in resources:
            if resource.get("type") == "ImagingStudy" and "quang" in KB.fold(str(resource.get("modality", ""))):
                found.append(RecentTest(date=resource.get("date", ""), value=str(resource.get("text", "Đã có kết quả")), source_ref=resource["id"]))
    else:
        analyte = _ANALYTE.get(code)
        for resource in resources:
            results = resource.get("results", {})
            if analyte and analyte in results:
                found.append(RecentTest(date=resource.get("date", ""), value=str(results[analyte]), source_ref=resource["id"]))
    found.sort(key=lambda item: item.date, reverse=True)
    if not found:
        return [], "unknown"
    days = _days_between(as_of, found[0].date)
    return found[:3], "recent" if days is not None and days <= _DUPLICATE_DAYS[code] else "clear"


def evaluate_coverage(patient_id: str, service_codes: list[str]) -> CoverageResponse:
    record = KB.load_patient(patient_id)
    if record is None:
        raise KeyError(patient_id)
    unknown = [code for code in service_codes if code.upper() not in _BY_CODE]
    if unknown:
        raise ValueError("Dịch vụ chưa có luật kiểm tra: " + ", ".join(unknown))

    diagnosis_codes, folded_text, as_of = _facts(record)
    results: list[CoverageResult] = []
    for raw_code in service_codes:
        code = raw_code.upper()
        service = _BY_CODE[code]
        clinical_status, clinical_criterion, missing = _clinical_status(code, diagnosis_codes, folded_text)
        recent, duplicate_status = _recent_tests(record, code, as_of)
        duplicate_criterion = CoverageCriterion(
            label="Kết quả gần đây",
            status="not_met" if duplicate_status == "recent" else ("info" if duplicate_status == "clear" else "missing"),
            value=(f"Có kết quả trong cửa sổ {_DUPLICATE_DAYS[code]} ngày" if duplicate_status == "recent"
                   else "Không thấy kết quả trong cửa sổ kiểm tra" if duplicate_status == "clear"
                   else "Không có dữ liệu kết quả trước đó"),
            source_ref=recent[0].source_ref if recent else None,
        )

        if duplicate_status == "recent":
            risk: RiskLevel = "high"
            verdict = "Có kết quả gần đây. Bác sĩ cần xác nhận lý do làm lại nếu vẫn chỉ định."
            missing.append("Lý do làm lại trong cửa sổ kiểm tra")
        elif clinical_status == "insufficient":
            risk = "medium"
            verdict = "Chưa thấy đủ căn cứ trong dữ liệu hiện có. Cần rà soát hồ sơ trước khi chỉ định."
        elif duplicate_status == "unknown":
            risk = "unknown"
            verdict = "Không có dữ liệu xét nghiệm trước đó để đánh giá trùng lặp."
        else:
            risk = "low"
            verdict = "Chưa phát hiện rủi ro theo các luật demo đang bật."

        results.append(CoverageResult(
            service=service,
            risk_level=risk,
            risk_label=_RISK_LABEL[risk],
            verdict=verdict,
            clinical_status=clinical_status,
            duplicate_status=duplicate_status,
            criteria=[clinical_criterion, duplicate_criterion],
            recent_tests=recent,
            missing_data=sorted(set(missing)),
            basis=[CoverageBasis(
                title=f"Quy tắc demo {code}",
                detail=service.short_rule,
                url=f"internal://coverage-rules/{code.lower()}",
            )],
        ))

    counts: dict[RiskLevel, int] = {"low": 0, "medium": 0, "high": 0, "unknown": 0}
    for result in results:
        counts[result.risk_level] += 1
    return CoverageResponse(
        patient_id=patient_id,
        as_of=as_of,
        results=results,
        counts=counts,
        limitations=[
            "Chỉ dùng dữ liệu giả lập hiện có trong hồ sơ.",
            "Chưa kiểm tra quyền lợi thẻ, hợp đồng bệnh viện, giá hoặc danh mục thanh toán thực tế.",
            "Các cửa sổ thời gian là quy tắc demo để kiểm thử sản phẩm.",
        ],
        disclaimer="Kết quả chỉ hỗ trợ rà soát. Hệ thống không quyết định chỉ định chuyên môn hoặc quyền thanh toán BHYT.",
    )
