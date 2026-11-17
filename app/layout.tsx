import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./globals.css";

const inter = Inter({
  subsets: ["latin", "vietnamese"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Internal Medicine AI Clinical Copilot — Khoa Nội chung",
  description: "Ứng dụng hỗ trợ tóm tắt hồ sơ đa nguồn và soạn nháp bệnh án từ transcript với trích nguồn và HITL.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="vi" className={inter.variable}>
      <body>{children}</body>
    </html>
  );
}
