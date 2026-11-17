"use client";

import { AlertTriangle, ArrowRight, Check, History, Mic, RotateCcw, Search, UserCheck, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api, ApiError, fmtDate, useUser,
  type AssignmentHistory, type AssignmentList, type AssignmentRow, type AssignmentStatus, type AssignmentView, type DoctorInfo, type User,
} from "@/lib/api";
import { AppShell } from "./app-shell";
import { HandoffIntake } from "./handoff-intake";

const statusTag: Record<AssignmentStatus, string> = { unassigned: "danger", pending: "warn", accepted: "ok" };
const errMsg = (e: unknown) => (e instanceof Error ? e.message : "Có lỗi xảy ra.");
const when = (iso: string | null) => (iso ? fmtDate(new Date(new Date(iso).getTime() + 7 * 3600e3).toISOString()) : "—");
const shortName = (n: string | null | undefined) => (n ?? "").replace(/\s*\(.*\)$/, "");

export function AdminAssignments() {
  const router = useRouter();
  const user = useUser();
  useEffect(() => {
    if (user === null) router.replace("/login");
    else if (user && user.role !== "admin") router.replace("/");
  }, [user, router]);
  if (!user || user.role !== "admin") return <div className="boot">Đang mở…</div>;
  return <Assignments user={user} />;
}

function Assignments({ user }: { user: User }) {
  const [data, setData] = useState<AssignmentList | null>(null);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [doctor, setDoctor] = useState("");
  const [ward, setWard] = useState("");
  const [status, setStatus] = useState<AssignmentStatus | "">("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [assignFor, setAssignFor] = useState<AssignmentRow[] | null>(null);
  const [historyFor, setHistoryFor] = useState<AssignmentRow | null>(null);
  const [intake, setIntake] = useState(false);
  const [toast, setToast] = useState("");

  const load = useCallback(async () => {
    try { const d = await api<AssignmentList>("/admin/assignments"); setData(d); setError(""); return d; } catch (e) { setError(errMsg(e)); return null; }
  }, []);
  useEffect(() => {
    let alive = true;
    api<AssignmentList>("/admin/assignments").then((d) => { if (alive) setData(d); }).catch((e) => { if (alive) setError(errMsg(e)); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(""), 4000);
    return () => window.clearTimeout(t);
  }, [toast]);

  const rows = useMemo(() => {
    const needle = q.trim().toLocaleLowerCase("vi");
    return (data?.patients ?? []).filter((r) =>
      (!needle || `${r.id} ${r.name} ${r.bed} ${r.reason ?? ""}`.toLocaleLowerCase("vi").includes(needle))
      && (!doctor || (doctor === "none" ? !r.doctor : r.doctor === doctor))
      && (!ward || r.ward === ward) && (!status || r.status === status));
  }, [data, q, doctor, ward, status]);
  const counts = useMemo(() => {
    const c: Record<AssignmentStatus, number> = { unassigned: 0, pending: 0, accepted: 0 };
    (data?.patients ?? []).forEach((r) => { c[r.status] += 1; });
    return c;
  }, [data]);
  const picked = (data?.patients ?? []).filter((r) => selected.has(r.id));
  const allShown = rows.length > 0 && rows.every((r) => selected.has(r.id));

  function toggle(id: string) { setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; }); }
  function toggleAll() { setSelected((s) => { const n = new Set(s); rows.forEach((r) => (allShown ? n.delete(r.id) : n.add(r.id))); return n; }); }

  return (
    <AppShell user={user} active="assignments">
      <div className="page">
        <header className="page-head">
          <div>
            <h1>Phân công bệnh nhân</h1>
            <p>Chỉ hiển thị thông tin cần để phân công. Quản trị không mở được nội dung bệnh án.</p>
          </div>
          <div className="head-actions">
            <button type="button" className="btn" onClick={() => setIntake(true)}><Mic aria-hidden="true" />Tiếp nhận bàn giao</button>
            <button type="button" className="btn primary" disabled={picked.length === 0} onClick={() => setAssignFor(picked)}>
              <UserCheck aria-hidden="true" />Phân công{picked.length > 0 && ` (${picked.length})`}
            </button>
          </div>
        </header>

        {error && <p className="banner danger flat" role="alert"><AlertTriangle aria-hidden="true" /><span>{error}</span></p>}

        <dl className="stats three">
          <div><dt>Chưa phân công</dt><dd>{data ? counts.unassigned : "—"}</dd><span>cần chọn bác sĩ phụ trách</span></div>
          <div><dt>Chờ tiếp nhận</dt><dd>{data ? counts.pending : "—"}</dd><span>bác sĩ chưa bấm “Tiếp nhận hồ sơ”</span></div>
          <div><dt>Đã phân công</dt><dd>{data ? counts.accepted : "—"}</dd><span>{data ? data.doctors.map((d) => `${shortName(d.name)}: ${d.active}`).join(" · ") : ""}</span></div>
        </dl>

        <div className="toolbar wrap">
          <label className="search">
            <Search aria-hidden="true" />
            <span className="sr-only">Tìm</span>
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm mã, họ tên, giường, lý do vào viện" />
          </label>
          <label className="select"><span className="sr-only">Bác sĩ</span>
            <select value={doctor} onChange={(e) => setDoctor(e.target.value)}>
              <option value="">Mọi bác sĩ</option><option value="none">Chưa có bác sĩ</option>
              {data?.doctors.map((d) => <option key={d.username} value={d.username}>{shortName(d.name)}</option>)}
            </select>
          </label>
          <label className="select"><span className="sr-only">Khoa</span>
            <select value={ward} onChange={(e) => setWard(e.target.value)}>
              <option value="">Mọi khoa</option>
              {data?.wards.map((w) => <option key={w} value={w}>{w}</option>)}
            </select>
          </label>
          <label className="select"><span className="sr-only">Trạng thái</span>
            <select value={status} onChange={(e) => setStatus(e.target.value as AssignmentStatus | "")}>
              <option value="">Mọi trạng thái</option>
              {data && (Object.entries(data.statuses) as [AssignmentStatus, string][]).map(([k, l]) => <option key={k} value={k}>{l} ({counts[k]})</option>)}
            </select>
          </label>
          <button type="button" className="btn ghost" onClick={() => { load(); setToast("Đã tải lại danh sách."); }}><RotateCcw aria-hidden="true" />Tải lại</button>
        </div>

        <div className="card flush">
          <table className="mini assign">
            <thead>
              <tr>
                <th className="pick"><input type="checkbox" checked={allShown} onChange={toggleAll} aria-label="Chọn tất cả hồ sơ đang hiển thị" /></th>
                <th>Mã</th><th>Họ tên</th><th>Khoa · buồng · giường</th><th>Lý do nhập viện</th><th>Bác sĩ hiện tại</th><th>Trạng thái</th><th>Phân công gần nhất</th><th><span className="sr-only">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className={selected.has(r.id) ? "on" : ""}>
                  <td className="pick"><input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} aria-label={`Chọn ${r.id}`} /></td>
                  <td className="mono">{r.id}{r.origin === "handoff" && <span className="tag">bàn giao</span>}</td>
                  <td>{r.name}</td>
                  <td>{r.ward}<small className="block muted">{r.bed}</small></td>
                  <td className="cell-reason">{r.reason ?? "—"}</td>
                  <td>{r.doctor ? <>{shortName(r.doctor_name)}<small className="block mono muted">{r.doctor}</small></> : <span className="muted">—</span>}</td>
                  <td><span className={`tag ${statusTag[r.status]}`}>{r.status_label}</span></td>
                  <td className="mono small">{r.assigned_at ? when(r.assigned_at) : r.status === "accepted" ? "theo dữ liệu gốc" : "—"}</td>
                  <td className="row-actions">
                    <button type="button" className="btn ghost sm" onClick={() => setAssignFor([r])}>{r.doctor ? "Chuyển" : "Phân công"}</button>
                    <button type="button" className="icon-btn" onClick={() => setHistoryFor(r)} aria-label={`Lịch sử phân công ${r.id}`} title="Lịch sử phân công"><History aria-hidden="true" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && rows.length === 0 && <div className="empty small"><strong>Không có hồ sơ phù hợp</strong><span>Đổi từ khóa hoặc bộ lọc.</span></div>}
          {!data && !error && <div className="empty small"><span>Đang tải…</span></div>}
        </div>
      </div>

      {assignFor && data && (
        <AssignDialog rows={assignFor} doctors={data.doctors} onClose={() => setAssignFor(null)}
          onDone={async (msg) => { setAssignFor(null); setSelected(new Set()); await load(); setToast(msg); }}
          onStale={async (msg) => { setAssignFor(null); await load(); setError(msg); }} />
      )}
      {historyFor && <HistoryDialog row={historyFor} onClose={() => setHistoryFor(null)} />}
      {intake && (
        <HandoffIntake user={user} onClose={() => setIntake(false)} onCreated={async (r) => {
          setIntake(false);
          const d = await load();
          const row = d?.patients.find((p) => p.id === r.patient_id);
          setToast(`Đã tạo hồ sơ ${r.patient_id} (Chưa phân công). Chọn bác sĩ phụ trách.`);
          if (row) { setSelected(new Set([row.id])); setAssignFor([row]); }
        }} />
      )}
      {toast && <div className="toast" role="status"><Check aria-hidden="true" /><span>{toast}</span><button type="button" onClick={() => setToast("")} aria-label="Đóng"><X aria-hidden="true" /></button></div>}
    </AppShell>
  );
}

function AssignDialog({ rows, doctors, onClose, onDone, onStale }: {
  rows: AssignmentRow[]; doctors: DoctorInfo[]; onClose: () => void; onDone: (msg: string) => void; onStale: (msg: string) => void;
}) {
  const [doctor, setDoctor] = useState("");
  const [note, setNote] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const target = doctors.find((d) => d.username === doctor);
  const fresh = rows.filter((r) => !r.doctor);
  const moves = rows.filter((r) => r.doctor && r.doctor !== doctor);
  const same = rows.filter((r) => r.doctor && r.doctor === doctor);
  const needReason = moves.length > 0;
  const reasonOk = !needReason || note.trim().length >= 5;
  const valid = !!target && reasonOk && fresh.length + moves.length > 0;

  async function save() {
    setBusy(true); setError("");
    try {
      if (rows.length === 1) {
        const r = rows[0];
        if (r.doctor) await api(`/admin/assignments/${r.id}/transfer`, { body: { doctor, reason: note.trim(), expected_version: r.version } });
        else await api("/admin/assignments", { body: { patient_id: r.id, doctor, note: note.trim(), expected_version: r.version } });
      } else {
        await api("/admin/assignments/bulk", { body: { items: rows.map((r) => ({ patient_id: r.id, expected_version: r.version })), doctor, note: note.trim() } });
      }
      onDone(`Đã giao ${fresh.length + moves.length} hồ sơ cho ${shortName(target?.name)}. Hồ sơ ở trạng thái “Chờ tiếp nhận”.`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) onStale(`${e.message} Danh sách đã được tải lại.`);
      else { setError(errMsg(e)); setConfirming(false); }
    } finally { setBusy(false); }
  }

  return (
    <div className="backdrop" role="presentation" onClick={onClose}>
      <section className="dialog wide" role="dialog" aria-modal="true" aria-labelledby="as-title" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2 id="as-title">{confirming ? "Xác nhận phân công" : rows.length === 1 && rows[0].doctor ? `Chuyển hồ sơ ${rows[0].id}` : `Phân công ${rows.length} hồ sơ`}</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Đóng"><X aria-hidden="true" /></button>
        </header>
        {error && <p className="rec-error flat" role="alert">{error}</p>}

        {!confirming ? (
          <>
            <ul className="as-picked">
              {rows.map((r) => (
                <li key={r.id}><span className="mono">{r.id}</span> {r.name} <small className="muted">· {r.bed}</small>
                  <span className="grow" />{r.doctor ? <span className="muted small">hiện tại: {r.doctor}</span> : <span className="tag danger">Chưa phân công</span>}</li>
              ))}
            </ul>
            <fieldset className="as-doctors">
              <legend>Bác sĩ nhận hồ sơ</legend>
              {doctors.map((d) => (
                <label key={d.username} className={`as-doc ${doctor === d.username ? "on" : ""}`}>
                  <input type="radio" name="doctor" value={d.username} checked={doctor === d.username} onChange={() => setDoctor(d.username)} />
                  <span><strong>{shortName(d.name)}</strong><small className="mono">{d.username}</small></span>
                  <span className="as-load"><b>{d.active}</b> đang phụ trách{d.pending > 0 && <small> · {d.pending} chờ tiếp nhận</small>}</span>
                </label>
              ))}
            </fieldset>
            <label className="field">
              <span>{needReason ? "Lý do chuyển hồ sơ (bắt buộc)" : "Ghi chú bàn giao (không bắt buộc)"}</span>
              <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500}
                placeholder={needReason ? "Ví dụ: BS An nghỉ phép, chuyển cho BS Bình theo dõi" : "Ví dụ: Bệnh nhân mới từ cấp cứu, cần khám trong 1 giờ"} />
              {needReason && <small className={reasonOk ? "ok" : "err"}>{reasonOk ? "Đủ" : `${moves.length} hồ sơ đang có bác sĩ khác phụ trách: cần lý do (ít nhất 5 ký tự)`}</small>}
            </label>
            {same.length > 0 && target && <p className="muted small">{same.length} hồ sơ đã do {shortName(target.name)} phụ trách sẽ giữ nguyên.</p>}
            <footer>
              <button type="button" className="btn" onClick={onClose}>Hủy</button>
              <button type="button" className="btn primary" disabled={!valid} onClick={() => setConfirming(true)}>Tiếp tục<ArrowRight aria-hidden="true" /></button>
            </footer>
          </>
        ) : (
          <>
            <ul className="checklist">
              <li>Bác sĩ nhận: <strong>{shortName(target?.name)}</strong> ({doctor}) · sau khi giao sẽ phụ trách {(target?.active ?? 0) + fresh.length + moves.length} người bệnh</li>
              {fresh.length > 0 && <li>{fresh.length} hồ sơ phân công mới: {fresh.map((r) => r.id).join(", ")}</li>}
              {moves.length > 0 && <li>{moves.length} hồ sơ chuyển từ bác sĩ khác: {moves.map((r) => `${r.id} (${r.doctor})`).join(", ")}. Bác sĩ cũ mất quyền ghi ngay, chỉ còn truy cập khẩn cấp.</li>}
              {note.trim() && <li>{needReason ? "Lý do" : "Ghi chú"}: “{note.trim()}”</li>}
              <li>Hồ sơ ở trạng thái “Chờ tiếp nhận” cho đến khi bác sĩ bấm “Tiếp nhận hồ sơ”.</li>
            </ul>
            <footer>
              <button type="button" className="btn" onClick={() => setConfirming(false)} disabled={busy}>Quay lại</button>
              <button type="button" className="btn primary" onClick={save} disabled={busy}><Check aria-hidden="true" />{busy ? "Đang lưu…" : "Xác nhận phân công"}</button>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}

function HistoryDialog({ row, onClose }: { row: AssignmentRow; onClose: () => void }) {
  const [data, setData] = useState<{ current: AssignmentView; history: AssignmentHistory[] } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    api<{ current: AssignmentView; history: AssignmentHistory[] }>(`/admin/assignments/${row.id}/history`)
      .then((d) => { if (alive) setData(d); }).catch((e) => { if (alive) setError(errMsg(e)); });
    return () => { alive = false; };
  }, [row.id]);
  return (
    <div className="backdrop" role="presentation" onClick={onClose}>
      <section className="dialog wide" role="dialog" aria-modal="true" aria-labelledby="hi-title" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2 id="hi-title">Lịch sử phân công · <span className="mono">{row.id}</span></h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Đóng"><X aria-hidden="true" /></button>
        </header>
        {error && <p className="rec-error flat">{error}</p>}
        {data && (
          <>
            <p className="muted">Hiện tại: <strong>{data.current.doctor ?? "chưa có bác sĩ"}</strong> · {data.current.status_label}
              {data.current.accepted_at && ` · tiếp nhận ${when(data.current.accepted_at)} bởi ${data.current.accepted_by}`} · phiên bản {data.current.version}</p>
            {data.history.length === 0 ? <div className="empty small"><span>Chưa có thay đổi. Bác sĩ phụ trách lấy theo dữ liệu gốc.</span></div> : (
              <ol className="timeline">
                {data.history.map((h) => (
                  <li key={h.id}>
                    <span className="mono small">{when(h.ts)}</span>
                    <div>
                      <strong>{h.action_label}</strong>
                      {h.action !== "accept" && <> · {h.from_doctor ?? "chưa có"} → {h.to_doctor ?? "chưa có"}</>}
                      <small className="block muted">bởi {h.by_user} ({h.by_role === "admin" ? "quản trị" : "bác sĩ"}) · phiên bản {h.version}{h.reason ? ` · “${h.reason}”` : ""}</small>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </>
        )}
        <footer><button type="button" className="btn" onClick={onClose}>Đóng</button></footer>
      </section>
    </div>
  );
}
