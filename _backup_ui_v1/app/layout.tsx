import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Internal Medicine AI Clinical Copilot — Khoa Nội chung",
  description: "Ứng dụng hỗ trợ tóm tắt hồ sơ đa nguồn và soạn nháp bệnh án từ transcript với trích nguồn và HITL.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
