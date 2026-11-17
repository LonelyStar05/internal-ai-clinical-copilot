"use client";

import { AlertTriangle, ArrowLeft, ClipboardPaste, Mic, Plus, ShieldCheck, Sparkles, Trash2, X } from "lucide-react";
import { cloneElement, useId, useMemo, useState, type ReactElement } from "react";
import {
  api,
  type FieldDraft, type HandoffConfirmResponse, type HandoffDraft, type HandoffFieldKey, type HandoffListKey, type ItemDraft, type User,
} from "@/lib/api";
import { VoiceRecorder, type RecTurn, type SpeakerDef } from "./voice-recorder";

const SPEAKERS: SpeakerDef[] = [
  { key: "BG", label: "Người bàn giao", hint: "1" },
  { key: "TN", label: "Người nhận", hint: "2" },
  { key: "DD", label: "Điều dưỡng", hint: "3" },
];
const speakerLabel: Record<string, string> = { BG: "Người bàn giao", TN: "Người nhận", DD: "Điều dưỡng", BS: "Bác sĩ", BN: "Người bệnh", NN: "Người nhà" };
const VITALS: { k: HandoffFieldKey; label: string; unit: string; mode: "numeric" | "decimal" | "text" }[] = [
  { k: "pulse", label: "Mạch", unit: "lần/phút", mode: "numeric" },
  { k: "temp", label: "Nhiệt độ", unit: "°C", mode: "decimal" },
  { k: "bp", label: "Huyết áp", unit: "mmHg", mode: "text" },
  { k: "resp_rate", label: "Nhịp thở", unit: "lần/phút", mode: "numeric" },
  { k: "spo2", label: "SpO2", unit: "%", mode: "numeric" },
  { k: "weight", label: "Cân nặng", unit: "kg", mode: "decimal" },
];
const LISTS: { k: HandoffListKey; label: string; placeholder: string }[] = [
  { k: "diagnoses", label: "Chẩn đoán / vấn đề chính", placeholder: "Ví dụ: Viêm phổi cộng đồng" },
  { k: "comorbidities", label: "Bệnh nền", placeholder: "Ví dụ: Tăng huyết áp" },
  { k: "meds", label: "Thuốc đang dùng", placeholder: "Tên thuốc, liều, cách dùng" },
  { k: "labs", label: "Xét nghiệm và hình ảnh quan trọng", placeholder: "Ví dụ: Kali 5,8 mmol/L" },
  { k: "pending", label: "Việc chờ xử lý / cần theo dõi", placeholder: "Ví dụ: Chờ kết quả cấy máu" },
];
const SAMPLE = `BG: Bàn giao bệnh nhân mới vào khoa Nội tổng hợp, buồng năm giường bảy.
BG: Bệnh nhân tên Nguyễn Thị Hoa, nữ, sinh năm một nghìn chín trăm năm mươi hai.
BG: Vào viện lúc chín giờ ba mươi sáng nay vì đau ngực trái và khó thở.
BG: Chẩn đoán ban đầu suy tim mất bù, theo dõi hội chứng vành cấp.
BG: Tiền sử tăng huyết áp, đái tháo đường type 2.
BG: Dị ứng penicillin, nổi mề đay.
BG: Đang dùng Amlodipin 5 mg ngày 1 viên, Metformin 850 mg ngày 2 lần.
BG: Sinh hiệu mạch một trăm linh hai, nhiệt độ ba mươi bảy độ hai, huyết áp một trăm năm mươi trên chín mươi, nhịp thở hai mươi tư, SpO2 chín mươi ba phần trăm.
DD: Mạch em đo lại lúc nãy là 96 ạ.
BG: Xét nghiệm troponin lần 1 âm tính, X-quang ngực có bóng tim to.
BG: Đang chờ kết quả troponin lần 2 lúc 15 giờ, cần theo dõi SpO2 và lượng nước tiểu.`;

type Values = Record<HandoffFieldKey, string>;
type AllergyStatus = "has" | "none" | "unknown" | "";
const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Có lỗi xảy ra.");

export function HandoffIntake({ user, onClose, onCreated }: { user: User; onClose: () => void; onCreated: (r: HandoffConfirmResponse) => void }) {
  const handoffSessionId = `handoff-${useId().replaceAll(":", "")}`;
  const [step, setStep] = useState<"input" | "review">("input");
  const [mode, setMode] = useState<"record" | "paste">("record");
  const [recTurns, setRecTurns] = useState<RecTurn[]>([]);
  const [paste, setPaste] = useState("");
  const [sent, setSent] = useState("");  // đúng văn bản đã phân tích, gửi lại khi xác nhận
  const [draft, setDraft] = useState<HandoffDraft | null>(null);
  const [values, setValues] = useState<Values | null>(null);
  const [lists, setLists] = useState<Record<HandoffListKey, string[]> | null>(null);
  const [allergyStatus, setAllergyStatus] = useState<AllergyStatus>("");
  const [allergies, setAllergies] = useState<string[]>([]);
  const [edited, setEdited] = useState<Set<string>>(new Set());
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [focusTurns, setFocusTurns] = useState<number[]>([]);

  const recText = recTurns.map((t) => `${t.speaker}: ${t.text.replace(/\s+/g, " ").trim()}`).join("\n");
  const hasInput = !!(recTurns.length || paste.trim() || draft);

  function cancel() {
    if (hasInput && !window.confirm("Hủy tiếp nhận bàn giao? Nội dung đã ghi và bản nháp sẽ bị bỏ, không có gì được lưu.")) return;
    onClose();
  }

  async function analyze(text: string) {
    setBusy(true); setError("");
    try {
      const d = await api<HandoffDraft>("/handoffs/parse", { body: { transcript_text: text } });
      const v = Object.fromEntries(Object.entries(d.fields).map(([k, f]) => [k, f.value ?? ""])) as Values;
      setDraft(d); setValues(v); setSent(text); setEdited(new Set()); setAck(false); setFocusTurns([]);
      setLists(Object.fromEntries(LISTS.map(({ k }) => [k, d.lists[k].map((i) => i.text)])) as Record<HandoffListKey, string[]>);
      setAllergies(d.lists.allergies.map((i) => i.text));
      setAllergyStatus((d.allergy_status.value as AllergyStatus) ?? "");
      setStep("review");
    } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }

  function setField(k: HandoffFieldKey, v: string) {
    setValues((old) => (old ? { ...old, [k]: v } : old));
    setEdited((s) => new Set(s).add(k));
  }
  function setList(k: HandoffListKey, items: string[]) {
    setLists((old) => (old ? { ...old, [k]: items } : old));
    setEdited((s) => new Set(s).add(k));
  }

  const missing = useMemo(() => {
    if (!draft || !values) return [];
    const m: string[] = draft.required.filter((k) => !values[k].trim()).map((k) => draft.labels[k] ?? k);
    if (!allergyStatus) m.push("Tình trạng dị ứng");
    if (allergyStatus === "has" && !allergies.some((a) => a.trim())) m.push("Dị nguyên");
    return m;
  }, [draft, values, allergyStatus, allergies]);

  async function confirmIntake() {
    if (!draft || !values || !lists) return;
    const num = (s: string, int = false) => { const t = s.trim().replace(",", "."); return t === "" ? null : int ? Number.parseInt(t, 10) : Number(t); };
    const clean = (xs: string[]) => xs.map((x) => x.trim()).filter(Boolean);
    const body = {
      transcript_text: sent, name: values.name.trim(), birth_year: num(values.birth_year, true), gender: values.gender,
      ward: values.ward.trim(), room: values.room.trim(), bed: values.bed.trim(),
      admitted_at: `${values.admitted_date}T${values.admitted_time}`, reason: values.reason.trim(),
      vitals: { pulse: num(values.pulse, true), temp: num(values.temp), bp: values.bp.trim() || null, resp_rate: num(values.resp_rate, true), spo2: num(values.spo2, true), weight: num(values.weight) },
      ...Object.fromEntries(LISTS.map(({ k }) => [k, clean(lists[k])])),
      allergies: allergyStatus === "has" ? clean(allergies) : [], allergy_status: allergyStatus, acknowledged_warnings: ack,
    };
    setBusy(true); setError("");
    try { onCreated(await api<HandoffConfirmResponse>("/handoffs/confirm", { body })); } catch (e) { setError(errMsg(e)); } finally { setBusy(false); }
  }

  const needAck = !!draft && draft.flag_count > 0;
  const canConfirm = step === "review" && missing.length === 0 && (!needAck || ack) && !busy;

  return (
    <div className="backdrop" role="presentation">
      <section className="dialog handoff" role="dialog" aria-modal="true" aria-labelledby="ho-title">
        <header>
          <div>
            <h2 id="ho-title">Tiếp nhận bàn giao người bệnh mới</h2>
            <p className="muted small">{step === "input" ? "Bước 1/2 · Ghi âm hoặc dán lời bàn giao" : "Bước 2/2 · Kiểm tra, sửa và xác nhận"} · chưa có gì được lưu</p>
          </div>
          <button type="button" className="icon-btn" onClick={cancel} aria-label="Hủy và đóng"><X aria-hidden="true" /></button>
        </header>

        {error && <p className="banner danger flat" role="alert"><AlertTriangle aria-hidden="true" /><span>{error}</span></p>}

        {step === "input" ? (
          <div className="ho-input">
            <div className="segmented" role="group" aria-label="Cách nhập">
              <button type="button" aria-pressed={mode === "record"} onClick={() => setMode("record")}><Mic aria-hidden="true" />Ghi âm</button>
              <button type="button" aria-pressed={mode === "paste"} onClick={() => setMode("paste")}><ClipboardPaste aria-hidden="true" />Dán transcript</button>
            </div>
            {mode === "record" ? (
              <VoiceRecorder turns={recTurns} setTurns={setRecTurns} onDraft={() => analyze(recText)} busy={busy} speakers={SPEAKERS}
                actionLabel="Phân tích bàn giao" busyLabel="Đang phân tích…" unsupportedHint="hoặc chuyển sang “Dán transcript”."
                caseId={handoffSessionId} caseLabel="Ca bàn giao mới · chưa tạo hồ sơ"
                context="Bàn giao người bệnh Khoa Nội chung. Hội thoại có thể xen kẽ tiếng Việt và English."
                hotwords="SpO2, troponin, HbA1c, eGFR, metformin, amlodipin, penicillin, suy tim, hội chứng vành cấp" />
            ) : (
              <div className="ho-paste">
                <label className="field">
                  <span>Lời bàn giao, mỗi dòng một lượt nói. Nhãn người nói (BG:, TN:, ĐD:) không bắt buộc.</span>
                  <textarea rows={12} value={paste} onChange={(e) => setPaste(e.target.value)} placeholder={"BG: Bàn giao bệnh nhân mới vào khoa Nội tổng hợp, buồng 5 giường 7…"} />
                  <small>{paste.trim() ? `${paste.split("\n").filter((l) => l.trim()).length} dòng · ${paste.length.toLocaleString("vi-VN")}/20.000 ký tự` : "Chưa có nội dung"}</small>
                </label>
                <div className="review-actions">
                  <button type="button" className="btn ghost" onClick={() => setPaste(SAMPLE)}>Dùng ví dụ giả lập</button>
                  <button type="button" className="btn primary" disabled={!paste.trim() || busy} onClick={() => analyze(paste)}><Sparkles aria-hidden="true" />{busy ? "Đang phân tích…" : "Phân tích bàn giao"}</button>
                </div>
              </div>
            )}
          </div>
        ) : draft && values && lists ? (
          <div className="ho-review">
            <div className="ho-form">
              <div className={`banner ${draft.flag_count || missing.length ? "warn" : "flat"} ho-summary`}>
                <AlertTriangle aria-hidden="true" />
                <span>
                  <strong>{missing.length ? `Còn thiếu ${missing.length} trường bắt buộc` : "Đủ trường bắt buộc"}</strong>
                  {draft.flag_count > 0 && <> · {draft.flag_count} mục mâu thuẫn hoặc không chắc chắn</>}
                  {" "}· {draft.mode === "llm" ? "trích xuất bằng LLM, đã kiểm chứng bằng quy tắc" : "trích xuất bằng quy tắc"}.
                  {missing.length > 0 && <small className="block">Thiếu: {missing.join(", ")}</small>}
                </span>
              </div>
              {draft.warnings.map((w) => <p key={w} className="muted small">{w}</p>)}

              <fieldset className="ho-group">
                <legend>Hành chính</legend>
                <Row draft={draft} k="name" edited={edited} onFocus={setFocusTurns} onUse={setField} wide>
                  <input value={values.name} onChange={(e) => setField("name", e.target.value)} autoComplete="off" />
                </Row>
                <Row draft={draft} k="birth_year" edited={edited} onFocus={setFocusTurns} onUse={setField}>
                  <input value={values.birth_year} onChange={(e) => setField("birth_year", e.target.value)} inputMode="numeric" maxLength={4} />
                </Row>
                <Row draft={draft} k="gender" edited={edited} onFocus={setFocusTurns} onUse={setField}>
                  <select value={values.gender} onChange={(e) => setField("gender", e.target.value)}>
                    <option value="">Chọn</option><option value="Nam">Nam</option><option value="Nữ">Nữ</option>
                  </select>
                </Row>
              </fieldset>

              <fieldset className="ho-group">
                <legend>Vị trí và phụ trách</legend>
                <Row draft={draft} k="ward" edited={edited} onFocus={setFocusTurns} onUse={setField} wide>
                  <input value={values.ward} onChange={(e) => setField("ward", e.target.value)} />
                </Row>
                <Row draft={draft} k="room" edited={edited} onFocus={setFocusTurns} onUse={setField}>
                  <input value={values.room} onChange={(e) => setField("room", e.target.value)} maxLength={10} />
                </Row>
                <Row draft={draft} k="bed" edited={edited} onFocus={setFocusTurns} onUse={setField}>
                  <input value={values.bed} onChange={(e) => setField("bed", e.target.value)} maxLength={10} />
                </Row>
                <div className="ho-field wide">
                  <span className="ho-label">Bác sĩ điều trị</span>
                  <p className="ho-static">
                    <ShieldCheck aria-hidden="true" />
                    {user.role === "doctor"
                      ? <>Giao cho <strong>{user.name}</strong> (bạn) sau khi xác nhận.</>
                      : <>Hồ sơ ở trạng thái <strong>Chưa phân công</strong>. Phân công ở trang “Phân công bệnh nhân”.</>}
                  </p>
                  {draft.fields.attending_spoken.value && (
                    <small className="muted">Bàn giao có nhắc “{draft.fields.attending_spoken.value}” (L{draft.fields.attending_spoken.turns.join(", L")}). Hệ thống không phân công theo tên nghe được.</small>
                  )}
                </div>
              </fieldset>

              <fieldset className="ho-group">
                <legend>Nhập viện</legend>
                <Row draft={draft} k="admitted_date" edited={edited} onFocus={setFocusTurns} onUse={setField}>
                  <input type="date" value={values.admitted_date} onChange={(e) => setField("admitted_date", e.target.value)} />
                </Row>
                <Row draft={draft} k="admitted_time" edited={edited} onFocus={setFocusTurns} onUse={setField}>
                  <input type="time" value={values.admitted_time} onChange={(e) => setField("admitted_time", e.target.value)} />
                </Row>
                <Row draft={draft} k="reason" edited={edited} onFocus={setFocusTurns} onUse={setField} wide>
                  <textarea rows={2} value={values.reason} onChange={(e) => setField("reason", e.target.value)} />
                </Row>
              </fieldset>

              <fieldset className="ho-group">
                <legend>Sinh hiệu</legend>
                {VITALS.map((v) => (
                  <Row key={v.k} draft={draft} k={v.k} edited={edited} onFocus={setFocusTurns} onUse={setField} unit={v.unit}>
                    <input value={values[v.k]} onChange={(e) => setField(v.k, e.target.value)} inputMode={v.mode} placeholder="—" />
                  </Row>
                ))}
              </fieldset>

              <fieldset className="ho-group">
                <legend>Dị ứng</legend>
                <div className="ho-field wide">
                  <span className="ho-label">Tình trạng dị ứng <Badge f={draft.allergy_status} required edited={edited.has("allergy_status")} onFocus={setFocusTurns} /></span>
                  <div className="segmented" role="radiogroup" aria-label="Tình trạng dị ứng">
                    {([["has", "Có dị ứng"], ["none", "Không dị ứng"], ["unknown", "Chưa rõ"]] as const).map(([k, l]) => (
                      <button key={k} type="button" role="radio" aria-checked={allergyStatus === k}
                        onClick={() => { setAllergyStatus(k); setEdited((s) => new Set(s).add("allergy_status")); }}>{l}</button>
                    ))}
                  </div>
                  <Notes f={draft.allergy_status} />
                </div>
                {allergyStatus === "has" && (
                  <ListEditor label="Dị nguyên và phản ứng" items={allergies} drafts={draft.lists.allergies} placeholder="Ví dụ: Penicillin, nổi mề đay"
                    onChange={(xs) => { setAllergies(xs); setEdited((s) => new Set(s).add("allergies")); }} onFocus={setFocusTurns} />
                )}
              </fieldset>

              {LISTS.map((l) => (
                <fieldset className="ho-group" key={l.k}>
                  <legend>{l.label}</legend>
                  <ListEditor label={l.label} items={lists[l.k]} drafts={draft.lists[l.k]} placeholder={l.placeholder} onChange={(xs) => setList(l.k, xs)} onFocus={setFocusTurns} />
                </fieldset>
              ))}

              {draft.dropped.length > 0 && (
                <details className="rejected">
                  <summary>{draft.dropped.length} nội dung bị loại vì không có căn cứ trong lời bàn giao</summary>
                  <ul>{draft.dropped.map((d, i) => <li key={i}>{d.field}: <q>{d.value}</q> ({d.source}) — {d.reason}</li>)}</ul>
                </details>
              )}
            </div>

            <aside className="ho-transcript" aria-label="Transcript đã chuẩn hóa">
              <h3>Transcript <small>{draft.turns.length} lượt · bấm nhãn L để xem nguồn</small></h3>
              <ol className="turns compact">
                {draft.turns.map((t) => (
                  <li key={t.n} className={focusTurns.includes(t.n) ? "active" : focusTurns.length ? "dim" : ""} id={`ho-l${t.n}`}>
                    <span className="turn-no">L{t.n}</span>
                    <div>
                      <span className={`spk ${t.speaker.toLowerCase()}`}>{speakerLabel[t.speaker] ?? t.speaker}</span>
                      <p>{t.text}</p>
                      {t.norm && t.norm !== t.text && <p className="norm">Chuẩn hóa: {t.norm}</p>}
                    </div>
                  </li>
                ))}
              </ol>
            </aside>
          </div>
        ) : null}

        <footer className="ho-foot">
          <button type="button" className="btn" onClick={cancel}>Hủy, không lưu</button>
          {step === "review" && <button type="button" className="btn ghost" onClick={() => { setStep("input"); setError(""); }}><ArrowLeft aria-hidden="true" />Quay lại transcript</button>}
          <span className="grow" />
          {step === "review" && needAck && (
            <label className="check">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              Tôi đã kiểm tra {draft?.flag_count} mục mâu thuẫn / không chắc chắn
            </label>
          )}
          {step === "review" && (
            <button type="button" className="btn primary" disabled={!canConfirm} onClick={confirmIntake}
              title={missing.length ? `Còn thiếu: ${missing.join(", ")}` : needAck && !ack ? "Cần xác nhận đã kiểm tra các cảnh báo" : undefined}>
              <ShieldCheck aria-hidden="true" />{busy ? "Đang lưu…" : "Xác nhận tiếp nhận"}
            </button>
          )}
        </footer>
      </section>
    </div>
  );
}

function Badge({ f, required, edited, onFocus }: { f: FieldDraft | ItemDraft; required?: boolean; edited?: boolean; onFocus: (t: number[]) => void }) {
  const cites = f.turns.length > 0 && (
    <button type="button" className="cite turn" onClick={() => onFocus(f.turns)} aria-label={`Xem lượt nói L${f.turns.join(", L")}`}>L{f.turns.join(",")}</button>
  );
  const tag = f.status === "missing"
    ? <span className={`tag ${required ? "danger" : ""}`}>{required ? "Thiếu" : "Chưa ghi nhận"}</span>
    : f.status === "conflict" ? <span className="tag danger">Mâu thuẫn</span>
      : f.status === "uncertain" ? <span className="tag warn">Không chắc chắn</span> : null;
  return <span className="ho-badges">{tag}{edited && <span className="tag ok">Đã sửa</span>}{cites}</span>;
}

function Notes({ f }: { f: FieldDraft | ItemDraft }) {
  if (!f.notes.length) return null;
  return <ul className="ho-notes">{f.notes.map((n) => <li key={n}>{n}</li>)}</ul>;
}

function Row({ draft, k, edited, onFocus, onUse, children, wide, unit }: {
  draft: HandoffDraft; k: HandoffFieldKey; edited: Set<string>; onFocus: (t: number[]) => void; onUse: (k: HandoffFieldKey, v: string) => void;
  children: ReactElement<{ id?: string }>; wide?: boolean; unit?: string;
}) {
  const id = useId();
  const f = draft.fields[k];
  const required = draft.required.includes(k);
  return (
    <div className={`ho-field ${wide ? "wide" : ""} st-${f.status}`}>
      <span className="ho-label"><label htmlFor={id}>{draft.labels[k] ?? k}</label>{required && <i aria-label="bắt buộc">*</i>}{unit && <small>{unit}</small>}<Badge f={f} required={required} edited={edited.has(k)} onFocus={onFocus} /></span>
      {cloneElement(children, { id })}
      {f.alternatives.length > 1 && (
        <span className="ho-alts">
          Các giá trị nghe được:
          {f.alternatives.map((a) => (
            <button key={a.value} type="button" className="btn ghost sm" onClick={() => { onUse(k, a.value); onFocus(a.turns); }}>
              {a.value} <small>L{a.turns.join(",")}</small>
            </button>
          ))}
        </span>
      )}
      <Notes f={f} />
    </div>
  );
}

function ListEditor({ label, items, drafts, placeholder, onChange, onFocus }: {
  label: string; items: string[]; drafts: ItemDraft[]; placeholder: string; onChange: (xs: string[]) => void; onFocus: (t: number[]) => void;
}) {
  return (
    <div className="ho-list">
      {items.length === 0 && <p className="muted small">Chưa ghi nhận trong bàn giao.</p>}
      {items.map((it, i) => {
        const d = drafts.find((x) => x.text === it);  // không khớp = bác sĩ tự nhập hoặc đã sửa mục AI
        return (
          <div className="ho-item" key={i}>
            <input value={it} onChange={(e) => onChange(items.map((x, j) => (j === i ? e.target.value : x)))} aria-label={`${label} ${i + 1}`} placeholder={placeholder} />
            <span className="ho-badges">
              {d ? <Badge f={d} onFocus={onFocus} /> : <span className="tag ok">Bác sĩ nhập / đã sửa</span>}
            </span>
            <button type="button" className="icon-btn" onClick={() => onChange(items.filter((_, j) => j !== i))} aria-label={`Xóa ${label} ${i + 1}`}><Trash2 aria-hidden="true" /></button>
            {d && d.notes.length > 0 && <Notes f={d} />}
          </div>
        );
      })}
      <button type="button" className="btn ghost sm" onClick={() => onChange([...items, ""])}><Plus aria-hidden="true" />Thêm</button>
    </div>
  );
}
