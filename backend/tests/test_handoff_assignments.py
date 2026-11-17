"""Tiếp nhận bàn giao bằng lời + phân công bác sĩ phụ trách. Dữ liệu giả lập; môi trường tạm đặt trong conftest.py."""
import json
import threading

import pytest
from fastapi.testclient import TestClient

from app import assignments, auth
from app.core import kb as KB
from app.main import app
from app.modules import handoff

client = TestClient(app)
AN = {"Authorization": "Bearer demo-bs-an"}
BINH = {"Authorization": "Bearer demo-bs-binh"}
ADMIN = {"Authorization": "Bearer demo-admin"}
EMERGENCY = {"emergency_reason": "Trực đêm, cần xem thuốc đang dùng"}

SAMPLE = """BG: Bàn giao bệnh nhân mới vào khoa Nội tổng hợp, buồng năm giường bảy.
BG: Bệnh nhân tên Nguyễn Thị Hoa, nữ, sinh năm một nghìn chín trăm năm mươi hai.
BG: Vào viện lúc chín giờ ba mươi ngày 10/11/2025 vì đau ngực trái và khó thở.
BG: Chẩn đoán ban đầu suy tim mất bù, theo dõi hội chứng vành cấp.
BG: Tiền sử tăng huyết áp, đái tháo đường type 2.
BG: Dị ứng penicillin, nổi mề đay.
BG: Đang dùng Amlodipin 5 mg ngày 1 viên, Metformin 850 mg ngày 2 lần.
BG: Sinh hiệu mạch một trăm linh hai, nhiệt độ ba mươi bảy độ hai, huyết áp một trăm năm mươi trên chín mươi, nhịp thở hai mươi tư, SpO2 chín mươi ba phần trăm.
BG: Xét nghiệm troponin lần 1 âm tính, X-quang ngực có bóng tim to.
BG: Đang chờ kết quả troponin lần 2 lúc 15 giờ, cần theo dõi SpO2 và lượng nước tiểu.
TN: Bác sĩ điều trị là ai?
BG: Bác sĩ Bình nhận."""

CONFLICT = """BG: Ông Lê Văn Tám, bảy mươi hai tuổi, giường 3 buồng 2 khoa Nội tổng hợp.
BG: Mạch 88. Không có tiền sử dị ứng.
DD: Mạch lúc nãy em đo 120 ạ. Bệnh nhân khai dị ứng aspirin.
BG: Nhập viện ngày 09/11/2025 lúc 10 giờ tối do sốt cao."""


def runtime_files() -> set[str]:
    out = set()
    for d in (KB.RUNTIME_PATIENTS, KB.RUNTIME_TS):
        if d.exists():
            out |= {f"{d.name}/{p.name}" for p in d.iterdir()}
    return out


def audit_actions(username: str) -> list[dict]:
    return [a for a in client.get("/api/admin/audit", headers=ADMIN).json() if a["username"] == username]


def form_from(draft: dict, **over) -> dict:
    """Biến bản nháp thành dữ liệu xác nhận như giao diện gửi lên."""
    f = {k: v["value"] for k, v in draft["fields"].items()}
    vit = {k: f[k] for k in ("pulse", "temp", "bp", "resp_rate", "spo2", "weight")}
    vit = {k: (None if v is None else v if k == "bp" else float(v) if k in ("temp", "weight") else int(v)) for k, v in vit.items()}
    body = {
        "transcript_text": over.pop("transcript_text", SAMPLE), "name": f["name"], "birth_year": int(f["birth_year"]),
        "gender": f["gender"], "ward": f["ward"], "room": f["room"], "bed": f["bed"],
        "admitted_at": f"{f['admitted_date']}T{f['admitted_time']}", "reason": f["reason"], "vitals": vit,
        **{k: [i["text"] for i in draft["lists"][k]] for k in handoff.LIST_KEYS},
        "allergy_status": draft["allergy_status"]["value"] or "unknown", "acknowledged_warnings": True,
    }
    body.update(over)
    return body


def parse(text: str = SAMPLE, headers=AN) -> dict:
    r = client.post("/api/handoffs/parse", headers=headers, json={"transcript_text": text})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- parse
def test_parse_extracts_structured_draft_without_saving():
    before = runtime_files()
    d = parse()
    f = d["fields"]
    assert (f["name"]["value"], f["birth_year"]["value"], f["gender"]["value"]) == ("Nguyễn Thị Hoa", "1952", "Nữ")
    assert (f["ward"]["value"], f["room"]["value"], f["bed"]["value"]) == ("Khoa Nội tổng hợp", "5", "7")
    assert (f["admitted_date"]["value"], f["admitted_time"]["value"]) == ("2025-11-10", "09:30")
    assert f["reason"]["value"] == "Đau ngực trái và khó thở" and f["reason"]["turns"] == [3]
    assert [f[k]["value"] for k in ("pulse", "temp", "bp", "resp_rate", "spo2")] == ["102", "37.2", "150/90", "24", "93"]
    assert f["attending_spoken"]["value"] == "Bình" and "không phân công" in " ".join(f["attending_spoken"]["notes"])
    L = {k: [i["text"] for i in v] for k, v in d["lists"].items()}
    assert L["diagnoses"] == ["Suy tim mất bù", "Theo dõi hội chứng vành cấp"]
    assert d["lists"]["diagnoses"][1]["status"] == "uncertain"
    assert L["comorbidities"] == ["Tăng huyết áp", "Đái tháo đường type 2"]
    assert L["allergies"] == ["Penicillin, nổi mề đay"] and d["allergy_status"]["value"] == "has"
    assert L["meds"] == ["Amlodipin 5 mg ngày 1 viên", "Metformin 850 mg ngày 2 lần"]
    assert len(L["labs"]) == 2 and any("troponin lần 2" in x for x in L["pending"])
    assert d["missing_required"] == [] and d["mode"] == "offline" and d["dropped"] == []
    assert all(i["turns"] for v in d["lists"].values() for i in v)  # mọi mục đều có lượt nói dẫn chứng
    assert runtime_files() == before, "parse không được ghi file"
    assert any(a["action"] == "PHÂN TÍCH BÀN GIAO" and "chưa lưu" in a["detail"] for a in audit_actions("bs.an"))


@pytest.mark.parametrize("text", ["", "   \n  \n", "BG:   ", "...\n---"])
def test_parse_rejects_empty_transcript(text):
    r = client.post("/api/handoffs/parse", headers=AN, json={"transcript_text": text})
    assert r.status_code == 422 and "trống" in r.json()["detail"]


def test_parse_rejects_bad_input():
    assert client.post("/api/handoffs/parse", headers=AN, json={"transcript_text": "x" * 20001}).status_code == 422
    assert client.post("/api/handoffs/parse", headers=AN, json={"transcript_text": 123}).status_code == 422
    assert client.post("/api/handoffs/parse", headers=AN, json={"transcript_text": "BG: a", "patient_id": "p001"}).status_code == 422
    assert client.post("/api/handoffs/parse", json={"transcript_text": SAMPLE}).status_code == 401
    assert any(a["action"] == "TỪ CHỐI PHÂN TÍCH BÀN GIAO" for a in audit_actions("bs.an"))


def test_parse_marks_missing_conflict_and_uncertain():
    d = parse("BG: Bệnh nhân nam, khoảng 60 tuổi, vào viện vì sốt.")
    assert {"name", "ward", "room", "bed", "admitted_date", "admitted_time"} <= set(d["missing_required"])
    assert d["fields"]["birth_year"]["status"] == "uncertain"  # tính từ tuổi + "khoảng"
    d = parse(CONFLICT)
    f = d["fields"]
    assert f["name"]["value"] == "Lê Văn Tám"  # "Tám" không bị chuẩn hóa thành số 8
    assert f["pulse"]["status"] == "conflict" and {a["value"] for a in f["pulse"]["alternatives"]} == {"88", "120"}
    assert d["allergy_status"]["status"] == "conflict"
    assert f["gender"]["status"] == "uncertain" and f["gender"]["value"] == "Nam"  # suy ra từ "Ông"
    assert f["admitted_time"]["value"] == "22:00" and d["flag_count"] >= 4


def test_llm_output_is_validated_and_grounded(monkeypatch):
    from app.core import llm

    fake = {"fields": {"name": [{"value": "Nguyễn Thị Hoa", "quote": "Bệnh nhân tên Nguyễn Thị Hoa", "turn": 2}],
                       "pulse": [{"value": "130", "quote": "mạch 102", "turn": 8}]},
            "lists": {"diagnoses": [{"value": "Suy tim mất bù", "quote": "suy tim mất bù", "turn": 4},
                                    {"value": "Nhồi máu cơ tim cấp", "quote": "đau ngực trái", "turn": 3}],
                      "meds": [{"value": "Warfarin 5 mg", "quote": "Amlodipin 5 mg ngày 1 viên", "turn": 7},
                               {"value": "Aspirin 81 mg", "quote": "Aspirin 81 mg mỗi sáng", "turn": 7}],
                      "labs": [{"value": "Troponin tăng", "quote": "troponin lần 1 âm tính", "turn": 99}]},
            "allergy_status": []}
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: fake)
    d = parse()
    assert d["mode"] == "llm"
    dx = [i["text"] for i in d["lists"]["diagnoses"]]
    meds = [i["text"] for i in d["lists"]["meds"]]
    assert "Nhồi máu cơ tim cấp" not in dx and "Suy tim mất bù" in dx
    assert not any("Warfarin" in m or "Aspirin" in m for m in meds)
    assert d["fields"]["pulse"]["value"] == "102" and d["fields"]["pulse"]["status"] == "ok"
    reasons = {x["value"]: x["reason"] for x in d["dropped"] if x["source"] == "LLM"}
    assert set(reasons) == {"130", "Nhồi máu cơ tim cấp", "Warfarin 5 mg", "Aspirin 81 mg", "Troponin tăng"}
    assert "trích dẫn không có" in reasons["Aspirin 81 mg"] and "không tồn tại" in reasons["Troponin tăng"]

    # LLM trả sai cấu trúc -> Pydantic từ chối, quay về quy tắc
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"fields": {"patient_id": [{"value": "p001"}]}})
    d = parse()
    assert d["mode"] == "offline" and any("sai cấu trúc" in w for w in d["warnings"])


# ---------------------------------------------------------------- confirm
def test_confirm_by_doctor_creates_patient_assigned_to_self():
    gold_before = sorted(p.name for p in (KB.DATA / "gold").iterdir())
    base_before = sorted(p.name for p in (KB.DATA / "patients").iterdir())
    d = parse()
    r = client.post("/api/handoffs/confirm", headers=AN, json=form_from(d))
    assert r.status_code == 200, r.text
    pid, tid = r.json()["patient_id"], r.json()["transcript_id"]
    assert pid not in base_before and pid.startswith("p") and int(pid[1:]) > 81
    assert r.json()["assignment"]["doctor"] == "bs.an" and r.json()["assignment"]["status"] == "accepted"
    assert (KB.RUNTIME_PATIENTS / f"{pid}.json").exists() and (KB.RUNTIME_TS / f"{tid}.json").exists()
    rec = json.loads((KB.RUNTIME_PATIENTS / f"{pid}.json").read_text(encoding="utf-8"))
    assert rec["patient"]["attending"] is None  # JSON không ghi bác sĩ; phân công nằm trong DB
    assert rec["handoff"]["transcript_id"] == tid and rec["patient"]["bed"] == "Buồng 5 - Giường 7"
    assert json.loads((KB.RUNTIME_TS / f"{tid}.json").read_text(encoding="utf-8"))["patient_id"] == pid
    assert sorted(p.name for p in (KB.DATA / "gold").iterdir()) == gold_before
    assert sorted(p.name for p in (KB.DATA / "patients").iterdir()) == base_before

    assert any(p["id"] == pid and not p["is_new"] for p in client.get("/api/patients", headers=AN).json())
    s = client.get(f"/api/patients/{pid}/summary", headers=AN).json()
    assert s["patient"]["name"] == "Nguyễn Thị Hoa" and s["can_write"]
    keys = {sec["key"]: sec for sec in s["summary"]["sections"]}
    assert any("Suy tim" in l["text"] for l in keys["ban_giao"]["lines"]) and s["summary"]["dropped"] == []
    assert {m["ingredient"] for m in s["summary"]["active_meds"]} == {"amlodipine", "metformin"}
    assert [a["substance"] for a in s["summary"]["allergies"]] == ["Penicillin, nổi mề đay"]
    assert client.get(f"/api/patients/{pid}/transcripts/{tid}", headers=AN).status_code == 200
    assert any(a["action"] == "TIẾP NHẬN BÀN GIAO" and a["patient_id"] == pid for a in audit_actions("bs.an"))
    assert assignments.history(pid)[0]["action"] == "intake"


def test_confirm_ids_are_unique_even_in_parallel():
    body = form_from(parse())
    pids, errors = [], []

    def go():
        r = client.post("/api/handoffs/confirm", headers=AN, json=body)
        (pids.append(r.json()["patient_id"]) if r.status_code == 200 else errors.append(r.text))

    threads = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors and len(pids) == 6 and len(set(pids)) == 6
    assert not list(KB.RUNTIME_PATIENTS.glob("*.lock")) and not list(KB.RUNTIME_PATIENTS.glob("*.tmp"))


def test_write_new_never_overwrites(tmp_path):
    target = tmp_path / "p999.json"
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        handoff._write_new(target, {"x": 1})
    assert target.read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("over, needle", [
    ({"patient_id": "p001"}, "patient_id"),
    ({"attending": "bs.binh"}, "attending"),
    ({"birth_year": 1800}, "Năm sinh"),
    ({"gender": "X"}, "Giới tính"),
    ({"name": "12345"}, "Họ tên"),
    ({"room": "../../etc"}, "Buồng"),
    ({"bed": ""}, "Giường"),
    ({"admitted_at": "2999-01-01T10:00"}, "tương lai"),
    ({"admitted_at": "không phải ngày"}, "Thời điểm vào viện"),
    ({"vitals": {"bp": "90/150"}}, "huyết áp"),
    ({"vitals": {"spo2": 140}}, "SpO2"),
    ({"vitals": {"glucose": 8}}, "glucose"),
    ({"allergy_status": "none"}, "dị ứng"),
    ({"reason": ""}, "Lý do vào viện"),
    ({"diagnoses": ["x" * 301]}, "Chẩn đoán"),
    ({"transcript_text": "   "}, "trống"),
    ({"acknowledged_warnings": False, "transcript_text": CONFLICT}, "xác nhận đã kiểm tra"),
])
def test_confirm_rejects_invalid_data(over, needle):
    d = parse()
    before = runtime_files()
    r = client.post("/api/handoffs/confirm", headers=AN, json=form_from(d, **over))
    assert r.status_code == 422, r.text
    assert needle.lower() in r.json()["detail"].lower()
    assert runtime_files() == before, "dữ liệu sai không được tạo file"
    assert audit_actions("bs.an")[0]["action"] == "TỪ CHỐI TIẾP NHẬN BÀN GIAO"
    assert "Nguyễn" not in audit_actions("bs.an")[0]["detail"]  # audit không chứa nội dung lâm sàng


def admin_intake() -> str:
    r = client.post("/api/handoffs/confirm", headers=ADMIN, json=form_from(parse(headers=ADMIN)))
    assert r.status_code == 200, r.text
    assert r.json()["assignment"]["status"] == "unassigned" and r.json()["assignment"]["doctor"] is None
    return r.json()["patient_id"]


def rows() -> dict[str, dict]:
    return {p["id"]: p for p in client.get("/api/admin/assignments", headers=ADMIN).json()["patients"]}


# ---------------------------------------------------------------- phân công
def test_admin_intake_is_unassigned_and_hidden():
    pid = admin_intake()
    assert rows()[pid]["status"] == "unassigned"
    for h in (AN, BINH):
        assert all(p["id"] != pid for p in client.get("/api/patients", headers=h).json())
        assert client.get(f"/api/patients/{pid}/summary", headers=h).status_code == 403
    assert client.get(f"/api/patients/{pid}/summary", headers=ADMIN).status_code == 403  # admin không mở bệnh án


def test_assign_accept_and_write_flow():
    pid = admin_intake()
    v = rows()[pid]["version"]
    r = client.post("/api/admin/assignments", headers=ADMIN,
                    json={"patient_id": pid, "doctor": "bs.binh", "note": "Nhận từ cấp cứu", "expected_version": v})
    assert r.status_code == 200 and r.json()["to"] == "bs.binh"
    assert rows()[pid]["status"] == "pending" and rows()[pid]["assigned_at"]
    mine = {p["id"]: p for p in client.get("/api/patients", headers=BINH).json()}
    assert mine[pid]["is_new"] and mine[pid]["assignment_status"] == "pending"
    s = client.get(f"/api/patients/{pid}/summary", headers=BINH).json()
    assert s["assignment"]["status"] == "pending" and not s["can_write"]
    r = client.post(f"/api/patients/{pid}/summary/review", headers=BINH, json={"decision": "xác nhận"})
    assert r.status_code == 403 and "Tiếp nhận hồ sơ" in r.json()["detail"]
    assert client.post(f"/api/patients/{pid}/accept-assignment", headers=AN).status_code == 403  # không được giao
    assert client.post(f"/api/patients/{pid}/accept-assignment", headers=ADMIN).status_code == 403
    r = client.post(f"/api/patients/{pid}/accept-assignment", headers=BINH)
    assert r.status_code == 200 and r.json()["accepted_by"] == "bs.binh" and r.json()["accepted_at"]
    assert client.post(f"/api/patients/{pid}/accept-assignment", headers=BINH).status_code == 409
    assert rows()[pid]["status"] == "accepted" and rows()[pid]["accepted_by"] == "bs.binh"
    assert not {p["id"]: p for p in client.get("/api/patients", headers=BINH).json()}[pid]["is_new"]
    assert client.post(f"/api/patients/{pid}/summary/review", headers=BINH, json={"decision": "xác nhận"}).status_code == 200
    # gán lại cho hồ sơ đã có bác sĩ bằng /assignments phải đi qua /transfer
    r = client.post("/api/admin/assignments", headers=ADMIN,
                    json={"patient_id": pid, "doctor": "bs.an", "expected_version": rows()[pid]["version"]})
    assert r.status_code == 409 and "Chuyển hồ sơ" in r.json()["detail"]


def an_patient(i: int) -> str:
    return [p["id"] for p in KB.list_patients() if p.get("attending") == "bs.an" and p["id"] != "p001"][i]


def test_transfer_an_to_binh_blocks_old_doctor():
    pid = an_patient(0)
    ts = client.get(f"/api/patients/{pid}/transcripts", headers=AN).json()
    note_id = None
    if ts:
        note_id = client.post("/api/notes/draft", headers=AN, json={"patient_id": pid, "transcript_id": ts[0]["id"]}).json()["note_id"]
    v = rows()[pid]["version"]
    assert v == 0 and rows()[pid]["doctor"] == "bs.an" and rows()[pid]["status"] == "accepted"  # mặc định từ JSON
    url = f"/api/admin/assignments/{pid}/transfer"
    r = client.post(url, headers=ADMIN, json={"doctor": "bs.binh", "reason": "", "expected_version": v})
    assert r.status_code == 422 and "lý do" in r.json()["detail"]
    r = client.post(url, headers=ADMIN, json={"doctor": "bs.an", "reason": "Không đổi người", "expected_version": v})
    assert r.status_code == 422
    r = client.post(url, headers=ADMIN, json={"doctor": "bs.binh", "reason": "BS An nghỉ phép 1 tuần", "expected_version": v})
    assert r.status_code == 200 and (r.json()["from"], r.json()["to"]) == ("bs.an", "bs.binh")
    src = json.loads((KB.DATA / "patients" / f"{pid}.json").read_text(encoding="utf-8"))
    assert src["patient"]["attending"] == "bs.an", "JSON nguồn không bị sửa"

    # bác sĩ cũ: không còn trong danh sách, chỉ đọc qua khẩn cấp, mọi thao tác ghi bị chặn
    assert all(p["id"] != pid for p in client.get("/api/patients", headers=AN).json())
    assert client.get(f"/api/patients/{pid}/summary", headers=AN).status_code == 403
    assert client.get(f"/api/patients/{pid}/summary", headers=AN, params=EMERGENCY).status_code == 200
    assert client.post(f"/api/patients/{pid}/summary/review", headers=AN, params=EMERGENCY, json={"decision": "xác nhận"}).status_code == 403
    if ts:
        assert client.post("/api/notes/draft", headers=AN, json={"patient_id": pid, "transcript_id": ts[0]["id"]}).status_code == 403
        r = client.post(f"/api/notes/{note_id}/approve", headers=AN, json={"final_text": "## A\n- sửa"})
        assert r.status_code == 403
        assert client.get(f"/api/notes/{note_id}", headers=AN).json()["detail"]  # 403 detail
        # bác sĩ mới: phải tiếp nhận trước rồi mới ký được
        assert client.post(f"/api/notes/{note_id}/approve", headers=BINH, json={"final_text": "## A\n- x"}).status_code == 403
    assert client.post(f"/api/patients/{pid}/accept-assignment", headers=BINH).status_code == 200
    assert client.get(f"/api/patients/{pid}/summary", headers=BINH).json()["can_write"]

    h = client.get(f"/api/admin/assignments/{pid}/history", headers=ADMIN).json()
    assert [x["action"] for x in h["history"]] == ["accept", "transfer"]
    t = h["history"][1]
    assert (t["from_doctor"], t["to_doctor"], t["by_user"], t["reason"]) == ("bs.an", "bs.binh", "admin", "BS An nghỉ phép 1 tuần")
    log = [a for a in audit_actions("admin") if a["patient_id"] == pid]
    assert any(a["action"] == "CHUYỂN HỒ SƠ" and "bs.an → bs.binh" in a["detail"] and "nghỉ phép" in a["detail"]
               and "thành công" in a["detail"] for a in log)
    assert any(a["action"] == "TỪ CHỐI CHUYỂN HỒ SƠ" and "thất bại" in a["detail"] for a in log)


def test_bulk_assignment_is_all_or_nothing():
    p1, p2 = admin_intake(), admin_intake()
    p3 = an_patient(1)  # đang do bs.an phụ trách
    r0 = rows()
    items = [{"patient_id": p, "expected_version": r0[p]["version"]} for p in (p1, p2, p3)]
    r = client.post("/api/admin/assignments/bulk", headers=ADMIN, json={"items": items, "doctor": "bs.binh", "note": ""})
    assert r.status_code == 422 and p3 in r.json()["detail"]
    assert rows()[p1]["status"] == "unassigned", "lỗi một hồ sơ thì không hồ sơ nào bị đổi"
    stale = [dict(i) for i in items]
    stale[1]["expected_version"] += 5
    r = client.post("/api/admin/assignments/bulk", headers=ADMIN, json={"items": stale, "doctor": "bs.binh", "note": "Chia lại ca trực"})
    assert r.status_code == 409 and rows()[p1]["status"] == "unassigned"
    r = client.post("/api/admin/assignments/bulk", headers=ADMIN, json={"items": items, "doctor": "bs.binh", "note": "Chia lại ca trực"})
    assert r.status_code == 200
    assert [x["action"] for x in r.json()["results"]] == ["assign", "assign", "transfer"]
    after = rows()
    assert all(after[p]["doctor"] == "bs.binh" and after[p]["status"] == "pending" for p in (p1, p2, p3))
    log = audit_actions("admin")
    assert sum(a["action"] == "PHÂN CÔNG HÀNG LOẠT" and a["patient_id"] in (p1, p2, p3) for a in log) == 3
    doctors = {d["username"]: d for d in client.get("/api/admin/assignments", headers=ADMIN).json()["doctors"]}
    assert set(doctors) == {"bs.an", "bs.binh"} and doctors["bs.binh"]["pending"] >= 3


def test_only_admin_can_assign():
    pid = an_patient(2)
    v = rows()[pid]["version"]
    calls = [("get", "/api/admin/assignments", None),
             ("post", "/api/admin/assignments", {"patient_id": pid, "doctor": "bs.binh", "expected_version": v}),
             ("post", "/api/admin/assignments/bulk", {"items": [{"patient_id": pid, "expected_version": v}], "doctor": "bs.binh"}),
             ("post", f"/api/admin/assignments/{pid}/transfer", {"doctor": "bs.binh", "reason": "thử quyền", "expected_version": v}),
             ("get", f"/api/admin/assignments/{pid}/history", None)]
    for method, url, body in calls:
        for h in (AN, BINH):
            r = client.get(url, headers=h) if method == "get" else client.post(url, headers=h, json=body)
            assert r.status_code == 403, url
        r = client.get(url) if method == "get" else client.post(url, json=body)
        assert r.status_code == 401, url
    assert rows()[pid]["version"] == v


@pytest.mark.parametrize("doctor, needle", [("bs.khong-ton-tai", "Không có tài khoản"), ("admin", "quản trị"), ("", "Cần chọn")])
def test_rejects_unknown_or_wrong_role_doctor(doctor, needle):
    pid = an_patient(3)
    v = rows()[pid]["version"]
    r = client.post(f"/api/admin/assignments/{pid}/transfer", headers=ADMIN,
                    json={"doctor": doctor, "reason": "Đổi bác sĩ phụ trách", "expected_version": v})
    assert r.status_code == 422 and needle in r.json()["detail"]
    with pytest.raises(assignments.AssignError):
        assignments.check_doctor(doctor)
    assert rows()[pid]["version"] == v and rows()[pid]["doctor"] == "bs.an"
    assert audit_actions("admin")[0]["action"] == "TỪ CHỐI CHUYỂN HỒ SƠ"


def test_stale_version_and_concurrent_transfers():
    pid = an_patient(4)
    v = rows()[pid]["version"]
    admin = {"username": "admin", **auth.USERS["admin"]}
    barrier, results = threading.Barrier(4), []

    def go(i):
        barrier.wait()
        try:
            results.append(("ok", assignments.transfer(admin, pid, "bs.binh", f"Yêu cầu đồng thời {i}", v)))
        except assignments.AssignError as e:
            results.append((e.status, str(e)))

    threads = [threading.Thread(target=go, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(str(r[0]) for r in results) == ["409", "409", "409", "ok"]
    a = assignments.current(pid)
    assert a["doctor"] == "bs.binh" and a["version"] == v + 1
    assert [h["action"] for h in assignments.history(pid)] == ["transfer"]  # đúng một lần chuyển
    # admin khác bấm tiếp với phiên bản cũ qua API -> 409, không ghi đè
    r = client.post(f"/api/admin/assignments/{pid}/transfer", headers=ADMIN,
                    json={"doctor": "bs.an", "reason": "Trả lại cho BS An", "expected_version": v})
    assert r.status_code == 409 and assignments.current(pid)["doctor"] == "bs.binh"


def test_history_unknown_patient_404():
    assert client.get("/api/admin/assignments/p99999/history", headers=ADMIN).status_code == 404
    assert client.get("/api/admin/assignments/..%2Fkb/history", headers=ADMIN).status_code == 404
