"""Module 2 (VMEC-06): soạn nháp bệnh án / tờ điều trị từ transcript buổi khám.

Luồng LangGraph: normalize -> extract (LLM hoặc offline) -> verify -> context (hồ sơ cũ từ Module 1)
                 -> missing -> safety -> icd -> compose
Nguyên tắc: chẩn đoán chỉ lấy từ lời bác sĩ; mục không được nêu ghi "Chưa ghi nhận"; mọi dòng có dẫn chứng.
"""
from __future__ import annotations

import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from ..core import kb as KB
from ..core import llm
from ..core.models import Citation, Fact, Flag, Line, NoteDraft, Section
from ..core.verify import source_numbers, _canon, _strip_labels
from ..core.vn_text import normalize, numbers_in
from .summary import dmy, summarize, vn

DISCLAIMER = ("BẢN NHÁP DO AI SOẠN – CHƯA DUYỆT. Chỉ tổng hợp từ nội dung buổi khám và hồ sơ. "
              "AI không chẩn đoán, không chỉ định điều trị. Bác sĩ rà soát, chỉnh sửa và ký trước khi lưu.")

FILLER = re.compile(r"^(chào|được rồi|thế à|để tôi|à\b|vâng|dạ\b|ừ\b)", re.I)
A_KEYS = ("nghĩ", "phù hợp", "chẩn đoán", "có lẽ là", "theo dõi bệnh")
P_KEYS = ("cho ", "truyền", "làm thêm", "theo dõi", "tiếp tục", "báo tôi", "chỉ định", "dùng ")
O_KEYS = ("phổi", "tim ", "tim,", "bụng", "spo2", "huyết áp", "x-quang", "bạch cầu", "crp", "mạch", "nhiệt độ",
          "ran ", "khám", "điện tim", "siêu âm", "ấn đau", "thận", "phù", "tĩnh mạch cổ", "rì rào", "cân nặng",
          "da ", "niêm mạc")
LAB_KEYS = ("x-quang", "bạch cầu", "crp", "xét nghiệm", "siêu âm", "điện tim")


class S2(TypedDict, total=False):
    pid: str
    tid: str
    transcript: dict
    turns: list[dict]
    asr_fixes: list[dict]
    facts: list[Fact]
    dropped: list[dict]
    mode: str
    summary: Any
    missing: list[dict]
    flags: list[Flag]
    icd: list[dict]
    sections: list[Section]


# ---------------------------------------------------------------- nodes
def normalize_turns(state: S2) -> S2:
    t = KB.load_transcript(state["tid"])
    if t is None or t["patient_id"] != state["pid"]:
        raise KeyError(state["tid"])
    turns, fixes = [], []
    for turn in t["turns"]:
        n = normalize(turn["text"])
        turns.append({**turn, "norm": n.text})
        fixes += [{"turn": turn["n"], "from": a, "to": b} for a, b in n.asr_fixes]
    return {"transcript": t, "turns": turns, "asr_fixes": fixes}


def _clauses(sentence: str) -> list[str]:
    return [c.strip() for c in re.split(r",\s+(?=[^\d])", sentence) if c.strip()]


def _classify_bs(clause: str) -> str | None:
    low = clause.lower()
    if any(k in low for k in A_KEYS):
        return "A"
    if any(k in low for k in P_KEYS) or (KB.drugs_mentioned(clause) and re.search(r"\d+\s*mg|khi sốt|truyền", low)):
        return "P"
    if any(k in low for k in O_KEYS):
        return "O"
    return None


def _field_for(section: str, text: str) -> str:
    low = text.lower()
    if section == "S":
        return "Thuốc đã dùng" if KB.drugs_mentioned(text) or "thuốc" in low else "Quá trình bệnh lý"
    if section == "O":
        if any(k in low for k in LAB_KEYS):
            return "Cận lâm sàng"
        if any(k in low for k in ("spo2", "huyết áp", "mạch", "nhiệt độ")):
            return "Dấu hiệu sinh tồn"
        return "Khám các cơ quan"
    if section == "A":
        return "Chẩn đoán (theo bác sĩ)"
    return "Hướng điều trị"


QUESTION_TOPICS = ["khó thở", "đau ngực", "đau bụng", "sốt", "ho", "nôn", "chóng mặt", "phù"]


def _question_topic(prev: dict | None) -> str | None:
    """Chủ đề câu hỏi của bác sĩ ở lượt trước, để câu trả lời ngắn của bệnh nhân không mất ngữ cảnh."""
    if not prev or prev["speaker"] != "BS" or not prev["norm"].strip().endswith("?"):
        return None
    low = prev["norm"].lower()
    return next((k for k in QUESTION_TOPICS if re.search(rf"\b{k}\b", low)), None)


def extract_offline(turns: list[dict]) -> list[Fact]:
    facts: list[Fact] = []
    for idx, t in enumerate(turns):
        topic = _question_topic(turns[idx - 1] if idx > 0 else None)
        sentences = [s.strip() for s in re.split(r"(?<=[.?!])\s+", t["norm"]) if s.strip()]
        for s in sentences:
            if s.endswith("?") or (t["speaker"] == "BS" and FILLER.match(s)):
                continue
            if t["speaker"] in ("BN", "NN"):
                text = re.sub(r"^(bác sĩ ơi|thưa bác sĩ)[,\s]*", "", s.rstrip("."), flags=re.I)
                text = re.sub(r"^(à|ừ|dạ)[,\s]+", "", text, flags=re.I)
                if len(text.split()) < 2:
                    continue
                cited = [t["n"]]
                if topic and topic not in text.lower():
                    text = f"{topic.capitalize()}: {text[0].lower()}{text[1:]}"
                    cited = [turns[idx - 1]["n"], t["n"]]
                    topic = None  # chỉ gắn cho câu đầu của câu trả lời
                if t["speaker"] == "NN":
                    text = f"Người nhà kể: {text[0].lower()}{text[1:]}"
                facts.append(Fact(section="S", field=_field_for("S", text), text=text, turns=cited,
                                  speaker=t["speaker"], numbers=sorted(numbers_in(_strip_labels(text)))))
                continue
            # Bác sĩ: tách mệnh đề, gom các mệnh đề liền nhau cùng loại
            current: tuple[str, list[str]] | None = None
            groups: list[tuple[str, list[str]]] = []
            for c in _clauses(s.rstrip(".")):
                sec = _classify_bs(c)
                if sec is None:
                    sec = current[0] if current else None
                if sec is None:
                    continue
                if current and current[0] == sec:
                    current[1].append(c)
                else:
                    current = (sec, [c])
                    groups.append(current)
            for sec, parts in groups:
                text = ", ".join(parts)
                facts.append(Fact(section=sec, field=_field_for(sec, text), text=text, turns=[t["n"]],
                                  speaker="BS", numbers=sorted(numbers_in(_strip_labels(text)))))
    return facts


EXTRACT_SYSTEM = """Bạn trích thông tin lâm sàng từ transcript buổi khám nội khoa (tiếng Việt) để soạn nháp bệnh án.
Quy tắc bắt buộc:
- Chỉ dùng thông tin có trong transcript. Không suy luận, không thêm triệu chứng hay con số.
- Mỗi mục ghi rõ các lượt nói (số n) làm dẫn chứng.
- section: S = bệnh nhân/người nhà kể; O = bác sĩ khám, sinh hiệu, cận lâm sàng; A = CHỈ khi bác sĩ nói ra chẩn đoán/đánh giá; P = y lệnh, xét nghiệm, theo dõi do bác sĩ nói.
- Lời người nhà phải bắt đầu bằng "Người nhà kể:".
- Giữ nguyên con số như trong transcript đã chuẩn hóa.
Trả JSON: {"facts": [{"section": "S|O|A|P", "field": "...", "text": "...", "turns": [n, ...]}]}"""


def extract(state: S2) -> S2:
    turns = state["turns"]
    if llm.available():
        payload = "\n".join(f"[{t['n']}] {t['speaker']}: {t['norm']}" for t in turns)
        out = llm.complete_json(EXTRACT_SYSTEM, payload)
        if out and isinstance(out.get("facts"), list):
            spk = {t["n"]: t["speaker"] for t in turns}
            facts = []
            for f in out["facts"]:
                try:
                    tn = [int(x) for x in f.get("turns", [])]
                    facts.append(Fact(section=f["section"], field=f.get("field", ""), text=f["text"], turns=tn,
                                      speaker=spk.get(tn[0], "?") if tn else "?",
                                      numbers=sorted(numbers_in(_strip_labels(f["text"])))))
                except Exception:
                    continue
            return {"facts": facts, "mode": "llm"}
    return {"facts": extract_offline(turns), "mode": "offline"}


def verify_facts(state: S2) -> S2:
    by_n = {t["n"]: t for t in state["turns"]}
    kept, dropped = [], []
    for f in state["facts"]:
        if not f.turns or any(n not in by_n for n in f.turns):
            dropped.append({"text": f.text, "reason": "lượt dẫn chứng không tồn tại"})
            continue
        if f.section == "A" and any(by_n[n]["speaker"] != "BS" for n in f.turns):
            dropped.append({"text": f.text, "reason": "chẩn đoán không do bác sĩ nêu"})
            continue
        allowed = set()
        for n in f.turns:
            allowed |= source_numbers(by_n[n]["norm"])
        allowed = {_canon(x) for x in allowed}
        bad = [x for x in f.numbers if _canon(x) not in allowed]
        if bad:
            dropped.append({"text": f.text, "reason": f"con số không có trong lượt được dẫn: {', '.join(bad)}"})
            continue
        kept.append(f)
    return {"facts": kept, "dropped": dropped}


def context(state: S2) -> S2:
    return {"summary": summarize(state["pid"])}


def find_missing(state: S2) -> S2:
    text = " ".join(t["norm"].lower() for t in state["turns"])
    adm = KB.load_patient(state["pid"])["patient"].get("admission", {})
    missing = []
    for rf in KB.kb()["required_fields"]:
        covered = any(k in text for k in rf["keywords"])
        if rf["id"] == "can_nang" and adm.get("vitals", {}).get("weight"):
            covered = True
        if rf["id"] == "kham_toan_than" and adm.get("vitals"):
            covered = True
        if not covered:
            missing.append({"id": rf["id"], "label": rf["label"]})
    return {"missing": missing}


def _turn_cite(t: dict) -> Citation:
    return Citation(ref=f"L{t['n']}", quote=t["text"])


def safety(state: S2) -> S2:
    k = KB.kb()
    turns, summ = state["turns"], state["summary"]
    adm = KB.load_patient(state["pid"])["patient"].get("admission", {})
    flags: list[Flag] = []

    # Cờ đỏ trong lời bệnh nhân / người nhà
    for rf in k["red_flags"]:
        hits = [t for t in turns if t["speaker"] in ("BN", "NN") and any(p in t["norm"].lower() for p in rf["patterns"])]
        if hits:
            who = ", ".join(sorted({"người nhà" if t["speaker"] == "NN" else "bệnh nhân" for t in hits}))
            flags.append(Flag(id=f"red-{rf['id']}", kind="red_flag", severity="đỏ", title=f"Cờ đỏ: {rf['label']}",
                              detail=f"Theo lời {who}: " + " / ".join(f"\"{t['text']}\" (lượt {t['n']})" for t in hits)
                                     + ". Cần bác sĩ đánh giá ngay.",
                              citations=[_turn_cite(t) for t in hits], data={"rule": rf["id"]}))

    # Sinh hiệu bất thường (bệnh án lúc vào khoa + lời bác sĩ)
    vf, v = k["vital_flags"], adm.get("vitals", {})
    issues, cites = [], []
    spo2_turns = [t for t in turns if t["speaker"] == "BS" and re.search(r"spo2\D{0,10}(\d+)", t["norm"].lower())]
    if v.get("spo2") is not None and v["spo2"] < vf["spo2_below"]:
        issues.append(f"SpO2 {v['spo2']}%")
    for t in spo2_turns:
        m = re.search(r"spo2\D{0,10}(\d+)", t["norm"].lower())
        if m and int(m.group(1)) < vf["spo2_below"] and "dưới" not in t["norm"].lower()[:m.end()]:
            cites.append(_turn_cite(t))
    if v.get("resp_rate") is not None and v["resp_rate"] >= vf["resp_rate_at_least"]:
        issues.append(f"nhịp thở {v['resp_rate']} lần/phút")
    if v.get("bp"):
        sbp = int(str(v["bp"]).split("/")[0])
        if sbp <= vf["sbp_at_most"]:
            issues.append(f"HA tâm thu {sbp} mmHg")
    if v.get("pulse") is not None and v["pulse"] >= vf["pulse_at_least"]:
        issues.append(f"mạch {v['pulse']} lần/phút")
    if issues and Citation(ref=adm["id"]) not in cites:
        cites.insert(0, Citation(ref=adm["id"]))
    if issues:
        flags.append(Flag(id="vitals", kind="vital_abnormal", severity="cao", title="Sinh hiệu ngoài ngưỡng cảnh báo",
                          detail=", ".join(issues) + f" (ngưỡng cảnh báo: SpO2 < {vf['spo2_below']}%, nhịp thở ≥ {vf['resp_rate_at_least']}, "
                                 f"HA tâm thu ≤ {vf['sbp_at_most']}, mạch ≥ {vf['pulse_at_least']}).",
                          citations=cites))

    # Thuốc nhắc đến trong buổi khám vs thuốc đang dùng theo hồ sơ
    active = {m.ingredient: m for m in summ.active_meds}
    mentioned: dict[str, list[dict]] = {}
    for t in turns:
        for d in KB.drugs_mentioned(t["text"]):
            mentioned.setdefault(d, []).append(t)
    pool = set(active) | set(mentioned)
    seen = set()
    for it in k["interactions"]:
        a, b = it["a"], it["b"]
        if a in pool and b in pool and (a in mentioned or b in mentioned) and (a, b) not in seen:
            seen.add((a, b))
            cites = []
            for d in (a, b):
                cites += [_turn_cite(t) for t in mentioned.get(d, [])]
                if d in active:
                    cites += [Citation(ref=e["ref"]) for e in active[d].entries]
            origin = []
            for d in (a, b):
                if d in mentioned:
                    who = mentioned[d][0]["speaker"]
                    origin.append(f"{KB.drug_display(d)} ({'bệnh nhân tự dùng' if who == 'BN' else 'nhắc trong buổi khám'}, lượt {mentioned[d][0]['n']})")
                else:
                    origin.append(f"{KB.drug_display(d)} (đang dùng theo hồ sơ)")
            flags.append(Flag(id=f"ddi-{a}-{b}", kind="interaction", severity=it["severity"],
                              title=f"Tương tác thuốc: {KB.drug_display(a)} + {KB.drug_display(b)}",
                              detail=f"{' + '.join(origin)}. {it['effect']} Nguồn: bộ quy tắc nhóm tự soạn, cần đối chiếu DDInter.",
                              citations=cites, data={"pair": [a, b]}))

    # Dị ứng: chưa hỏi trong buổi khám nhưng hồ sơ có ghi; phản ứng chéo cùng nhóm
    asked = any("dị ứng" in t["norm"].lower() for t in turns)
    uniq = {}
    for al in summ.allergies:
        uniq.setdefault(al["substance"], al)
    for al in uniq.values():
        if not asked:
            flags.append(Flag(id=f"allergy-remind-{al['substance']}", kind="allergy_reminder", severity="cao",
                              title="Buổi khám chưa hỏi dị ứng",
                              detail=f"Hồ sơ cũ ghi dị ứng {al['substance']} ({al['reaction']}) theo {al['source']}; "
                                     f"hồ sơ Vinmec có lần ghi không dị ứng. Nên hỏi lại người bệnh.",
                              citations=[Citation(ref=al["ref"])], data={"substance": al["substance"]}))
        aing = KB.ingredient_of(al["substance"])
        if aing:
            for d, ts in mentioned.items():
                if d != aing and KB.drug_class(d) == KB.drug_class(aing):
                    flags.append(Flag(id=f"allergy-cross-{d}", kind="allergy_cross", severity="cao",
                                      title=f"{KB.drug_display(d)} cùng nhóm với chất đã ghi dị ứng ({al['substance']})",
                                      detail=f"{KB.drug_display(d)} được nhắc ở lượt {ts[0]['n']}. "
                                             + k["allergy_cross"][0]["note"],
                                      citations=[_turn_cite(ts[0]), Citation(ref=al["ref"])]))

    # Thuốc nhắc đến vs chức năng thận
    egfr = next((t for t in summ.trends if t.analyte == "egfr"), None)
    if egfr:
        last = egfr.points[-1]
        for d, ts in mentioned.items():
            if d in active:
                continue  # thuốc đang dùng đã được Module 1 cảnh báo
            for r in sorted(k["renal_rules"], key=lambda r: r["egfr_below"]):
                if r["drug"] == d and last.value < r["egfr_below"]:
                    flags.append(Flag(id=f"renal-{d}", kind="renal_dose", severity="trung bình",
                                      title=f"{KB.drug_display(d)} trên bệnh nhân giảm chức năng thận",
                                      detail=f"eGFR {vn(last.value)} ({dmy(last.date)}). {r['note']}",
                                      citations=[_turn_cite(ts[0]), Citation(ref=last.ref)]))
                    break

    # Lỗi ASR đã tự sửa
    for fx in state["asr_fixes"]:
        t = next(t for t in turns if t["n"] == fx["turn"])
        flags.append(Flag(id=f"asr-{fx['turn']}-{fx['from']}", kind="asr_normalized", severity="thông tin",
                          title="Đã chuẩn hóa lỗi nhận dạng giọng nói",
                          detail=f"Lượt {fx['turn']}: \"{fx['from']}\" → \"{fx['to']}\". Văn bản sau chuẩn hóa: \"{t['norm']}\". Bác sĩ kiểm tra lại.",
                          citations=[_turn_cite(t)], data={"normalized": t["norm"]}))

    order = {"đỏ": 0, "cao": 1, "trung bình": 2, "thông tin": 3}
    flags.sort(key=lambda f: order[f.severity])
    return {"flags": flags}


def suggest_icd(state: S2) -> S2:
    icd = KB.kb()["icd10"]
    out = []
    for f in (f for f in state["facts"] if f.section == "A"):
        low = f.text.lower()
        hits = [c for c in icd if any(kw in low for kw in c["keywords"])]
        best_len = max((max(len(kw) for kw in c["keywords"] if kw in low) for c in hits), default=0)
        for c in hits:
            spec = max(len(kw) for kw in c["keywords"] if kw in low)
            out.append({"code": c["code"], "display": c["display"], "role": "bệnh chính (bác sĩ nêu)",
                        "from": f"L{f.turns[0]}", "match": "khớp nhất" if spec == best_len else "khớp một phần"})
    for p in state["summary"].sections[0].lines:
        low = p.text.lower()
        for c in icd:
            if any(kw in low for kw in c["keywords"]) and c["code"].split(".")[0] in p.text:
                out.append({"code": c["code"], "display": c["display"], "role": "bệnh kèm theo (từ hồ sơ)",
                            "from": p.citations[0].ref, "match": "khớp nhất"})
    return {"icd": out}


def compose(state: S2) -> S2:
    pat = KB.load_patient(state["pid"])["patient"]
    adm = pat.get("admission", {})
    summ = state["summary"]
    facts = state["facts"]
    miss = {m["id"] for m in state["missing"]}

    def fl(sec: str, field: str | None = None) -> list[Line]:
        return [Line(text=f.text[:1].upper() + f.text[1:], citations=[Citation(ref=f"L{n}") for n in f.turns])
                for f in facts if f.section == sec and (field is None or f.field == field)]

    def missing_line(label: str) -> Line:
        return Line(text=f"{label}: Chưa ghi nhận.", kind="missing")

    secs = []
    s = Section(key="ly_do", title="I. Lý do vào viện")
    if adm:
        s.lines.append(Line(text=adm["reason"], citations=[Citation(ref=adm["id"])]))
    secs.append(s)

    s = Section(key="qua_trinh", title="II.1. Quá trình bệnh lý")
    s.lines = fl("S", "Quá trình bệnh lý") or [missing_line("Quá trình bệnh lý")]
    secs.append(s)

    s = Section(key="tien_su", title="II.2. Tiền sử bản thân")
    for l in summ.sections[0].lines:
        s.lines.append(Line(text=l.text, citations=l.citations))
    s.lines += fl("S", "Thuốc đã dùng")
    meds = "; ".join(f"{e['drug_name']} {e['dose']}" for m in summ.active_meds for e in m.entries)
    s.lines.append(Line(text=f"Thuốc đang dùng theo hồ sơ: {meds}.",
                        citations=[Citation(ref=e["ref"]) for m in summ.active_meds for e in m.entries]))
    s.lines.append(missing_line("Dị ứng (chưa hỏi trong buổi khám)") if "di_ung" in miss else Line(text="Dị ứng: xem lời bệnh nhân.", kind="info"))
    if "thuoc_la_ruou" in miss:
        s.lines.append(missing_line("Thuốc lá / rượu bia"))
    secs.append(s)

    s = Section(key="gia_dinh", title="II.3. Tiền sử gia đình")
    s.lines = [missing_line("Tiền sử gia đình")] if "tien_su_gia_dinh" in miss else [Line(text="Xem transcript.", kind="info")]
    secs.append(s)

    s = Section(key="toan_than", title="III.1. Toàn thân và dấu hiệu sinh tồn")
    if adm.get("vitals"):
        v = adm["vitals"]
        s.lines.append(Line(text=f"Lúc vào khoa (điều dưỡng đo): mạch {v['pulse']} lần/phút, nhiệt độ {vn(v['temp'])}°C, "
                                 f"HA {v['bp']} mmHg, nhịp thở {v['resp_rate']} lần/phút, SpO2 {v['spo2']}%.",
                            citations=[Citation(ref=adm["id"])]))
    s.lines += fl("O", "Dấu hiệu sinh tồn")
    if "can_nang" in miss:
        s.lines.append(missing_line("Cân nặng"))
    secs.append(s)

    s = Section(key="co_quan", title="III.2. Khám các cơ quan")
    s.lines = fl("O", "Khám các cơ quan") or [missing_line("Khám các cơ quan")]
    secs.append(s)

    s = Section(key="cls", title="III.3. Cận lâm sàng")
    s.lines = fl("O", "Cận lâm sàng")
    secs.append(s)

    s = Section(key="chan_doan", title="IV. Chẩn đoán (theo lời bác sĩ)")
    s.lines = fl("A") or [Line(text="Bác sĩ chưa nêu chẩn đoán trong buổi khám. AI không tự đưa chẩn đoán.", kind="missing")]
    for c in state["icd"]:
        s.lines.append(Line(text=f"Gợi ý ICD-10 {c['code']} – {c['display']} ({c['role']}, {c['match']}). Bác sĩ chọn mã.",
                            citations=[Citation(ref=c["from"])], kind="suggestion"))
    secs.append(s)

    s = Section(key="dieu_tri", title="VI. Hướng điều trị (theo lời bác sĩ)")
    s.lines = fl("P") or [missing_line("Hướng điều trị")]
    secs.append(s)
    return {"sections": secs}


def build_graph():
    g = StateGraph(S2)
    steps = [("normalize", normalize_turns), ("extract", extract), ("verify", verify_facts), ("context", context),
             ("missing", find_missing), ("safety", safety), ("icd", suggest_icd), ("compose", compose)]
    for name, fn in steps:
        g.add_node(name, fn)
    g.set_entry_point(steps[0][0])
    for (a, _), (b, _) in zip(steps, steps[1:]):
        g.add_edge(a, b)
    g.add_edge(steps[-1][0], END)
    return g.compile()


GRAPH = None


def draft_note(pid: str, tid: str) -> NoteDraft:
    global GRAPH
    GRAPH = GRAPH or build_graph()
    st = GRAPH.invoke({"pid": pid, "tid": tid})
    return NoteDraft(patient_id=pid, transcript_id=tid, mode=st.get("mode", "offline"), sections=st["sections"],
                     flags=st["flags"], missing=st["missing"], icd_suggestions=st["icd"], facts=st["facts"],
                     dropped=st.get("dropped", []),
                     normalized_turns=[{"n": t["n"], "speaker": t["speaker"], "text": t["text"], "norm": t["norm"]} for t in st["turns"]],
                     disclaimer=DISCLAIMER)


def to_text(d: NoteDraft) -> str:
    """Bản văn bản để bác sĩ chỉnh trong editor."""
    out = []
    for s in d.sections:
        out.append(f"## {s.title}")
        for l in s.lines:
            refs = " ".join(f"[{c.ref}]" for c in l.citations)
            out.append(f"- {l.text}" + (f" {refs}" if refs else ""))
        out.append("")
    return "\n".join(out).strip() + "\n"
