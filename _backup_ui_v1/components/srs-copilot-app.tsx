"use client";

import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bell,
  BookOpenCheck,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  ClipboardCheck,
  Copy,
  Download,
  ExternalLink,
  FileCheck2,
  FileText,
  HeartPulse,
  History,
  Info,
  ListFilter,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Menu,
  PencilLine,
  Pill,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  UserRound,
  UsersRound,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Patient = {
  id: string;
  name: string;
  gender: "Nam" | "Nữ";
  birthYear: number;
  room: string;
  bed: string;
  reason: string;
  mine: boolean;
};

type SourceKey = "admission" | "medication" | "lab" | "external" | "encounter";
type ModuleTab = "summary" | "documentation";
type Severity = "red" | "high" | "medium" | "info";

const patients: Patient[] = [
  { id: "p001", name: "Trần Văn Bình", gender: "Nam", birthYear: 1958, room: "Buồng 3", bed: "Giường 12", reason: "Sốt, ho đờm, khó thở. Vào ngày thứ 3 của bệnh.", mine: true },
  { id: "p003", name: "Bùi Minh Long", gender: "Nam", birthYear: 1944, room: "Buồng 8", bed: "Giường 2", reason: "Khó thở tăng, ho khạc đờm nhiều. Vào ngày thứ 4.", mine: true },
  { id: "p005", name: "Dương Minh Tuấn", gender: "Nam", birthYear: 1974, room: "Buồng 3", bed: "Giường 29", reason: "Khó thở tăng, ho khạc đờm nhiều. Vào ngày thứ 2.", mine: true },
  { id: "p006", name: "Bùi Đức Quân", gender: "Nam", birthYear: 1940, room: "Buồng 3", bed: "Giường 6", reason: "Khó thở tăng, ho khạc đờm nhiều. Vào ngày thứ 4.", mine: true },
  { id: "p009", name: "Dương Thị Loan", gender: "Nữ", birthYear: 1958, room: "Buồng 5", bed: "Giường 10", reason: "Khó thở khi nằm, phù hai chân. Vào ngày thứ 4.", mine: true },
  { id: "p012", name: "Nguyễn Quang Sơn", gender: "Nam", birthYear: 1943, room: "Buồng 1", bed: "Giường 16", reason: "Sốt rét run, tiểu buốt. Vào ngày thứ 3.", mine: true },
  { id: "p021", name: "Hoàng Đức Hải", gender: "Nam", birthYear: 1971, room: "Buồng 4", bed: "Giường 22", reason: "Sốt, ho đờm, khó thở. Vào ngày thứ 4.", mine: false },
  { id: "p024", name: "Ngô Thanh Hằng", gender: "Nữ", birthYear: 1941, room: "Buồng 2", bed: "Giường 26", reason: "Khó thở tăng, ho khạc đờm nhiều. Vào ngày thứ 4.", mine: false },
  { id: "p031", name: "Bùi Đức Quân", gender: "Nam", birthYear: 1956, room: "Buồng 3", bed: "Giường 4", reason: "Khó thở khi nằm, phù hai chân. Vào ngày thứ 3.", mine: false },
];

const sources: Record<SourceKey, { id: string; type: string; date: string; origin: string; content: string }> = {
  admission: { id: "BA-2026-11-08", type: "Admission", date: "08/11/2026", origin: "Khoa Nội chung", content: "Vào viện vì sốt, ho đờm, khó thở. Mạch 104 lần/phút, nhiệt độ 38,6°C, HA 128/76 mmHg, nhịp thở 26 lần/phút, SpO₂ 91%." },
  medication: { id: "RX-2025-02-20-3", type: "MedicationRequest", date: "20/02/2025", origin: "Vinmec Times City", content: "Amlodipin 5 mg, 1 viên mỗi ngày. Trạng thái: active. Người kê: BS. Phạm Minh." },
  lab: { id: "XN-2026-11-08", type: "Observation", date: "08/11/2026", origin: "Khoa Xét nghiệm", content: "Kali 5,4 mmol/L; eGFR 38 mL/phút/1,73m²; bạch cầu 15,2 G/L; CRP 96 mg/L." },
  external: { id: "NGOAI-2025-06-03", type: "DocumentReference", date: "03/06/2025", origin: "Bệnh viện đa khoa tỉnh", content: "Giấy ra viện ghi nhận dị ứng Aspirin với biểu hiện nổi mẩn. Thông tin này mâu thuẫn với lần khám ngày 05/12/2025 ghi không dị ứng." },
  encounter: { id: "KB-2025-02-20", type: "Encounter", date: "20/02/2025", origin: "Vinmec Times City", content: "Chẩn đoán: rung nhĩ I48, tăng huyết áp I10. Đơn đang dùng gồm Apixaban, Bisoprolol và Losartan." },
};

const transcript = [
  { n: 1, speaker: "BS", text: "Chào bác, bác thấy trong người thế nào?" },
  { n: 2, speaker: "BN", text: "Mệt lắm bác sĩ ạ. Sốt ba hôm nay rồi, ho nhiều, đờm màu vàng." },
  { n: 3, speaker: "BS", text: "Khó thở từ bao giờ ạ?" },
  { n: 4, speaker: "BN", text: "Từ hôm qua, đi vào nhà vệ sinh cũng thở hổn hển." },
  { n: 5, speaker: "BS", text: "Có đau ngực không bác?" },
  { n: 6, speaker: "BN", text: "Đau bên phải, ho mạnh thì đau hơn." },
  { n: 7, speaker: "BS", text: "Ở nhà bác đã uống thuốc gì chưa?" },
  { n: 8, speaker: "BN", text: "Tôi uống ibuprofen ấy, ngày hai ba viên. Thuốc huyết áp vẫn uống đều." },
  { n: 9, speaker: "NN", text: "Mấy hôm nay bố cháu hay lú lẫn, tối qua còn nói lảm nhảm." },
  { n: 10, speaker: "BS", text: "Bác ăn uống được không, đi tiểu bình thường không?" },
  { n: 11, speaker: "BN", text: "Ăn kém lắm. Tiểu ít hơn mọi khi. Hôm kia đi ngoài phân hơi đen." },
  { n: 12, speaker: "BS", text: "Phổi phải có ran nổ vùng đáy, phổi trái thông khí được. Tim loạn nhịp hoàn toàn." },
  { n: 13, speaker: "BS", text: "SpO2 đang chín mươi mốt, huyết áp một trăm hai mươi tám trên bảy mươi sáu." },
  { n: 14, speaker: "BS", text: "X-quang có đám mờ đáy phổi phải, bạch cầu 15,2, CRP 96." },
  { n: 15, speaker: "BS", text: "Chẩn đoán phù hợp viêm phổi cộng đồng phổi phải. Cho Augmentin và Clarithromycin." },
  { n: 16, speaker: "BS", text: "Cho thở oxy kính 2 lít và theo dõi sát SpO2." },
];

const flags: { severity: Severity; title: string; body: string; evidence: string }[] = [
  { severity: "red", title: "Cờ đỏ: lú lẫn hoặc thay đổi ý thức mới", body: "Người nhà mô tả người bệnh hay lú lẫn và nói lảm nhảm. Bác sĩ cần đánh giá ngay.", evidence: "L9" },
  { severity: "red", title: "Dấu hiệu nghi chảy máu tiêu hóa", body: "Người bệnh nói có một lần đi ngoài phân hơi đen.", evidence: "L11" },
  { severity: "high", title: "Sinh hiệu ngoài ngưỡng cảnh báo", body: "SpO₂ 91% và nhịp thở 26 lần/phút vượt ngưỡng BR-23.", evidence: "BA-2026-11-08" },
  { severity: "high", title: "Tương tác Apixaban + Ibuprofen", body: "Tăng nguy cơ chảy máu khi dùng thuốc chống đông cùng NSAID.", evidence: "L8" },
  { severity: "high", title: "Buổi khám chưa hỏi dị ứng", body: "Hồ sơ có dị ứng Aspirin nhưng transcript chưa ghi nhận câu hỏi dị ứng.", evidence: "NGOAI-2025-06-03" },
  { severity: "medium", title: "NSAID và chức năng thận", body: "Ibuprofen mới nhắc trong khi eGFR gần nhất là 38 mL/phút/1,73m².", evidence: "XN-2026-11-08" },
];

const noteDraft = `I. Lý do vào viện\nSốt, ho đờm, khó thở. Vào ngày thứ 3 của bệnh. [BA-2026-11-08]\n\nII.1. Quá trình bệnh lý\nSốt 3 hôm, ho nhiều, đờm vàng. [L2]\nKhó thở từ hôm qua, gắng sức nhẹ cũng khó thở. [L3, L4]\nĐau ngực phải tăng khi ho. [L5, L6]\nNgười nhà kể người bệnh lú lẫn, nói lảm nhảm. [L9]\nĂn kém, tiểu ít, có một lần đi ngoài phân đen. [L11]\n\nII.2. Tiền sử bản thân\nĐái tháo đường típ 2, rung nhĩ và tăng huyết áp. [KB-2025-02-20]\nDị ứng: Chưa ghi nhận trong buổi khám.\nThuốc lá / rượu bia: Chưa ghi nhận.\n\nIII.1. Toàn thân và dấu hiệu sinh tồn\nMạch 104 lần/phút, nhiệt độ 38,6°C, HA 128/76 mmHg, nhịp thở 26 lần/phút, SpO₂ 91%. [BA-2026-11-08]\nCân nặng: Chưa ghi nhận.\n\nIII.2. Khám các cơ quan\nPhổi phải có ran nổ vùng đáy; tim loạn nhịp hoàn toàn. [L12]\n\nIII.3. Cận lâm sàng\nX-quang có đám mờ đáy phổi phải, bạch cầu 15,2 G/L, CRP 96 mg/L. [L14]\n\nIV. Chẩn đoán theo lời bác sĩ\nViêm phổi cộng đồng phổi phải. Gợi ý ICD-10 J18.9 — bác sĩ chọn mã. [L15]\n\nVI. Hướng điều trị theo lời bác sĩ\nThở oxy kính 2 lít, Augmentin và Clarithromycin; theo dõi sát SpO₂. [L15, L16]`;

function Citation({ source, onOpen }: { source: SourceKey; onOpen: (source: SourceKey) => void }) {
  return <button className="srs-citation" onClick={() => onOpen(source)} aria-label={`Mở nguồn ${sources[source].id}`}><FileText aria-hidden="true" />{sources[source].id}</button>;
}

function Brand() {
  return <Link className="srs-brand" href="/" aria-label="Internal Medicine AI Clinical Copilot"><span><HeartPulse aria-hidden="true" /></span><strong>Internal Medicine</strong><b>AI Clinical Copilot</b></Link>;
}

function GlobalHeader({ onMenu }: { onMenu: () => void }) {
  return <header className="srs-header">
    <button className="srs-icon-btn srs-menu-btn" onClick={onMenu} aria-label="Mở điều hướng"><Menu aria-hidden="true" /></button>
    <Brand />
    <div className="srs-header-context"><span>Khoa Nội chung</span><i>•</i><span>Dữ liệu giả lập</span><em><ShieldCheck aria-hidden="true" /> Offline · rule-based</em></div>
    <div className="srs-header-actions"><button className="srs-icon-btn" aria-label="Thông báo"><Bell aria-hidden="true" /><i /></button><div className="srs-user"><span>NA</span><div><strong>BS. Nguyễn An</strong><small>Bác sĩ điều trị</small></div><ChevronDown aria-hidden="true" /></div><Link className="srs-icon-btn" href="/login" aria-label="Đăng xuất"><LogOut aria-hidden="true" /></Link></div>
  </header>;
}

function Disclaimer({ emergency = false }: { emergency?: boolean }) {
  return <div className={`srs-disclaimer ${emergency ? "emergency" : ""}`} role="note">{emergency ? <ShieldAlert aria-hidden="true" /> : <Info aria-hidden="true" />}<p><strong>{emergency ? "Đang xem ở chế độ truy cập khẩn cấp." : "Công cụ hỗ trợ tham khảo."}</strong> {emergency ? "Quyền truy cập chỉ để xem và đã được ghi vào audit log." : "AI không chẩn đoán, không chỉ định điều trị. Bác sĩ kiểm tra nguồn và chịu trách nhiệm quyết định lâm sàng."}</p></div>;
}

export function SrsCopilotApp() {
  const [screen, setScreen] = useState<"list" | "record">("list");
  const [activeModule, setActiveModule] = useState<ModuleTab>("summary");
  const [selectedPatient, setSelectedPatient] = useState<Patient>(patients[0]);
  const [search, setSearch] = useState("");
  const [mineOnly, setMineOnly] = useState(true);
  const [sourceKey, setSourceKey] = useState<SourceKey>("medication");
  const [sourceOpen, setSourceOpen] = useState(true);
  const [breakGlassPatient, setBreakGlassPatient] = useState<Patient | null>(null);
  const [breakGlassReason, setBreakGlassReason] = useState("");
  const [emergencyAccess, setEmergencyAccess] = useState(false);
  const [reviewDecision, setReviewDecision] = useState<"confirmed" | "needs-fix" | null>(null);
  const [toast, setToast] = useState("");
  const [mobileNav, setMobileNav] = useState(false);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 3600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const filteredPatients = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("vi");
    return patients.filter((patient) => {
      if (mineOnly && !patient.mine) return false;
      if (!needle) return true;
      return [patient.id, patient.name, patient.room, patient.bed, patient.reason].some((value) => value.toLocaleLowerCase("vi").includes(needle));
    });
  }, [search, mineOnly]);

  function openPatient(patient: Patient) {
    if (!patient.mine) {
      setBreakGlassPatient(patient);
      setBreakGlassReason("");
      return;
    }
    setSelectedPatient(patient);
    setEmergencyAccess(false);
    setScreen("record");
    setActiveModule("summary");
  }

  function grantEmergencyAccess() {
    if (!breakGlassPatient || breakGlassReason.trim().length < 10) return;
    setSelectedPatient(breakGlassPatient);
    setEmergencyAccess(true);
    setBreakGlassPatient(null);
    setScreen("record");
    setActiveModule("summary");
    setToast("Truy cập khẩn cấp đã được ghi vào audit log.");
  }

  function openSource(key: SourceKey) {
    setSourceKey(key);
    setSourceOpen(true);
  }

  return <div className="srs-app">
    <a className="skip-link" href="#srs-main">Chuyển đến nội dung chính</a>
    <GlobalHeader onMenu={() => setMobileNav((value) => !value)} />
    <aside className={`srs-sidebar ${mobileNav ? "open" : ""}`}>
      <nav aria-label="Điều hướng chính">
        <span className="srs-nav-label">Không gian lâm sàng</span>
        <button className={screen === "list" ? "active" : ""} onClick={() => { setScreen("list"); setMobileNav(false); }}><UsersRound aria-hidden="true" /><span>Danh sách người bệnh</span><small>81</small></button>
        <button className={screen === "record" && activeModule === "summary" ? "active" : ""} onClick={() => { setScreen("record"); setActiveModule("summary"); setMobileNav(false); }}><BookOpenCheck aria-hidden="true" /><span>Patient Intelligence</span></button>
        <button className={screen === "record" && activeModule === "documentation" ? "active" : ""} onClick={() => { setScreen("record"); setActiveModule("documentation"); setMobileNav(false); }}><Stethoscope aria-hidden="true" /><span>Clinical Documentation</span></button>
        <span className="srs-nav-label">Hệ thống</span>
        <Link href="/admin"><Activity aria-hidden="true" /><span>Quản trị & audit</span></Link>
      </nav>
      <div className="srs-sidebar-scope"><ShieldCheck aria-hidden="true" /><div><strong>Phạm vi v1.0</strong><span>2 module · 15 ca sử dụng</span></div></div>
    </aside>

    <main id="srs-main" className="srs-main">
      {screen === "list" ? <PatientList patients={filteredPatients} search={search} setSearch={setSearch} mineOnly={mineOnly} setMineOnly={setMineOnly} onOpen={openPatient} /> : <PatientRecord patient={selectedPatient} activeModule={activeModule} setActiveModule={setActiveModule} emergency={emergencyAccess} sourceKey={sourceKey} sourceOpen={sourceOpen} setSourceOpen={setSourceOpen} openSource={openSource} reviewDecision={reviewDecision} setReviewDecision={setReviewDecision} onBack={() => setScreen("list")} showToast={setToast} />}
    </main>

    {breakGlassPatient && <BreakGlassModal patient={breakGlassPatient} reason={breakGlassReason} setReason={setBreakGlassReason} onCancel={() => setBreakGlassPatient(null)} onConfirm={grantEmergencyAccess} />}
    {toast && <div className="srs-toast" role="status" aria-live="polite"><CheckCircle2 aria-hidden="true" /><span>{toast}</span><button onClick={() => setToast("")} aria-label="Đóng thông báo"><X aria-hidden="true" /></button></div>}
  </div>;
}

function PatientList({ patients: visiblePatients, search, setSearch, mineOnly, setMineOnly, onOpen }: { patients: Patient[]; search: string; setSearch: (value: string) => void; mineOnly: boolean; setMineOnly: (value: boolean) => void; onOpen: (patient: Patient) => void }) {
  return <div className="srs-page">
    <div className="srs-page-heading"><div><span className="srs-eyebrow">SC-02 · Patient Intelligence</span><h1>Người bệnh trong khoa</h1><p>Chọn người bệnh để xem tóm tắt hồ sơ hoặc soạn nháp bệnh án.</p></div><div className="srs-count"><strong>6</strong><span>BN của bạn</span><i /><strong>9</strong><span>BN trong khoa</span></div></div>
    <Disclaimer />
    <section className="srs-list-card">
      <div className="srs-list-toolbar"><label className="srs-search"><Search aria-hidden="true" /><span className="sr-only">Tìm người bệnh</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm theo tên, mã, giường hoặc lý do vào viện" /></label><label className="srs-check"><input type="checkbox" checked={mineOnly} onChange={(event) => setMineOnly(event.target.checked)} />Chỉ BN tôi điều trị</label><span><ListFilter aria-hidden="true" />{visiblePatients.length} kết quả</span></div>
      <div className="srs-patient-table" role="table" aria-label="Danh sách người bệnh">
        <div className="srs-patient-row head" role="row"><span>Mã</span><span>Người bệnh</span><span>Buồng / giường</span><span>Lý do vào viện</span><span /></div>
        {visiblePatients.map((patient) => <div className="srs-patient-row" role="row" key={patient.id}><span className="srs-id">{patient.id}</span><span className="srs-patient-name"><b>{patient.mine ? patient.name : "Tên được ẩn"}</b><small>{patient.gender} · {patient.birthYear}{!patient.mine && " · Không phụ trách"}</small></span><span>{patient.room}<small>{patient.bed}</small></span><span>{patient.reason}</span><button onClick={() => onOpen(patient)}>{patient.mine ? "Mở hồ sơ" : "Yêu cầu truy cập"}<ChevronRight aria-hidden="true" /></button></div>)}
        {visiblePatients.length === 0 && <div className="srs-empty"><Search aria-hidden="true" /><strong>Không tìm thấy người bệnh</strong><span>Thử từ khóa khác hoặc bỏ bộ lọc người bệnh của bạn.</span></div>}
      </div>
    </section>
  </div>;
}

function BreakGlassModal({ patient, reason, setReason, onCancel, onConfirm }: { patient: Patient; reason: string; setReason: (value: string) => void; onCancel: () => void; onConfirm: () => void }) {
  const valid = reason.trim().length >= 10;
  return <div className="srs-modal-backdrop" role="presentation"><section className="srs-modal srs-break-glass" role="dialog" aria-modal="true" aria-labelledby="break-glass-title"><button className="srs-icon-btn close" onClick={onCancel} aria-label="Đóng"><X aria-hidden="true" /></button><div className="srs-modal-icon danger"><LockKeyhole aria-hidden="true" /></div><span className="srs-eyebrow danger">SC-05 · Break the glass</span><h2 id="break-glass-title">Bạn không phải bác sĩ điều trị</h2><p>Hồ sơ <strong>{patient.id}</strong> đang bị chặn. Chỉ sử dụng truy cập khẩn cấp khi cần chăm sóc người bệnh; cả lần bị từ chối và lần truy cập sẽ được ghi audit.</p><label htmlFor="emergency-reason">Lý do truy cập khẩn cấp <span>*</span></label><textarea id="emergency-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Ví dụ: Trực đêm, cần kiểm tra thuốc đang dùng trước xử trí..." aria-describedby="reason-help" /><div id="reason-help" className={valid ? "valid" : ""}>{valid ? <Check aria-hidden="true" /> : <Info aria-hidden="true" />}{reason.trim().length}/10 ký tự tối thiểu</div><div className="srs-modal-actions"><button className="srs-btn secondary" onClick={onCancel}>Quay lại danh sách</button><button className="srs-btn danger" disabled={!valid} onClick={onConfirm}><ShieldAlert aria-hidden="true" />Truy cập khẩn cấp</button></div></section></div>;
}

function PatientRecord({ patient, activeModule, setActiveModule, emergency, sourceKey, sourceOpen, setSourceOpen, openSource, reviewDecision, setReviewDecision, onBack, showToast }: { patient: Patient; activeModule: ModuleTab; setActiveModule: (tab: ModuleTab) => void; emergency: boolean; sourceKey: SourceKey; sourceOpen: boolean; setSourceOpen: (open: boolean) => void; openSource: (key: SourceKey) => void; reviewDecision: "confirmed" | "needs-fix" | null; setReviewDecision: (decision: "confirmed" | "needs-fix") => void; onBack: () => void; showToast: (message: string) => void }) {
  return <div className="srs-page record-page">
    <button className="srs-back" onClick={onBack}><ArrowLeft aria-hidden="true" />Danh sách người bệnh</button>
    <div className="srs-record-heading"><div className="srs-record-avatar"><UserRound aria-hidden="true" /></div><div><span className="srs-eyebrow">Mã BN · {patient.id}</span><h1>{patient.name}</h1><p>{patient.gender} · {patient.birthYear} · {patient.room} — {patient.bed}</p></div><div className="srs-record-meta"><span>Bác sĩ điều trị<strong>BS. Nguyễn An</strong></span><span>Vào khoa<strong>08/11/2026 · 09:15</strong></span></div></div>
    <Disclaimer emergency={emergency} />
    <div className="srs-module-tabs" role="tablist" aria-label="Module hồ sơ"><button role="tab" aria-selected={activeModule === "summary"} className={activeModule === "summary" ? "active" : ""} onClick={() => setActiveModule("summary")}><BookOpenCheck aria-hidden="true" /><span><small>Module 1</small>Patient Intelligence</span></button><button role="tab" aria-selected={activeModule === "documentation"} className={activeModule === "documentation" ? "active" : ""} onClick={() => setActiveModule("documentation")}><Stethoscope aria-hidden="true" /><span><small>Module 2</small>Clinical Documentation</span></button></div>
    {activeModule === "summary" ? <SummaryModule sourceKey={sourceKey} sourceOpen={sourceOpen} setSourceOpen={setSourceOpen} openSource={openSource} emergency={emergency} reviewDecision={reviewDecision} setReviewDecision={setReviewDecision} showToast={showToast} /> : <DocumentationModule openSource={openSource} showToast={showToast} />}
  </div>;
}

function SummaryModule({ sourceKey, sourceOpen, setSourceOpen, openSource, emergency, reviewDecision, setReviewDecision, showToast }: { sourceKey: SourceKey; sourceOpen: boolean; setSourceOpen: (open: boolean) => void; openSource: (source: SourceKey) => void; emergency: boolean; reviewDecision: "confirmed" | "needs-fix" | null; setReviewDecision: (decision: "confirmed" | "needs-fix") => void; showToast: (message: string) => void }) {
  const source = sources[sourceKey];
  return <div className={`srs-summary-layout ${sourceOpen ? "with-source" : ""}`}>
    <div className="srs-summary-main">
      <div className="srs-section-heading"><div><span className="srs-eyebrow"><Sparkles aria-hidden="true" />Pipeline đã kiểm chứng</span><h2>Tóm tắt hồ sơ 6 mục</h2><p>7 loại bản ghi · 18 nguồn · cập nhật 09:42 ngày 11/11/2026</p></div><button className="srs-btn secondary" onClick={() => setSourceOpen(!sourceOpen)}><FileText aria-hidden="true" />{sourceOpen ? "Ẩn panel nguồn" : "Mở panel nguồn"}</button></div>
      <SafetyFlags openSource={openSource} />
      <section className="srs-summary-section"><header><span>01</span><div><h3>Bệnh nền và vấn đề chính</h3><p>Thông tin đã đối chiếu từ các lần khám trước.</p></div></header><ul><li>Đái tháo đường típ 2, ICD-10 E11, ghi nhận từ 14/05/2024. <Citation source="encounter" onOpen={openSource} /></li><li>Rung nhĩ, ICD-10 I48 và tăng huyết áp, ICD-10 I10. <Citation source="encounter" onOpen={openSource} /></li></ul></section>
      <section className="srs-summary-section"><header><span>02</span><div><h3>Đợt điều trị hiện tại</h3><p>Lý do vào viện, sinh hiệu và cận lâm sàng chính.</p></div></header><ul><li>Vào viện vì sốt, ho đờm và khó thở; ngày thứ 3 của bệnh. <Citation source="admission" onOpen={openSource} /></li><li>Mạch 104 lần/phút, nhiệt độ 38,6°C, HA 128/76 mmHg, nhịp thở 26 lần/phút, SpO₂ 91%. <Citation source="admission" onOpen={openSource} /></li><li>X-quang: đám mờ thùy dưới phổi phải. <Citation source="admission" onOpen={openSource} /></li></ul></section>
      <section className="srs-summary-section"><header><span>03</span><div><h3>Thuốc đang dùng theo hoạt chất</h3><p>Biệt dược được quy đổi trước khi kiểm tra trùng và tương tác.</p></div></header><div className="srs-med-grid"><div><Pill aria-hidden="true" /><span><strong>Amlodipin</strong><small>5 mg · 1 lần/ngày</small></span><Citation source="medication" onOpen={openSource} /></div><div><Pill aria-hidden="true" /><span><strong>Apixaban</strong><small>5 mg · 2 lần/ngày</small></span><Citation source="encounter" onOpen={openSource} /></div><div><Pill aria-hidden="true" /><span><strong>Metformin</strong><small>850 mg · 2 lần/ngày</small></span><Citation source="medication" onOpen={openSource} /></div></div></section>
      <section className="srs-summary-section"><header><span>04</span><div><h3>Xu hướng xét nghiệm</h3><p>Giá trị đầu → mới nhất; đánh dấu khi thay đổi từ 5%.</p></div></header><div className="srs-trend-grid"><div><span>Kali</span><strong>5,8 → 5,4 <small>mmol/L</small></strong><em className="down">Giảm · vẫn cao</em></div><div><span>eGFR</span><strong>52 → 38 <small>mL/phút</small></strong><em className="down">Giảm 27%</em></div><div><span>CRP</span><strong>28 → 96 <small>mg/L</small></strong><em className="up">Tăng 243%</em></div></div><Citation source="lab" onOpen={openSource} /></section>
      <section className="srs-summary-section conflict"><header><span>05</span><div><h3>Dị ứng</h3><p>Nguồn mâu thuẫn được giữ nguyên để bác sĩ đối chiếu.</p></div></header><div className="srs-conflict"><AlertTriangle aria-hidden="true" /><div><strong>Hai nguồn ghi khác nhau</strong><p>Giấy ra viện ngoài ghi dị ứng Aspirin (nổi mẩn); lần khám tại Vinmec ghi “không dị ứng”. AI không chọn bên đúng.</p><Citation source="external" onOpen={openSource} /><Citation source="encounter" onOpen={openSource} /></div></div></section>
      <section className="srs-summary-section missing"><header><span>06</span><div><h3>Chưa ghi nhận</h3><p>Không suy đoán khi hồ sơ chưa có dữ liệu.</p></div></header><ul><li>Tiền sử gia đình.</li><li>Tình trạng hút thuốc và sử dụng rượu bia.</li><li>Cân nặng hiện tại.</li></ul></section>
      <details className="srs-rejected"><summary><CircleAlert aria-hidden="true" />2 dòng bị bộ kiểm chứng loại</summary><p>“Người bệnh suy thận tiến triển” — loại vì không có nguồn nêu chẩn đoán.</p><p>“Cần ngừng metformin” — loại vì hệ thống không được đề xuất thay đổi điều trị.</p></details>
    </div>
    {sourceOpen && <aside className="srs-source-panel"><div className="srs-panel-header"><div><span className="srs-eyebrow">SC-04 · Nguồn</span><h2>Bản ghi gốc</h2></div><button className="srs-icon-btn" onClick={() => setSourceOpen(false)} aria-label="Đóng panel nguồn"><X aria-hidden="true" /></button></div><div className="srs-source-verified"><ShieldCheck aria-hidden="true" /><span><strong>Đã tìm thấy trong hồ sơ</strong><small>Mã và nội dung khớp dữ liệu nguồn</small></span></div><article className="srs-source-record"><span>{source.type}</span><h3>{source.id}</h3><dl><div><dt>Ngày</dt><dd>{source.date}</dd></div><div><dt>Nơi phát sinh</dt><dd>{source.origin}</dd></div></dl><pre>{source.content}</pre><button className="srs-btn secondary wide" onClick={() => showToast(`Đã ghi audit xem bản ghi ${source.id}.`)}>Mở toàn bộ bản ghi<ExternalLink aria-hidden="true" /></button></article><ReviewPanel emergency={emergency} decision={reviewDecision} onDecision={(decision) => { setReviewDecision(decision); showToast(decision === "confirmed" ? "Đã lưu lượt xác nhận và bản chụp tóm tắt." : "Đã ghi nhận yêu cầu sửa tóm tắt."); }} /></aside>}
  </div>;
}

function SafetyFlags({ openSource }: { openSource: (source: SourceKey) => void }) {
  const items = [
    { severity: "high", title: "Trùng hoạt chất: Amlodipin", text: "Amlodipin 5 mg và Amlor 5 mg cùng hoạt chất; cả hai đơn đang active.", source: "medication" as SourceKey },
    { severity: "high", title: "Kali bất thường chưa thấy xử trí", text: "Kali 5,8 mmol/L; lần đo tiếp theo sau 241 ngày là 5,4 mmol/L.", source: "lab" as SourceKey },
    { severity: "high", title: "Dị ứng ghi không thống nhất", text: "Giấy ra viện ngoài ghi dị ứng Aspirin; lần khám Vinmec ghi không dị ứng.", source: "external" as SourceKey },
    { severity: "medium", title: "Metformin cần xem lại theo chức năng thận", text: "eGFR mới nhất 38 mL/phút/1,73m²; hệ thống chỉ nhắc bác sĩ rà soát.", source: "lab" as SourceKey },
  ];
  return <section className="srs-flags"><div className="srs-card-header"><div><ShieldAlert aria-hidden="true" /><span><strong>Cờ cần chú ý</strong><small>Quy tắc xác định R-01 đến R-06 · không do LLM</small></span></div><b>{items.length}</b></div><div className="srs-flag-list">{items.map((item) => <article className={`srs-flag ${item.severity}`} key={item.title}><AlertTriangle aria-hidden="true" /><div><span>{item.severity === "high" ? "Cao" : "Trung bình"}</span><h3>{item.title}</h3><p>{item.text}</p><button onClick={() => openSource(item.source)}><FileText aria-hidden="true" />Xem dẫn chứng</button></div></article>)}</div></section>;
}

function ReviewPanel({ emergency, decision, onDecision }: { emergency: boolean; decision: "confirmed" | "needs-fix" | null; onDecision: (decision: "confirmed" | "needs-fix") => void }) {
  return <section className="srs-review"><div className="srs-card-header"><div><ClipboardCheck aria-hidden="true" /><span><strong>Bác sĩ rà soát tóm tắt</strong><small>{decision ? `Lần gần nhất: ${decision === "confirmed" ? "Đã xác nhận" : "Cần sửa"}` : "Chưa có lượt rà soát"}</small></span></div></div><label htmlFor="review-note">Góp ý không bắt buộc</label><textarea id="review-note" placeholder="Ghi rõ mục cần sửa hoặc thông tin cần kiểm tra lại..." disabled={emergency} /><div className="srs-review-actions"><button className="srs-btn primary" disabled={emergency} onClick={() => onDecision("confirmed")}><CheckCircle2 aria-hidden="true" />Xác nhận tóm tắt</button><button className="srs-btn secondary" disabled={emergency} onClick={() => onDecision("needs-fix")}>Cần sửa</button></div>{emergency && <p className="srs-lock-note"><LockKeyhole aria-hidden="true" />Truy cập khẩn cấp chỉ cho phép xem.</p>}</section>;
}

function DocumentationModule({ openSource, showToast }: { openSource: (source: SourceKey) => void; showToast: (message: string) => void }) {
  const [draftReady, setDraftReady] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [signed, setSigned] = useState(false);
  const [note, setNote] = useState(noteDraft);
  const [highlightTurn, setHighlightTurn] = useState<number | null>(null);
  const [signModal, setSignModal] = useState(false);
  const [fhirOpen, setFhirOpen] = useState(false);

  function generate() {
    setGenerating(true);
    window.setTimeout(() => { setGenerating(false); setDraftReady(true); showToast("Đã soạn bản nháp và kiểm chứng từng dòng trong 1,8 giây."); }, 700);
  }

  function sign() {
    setSigned(true);
    setEditing(false);
    setSignModal(false);
    showToast("Bệnh án đã được ký, khóa và ghi vào audit log.");
  }

  return <div className="srs-documentation">
    <section className="srs-transcript-input"><div><label htmlFor="transcript-select">Transcript có sẵn</label><select id="transcript-select" defaultValue="TS-2026-11-08"><option>TS-2026-11-08 · 16 lượt</option><option>TS-2026-11-05 · 12 lượt</option></select></div><span>hoặc</span><label className="srs-paste"><span>Dán transcript mới</span><textarea placeholder="Mỗi dòng bắt đầu bằng BS:, BN: hoặc NN:" /></label><button className="srs-btn primary" onClick={generate} disabled={generating}>{generating ? <LoaderCircle className="spin" aria-hidden="true" /> : <Sparkles aria-hidden="true" />}{generating ? "Đang chuẩn hóa & kiểm chứng" : "Soạn nháp bệnh án"}</button></section>
    {!draftReady ? <div className="srs-empty large"><FileText aria-hidden="true" /><strong>Chưa có bản nháp</strong><span>Chọn transcript hoặc dán nội dung đúng định dạng để bắt đầu.</span></div> : <div className="srs-doc-grid">
      <section className="srs-transcript-column"><div className="srs-column-header"><div><span className="srs-eyebrow">Transcript</span><h2>TS-2026-11-08</h2></div><span>16 lượt</span></div><div className="srs-transcript-list">{transcript.map((turn) => <button key={turn.n} className={highlightTurn === turn.n ? "active" : ""} onClick={() => setHighlightTurn(turn.n)}><span>{turn.n}</span><div><strong className={turn.speaker.toLowerCase()}>{turn.speaker}</strong><p>{turn.text}</p>{turn.n === 13 && <small>Chuẩn hóa: SpO₂ 91%, HA 128/76 mmHg</small>}</div></button>)}</div></section>
      <section className="srs-note-column"><div className="srs-column-header"><div><span className={`srs-status ${signed ? "signed" : "draft"}`}>{signed ? <CheckCircle2 aria-hidden="true" /> : <FileText aria-hidden="true" />}{signed ? "Đã ký duyệt" : "Bản nháp — chưa duyệt"}</span><h2>Bệnh án Nội khoa</h2></div><div className="srs-note-actions">{!signed && <button className="srs-btn secondary" onClick={() => setEditing(!editing)}><PencilLine aria-hidden="true" />{editing ? "Xem có dẫn chứng" : "Chỉnh sửa"}</button>}{!signed && <button className="srs-btn primary" onClick={() => setSignModal(true)}><FileCheck2 aria-hidden="true" />Bác sĩ ký duyệt</button>}{signed && <button className="srs-btn primary" onClick={() => setFhirOpen(true)}><Download aria-hidden="true" />Xuất FHIR</button>}</div></div>{editing ? <textarea className="srs-note-editor" value={note} onChange={(event) => setNote(event.target.value)} aria-label="Nội dung bệnh án" /> : <StructuredNote onTurn={setHighlightTurn} openSource={openSource} signed={signed} />}{signed && <SignedStats />}</section>
      <section className="srs-safety-column"><div className="srs-column-header"><div><span className="srs-eyebrow">An toàn buổi khám</span><h2>Cờ & mục thiếu</h2></div><b>{flags.length}</b></div><div className="srs-doc-flags">{flags.map((flag) => <article className={`srs-doc-flag ${flag.severity}`} key={flag.title}><span>{flag.severity === "red" ? "Đỏ" : flag.severity === "high" ? "Cao" : flag.severity === "medium" ? "Trung bình" : "Thông tin"}</span><h3>{flag.title}</h3><p>{flag.body}</p><button onClick={() => { const turn = Number(flag.evidence.replace("L", "")); if (Number.isFinite(turn)) setHighlightTurn(turn); }}><FileText aria-hidden="true" />{flag.evidence}</button></article>)}</div></section>
    </div>}
    {signModal && <div className="srs-modal-backdrop"><section className="srs-modal" role="dialog" aria-modal="true" aria-labelledby="sign-title"><button className="srs-icon-btn close" onClick={() => setSignModal(false)} aria-label="Đóng"><X aria-hidden="true" /></button><div className="srs-modal-icon"><FileCheck2 aria-hidden="true" /></div><span className="srs-eyebrow">UC-12 · Ký duyệt</span><h2 id="sign-title">Ký và khóa bệnh án?</h2><p>Sau khi ký, bệnh án chuyển sang chỉ đọc và không thể sửa hoặc ký lại. Hệ thống lưu bản AI, bản cuối cùng và diff theo dòng.</p><label className="srs-check sign"><input type="checkbox" defaultChecked />Tôi đã rà soát cờ đỏ, mục thiếu và các nguồn dẫn.</label><div className="srs-modal-actions"><button className="srs-btn secondary" onClick={() => setSignModal(false)}>Tiếp tục kiểm tra</button><button className="srs-btn primary" onClick={sign}><FileCheck2 aria-hidden="true" />Ký duyệt & khóa</button></div></section></div>}
    {fhirOpen && <div className="srs-modal-backdrop"><section className="srs-modal fhir" role="dialog" aria-modal="true" aria-labelledby="fhir-title"><button className="srs-icon-btn close" onClick={() => setFhirOpen(false)} aria-label="Đóng"><X aria-hidden="true" /></button><div className="srs-modal-icon"><Download aria-hidden="true" /></div><span className="srs-eyebrow">FHIR R4 Bundle</span><h2 id="fhir-title">Composition + Provenance</h2><pre>{`{\n  "resourceType": "Bundle",\n  "type": "document",\n  "entry": [\n    { "resource": { "resourceType": "Composition", "status": "final" } },\n    { "resource": { "resourceType": "Provenance", "recorded": "2026-11-11T09:48:00+07:00" } }\n  ]\n}`}</pre><div className="srs-modal-actions"><button className="srs-btn secondary" onClick={() => { navigator.clipboard?.writeText("FHIR R4 demo bundle"); showToast("Đã sao chép FHIR Bundle."); }}><Copy aria-hidden="true" />Sao chép JSON</button><button className="srs-btn primary" onClick={() => showToast("Đã chuẩn bị tệp FHIR Bundle mô phỏng.")}><Download aria-hidden="true" />Tải xuống</button></div></section></div>}
  </div>;
}

function StructuredNote({ onTurn, openSource, signed }: { onTurn: (turn: number) => void; openSource: (source: SourceKey) => void; signed: boolean }) {
  const turnButton = (turn: number) => <button className="srs-turn-cite" onClick={() => onTurn(turn)}>L{turn}</button>;
  return <div className="srs-structured-note"><div className="srs-note-disclaimer"><Info aria-hidden="true" /><p><strong>{signed ? "Bác sĩ đã rà soát và ký duyệt." : "Bản nháp do AI soạn — chưa duyệt."}</strong> Mỗi dòng giữ liên kết tới transcript hoặc hồ sơ nguồn.</p></div><section><h3>I. Lý do vào viện</h3><p>Sốt, ho đờm, khó thở. Vào ngày thứ 3 của bệnh. <Citation source="admission" onOpen={openSource} /></p></section><section><h3>II.1. Quá trình bệnh lý</h3><p>Mệt, sốt 3 hôm, ho nhiều, đờm vàng. {turnButton(2)}</p><p>Khó thở từ hôm qua, đau ngực phải tăng khi ho. {turnButton(4)} {turnButton(6)}</p><p>Người nhà kể người bệnh lú lẫn, nói lảm nhảm. {turnButton(9)}</p><p>Ăn kém, tiểu ít, một lần đi ngoài phân đen. {turnButton(11)}</p></section><section><h3>II.2. Tiền sử bản thân</h3><p>Đái tháo đường típ 2, rung nhĩ và tăng huyết áp. <Citation source="encounter" onOpen={openSource} /></p><p className="missing-line"><AlertTriangle aria-hidden="true" />Dị ứng: Chưa ghi nhận trong buổi khám.</p><p className="missing-line"><AlertTriangle aria-hidden="true" />Thuốc lá / rượu bia: Chưa ghi nhận.</p></section><section><h3>III.1. Toàn thân và dấu hiệu sinh tồn</h3><p>Mạch 104, nhiệt độ 38,6°C, HA 128/76 mmHg, nhịp thở 26, SpO₂ 91%. <Citation source="admission" onOpen={openSource} /></p><p className="missing-line"><AlertTriangle aria-hidden="true" />Cân nặng: Chưa ghi nhận.</p></section><section><h3>III.2. Khám các cơ quan</h3><p>Phổi phải có ran nổ vùng đáy; tim loạn nhịp hoàn toàn. {turnButton(12)}</p></section><section><h3>IV. Chẩn đoán theo lời bác sĩ</h3><p>Viêm phổi cộng đồng phổi phải. Gợi ý ICD-10 J18.9 — <strong>bác sĩ chọn mã</strong>. {turnButton(15)}</p></section><section><h3>VI. Hướng điều trị theo lời bác sĩ</h3><p>Thở oxy kính 2 lít; Augmentin và Clarithromycin; theo dõi sát SpO₂. {turnButton(15)} {turnButton(16)}</p></section></div>;
}

function SignedStats() {
  return <section className="srs-signed-stats"><div className="srs-diff"><h3><History aria-hidden="true" />Track changes · bản AI → bản bác sĩ</h3><p className="removed">− Dị ứng: Chưa ghi nhận trong buổi khám.</p><p className="added">+ Dị ứng Aspirin (nổi mẩn), bác sĩ đã hỏi lại người bệnh.</p></div><div className="srs-retention"><div><span>Tỉ lệ dòng AI được giữ</span><strong>97%</strong></div><div className="srs-retention-bar"><i style={{ width: "97%" }} /></div><table><thead><tr><th>Mục</th><th>Dòng AI</th><th>Bị sửa</th><th>BS thêm</th></tr></thead><tbody><tr><td>Lý do vào viện</td><td>1</td><td>0</td><td>0</td></tr><tr><td>Quá trình bệnh lý</td><td>8</td><td>0</td><td>0</td></tr><tr><td>Tiền sử bản thân</td><td>8</td><td>1</td><td>1</td></tr><tr><td>Chẩn đoán & điều trị</td><td>6</td><td>0</td><td>0</td></tr></tbody></table></div></section>;
}
