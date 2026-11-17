"use client";

import { AlertTriangle, Check, Play, RotateCcw, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, useUser, type AuditEntry, type EvalReport, type User } from "@/lib/api";
import { AppShell } from "./app-shell";

const kindLabel: Record<string, string> = {
  allergy_conflict: "Dị ứng mâu thuẫn", duplicate_ingredient: "Trùng hoạt chất", interaction: "Tương tác thuốc", missing_result: "Hẹn chưa có kết quả",
  renal_dose: "Thuốc – chức năng thận", unresolved_abnormal: "Bất thường chưa xử trí", allergy_cross: "Dị ứng chéo cùng nhóm", allergy_reminder: "Nhắc hỏi dị ứng",
  asr_normalized: "Sửa lỗi nhận dạng giọng nói", red_flag: "Cờ đỏ", vital_abnormal: "Sinh hiệu bất thường",
};
const pct = (n: number) => `${Math.round(n * 1000) / 10}%`;
const localTime = (iso: string) => new Date(iso).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit", day: "2-digit", month: "2-digit" });
const kindOf = (a: AuditEntry) => (a.action.startsWith("TỪ CHỐI") ? "denied" : a.action.includes("KHẨN CẤP") ? "emergency" : "normal");

export function AdminDashboard() {
  const router = useRouter();
  const user = useUser();
  useEffect(() => {
    if (user === null) router.replace("/login");
    else if (user && user.role !== "admin") router.replace("/");
  }, [user, router]);
  if (!user || user.role !== "admin") return <div className="boot">Đang mở…</div>;
  return <Admin user={user} />;
}

function Admin({ user }: { user: User }) {
  const [audit, setAudit] = useState<AuditEntry[] | null>(null);
  const [report, setReport] = useState<EvalReport | null>(null);
  const [seconds, setSeconds] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [filter, setFilter] = useState<"all" | "watch">("all");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");

  const loadAudit = useCallback(() => api<AuditEntry[]>("/admin/audit").then(setAudit).catch((e) => setError(e instanceof Error ? e.message : "Lỗi")), []);
  useEffect(() => { loadAudit(); }, [loadAudit]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(""), 3500);
    return () => window.clearTimeout(t);
  }, [toast]);

  async function run() {
    setRunning(true); setError("");
    const t0 = performance.now();
    try {
      const r = await api<EvalReport>("/admin/eval");
      setReport(r); setSeconds(Math.round((performance.now() - t0) / 100) / 10);
      setToast(`Đã chấm ${r.n_records} hồ sơ: ${r.errors.length} lỗi, ${r.forbidden_found} nội dung cấm.`);
    } catch (e) { setError(e instanceof Error ? e.message : "Lỗi"); } finally { setRunning(false); }
  }

  const rows = (audit ?? []).filter((a) => filter === "all" || kindOf(a) !== "normal");
  const watch = (audit ?? []).filter((a) => kindOf(a) !== "normal").length;
  const v = (x: number | string | undefined) => (report ? x : "—");

  return (
    <AppShell user={user} active="admin">
      <div className="page">
        <header className="page-head">
          <div>
            <h1>Chất lượng & audit</h1>
            <p>Chỉ có số liệu chấm và mã người bệnh. Không hiển thị nội dung lâm sàng.</p>
          </div>
          <button type="button" className="btn primary" onClick={run} disabled={running}><Play aria-hidden="true" />{running ? "Đang chấm…" : "Chạy đánh giá"}</button>
        </header>

        {error && <p className="banner danger flat"><AlertTriangle aria-hidden="true" /><span>{error}</span></p>}

        <dl className="stats">
          <div><dt>Hồ sơ giả lập</dt><dd>{v(report?.n_records)}</dd><span>{report ? `chế độ ${report.mode}` : "chưa chạy đánh giá"}</span></div>
          <div><dt>Lỗi khi chạy</dt><dd>{v(report?.errors.length)}</dd><span>hồ sơ không xử lý được</span></div>
          <div><dt>Nội dung cấm</dt><dd>{v(report?.forbidden_found)}</dd><span>chẩn đoán bác sĩ chưa nói</span></div>
          <div><dt>Dòng bị loại</dt><dd>{v(report?.dropped_by_verifier)}</dd><span>không nguồn hoặc sai số</span></div>
          <div><dt>Thời gian chấm</dt><dd>{seconds === null ? "—" : `${String(seconds).replace(".", ",")}s`}</dd><span>{report ? `${report.failures.length} hồ sơ sai đáp án` : "bấm “Chạy đánh giá”"}</span></div>
        </dl>

        <p className="banner warn"><AlertTriangle aria-hidden="true" /><span><strong>Đọc kết quả thận trọng.</strong> Hồ sơ và đáp án vàng do cùng một bộ sinh tạo ra, nên điểm cao chỉ cho thấy pipeline chạy ổn định, chưa chứng minh độ chính xác trên ca thật.</span></p>

        {report && (
          <div className="eval-grid">
            <EvalTable title="Module 1 · Tóm tắt hồ sơ" counts={report.module1.flag_recall_by_kind}
              summary={[["Cờ: recall / precision", `${pct(report.module1.flag_recall)} / ${pct(report.module1.flag_precision)}`], ["Fact đúng nguồn", pct(report.module1.fact_recall)], ["Câu không có nguồn", String(report.module1.uncited_lines)]]} />
            <EvalTable title="Module 2 · Soạn nháp bệnh án" counts={report.module2.flag_recall_by_kind}
              summary={[["Fact: recall / precision", `${pct(report.module2.fact_recall)} / ${pct(report.module2.fact_precision)}`], ["“Chưa ghi nhận”: recall / precision", `${pct(report.module2.missing_recall)} / ${pct(report.module2.missing_precision)}`], ["Cờ: recall / precision", `${pct(report.module2.flag_recall)} / ${pct(report.module2.flag_precision)}`]]} />
          </div>
        )}

        <section className="card">
          <header className="card-head">
            <div>
              <h2>Audit log</h2>
              <p>{audit ? `${audit.length} bản ghi gần nhất · giờ máy của bạn` : "Đang tải…"}</p>
            </div>
            <div className="segmented" role="group" aria-label="Lọc audit">
              <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>Tất cả <span>{audit?.length ?? 0}</span></button>
              <button type="button" aria-pressed={filter === "watch"} onClick={() => setFilter("watch")}>Từ chối & khẩn cấp <span>{watch}</span></button>
            </div>
            <button type="button" className="btn" onClick={loadAudit}><RotateCcw aria-hidden="true" />Tải lại</button>
          </header>
          <table className="mini audit">
            <thead><tr><th>Thời điểm</th><th>Người dùng</th><th>Hành động</th><th>Người bệnh</th><th>Chi tiết</th></tr></thead>
            <tbody>
              {rows.map((a) => {
                const k = kindOf(a);
                const action = a.action.charAt(0) + a.action.slice(1).toLocaleLowerCase("vi");
                return (
                  <tr key={a.id} className={k}>
                    <td className="mono">{localTime(a.ts)}</td>
                    <td className="mono">{a.username}</td>
                    <td>{k === "normal" ? action : <span className={`tag ${k === "denied" ? "danger" : "warn"}`}>{action}</span>}</td>
                    <td className="mono">{a.patient_id || "—"}</td>
                    <td>{a.detail || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {audit && rows.length === 0 && <div className="empty small"><span>Chưa có bản ghi nào.</span></div>}
        </section>
      </div>
      {toast && <div className="toast" role="status"><Check aria-hidden="true" /><span>{toast}</span><button type="button" onClick={() => setToast("")} aria-label="Đóng"><X aria-hidden="true" /></button></div>}
    </AppShell>
  );
}

function EvalTable({ title, summary, counts }: { title: string; summary: string[][]; counts: Record<string, { found: number; total: number }> }) {
  return (
    <section className="card">
      <header className="card-head"><div><h2>{title}</h2><p>So với tệp đáp án vàng của từng hồ sơ</p></div></header>
      <dl className="kv">{summary.map(([k, val]) => <div key={k}><dt>{k}</dt><dd>{val}</dd></div>)}</dl>
      <table className="mini">
        <thead><tr><th>Loại cờ</th><th className="num">Bắt được</th><th className="num">Đã cài</th></tr></thead>
        <tbody>{Object.entries(counts).map(([k, c]) => <tr key={k}><td>{kindLabel[k] ?? k}</td><td className="num">{c.found}</td><td className="num">{c.total}</td></tr>)}</tbody>
      </table>
    </section>
  );
}
