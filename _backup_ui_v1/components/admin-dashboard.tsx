"use client";

import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock3,
  Download,
  HeartPulse,
  LoaderCircle,
  LogOut,
  Play,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";

const auditEntries = [
  ["11/11/2026 09:48:22", "bs.an", "doctor", "XUẤT FHIR", "p001", "Composition + Provenance"],
  ["11/11/2026 09:47:51", "bs.an", "doctor", "KÝ DUYỆT BỆNH ÁN", "p001", "Note N-2026-1108"],
  ["11/11/2026 09:45:13", "bs.an", "doctor", "SOẠN NHÁP BỆNH ÁN", "p001", "TS-2026-11-08"],
  ["11/11/2026 09:41:08", "bs.binh", "doctor", "TRUY CẬP KHẨN CẤP", "p021", "Trực đêm, cần kiểm tra thuốc"],
  ["11/11/2026 09:40:52", "bs.binh", "doctor", "TỪ CHỐI XEM TÓM TẮT", "p021", "Không phải bác sĩ điều trị"],
  ["11/11/2026 09:38:19", "bs.an", "doctor", "XEM BẢN GHI GỐC", "p001", "RX-2025-02-20-3"],
  ["11/11/2026 09:36:04", "bs.an", "doctor", "XEM TÓM TẮT", "p001", ""],
  ["11/11/2026 09:31:13", "admin", "admin", "ĐĂNG NHẬP", "—", ""],
];

function Brand() {
  return <Link className="srs-brand" href="/admin" aria-label="Internal Medicine AI Clinical Copilot"><span><HeartPulse aria-hidden="true" /></span><strong>Internal Medicine</strong><b>AI Clinical Copilot</b></Link>;
}

export function AdminDashboard() {
  const [running, setRunning] = useState(false);
  const [toast, setToast] = useState("");

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 3500);
    return () => window.clearTimeout(timer);
  }, [toast]);

  function runEvaluation() {
    setRunning(true);
    window.setTimeout(() => { setRunning(false); setToast("Đã chấm 81 hồ sơ: 0 lỗi, 0 nội dung cấm."); }, 900);
  }

  return <div className="srs-admin-app">
    <header className="srs-header admin"><Brand /><div className="srs-header-context"><span>Khoa Nội chung</span><i>•</i><em><ShieldCheck aria-hidden="true" /> Offline · rule-based</em></div><div className="srs-header-actions"><div className="srs-user"><span>QT</span><div><strong>Quản trị hệ thống</strong><small>Không có quyền xem nội dung lâm sàng</small></div></div><Link className="srs-icon-btn" href="/login" aria-label="Đăng xuất"><LogOut aria-hidden="true" /></Link></div></header>
    <main className="srs-admin-main">
      <Link className="srs-back" href="/"><ArrowLeft aria-hidden="true" />Không gian lâm sàng</Link>
      <div className="srs-page-heading"><div><span className="srs-eyebrow">SC-09 · Quản trị</span><h1>Chất lượng pipeline & audit log</h1><p>Chỉ hiển thị số liệu đánh giá và mã người bệnh, không hiển thị nội dung lâm sàng.</p></div><button className="srs-btn primary" onClick={runEvaluation} disabled={running}>{running ? <LoaderCircle className="spin" aria-hidden="true" /> : <Play aria-hidden="true" />}{running ? "Đang chấm 81 hồ sơ" : "Chạy đánh giá"}</button></div>
      <div className="srs-admin-metrics"><article><span><Activity aria-hidden="true" /></span><div><small>Hồ sơ giả lập</small><strong>81</strong><em>p001–p081</em></div></article><article><span><CheckCircle2 aria-hidden="true" /></span><div><small>Lỗi pipeline</small><strong>0</strong><em>Offline mode</em></div></article><article><span><ShieldAlert aria-hidden="true" /></span><div><small>Nội dung cấm</small><strong>0</strong><em>Không chẩn đoán bịa</em></div></article><article><span><Clock3 aria-hidden="true" /></span><div><small>Thời gian chấm</small><strong>74s</strong><em>Mục tiêu &lt; 2 phút</em></div></article></div>
      <div className="srs-admin-grid">
        <EvaluationCard title="Module 1 · Patient Intelligence" metrics={["Cờ: recall / precision|100% / 100%", "Facts vàng có đúng nguồn|100%", "Câu không có nguồn|0"]} flags={["Dị ứng mâu thuẫn|8/8", "Trùng hoạt chất|20/20", "Tương tác thuốc|12/12", "Hẹn chưa có kết quả|21/21", "Thuốc – chức năng thận|17/17", "Bất thường chưa xử trí|21/21"]} />
        <EvaluationCard title="Module 2 · Clinical Documentation" metrics={["Facts: recall / precision|100% / 100%", "Chưa ghi nhận: recall / precision|100% / 100%", "Cờ: recall / precision|100% / 100%"]} flags={["Dị ứng chéo cùng nhóm|11/11", "Nhắc hỏi dị ứng|32/32", "Sửa lỗi nhận dạng giọng nói|30/30", "Tương tác thuốc|60/60", "Cờ đỏ|44/44", "Sinh hiệu bất thường|33/33"]} />
      </div>
      <p className="srs-eval-note"><AlertTriangle aria-hidden="true" /><span><strong>Giới hạn dữ liệu:</strong> hồ sơ và đáp án vàng do cùng bộ sinh tạo ra. Kết quả cho thấy pipeline chạy ổn định, chưa chứng minh độ chính xác lâm sàng trên ca thật.</span></p>
      <section className="srs-audit-card"><div className="srs-card-title"><div><ShieldCheck aria-hidden="true" /><span><strong>Audit log truy cập dữ liệu người bệnh</strong><small>Ưu tiên theo dõi các lần bị từ chối và truy cập khẩn cấp</small></span></div><button className="srs-btn secondary" onClick={() => setToast("Đã chuẩn bị tệp audit CSV mô phỏng.")}><Download aria-hidden="true" />Xuất CSV</button></div><div className="srs-audit-table"><div className="srs-audit-row head"><span>Thời điểm</span><span>Người dùng</span><span>Vai trò</span><span>Hành động</span><span>BN</span><span>Chi tiết</span></div>{auditEntries.map((entry) => <div className={`srs-audit-row ${entry[3].includes("TỪ CHỐI") ? "denied" : entry[3].includes("KHẨN CẤP") ? "emergency" : ""}`} key={entry.join("-")}><span>{entry[0]}</span><span>{entry[1]}</span><span>{entry[2]}</span><strong>{entry[3]}</strong><span>{entry[4]}</span><span>{entry[5] || "—"}</span></div>)}</div></section>
    </main>
    {toast && <div className="srs-toast" role="status"><CheckCircle2 aria-hidden="true" /><span>{toast}</span><button onClick={() => setToast("")} aria-label="Đóng"><X aria-hidden="true" /></button></div>}
  </div>;
}

function EvaluationCard({ title, metrics, flags }: { title: string; metrics: string[]; flags: string[] }) {
  return <section className="srs-evaluation-card"><div className="srs-card-title"><div><Activity aria-hidden="true" /><span><strong>{title}</strong><small>Đối chiếu tệp đáp án vàng</small></span></div><b>PASS</b></div><div className="srs-eval-metrics">{metrics.map((metric) => { const [label, value] = metric.split("|"); return <div key={label}><span>{label}</span><strong>{value}</strong></div>; })}</div><div className="srs-eval-flags"><div><span>Loại cờ</span><span>Bắt được / đã cài</span></div>{flags.map((flag) => { const [label, value] = flag.split("|"); return <div key={label}><span>{label}</span><strong>{value}</strong></div>; })}</div></section>;
}
