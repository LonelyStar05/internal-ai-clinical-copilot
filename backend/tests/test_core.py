# Biến môi trường (offline, thư mục tạm) được đặt trong conftest.py trước khi import app.
import pytest

from fastapi.testclient import TestClient  # noqa: E402

from app.core.models import Citation, Line  # noqa: E402
from app.core.verify import verify_line  # noqa: E402
from app.core.vn_text import normalize  # noqa: E402
from app.evaluate import eval_module1, eval_module2  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
AN = {"Authorization": "Bearer demo-bs-an"}
BINH = {"Authorization": "Bearer demo-bs-binh"}
ADMIN = {"Authorization": "Bearer demo-admin"}


def test_vietnamese_numbers():
    assert normalize("SpO2 đang chín mươi mốt").text == "SpO2 đang 91"
    assert normalize("Huyết áp một trăm hai mươi tám trên bảy mươi sáu").text == "Huyết áp 128/76"
    assert normalize("bạch cầu mười lăm phẩy hai").text == "bạch cầu 15,2"
    assert normalize("sốt trên ba mươi tám rưỡi").text == "sốt trên 38,5"
    assert normalize("Bụng mềm, không chướng").text == "Bụng mềm, không chướng"
    assert normalize("hút thuốc ba mươi năm, bỏ được hai năm rồi").text == "hút thuốc 30 năm, bỏ được 2 năm rồi"
    assert normalize("xịt ngày bốn năm lần").text == "xịt ngày 4-5 lần"
    assert normalize("mạch một trăm linh năm").text == "mạch 105"
    n = normalize("SpO2 dưới chin mươi")
    assert n.text == "SpO2 dưới 90" and n.asr_fixes == [("chin", "chín")]


def test_verifier_rejects_invented_number():
    src = {"XN-1": {"results": {"potassium": 5.8}, "date": "2026-03-12"}}
    ok, _ = verify_line(Line(text="Kali 5,8 ngày 12/03/2026", citations=[Citation(ref="XN-1")]), src)
    assert ok
    ok, why = verify_line(Line(text="Kali 6,2", citations=[Citation(ref="XN-1")]), src)
    assert not ok and "6.2" in why
    ok, why = verify_line(Line(text="Kali 5,8", citations=[]), src)
    assert not ok
    ok, why = verify_line(Line(text="Kali 5,8", citations=[Citation(ref="XN-9")]), src)
    assert not ok and "không tồn tại" in why


def test_module1_gold_p001():
    r = eval_module1("p001")
    assert all(f["found"] for f in r["flags"]) and r["extra_flags"] == []
    assert all(f["found"] for f in r["facts"])
    assert r["forbidden_found"] == [] and r["uncited"] == []


def test_module2_gold_p001():
    r = eval_module2("p001")
    assert all(f["found"] for f in r["facts"]) and r["wrong_facts"] == []
    assert sorted(r["missing_expected"]) == sorted(r["missing_got"])
    assert all(f["found"] for f in r["flags"]) and r["extra_flags"] == []
    assert r["forbidden_found"] == []


def test_all_mock_records():
    from app.evaluate import run
    r = run()
    assert r["n_records"] >= 50 and not r["errors"]
    assert r["module1"]["flag_recall"] >= 0.95 and r["module1"]["flag_precision"] >= 0.95
    assert r["module2"]["fact_recall"] >= 0.95 and r["module2"]["flag_recall"] >= 0.95
    assert r["forbidden_found"] == 0 and r["module1"]["uncited_lines"] == 0


def test_access_control_and_audit():
    assert client.get("/api/patients/p001/summary").status_code == 401
    assert client.get("/api/patients/p001/summary", headers=ADMIN).status_code == 403
    assert client.get("/api/patients/p001/summary", headers=BINH).status_code == 403
    r = client.get("/api/patients/p001/summary", headers=BINH, params={"emergency_reason": "Bệnh nhân suy hô hấp lúc trực đêm"})
    assert r.status_code == 200
    assert client.get("/api/patients/p001/summary", headers=AN).status_code == 200
    log = client.get("/api/admin/audit", headers=ADMIN).json()
    actions = [a["action"] for a in log]
    assert any("KHẨN CẤP" in a for a in actions) and any(a.startswith("TỪ CHỐI") for a in actions)


REASON = "Bệnh nhân suy hô hấp lúc trực đêm"
EMERGENCY = {"emergency_reason": REASON}


@pytest.fixture(scope="module")
def p001_notes():
    """BS điều trị (bs.an) tạo sẵn 1 bản nháp và 1 bản đã ký duyệt cho p001."""
    def new_draft() -> str:
        r = client.post("/api/notes/draft", headers=AN, json={"patient_id": "p001", "transcript_id": "TS-2026-11-08"})
        assert r.status_code == 200
        return r.json()["note_id"]
    draft_id, approved_id = new_draft(), new_draft()
    text = client.get(f"/api/notes/{approved_id}", headers=AN).json()["ai_text"]
    assert client.post(f"/api/notes/{approved_id}/approve", headers=AN, json={"final_text": text}).status_code == 200
    src = client.get("/api/patients/p001/summary", headers=AN).json()["summary"]["sections"][0]["lines"][0]["citations"][0]["ref"]
    return {"draft": draft_id, "approved": approved_id, "src": src}


def _read_requests(ids: dict) -> list[tuple[str, str]]:
    return [
        ("summary", "/api/patients/p001/summary"),
        ("source", f"/api/patients/p001/sources/{ids['src']}"),
        ("transcript list", "/api/patients/p001/transcripts"),
        ("transcript", "/api/patients/p001/transcripts/TS-2026-11-08"),
        ("note list", "/api/patients/p001/notes"),
        ("draft note", f"/api/notes/{ids['draft']}"),
        ("approved note", f"/api/notes/{ids['approved']}"),
    ]


def _write_requests(ids: dict, extra: dict | None = None) -> list[tuple[str, str, str, dict | None]]:
    """(tên, method, path, body). `extra` gắn lý do khẩn cấp vào cả body lẫn query để chắc chắn bị bỏ qua."""
    e = extra or {}
    return [
        ("review", "post", "/api/patients/p001/summary/review", {"decision": "xác nhận", "comment": "", **e}),
        ("draft from transcript", "post", "/api/notes/draft", {"patient_id": "p001", "transcript_id": "TS-2026-11-08", **e}),
        ("draft from text", "post", "/api/notes/draft", {"patient_id": "p001", "transcript_text": "BS: Huyết áp một trăm ba mươi trên tám mươi.", **e}),
        ("approve", "post", f"/api/notes/{ids['draft']}/approve", {"final_text": "## Bị sửa\n- nội dung lạ", **e}),
        ("fhir", "get", f"/api/notes/{ids['approved']}/fhir", None),
    ]


def _call(method: str, path: str, headers: dict, body: dict | None = None, params: dict | None = None):
    if method == "get":
        return client.get(path, headers=headers, params=params)
    return client.post(path, headers=headers, json=body, params=params)


def test_attending_can_read_and_write(p001_notes):
    for name, path in _read_requests(p001_notes):
        assert client.get(path, headers=AN).status_code == 200, name
    assert client.get(f"/api/notes/{p001_notes['approved']}/fhir", headers=AN).status_code == 200
    assert client.post("/api/patients/p001/summary/review", headers=AN, json={"decision": "xác nhận"}).status_code == 200


def test_non_attending_without_reason_denied_everything(p001_notes):
    for name, path in _read_requests(p001_notes):
        assert client.get(path, headers=BINH).status_code == 403, name
    short = {"emergency_reason": "gấp quá"}  # < 10 ký tự
    for name, path in _read_requests(p001_notes):
        assert client.get(path, headers=BINH, params=short).status_code == 403, f"{name} (lý do quá ngắn)"
    for name, method, path, body in _write_requests(p001_notes):
        assert _call(method, path, BINH, body).status_code == 403, name


def test_emergency_access_is_read_only(p001_notes):
    for name, path in _read_requests(p001_notes):
        r = client.get(path, headers=BINH, params=EMERGENCY)
        assert r.status_code == 200, name
    note = client.get(f"/api/notes/{p001_notes['approved']}", headers=BINH, params=EMERGENCY).json()
    assert note["status"] == "approved" and note["final_text"]

    ts_before = client.get("/api/patients/p001/transcripts", headers=AN).json()
    notes_before = client.get("/api/patients/p001/notes", headers=AN).json()
    for name, method, path, body in _write_requests(p001_notes, EMERGENCY):
        r = _call(method, path, BINH, body, params=EMERGENCY)
        assert r.status_code == 403, name
        assert "chỉ cho xem" in r.json()["detail"], name

    # Không có gì bị ghi: không transcript mới, không note mới, bản nháp vẫn là nháp, không có rà soát của bs.binh
    assert client.get("/api/patients/p001/transcripts", headers=AN).json() == ts_before
    assert client.get("/api/patients/p001/notes", headers=AN).json() == notes_before
    assert client.get(f"/api/notes/{p001_notes['draft']}", headers=AN).json()["status"] == "draft"
    last = client.get("/api/patients/p001/summary", headers=AN).json()["last_review"]
    assert last is None or last["reviewed_by"] != "bs.binh"

    log = client.get("/api/admin/audit", headers=ADMIN).json()
    binh = [a for a in log if a["username"] == "bs.binh" and a["patient_id"] == "p001"]
    for action in ("XEM TÓM TẮT", "XEM BẢN GHI GỐC", "XEM DANH SÁCH TRANSCRIPT", "XEM TRANSCRIPT",
                   "XEM DANH SÁCH BỆNH ÁN", "XEM BỆNH ÁN"):
        assert any(a["action"] == f"{action} [KHẨN CẤP]" and REASON in a["detail"] for a in binh), action
    for action in ("DUYỆT TÓM TẮT: xác nhận", "SOẠN NHÁP BỆNH ÁN", "KÝ DUYỆT BỆNH ÁN", "XUẤT FHIR"):
        assert any(a["action"] == f"TỪ CHỐI {action}" for a in binh), action


def test_attending_of_other_patient_is_symmetric():
    """bs.an cũng chỉ đọc được hồ sơ của bs.binh khi có lý do, và không bao giờ được ghi."""
    from app.core import kb as KB
    other = next(p["id"] for p in KB.list_patients() if p.get("attending") == "bs.binh")
    assert all(p["id"] != other for p in client.get("/api/patients", headers=AN).json())  # không hiện trong danh sách bs.an
    assert client.get(f"/api/patients/{other}/summary", headers=AN).status_code == 403
    assert client.get(f"/api/patients/{other}/summary", headers=AN, params=EMERGENCY).status_code == 200
    assert client.get(f"/api/patients/{other}/transcripts", headers=AN, params=EMERGENCY).status_code == 200
    assert client.post(f"/api/patients/{other}/summary/review", headers=AN, params=EMERGENCY,
                       json={"decision": "cần sửa"}).status_code == 403
    ts = client.get(f"/api/patients/{other}/transcripts", headers=BINH).json()
    if ts:
        assert client.post("/api/notes/draft", headers=AN, json={"patient_id": other, "transcript_id": ts[0]["id"],
                                                                "emergency_reason": REASON}).status_code == 403


def test_admin_cannot_touch_patient_data(p001_notes):
    for name, path in _read_requests(p001_notes):
        assert client.get(path, headers=ADMIN, params=EMERGENCY).status_code == 403, name
    for name, method, path, body in _write_requests(p001_notes, EMERGENCY):
        assert _call(method, path, ADMIN, body).status_code == 403, name


def test_draft_approve_fhir():
    r = client.post("/api/notes/draft", headers=AN, json={"patient_id": "p001", "transcript_id": "TS-2026-11-08"})
    assert r.status_code == 200
    nid, text = r.json()["note_id"], r.json()["text"]
    assert client.get(f"/api/notes/{nid}/fhir", headers=AN).status_code == 409  # chưa duyệt
    edited = text.replace("- Mệt lắm bác sĩ ạ [L2]\n", "") + "- Bác sĩ bổ sung: dị ứng aspirin, đã hỏi lại\n"
    a = client.post(f"/api/notes/{nid}/approve", headers=AN, json={"final_text": edited})
    assert a.status_code == 200 and a.json()["stats"]["ai_lines_kept_ratio"] < 1
    f = client.get(f"/api/notes/{nid}/fhir", headers=AN).json()
    assert f["entry"][0]["resource"]["resourceType"] == "Composition"
    assert f["entry"][1]["resource"]["resourceType"] == "Provenance"
    assert client.post(f"/api/notes/{nid}/approve", headers=AN, json={"final_text": edited}).status_code == 409


def test_pasted_transcript():
    raw = "BS: Bác thấy sao?\nBN: Tôi sốt hai hôm, ho khan.\nBS: Huyết áp một trăm ba mươi trên tám mươi. Nghĩ viêm phế quản. Cho Paracetamol khi sốt."
    r = client.post("/api/notes/draft", headers=AN, json={"patient_id": "p001", "transcript_text": raw})
    assert r.status_code == 200
    d = r.json()["draft"]
    assert any(f["section"] == "S" and "2 hôm" in f["text"] for f in d["facts"])
    assert any(f["section"] == "O" and "130/80" in f["text"] for f in d["facts"])
    assert any(f["section"] == "A" for f in d["facts"])
    assert client.post("/api/notes/draft", headers=AN, json={"patient_id": "p001", "transcript_text": "xin chào"}).status_code == 422


def test_llm_output_goes_through_verifier(monkeypatch):
    """Giả lập LLM trả về 1 fact đúng, 1 fact bịa số, 1 'chẩn đoán' lấy từ lời bệnh nhân: 2 cái sau phải bị loại."""
    from app.core import llm
    from app.modules import note

    fake = {"facts": [
        {"section": "O", "field": "Dấu hiệu sinh tồn", "text": "SpO2 91%", "turns": [13]},
        {"section": "O", "field": "Dấu hiệu sinh tồn", "text": "Huyết áp 152/90", "turns": [13]},
        {"section": "A", "field": "Chẩn đoán", "text": "Xuất huyết tiêu hóa", "turns": [11]},
    ]}
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: fake)
    monkeypatch.setattr(note, "GRAPH", None)
    d = note.draft_note("p001", "TS-2026-11-08")
    monkeypatch.setattr(note, "GRAPH", None)
    assert d.mode == "llm"
    assert [f.text for f in d.facts] == ["SpO2 91%"]
    reasons = " | ".join(x["reason"] for x in d.dropped)
    assert "152" in reasons and "không do bác sĩ" in reasons
