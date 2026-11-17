"""Nhận dạng giọng nói đa ngôn ngữ chạy cục bộ bằng faster-whisper.

Âm thanh chỉ tồn tại trong file tạm trong lúc suy luận và bị xóa ngay sau đó.
Mỗi request là một lượt nói độc lập để context của cuộc điện thoại hoặc ca khác
không bị kéo sang lượt tiếp theo.
"""
from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

from pydantic import BaseModel, Field


MODEL_NAME = os.getenv("STT_MODEL", "large-v3-turbo")
REQUEST_LIMIT = int(os.getenv("STT_MAX_BYTES", str(20 * 1024 * 1024)))
DEFAULT_HOTWORDS = (
    "SpO2, HbA1c, CRP, eGFR, troponin, metformin, amlodipin, apixaban, "
    "bisoprolol, losartan, aspirin, penicillin, ceftriaxone, clarithromycin"
)


class WordResult(BaseModel):
    start: float
    end: float
    text: str
    probability: float


class SegmentResult(BaseModel):
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float
    words: list[WordResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    needs_review: bool = False


class TranscriptionResult(BaseModel):
    engine: str
    model: str
    device: str
    case_id: str
    speaker: str
    text: str
    detected_language: str
    language_probability: float
    expected_languages: list[str]
    duration: float
    duration_after_vad: float
    segments: list[SegmentResult]
    warnings: list[str]
    needs_review: bool
    audio_retained: bool = False


_model = None
_model_device = ""
_lock = threading.Lock()


def _device() -> tuple[str, str]:
    requested = os.getenv("STT_DEVICE", "auto").lower()
    if requested in {"cpu", "cuda"}:
        return requested, os.getenv("STT_COMPUTE", "float16" if requested == "cuda" else "int8")
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", os.getenv("STT_COMPUTE", "float16")
    except Exception:
        pass
    return "cpu", os.getenv("STT_COMPUTE", "int8")


def _get_model():
    global _model, _model_device
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        from faster_whisper import WhisperModel

        device, compute = _device()
        try:
            _model = WhisperModel(MODEL_NAME, device=device, compute_type=compute)
            _model_device = f"{device}/{compute}"
        except Exception:
            if device != "cuda":
                raise
            # Driver/CUDA runtime có thể không khớp dù máy có GPU. Vẫn cho demo chạy bằng CPU.
            _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
            _model_device = "cpu/int8 (CUDA fallback)"
        return _model


def _get_cpu_model():
    """Chuyển model sang CPU khi CUDA được phát hiện nhưng thiếu runtime ở lúc suy luận."""
    global _model, _model_device
    from faster_whisper import WhisperModel

    with _lock:
        _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        _model_device = "cpu/int8 (CUDA fallback)"
        return _model


def _segment_warnings(avg_logprob: float, no_speech_prob: float, words: list[WordResult]) -> list[str]:
    warnings: list[str] = []
    if avg_logprob < -0.8:
        warnings.append("Độ tin cậy thấp; cần nghe lại đoạn âm thanh.")
    if no_speech_prob > 0.45:
        warnings.append("Có nhiều khoảng lặng hoặc tạp âm.")
    if words and min(word.probability for word in words) < 0.35:
        warnings.append("Có từ nhận dạng không chắc chắn.")
    return warnings


def _transcribe_file(model, temp_path: str, prompt: str, terms: str):
    """Chạy cả generator trong cùng khối để bắt được lỗi CUDA phát sinh muộn."""
    segments_iter, info = model.transcribe(
        temp_path,
        language=None,
        task="transcribe",
        beam_size=5,
        best_of=5,
        temperature=0.0,
        condition_on_previous_text=False,
        initial_prompt=prompt,
        hotwords=terms,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 250},
        word_timestamps=True,
        multilingual=True,
    )
    out: list[SegmentResult] = []
    for segment in segments_iter:
        words = [WordResult(
            start=round(word.start, 3), end=round(word.end, 3), text=word.word.strip(),
            probability=round(float(word.probability), 4),
        ) for word in (segment.words or []) if word.word.strip()]
        warnings = _segment_warnings(float(segment.avg_logprob), float(segment.no_speech_prob), words)
        text = segment.text.strip()
        if text:
            out.append(SegmentResult(
                start=round(segment.start, 3), end=round(segment.end, 3), text=text,
                avg_logprob=round(float(segment.avg_logprob), 4),
                no_speech_prob=round(float(segment.no_speech_prob), 4),
                words=words, warnings=warnings, needs_review=bool(warnings),
            ))
    return info, out


def transcribe_bytes(
    data: bytes,
    *,
    filename: str,
    case_id: str,
    speaker: str,
    context: str = "",
    hotwords: str = "",
) -> TranscriptionResult:
    if not data:
        raise ValueError("File âm thanh trống")
    if len(data) > REQUEST_LIMIT:
        raise ValueError(f"File âm thanh vượt giới hạn {REQUEST_LIMIT // (1024 * 1024)} MB")

    suffix = Path(filename or "audio.webm").suffix.lower()
    if suffix not in {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mp4"}:
        suffix = ".webm"
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(data)
            temp_path = handle.name

        model = _get_model()
        prompt = (context.strip()[:600] or
                  "Bàn giao và thăm khám tại Khoa Nội chung. Có thể nói xen kẽ tiếng Việt và tiếng Anh.")
        terms = ", ".join(value for value in (DEFAULT_HOTWORDS, hotwords.strip()[:600]) if value)
        try:
            info, out = _transcribe_file(model, temp_path, prompt, terms)
        except Exception:
            if not _model_device.startswith("cuda"):
                raise
            info, out = _transcribe_file(_get_cpu_model(), temp_path, prompt, terms)

        warnings: list[str] = []
        if not out:
            warnings.append("Không phát hiện được lời nói rõ ràng.")
        if float(info.language_probability) < 0.65:
            warnings.append("Không chắc chắn ngôn ngữ; có thể đang nói xen kẽ hoặc âm thanh quá nhiễu.")
        if any(segment.needs_review for segment in out):
            warnings.append("Có đoạn cần người dùng nghe lại trước khi đưa vào hồ sơ.")
        text = " ".join(segment.text for segment in out).strip()
        return TranscriptionResult(
            engine="faster-whisper", model=MODEL_NAME, device=_model_device,
            case_id=case_id, speaker=speaker, text=text,
            detected_language=info.language, language_probability=round(float(info.language_probability), 4),
            expected_languages=["vi", "en"], duration=round(float(info.duration), 3),
            duration_after_vad=round(float(info.duration_after_vad), 3), segments=out,
            warnings=warnings, needs_review=bool(warnings),
        )
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

