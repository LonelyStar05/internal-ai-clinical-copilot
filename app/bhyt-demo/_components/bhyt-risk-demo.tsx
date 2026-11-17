"use client";

import {
  AlertTriangle,
  BarChart3,
  Check,
  ChevronDown,
  CircleDollarSign,
  ClipboardCheck,
  Download,
  FileSearch,
  HeartPulse,
  Info,
  RotateCcw,
  SearchCheck,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import { useMemo, useState } from "react";
import { causes, denialCases, departments, mockOrders, mockPatient, quarterTrend, type MockOrder, type RiskLevel } from "../mock-data";
import styles from "../demo.module.css";

type Tab = "overview" | "order" | "claims";
type Resolution = "documented" | "insurance" | "continue" | "removed";

const money = (value: number) => new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND", maximumFractionDigits: 0 }).format(value);
const compactMoney = (value: number) => value >= 1_000_000_000
  ? `${String(Math.round(value / 10_000_000) / 100).replace(".", ",")} tỷ`
  : `${String(Math.round(value / 100_000) / 10).replace(".", ",")} triệu`;

const riskClass = (risk: RiskLevel) => risk === "safe" ? styles.safe : risk === "review" ? styles.review : styles.high;

function RiskStatusIcon({ risk }: { risk: RiskLevel }) {
  if (risk === "safe") return <Check aria-hidden="true" />;
  if (risk === "review") return <Info aria-hidden="true" />;
  return <AlertTriangle aria-hidden="true" />;
}

const resolutionLabel: Record<Resolution, string> = {
  documented: "Đã ghi căn cứ có thật",
  insurance: "Chuyển phòng BHYT",
  continue: "Tiếp tục vì chuyên môn",
  removed: "Bỏ chỉ định",
};

function NavIcon({ tab }: { tab: Tab }) {
  if (tab === "overview") return <BarChart3 aria-hidden="true" />;
  if (tab === "order") return <Stethoscope aria-hidden="true" />;
  return <FileSearch aria-hidden="true" />;
}

export function BhytRiskDemo() {
  const [tab, setTab] = useState<Tab>("order");
  const [selected, setSelected] = useState(() => mockOrders.map((order) => order.code));
  const [analyzed, setAnalyzed] = useState(true);
  const [resolutions, setResolutions] = useState<Record<string, Resolution>>({});
  const [saved, setSaved] = useState(false);

  const selectedOrders = useMemo(() => mockOrders.filter((order) => selected.includes(order.code)), [selected]);
  const atRisk = selectedOrders.filter((order) => order.risk !== "safe");
  const riskAmount = atRisk.reduce((sum, order) => sum + order.price, 0);
  const handledAmount = atRisk.filter((order) => resolutions[order.code]).reduce((sum, order) => sum + order.price, 0);
  const unresolved = atRisk.filter((order) => !resolutions[order.code]).length;

  function toggleOrder(code: string) {
    setSelected((current) => current.includes(code) ? current.filter((item) => item !== code) : [...current, code]);
    setAnalyzed(false);
    setSaved(false);
  }

  function runAnalysis() {
    setAnalyzed(true);
    setSaved(false);
  }

  function resetDemo() {
    setSelected(mockOrders.map((order) => order.code));
    setResolutions({});
    setAnalyzed(true);
    setSaved(false);
  }

  function exportCsv() {
    const header = ["Mã hồ sơ", "Khoa", "Dịch vụ", "Lý do", "Cổng phát hiện", "Đề nghị", "Thu hồi", "Kết quả"];
    const rows = denialCases.map((item) => [item.id, item.department, item.service, item.reason, item.gate, item.requested, item.recovered, item.result]);
    const csv = [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "mock-bhyt-q4-2024.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className={styles.app}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <span className={styles.brandMark}><ShieldCheck aria-hidden="true" /></span>
          <div>
            <strong>BHYT Risk Guard</strong>
            <span>Kiểm soát rủi ro thanh toán</span>
          </div>
        </div>
        <div className={styles.topMeta}>
          <span className={styles.mockBadge}>DỮ LIỆU GIẢ LẬP</span>
          <span className={styles.period}>Kỳ rà soát Q4/2024</span>
          <button type="button" className={styles.iconButton} onClick={resetDemo} aria-label="Đặt lại demo" title="Đặt lại demo"><RotateCcw aria-hidden="true" /></button>
        </div>
      </header>

      <div className={styles.shell}>
        <aside className={styles.sidebar} aria-label="Điều hướng demo">
          <p className={styles.navLabel}>Không gian làm việc</p>
          {([
            ["overview", "Tổng quan quý", "2,48 tỷ thu hồi"],
            ["order", "Kiểm tra chỉ định", `${unresolved} rủi ro chưa xử lý`],
            ["claims", "Hồ sơ hậu kiểm", `${denialCases.length} hồ sơ mẫu`],
          ] as const).map(([key, label, hint]) => (
            <button key={key} type="button" className={`${styles.navItem} ${tab === key ? styles.navActive : ""}`} onClick={() => setTab(key)} aria-current={tab === key ? "page" : undefined}>
              <NavIcon tab={key} />
              <span><strong>{label}</strong><small>{hint}</small></span>
            </button>
          ))}

          <section className={styles.flowCard}>
            <p>Ba cổng kiểm soát</p>
            <ol>
              <li><span>1</span><div><strong>Trước chỉ định</strong><small>Điều kiện, trùng, tần suất</small></div></li>
              <li><span>2</span><div><strong>Trước đóng bệnh án</strong><small>Căn cứ, diễn biến, gói</small></div></li>
              <li><span>3</span><div><strong>Trước gửi BHXH</strong><small>Mã, giá, danh mục, dữ liệu</small></div></li>
            </ol>
          </section>

          <div className={styles.userCard}>
            <span>NT</span>
            <div><strong>Nguyễn Thu Hà</strong><small>Phòng BHYT</small></div>
          </div>
        </aside>

        <section className={styles.content}>
          {tab === "overview" && <Overview onOpenOrder={() => setTab("order")} />}
          {tab === "order" && (
            <OrderCheck
              selected={selected}
              selectedOrders={selectedOrders}
              analyzed={analyzed}
              resolutions={resolutions}
              riskAmount={riskAmount}
              handledAmount={handledAmount}
              unresolved={unresolved}
              saved={saved}
              onToggle={toggleOrder}
              onAnalyze={runAnalysis}
              onResolve={(code, action) => { setResolutions((current) => ({ ...current, [code]: action })); setSaved(false); }}
              onSave={() => setSaved(true)}
            />
          )}
          {tab === "claims" && <ClaimsTable onExport={exportCsv} />}
        </section>
      </div>
    </main>
  );
}

function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return (
    <header className={styles.pageHeading}>
      <div><p>{eyebrow}</p><h1>{title}</h1><span>{description}</span></div>
      {action}
    </header>
  );
}

function Overview({ onOpenOrder }: { onOpenOrder: () => void }) {
  const maxQuarter = Math.max(...quarterTrend.map((item) => item.amount));
  const maxDepartment = Math.max(...departments.map((item) => item.annual));
  return (
    <>
      <PageHeading eyebrow="HẬU KIỂM BHYT · DỮ LIỆU GIẢ LẬP" title="Rủi ro được phát hiện quá muộn" description="Mô phỏng số liệu một bệnh viện tư có ký hợp đồng khám chữa bệnh BHYT." action={<button type="button" className={styles.primaryButton} onClick={onOpenOrder}><SearchCheck aria-hidden="true" />Thử một chỉ định</button>} />

      <dl className={styles.metrics}>
        <div><dt>Thu hồi năm 2024</dt><dd>8,64 tỷ</dd><span>4 kỳ rà soát</span></div>
        <div><dt>Riêng Q4/2024</dt><dd>2,48 tỷ</dd><span className={styles.negative}>+14,8% so với Q3</span></div>
        <div><dt>Có thể chặn trước chỉ định</dt><dd>41%</dd><span>ước tính 1,02 tỷ trong quý</span></div>
        <div><dt>Cần rà trước đóng bệnh án</dt><dd>32%</dd><span>căn cứ và gói dịch vụ</span></div>
      </dl>

      <div className={styles.dashboardGrid}>
        <section className={styles.card}>
          <header className={styles.cardHeader}><div><h2>Thu hồi theo quý</h2><p>Đơn vị: tỷ đồng</p></div><span className={styles.statusPill}>Năm 2024</span></header>
          <div className={styles.quarterChart} role="img" aria-label="Thu hồi Q1 1,86 tỷ, Q2 2,14 tỷ, Q3 2,16 tỷ và Q4 2,48 tỷ đồng">
            {quarterTrend.map((item) => <div key={item.quarter} className={styles.quarterBar}><strong>{compactMoney(item.amount)}</strong><i style={{ height: `${Math.round(item.amount / maxQuarter * 100)}%` }} /><span>{item.quarter.replace("/2024", "")}</span></div>)}
          </div>
        </section>

        <section className={styles.card}>
          <header className={styles.cardHeader}><div><h2>Nguyên nhân gốc</h2><p>Tỷ trọng trên tổng tiền thu hồi Q4</p></div></header>
          <div className={styles.causeList}>
            {causes.map((cause) => <div key={cause.name}><p><span>{cause.name}<small>{cause.gate}</small></span><strong>{cause.share}%</strong></p><i><b style={{ width: `${cause.share}%` }} /></i></div>)}
          </div>
        </section>

        <section className={`${styles.card} ${styles.wideCard}`}>
          <header className={styles.cardHeader}><div><h2>Khoa chịu thu hồi cao</h2><p>Không đồng nghĩa toàn bộ là lỗi của bác sĩ</p></div><span className={styles.mutedPill}>Số liệu năm</span></header>
          <div className={styles.departmentList}>
            {departments.map((department, index) => <div key={department.name}><span className={styles.rank}>{index + 1}</span><div><p><strong>{department.name}</strong><span>{department.cases} khoản bị hậu kiểm</span></p><i><b style={{ width: `${Math.round(department.annual / maxDepartment * 100)}%` }} /></i></div><strong>{compactMoney(department.annual)}</strong></div>)}
          </div>
        </section>
      </div>
      <p className={styles.disclaimer}><Info aria-hidden="true" /><span>Toàn bộ con số trên là dữ liệu mock để kiểm thử sản phẩm, không phải số liệu của một bệnh viện thật.</span></p>
    </>
  );
}

function OrderCheck({ selected, selectedOrders, analyzed, resolutions, riskAmount, handledAmount, unresolved, saved, onToggle, onAnalyze, onResolve, onSave }: {
  selected: string[];
  selectedOrders: MockOrder[];
  analyzed: boolean;
  resolutions: Record<string, Resolution>;
  riskAmount: number;
  handledAmount: number;
  unresolved: number;
  saved: boolean;
  onToggle: (code: string) => void;
  onAnalyze: () => void;
  onResolve: (code: string, action: Resolution) => void;
  onSave: () => void;
}) {
  return (
    <>
      <PageHeading eyebrow="CỔNG 1 · TRƯỚC CHỈ ĐỊNH" title="Kiểm tra rủi ro trước khi phát sinh chi phí" description="Bác sĩ quyết định chuyên môn; hệ thống chỉ đối chiếu điều kiện thanh toán và dữ liệu đang có." />

      <section className={styles.patientStrip}>
        <div className={styles.patientAvatar}>NM</div>
        <div className={styles.patientIdentity}><strong>{mockPatient.name}</strong><span>{mockPatient.id} · {mockPatient.age} tuổi · {mockPatient.sex}</span></div>
        <dl><div><dt>Khoa</dt><dd>{mockPatient.department}</dd></div><div><dt>Đợt điều trị</dt><dd>{mockPatient.encounter}</dd></div><div><dt>Nguồn thanh toán</dt><dd>{mockPatient.insurance}</dd></div></dl>
        <button type="button" className={styles.secondaryButton}>Đổi hồ sơ <ChevronDown aria-hidden="true" /></button>
      </section>

      <div className={styles.orderLayout}>
        <div className={styles.orderMain}>
          <section className={styles.card}>
            <header className={styles.cardHeader}><div><h2>Chỉ định dự kiến</h2><p>Chọn dịch vụ rồi chạy kiểm tra theo hồ sơ hiện tại</p></div><span className={styles.statusPill}>{selected.length} dịch vụ</span></header>
            <div className={styles.orderPicker}>
              {mockOrders.map((order) => <label key={order.code} className={selected.includes(order.code) ? styles.orderSelected : ""}><input type="checkbox" checked={selected.includes(order.code)} onChange={() => onToggle(order.code)} /><span><strong>{order.name}</strong><small>{order.code} · {money(order.price)}</small></span></label>)}
            </div>
            <button type="button" className={styles.primaryButton} onClick={onAnalyze} disabled={selected.length === 0}><SearchCheck aria-hidden="true" />Phân tích {selected.length || ""} chỉ định</button>
          </section>

          {analyzed && selectedOrders.length > 0 && (
            <section className={styles.results} aria-live="polite">
              <header><div><p>Kết quả kiểm tra</p><h2>{selectedOrders.length} chỉ định · {unresolved} điểm cần xử lý</h2></div><div><span>Giá trị có nguy cơ</span><strong>{money(riskAmount)}</strong></div></header>
              {selectedOrders.map((order) => <RiskResult key={order.code} order={order} resolution={resolutions[order.code]} onResolve={(action) => onResolve(order.code, action)} />)}
            </section>
          )}
        </div>

        <aside className={styles.contextPanel}>
          <section className={styles.card}>
            <header className={styles.cardHeader}><div><h2>Hồ sơ đang có</h2><p>Dữ liệu dùng để kiểm tra</p></div><HeartPulse aria-hidden="true" /></header>
            <div className={styles.diagnosis}><span>Chẩn đoán chính</span><strong>{mockPatient.diagnosis}</strong></div>
            <ul className={styles.factList}>{mockPatient.facts.map((fact) => <li key={fact}><Check aria-hidden="true" />{fact}</li>)}</ul>
          </section>

          <section className={styles.summaryCard}>
            <p><CircleDollarSign aria-hidden="true" />Tác động dự kiến</p>
            <dl><div><dt>Giá trị có nguy cơ</dt><dd>{money(riskAmount)}</dd></div><div><dt>Đã có phương án</dt><dd>{money(handledAmount)}</dd></div><div><dt>Chưa xử lý</dt><dd>{unresolved} chỉ định</dd></div></dl>
            <button type="button" className={styles.primaryButton} disabled={unresolved > 0 || selectedOrders.length === 0} onClick={onSave}><ClipboardCheck aria-hidden="true" />Lưu phương án chỉ định</button>
            {saved && <p className={styles.savedMessage} role="status"><Check aria-hidden="true" />Đã lưu vào audit log giả lập.</p>}
            {unresolved > 0 && <small>Chọn một phương án cho từng cảnh báo trước khi lưu.</small>}
          </section>
        </aside>
      </div>
      <p className={styles.disclaimer}><Info aria-hidden="true" /><span>Quy tắc trong demo là giả lập, không phải căn cứ thanh toán BHYT và không dùng để tư vấn hay thay thế quyết định chuyên môn.</span></p>
    </>
  );
}

function RiskResult({ order, resolution, onResolve }: { order: MockOrder; resolution?: Resolution; onResolve: (action: Resolution) => void }) {
  return (
    <article className={`${styles.riskCard} ${riskClass(order.risk)}`}>
      <div className={styles.riskTop}>
        <span className={styles.riskIcon}><RiskStatusIcon risk={order.risk} /></span>
        <div><p><strong>{order.name}</strong><span>{money(order.price)}</span></p><span className={styles.riskLabel}>{order.label}</span></div>
      </div>
      <p className={styles.issue}>{order.issue}</p>
      <div className={styles.evidenceGrid}>
        <div><span>Căn cứ đang có</span><ul>{order.evidence.map((item) => <li key={item}>{item}</li>)}</ul></div>
        {order.missing && <div><span>Còn thiếu</span><ul>{order.missing.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      </div>
      <p className={styles.rule}><ShieldCheck aria-hidden="true" />{order.rule}</p>
      {order.risk !== "safe" && (
        <div className={styles.resolveActions} role="group" aria-label={`Chọn phương án cho ${order.name}`}>
          <span>Phương án:</span>
          {(["documented", "insurance", "continue", "removed"] as Resolution[]).map((action) => <button type="button" key={action} aria-pressed={resolution === action} onClick={() => onResolve(action)}>{resolution === action && <Check aria-hidden="true" />}{resolutionLabel[action]}</button>)}
        </div>
      )}
    </article>
  );
}

function ClaimsTable({ onExport }: { onExport: () => void }) {
  const [query, setQuery] = useState("");
  const [gate, setGate] = useState("Tất cả");
  const filtered = denialCases.filter((item) => {
    const haystack = `${item.id} ${item.department} ${item.service} ${item.reason}`.toLocaleLowerCase("vi");
    return haystack.includes(query.toLocaleLowerCase("vi")) && (gate === "Tất cả" || item.gate === gate);
  });
  const total = filtered.reduce((sum, item) => sum + item.recovered, 0);
  return (
    <>
      <PageHeading eyebrow="DANH SÁCH MOCK · Q4/2024" title="Hồ sơ bị hậu kiểm" description="Dùng dữ liệu rà soát theo quý để tìm các quy tắc có thể phòng ngừa sớm." action={<button type="button" className={styles.secondaryButton} onClick={onExport}><Download aria-hidden="true" />Tải CSV mẫu</button>} />
      <section className={styles.card}>
        <div className={styles.filters}>
          <label><span>Tìm hồ sơ, khoa hoặc dịch vụ</span><div><FileSearch aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ví dụ: HbA1c" /></div></label>
          <label><span>Cổng có thể phát hiện</span><select value={gate} onChange={(event) => setGate(event.target.value)}><option>Tất cả</option><option>Trước chỉ định</option><option>Trước đóng bệnh án</option><option>Trước gửi BHXH</option></select></label>
          <div className={styles.filterSummary}><span>Tiền thu hồi trong mẫu</span><strong>{money(total)}</strong></div>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.claimsTable}>
            <thead><tr><th>Mã hồ sơ</th><th>Khoa · dịch vụ</th><th>Lý do hậu kiểm</th><th>Cổng phát hiện</th><th className={styles.numberCell}>Đề nghị</th><th className={styles.numberCell}>Thu hồi</th><th>Kết quả</th></tr></thead>
            <tbody>{filtered.map((item) => <tr key={item.id}><td className={styles.mono}>{item.id}</td><td><strong>{item.department}</strong><span>{item.service}</span></td><td>{item.reason}</td><td><span className={styles.gatePill}>{item.gate}</span></td><td className={styles.numberCell}>{money(item.requested)}</td><td className={`${styles.numberCell} ${styles.recovered}`}>{item.recovered ? money(item.recovered) : "—"}</td><td><span className={item.result === "Thu hồi" ? styles.badResult : item.result === "Đang giải trình" ? styles.pendingResult : styles.partialResult}>{item.result}</span></td></tr>)}</tbody>
          </table>
        </div>
        {filtered.length === 0 && <div className={styles.emptyState}><FileSearch aria-hidden="true" /><strong>Không tìm thấy hồ sơ</strong><span>Thử từ khóa hoặc cổng kiểm soát khác.</span></div>}
      </section>
      <p className={styles.disclaimer}><Info aria-hidden="true" /><span>CSV chỉ chứa dữ liệu giả lập và không có thông tin định danh người bệnh thật.</span></p>
    </>
  );
}

