"use client";

import { useMemo, useSyncExternalStore } from "react";

export type User = { token: string; username: string; role: "doctor" | "admin"; name: string };
export type Citation = { ref: string; quote: string | null };
export type Line = { text: string; citations: Citation[]; kind: "fact" | "missing" | "info" | "suggestion" };
export type Section = { key: string; title: string; lines: Line[] };
export type Flag = { id: string; kind: string; severity: "đỏ" | "cao" | "trung bình" | "thông tin"; title: string; detail: string; citations: Citation[] };
export type Trend = { analyte: string; display: string; unit: string; points: { date: string; value: number; ref: string }[]; direction: "tăng" | "giảm" | "ổn định"; abnormal_latest: boolean };
export type ActiveMed = { ingredient: string; display: string; entries: { drug_name: string; dose: string; practitioner: string; date: string; ref: string }[] };
export type Summary = { mode: string; sections: Section[]; flags: Flag[]; trends: Trend[]; active_meds: ActiveMed[]; narrative: Line[]; dropped: { text?: string; reason?: string }[]; disclaimer: string };
export type AssignmentStatus = "unassigned" | "pending" | "accepted";
export type PatientRow = { id: string; ward: string; bed: string; is_mine: boolean; name?: string; birth_year?: number; gender?: string; reason?: string; assignment_status?: AssignmentStatus; assigned_at?: string | null; is_new?: boolean };
export type Patient = { id: string; name: string; birth_year: number; gender: string; bed: string; attending: string | null; admission?: { admitted_at?: string; ward_at?: string; reason?: string } };
export type Review = { reviewed_by: string; reviewed_at: string; decision: string; comment: string } | null;
export type AssignmentView = { doctor: string | null; status: AssignmentStatus; status_label: string; assigned_by: string | null; assigned_at: string | null; accepted_by: string | null; accepted_at: string | null; note: string | null; version: number };
export type SummaryResponse = { patient: Patient; summary: Summary; last_review: Review; assignment: AssignmentView; can_write: boolean };

/* ---------- Kiểm tra rủi ro thanh toán BHYT trước chỉ định ---------- */
export type CoverageRisk = "low" | "medium" | "high" | "unknown";
export type CoverageService = { code: string; display: string; group: string; short_rule: string };
export type CoverageCriterion = { label: string; status: "met" | "not_met" | "missing" | "info"; value: string; source_ref: string | null };
export type CoverageBasis = { title: string; detail: string; url: string; kind: "official" | "demo" };
export type CoverageResult = {
  service: CoverageService; risk_level: CoverageRisk; risk_label: string; verdict: string;
  clinical_status: "eligible" | "not_eligible" | "insufficient" | "no_special_condition";
  duplicate_status: "clear" | "recent" | "unknown"; admin_status: "unknown";
  criteria: CoverageCriterion[]; recent_tests: { date: string; value: string; source_ref: string }[];
  missing_data: string[]; basis: CoverageBasis[];
};
export type CoverageResponse = {
  patient_id: string; as_of: string; results: CoverageResult[]; counts: Record<CoverageRisk, number>;
  limitations: string[]; disclaimer: string;
};

/* ---------- Tiếp nhận bàn giao (POST /handoffs/parse, /handoffs/confirm) ---------- */
export type FieldStatus = "ok" | "uncertain" | "conflict" | "missing";
export type FieldDraft = { value: string | null; turns: number[]; status: FieldStatus; notes: string[]; alternatives: { value: string; turns: number[] }[] };
export type ItemDraft = { text: string; turns: number[]; status: FieldStatus; notes: string[] };
export type HandoffFieldKey = "name" | "birth_year" | "gender" | "ward" | "room" | "bed" | "attending_spoken" | "admitted_date" | "admitted_time" | "reason" | "pulse" | "temp" | "bp" | "resp_rate" | "spo2" | "weight";
export type HandoffListKey = "diagnoses" | "comorbidities" | "allergies" | "meds" | "labs" | "pending";
export type HandoffDraft = {
  mode: "llm" | "offline"; turns: Turn[]; fields: Record<HandoffFieldKey, FieldDraft>; lists: Record<HandoffListKey, ItemDraft[]>;
  allergy_status: FieldDraft; required: HandoffFieldKey[]; missing_required: HandoffFieldKey[]; flag_count: number;
  dropped: { field: string; value: string; source: string; reason: string }[]; warnings: string[]; labels: Record<string, string>; disclaimer: string;
};
export type HandoffConfirmResponse = { patient_id: string; transcript_id: string; assignment: AssignmentView };

/* ---------- Phân công (GET/POST /admin/assignments...) ---------- */
export type AssignmentRow = AssignmentView & { id: string; name: string; ward: string; bed: string; reason: string | null; origin: string; doctor_name: string | null };
export type DoctorInfo = { username: string; name: string; active: number; pending: number };
export type AssignmentList = { patients: AssignmentRow[]; doctors: DoctorInfo[]; wards: string[]; statuses: Record<AssignmentStatus, string> };
export type AssignmentHistory = { id: number; patient_id: string; ts: string; action: string; action_label: string; from_doctor: string | null; to_doctor: string | null; by_user: string; by_role: string; reason: string | null; version: number };
export type Turn = { n: number; speaker: string; text: string; norm?: string };
export type Draft = { transcript_id: string; mode: string; sections: Section[]; flags: Flag[]; missing: { id: string; label: string }[]; icd_suggestions: { code: string; display: string; role: string; from: string }[]; dropped: { text?: string; reason?: string }[]; normalized_turns: Turn[] };
export type DraftResponse = { note_id: string; draft: Draft; text: string };
export type EditStats = { sections: Record<string, { ai_lines: number; removed: number; added: number }>; ai_lines_kept_ratio: number; unified: string[] };
/** GET /patients/{id}/notes: bệnh án đã lưu (diff_json là chuỗi JSON của EditStats). */
export type NoteMeta = { id: string; transcript_id: string; created_by: string; created_at: string; status: "draft" | "approved"; approved_by: string | null; approved_at: string | null; diff_json: string | null };
/** GET /notes/{id}: bản ghi đầy đủ; ai_json là chuỗi JSON của Draft. */
export type NoteRecord = NoteMeta & { patient_id: string; ai_json: string; ai_text: string; final_text: string | null };
export type AuditEntry = { id: number; ts: string; username: string; role: string; action: string; patient_id: string | null; detail: string };
export type SttWord = { start: number; end: number; text: string; probability: number };
export type SttSegment = { start: number; end: number; text: string; avg_logprob: number; no_speech_prob: number; words: SttWord[]; warnings: string[]; needs_review: boolean };
export type SttResponse = {
  engine: string; model: string; device: string; case_id: string; speaker: string; text: string;
  detected_language: string; language_probability: number; expected_languages: string[];
  duration: number; duration_after_vad: number; segments: SttSegment[]; warnings: string[];
  needs_review: boolean; audio_retained: boolean;
};
type Counts = Record<string, { found: number; total: number }>;
export type EvalReport = {
  n_records: number; mode: string; errors: unknown[]; forbidden_found: number; dropped_by_verifier: number; failures: unknown[];
  module1: { flag_recall: number; flag_precision: number; fact_recall: number; uncited_lines: number; flag_recall_by_kind: Counts };
  module2: { fact_recall: number; fact_precision: number; missing_recall: number; missing_precision: number; flag_recall: number; flag_precision: number; flag_recall_by_kind: Counts };
};

const KEY = "cc_user";
const listeners = new Set<() => void>();
const subscribe = (cb: () => void) => { listeners.add(cb); window.addEventListener("storage", cb); return () => { listeners.delete(cb); window.removeEventListener("storage", cb); }; };
const read = () => { try { return window.localStorage.getItem(KEY); } catch { return null; } };

export function setUser(u: User | null) {
  try { if (u) window.localStorage.setItem(KEY, JSON.stringify(u)); else window.localStorage.removeItem(KEY); } catch { /* bỏ qua */ }
  listeners.forEach((l) => l());
}

/** undefined = chưa đọc được (đang render phía server), null = chưa đăng nhập. */
export function useUser(): User | null | undefined {
  const raw = useSyncExternalStore(subscribe, read, () => undefined as unknown as string | null);
  return useMemo(() => { if (raw === undefined) return undefined; try { return raw ? (JSON.parse(raw) as User) : null; } catch { return null; } }, [raw]);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const raw = read();
  const token = raw ? (JSON.parse(raw) as User).token : "";
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: opts.method ?? (opts.body ? "POST" : "GET"),
      headers: { ...(opts.body ? { "content-type": "application/json" } : {}), ...(token ? { authorization: `Bearer ${token}` } : {}) },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Không kết nối được backend. Kiểm tra backend đã chạy ở cổng 8000 chưa.");
  }
  if (!res.ok) {
    let msg = `Lỗi ${res.status}`;
    try { const j = await res.json(); if (typeof j.detail === "string") msg = j.detail; } catch { if (res.status >= 500) msg = "Không kết nối được backend. Kiểm tra backend đã chạy ở cổng 8000 chưa."; }
    if (res.status === 401 && !path.startsWith("/auth/")) setUser(null);
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export async function apiForm<T>(path: string, body: FormData): Promise<T> {
  const raw = read();
  const token = raw ? (JSON.parse(raw) as User).token : "";
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method: "POST",
      headers: token ? { authorization: `Bearer ${token}` } : {},
      body,
    });
  } catch {
    throw new ApiError(0, "Không kết nối được backend nhận dạng giọng nói.");
  }
  if (!res.ok) {
    let msg = `Lỗi ${res.status}`;
    try { const json = await res.json(); if (typeof json.detail === "string") msg = json.detail; } catch { /* giữ thông báo mặc định */ }
    throw new ApiError(res.status, msg);
  }
  return (await res.json()) as T;
}

export const fmtDate = (iso?: string | null) => {
  if (!iso) return "";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
  return m ? `${m[3]}/${m[2]}/${m[1]}${m[4] ? `, ${m[4]}:${m[5]}` : ""}` : iso;
};
export const fmtNum = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");
