"use client";

import Link from "next/link";
import { Activity, ClipboardList, HeartPulse, LogOut, UsersRound } from "lucide-react";
import type { ReactNode } from "react";
import { setUser, type User } from "@/lib/api";

export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <span className="brand-mark" style={{ width: size, height: size }} aria-hidden="true">
      <HeartPulse />
    </span>
  );
}

type QuickPatient = { id: string; name: string; bed: string };

export function AppShell({
  user,
  active,
  children,
  quickPatients = [],
  currentPatientId,
  onQuickOpen,
  onNavPatients,
}: {
  user: User;
  active: "patients" | "admin" | "assignments";
  children: ReactNode;
  quickPatients?: QuickPatient[];
  currentPatientId?: string;
  onQuickOpen?: (id: string) => void;
  onNavPatients?: () => void;
}) {
  const role = user.role;
  const display = user.name.replace(/\s*\(.*\)$/, "");
  const initials = display.replace(/^BS\.\s*/, "").split(" ").slice(-2).map((w) => w[0]).join("").toUpperCase();
  const roleLabel = role === "doctor" ? "Bác sĩ" : "Quản trị · không mở bệnh án";

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Chuyển đến nội dung chính</a>
      <aside className="sidebar" aria-label="Điều hướng">
        <div className="sidebar-brand">
          <BrandMark />
          <div>
            <strong>Clinical Copilot</strong>
            <span>Khoa Nội chung</span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {role === "doctor" ? (
            <button type="button" className={active === "patients" ? "active" : ""} onClick={onNavPatients}>
              <UsersRound aria-hidden="true" />
              <span>Người bệnh</span>
            </button>
          ) : (
            <>
              <Link href="/admin/assignments" className={active === "assignments" ? "active" : ""}>
                <ClipboardList aria-hidden="true" />
                <span>Phân công bệnh nhân</span>
              </Link>
              <Link href="/admin" className={active === "admin" ? "active" : ""}>
                <Activity aria-hidden="true" />
                <span>Chất lượng & audit</span>
              </Link>
            </>
          )}
        </nav>

        {quickPatients.length > 0 && (
          <div className="sidebar-section">
            <span className="sidebar-label">Đang điều trị</span>
            <ul>
              {quickPatients.map((p) => (
                <li key={p.id}>
                  <button
                    type="button"
                    className={currentPatientId === p.id ? "active" : ""}
                    onClick={() => onQuickOpen?.(p.id)}
                  >
                    <span className="qp-name">{p.name}</span>
                    <span className="qp-bed">{p.bed}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="sidebar-foot">
          <p className="env-note"><span className="dot" aria-hidden="true" />Dữ liệu giả lập</p>
          <div className="user-row">
            <span className="avatar">{initials}</span>
            <div>
              <strong>{display}</strong>
              <span>{roleLabel}</span>
            </div>
            <Link href="/login" className="icon-btn" aria-label="Đăng xuất" title="Đăng xuất" onClick={() => setUser(null)}>
              <LogOut aria-hidden="true" />
            </Link>
          </div>
        </div>
      </aside>
      <main id="main" className="main">{children}</main>
    </div>
  );
}
