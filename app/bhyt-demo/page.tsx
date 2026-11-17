import type { Metadata } from "next";
import { BhytRiskDemo } from "./_components/bhyt-risk-demo";

export const metadata: Metadata = {
  title: "Demo kiểm soát rủi ro BHYT",
  description: "Dữ liệu giả lập minh họa kiểm tra rủi ro trước chỉ định, trước đóng bệnh án và trước gửi BHXH.",
};

export default function BhytDemoPage() {
  return <BhytRiskDemo />;
}

