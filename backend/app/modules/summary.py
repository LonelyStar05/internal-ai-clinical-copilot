"""Module 1 (VMEC-03): tóm tắt hồ sơ đa nguồn có trích nguồn.

Luồng LangGraph: fetch -> analyze -> compose -> narrate (LLM, tùy chọn) -> verify
Mọi con số, thuốc, xu hướng, cờ đều do code tính; LLM chỉ viết lại đoạn tóm tắt ngắn từ các dòng đã có nguồn.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from ..core import kb as KB
from ..core import llm
from ..core.models import ActiveMed, Citation, Flag, Line, Section, Summary, Trend, TrendPoint
from ..core.verify import verify_line

DISCLAIMER = ("Kết quả do AI tổng hợp từ hồ sơ, chỉ để tham khảo. Bác sĩ kiểm tra nguồn "
              "và chịu trách nhiệm quyết định lâm sàng. AI không chẩn đoán, không chỉ định.")


def dmy(d: str) -> str:
    y, m, dd = d[:10].split("-")
    return f"{dd}/{m}/{y}"


def vn(x: float) -> str:
    s = f"{x:g}"
    return s.replace(".", ",")


class S1(TypedDict, total=False):
    pid: str
    record: dict
    sources: dict[str, Any]
    today: str
    flags: list[Flag]
    trends: list[Trend]
    meds: list[ActiveMed]
    allergies: list[dict]
    problems: list[dict]
    sections: list[Section]
    narrative: list[Line]
    dropped: list[dict]
    mode: str


# ---------------------------------------------------------------- nodes
def fetch(state: S1) -> S1:
    rec = KB.load_patient(state["pid"])
    if rec is None:
        raise KeyError(state["pid"])
    sources = {r["id"]: r for r in rec["resources"]}
    adm = rec["patient"].get("admission")
    if adm:
        sources[adm["id"]] = adm
    today = adm["admitted_at"][:10] if adm else date.today().isoformat()
    return {"record": rec, "sources": sources, "today": today}


def analyze(state: S1) -> S1:
    rec, sources, today = state["record"], state["sources"], state["today"]
    res = rec["resources"]
    k = KB.kb()
    flags: list[Flag] = []

    # Danh sách vấn đề từ chẩn đoán của các lần khám
    probs: dict[str, dict] = {}
    for r in sorted((r for r in res if r["type"] == "Encounter"), key=lambda r: r["date"]):
        for dx in r.get("diagnoses", []):
            p = probs.setdefault(dx["code"], {"code": dx["code"], "display": dx["display"], "first": r["date"], "refs": []})
            p["refs"].append(r["id"])

    # Thuốc đang dùng, quy về hoạt chất
    by_ing: dict[str, list[dict]] = defaultdict(list)
    for r in res:
        if r["type"] == "MedicationRequest" and r.get("status") == "active":
            ing = KB.ingredient_of(r["drug_name"]) or r["drug_name"]
            by_ing[ing].append({"drug_name": r["drug_name"], "dose": r["dose"], "practitioner": r.get("practitioner"),
                                "date": r["date"], "ref": r["id"]})
    meds = [ActiveMed(ingredient=i, display=KB.drug_display(i) if i in k["drugs"] else i, entries=e)
            for i, e in sorted(by_ing.items())]
    for m in meds:
        if len(m.entries) > 1:
            names = " và ".join(f"{e['drug_name']} ({e['practitioner']}, {dmy(e['date'])})" for e in m.entries)
            flags.append(Flag(id=f"dup-{m.ingredient}", kind="duplicate_ingredient", severity="cao",
                              title=f"Trùng hoạt chất: {m.display}",
                              detail=f"{names} cùng là {m.display}, cả hai đơn đều đang ở trạng thái dùng.",
                              citations=[Citation(ref=e["ref"]) for e in m.entries]))

    # Xu hướng xét nghiệm + kết quả bất thường chưa xử trí
    panels = sorted((r for r in res if r["type"] == "LabPanel"), key=lambda r: r["date"])
    trends: list[Trend] = []
    for key, meta in k["labs"].items():
        pts = [TrendPoint(date=p["date"], value=p["results"][key], ref=p["id"]) for p in panels if key in p["results"]]
        if not pts:
            continue
        delta = pts[-1].value - pts[0].value
        rel = abs(delta) / (abs(pts[0].value) or 1)
        direction = "ổn định" if len(pts) < 2 or rel < 0.05 else ("tăng" if delta > 0 else "giảm")
        last = pts[-1].value
        abnormal = (meta["high"] is not None and last > meta["high"]) or (meta["low"] is not None and last < meta["low"])
        trends.append(Trend(analyte=key, display=meta["display"], unit=meta["unit"], loinc=meta["loinc"],
                            points=pts, direction=direction, abnormal_latest=abnormal))

        crit = meta.get("critical_high")
        if crit:
            for idx, p in enumerate(panels):
                v = p["results"].get(key)
                if v is None or v <= crit:
                    continue
                later = [q for q in panels[idx + 1:] if key in q["results"]]
                gap = (date.fromisoformat(later[0]["date"]) - date.fromisoformat(p["date"])).days if later else None
                if gap is None or gap > k["follow_up_days"]:
                    skipped = [q for q in panels[idx + 1:] if key not in q["results"]
                               and (not later or q["date"] < later[0]["date"])]
                    cites = [Citation(ref=p["id"], quote=p.get("note"))] + [Citation(ref=q["id"], quote=f"không làm {meta['display'].lower()}") for q in skipped]
                    detail = f"{meta['display']} {vn(v)} {meta['unit']} ngày {dmy(p['date'])} (trên ngưỡng {vn(crit)})"
                    if p.get("note"):
                        detail += f"; hồ sơ ghi: \"{p['note']}\""
                    if skipped:
                        detail += f"; lần xét nghiệm {', '.join(dmy(q['date']) for q in skipped)} không làm lại {meta['display'].lower()}"
                    if later:
                        detail += f"; lần đo tiếp theo sau {gap} ngày: {vn(later[0]['results'][key])} {meta['unit']} ({dmy(later[0]['date'])})"
                        cites.append(Citation(ref=later[0]["id"]))
                    related = [m for m in meds if m.ingredient == "losartan"] if key == "potassium" else []
                    for m in related:
                        detail += f". Đang dùng {m.display} (thuốc có thể làm tăng kali)"
                        cites += [Citation(ref=e["ref"]) for e in m.entries]
                    flags.append(Flag(id=f"unresolved-{key}-{p['id']}", kind="unresolved_abnormal", severity="cao",
                                      title=f"Kết quả bất thường chưa thấy xử trí: {meta['display']}",
                                      detail=detail + ".", citations=cites))

    # Thuốc cần xem lại theo chức năng thận
    egfr = next((t for t in trends if t.analyte == "egfr"), None)
    if egfr:
        latest = egfr.points[-1]
        for m in meds:
            rules = sorted((r for r in k["renal_rules"] if r["drug"] == m.ingredient and latest.value < r["egfr_below"]),
                           key=lambda r: r["egfr_below"])
            if rules:
                r = rules[0]
                flags.append(Flag(id=f"renal-{m.ingredient}", kind="renal_dose",
                                  severity="cao" if r["level"] == "cao" else "trung bình",
                                  title=f"{m.display}: cần xem lại theo chức năng thận",
                                  detail=f"eGFR mới nhất {vn(latest.value)} ({dmy(latest.date)}). {r['note']} "
                                         f"Đơn hiện tại: {m.entries[0]['dose']}.",
                                  citations=[Citation(ref=e["ref"]) for e in m.entries] + [Citation(ref=latest.ref)]))

    # Dị ứng: gom từ mọi nguồn, phát hiện mâu thuẫn
    allergies, none_refs = [], []
    for r in sorted(res, key=lambda r: r["date"]):
        rec_a = r.get("allergies_recorded")
        if rec_a is None:
            continue
        if rec_a == []:
            none_refs.append(r)
        for a in rec_a:
            allergies.append({**a, "ref": r["id"], "source": r["source"], "date": r["date"]})
    if allergies and none_refs:
        a_txt = ", ".join(f"{a['substance']} ({a['reaction']})" for a in allergies)
        flags.append(Flag(id="allergy-conflict", kind="allergy_conflict", severity="cao",
                          title="Dị ứng ghi không thống nhất giữa các nguồn",
                          detail=f"{allergies[0]['source']} ghi dị ứng {a_txt}; "
                                 + "; ".join(f"{r['source']} ({dmy(r['date'])}) ghi không dị ứng" for r in none_refs)
                                 + ". AI không chọn bên nào đúng; cần bác sĩ hỏi lại người bệnh.",
                          citations=[Citation(ref=a["ref"]) for a in allergies] + [Citation(ref=r["id"]) for r in none_refs]))

    # Hẹn cận lâm sàng chưa có kết quả
    for apt in (r for r in res if r["type"] == "Appointment"):
        done = [r for r in res if r["type"] in ("ImagingStudy", "DocumentReference")
                and apt["description"].lower() in (r.get("modality", "") + " " + r.get("text", "")).lower()
                and r["date"] >= apt["date"]]
        if not done and apt["due"] < today:
            flags.append(Flag(id=f"missing-{apt['id']}", kind="missing_result", severity="trung bình",
                              title=f"Chưa ghi nhận kết quả: {apt['description']}",
                              detail=f"Hẹn {apt['description'].lower()} từ lần khám {dmy(apt['date'])} (dự kiến {dmy(apt['due'])}); "
                                     f"không tìm thấy kết quả nào trong hồ sơ.",
                              citations=[Citation(ref=apt["id"]), Citation(ref=apt["encounter"])]))

    # Tương tác giữa các thuốc đang dùng
    ings = [m.ingredient for m in meds]
    for it in k["interactions"]:
        if it["a"] in ings and it["b"] in ings:
            ma = next(m for m in meds if m.ingredient == it["a"])
            mb = next(m for m in meds if m.ingredient == it["b"])
            flags.append(Flag(id=f"ddi-{it['a']}-{it['b']}", kind="interaction", severity=it["severity"],
                              title=f"Tương tác: {ma.display} + {mb.display}", detail=it["effect"],
                              citations=[Citation(ref=e["ref"]) for e in ma.entries + mb.entries]))

    order = {"đỏ": 0, "cao": 1, "trung bình": 2, "thông tin": 3}
    flags.sort(key=lambda f: order[f.severity])
    return {"flags": flags, "trends": trends, "meds": meds, "allergies": allergies, "problems": list(probs.values())}


def compose(state: S1) -> S1:
    rec, sources = state["record"], state["sources"]
    pat = rec["patient"]
    sections: list[Section] = []

    handoff = next((r for r in rec["resources"] if r["type"] == "Handoff"), None)  # hồ sơ tạo từ bàn giao bằng lời
    s1 = Section(key="benh_nen", title="1. Bệnh nền và vấn đề chính")
    for p in state["problems"]:
        s1.lines.append(Line(text=f"{p['display']} (ICD-10 {p['code']}), ghi nhận từ {dmy(p['first'])}.",
                             citations=[Citation(ref=r) for r in p["refs"]]))
    if handoff:
        for x in handoff.get("comorbidities", []):
            s1.lines.append(Line(text=f"{x} (theo bàn giao).", citations=[Citation(ref=handoff["id"])]))
        if not s1.lines:
            s1.lines.append(Line(text="Chưa ghi nhận.", kind="missing"))
    sections.append(s1)

    adm = pat.get("admission")
    if adm:
        s2 = Section(key="dot_nay", title="2. Đợt điều trị hiện tại")
        s2.lines.append(Line(text=f"Vào viện {dmy(adm['admitted_at'])}: {adm['reason']}", citations=[Citation(ref=adm["id"])]))
        v = adm["vitals"]
        parts = [f"mạch {v['pulse']} lần/phút ({v.get('pulse_note', '')})" if v.get("pulse") is not None else None,
                 f"nhiệt độ {vn(v['temp'])}°C" if v.get("temp") is not None else None,
                 f"HA {v['bp']} mmHg" if v.get("bp") else None,
                 f"nhịp thở {v['resp_rate']} lần/phút" if v.get("resp_rate") is not None else None,
                 f"SpO2 {v['spo2']}%" if v.get("spo2") is not None else None]
        if handoff:  # hồ sơ bàn giao không có pulse_note và có thể thiếu chỉ số
            parts[0] = f"mạch {v['pulse']} lần/phút" if v.get("pulse") is not None else None
        if any(parts):
            s2.lines.append(Line(text="Sinh hiệu lúc vào khoa: " + ", ".join(x for x in parts if x) + ".",
                                 citations=[Citation(ref=adm["id"])]))
        else:
            s2.lines.append(Line(text="Sinh hiệu lúc vào khoa: chưa ghi nhận.", kind="missing"))
        for r in rec["resources"]:
            if r["type"] == "ImagingStudy" and r["date"] >= adm["admitted_at"][:10]:
                s2.lines.append(Line(text=f"{r['modality']} {dmy(r['date'])}: {r['text']}", citations=[Citation(ref=r["id"])]))
        sections.append(s2)

    if handoff:
        sb = Section(key="ban_giao", title="7. Bàn giao tiếp nhận")
        ref = [Citation(ref=handoff["id"])]
        sb.lines += [Line(text=f"Chẩn đoán / vấn đề: {x}.", citations=ref) for x in handoff.get("problems", [])]
        sb.lines += [Line(text=f"Xét nghiệm / hình ảnh: {x}.", citations=ref) for x in handoff.get("labs_imaging", [])]
        sb.lines += [Line(text=f"Chờ xử lý / cần theo dõi: {x}.", citations=ref) for x in handoff.get("pending", [])]
        if not sb.lines:
            sb.lines.append(Line(text="Bàn giao không nêu chẩn đoán, xét nghiệm hay việc cần theo dõi.", kind="missing"))
        sections.append(sb)

    s3 = Section(key="thuoc", title="3. Thuốc đang dùng (đã quy về hoạt chất)")
    for m in state["meds"]:
        for e in m.entries:
            s3.lines.append(Line(text=f"{m.display}: {e['drug_name']}, {e['dose']} ({e['practitioner']}, {dmy(e['date'])}).",
                                 citations=[Citation(ref=e["ref"])]))
    sections.append(s3)

    s4 = Section(key="xu_huong", title="4. Xu hướng chỉ số")
    for t in state["trends"]:
        first, last = t.points[0], t.points[-1]
        if len(t.points) == 1:
            txt = f"{t.display}: {vn(last.value)} {t.unit} ({dmy(last.date)})."
        else:
            series = ", ".join(f"{vn(p.value)}" for p in t.points)
            txt = (f"{t.display} {t.direction} từ {vn(first.value)} ({dmy(first.date)}) đến {vn(last.value)} "
                   f"({dmy(last.date)}); các lần đo: {series} {t.unit}.")
        if t.abnormal_latest:
            txt += " Giá trị mới nhất ngoài ngưỡng tham chiếu."
        s4.lines.append(Line(text=txt, citations=[Citation(ref=p.ref) for p in t.points]))
    sections.append(s4)

    s5 = Section(key="di_ung", title="5. Dị ứng")
    if state["allergies"]:
        for a in state["allergies"]:
            s5.lines.append(Line(text=f"{a['substance']} ({a['reaction']}), theo {a['source']}.", citations=[Citation(ref=a["ref"])]))
        if any(f.kind == "allergy_conflict" for f in state["flags"]):
            s5.lines.append(Line(text="Có nguồn khác ghi không dị ứng: xem cờ cảnh báo.", kind="info"))
    else:
        s5.lines.append(Line(text="Chưa ghi nhận.", kind="missing"))
    sections.append(s5)

    s6 = Section(key="chua_ghi_nhan", title="6. Chưa ghi nhận trong hồ sơ")
    for f in state["flags"]:
        if f.kind == "missing_result":
            s6.lines.append(Line(text=f.title.replace("Chưa ghi nhận kết quả: ", "Kết quả ") + ".", kind="missing"))
    if adm and adm["vitals"].get("weight") is None:
        s6.lines.append(Line(text="Cân nặng.", kind="missing"))
    if not any(t.analyte == "egfr" for t in state["trends"]):
        s6.lines.append(Line(text="Chức năng thận.", kind="missing"))
    sections.append(s6)
    return {"sections": sections}


NARRATE_SYSTEM = """Bạn là trợ lý tóm tắt hồ sơ cho bác sĩ nội khoa. Chỉ dùng các dòng dữ liệu được cung cấp.
Viết 3-5 câu tiếng Việt ngắn gọn, mỗi câu kèm danh sách mã nguồn lấy từ đúng các dòng đã dùng.
Không chẩn đoán mới, không khuyên dùng hay ngừng thuốc, không thêm con số không có trong dữ liệu.
Trả về JSON: {"sentences": [{"text": "...", "refs": ["MÃ", ...]}]}"""


def narrate(state: S1) -> S1:
    if not llm.available():
        return {"narrative": [], "mode": "offline"}
    payload = [{"text": l.text, "refs": [c.ref for c in l.citations]}
               for s in state["sections"] for l in s.lines if l.kind == "fact"]
    payload += [{"text": f"CỜ: {f.title}. {f.detail}", "refs": [c.ref for c in f.citations]} for f in state["flags"]]
    out = llm.complete_json(NARRATE_SYSTEM, json.dumps(payload, ensure_ascii=False))
    if not out or "sentences" not in out:
        return {"narrative": [], "mode": "offline"}
    lines = [Line(text=s["text"], citations=[Citation(ref=r) for r in s.get("refs", [])]) for s in out["sentences"]]
    return {"narrative": lines, "mode": "llm"}


def verify(state: S1) -> S1:
    sources = state["sources"]
    dropped = []
    for s in state["sections"]:
        kept = []
        for l in s.lines:
            ok, why = verify_line(l, sources)
            (kept.append(l) if ok else dropped.append({"where": s.title, "text": l.text, "reason": why}))
        s.lines = kept
    narrative = []
    for l in state.get("narrative", []):
        ok, why = verify_line(l, sources)
        (narrative.append(l) if ok else dropped.append({"where": "Tóm tắt LLM", "text": l.text, "reason": why}))
    return {"sections": state["sections"], "narrative": narrative, "dropped": dropped}


def build_graph():
    g = StateGraph(S1)
    for name, fn in [("fetch", fetch), ("analyze", analyze), ("compose", compose), ("narrate", narrate), ("verify", verify)]:
        g.add_node(name, fn)
    g.set_entry_point("fetch")
    g.add_edge("fetch", "analyze")
    g.add_edge("analyze", "compose")
    g.add_edge("compose", "narrate")
    g.add_edge("narrate", "verify")
    g.add_edge("verify", END)
    return g.compile()


GRAPH = None


def summarize(pid: str) -> Summary:
    global GRAPH
    GRAPH = GRAPH or build_graph()
    st = GRAPH.invoke({"pid": pid})
    return Summary(patient_id=pid, mode=st.get("mode", "offline"), sections=st["sections"], flags=st["flags"],
                   trends=st["trends"], active_meds=st["meds"], allergies=st["allergies"],
                   narrative=st.get("narrative", []), dropped=st.get("dropped", []), disclaimer=DISCLAIMER)


def source_index(pid: str) -> dict[str, Any]:
    rec = KB.load_patient(pid)
    out = {r["id"]: r for r in rec["resources"]}
    adm = rec["patient"].get("admission")
    if adm:
        out[adm["id"]] = {"id": adm["id"], "type": "Admission", "date": adm["admitted_at"][:10], "source": "Vinmec - Bệnh án nội trú", **adm}
    return out
