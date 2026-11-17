"""API STT: kiểm tra phân quyền, ràng buộc ca và metadata mà không tải model thật."""
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.modules import stt


client = TestClient(app)
AN = {"Authorization": "Bearer demo-bs-an"}
BINH = {"Authorization": "Bearer demo-bs-binh"}


def _fake_result(*_args, **kwargs):
    return stt.TranscriptionResult(
        engine="faster-whisper", model="test-model", device="cpu/int8",
        case_id=kwargs["case_id"], speaker=kwargs["speaker"],
        text="Bệnh nhân khó thở, troponin negative.", detected_language="vi",
        language_probability=0.92, expected_languages=["vi", "en"],
        duration=3.2, duration_after_vad=2.8,
        segments=[stt.SegmentResult(
            start=0, end=2.8, text="Bệnh nhân khó thở, troponin negative.",
            avg_logprob=-0.2, no_speech_prob=0.03,
            words=[stt.WordResult(start=0, end=0.5, text="Bệnh nhân", probability=0.91)],
        )],
        warnings=[], needs_review=False,
    )


def _post(headers=None, case_id="handoff-test"):
    return client.post(
        "/api/stt/transcribe", headers=headers or {},
        files={"audio": ("turn.webm", b"fake-audio", "audio/webm")},
        data={"case_id": case_id, "speaker": "BG", "context": "Khoa Nội", "hotwords": "troponin"},
    )


def test_stt_requires_login(monkeypatch):
    monkeypatch.setattr(stt, "transcribe_bytes", _fake_result)
    assert _post().status_code == 401


def test_stt_preserves_case_and_speaker(monkeypatch):
    monkeypatch.setattr(stt, "transcribe_bytes", _fake_result)
    response = _post(AN)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["case_id"] == "handoff-test" and body["speaker"] == "BG"
    assert body["expected_languages"] == ["vi", "en"]
    assert body["audio_retained"] is False


def test_known_patient_obeys_assignment(monkeypatch):
    monkeypatch.setattr(stt, "transcribe_bytes", _fake_result)
    assert _post(BINH, "p001").status_code == 403
    assert _post(AN, "p001").status_code == 200


def test_empty_audio_is_rejected(monkeypatch):
    monkeypatch.setattr(stt, "transcribe_bytes", stt.transcribe_bytes)
    response = client.post(
        "/api/stt/transcribe", headers=AN,
        files={"audio": ("empty.webm", b"", "audio/webm")},
        data={"case_id": "handoff-empty", "speaker": "BG"},
    )
    assert response.status_code == 422


def test_lazy_cuda_error_falls_back_to_cpu(monkeypatch):
    """CTranslate2 có thể chỉ báo thiếu cublas khi bắt đầu iterate segment, không phải lúc load model."""
    class CudaModel:
        def transcribe(self, *_args, **_kwargs):
            def broken():
                raise RuntimeError("cublas64_12.dll is not found")
                yield  # pragma: no cover
            return broken(), SimpleNamespace(language="vi", language_probability=1, duration=1, duration_after_vad=1)

    class CpuModel:
        def transcribe(self, *_args, **_kwargs):
            word = SimpleNamespace(start=0, end=0.5, word=" xin chào", probability=0.99)
            segment = SimpleNamespace(start=0, end=0.5, text="Xin chào", avg_logprob=-0.1, no_speech_prob=0, words=[word])
            info = SimpleNamespace(language="vi", language_probability=0.99, duration=1, duration_after_vad=0.5)
            return iter([segment]), info

    monkeypatch.setattr(stt, "_get_model", lambda: CudaModel())
    monkeypatch.setattr(stt, "_model_device", "cuda/float16")

    def cpu():
        monkeypatch.setattr(stt, "_model_device", "cpu/int8 (CUDA fallback)")
        return CpuModel()

    monkeypatch.setattr(stt, "_get_cpu_model", cpu)
    result = stt.transcribe_bytes(b"fake", filename="turn.webm", case_id="handoff-cuda", speaker="BG")
    assert result.text == "Xin chào"
    assert result.device == "cpu/int8 (CUDA fallback)"
