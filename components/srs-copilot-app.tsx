"use client";

import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Check,
  ChevronRight,
  ClipboardPaste,
  Copy,
  Download,
  FileCheck2,
  Lock,
  Mic,
  PencilLine,
  RotateCcw,
  Search,
  ShieldAlert,
  Sparkles,
  UserCheck,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api, fmtDate, fmtNum, useUser,
  type Draft, type DraftResponse, type EditStats, type Flag, type Line, type NoteMeta, type NoteRecord, type Patient, type PatientRow,
  type Review, type Summary, type SummaryResponse, type Turn, type User,
} from "@/lib/api";
import { AppShell } from "./app-shell";
import { HandoffIntake } from "./handoff-intake";
import { VoiceRecorder, type RecTurn } from "./voice-recorder";

type Tab = "summary" | "note" | "transcript";
type TranscriptMeta = { id: string; date: string; turns: number };

const YEAR = new Date().getFullYear();
const speakerLabel: Record<string, string> = { BS: "Bác sĩ", BN: "Người bệnh", NN: "Người nhà" };
const sevClass: Record<Flag["severity"], string> = { "đỏ": "red", cao: "high", "trung bình": "medium", "thông tin": "info" };
const sevLabel: Record<Flag["severity"], string> = { "đỏ": "Cờ đỏ", cao: "Cao", "trung bình": "Trung bình", "thông tin": "Thông tin" };
const sevOrder: Record<Flag["severity"], number> = { "đỏ": 0, cao: 1, "trung bình": 2, "thông tin": 3 };

const initials = (name: string) => name.split(" ").slice(-2).map((w) => w[0]).join("").toUpperCase();
const isTurn = (ref: string) => /^L\d+$/.test(ref);
const bedShort = (bed: string) => bed.replace("Buồng ", "B").replace(" - Giường ", " · G");
const bedLong = (bed: string) => bed.replace(" - ", " · ");
const stripNo = (title: string) => title.replace(/^\d+\.\s*/, "").replace(/\s*\(.*\)$/, "");
const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Có lỗi xảy ra.");
const READ_ONLY = "Truy cập khẩn cấp chỉ cho xem";

/** Bệnh án đã lưu -> trạng thái hiển thị (dùng chung khung NoteDoc, chỉ đọc). */
function fromSaved(r: NoteRecord) {
  return {
    note: { note_id: r.id, draft: JSON.parse(r.ai_json) as Draft, text: r.ai_text } satisfies DraftResponse,
    text: r.final_text ?? r.ai_text,
    stats: r.diff_json ? (JSON.parse(r.diff_json) as EditStats) : null,
    approver: r.approved_by,
  };
}

/* ------------------------------------------------------------------ */
/* App                                                                 */
/* ------------------------------------------------------------------ */

export function SrsCopilotApp() {
  const router = useRouter();
  const user = useUser();

  useEffect(() => {
    if (user === null) router.replace("/login");
    else if (user && user.role === "admin") router.replace("/admin");
  }, [user, router]);

  if (!user || user.role !== "doctor") return <div className="boot">Đang mở…</div>;
  return <DoctorApp user={user} />;
}

function DoctorApp({ user }: { user: User }) {
  const [patients, setPatients] = useState<PatientRow[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [open, setOpen] = useState<{ id: string; emergency: string | null } | null>(null);
  const [breakGlass, setBreakGlass] = useState(false);
  const [intake, setIntake] = useState(false);
  const [toast, setToast] = useState("");

  // Danh sách chỉ gồm người bệnh đang phân công cho bác sĩ đăng nhập.
  const reload = useCallback(() => api<PatientRow[]>("/patients").then((d) => { setPatients(d); setLoadError(""); }).catch((e) => setLoadError(errMsg(e))), []);
  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(""), 3600);
    return () => window.clearTimeout(t);
  }, [toast]);

  function openPatient(p: PatientRow) { setOpen({ id: p.id, emergency: null }); }

  const mine = patients ?? [];

  return (
    <AppShell
      user={user}
      active="patients"
      quickPatients={mine.slice(0, 8).map((p) => ({ id: p.id, name: p.name ?? p.id, bed: bedShort(p.bed) }))}
      currentPatientId={open?.id}
      onQuickOpen={(id) => setOpen({ id, emergency: null })}
      onNavPatients={() => setOpen(null)}
    >
      {open ? (
        <PatientRecord key={`${open.id}-${open.emergency ?? ""}`} pid={open.id} emergency={open.emergency} user={user} onBack={() => setOpen(null)} toast={setToast} onChanged={reload} />
      ) : loadError ? (
        <div className="page"><p className="banner danger flat"><AlertTriangle aria-hidden="true" /><span>{loadError}</span></p></div>
      ) : (
        <PatientList patients={patients} onOpen={openPatient} onIntake={() => setIntake(true)} onEmergency={() => setBreakGlass(true)} />
      )}

      {breakGlass && (
        <BreakGlassDialog
          onCancel={() => setBreakGlass(false)}
          onConfirm={(id, reason) => {
            setBreakGlass(false);
            // hồ sơ của chính mình thì mở bình thường, không cần lý do khẩn cấp
            setOpen(mine.some((p) => p.id === id) ? { id, emergency: null } : { id, emergency: reason });
          }}
        />
      )}
      {intake && (
        <HandoffIntake user={user} onClose={() => setIntake(false)} onCreated={async (r) => {
          setIntake(false);
          await reload();
          setOpen({ id: r.patient_id, emergency: null });
          setToast(`Đã tạo hồ sơ ${r.patient_id} và giao cho bạn. Transcript bàn giao đã được lưu.`);
        }} />
      )}

      {toast && (
        <div className="toast" role="status" aria-live="polite">
          <Check aria-hidden="true" />
          <span>{toast}</span>
          <button type="button" onClick={() => setToast("")} aria-label="Đóng thông báo"><X aria-hidden="true" /></button>
        </div>
      )}
    </AppShell>
  );
}

/* ------------------------------------------------------------------ */
/* Danh sách người bệnh                                                */
/* ------------------------------------------------------------------ */

function PatientList({ patients, onOpen, onIntake, onEmergency }: { patients: PatientRow[] | null; onOpen: (p: PatientRow) => void; onIntake: () => void; onEmergency: () => void }) {
  const [q, setQ] = useState("");
  const all = patients ?? [];
  const newCount = all.filter((p) => p.is_new).length;

  const rows = useMemo(() => {
    const needle = q.trim().toLocaleLowerCase("vi");
    const list = (patients ?? []).filter((p) => !needle || [p.id, p.name ?? "", p.bed, p.reason ?? ""].join(" ").toLocaleLowerCase("vi").includes(needle));
    return [...list].sort((a, b) => Number(!!b.is_new) - Number(!!a.is_new));  // hồ sơ mới được phân công lên đầu
  }, [q, patients]);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Đang điều trị</h1>
          <p>{patients ? `${all.length} người bệnh đang phân công cho bạn${newCount ? ` · ${newCount} mới được phân công, chờ bạn tiếp nhận` : ""}` : "Đang tải danh sách…"}</p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn" onClick={onEmergency}><ShieldAlert aria-hidden="true" />Truy cập khẩn cấp</button>
          <button type="button" className="btn primary" onClick={onIntake}><Mic aria-hidden="true" />Tiếp nhận bàn giao</button>
        </div>
      </header>

      <div className="toolbar">
        <label className="search">
          <Search aria-hidden="true" />
          <span className="sr-only">Tìm người bệnh</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm theo tên, mã, giường, lý do vào viện" />
        </label>
      </div>

      <div className="table patient-table" role="table" aria-label="Danh sách người bệnh">
        <div className="tr th" role="row">
          <span role="columnheader">Người bệnh</span>
          <span role="columnheader">Mã</span>
          <span role="columnheader">Vị trí</span>
          <span role="columnheader">Lý do vào viện</span>
          <span role="columnheader" className="sr-only">Mở</span>
        </div>
        {rows.map((p) => (
          <button type="button" className={`tr ${p.is_new ? "is-new" : ""}`} role="row" key={p.id} onClick={() => onOpen(p)}>
            <span className="cell-person" role="cell">
              <span className="avatar sm">{p.name ? initials(p.name) : <Lock aria-hidden="true" />}</span>
              <span>
                <strong>{p.name}{p.is_new && <span className="tag warn">Mới được phân công</span>}</strong>
                <small>{p.birth_year ? `${p.gender}, ${YEAR - p.birth_year} tuổi` : ""}</small>
              </span>
            </span>
            <span className="mono" role="cell">{p.id}</span>
            <span role="cell">{bedLong(p.bed)}</span>
            <span className="cell-reason" role="cell">{p.reason ?? "—"}</span>
            <span className="cell-action" role="cell">{p.is_new ? <em>Cần tiếp nhận</em> : <ChevronRight aria-hidden="true" />}</span>
          </button>
        ))}
        {patients && rows.length === 0 && (
          <div className="empty">
            <strong>{all.length ? "Không có người bệnh phù hợp" : "Chưa có người bệnh nào được phân công cho bạn"}</strong>
            <span>{all.length ? "Thử từ khóa khác." : "Quản trị phân công hồ sơ ở trang “Phân công bệnh nhân”, hoặc bấm “Tiếp nhận bàn giao”."}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function BreakGlassDialog({ onCancel, onConfirm }: { onCancel: () => void; onConfirm: (id: string, reason: string) => void }) {
  const [id, setId] = useState("");
  const [reason, setReason] = useState("");
  const len = reason.trim().length;
  const idOk = /^[A-Za-z0-9_-]{1,40}$/.test(id.trim());
  const ok = len >= 10 && idOk;
  return (
    <div className="backdrop" role="presentation" onClick={onCancel}>
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="bg-title" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2 id="bg-title">Truy cập khẩn cấp hồ sơ khác</h2>
          <button type="button" className="icon-btn" onClick={onCancel} aria-label="Đóng"><X aria-hidden="true" /></button>
        </header>
        <p>
          Chỉ dùng khi cần cho việc chăm sóc người bệnh không do bạn phụ trách (trực đêm, cấp cứu). Lần truy cập chỉ cho xem,
          không được rà soát, soạn, sửa, ký hay xuất FHIR, và được ghi vào audit log kèm lý do.
        </p>
        <label className="field">
          <span>Mã hồ sơ</span>
          <input value={id} onChange={(e) => setId(e.target.value)} placeholder="Ví dụ: p061" autoFocus spellCheck={false} />
          {id && !idOk && <small className="err">Mã chỉ gồm chữ, số, “-” và “_”</small>}
        </label>
        <label className="field">
          <span>Lý do truy cập</span>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="Ví dụ: Trực đêm, cần kiểm tra thuốc đang dùng trước khi xử trí" />
          <small className={len >= 10 ? "ok" : ""}>{len >= 10 ? "Đủ độ dài" : `Tối thiểu 10 ký tự (${len}/10)`}</small>
        </label>
        <footer>
          <button type="button" className="btn" onClick={onCancel}>Hủy</button>
          <button type="button" className="btn danger" disabled={!ok} onClick={() => onConfirm(id.trim(), reason.trim())}>Truy cập khẩn cấp</button>
        </footer>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Hồ sơ người bệnh                                                    */
/* ------------------------------------------------------------------ */

function PatientRecord({ pid, emergency, user, onBack, toast, onChanged }: { pid: string; emergency: string | null; user: User; onBack: () => void; toast: (m: string) => void; onChanged: () => void }) {
  const [data, setData] = useState<SummaryResponse | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("summary");
  const [inspector, setInspector] = useState<"flags" | "source" | "icd">("flags");
  const [selected, setSelected] = useState<string | null>(null);

  // Module 2
  const [transcripts, setTranscripts] = useState<TranscriptMeta[]>([]);
  const [tid, setTid] = useState("");
  const [note, setNote] = useState<DraftResponse | null>(null);
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);
  const [stats, setStats] = useState<EditStats | null>(null);
  const [drafting, setDrafting] = useState(false);
  const [draftError, setDraftError] = useState("");
  const [signOpen, setSignOpen] = useState(false);
  const [fhir, setFhir] = useState<string | null>(null);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pickedIcd, setPickedIcd] = useState<string[]>([]);
  const [recTurns, setRecTurns] = useState<RecTurn[]>([]);
  // Truy cập khẩn cấp: xem bệnh án đã lưu
  const [savedNotes, setSavedNotes] = useState<NoteMeta[]>([]);
  const [noteApprover, setNoteApprover] = useState<string | null>(null);

  const [accepting, setAccepting] = useState(false);

  // Truy cập khẩn cấp là chỉ đọc: xem tóm tắt, nguồn, transcript, bệnh án đã có; không rà soát, soạn, sửa, ký, xuất FHIR.
  // Quyền ghi do server quyết định (đang phụ trách + đã tiếp nhận hồ sơ).
  const pending = !emergency && data?.assignment.status === "pending";
  const canWrite = !emergency && !!data?.can_write;
  const roTitle = emergency ? READ_ONLY : pending ? "Bấm “Tiếp nhận hồ sơ” trước khi thao tác ghi" : "Bạn không còn phụ trách hồ sơ này";
  const q = emergency ? `?emergency_reason=${encodeURIComponent(emergency)}` : "";

  async function acceptAssignment() {
    setAccepting(true);
    try {
      await api(`/patients/${pid}/accept-assignment`, { method: "POST", body: {} });
      setData(await api<SummaryResponse>(`/patients/${pid}/summary`));
      onChanged();
      toast("Đã tiếp nhận hồ sơ. Bạn có thể rà soát, soạn nháp và ký duyệt.");
    } catch (e) { toast(errMsg(e)); } finally { setAccepting(false); }
  }

  useEffect(() => {
    let alive = true;
    api<SummaryResponse>(`/patients/${pid}/summary${q}`).then((d) => { if (alive) setData(d); }).catch((e) => { if (alive) setError(errMsg(e)); });
    api<TranscriptMeta[]>(`/patients/${pid}/transcripts${q}`).then((t) => { if (alive) { setTranscripts(t); setTid(t[0]?.id ?? ""); } }).catch(() => undefined);
    if (emergency) {
      api<NoteMeta[]>(`/patients/${pid}/notes${q}`)
        .then(async (list) => {
          if (!alive) return;
          setSavedNotes(list);
          if (!list[0]) return;
          const s = fromSaved(await api<NoteRecord>(`/notes/${list[0].id}${q}`));
          if (alive) { setNote(s.note); setText(s.text); setStats(s.stats); setNoteApprover(s.approver); }
        })
        .catch((e) => { if (alive) setDraftError(errMsg(e)); });
    }
    return () => { alive = false; };
  }, [pid, q, emergency]);

  function show(ref: string) { setSelected(ref); setInspector("source"); }

  function switchTab(t: Tab) {
    setTab(t); setInspector("flags"); setSelected(null);
  }

  async function openSaved(nid: string) {
    setDraftError("");
    try {
      const s = fromSaved(await api<NoteRecord>(`/notes/${nid}${q}`));
      setNote(s.note); setText(s.text); setStats(s.stats); setNoteApprover(s.approver); setSelected(null); setInspector("flags");
    } catch (e) { setDraftError(errMsg(e)); }
  }

  async function draft(body: { transcript_id?: string; transcript_text?: string }) {
    if (!canWrite) return false;
    setDrafting(true); setDraftError("");
    try {
      const d = await api<DraftResponse>("/notes/draft", { body: { patient_id: pid, ...body } });
      setNote(d); setText(d.text); setStats(null); setEditing(false); setPickedIcd([]);
      if (body.transcript_text) {
        setTid(d.draft.transcript_id);
        api<TranscriptMeta[]>(`/patients/${pid}/transcripts`).then(setTranscripts).catch(() => undefined);
      }
      setTab("note"); setInspector("flags"); setSelected(null);
      toast(`Đã soạn nháp từ ${d.draft.transcript_id} và kiểm chứng từng dòng.`);
      return true;
    } catch (e) { setDraftError(errMsg(e)); return false; } finally { setDrafting(false); }
  }

  async function sign() {
    if (!note || !canWrite) return;
    try {
      const r = await api<{ stats: EditStats }>(`/notes/${note.note_id}/approve`, { body: { final_text: text } });
      setStats(r.stats); setEditing(false); setSignOpen(false);
      toast("Đã ký duyệt. Bệnh án chuyển sang chỉ đọc.");
    } catch (e) { setSignOpen(false); setDraftError(errMsg(e)); }
  }

  async function exportFhir() {
    if (!note || !canWrite) return;
    try { setFhir(JSON.stringify(await api<unknown>(`/notes/${note.note_id}/fhir`), null, 2)); } catch (e) { setDraftError(errMsg(e)); }
  }

  if (error) {
    return <div className="page"><p className="banner danger flat"><AlertTriangle aria-hidden="true" /><span>{error}</span></p><button type="button" className="btn" onClick={onBack}>Về danh sách</button></div>;
  }
  if (!data) return <div className="boot">Đang đọc hồ sơ và chạy quy tắc…</div>;

  const p: Patient = data.patient;
  const signed = !!stats;
  const flags = [...(tab === "summary" ? data.summary.flags : note?.draft.flags ?? [])].sort((a, b) => sevOrder[a.severity] - sevOrder[b.severity]);
  const turns = note?.draft.normalized_turns ?? [];

  return (
    <div className="record">
      <header className="record-head">
        <nav className="crumbs" aria-label="Đường dẫn">
          <button type="button" onClick={onBack}>Người bệnh</button>
          <ChevronRight aria-hidden="true" />
          <span>{p.name}</span>
        </nav>
        <div className="record-title">
          <span className="avatar lg">{initials(p.name)}</span>
          <div>
            <h1>{p.name}</h1>
            <p className="meta">
              <span>{p.gender}, {YEAR - p.birth_year} tuổi</span>
              <span>{bedLong(p.bed)}</span>
              {p.admission?.ward_at && <span>Vào khoa {fmtDate(p.admission.ward_at)}</span>}
              <span>BS điều trị: <span className="mono">{p.attending}</span></span>
              <span className="mono">{p.id}</span>
            </p>
          </div>
        </div>
        <div className="tabs" role="tablist" aria-label="Nội dung hồ sơ">
          <button role="tab" type="button" aria-selected={tab === "summary"} onClick={() => switchTab("summary")}>Tóm tắt hồ sơ</button>
          <button role="tab" type="button" aria-selected={tab === "note"} onClick={() => switchTab("note")}>
            {!emergency ? "Bệnh án nháp" : "Bệnh án đã có"} {note && (signed ? <span className="tab-badge ok">Đã ký</span> : <span className="tab-badge">Nháp</span>)}
          </button>
          <button role="tab" type="button" aria-selected={tab === "transcript"} onClick={() => switchTab("transcript")}>Transcript</button>
          {emergency && <span className="tab-badge" style={{ alignSelf: "center" }} title={READ_ONLY}>Truy cập khẩn cấp · chỉ đọc</span>}
          {!emergency && !canWrite && <span className="tab-badge" style={{ alignSelf: "center" }} title={roTitle}>Chỉ đọc · {pending ? "chờ bạn tiếp nhận" : "không còn phụ trách"}</span>}
        </div>
      </header>

      {pending && (
        <div className="banner accept" role="note">
          <UserCheck aria-hidden="true" />
          <p>
            <strong>Hồ sơ mới được phân công cho bạn</strong>
            {data.assignment.assigned_by && <> bởi <span className="mono">{data.assignment.assigned_by}</span></>}
            {data.assignment.note && <> · “{data.assignment.note}”</>}. Bạn đã xem được hồ sơ; bấm “Tiếp nhận hồ sơ” để nhận trách nhiệm và bắt đầu rà soát, soạn nháp, ký duyệt.
          </p>
          <button type="button" className="btn primary" onClick={acceptAssignment} disabled={accepting}><UserCheck aria-hidden="true" />{accepting ? "Đang lưu…" : "Tiếp nhận hồ sơ"}</button>
        </div>
      )}

      {emergency && (
        <div className="banner danger" role="note">
          <ShieldAlert aria-hidden="true" />
          <p>
            <strong>Truy cập khẩn cấp, chỉ đọc.</strong> Lý do: “{emergency}”. Mọi lần xem đều được ghi vào audit log.
            {" "}Bạn xem được tóm tắt, bản ghi gốc, transcript và bệnh án đã có; không được rà soát tóm tắt, soạn nháp, sửa, ký duyệt hay xuất FHIR.
          </p>
        </div>
      )}

      <div className="workspace">
        <div className="doc-col">
          {tab === "summary" && (
            <SummaryDoc pid={pid} summary={data.summary} lastReview={data.last_review} onRef={show} selected={selected} readOnly={canWrite ? null : emergency ? "Truy cập khẩn cấp chỉ đọc: không được rà soát tóm tắt." : `${roTitle}.`} toast={toast} onShowFlags={() => setInspector("flags")} />
          )}
          {tab === "note" && (
            <article className="doc">
              <div className="doc-toolbar">
                {!emergency ? (
                  <label className="select">
                    <span className="sr-only">Transcript</span>
                    <select value={tid} onChange={(e) => setTid(e.target.value)} disabled={drafting}>
                      {transcripts.length === 0 && <option value="">Chưa có transcript</option>}
                      {transcripts.map((t) => <option key={t.id} value={t.id}>{t.id} · {t.turns} lượt</option>)}
                    </select>
                  </label>
                ) : (
                  <label className="select">
                    <span className="sr-only">Bệnh án đã có</span>
                    <select value={note?.note_id ?? ""} onChange={(e) => openSaved(e.target.value)} disabled={savedNotes.length === 0}>
                      {savedNotes.length === 0 && <option value="">Chưa có bệnh án</option>}
                      {savedNotes.map((n) => <option key={n.id} value={n.id}>{n.status === "approved" ? "Đã ký" : "Nháp"} · {fmtDate(n.approved_at ?? n.created_at)} · {n.transcript_id}</option>)}
                    </select>
                  </label>
                )}
                <button type="button" className="btn ghost" onClick={() => setPasteOpen(true)} disabled={drafting || !canWrite} title={canWrite ? undefined : roTitle}><ClipboardPaste aria-hidden="true" />Dán transcript</button>
                {note && <button type="button" className="btn ghost" onClick={() => draft({ transcript_id: tid })} disabled={drafting || !tid || !canWrite} title={canWrite ? undefined : roTitle}><RotateCcw aria-hidden="true" className={drafting ? "spin" : ""} />{drafting ? "Đang soạn…" : "Soạn lại"}</button>}
                <span className="grow" />
                {note && !signed && (
                  <>
                    <button type="button" className="btn" onClick={() => setEditing(!editing)} disabled={!canWrite} title={canWrite ? undefined : roTitle}>{editing ? "Xem kèm nguồn" : <><PencilLine aria-hidden="true" />Chỉnh sửa</>}</button>
                    <button type="button" className="btn primary" onClick={() => setSignOpen(true)} disabled={!canWrite} title={canWrite ? undefined : roTitle}><FileCheck2 aria-hidden="true" />Ký duyệt</button>
                  </>
                )}
                {signed && <button type="button" className="btn primary" onClick={exportFhir} disabled={!canWrite} title={canWrite ? undefined : roTitle}><Download aria-hidden="true" />Xuất FHIR</button>}
              </div>
              {draftError && <p className="rec-error" role="alert">{draftError}</p>}
              {!note ? (
                !emergency ? (
                  <div className="empty tall">
                    <strong>Chưa có bản nháp</strong>
                    <span>{tid ? `Soạn bệnh án từ transcript ${tid}, hoặc dán / ghi âm một buổi khám mới.` : "Người bệnh này chưa có transcript. Dán transcript hoặc ghi âm ở tab Transcript."}</span>
                    <button type="button" className="btn primary" disabled={!tid || drafting || !canWrite} title={canWrite ? undefined : roTitle} onClick={() => draft({ transcript_id: tid })}><Sparkles aria-hidden="true" />{drafting ? "Đang soạn…" : "Soạn nháp bệnh án"}</button>
                  </div>
                ) : (
                  <div className="empty tall">
                    <strong>Chưa có bệnh án được lưu</strong>
                    <span>Người bệnh này chưa có bản nháp hay bệnh án đã ký. Truy cập khẩn cấp không được soạn nháp.</span>
                    <button type="button" className="btn primary" disabled title={READ_ONLY}><Lock aria-hidden="true" />Soạn nháp bệnh án</button>
                  </div>
                )
              ) : (
                <NoteDoc draft={note.draft} aiText={note.text} text={text} setText={setText} editing={editing && canWrite} stats={stats} onRef={show} selected={selected} approver={noteApprover ?? user.name} />
              )}
            </article>
          )}
          {tab === "transcript" && (
            <TranscriptDoc pid={pid} q={q} readOnly={!canWrite} tid={tid} setTid={setTid} transcripts={transcripts} draftTurns={note?.draft.transcript_id === tid ? turns : null}
              recTurns={recTurns} setRecTurns={setRecTurns} drafting={drafting} error={draftError}
              onDraft={async () => { if (await draft({ transcript_text: recTurns.map((t) => `${t.speaker}: ${t.text.replace(/\s+/g, " ").trim()}`).join("\n") })) setRecTurns(() => []); }} />
          )}
          <p className="doc-foot"><AlertTriangle aria-hidden="true" />{data.summary.disclaimer}</p>
        </div>

        {tab !== "transcript" && (
          <aside className="inspector" aria-label="Panel rà soát">
            <div className="inspector-tabs" role="tablist">
              <button role="tab" type="button" aria-selected={inspector === "flags"} onClick={() => setInspector("flags")}>Cảnh báo <span className="count">{flags.length}</span></button>
              <button role="tab" type="button" aria-selected={inspector === "source"} onClick={() => setInspector("source")}>Nguồn</button>
              {tab === "note" && note && <button role="tab" type="button" aria-selected={inspector === "icd"} onClick={() => setInspector("icd")}>Mã ICD-10</button>}
            </div>
            <div className="inspector-body">
              {inspector === "flags" && <FlagList flags={flags} onRef={show} empty={tab === "note" && !note ? "Cảnh báo của buổi khám hiện sau khi soạn nháp." : "Không có cảnh báo."} />}
              {inspector === "source" && <SourceView key={selected ?? ""} pid={pid} q={q} ref_={selected} turns={turns} transcriptId={note?.draft.transcript_id} onRef={show} />}
              {inspector === "icd" && note && <IcdList items={note.draft.icd_suggestions} picked={pickedIcd} setPicked={setPickedIcd} onRef={show} locked={signed || !canWrite} />}
            </div>
          </aside>
        )}
      </div>

      {signOpen && note && canWrite && <SignDialog draft={note.draft} onCancel={() => setSignOpen(false)} onSign={sign} />}
      {fhir && <FhirDialog json={fhir} pid={pid} onClose={() => setFhir(null)} toast={toast} />}
      {pasteOpen && canWrite && <PasteDialog onClose={() => setPasteOpen(false)} onSubmit={(t) => { setPasteOpen(false); draft({ transcript_text: t }); }} />}
    </div>
  );
}

/* ---------- chip trích nguồn ---------- */

function Cite({ r, onRef, selected }: { r: string; onRef: (r: string) => void; selected: string | null }) {
  return <button type="button" className={`cite ${isTurn(r) ? "turn" : "record"} ${selected === r ? "active" : ""}`} onClick={() => onRef(r)} aria-label={`Mở nguồn ${r}`}>{r}</button>;
}

function LineView({ l, onRef, selected, as: Tag = "li" }: { l: Line; onRef: (r: string) => void; selected: string | null; as?: "li" | "p" }) {
  const cites = l.citations.map((c) => <Cite key={c.ref} r={c.ref} onRef={onRef} selected={selected} />);
  if (l.kind === "missing") {
    const [label, rest] = l.text.includes(":") ? [l.text.slice(0, l.text.indexOf(":")), l.text.slice(l.text.indexOf(":") + 1).trim()] : [l.text, ""];
    return <Tag className="line missing">{label}{rest && <span className="tag warn">{rest.replace(/\.$/, "")}</span>}</Tag>;
  }
  return <Tag className={`line ${l.kind}`}>{l.text} {cites}</Tag>;
}

/* ---------- Module 1: tóm tắt ---------- */

function SummaryDoc({ pid, summary, lastReview, onRef, selected, readOnly, toast, onShowFlags }: {
  pid: string; summary: Summary; lastReview: Review; onRef: (r: string) => void; selected: string | null; readOnly: string | null; toast: (m: string) => void; onShowFlags: () => void;
}) {
  const [review, setReview] = useState<Review>(lastReview);
  const [comment, setComment] = useState("");
  const [showComment, setShowComment] = useState(false);
  const [saving, setSaving] = useState(false);
  const sec = (key: string) => summary.sections.find((s) => s.key === key);
  const C = (r: string) => <Cite r={r} onRef={onRef} selected={selected} />;
  const hasKind = (k: string) => summary.flags.some((f) => f.kind === k);
  const flaggedIngredients = new Set(summary.flags.filter((f) => f.kind === "renal_dose").map((f) => f.title.toLocaleLowerCase("vi")));
  const nRefs = new Set(summary.sections.flatMap((s) => s.lines.flatMap((l) => l.citations.map((c) => c.ref)))).size;

  async function send(decision: "xác nhận" | "cần sửa") {
    setSaving(true);
    try {
      await api(`/patients/${pid}/summary/review`, { body: { decision, comment } });
      setReview({ reviewed_by: "bạn", reviewed_at: new Date().toISOString(), decision, comment });
      toast(decision === "xác nhận" ? "Đã lưu xác nhận kèm bản chụp tóm tắt." : "Đã ghi yêu cầu sửa tóm tắt.");
    } catch (e) { toast(errMsg(e)); } finally { setSaving(false); }
  }

  const plain = ["benh_nen", "dot_nay", "ban_giao"].map(sec).filter((s): s is NonNullable<typeof s> => !!s);
  const allergy = sec("di_ung");
  const missing = sec("chua_ghi_nhan");

  return (
    <article className="doc">
      <header className="doc-head">
        <div>
          <h2>Tóm tắt hồ sơ</h2>
          <p>Tổng hợp từ {nRefs} bản ghi · {summary.mode === "llm" ? "có đoạn tóm tắt nhanh do LLM viết" : "chế độ quy tắc, không dùng LLM"}</p>
        </div>
        {summary.flags.length > 0 && <button type="button" className="flag-pill" onClick={onShowFlags}><AlertTriangle aria-hidden="true" />{summary.flags.length} cảnh báo cần xem</button>}
      </header>

      {summary.narrative.length > 0 && (
        <section className="doc-sec"><h3>Tóm tắt nhanh</h3><ul className="lines">{summary.narrative.map((l, i) => <LineView key={i} l={l} onRef={onRef} selected={selected} />)}</ul></section>
      )}

      {plain.map((s) => (
        <section className="doc-sec" key={s.key}>
          <h3>{stripNo(s.title)}</h3>
          <ul className="lines">{s.lines.map((l, i) => <LineView key={i} l={l} onRef={onRef} selected={selected} />)}</ul>
        </section>
      ))}

      <section className="doc-sec">
        <h3>Thuốc đang dùng <small>theo hoạt chất</small></h3>
        {summary.active_meds.length === 0 ? <p className="line missing">Không có đơn còn hiệu lực trong hồ sơ.</p> : (
          <table className="mini">
            <thead><tr><th>Hoạt chất</th><th>Đơn kê</th><th>Nguồn</th></tr></thead>
            <tbody>
              {summary.active_meds.map((m) => (
                <tr key={m.ingredient}>
                  <td>{m.display}{m.entries.length > 1 && <span className="tag warn">trùng {m.entries.length} đơn</span>}{[...flaggedIngredients].some((t) => t.includes(m.display.toLocaleLowerCase("vi"))) && <span className="tag warn">xem lại theo eGFR</span>}</td>
                  <td>{m.entries.map((e) => <div key={e.ref}>{e.drug_name} · {e.dose.replace(" x ", " × ")}</div>)}</td>
                  <td>{m.entries.map((e) => <div key={e.ref}>{C(e.ref)}</div>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="doc-sec">
        <h3>Xu hướng xét nghiệm <small>lần đầu → mới nhất</small></h3>
        {summary.trends.length === 0 ? <p className="line missing">Chưa có kết quả xét nghiệm.</p> : (
          <table className="mini">
            <thead><tr><th>Chỉ số</th><th>Giá trị</th><th>Thay đổi</th><th>Lần đo mới nhất</th></tr></thead>
            <tbody>
              {summary.trends.map((t) => {
                const first = t.points[0]; const last = t.points[t.points.length - 1];
                const pct = t.points.length > 1 && first.value ? Math.round((Math.abs(last.value - first.value) / first.value) * 100) : null;
                return (
                  <tr key={t.analyte}>
                    <td>{t.display}</td>
                    <td>{t.points.length > 1 && <>{fmtNum(first.value)} → </>}<b className={t.abnormal_latest ? "out" : ""}>{fmtNum(last.value)}</b> {t.unit}{t.abnormal_latest && <span className="tag danger">ngoài ngưỡng</span>}</td>
                    <td className="trend">{t.points.length < 2 ? "1 lần đo" : t.direction === "ổn định" ? "Ổn định" : <>{t.direction === "tăng" ? <ArrowUp aria-hidden="true" /> : <ArrowDown aria-hidden="true" />}{t.direction === "tăng" ? "Tăng" : "Giảm"} {pct}% · {t.points.length} lần đo</>}</td>
                    <td>{C(last.ref)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {allergy && (
        <section className="doc-sec">
          <h3>Dị ứng</h3>
          {hasKind("allergy_conflict") ? (
            <div className="callout warn">
              <AlertTriangle aria-hidden="true" />
              <div>
                <p><strong>Các nguồn ghi không thống nhất.</strong></p>
                <ul className="lines">{allergy.lines.map((l, i) => <LineView key={i} l={l} onRef={onRef} selected={selected} />)}</ul>
                <p className="muted">Hệ thống giữ cả hai, không tự chọn bên đúng.</p>
              </div>
            </div>
          ) : <ul className="lines">{allergy.lines.map((l, i) => <LineView key={i} l={l} onRef={onRef} selected={selected} />)}</ul>}
        </section>
      )}

      {missing && missing.lines.length > 0 && (
        <section className="doc-sec">
          <h3>Chưa ghi nhận</h3>
          <ul className="lines missing">{missing.lines.map((l, i) => <li key={i}>{l.text.replace(/\.$/, "")}</li>)}</ul>
        </section>
      )}

      {summary.dropped.length > 0 && (
        <details className="rejected">
          <summary>{summary.dropped.length} dòng bị loại khi kiểm chứng</summary>
          <ul>{summary.dropped.map((d, i) => <li key={i}><q>{d.text}</q> — {d.reason}</li>)}</ul>
        </details>
      )}

      <footer className="review-bar">
        {readOnly ? (
          <>
            <p className="muted"><Lock aria-hidden="true" />{readOnly}</p>
            <div className="review-actions">
              <button type="button" className="btn" disabled title={readOnly}>Cần sửa</button>
              <button type="button" className="btn primary" disabled title={readOnly}>Xác nhận tóm tắt</button>
            </div>
          </>
        ) : (
          <>
            <div className="review-state">
              {!review && <span>Bác sĩ chưa rà soát tóm tắt này</span>}
              {review && <span className={review.decision === "xác nhận" ? "ok" : "warn"}>{review.decision === "xác nhận" ? <Check aria-hidden="true" /> : <PencilLine aria-hidden="true" />}{review.decision === "xác nhận" ? "Đã xác nhận" : "Đã yêu cầu sửa"} · {review.reviewed_by}, {fmtDate(new Date(new Date(review.reviewed_at).getTime() + 7 * 3600e3).toISOString())}{review.comment && ` · “${review.comment}”`}</span>}
              {showComment && <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} placeholder="Ghi mục cần sửa hoặc cần kiểm tra lại" aria-label="Góp ý" autoFocus />}
            </div>
            <div className="review-actions">
              {!showComment && <button type="button" className="btn ghost" onClick={() => setShowComment(true)}>Thêm góp ý</button>}
              <button type="button" className="btn" disabled={saving} onClick={() => send("cần sửa")}>Cần sửa</button>
              <button type="button" className="btn primary" disabled={saving} onClick={() => send("xác nhận")}>Xác nhận tóm tắt</button>
            </div>
          </>
        )}
      </footer>
    </article>
  );
}

/* ---------- Module 2: bệnh án nháp ---------- */

function NoteDoc({ draft, aiText, text, setText, editing, stats, onRef, selected, approver }: {
  draft: Draft; aiText: string; text: string; setText: (v: string) => void; editing: boolean; stats: EditStats | null; onRef: (r: string) => void; selected: string | null; approver: string;
}) {
  const signed = !!stats;
  const ai = aiText.split("\n");
  const changed = text.split("\n").filter((l, i) => l !== ai[i]).length + Math.max(0, ai.length - text.split("\n").length);
  const diff = stats ? stats.unified.filter((l) => /^[+-]/.test(l) && !/^(\+\+\+|---)/.test(l)) : [];

  return (
    <>
      <header className="doc-head">
        <div>
          <h2>Bệnh án nội khoa</h2>
          <p>Soạn từ {draft.transcript_id} · {draft.normalized_turns.length} lượt nói · {draft.mode === "llm" ? "trích xuất bằng LLM" : "trích xuất bằng quy tắc"}</p>
        </div>
        <span className={`status ${signed ? "ok" : "draft"}`}>{signed ? `Đã ký duyệt · ${approver.replace(/\s*\(.*\)$/, "")}` : "Bản nháp, chưa duyệt"}</span>
      </header>

      {signed && text !== aiText ? (
        <pre className="final-text">{text}</pre>
      ) : editing ? (
        <div className="editor-wrap">
          <textarea className="editor" value={text} onChange={(e) => setText(e.target.value)} aria-label="Nội dung bệnh án" spellCheck={false} />
          <p className="muted small">{changed === 0 ? "Chưa thay đổi so với bản AI." : `${changed} dòng khác bản AI. Thay đổi được lưu khi ký duyệt.`}</p>
        </div>
      ) : (
        <div className="note">
          {text !== aiText && <p className="rec-error info">Bạn đã sửa nội dung trong trình chỉnh sửa. Phần dưới đây là bản AI kèm nguồn; bản đã sửa sẽ được lưu khi ký.</p>}
          {draft.sections.map((s) => (
            <section className="doc-sec" key={s.key}>
              <h3>{s.title.replace(/\s*\((theo lời bác sĩ)\)$/, "")}{/theo lời bác sĩ/.test(s.title) && <small>theo lời bác sĩ</small>}</h3>
              {s.lines.map((l, i) => <LineView key={i} l={l} as="p" onRef={onRef} selected={selected} />)}
            </section>
          ))}
          {draft.dropped.length > 0 && (
            <details className="rejected">
              <summary>{draft.dropped.length} dòng bị loại khi kiểm chứng</summary>
              <ul>{draft.dropped.map((d, i) => <li key={i}><q>{d.text}</q> — {d.reason}</li>)}</ul>
            </details>
          )}
        </div>
      )}

      {stats && (
        <section className="signed">
          <h3>Thay đổi so với bản AI</h3>
          {diff.length === 0 ? <p className="muted">Bác sĩ ký bản nháp không chỉnh sửa.</p> : (
            <div className="diff">{diff.map((l, i) => <p key={i} className={l[0] === "-" ? "del" : "add"}><span>{l[0] === "-" ? "−" : "+"}</span>{l.slice(1).replace(/^- /, "")}</p>)}</div>
          )}
          <div className="keep">
            <div><span>Dòng AI được giữ nguyên</span><strong>{Math.round(stats.ai_lines_kept_ratio * 100)}%</strong></div>
            <div className="bar"><i style={{ width: `${Math.round(stats.ai_lines_kept_ratio * 100)}%` }} /></div>
          </div>
          <table className="mini">
            <thead><tr><th>Mục</th><th className="num">Dòng AI</th><th className="num">Bị sửa / xóa</th><th className="num">BS thêm</th></tr></thead>
            <tbody>{Object.entries(stats.sections).map(([k, v]) => <tr key={k}><td>{k.replace(/\s*\(.*\)$/, "")}</td><td className="num">{v.ai_lines}</td><td className="num">{v.removed}</td><td className="num">{v.added}</td></tr>)}</tbody>
          </table>
        </section>
      )}
    </>
  );
}

/* ---------- Transcript ---------- */

function TranscriptDoc({ pid, q, readOnly, tid, setTid, transcripts, draftTurns, recTurns, setRecTurns, onDraft, drafting, error }: {
  pid: string; q: string; readOnly: boolean; tid: string; setTid: (t: string) => void; transcripts: TranscriptMeta[]; draftTurns: Turn[] | null;
  recTurns: RecTurn[]; setRecTurns: (fn: (t: RecTurn[]) => RecTurn[]) => void; onDraft: () => void; drafting: boolean; error: string;
}) {
  const [modeState, setMode] = useState<"saved" | "record">(transcripts.length || readOnly ? "saved" : "record");
  const mode = readOnly ? "saved" : modeState;  // truy cập khẩn cấp không được ghi âm / tạo transcript
  const [loaded, setLoaded] = useState<{ id: string; turns: Turn[] } | null>(null);

  useEffect(() => {
    if (!tid || draftTurns) return;
    let alive = true;
    api<{ id: string; turns: Turn[] }>(`/patients/${pid}/transcripts/${tid}${q}`).then((t) => { if (alive) setLoaded({ id: t.id, turns: t.turns }); }).catch(() => undefined);
    return () => { alive = false; };
  }, [pid, q, tid, draftTurns]);

  const turns = draftTurns ?? (loaded?.id === tid ? loaded.turns : []);
  const meta = transcripts.find((t) => t.id === tid);

  return (
    <article className="doc">
      <header className="doc-head">
        <div>
          <h2>{mode === "saved" ? (tid || "Transcript") : "Ghi âm buổi khám"}</h2>
          <p>{mode === "saved" ? (meta ? `${meta.turns} lượt nói · ${fmtDate(meta.date)}${draftTurns ? " · đã chuẩn hóa số đọc bằng chữ" : ""}` : "Chưa có transcript") : `${recTurns.length} lượt nói · Việt–Anh · xử lý cục bộ · sửa được trước khi soạn nháp`}</p>
        </div>
        <div className="head-actions">
          {mode === "saved" && transcripts.length > 1 && (
            <label className="select"><span className="sr-only">Chọn transcript</span>
              <select value={tid} onChange={(e) => setTid(e.target.value)}>{transcripts.map((t) => <option key={t.id} value={t.id}>{t.id}</option>)}</select>
            </label>
          )}
          <div className="segmented" role="group" aria-label="Nguồn transcript">
            <button type="button" aria-pressed={mode === "saved"} onClick={() => setMode("saved")}>Bản có sẵn</button>
            <button type="button" aria-pressed={mode === "record"} onClick={() => setMode("record")} disabled={readOnly} title={readOnly ? READ_ONLY : undefined}>Ghi âm mới{recTurns.length > 0 && <span>{recTurns.length}</span>}</button>
          </div>
        </div>
      </header>
      {mode === "record" ? (
        <>
          {error && <p className="rec-error" role="alert">{error}</p>}
          <VoiceRecorder turns={recTurns} setTurns={setRecTurns} onDraft={onDraft} busy={drafting}
            caseId={pid} caseLabel={`Hồ sơ người bệnh ${pid}`}
            context="Buổi khám Nội khoa. Hội thoại có thể xen kẽ tiếng Việt và English. Không suy diễn ngoài lời nói."
            hotwords="SpO2, HbA1c, CRP, eGFR, troponin, metformin, amlodipin, insulin, penicillin" />
        </>
      ) : turns.length === 0 ? (
        <div className="empty tall"><strong>{tid ? "Đang tải transcript…" : "Chưa có transcript"}</strong>{!tid && <span>{readOnly ? "Người bệnh này chưa có transcript nào." : "Chuyển sang “Ghi âm mới” để tạo transcript đầu tiên."}</span>}</div>
      ) : (
        <ol className="turns">
          {turns.map((t) => (
            <li key={t.n}>
              <span className="turn-no">L{t.n}</span>
              <div>
                <span className={`spk ${t.speaker.toLowerCase()}`}>{speakerLabel[t.speaker] ?? t.speaker}</span>
                <p>{t.text}</p>
                {t.norm && t.norm !== t.text && <p className="norm">Chuẩn hóa: {t.norm}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}

/* ---------- Inspector ---------- */

function FlagList({ flags, onRef, empty }: { flags: Flag[]; onRef: (r: string) => void; empty: string }) {
  if (flags.length === 0) return <div className="empty small"><span>{empty}</span></div>;
  return (
    <div className="flags">
      <p className="muted small">Tính bằng quy tắc cố định từ hồ sơ và transcript, không do AI suy luận.</p>
      {flags.map((f) => (
        <article key={f.id} className={`flag ${sevClass[f.severity]}`}>
          <span className="sev">{sevLabel[f.severity]}</span>
          <h4>{f.title.replace(/^Cờ đỏ:\s*/, "")}</h4>
          <p>{f.detail}</p>
          <div className="refs">{f.citations.map((c) => <button type="button" key={c.ref} className={`cite ${isTurn(c.ref) ? "turn" : "record"}`} onClick={() => onRef(c.ref)}>{c.ref}</button>)}</div>
        </article>
      ))}
    </div>
  );
}

const fieldLabel: Record<string, string> = {
  date: "Ngày", source: "Nơi phát sinh", practitioner: "Bác sĩ", type: "Loại bản ghi", status: "Trạng thái", drug_name: "Thuốc", dose: "Liều", encounter: "Thuộc lần khám",
  admitted_at: "Vào viện", ward_at: "Vào khoa", reason: "Lý do", kkb_diagnosis: "Chẩn đoán khoa khám bệnh", modality: "Kỹ thuật", conclusion: "Kết luận", due: "Hạn dự kiến", service: "Dịch vụ", note: "Ghi chú",
  diagnoses: "Chẩn đoán", allergies_recorded: "Dị ứng được ghi", results: "Kết quả", vitals: "Sinh hiệu", text: "Nội dung",
  problems: "Chẩn đoán / vấn đề", comorbidities: "Bệnh nền", medications: "Thuốc đang dùng", labs_imaging: "Xét nghiệm / hình ảnh",
  pending: "Việc cần theo dõi", transcript_id: "Transcript bàn giao",
};
function fmtValue(v: unknown): string {
  if (v === null || v === undefined) return "không ghi";
  if (Array.isArray(v)) return v.length ? v.map(fmtValue).join("; ") : "không có";
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).filter(([, x]) => x !== null).map(([k, x]) => (k === "code" || k === "display" || k === "substance" ? fmtValue(x) : `${k} ${fmtValue(x)}`)).join(", ");
  if (typeof v === "number") return fmtNum(v);
  const s = String(v);
  return /^\d{4}-\d{2}-\d{2}/.test(s) ? fmtDate(s) : s;
}

function SourceView({ pid, q, ref_, turns, transcriptId, onRef }: { pid: string; q: string; ref_: string | null; turns: Turn[]; transcriptId?: string; onRef: (r: string) => void }) {
  const [rec, setRec] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");
  const turn = ref_ && isTurn(ref_) ? Number(ref_.slice(1)) : null;

  useEffect(() => {
    if (!ref_ || turn !== null) return;
    let alive = true;
    api<Record<string, unknown>>(`/patients/${pid}/sources/${encodeURIComponent(ref_)}${q}`).then((r) => { if (alive) setRec(r); }).catch((e) => { if (alive) setErr(errMsg(e)); });
    return () => { alive = false; };
  }, [pid, q, ref_, turn]);

  if (!ref_) return <div className="empty small"><strong>Chưa chọn nguồn</strong><span>Bấm vào một mã nguồn trong văn bản để xem bản ghi gốc.</span></div>;

  if (turn !== null) {
    const idx = turns.findIndex((t) => t.n === turn);
    const ctx = idx < 0 ? [] : turns.slice(Math.max(0, idx - 1), idx + 2);
    return (
      <div className="source">
        <p className="source-kind">Lượt nói trong transcript</p>
        <h4 className="mono">{transcriptId} · L{turn}</h4>
        <ol className="turns compact">
          {ctx.map((t) => (
            <li key={t.n} className={t.n === turn ? "active" : "dim"}>
              <button type="button" className="turn-no" onClick={() => onRef(`L${t.n}`)}>L{t.n}</button>
              <div>
                <span className={`spk ${t.speaker.toLowerCase()}`}>{speakerLabel[t.speaker] ?? t.speaker}</span>
                <p>{t.text}</p>
                {t.norm && t.norm !== t.text && <p className="norm">Chuẩn hóa: {t.norm}</p>}
              </div>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  if (err) return <div className="empty small"><strong>{err}</strong><span className="mono">{ref_}</span></div>;
  if (!rec) return <div className="empty small"><span>Đang tải {ref_}…</span></div>;
  const rows = Object.entries(rec).filter(([k, v]) => !["id", "text", "conclusion"].includes(k) && v !== null && v !== "");
  const body = (rec.text ?? rec.conclusion) as string | undefined;
  return (
    <div className="source">
      <p className="source-kind">Bản ghi gốc</p>
      <h4 className="mono">{String(rec.id)}</h4>
      <dl>{rows.map(([k, v]) => <div key={k}><dt>{fieldLabel[k] ?? k}</dt><dd>{fmtValue(v)}</dd></div>)}</dl>
      {body && <blockquote>{body}</blockquote>}
      <p className="verified"><Check aria-hidden="true" />Lần xem này đã được ghi vào audit log</p>
    </div>
  );
}

function IcdList({ items, picked, setPicked, onRef, locked }: { items: Draft["icd_suggestions"]; picked: string[]; setPicked: (v: string[]) => void; onRef: (r: string) => void; locked: boolean }) {
  const toggle = (c: string) => setPicked(picked.includes(c) ? picked.filter((x) => x !== c) : [...picked, c]);
  if (items.length === 0) return <div className="empty small"><strong>Chưa có gợi ý</strong><span>Bác sĩ chưa nêu chẩn đoán trong buổi khám.</span></div>;
  return (
    <div className="icd">
      <p className="muted small">Gợi ý trong danh mục ICD-10 của bệnh viện. Bác sĩ chọn mã; mã phải nhập thủ công vào EMR.</p>
      {items.map((s) => (
        <label key={s.code} className={`icd-row ${picked.includes(s.code) ? "on" : ""}`}>
          <input type="checkbox" checked={picked.includes(s.code)} onChange={() => toggle(s.code)} disabled={locked} />
          <span>
            <b className="mono">{s.code}</b> {s.display}
            <small>{s.role} · <button type="button" className="link" onClick={(e) => { e.preventDefault(); onRef(s.from); }}>{s.from}</button></small>
          </span>
        </label>
      ))}
      <button type="button" className="btn ghost full" disabled={picked.length === 0} onClick={() => navigator.clipboard?.writeText(picked.join(", "))}><Copy aria-hidden="true" />Sao chép {picked.length || ""} mã đã chọn</button>
    </div>
  );
}

/* ---------- Dialogs ---------- */

function SignDialog({ draft, onCancel, onSign }: { draft: Draft; onCancel: () => void; onSign: () => void }) {
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const red = draft.flags.filter((f) => f.severity === "đỏ");
  const high = draft.flags.filter((f) => f.severity === "cao");
  return (
    <div className="backdrop" role="presentation" onClick={onCancel}>
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="sign-title" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2 id="sign-title">Ký duyệt bệnh án?</h2>
          <button type="button" className="icon-btn" onClick={onCancel} aria-label="Đóng"><X aria-hidden="true" /></button>
        </header>
        <p>Sau khi ký, bệnh án chuyển sang chỉ đọc và không thể ký lại. Hệ thống lưu bản AI, bản cuối và phần thay đổi giữa hai bản.</p>
        {(red.length + high.length + draft.missing.length > 0) && (
          <ul className="checklist">
            {red.length > 0 && <li>{red.length} cờ đỏ: {red.map((f) => f.title.replace(/^Cờ đỏ:\s*/, "")).join("; ")}</li>}
            {high.length > 0 && <li>{high.length} cảnh báo mức cao</li>}
            {draft.missing.length > 0 && <li>{draft.missing.length} mục chưa ghi nhận: {draft.missing.map((m) => m.label.toLocaleLowerCase("vi")).join(", ")}</li>}
          </ul>
        )}
        <label className="check">
          <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
          Tôi đã xem các cờ, mục chưa ghi nhận và nguồn dẫn.
        </label>
        <footer>
          <button type="button" className="btn" onClick={onCancel}>Xem lại</button>
          <button type="button" className="btn primary" disabled={!ack || busy} onClick={() => { setBusy(true); onSign(); }}>Ký duyệt</button>
        </footer>
      </section>
    </div>
  );
}

function FhirDialog({ json, pid, onClose, toast }: { json: string; pid: string; onClose: () => void; toast: (m: string) => void }) {
  return (
    <div className="backdrop" role="presentation" onClick={onClose}>
      <section className="dialog wide" role="dialog" aria-modal="true" aria-labelledby="fhir-title" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2 id="fhir-title">FHIR R4 Bundle</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Đóng"><X aria-hidden="true" /></button>
        </header>
        <p className="muted">Composition (status final) và Provenance ghi AI soạn nháp, bác sĩ duyệt.</p>
        <pre className="code">{json}</pre>
        <footer>
          <button type="button" className="btn" onClick={() => { navigator.clipboard?.writeText(json); toast("Đã sao chép FHIR Bundle."); }}><Copy aria-hidden="true" />Sao chép</button>
          <button type="button" className="btn primary" onClick={() => {
            const url = URL.createObjectURL(new Blob([json], { type: "application/fhir+json" }));
            const a = document.createElement("a"); a.href = url; a.download = `${pid}-composition.json`; a.click(); URL.revokeObjectURL(url);
          }}><Download aria-hidden="true" />Tải JSON</button>
        </footer>
      </section>
    </div>
  );
}

function PasteDialog({ onClose, onSubmit }: { onClose: () => void; onSubmit: (text: string) => void }) {
  const [text, setText] = useState("");
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const bad = lines.findIndex((l) => !/^(BS|BN|NN)\s*:/i.test(l));
  return (
    <div className="backdrop" role="presentation" onClick={onClose}>
      <section className="dialog wide" role="dialog" aria-modal="true" aria-labelledby="paste-title" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2 id="paste-title">Dán transcript mới</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Đóng"><X aria-hidden="true" /></button>
        </header>
        <label className="field">
          <span>Mỗi dòng bắt đầu bằng <span className="mono">BS:</span>, <span className="mono">BN:</span> hoặc <span className="mono">NN:</span></span>
          <textarea rows={9} value={text} onChange={(e) => setText(e.target.value)} placeholder={"BS: Bác thấy trong người thế nào?\nBN: Tôi sốt ba hôm nay rồi…"} autoFocus />
          {lines.length > 0 && <small className={bad === -1 ? "ok" : "err"}>{bad === -1 ? `${lines.length} lượt nói hợp lệ` : `Dòng ${bad + 1} không bắt đầu bằng BS:, BN: hoặc NN:`}</small>}
        </label>
        <footer>
          <button type="button" className="btn" onClick={onClose}>Hủy</button>
          <button type="button" className="btn primary" disabled={lines.length === 0 || bad !== -1} onClick={() => onSubmit(lines.join("\n"))}>Soạn nháp</button>
        </footer>
      </section>
    </div>
  );
}
