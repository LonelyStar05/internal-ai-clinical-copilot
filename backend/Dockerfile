FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Vercel Hobby có 2 GB RAM: dùng model small/int8 cho bản cloud.
# Bản chạy Windows trực tiếp vẫn mặc định large-v3-turbo trong app/modules/stt.py.
ARG STT_MODEL=small
ENV STT_MODEL=${STT_MODEL} \
    STT_DEVICE=cpu \
    STT_COMPUTE=int8 \
    HF_HOME=/opt/huggingface \
    HF_HUB_DISABLE_XET=1 \
    DATABASE_PATH=/tmp/clinical-copilot/runtime.db \
    RUNTIME_TRANSCRIPTS=/tmp/clinical-copilot/transcripts \
    RUNTIME_PATIENTS=/tmp/clinical-copilot/patients
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${STT_MODEL}', device='cpu', compute_type='int8')"

COPY app ./app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
