"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Eye, EyeOff, HeartPulse, LockKeyhole, ShieldCheck, UserRound } from "lucide-react";

export function LoginForm() {
  const [showPassword, setShowPassword] = useState(false);
  const [account, setAccount] = useState("doctor");
  const destination = account === "admin" ? "/admin" : "/";

  return (
    <main className="login-shell">
      <section className="login-brand" aria-labelledby="login-brand-title">
        <Link className="brand brand-on-dark" href="/" aria-label="Internal Medicine AI Clinical Copilot - Trang chủ">
          <span className="brand-mark"><HeartPulse aria-hidden="true" /></span>
          <span className="brand-name">Internal Medicine <b>AI Clinical Copilot</b></span>
        </Link>
        <div className="login-brand-copy">
          <span className="eyebrow light">Nền tảng AI cho Khoa Nội chung</span>
          <h1 id="login-brand-title">Internal Medicine AI Clinical Copilot</h1>
          <p>Hai module hỗ trợ tóm tắt hồ sơ đa nguồn và soạn nháp bệnh án từ transcript — trong khi bác sĩ luôn giữ quyền kiểm soát và chịu trách nhiệm nội dung.</p>
        </div>
        <div className="security-note">
          <ShieldCheck aria-hidden="true" />
          <div><strong>Mọi dòng đều có thể truy về nguồn</strong><span>AI không chẩn đoán, không ra y lệnh và không ghi vào EMR.</span></div>
        </div>
      </section>

      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-card">
          <div className="mobile-login-logo">
            <span className="brand-mark"><HeartPulse aria-hidden="true" /></span>
          </div>
          <span className="eyebrow">Dành cho nhân viên y tế</span>
          <h2 id="login-title">Đăng nhập không gian Khoa Nội chung</h2>
          <p className="muted">Chọn tài khoản demo để mở đúng không gian theo vai trò.</p>
          <form onSubmit={(event) => event.preventDefault()}>
            <label htmlFor="account">Tài khoản demo</label>
            <div className="login-select-field"><UserRound aria-hidden="true" /><select id="account" value={account} onChange={(event) => setAccount(event.target.value)}><option value="doctor">BS. Nguyễn An — bác sĩ điều trị</option><option value="other-doctor">BS. Trần Bình — bác sĩ trực</option><option value="admin">Quản trị hệ thống</option><option value="nurse" disabled>Điều dưỡng tiếp nhận — dự kiến</option></select></div>
            <label htmlFor="password">Mật khẩu</label>
            <div className="password-field">
              <LockKeyhole aria-hidden="true" />
              <input id="password" type={showPassword ? "text" : "password"} autoComplete="current-password" defaultValue="demopassword" />
              <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}>
                {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
              </button>
            </div>
            <div className="form-row">
              <label className="check-label"><input type="checkbox" defaultChecked /> Ghi nhớ đăng nhập</label>
              <a href="#">Quên mật khẩu?</a>
            </div>
            <Link className="button primary wide" href={destination}>Đăng nhập <ArrowRight aria-hidden="true" /></Link>
          </form>
          <p className="login-disclaimer">Đây là môi trường demo sử dụng dữ liệu mô phỏng, không chứa PHI thực.</p>
        </div>
      </section>
    </main>
  );
}
