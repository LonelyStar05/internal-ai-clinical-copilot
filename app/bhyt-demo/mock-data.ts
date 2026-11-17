export type RiskLevel = "safe" | "review" | "high";

export type MockOrder = {
  code: string;
  name: string;
  price: number;
  risk: RiskLevel;
  label: string;
  issue: string;
  evidence: string[];
  missing?: string[];
  rule: string;
};

export type DenialCase = {
  id: string;
  department: string;
  service: string;
  reason: string;
  gate: "Trước chỉ định" | "Trước đóng bệnh án" | "Trước gửi BHXH";
  requested: number;
  recovered: number;
  result: "Thu hồi" | "Giải trình một phần" | "Đang giải trình";
};

export const quarterTrend = [
  { quarter: "Q1/2024", amount: 1_860_000_000 },
  { quarter: "Q2/2024", amount: 2_140_000_000 },
  { quarter: "Q3/2024", amount: 2_160_000_000 },
  { quarter: "Q4/2024", amount: 2_480_000_000 },
];

export const departments = [
  { name: "Nội tim mạch", annual: 382_400_000, q4: 112_600_000, cases: 87 },
  { name: "Nội tiết", annual: 347_800_000, q4: 96_400_000, cases: 74 },
  { name: "Ngoại tổng hợp", annual: 318_600_000, q4: 91_200_000, cases: 61 },
  { name: "Hồi sức tích cực", annual: 284_300_000, q4: 79_800_000, cases: 53 },
  { name: "Hô hấp", annual: 248_900_000, q4: 67_500_000, cases: 58 },
];

export const causes = [
  { name: "Không đủ điều kiện chỉ định", share: 29, gate: "Trước chỉ định" },
  { name: "Thiếu căn cứ trong bệnh án", share: 23, gate: "Trước đóng bệnh án" },
  { name: "Sai giá, danh mục hoặc cấu hình", share: 15, gate: "Trước gửi BHXH" },
  { name: "Trùng hoặc sai tần suất", share: 12, gate: "Trước chỉ định" },
  { name: "Dịch vụ đã nằm trong gói", share: 9, gate: "Trước đóng bệnh án" },
  { name: "Điều kiện nhân lực, thiết bị", share: 7, gate: "Trước gửi BHXH" },
  { name: "Khác/đang tranh chấp", share: 5, gate: "Trước gửi BHXH" },
];

export const mockPatient = {
  id: "BN-240912",
  name: "Nguyễn Văn Minh",
  age: 58,
  sex: "Nam",
  department: "Nội tim mạch",
  encounter: "ĐT-2024-0912-018",
  insurance: "BHYT nhà nước · mức hưởng 80%",
  diagnosis: "E78.5 · Rối loạn lipid máu, không đặc hiệu",
  facts: [
    "Khám định kỳ, chưa ghi nhận đa niệu hoặc khát nhiều",
    "Chưa có chẩn đoán đái tháo đường hoặc bệnh thận trong hồ sơ",
    "Đường máu đói 5,4 mmol/L ngày 11/09/2024",
    "Chưa ghi nhận lý do theo dõi chức năng thận trong diễn biến",
  ],
};

export const mockOrders: MockOrder[] = [
  {
    code: "LIPID",
    name: "Bộ xét nghiệm lipid máu",
    price: 186_000,
    risk: "safe",
    label: "Khả năng hợp lệ",
    issue: "Chẩn đoán hiện tại phù hợp với mục đích theo dõi lipid máu.",
    evidence: ["E78.5 trong chẩn đoán vào khoa", "Chưa có kết quả lipid trong đợt điều trị"],
    rule: "Quy tắc demo BHYT-R01 · đối chiếu chẩn đoán và kết quả gần đây",
  },
  {
    code: "HBA1C",
    name: "Định lượng HbA1c",
    price: 142_000,
    risk: "high",
    label: "Nguy cơ bị thu hồi",
    issue: "Chưa tìm thấy chẩn đoán, triệu chứng hoặc yếu tố nguy cơ được ghi nhận để hỗ trợ chỉ định trong hồ sơ hiện tại.",
    evidence: ["Chẩn đoán hiện tại: E78.5", "Đường máu đói 5,4 mmol/L ngày 11/09/2024"],
    missing: ["Mục đích xét nghiệm", "Căn cứ lâm sàng có thật nếu đang nghi ngờ rối loạn đường huyết"],
    rule: "Quy tắc demo BHYT-R06 · điều kiện chỉ định phải có căn cứ trong bệnh án",
  },
  {
    code: "CREAT",
    name: "Định lượng Creatinin máu",
    price: 41_000,
    risk: "review",
    label: "Cần bổ sung căn cứ",
    issue: "Xét nghiệm có thể cần thiết, nhưng diễn biến chưa ghi lý do đánh giá hoặc theo dõi chức năng thận.",
    evidence: ["Chưa có chẩn đoán bệnh thận", "Chưa ghi thuốc hoặc can thiệp cần theo dõi thận"],
    missing: ["Lý do chuyên môn thực tế của chỉ định"],
    rule: "Quy tắc demo BHYT-R11 · kiểm tra căn cứ theo dõi chức năng cơ quan",
  },
  {
    code: "GLU",
    name: "Định lượng Glucose máu",
    price: 48_000,
    risk: "high",
    label: "Trùng trong 24 giờ",
    issue: "Hồ sơ đã có kết quả đường máu đói từ ngày trước; chưa ghi lý do cần thực hiện lại.",
    evidence: ["Glucose 5,4 mmol/L ngày 11/09/2024", "Chỉ định mới ngày 12/09/2024"],
    missing: ["Lý do làm lại sớm nếu có"],
    rule: "Quy tắc demo BHYT-R03 · phát hiện dịch vụ lặp trong cửa sổ 24 giờ",
  },
];

export const denialCases: DenialCase[] = [
  { id: "HS-24Q4-0018", department: "Nội tim mạch", service: "HbA1c", reason: "Không đủ căn cứ chỉ định trong bệnh án", gate: "Trước chỉ định", requested: 142_000, recovered: 142_000, result: "Thu hồi" },
  { id: "HS-24Q4-0034", department: "Nội tim mạch", service: "Glucose máu", reason: "Lặp trong 24 giờ, không ghi lý do", gate: "Trước chỉ định", requested: 96_000, recovered: 48_000, result: "Giải trình một phần" },
  { id: "HS-24Q4-0071", department: "Nội tiết", service: "Siêu âm ổ bụng", reason: "Thiếu diễn biến hỗ trợ chỉ định", gate: "Trước đóng bệnh án", requested: 211_000, recovered: 211_000, result: "Thu hồi" },
  { id: "HS-24Q4-0103", department: "Ngoại tổng hợp", service: "CRP", reason: "Dịch vụ đã nằm trong gói phẫu thuật", gate: "Trước đóng bệnh án", requested: 168_000, recovered: 168_000, result: "Thu hồi" },
  { id: "HS-24Q4-0148", department: "Hồi sức tích cực", service: "Procalcitonin", reason: "Chưa đáp ứng điều kiện thanh toán được mã hóa", gate: "Trước chỉ định", requested: 812_000, recovered: 812_000, result: "Thu hồi" },
  { id: "HS-24Q4-0182", department: "Hô hấp", service: "CT ngực", reason: "Dữ liệu điện tử không khớp bệnh án", gate: "Trước gửi BHXH", requested: 1_080_000, recovered: 0, result: "Đang giải trình" },
  { id: "HS-24Q4-0217", department: "Nội tim mạch", service: "Điện giải đồ", reason: "Áp sai giá dịch vụ", gate: "Trước gửi BHXH", requested: 226_000, recovered: 74_000, result: "Giải trình một phần" },
  { id: "HS-24Q4-0261", department: "Nội tiết", service: "Creatinin máu", reason: "Thiếu lý do làm lại trong cùng đợt", gate: "Trước đóng bệnh án", requested: 82_000, recovered: 41_000, result: "Giải trình một phần" },
];

