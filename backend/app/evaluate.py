"""Chấm tự động 2 module theo đáp án vàng (data/gold/<pid>.json) trên toàn bộ hồ sơ.

    python -m app.evaluate            # tổng hợp tất cả hồ sơ
    python -m app.evaluate p001       # một hồ sơ, in chi tiết

p001 là ca viết tay; p002 trở đi do scripts/generate_mock.py sinh, kèm đáp án tự sinh.
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from collections import defaultdict

from .core import kb as KB
from .modules.note import draft_note, to_text
from .modules.summary import summarize

INFO_KINDS = {"asr_normalized"}  # cờ thông tin, không tính vào precision


def load_gold(pid: str) -> dict:
    return json.loads((KB.DATA / "gold" / f"{pid}.json").read_text(encoding="utf-8"))


def all_gold_ids() -> list[str]:
    return sorted(p.stem for p in (KB.DATA / "gold").glob("p*.json"))


def _spec_list(x) -> list[dict]:
    return list(x.values()) if isinstance(x, dict) else list(x)


def eval_module1(pid: str) -> dict:
    g = load_gold(pid)["module1"]
    s = summarize(pid)
    specs = _spec_list(g["flags"])
    matched_ids, per = set(), []
    for spec in specs:
        hit = next((f for f in s.flags if f.kind == spec["kind"] and f.id not in matched_ids
                    and set(spec["must_cite"]) <= {c.ref for c in f.citations}), None)
        if hit:
            matched_ids.add(hit.id)
        per.append({"kind": spec["kind"], "found": hit is not None})
    extra = [{"kind": f.kind, "title": f.title} for f in s.flags if f.id not in matched_ids]
    lines = [l for sec in s.sections for l in sec.lines]
    facts = []
    for f in g["facts"]:
        hit = any(f["contains"].lower() in l.text.lower() and set(f["must_cite"]) <= {c.ref for c in l.citations} for l in lines)
        facts.append({"id": f["id"], "found": hit})
    text = " ".join(l.text.lower() for l in lines)
    return {
        "flags": per, "extra_flags": extra, "facts": facts,
        "forbidden_found": [w for w in g.get("forbidden", []) if w in text],
        "uncited": [l.text for l in lines if l.kind == "fact" and not l.citations],
        "dropped": s.dropped, "mode": s.mode,
    }


def _flag_match(spec: dict, f) -> bool:
    k = spec["kind"]
    if f.kind != k:
        return False
    if k == "red_flag":
        return f.data.get("rule") == spec["id"]
    if k == "interaction":
        return set(f.data.get("pair", [])) == set(spec["pair"])
    if k == "allergy_reminder":
        return f.data.get("substance") == spec["substance"]
    if k == "asr_normalized":
        return spec["value"] in f.data.get("normalized", "")
    if k == "allergy_cross":
        return f.id == f"allergy-cross-{spec['drug']}"
    if k == "renal_dose":
        return f.id == f"renal-{spec['drug']}"
    return True  # vital_abnormal


def eval_module2(pid: str) -> dict:
    gfull = load_gold(pid)
    g = gfull["module2"]
    d = draft_note(pid, g["transcript_id"])
    facts = []
    for f in g["facts"]:
        hit = any(x.section == f["section"] and f["turn"] in x.turns and all(k.lower() in x.text.lower() for k in f["keywords"])
                  for x in d.facts)
        facts.append({**f, "found": hit})
    gold_turn_sec = {(f["turn"], f["section"]) for f in g["facts"]}
    wrong = [{"section": x.section, "text": x.text, "turns": x.turns} for x in d.facts
             if not any((n, x.section) in gold_turn_sec for n in x.turns)]
    miss_got = {m["id"] for m in d.missing}
    specs = _spec_list(g["flags"])
    used, per = set(), []
    for spec in specs:
        hit = next((f for f in d.flags if f.id not in used and _flag_match(spec, f)), None)
        if hit:
            used.add(hit.id)
        per.append({"kind": spec["kind"], "found": hit is not None, "spec": spec})
    extra = [{"kind": f.kind, "title": f.title} for f in d.flags if f.id not in used and f.kind not in INFO_KINDS]
    body = "\n".join(l for l in to_text(d).splitlines() if "Gợi ý ICD" not in l)
    forbidden = ([n for n in g.get("forbidden_numbers", []) if n in body]
                 + [t for t in g.get("forbidden_text", []) if t.lower() in body.lower()]
                 + [p for p in g.get("forbidden_patterns", []) if re.search(p, body, flags=re.I)])
    return {
        "facts": facts, "n_ai_facts": len(d.facts), "wrong_facts": wrong,
        "missing_expected": g["missing"], "missing_got": sorted(miss_got),
        "flags": per, "extra_flags": extra, "forbidden_found": forbidden, "dropped": d.dropped, "mode": d.mode,
    }


def run(pids: list[str] | None = None) -> dict:
    pids = pids or all_gold_ids()
    agg = defaultdict(lambda: [0, 0])  # tên -> [đúng, tổng]
    by_kind1, by_kind2 = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    extra1, extra2, failures, errors = 0, 0, [], []
    n_forbidden = n_uncited = n_dropped = 0
    mode = None
    for pid in pids:
        try:
            m1, m2 = eval_module1(pid), eval_module2(pid)
        except Exception as e:  # một hồ sơ lỗi không làm dừng cả bộ
            errors.append({"pid": pid, "error": repr(e), "trace": traceback.format_exc()[-600:]})
            continue
        mode = m2["mode"]
        for f in m1["flags"]:
            by_kind1[f["kind"]][0] += f["found"]; by_kind1[f["kind"]][1] += 1
        for f in m1["facts"]:
            agg["m1_facts"][0] += f["found"]; agg["m1_facts"][1] += 1
        extra1 += len(m1["extra_flags"])
        for f in m2["flags"]:
            by_kind2[f["kind"]][0] += f["found"]; by_kind2[f["kind"]][1] += 1
        extra2 += len(m2["extra_flags"])
        for f in m2["facts"]:
            agg["m2_fact_recall"][0] += f["found"]; agg["m2_fact_recall"][1] += 1
        agg["m2_fact_precision"][0] += m2["n_ai_facts"] - len(m2["wrong_facts"])
        agg["m2_fact_precision"][1] += m2["n_ai_facts"]
        exp, got = set(m2["missing_expected"]), set(m2["missing_got"])
        agg["m2_missing_recall"][0] += len(exp & got); agg["m2_missing_recall"][1] += len(exp)
        agg["m2_missing_precision"][0] += len(exp & got); agg["m2_missing_precision"][1] += len(got)
        n_forbidden += len(m1["forbidden_found"]) + len(m2["forbidden_found"])
        n_uncited += len(m1["uncited"])
        n_dropped += len(m1["dropped"]) + len(m2["dropped"])
        bad = ([f"M1 sót cờ {f['kind']}" for f in m1["flags"] if not f["found"]]
               + [f"M1 cờ thừa {f['kind']}: {f['title']}" for f in m1["extra_flags"]]
               + [f"M1 sót fact {f['id']}" for f in m1["facts"] if not f["found"]]
               + [f"M2 sót fact lượt {f['turn']} ({f['section']}: {', '.join(f['keywords'])})" for f in m2["facts"] if not f["found"]]
               + [f"M2 fact lệch mục: [{w['section']}] {w['text']}" for w in m2["wrong_facts"]]
               + [f"M2 sót cờ {f['kind']} {json.dumps({k: v for k, v in f['spec'].items() if k != 'kind'}, ensure_ascii=False)}" for f in m2["flags"] if not f["found"]]
               + [f"M2 cờ thừa {f['kind']}: {f['title']}" for f in m2["extra_flags"]]
               + [f"M2 'Chưa ghi nhận' sai: thiếu {sorted(exp - got)}, thừa {sorted(got - exp)}"] * (exp != got)
               + [f"Nội dung cấm: {x}" for x in m1["forbidden_found"] + m2["forbidden_found"]])
        if bad:
            failures.append({"pid": pid, "issues": bad})

    def rate(x):
        return round(x[0] / x[1], 3) if x[1] else None

    f1_found = sum(v[0] for v in by_kind1.values())
    f2_found = sum(v[0] for v in by_kind2.values())
    return {
        "n_records": len(pids) - len(errors), "mode": mode, "errors": errors,
        "module1": {
            "flag_recall": rate([f1_found, sum(v[1] for v in by_kind1.values())]),
            "flag_precision": rate([f1_found, f1_found + extra1]),
            "flag_recall_by_kind": {k: {"found": v[0], "total": v[1]} for k, v in sorted(by_kind1.items())},
            "fact_recall": rate(agg["m1_facts"]),
            "uncited_lines": n_uncited,
        },
        "module2": {
            "fact_recall": rate(agg["m2_fact_recall"]),
            "fact_precision": rate(agg["m2_fact_precision"]),
            "missing_recall": rate(agg["m2_missing_recall"]),
            "missing_precision": rate(agg["m2_missing_precision"]),
            "flag_recall": rate([f2_found, sum(v[1] for v in by_kind2.values())]),
            "flag_precision": rate([f2_found, f2_found + extra2]),
            "flag_recall_by_kind": {k: {"found": v[0], "total": v[1]} for k, v in sorted(by_kind2.items())},
        },
        "forbidden_found": n_forbidden,
        "dropped_by_verifier": n_dropped,
        "failures": failures,
    }


def pct(x):
    return "–" if x is None else f"{x:.0%}"


if __name__ == "__main__":
    # Console Windows mặc định cp1252, không in được tiếng Việt.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if args and args[0] != "--json":
        pid = args[0]
        print(json.dumps({"module1": eval_module1(pid), "module2": eval_module2(pid)}, ensure_ascii=False, indent=2, default=str))
        sys.exit()
    r = run()
    if "--json" in args:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        sys.exit()
    m1, m2 = r["module1"], r["module2"]
    print(f"Hồ sơ chấm: {r['n_records']} · chế độ {r['mode']} · lỗi chạy: {len(r['errors'])}")
    print(f"Module 1: cờ recall {pct(m1['flag_recall'])} / precision {pct(m1['flag_precision'])} · facts {pct(m1['fact_recall'])} · câu không nguồn {m1['uncited_lines']}")
    for k, v in m1["flag_recall_by_kind"].items():
        print(f"    {k}: {v['found']}/{v['total']}")
    print(f"Module 2: facts recall {pct(m2['fact_recall'])} / precision {pct(m2['fact_precision'])} · "
          f"'Chưa ghi nhận' recall {pct(m2['missing_recall'])} / precision {pct(m2['missing_precision'])} · "
          f"cờ recall {pct(m2['flag_recall'])} / precision {pct(m2['flag_precision'])}")
    for k, v in m2["flag_recall_by_kind"].items():
        print(f"    {k}: {v['found']}/{v['total']}")
    print(f"Nội dung cấm: {r['forbidden_found']} · bị verifier loại: {r['dropped_by_verifier']} · hồ sơ có lỗi: {len(r['failures'])}")
    for f in r["failures"][:15]:
        print(f"  {f['pid']}: " + " | ".join(f["issues"][:4]))
    for e in r["errors"][:5]:
        print("ERROR", e["pid"], e["error"])
