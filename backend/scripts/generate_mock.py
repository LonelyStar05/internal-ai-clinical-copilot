"""Sinh bộ hồ sơ GIẢ LẬP cho Khoa Nội tổng hợp, kèm transcript buổi khám và đáp án vàng.

    python scripts/generate_mock.py --n 80 --seed 29

Mỗi hồ sơ gồm: hành chính, 2–6 lần khám cũ (Vinmec + đôi khi bệnh viện ngoài), đơn thuốc, xét nghiệm theo thời gian,
hẹn cận lâm sàng, đợt nội trú hiện tại (lý do, sinh hiệu, xét nghiệm, X-quang) và 1 transcript buổi khám.
Các "bẫy" (cờ cần phát hiện) được cài ngẫu nhiên với xác suất cố định; đáp án vàng ghi lại đúng những gì đã cài.

LƯU Ý: Đáp án sinh cùng lúc với dữ liệu, dùng chung danh sách tương tác thuốc với hệ thống. Điểm trên bộ này đo độ
bền của pipeline với nhiều biến thể, KHÔNG thay thế đánh giá trên ca do bác sĩ viết.
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "app" / "data"
KB = json.loads((ROOT / "kb.json").read_text(encoding="utf-8"))
PAIRS = {frozenset((i["a"], i["b"])) for i in KB["interactions"]}

# ------------------------------------------------------------------ số -> chữ tiếng Việt
U = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]


def words(n: int) -> str:
    if n < 10:
        return U[n]
    if n < 20:
        r = n % 10
        return "mười" if r == 0 else "mười " + ("lăm" if r == 5 else U[r])
    if n < 100:
        t, r = divmod(n, 10)
        tail = {0: "", 1: " mốt", 4: " tư", 5: " lăm"}.get(r, " " + U[r])
        return f"{U[t]} mươi{tail}"
    h, r = divmod(n, 100)
    if r == 0:
        return f"{U[h]} trăm"
    if r < 10:
        return f"{U[h]} trăm linh {U[r]}"
    return f"{U[h]} trăm {words(r)}"


def dec_words(x: float) -> str:
    i, f = int(x), round((x - int(x)) * 10)
    return words(i) if f == 0 else f"{words(i)} phẩy {U[f]}"


def vnum(x: float) -> str:
    return (f"{x:.1f}".rstrip("0").rstrip(".")).replace(".", ",")


# ------------------------------------------------------------------ danh mục giả lập
HO = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Vũ", "Đặng", "Bùi", "Đỗ", "Ngô", "Dương", "Lý"]
DEM_NAM, DEM_NU = ["Văn", "Đức", "Minh", "Quang", "Hữu", "Xuân"], ["Thị", "Thu", "Ngọc", "Thanh", "Minh"]
TEN_NAM = ["Hùng", "Dũng", "Tuấn", "Long", "Sơn", "Hải", "Nam", "Phúc", "Thắng", "Quân", "Khải", "Tâm"]
TEN_NU = ["Lan", "Hoa", "Mai", "Hương", "Hạnh", "Nga", "Thủy", "Yến", "Liên", "Hằng", "Dung", "Loan"]
QUAN = ["Hoàng Mai", "Hai Bà Trưng", "Thanh Xuân", "Long Biên", "Gia Lâm", "Đống Đa", "Cầu Giấy", "Hà Đông"]
BS = ["BS. Nguyễn Thu", "BS. Phạm Minh", "BS. Lê Hà", "BS. Đỗ Quang", "BS. Vũ Hạnh", "BS. Trịnh Sơn"]
BV_NGOAI = ["Giấy ra viện BV đa khoa tỉnh (scan PDF)", "Giấy ra viện BV huyện (ảnh chụp)", "Đơn thuốc phòng khám tư (ảnh chụp)"]

CHRONIC = {
    "E11": {"display": "Đái tháo đường type 2", "spec": "Khám nội tiết",
            "meds": [("metformin", "Metformin 850 mg", "850 mg x 2 lần/ngày"), ("gliclazide", "Diamicron MR 30 mg", "30 mg x 1 lần/ngày")]},
    "I10": {"display": "Tăng huyết áp", "spec": "Khám tim mạch",
            "meds": [("amlodipine", "Amlodipin 5 mg", "5 mg x 1 lần/ngày"), ("losartan", "Losartan 50 mg", "50 mg x 1 lần/ngày")]},
    "I48": {"display": "Rung nhĩ", "spec": "Khám tim mạch",
            "meds": [("apixaban", "Apixaban 5 mg", "5 mg x 2 lần/ngày"), ("bisoprolol", "Bisoprolol 2,5 mg", "2,5 mg x 1 lần/ngày")],
            "alt": [("warfarin", "Warfarin 2 mg", "2 mg x 1 lần/ngày")]},
    "I50": {"display": "Suy tim", "spec": "Khám tim mạch",
            "meds": [("furosemide", "Furosemid 40 mg", "40 mg x 1 lần/ngày"), ("bisoprolol", "Bisoprolol 2,5 mg", "2,5 mg x 1 lần/ngày")]},
    "J44": {"display": "Bệnh phổi tắc nghẽn mạn tính", "spec": "Khám hô hấp",
            "meds": [("salbutamol", "Ventolin xịt 100 mcg", "2 nhát khi khó thở")]},
    "E78": {"display": "Rối loạn lipid máu", "spec": "Khám nội",
            "meds": [("atorvastatin", "Atorvastatin 20 mg", "20 mg x 1 lần/ngày")]},
    "M10": {"display": "Gút", "spec": "Khám cơ xương khớp",
            "meds": [("allopurinol", "Allopurinol 300 mg", "300 mg x 1 lần/ngày")]},
    "I25": {"display": "Bệnh tim thiếu máu cục bộ mạn", "spec": "Khám tim mạch",
            "meds": [("clopidogrel", "Plavix 75 mg", "75 mg x 1 lần/ngày"), ("atorvastatin", "Atorvastatin 20 mg", "20 mg x 1 lần/ngày")]},
}
# Biệt dược dùng cho bẫy trùng hoạt chất
BRAND_TWIN = {"amlodipine": ("Amlor 5 mg", "5 mg x 1 lần/ngày"), "metformin": ("Glucophage 850 mg", "850 mg x 2 lần/ngày"),
              "atorvastatin": ("Lipitor 20 mg", "20 mg x 1 lần/ngày"), "losartan": ("Cozaar 50 mg", "50 mg x 1 lần/ngày")}

ACUTE = {
    "pneumonia": {
        "reason": "Sốt, ho đờm, khó thở", "xray": "Đám mờ thùy dưới phổi {side}.",
        "assess": "Nghe phù hợp viêm phổi cộng đồng phổi {side}", "assess_kw": "viêm phổi",
        "plan_drugs": [("Augmentin", "Cho Augmentin truyền tĩnh mạch")],
        "macrolide": "Clarithromycin",
    },
    "copd": {
        "reason": "Khó thở tăng, ho khạc đờm nhiều", "xray": "Phổi tăng sáng, không thấy đám mờ khu trú.",
        "assess": "Nghĩ đợt cấp bệnh phổi tắc nghẽn mạn tính", "assess_kw": "bệnh phổi tắc nghẽn",
        "plan_drugs": [("Salbutamol", "Cho khí dung Salbutamol"), ("Prednisolon", "Prednisolon 40 mg uống buổi sáng")],
        "macrolide": "Levofloxacin",
    },
    "hf": {
        "reason": "Khó thở khi nằm, phù hai chân", "xray": "Bóng tim to, xung huyết hai phổi.",
        "assess": "Phù hợp suy tim mất bù", "assess_kw": "suy tim",
        "plan_drugs": [("Furosemid", "Cho Furosemid tiêm tĩnh mạch")],
        "macrolide": None,
    },
    "uti": {
        "reason": "Sốt rét run, tiểu buốt", "xray": "Không thấy tổn thương nhu mô phổi.",
        "assess": "Nghĩ nhiễm khuẩn tiết niệu", "assess_kw": "nhiễm khuẩn tiết niệu",
        "plan_drugs": [("Ceftriaxone", "Cho Ceftriaxone truyền tĩnh mạch")],
        "macrolide": "Levofloxacin",
    },
}


def pick(rng, xs):
    return xs[rng.randrange(len(xs))]


def iso(d: date) -> str:
    return d.isoformat()


# ------------------------------------------------------------------ một hồ sơ
def make_patient(idx: int, rng: random.Random) -> tuple[dict, dict, dict]:
    pid = f"p{idx:03d}"
    used_ids: set[str] = set()

    def uid(prefix: str, d: date) -> str:
        base, k = f"{prefix}-{iso(d)}", 1
        out = base
        while out in used_ids:
            k += 1
            out = f"{base}-{k}"
        used_ids.add(out)
        return out
    male = rng.random() < 0.55
    name = f"{pick(rng, HO)} {pick(rng, DEM_NAM if male else DEM_NU)} {pick(rng, TEN_NAM if male else TEN_NU)}"
    birth = rng.randint(1940, 1975)
    adm_day = date(2026, 10, 1) + timedelta(days=rng.randint(0, 40))
    acute = pick(rng, list(ACUTE))
    if acute == "copd":
        conds = ["J44"]
    elif acute == "hf":
        conds = ["I50"]
    else:
        conds = []
    pool = [c for c in CHRONIC if c not in conds and c != "J44" and c != "I50"]
    rng.shuffle(pool)
    conds += pool[: rng.randint(1, 3)]

    traps = {
        "duplicate": rng.random() < 0.25,
        "unresolved_k": rng.random() < 0.25,
        "allergy_conflict": rng.random() < 0.2,
        "renal_metformin": rng.random() < 0.3,
        "missing_result": rng.random() < 0.25,
        "ddi_active": rng.random() < 0.2,
    }
    if traps["renal_metformin"] and "E11" not in conds:
        conds.append("E11")
    if traps["unresolved_k"] or traps["ddi_active"]:
        if "I10" not in conds:
            conds.append("I10")

    res: list[dict] = []
    gold1_flags: dict[str, dict] = {}
    gold1_facts: list[dict] = []
    start = adm_day - timedelta(days=rng.randint(500, 1100))

    # ---------------- lần khám + đơn thuốc
    active: dict[str, dict] = {}
    enc_dates = sorted({start + timedelta(days=rng.randint(0, (adm_day - start).days - 30)) for _ in range(rng.randint(2, 5))} | {start})
    cond_first: dict[str, str] = {}
    vinmec_encs = []
    for k, d in enumerate(enc_dates):
        c = conds[k % len(conds)] if k < len(conds) else pick(rng, conds)
        info = CHRONIC[c]
        doc = pick(rng, BS)
        eid = uid("KB", d)
        enc = {"id": eid, "type": "Encounter", "date": iso(d), "source": f"Vinmec - {info['spec']}", "practitioner": doc,
               "diagnoses": [{"code": c, "display": info["display"]}], "allergies_recorded": None, "text": ""}
        new_meds = []
        meds = list(info["meds"])
        if c == "I48" and rng.random() < 0.35:
            meds[0] = info["alt"][0]
        for ing, nm, dose in meds:
            if ing in active:
                continue
            clash = [a for a in active if frozenset((a, ing)) in PAIRS]
            if clash:
                continue
            rid = f"RX-{eid[3:]}-{len(new_meds) + 1}"
            rx = {"id": rid, "type": "MedicationRequest", "date": iso(d), "encounter": eid, "source": "Vinmec",
                  "practitioner": doc, "drug_name": nm, "dose": dose, "status": "active"}
            res.append(rx)
            active[ing] = rx
            new_meds.append(f"{nm} {dose}")
        enc["text"] = f"Chẩn đoán {info['display'].lower()}." + (f" Kê {', '.join(new_meds)}." if new_meds else " Tiếp tục thuốc cũ.")
        cond_first.setdefault(c, eid)
        res.append(enc)
        vinmec_encs.append(enc)

    for c, eid in cond_first.items():
        gold1_facts.append({"id": f"dx-{c}", "contains": CHRONIC[c]["display"], "must_cite": [eid]})

    last_enc = vinmec_encs[-1]
    last_date = date.fromisoformat(last_enc["date"])

    # Bẫy: trùng hoạt chất (biệt dược do bác sĩ khác kê ở lần khám sau)
    twin = [i for i in active if i in BRAND_TWIN]
    if traps["duplicate"] and twin:
        ing = pick(rng, twin)
        nm, dose = BRAND_TWIN[ing]
        d = last_date + timedelta(days=rng.randint(10, 25))
        eid = uid("KB", d)
        doc = pick(rng, [b for b in BS if b != active[ing]["practitioner"]])
        rid = f"RX-{eid[3:]}-9"
        res.append({"id": eid, "type": "Encounter", "date": iso(d), "source": "Vinmec - Khám nội", "practitioner": doc,
                    "diagnoses": [], "allergies_recorded": None, "text": f"Tái khám. Kê {nm} {dose}."})
        res.append({"id": rid, "type": "MedicationRequest", "date": iso(d), "encounter": eid, "source": "Vinmec",
                    "practitioner": doc, "drug_name": nm, "dose": dose, "status": "active"})
        gold1_flags["dup"] = {"kind": "duplicate_ingredient", "must_cite": [active[ing]["id"], rid]}
    else:
        traps["duplicate"] = False

    # Bẫy: tương tác giữa 2 thuốc đang dùng
    if traps["ddi_active"]:
        cand = [("spironolactone", "Verospiron 25 mg", "25 mg x 1 lần/ngày", "losartan"),
                ("omeprazole", "Omeprazol 20 mg", "20 mg x 1 lần/ngày", "clopidogrel")]
        options = [c for c in cand if c[3] in active and c[0] not in active]
        if options:
            ing, nm, dose, partner = pick(rng, options)
            d = last_date + timedelta(days=rng.randint(30, 60))
            eid = uid("KB", d)
            rid = f"RX-{eid[3:]}-8"
            doc = pick(rng, BS)
            res.append({"id": eid, "type": "Encounter", "date": iso(d), "source": "Vinmec - Khám nội", "practitioner": doc,
                        "diagnoses": [], "allergies_recorded": None, "text": f"Kê thêm {nm} {dose}."})
            res.append({"id": rid, "type": "MedicationRequest", "date": iso(d), "encounter": eid, "source": "Vinmec",
                        "practitioner": doc, "drug_name": nm, "dose": dose, "status": "active"})
            active[ing] = res[-1]
            gold1_flags["ddi"] = {"kind": "interaction", "must_cite": [active[partner]["id"], rid]}
        else:
            traps["ddi_active"] = False

    # ---------------- dị ứng
    allergen = pick(rng, [("Aspirin", "nổi mẩn"), ("Penicillin", "khó thở, nổi mề đay"), ("Hải sản", "ngứa")]) if rng.random() < 0.5 else None
    if allergen:
        od = start + timedelta(days=rng.randint(30, 200))
        oid = uid("NGOAI", od)
        res.append({"id": oid, "type": "DocumentReference", "date": iso(od), "source": pick(rng, BV_NGOAI),
                    "text": f"Ra viện ổn định. Dị ứng: {allergen[0]} ({allergen[1]}).",
                    "allergies_recorded": [{"substance": allergen[0], "reaction": allergen[1]}]})
        cd = max(od, last_date) + timedelta(days=rng.randint(15, 40))
        cid = uid("KB", cd)
        if traps["allergy_conflict"]:
            res.append({"id": cid, "type": "Encounter", "date": iso(cd), "source": "Vinmec - Khám nội", "practitioner": pick(rng, BS),
                        "diagnoses": [], "allergies_recorded": [], "text": "Tái khám định kỳ. Dị ứng: không."})
            gold1_flags["allergy"] = {"kind": "allergy_conflict", "must_cite": [oid, cid]}
        else:
            res.append({"id": cid, "type": "Encounter", "date": iso(cd), "source": "Vinmec - Khám nội", "practitioner": pick(rng, BS),
                        "diagnoses": [], "allergies_recorded": [{"substance": allergen[0], "reaction": allergen[1]}],
                        "text": f"Tái khám định kỳ. Dị ứng: {allergen[0]}."})
    else:
        traps["allergy_conflict"] = False
        if rng.random() < 0.6:
            last_enc["allergies_recorded"] = []
            last_enc["text"] += " Dị ứng: không."

    # ---------------- xét nghiệm theo thời gian
    n_panels = rng.randint(3, 5)
    pdates = sorted({start + timedelta(days=int(i * (adm_day - start).days / n_panels) + rng.randint(0, 20)) for i in range(n_panels)})
    pdates = [d for d in pdates if d < adm_day - timedelta(days=20)]
    declining = traps["renal_metformin"] or rng.random() < 0.3
    egfr0 = rng.randint(62, 85)
    egfr_end = rng.randint(34, 43) if traps["renal_metformin"] else (rng.randint(36, 55) if declining and "E11" not in conds else rng.randint(52, egfr0))
    if "metformin" in active and not traps["renal_metformin"]:
        egfr_end = max(egfr_end, 50)
    k_bad_idx = rng.randrange(1, max(2, len(pdates))) if traps["unresolved_k"] and len(pdates) >= 2 else None
    panels = []
    for i, d in enumerate(pdates + [adm_day]):
        frac = i / max(1, len(pdates))
        egfr = round(egfr0 + (egfr_end - egfr0) * frac)
        r = {"creatinine": round(7000 / max(egfr, 10)), "egfr": egfr}
        if "E11" in conds and d != adm_day:
            r["hba1c"] = round(rng.uniform(6.6, 8.8), 1)
        r["potassium"] = round(rng.uniform(3.8, 5.0), 1)
        panels.append({"date": d, "results": r, "note": None})
    if k_bad_idx is not None and k_bad_idx < len(pdates):
        panels[k_bad_idx]["results"]["potassium"] = round(rng.uniform(5.7, 6.1), 1)
        panels[k_bad_idx]["note"] = "Không có ghi chú xử trí"
        for q in panels[k_bad_idx + 1:-1]:
            q["results"].pop("potassium", None)  # các lần sau không làm lại kali
        # lần đo kali tiếp theo (lúc vào viện) phải cách > 120 ngày
        if (adm_day - panels[k_bad_idx]["date"]).days <= 120:
            panels[-1]["results"].pop("potassium", None)
    else:
        traps["unresolved_k"] = False
    adm_extra = {"crp": rng.randint(5, 180), "wbc": round(rng.uniform(6, 18), 1)}
    if "E11" in conds:
        adm_extra["glucose"] = round(rng.uniform(7.5, 16), 1)
    panels[-1]["results"].update(adm_extra)
    for p in panels:
        p["id"] = uid("XN", p["date"])
        rec = {"id": p["id"], "type": "LabPanel", "date": iso(p["date"]), "source": "Vinmec", "results": p["results"]}
        if p["note"]:
            rec["note"] = p["note"]
        res.append(rec)
    if k_bad_idx is not None:
        gold1_flags["k"] = {"kind": "unresolved_abnormal", "must_cite": [panels[k_bad_idx]["id"]]}
    egfr_series = [p for p in panels if "egfr" in p["results"]]
    gold1_facts.append({"id": "egfr", "contains": "eGFR", "must_cite": [egfr_series[0]["id"], egfr_series[-1]["id"]]})
    if traps["renal_metformin"] and "metformin" in active:
        gold1_flags["renal"] = {"kind": "renal_dose", "must_cite": [active["metformin"]["id"], panels[-1]["id"]]}
    else:
        traps["renal_metformin"] = False

    # ---------------- hẹn cận lâm sàng
    if rng.random() < 0.5 or traps["missing_result"]:
        desc = pick(rng, ["Siêu âm tim", "Siêu âm bụng", "Nội soi dạ dày"])
        ad = vinmec_encs[0]["date"]
        due = date.fromisoformat(ad) + timedelta(days=90)
        aid = uid("APT", date.fromisoformat(ad))
        res.append({"id": aid, "type": "Appointment", "date": ad, "encounter": vinmec_encs[0]["id"], "source": "Vinmec",
                    "description": desc, "due": iso(due)})
        if traps["missing_result"]:
            gold1_flags["missing"] = {"kind": "missing_result", "must_cite": [aid]}
        else:
            rd = due + timedelta(days=rng.randint(-10, 20))
            res.append({"id": uid("CDHA", rd), "type": "ImagingStudy", "date": iso(rd), "source": "Vinmec",
                        "modality": desc, "text": "Kết quả trong giới hạn bình thường."})

    # ---------------- đợt nội trú
    side = pick(rng, ["phải", "trái"])
    a = ACUTE[acute]
    sick = rng.random() < 0.45
    vit = {
        "pulse": rng.randint(98, 124) if sick else rng.randint(76, 96),
        "pulse_note": "không đều" if "I48" in conds else "đều",
        "temp": round(rng.uniform(38.2, 39.4), 1) if acute in ("pneumonia", "uti") else round(rng.uniform(36.6, 37.4), 1),
        "bp": f"{rng.randint(96, 150)}/{rng.randint(58, 90)}",
        "resp_rate": rng.randint(25, 30) if sick and acute != "uti" else rng.randint(17, 22),
        "spo2": rng.randint(86, 91) if sick and acute != "uti" else rng.randint(93, 98),
        "weight": rng.randint(45, 78) if rng.random() < 0.4 else None,
    }
    adm_id = f"BA-{iso(adm_day)}"
    res.append({"id": uid("CDHA", adm_day), "type": "ImagingStudy", "date": iso(adm_day), "source": "Vinmec",
                "modality": "X-quang ngực", "text": a["xray"].format(side=side)})
    patient = {
        "id": pid, "name": name, "birth_year": birth, "gender": "Nam" if male else "Nữ", "occupation": "Hưu trí",
        "address": f"{pick(rng, QUAN)}, Hà Nội", "insurance": f"BHYT (mức hưởng {pick(rng, ['80%', '95%', '100%'])})",
        "contact": f"{pick(rng, HO)} {pick(rng, DEM_NU)} {pick(rng, TEN_NU)} (con)", "ward": "Khoa Nội tổng hợp",
        "bed": f"Buồng {rng.randint(1, 8)} - Giường {rng.randint(1, 30)}",
        "attending": "bs.an" if rng.random() < 0.75 else "bs.binh",
        "admission": {"id": adm_id, "admitted_at": f"{iso(adm_day)}T{rng.randint(7, 20):02d}:{pick(rng, ['00', '15', '30', '45'])}",
                      "ward_at": f"{iso(adm_day)}T21:00", "reason": f"{a['reason']}. Vào ngày thứ {rng.randint(2, 5)} của bệnh.",
                      "kkb_diagnosis": a["assess_kw"].capitalize(), "vitals": vit},
    }
    record = {"_note": "DỮ LIỆU GIẢ LẬP 100% - sinh tự động, không phải bệnh nhân thật", "patient": patient,
              "resources": sorted(res, key=lambda r: (r["date"], r["id"]))}

    # ---------------- transcript + đáp án Module 2
    transcript, gold2 = make_transcript(pid, adm_day, acute, side, vit, conds, active, allergen, egfr_series[-1]["results"]["egfr"], rng)

    gold = {"patient_id": pid, "source": "sinh tự động",
            "traps": {k: v for k, v in traps.items() if v},
            "module1": {"flags": gold1_flags, "facts": gold1_facts, "forbidden": []},
            "module2": gold2}
    return record, transcript, gold


def make_transcript(pid, adm_day, acute, side, vit, conds, active, allergen, egfr, rng):
    a = ACUTE[acute]
    turns: list[dict] = []
    facts: list[dict] = []
    flags: list[dict] = []
    has_relative = rng.random() < 0.6

    def say(sp, text):
        turns.append({"n": len(turns) + 1, "speaker": sp, "text": text})
        return len(turns)

    days = rng.randint(2, 5)
    say("BS", "Chào bác, hôm nay bác thấy trong người thế nào?")
    if acute == "pneumonia":
        n = say("BN", f"Tôi sốt {words(days)} hôm nay rồi, ho nhiều, đờm màu vàng.")
        facts.append({"section": "S", "turn": n, "keywords": ["sốt", "đờm"]})
        say("BS", "Khó thở từ bao giờ ạ?")
        n = say("BN", "Từ hôm qua, đi lại trong nhà cũng thấy mệt, thở dốc.")
        facts.append({"section": "S", "turn": n, "keywords": ["khó thở"]})
    elif acute == "copd":
        n = say("BN", f"Mấy hôm nay tôi khó thở hơn hẳn, ho khạc đờm nhiều, {words(days)} hôm nay rồi.")
        facts.append({"section": "S", "turn": n, "keywords": ["khó thở", "đờm"]})
        say("BS", "Bác có xịt thuốc ở nhà không?")
        n = say("BN", "Có, tôi xịt Ventolin ngày bốn năm lần mà không đỡ.")
        facts.append({"section": "S", "turn": n, "keywords": ["ventolin"]})
    elif acute == "hf":
        n = say("BN", "Tôi nằm xuống là khó thở, phải kê cao gối mới ngủ được.")
        facts.append({"section": "S", "turn": n, "keywords": ["khó thở"]})
        say("BS", "Chân bác có phù không?")
        n = say("BN", f"Có, phù hai chân {words(days)} hôm nay, ấn vào lõm.")
        facts.append({"section": "S", "turn": n, "keywords": ["phù"]})
    else:  # uti
        n = say("BN", f"Tôi sốt rét run {words(days)} hôm nay, đi tiểu buốt, tiểu rắt.")
        facts.append({"section": "S", "turn": n, "keywords": ["sốt", "tiểu buốt"]})
        say("BS", "Có đau lưng không bác?")
        n = say("BN", "Đau âm ỉ bên hông phải.")
        facts.append({"section": "S", "turn": n, "keywords": ["đau"]})

    # Bệnh nhân tự dùng NSAID
    nsaid = rng.random() < 0.3
    say("BS", "Ở nhà bác đã uống thuốc gì chưa?")
    if nsaid:
        n_nsaid = say("BN", "Tôi có uống ibuprofen để hạ sốt, ngày hai ba viên. Thuốc của bệnh viện thì vẫn uống đều.")
        facts.append({"section": "S", "turn": n_nsaid, "keywords": ["ibuprofen"]})
    else:
        n = say("BN", "Chỉ uống thuốc của bệnh viện kê, vẫn uống đều hằng ngày.")
        facts.append({"section": "S", "turn": n, "keywords": ["thuốc"]})

    # Cờ đỏ
    if has_relative and rng.random() < 0.35:
        n = say("NN", "Bác sĩ ơi, từ tối qua bố cháu hay lú lẫn, nói lảm nhảm, gọi không nhận ra người nhà.")
        facts.append({"section": "S", "turn": n, "keywords": ["lú lẫn"]})
        flags.append({"kind": "red_flag", "id": "confusion"})
    if rng.random() < 0.2:
        say("BS", "Đi ngoài thế nào bác?")
        n = say("BN", "Hôm qua tôi đi ngoài phân đen, nát, một lần.")
        facts.append({"section": "S", "turn": n, "keywords": ["phân đen"]})
        flags.append({"kind": "red_flag", "id": "gi_bleed"})
    if acute == "pneumonia" and rng.random() < 0.15:
        n = say("BN", "Sáng nay tôi còn ho ra máu, có ít tia máu đỏ.")
        facts.append({"section": "S", "turn": n, "keywords": ["ho ra máu"]})
        flags.append({"kind": "red_flag", "id": "hemoptysis"})

    # Hỏi tiền sử (ngẫu nhiên có / không)
    asked_allergy = rng.random() < 0.5
    if asked_allergy:
        say("BS", "Bác có dị ứng thuốc gì không?")
        if allergen:
            n = say("BN", f"Tôi dị ứng {allergen[0].lower()}, bị {allergen[1]}.")
            facts.append({"section": "S", "turn": n, "keywords": [allergen[0].lower()]})
        else:
            n = say("BN", "Không, tôi chưa dị ứng thuốc gì.")
            facts.append({"section": "S", "turn": n, "keywords": ["dị ứng"]})
    asked_smoke = rng.random() < 0.4
    if asked_smoke:
        say("BS", "Bác có hút thuốc lá hay uống rượu không?")
        ans = pick(rng, [("Tôi hút thuốc lá ba mươi năm, bỏ được hai năm rồi.", "30 năm"), ("Không hút thuốc, thỉnh thoảng uống chút rượu.", "rượu")])
        n = say("BN", ans[0])
        facts.append({"section": "S", "turn": n, "keywords": [ans[1]]})
    asked_family = rng.random() < 0.3
    if asked_family:
        say("BS", "Trong gia đình có ai bị bệnh tim mạch, tiểu đường không?")
        ans = pick(rng, [("Mẹ tôi bị tiểu đường.", "tiểu đường"), ("Bố tôi bị tăng huyết áp.", "huyết áp")])
        n = say("BN", ans[0])
        facts.append({"section": "S", "turn": n, "keywords": [ans[1]]})

    # Khám
    exam = {
        "pneumonia": f"Phổi {side} có ran nổ vùng đáy, phổi còn lại thông khí được",
        "copd": "Phổi rì rào phế nang giảm, ran rít ran ngáy hai bên",
        "hf": "Ran ẩm hai đáy phổi, phù hai chi dưới, tĩnh mạch cổ nổi",
        "uti": "Ấn đau điểm niệu quản phải, rung thận phải dương tính",
    }[acute]
    heart = "Tim loạn nhịp hoàn toàn" if "I48" in conds else "Tim nhịp đều"
    n = say("BS", f"Được rồi, để tôi khám. {exam}. {heart}, tần số khoảng {words(vit['pulse'])}. Bụng mềm.")
    facts.append({"section": "O", "turn": n, "keywords": [exam.split(",")[0].split(" ")[0]]})
    sbp, dbp = map(int, vit["bp"].split("/"))
    spo2_text = f"SpO2 đang {words(vit['spo2'])}"
    typo = False
    if "chín" in spo2_text and rng.random() < 0.4:
        spo2_text, typo = spo2_text.replace("chín", "chin", 1), True
    o2 = vit["spo2"] < 92
    n = say("BS", f"{spo2_text}{', cho thở oxy kính hai lít' if o2 else ''}. Huyết áp {words(sbp)} trên {words(dbp)}.")
    facts.append({"section": "O", "turn": n, "keywords": [str(vit["spo2"])]})
    facts.append({"section": "O", "turn": n, "keywords": [f"{sbp}/{dbp}"]})
    if o2:
        facts.append({"section": "P", "turn": n, "keywords": ["oxy"]})
    if typo:
        flags.append({"kind": "asr_normalized", "value": str(vit["spo2"])})
    wbc = round(rng.uniform(9.5, 17.5), 1)
    n = say("BS", f"X-quang {ACUTE[acute]['xray'].format(side=side)[0].lower() + ACUTE[acute]['xray'].format(side=side)[1:-1]}, bạch cầu {dec_words(wbc)}.")
    facts.append({"section": "O", "turn": n, "keywords": ["x-quang"]})
    weight_said = vit["weight"] is None and rng.random() < 0.3
    if weight_said:
        kg = rng.randint(48, 75)
        n = say("BS", f"Cân nặng hôm nay {words(kg)} ki lô.")
        facts.append({"section": "O", "turn": n, "keywords": [str(kg)]})

    # Chẩn đoán + kế hoạch
    n = say("BS", ACUTE[acute]["assess"].format(side=side) + ".")
    facts.append({"section": "A", "turn": n, "keywords": [a["assess_kw"]]})
    plan_drugs = [d for d, _ in a["plan_drugs"]]
    plan = [t for _, t in a["plan_drugs"]]
    extra = a["macrolide"] if a["macrolide"] and rng.random() < 0.5 else None
    if extra:
        plan.append(f"phối hợp {extra} {'500 mg ngày hai lần' if extra == 'Clarithromycin' else '750 mg ngày một lần'}")
        plan_drugs.append(extra)
    n = say("BS", ", ".join(plan) + ".")
    facts.append({"section": "P", "turn": n, "keywords": [plan_drugs[0]]})
    n = say("BS", "Làm thêm điện giải đồ, khí máu, theo dõi sát sinh hiệu.")
    facts.append({"section": "P", "turn": n, "keywords": ["điện giải"]})
    if has_relative:
        say("NN", "Thuốc cũ của bố cháu vẫn uống tiếp ạ?")
        n = say("BS", "Tiếp tục thuốc cũ, chiều tôi xem lại đơn.")
        facts.append({"section": "P", "turn": n, "keywords": ["thuốc cũ"]})

    # ---------------- đáp án cờ Module 2
    mentioned = set()
    for t in turns:
        low = t["text"].lower()
        for key, d in KB["drugs"].items():
            if any(b in low for b in d["brands"]):
                mentioned.add(key)
    pool = set(active) | mentioned
    for it in KB["interactions"]:
        if it["a"] in pool and it["b"] in pool and (it["a"] in mentioned or it["b"] in mentioned):
            flags.append({"kind": "interaction", "pair": [it["a"], it["b"]]})
    if allergen and not asked_allergy:
        flags.append({"kind": "allergy_reminder", "substance": allergen[0]})
    if allergen:
        akey = {"Aspirin": "aspirin", "Penicillin": "penicillin"}.get(allergen[0])
        if akey:
            for m in mentioned:
                if m != akey and KB["drugs"][m]["class"] == KB["drugs"][akey]["class"]:
                    flags.append({"kind": "allergy_cross", "drug": m})
    if nsaid and "ibuprofen" not in active and egfr < 60:
        flags.append({"kind": "renal_dose", "drug": "ibuprofen"})
    if vit["spo2"] < 92 or vit["resp_rate"] >= 25 or sbp <= 90 or vit["pulse"] >= 130:
        flags.append({"kind": "vital_abnormal"})

    missing = []
    if not asked_allergy:
        missing.append("di_ung")
    if not asked_family:
        missing.append("tien_su_gia_dinh")
    if not asked_smoke:
        missing.append("thuoc_la_ruou")
    if vit["weight"] is None and not weight_said:
        missing.append("can_nang")

    tid = f"TS-{pid}"
    transcript = {"_note": "DỮ LIỆU GIẢ LẬP 100% - sinh tự động", "id": tid, "patient_id": pid,
                  "date": f"{iso(adm_day)}T21:30", "turns": turns}
    gold2 = {"transcript_id": tid, "facts": facts, "missing": missing, "flags": flags,
             "forbidden_numbers": [], "forbidden_text": ["xuất huyết tiêu hóa", "sốc nhiễm khuẩn"],
             "forbidden_patterns": [r"cân nặng:\s*\d"] if (vit["weight"] is None and not weight_said) else []}
    return transcript, gold2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--seed", type=int, default=29)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    for folder in ("patients", "transcripts", "gold"):
        (ROOT / folder).mkdir(exist_ok=True)
        for f in (ROOT / folder).glob("p[0-9][0-9][0-9].json"):
            if f.stem != "p001":
                f.unlink()
        for f in (ROOT / folder).glob("TS-p*.json"):
            f.unlink()
    stats = {}
    for i in range(2, args.n + 2):
        rec, ts, gold = make_patient(i, rng)
        pid = rec["patient"]["id"]
        (ROOT / "patients" / f"{pid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        (ROOT / "transcripts" / f"{ts['id']}.json").write_text(json.dumps(ts, ensure_ascii=False, indent=1), encoding="utf-8")
        (ROOT / "gold" / f"{pid}.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
        for t in gold["traps"]:
            stats[t] = stats.get(t, 0) + 1
        for f in gold["module2"]["flags"]:
            key = "M2 " + f["kind"]
            stats[key] = stats.get(key, 0) + 1
    print(f"Đã sinh {args.n} hồ sơ (p002–p{args.n + 1:03d}). Số bẫy đã cài:")
    for k, v in sorted(stats.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
