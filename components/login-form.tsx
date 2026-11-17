"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, setUser, type User } from "@/lib/api";
import { BrandMark } from "./app-shell";

const accounts = [
  { id: "bs.an", label: "BS. Nguyễn An", role: "Bác sĩ, điều trị 60 người bệnh" },
  { id: "bs.binh", label: "BS. Trần Bình", role: "Bác sĩ, điều trị 21 người bệnh" },
  { id: "admin", label: "Quản trị hệ thống", role: "Audit & chấm tự động" },
];

export function LoginForm() {
  const router = useRouter();
  const [account, setAccount] = useState("bs.an");
  const [password, setPassword] = useState("demo");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");

  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const u = await api<User>("/auth/login", { body: { username: account, password } });
      setUser(u);
      router.push(u.role === "admin" ? "/admin" : "/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không đăng nhập được.");
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="login-card" onSubmit={submit} aria-labelledby="login-title">
        <div className="login-brand"><BrandMark size={32} /><strong>Clinical Copilot</strong></div>
        <h1 id="login-title">Đăng nhập</h1>
        <p className="muted">Khoa Nội chung · Vinmec Times City</p>

        <fieldset className="account-list">
          <legend>Tài khoản demo</legend>
          {accounts.map((a) => (
            <label key={a.id} className={account === a.id ? "on" : ""}>
              <input type="radio" name="account" value={a.id} checked={account === a.id} onChange={() => setAccount(a.id)} />
              <span><strong>{a.label}</strong><small>{a.role}</small></span>
              <span className="mono">{a.id}</span>
            </label>
          ))}
        </fieldset>

        <label className="field">
          <span>Mật khẩu</span>
          <div className="pw">
            <input type={show ? "text" : "password"} value={password} onChange={(e) => { setPassword(e.target.value); setError(""); }} autoComplete="current-password" aria-invalid={!!error} />
            <button type="button" onClick={() => setShow(!show)}>{show ? "Ẩn" : "Hiện"}</button>
          </div>
          {error ? <small className="err" role="alert">{error}</small> : <small>Mật khẩu demo: <span className="mono">demo</span></small>}
        </label>

        <button type="submit" className="btn primary full lg" disabled={busy}>{busy ? "Đang đăng nhập…" : "Đăng nhập"}</button>
      </form>
      <p className="login-foot">Môi trường thử nghiệm với dữ liệu giả lập. AI không chẩn đoán, không ra y lệnh và không ghi vào EMR.</p>
    </main>
  );
}
