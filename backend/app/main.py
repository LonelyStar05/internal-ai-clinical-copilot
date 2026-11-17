"""API FastAPI cho AI Clinical Copilot (prototype, dữ liệu giả lập)."""
from __future__ import annotations

import os

from fastapi import Body, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from . import assignments, auth, store
from .core import kb as KB
from .core import llm
from .modules import handoff, stt
from .modules.coverage import evaluate_coverage, service_catalog
from .modules.note import draft_note, to_text
from .modules.summary import source_index, summarize

app = FastAPI(title="AI Clinical Copilot – Nội tổng hợp", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"], allow_headers=["*"],
)


class LoginIn(BaseModel):
    username: str
    password: str


class DraftIn(BaseModel):
    patient_id: str
    transcript_id: str | None = None
    transcript_text: str | None = None  # dán transcript mới: mỗi dòng "BS: ...", "BN: ...", "NN: ..."


class ApproveIn(BaseModel):
    final_text: str


class ReviewIn(BaseModel):
    decision: str  # "xác nhận" | "cần sửa"
    comment: str = ""


class CoverageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_codes: list[str] = Field(min_length=1, max_length=12)


def _guard(user: dict, pid: str, reason: str | None, action: str, detail: str = "") -> None:
    """Thao tác đọc: bác sĩ điều trị, hoặc bác sĩ khác có lý do khẩn cấp hợp lệ. Mọi lần đều ghi audit."""
    ok, emergency = auth.can_access(user, pid, reason)
    if not ok:
        store.audit(user["username"], user["role"], f"TỪ CHỐI {action}", pid, "không phải bác sĩ điều trị")
        raise HTTPException(403, "Bạn không phải bác sĩ điều trị người bệnh này. "
                                 "Trường hợp khẩn cấp: nhập lý do (ít nhất 10 ký tự) để truy cập, hệ thống sẽ ghi lại.")
    parts = ([f"lý do: {reason}"] if emergency else []) + ([detail] if detail else [])
    store.audit(user["username"], user["role"], action + (" [KHẨN CẤP]" if emergency else ""), pid, " · ".join(parts))


def _write_guard(user: dict, pid: str, action: str) -> None:
    """Thao tác ghi: chỉ bác sĩ đang phụ trách và đã tiếp nhận hồ sơ. Truy cập khẩn cấp là chỉ đọc nên không được ghi,
    kể cả khi có lý do; bác sĩ cũ mất quyền ghi ngay khi hồ sơ được chuyển."""
    why = auth.write_block_reason(user, pid)
    if why:
        store.audit(user["username"], user["role"], f"TỪ CHỐI {action}", pid, why)
        raise HTTPException(403, why)
    store.audit(user["username"], user["role"], action, pid)


@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm.available(), "mode": "llm" if llm.available() else "offline", "model": llm.MODEL,
            "stt": {"engine": "faster-whisper", "model": stt.MODEL_NAME, "loaded": stt._model is not None}}


@app.post("/api/stt/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    case_id: str = Form(..., min_length=1, max_length=80),
    speaker: str = Form(..., min_length=1, max_length=20),
    context: str = Form(default="", max_length=1000),
    hotwords: str = Form(default="", max_length=1000),
    user: dict = Depends(auth.require_staff),
):
    if KB.load_patient(case_id):
        _guard(user, case_id, None, "TRUY CẬP GHI ÂM")
    data = await audio.read(stt.REQUEST_LIMIT + 1)
    try:
        result = await run_in_threadpool(
            stt.transcribe_bytes, data, filename=audio.filename or "audio.webm", case_id=case_id,
            speaker=speaker, context=context, hotwords=hotwords,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception as exc:
        raise HTTPException(503, f"Không chạy được bộ nhận dạng giọng nói cục bộ: {exc}") from None
    patient_id = case_id if KB.load_patient(case_id) else None
    store.audit(user["username"], user["role"], "NHẬN DẠNG GIỌNG NÓI", patient_id,
                f"case: {case_id} · speaker: {speaker} · engine: {result.engine}/{result.model} · "
                f"duration: {result.duration}s · needs_review: {result.needs_review}")
    return result.model_dump()


@app.post("/api/auth/login")
def login(body: LoginIn):
    out = auth.login(body.username, body.password)
    store.audit(body.username, out["role"], "ĐĂNG NHẬP")
    return out


@app.get("/api/me")
def me(user: dict = Depends(auth.current_user)):
    return {k: user[k] for k in ("username", "role", "name")}


def _assignment_view(a: dict) -> dict:
    return {"doctor": a["doctor"], "status": a["status"], "status_label": assignments.STATUS_LABEL[a["status"]],
            "assigned_by": a["assigned_by"], "assigned_at": a["assigned_at"], "accepted_by": a["accepted_by"],
            "accepted_at": a["accepted_at"], "note": a["note"], "version": a["version"]}


@app.get("/api/patients")
def patients(user: dict = Depends(auth.require_doctor)):
    """Chỉ người bệnh đang được phân công cho bác sĩ đăng nhập. Hồ sơ khác chỉ mở được qua truy cập khẩn cấp theo mã."""
    current = assignments.all_current()
    out = []
    for p in KB.list_patients():
        a = current[p["id"]]
        if a["doctor"] != user["username"]:
            continue
        out.append({"id": p["id"], "ward": p.get("ward"), "bed": p.get("bed"), "is_mine": True, "name": p["name"],
                    "birth_year": p["birth_year"], "gender": p["gender"], "reason": p.get("admission", {}).get("reason"),
                    "assignment_status": a["status"], "assigned_at": a["assigned_at"], "is_new": a["status"] == "pending"})
    return out


@app.get("/api/patients/{pid}/summary")
def get_summary(pid: str, emergency_reason: str | None = Query(default=None), user: dict = Depends(auth.require_doctor)):
    _guard(user, pid, emergency_reason, "XEM TÓM TẮT")
    s = summarize(pid)
    a = assignments.current(pid)
    p = {**KB.load_patient(pid)["patient"], "attending": a["doctor"]}  # phân công trong DB ưu tiên hơn JSON
    return {"patient": p, "summary": s.model_dump(), "last_review": store.last_summary_review(pid),
            "assignment": _assignment_view(a), "can_write": auth.can_write(user, pid)}


@app.get("/api/coverage/services")
def coverage_services(user: dict = Depends(auth.require_doctor)):
    """Danh mục xét nghiệm đã có luật kiểm tra trong prototype."""
    return [item.model_dump() for item in service_catalog()]


@app.post("/api/patients/{pid}/coverage/check")
def coverage_check(pid: str, body: CoverageIn, emergency_reason: str | None = Query(default=None),
                   user: dict = Depends(auth.require_doctor)):
    """Rà soát read-only; không tạo y lệnh và không thay đổi hồ sơ."""
    _guard(user, pid, emergency_reason, "KIỂM TRA RỦI RO BHYT", ", ".join(body.service_codes))
    try:
        return evaluate_coverage(pid, body.service_codes).model_dump()
    except KeyError:
        raise HTTPException(404, "Không có hồ sơ") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@app.post("/api/patients/{pid}/accept-assignment")
def accept_assignment(pid: str, user: dict = Depends(auth.require_doctor)):
    try:
        out = assignments.accept(user, pid)
    except assignments.AssignError as e:
        store.audit(user["username"], user["role"], "TỪ CHỐI TIẾP NHẬN HỒ SƠ", pid, f"kết quả: thất bại · {e}")
        raise HTTPException(e.status, str(e)) from None
    store.audit(user["username"], user["role"], "TIẾP NHẬN HỒ SƠ", pid, f"người nhận: {user['username']} · kết quả: thành công")
    return out


@app.post("/api/patients/{pid}/summary/review")
def review_summary(pid: str, body: ReviewIn, user: dict = Depends(auth.require_doctor)):
    _write_guard(user, pid, f"DUYỆT TÓM TẮT: {body.decision}")
    rid = store.save_summary_review(pid, user["username"], body.decision, body.comment, summarize(pid).model_dump())
    return {"id": rid}


@app.get("/api/patients/{pid}/sources/{ref}")
def get_source(pid: str, ref: str, emergency_reason: str | None = None, user: dict = Depends(auth.require_doctor)):
    _guard(user, pid, emergency_reason, "XEM BẢN GHI GỐC", ref)
    src = source_index(pid).get(ref)
    if src is None:
        raise HTTPException(404, "Không có bản ghi")
    return src


@app.get("/api/patients/{pid}/transcripts")
def transcripts(pid: str, emergency_reason: str | None = None, user: dict = Depends(auth.require_doctor)):
    _guard(user, pid, emergency_reason, "XEM DANH SÁCH TRANSCRIPT")
    return KB.list_transcripts(pid)


@app.get("/api/patients/{pid}/transcripts/{tid}")
def transcript_detail(pid: str, tid: str, emergency_reason: str | None = None, user: dict = Depends(auth.require_doctor)):
    _guard(user, pid, emergency_reason, "XEM TRANSCRIPT", tid)
    t = KB.load_transcript(tid)
    if t is None or t.get("patient_id") != pid:
        raise HTTPException(404, "Không có transcript")
    return t


@app.get("/api/patients/{pid}/notes")
def notes(pid: str, emergency_reason: str | None = None, user: dict = Depends(auth.require_doctor)):
    _guard(user, pid, emergency_reason, "XEM DANH SÁCH BỆNH ÁN")
    return store.list_notes(pid)


@app.post("/api/notes/draft")
def create_draft(body: DraftIn, user: dict = Depends(auth.require_doctor)):
    _write_guard(user, body.patient_id, "SOẠN NHÁP BỆNH ÁN")
    tid = body.transcript_id
    if body.transcript_text:
        try:
            tid = KB.save_transcript(body.patient_id, body.transcript_text)["id"]
        except ValueError as e:
            raise HTTPException(422, str(e))
    if not tid:
        raise HTTPException(422, "Cần transcript_id hoặc transcript_text")
    try:
        d = draft_note(body.patient_id, tid)
    except KeyError:
        raise HTTPException(404, "Không có transcript")
    text = to_text(d)
    nid = store.save_draft(body.patient_id, tid, user["username"], d.model_dump(), text)
    return {"note_id": nid, "draft": d.model_dump(), "text": text}


@app.get("/api/notes/{nid}")
def get_note(nid: str, emergency_reason: str | None = None, user: dict = Depends(auth.require_doctor)):
    n = store.get_note(nid)
    if not n:
        raise HTTPException(404, "Không có bản nháp")
    _guard(user, n["patient_id"], emergency_reason, "XEM BỆNH ÁN", nid)
    return n


@app.post("/api/notes/{nid}/approve")
def approve(nid: str, body: ApproveIn, user: dict = Depends(auth.require_doctor)):
    n = store.get_note(nid)
    if not n:
        raise HTTPException(404, "Không có bản nháp")
    _write_guard(user, n["patient_id"], "KÝ DUYỆT BỆNH ÁN")
    if n["status"] == "approved":
        raise HTTPException(409, "Bản này đã được ký duyệt")
    stats = store.approve(nid, user["username"], body.final_text)
    return {"status": "approved", "stats": stats}


@app.get("/api/notes/{nid}/fhir")
def note_fhir(nid: str, user: dict = Depends(auth.require_doctor)):
    """Xuất bản đã duyệt dạng FHIR R4 Bundle: Composition (nội dung) + Provenance (AI soạn, bác sĩ duyệt)."""
    n = store.get_note(nid)
    if not n:
        raise HTTPException(404, "Không có bản nháp")
    _write_guard(user, n["patient_id"], "XUẤT FHIR")
    if n["status"] != "approved":
        raise HTTPException(409, "Chỉ xuất được bản đã ký duyệt")
    sections, cur = [], None
    for line in n["final_text"].splitlines():
        if line.startswith("## "):
            cur = {"title": line[3:].strip(), "text": {"status": "generated", "div": ""}}
            sections.append(cur)
        elif cur is not None and line.strip():
            cur["text"]["div"] += f"<p>{line.lstrip('- ').strip()}</p>"
    for s in sections:
        s["text"]["div"] = f'<div xmlns="http://www.w3.org/1999/xhtml">{s["text"]["div"]}</div>'
    comp_id = f"comp-{nid}"
    return {
        "resourceType": "Bundle", "type": "document",
        "entry": [
            {"resource": {"resourceType": "Composition", "id": comp_id, "status": "final",
                          "type": {"text": "Bệnh án nội khoa"}, "subject": {"reference": f"Patient/{n['patient_id']}"},
                          "date": n["approved_at"], "author": [{"display": n["approved_by"]}],
                          "title": "Bệnh án nội khoa (AI soạn nháp, bác sĩ duyệt)", "section": sections}},
            {"resource": {"resourceType": "Provenance", "target": [{"reference": f"Composition/{comp_id}"}],
                          "recorded": n["approved_at"],
                          "agent": [
                              {"type": {"text": "assembler"}, "who": {"display": "AI Clinical Copilot (bản nháp)"}},
                              {"type": {"text": "verifier"}, "who": {"display": n["approved_by"]}}],
                          "entity": [{"role": "source", "what": {"display": f"Transcript {n['transcript_id']}"}}]}},
        ],
    }


@app.get("/api/admin/audit")
def audit_log(user: dict = Depends(auth.require_admin)):
    return store.list_audit()


# ---------------------------------------------------------------- tiếp nhận bàn giao bằng lời
class HandoffParseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript_text: str = Field(max_length=handoff.MAX_CHARS)


@app.post("/api/handoffs/parse")
def handoff_parse(body: HandoffParseIn, user: dict = Depends(auth.require_staff)):
    """Chỉ trích xuất bản nháp, KHÔNG lưu gì (hủy ở giao diện là không còn dấu vết ngoài dòng audit)."""
    try:
        d = handoff.parse(body.transcript_text)
    except ValueError as e:
        store.audit(user["username"], user["role"], "TỪ CHỐI PHÂN TÍCH BÀN GIAO", None, str(e))
        raise HTTPException(422, str(e)) from None
    store.audit(user["username"], user["role"], "PHÂN TÍCH BÀN GIAO", None,
                f"{len(d.turns)} lượt nói · chế độ {d.mode} · {d.flag_count} cảnh báo · chưa lưu")
    return d.model_dump()


@app.post("/api/handoffs/confirm")
def handoff_confirm(body: dict = Body(...), user: dict = Depends(auth.require_staff)):
    try:
        out = handoff.confirm(body, user)
    except handoff.InvalidHandoff as e:
        store.audit(user["username"], user["role"], "TỪ CHỐI TIẾP NHẬN BÀN GIAO", None, e.audit)
        raise HTTPException(422, str(e)) from None
    assignments.record_intake(user, out["patient_id"])
    a = assignments.current(out["patient_id"])
    store.audit(user["username"], user["role"], "TIẾP NHẬN BÀN GIAO", out["patient_id"],
                f"transcript {out['transcript_id']} · trạng thái: {assignments.STATUS_LABEL[a['status']]}"
                + (f" · bác sĩ: {a['doctor']}" if a["doctor"] else ""))
    return {**out, "assignment": _assignment_view(a)}


# ---------------------------------------------------------------- phân công (chỉ quản trị)
class AssignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(max_length=40)
    doctor: str = Field(max_length=40)
    note: str = Field(default="", max_length=500)
    expected_version: int


class TransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doctor: str = Field(max_length=40)
    reason: str = Field(max_length=500)
    expected_version: int


class BulkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    patient_id: str = Field(max_length=40)
    expected_version: int


class BulkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[BulkItem] = Field(min_length=1, max_length=200)
    doctor: str = Field(max_length=40)
    note: str = Field(default="", max_length=500)


def _assign_call(user: dict, action: str, pids: list[str], detail: str, fn):
    try:
        out = fn()
    except assignments.AssignError as e:
        for pid in pids or [None]:
            store.audit(user["username"], user["role"], f"TỪ CHỐI {action}", pid, f"{detail} · kết quả: thất bại ({e})")
        raise HTTPException(e.status, str(e)) from None
    for r in out if isinstance(out, list) else [out]:
        store.audit(user["username"], user["role"], action, r["patient_id"],
                    f"{r['from'] or 'chưa có'} → {r['to']} · {detail} · kết quả: "
                    + ("không đổi" if r["action"] == "unchanged" else f"thành công (phiên bản {r['version']})"))
    return out


@app.get("/api/admin/assignments")
def list_assignments(q: str = "", doctor: str = "", ward: str = "", status: str = "", user: dict = Depends(auth.require_admin)):
    """Chỉ metadata cần cho phân công: không trả nội dung bệnh án."""
    current = assignments.all_current()
    rows = []
    for p in KB.list_patients():
        a = current[p["id"]]
        rows.append({"id": p["id"], "name": p["name"], "ward": p.get("ward"), "bed": p.get("bed"),
                     "reason": p.get("admission", {}).get("reason"), "origin": p.get("origin", "dataset"),
                     "doctor": a["doctor"], "doctor_name": auth.USERS.get(a["doctor"] or "", {}).get("name"),
                     **{k: v for k, v in _assignment_view(a).items() if k != "doctor"}})
    needle = q.strip().lower()
    rows = [r for r in rows
            if (not needle or needle in f"{r['id']} {r['name']} {r['bed']} {r['reason'] or ''}".lower())
            and (not doctor or (r["doctor"] or "") == ("" if doctor == "none" else doctor))
            and (not ward or r["ward"] == ward) and (not status or r["status"] == status)]
    return {"patients": rows, "doctors": assignments.doctors(current),
            "wards": sorted({p.get("ward") for p in KB.list_patients() if p.get("ward")}),
            "statuses": assignments.STATUS_LABEL}


@app.post("/api/admin/assignments")
def create_assignment(body: AssignIn, user: dict = Depends(auth.require_admin)):
    return _assign_call(user, "PHÂN CÔNG HỒ SƠ", [body.patient_id], f"ghi chú: {body.note or '—'}",
                        lambda: assignments.assign(user, body.patient_id, body.doctor, body.note, body.expected_version))


@app.post("/api/admin/assignments/bulk")
def bulk_assignment(body: BulkIn, user: dict = Depends(auth.require_admin)):
    pids = [i.patient_id for i in body.items]
    out = _assign_call(user, "PHÂN CÔNG HÀNG LOẠT", pids, f"{len(pids)} hồ sơ · lý do/ghi chú: {body.note or '—'}",
                       lambda: assignments.bulk(user, [i.model_dump() for i in body.items], body.doctor, body.note))
    return {"results": out}


@app.post("/api/admin/assignments/{pid}/transfer")
def transfer_assignment(pid: str, body: TransferIn, user: dict = Depends(auth.require_admin)):
    return _assign_call(user, "CHUYỂN HỒ SƠ", [pid], f"lý do: {body.reason or '—'}",
                        lambda: assignments.transfer(user, pid, body.doctor, body.reason, body.expected_version))


@app.get("/api/admin/assignments/{pid}/history")
def assignment_history(pid: str, user: dict = Depends(auth.require_admin)):
    try:
        cur = assignments.current(pid)
        return {"current": _assignment_view(cur), "history": assignments.history(pid)}
    except assignments.AssignError as e:
        raise HTTPException(e.status, str(e)) from None


@app.get("/api/admin/eval")
def run_eval(user: dict = Depends(auth.require_admin)):
    from .evaluate import run
    return run()
