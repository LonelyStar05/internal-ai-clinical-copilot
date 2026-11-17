"use client";

import { Languages, Mic, Pause, Play, Square, Trash2, Volume2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiForm, type SttResponse } from "@/lib/api";

export type Speaker = string;
export type RecTurn = {
  id: number;
  speaker: Speaker;
  text: string;
  language?: string;
  confidence?: number;
  needsReview?: boolean;
  warnings?: string[];
  duration?: number;
};
export type SpeakerDef = { key: Speaker; label: string; hint: string };

const DEFAULT_SPEAKERS: SpeakerDef[] = [
  { key: "BS", label: "Bác sĩ", hint: "1" },
  { key: "BN", label: "Người bệnh", hint: "2" },
  { key: "NN", label: "Người nhà", hint: "3" },
];

const mmss = (seconds: number) => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
const errMsg = (error: unknown) => error instanceof Error ? error.message : "Không nhận dạng được đoạn ghi âm.";

function supportedMime() {
  if (typeof MediaRecorder === "undefined") return "";
  return ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"].find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

export function VoiceRecorder({
  turns, setTurns, onDraft, busy = false, speakers = DEFAULT_SPEAKERS,
  actionLabel = "Soạn nháp từ bản ghi", busyLabel = "Đang soạn…",
  unsupportedHint = "hoặc dùng “Dán transcript” ở tab Bệnh án nháp.",
  caseId = "handoff-new", caseLabel = "Ca bàn giao mới", context = "", hotwords = "",
}: {
  turns: RecTurn[];
  setTurns: (fn: (turns: RecTurn[]) => RecTurn[]) => void;
  onDraft: () => void;
  busy?: boolean;
  speakers?: SpeakerDef[];
  actionLabel?: string;
  busyLabel?: string;
  unsupportedHint?: string;
  caseId?: string;
  caseLabel?: string;
  context?: string;
  hotwords?: string;
}) {
  const [supported] = useState(() => typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined");
  const [recording, setRecording] = useState(false);
  const [paused, setPaused] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [speaker, setSpeaker] = useState<Speaker>(speakers[0].key);
  const [error, setError] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [quiet, setQuiet] = useState(false);
  const pausedRef = useRef(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const speakerRef = useRef<Speaker>(speakers[0].key);
  const idRef = useRef(1);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const quietSinceRef = useRef<number | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  function pickSpeaker(value: Speaker) {
    if (recording) return;
    speakerRef.current = value;
    setSpeaker(value);
  }

  function cleanupAudio() {
    if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
    animationRef.current = null;
    analyserRef.current = null;
    audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setLevel(0);
    setQuiet(false);
    quietSinceRef.current = null;
  }

  function watchLevel(stream: MediaStream) {
    const audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.72;
    source.connect(analyser);
    audioContextRef.current = audioContext;
    analyserRef.current = analyser;
    const samples = new Uint8Array(analyser.fftSize);
    let lastPaint = 0;
    const tick = (now: number) => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const value of samples) { const normalized = (value - 128) / 128; sum += normalized * normalized; }
      const rms = Math.sqrt(sum / samples.length);
      const visual = Math.min(1, rms * 7);
      if (now - lastPaint > 90) { setLevel(visual); lastPaint = now; }
      if (!pausedRef.current && rms < 0.018) {
        quietSinceRef.current ??= now;
        if (now - quietSinceRef.current > 1800) setQuiet(true);
      } else {
        quietSinceRef.current = null;
        setQuiet(false);
      }
      animationRef.current = requestAnimationFrame(tick);
    };
    animationRef.current = requestAnimationFrame(tick);
  }

  async function upload(blob: Blob, capturedSpeaker: Speaker) {
    setTranscribing(true);
    setError("");
    try {
      const form = new FormData();
      const extension = blob.type.includes("ogg") ? "ogg" : "webm";
      form.append("audio", blob, `turn-${idRef.current}.${extension}`);
      form.append("case_id", caseId);
      form.append("speaker", capturedSpeaker);
      form.append("context", context);
      form.append("hotwords", hotwords);
      const result = await apiForm<SttResponse>("/stt/transcribe", form);
      if (!result.text.trim()) throw new Error(result.warnings[0] ?? "Không phát hiện được lời nói rõ ràng.");
      const probabilities = result.segments.flatMap((segment) => segment.words.map((word) => word.probability));
      const confidence = probabilities.length ? probabilities.reduce((sum, value) => sum + value, 0) / probabilities.length : result.language_probability;
      const warnings = [...new Set([
        ...result.warnings,
        ...result.segments.flatMap((segment) => segment.warnings),
      ])];
      const id = idRef.current++;
      setTurns((current) => [...current, {
        id, speaker: capturedSpeaker, text: result.text.trim(), language: result.detected_language,
        confidence, needsReview: result.needs_review || warnings.length > 0, warnings,
        duration: result.duration,
      }]);
    } catch (cause) {
      setError(errMsg(cause));
    } finally {
      setTranscribing(false);
    }
  }

  async function start() {
    setError("");
    setSeconds(0);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;
      chunksRef.current = [];
      const mimeType = supportedMime();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType, audioBitsPerSecond: 96_000 } : undefined);
      const capturedSpeaker = speakerRef.current;
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunksRef.current.push(event.data); };
      recorder.onerror = () => setError("Trình duyệt không ghi được âm thanh. Kiểm tra micro rồi thử lại.");
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        cleanupAudio();
        if (blob.size > 1000) void upload(blob, capturedSpeaker);
        else setError("Đoạn ghi âm quá ngắn hoặc không có tín hiệu.");
      };
      recorderRef.current = recorder;
      recorder.start(500);
      watchLevel(stream);
      pausedRef.current = false;
      setPaused(false);
      setRecording(true);
    } catch (cause) {
      cleanupAudio();
      const name = cause instanceof DOMException ? cause.name : "";
      setError(name === "NotAllowedError"
        ? "Chưa được cấp quyền micro. Cho phép micro cho trang này rồi thử lại."
        : name === "NotFoundError" ? "Không tìm thấy micro trên máy." : errMsg(cause));
    }
  }

  function stop() {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    pausedRef.current = false;
    setRecording(false);
    setPaused(false);
  }

  function togglePause() {
    const recorder = recorderRef.current;
    if (!recorder) return;
    if (recorder.state === "recording") { recorder.pause(); pausedRef.current = true; setPaused(true); setQuiet(false); }
    else if (recorder.state === "paused") { recorder.resume(); pausedRef.current = false; setPaused(false); }
  }

  useEffect(() => {
    if (!recording || paused) return;
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [recording, paused]);

  useEffect(() => () => {
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
    audioContextRef.current?.close().catch(() => undefined);
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const element = event.target as HTMLElement | null;
      if (element && (element.tagName === "INPUT" || element.tagName === "TEXTAREA")) return;
      const hit = speakers.find((item) => item.hint === event.key);
      if (hit && !recording) {
        speakerRef.current = hit.key;
        setSpeaker(hit.key);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [speakers, recording]);

  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest" }); }, [turns.length, transcribing]);

  const cycle = (value: Speaker): Speaker => speakers[(speakers.findIndex((item) => item.key === value) + 1) % speakers.length].key;
  const label = (value: Speaker) => speakers.find((item) => item.key === value)?.label ?? value;
  const pendingReview = turns.filter((turn) => turn.needsReview).length;

  return (
    <div className="recorder" aria-busy={transcribing}>
      <div className="recording-context" role="note">
        <span><strong>Ca đang ghi:</strong> {caseLabel}</span>
        <span className="tag"><Languages aria-hidden="true" />Tiếng Việt + English</span>
        <span className="mono">{caseId}</span>
      </div>

      {!supported ? (
        <p className="banner warn"><span><strong>Trình duyệt này không hỗ trợ ghi âm.</strong> Mở bằng Chrome hoặc Edge, {unsupportedHint}</span></p>
      ) : (
        <div className="rec-bar">
          <button type="button" className={`mic ${recording ? "on" : ""}`} onClick={recording ? stop : start} disabled={transcribing} aria-pressed={recording}>
            {recording ? <Square aria-hidden="true" /> : <Mic aria-hidden="true" />}
            <span>{recording ? "Dừng và nhận dạng" : transcribing ? "Đang nhận dạng…" : turns.length ? "Ghi lượt tiếp" : "Bắt đầu ghi"}</span>
          </button>
          {recording && (
            <button type="button" className={`btn ${paused ? "primary" : ""}`} onClick={togglePause}>
              {paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}{paused ? "Tiếp tục" : "Tạm dừng / điện thoại"}
            </button>
          )}
          <span className={`rec-time ${recording && !paused ? "on" : ""}`} aria-live="off">{recording && !paused && <i aria-hidden="true" />}{mmss(seconds)}</span>
          <div className="mic-level" aria-label={`Mức âm lượng ${Math.round(level * 100)} phần trăm`}>
            <Volume2 aria-hidden="true" /><i><b style={{ width: `${Math.max(2, level * 100)}%` }} /></i>
            <span>{paused ? "Đã tạm dừng" : quiet && recording ? "Âm quá nhỏ" : recording ? "Đang nghe" : "Micro"}</span>
          </div>
          <div className="who" role="radiogroup" aria-label="Người đang nói">
            <span>Đang nói:</span>
            {speakers.map((item) => (
              <button type="button" key={item.key} role="radio" aria-checked={speaker === item.key} disabled={recording}
                className={`${item.key.toLowerCase()} ${speaker === item.key ? "on" : ""}`} onClick={() => pickSpeaker(item.key)}>
                {item.label}<kbd>{item.hint}</kbd>
              </button>
            ))}
          </div>
        </div>
      )}
      {paused && <p className="banner warn flat"><span><strong>Đang tạm dừng.</strong> Âm thanh cuộc điện thoại hoặc hội thoại ngoài lề không được ghi vào ca này.</span></p>}
      {quiet && recording && !paused && <p className="rec-error" role="status">Âm lượng quá nhỏ. Đưa micro gần người nói hơn hoặc kiểm tra thiết bị đầu vào.</p>}
      {error && <p className="rec-error" role="alert">{error}</p>}

      {turns.length === 0 && !transcribing ? (
        <div className="empty"><strong>Chưa có lượt nói nào</strong><span>Chọn đúng người nói, ghi một lượt rồi bấm “Dừng và nhận dạng”. Khi có điện thoại, bấm “Tạm dừng”.</span></div>
      ) : (
        <ol className="turns rec-turns">
          {turns.map((turn, index) => (
            <li key={turn.id} className={turn.needsReview ? "needs-review" : ""}>
              <span className="turn-no">L{index + 1}</span>
              <div>
                <button type="button" className={`spk ${turn.speaker.toLowerCase()}`} title="Bấm để đổi người nói"
                  onClick={() => setTurns((all) => all.map((item) => item.id === turn.id ? { ...item, speaker: cycle(item.speaker) } : item))}>{label(turn.speaker)}</button>
                <textarea value={turn.text} rows={Math.max(1, Math.ceil(turn.text.length / 80))} aria-label={`Nội dung lượt L${index + 1}`}
                  onChange={(event) => setTurns((all) => all.map((item) => item.id === turn.id ? { ...item, text: event.target.value } : item))} />
                <div className="rec-quality">
                  <span>{turn.language === "vi" ? "Tiếng Việt" : turn.language === "en" ? "English" : turn.language ?? "Đa ngôn ngữ"}</span>
                  {typeof turn.confidence === "number" && <span>Độ tin cậy {Math.round(turn.confidence * 100)}%</span>}
                  {turn.duration && <span>{turn.duration.toFixed(1)} giây</span>}
                  {turn.needsReview && <span className="tag warn">Cần nghe lại</span>}
                  {turn.needsReview && (
                    <button type="button" className="btn compact" onClick={() => setTurns((all) => all.map((item) => item.id === turn.id
                      ? { ...item, needsReview: false, warnings: [] } : item))}>Đã kiểm tra</button>
                  )}
                </div>
                {turn.warnings?.map((warning) => <small className="err block" key={warning}>{warning}</small>)}
              </div>
              <button type="button" className="icon-btn" aria-label={`Xóa lượt L${index + 1}`}
                onClick={() => setTurns((all) => all.filter((item) => item.id !== turn.id))}><Trash2 aria-hidden="true" /></button>
            </li>
          ))}
          {transcribing && <li className="live" role="status" aria-live="polite"><span className="turn-no">…</span><div><strong>Đang nhận dạng cục bộ</strong><p>Đang tách tiếng nói và kiểm tra độ tin cậy…</p></div></li>}
        </ol>
      )}
      <div ref={endRef} />

      <footer className="review-bar">
        <p className="muted small">Âm thanh được xử lý cục bộ và xóa ngay sau khi nhận dạng. {pendingReview > 0 ? `Còn ${pendingReview} lượt phải nghe lại và xác nhận.` : "Các lượt ghi đã sẵn sàng để tạo bản nháp."}</p>
        <div className="review-actions">
          <button type="button" className="btn" disabled={turns.length === 0 || recording || transcribing} onClick={() => { setTurns(() => []); setSeconds(0); }}>Xóa hết</button>
          <button type="button" className="btn primary" disabled={turns.length === 0 || pendingReview > 0 || recording || transcribing || busy} onClick={onDraft}>{busy ? busyLabel : pendingReview > 0 ? `Xác nhận ${pendingReview} lượt trước` : actionLabel}</button>
        </div>
      </footer>
    </div>
  );
}
