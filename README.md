# Internal Medicine AI Clinical Copilot

Prototype cho Khoa Nội chung: tóm tắt hồ sơ có trích nguồn (Module 1), nhận dạng bàn giao Việt–Anh và soạn nháp bệnh án từ transcript hoặc giọng nói (Module 2). **Toàn bộ dữ liệu là giả lập.**

```
app/, components/, lib/   Frontend Next.js (giao diện)
backend/app/main.py       API FastAPI
backend/app/modules/      Lớp AI: summary.py (Module 1), note.py (Module 2)
backend/app/modules/stt.py Nhận dạng giọng nói cục bộ bằng faster-whisper
backend/app/core/         Chuẩn hóa tiếng Việt, bộ kiểm chứng, đọc dữ liệu, gọi LLM
backend/app/data/         kb.json (bảng tra), 81 hồ sơ, transcript, đáp án vàng
backend/tests/            Unit test
```

## Chạy trên Windows

Cần Python 3.11+ và Node 20+. Mở **hai** cửa sổ terminal tại thư mục dự án.

**1. Backend (cổng 8000)**

```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Từ lần sau chỉ cần `.venv\Scripts\activate` rồi lệnh `uvicorn`.

**2. Frontend (cổng 3000)**

```
npm install
npm run dev
```

Mở http://localhost:3000 bằng Chrome hoặc Edge (ghi âm cần hai trình duyệt này).

Hoặc chỉ cần bấm đúp `start.bat` ở thư mục gốc. Script sẽ kiểm tra phiên bản, tạo môi trường Python, cài dependency, bật cả hai server và mở trình duyệt. Log nằm trong `logs/`.

## Nhận dạng giọng nói Việt–Anh

- Trình duyệt ghi từng lượt nói bằng `MediaRecorder`; backend nhận dạng cục bộ với `faster-whisper` và VAD để bỏ khoảng lặng.
- Mỗi lượt bắt buộc mang `case_id` và nhãn người nói. Context không được dùng lại giữa hai lượt, tránh kéo nội dung điện thoại hoặc ca trước sang ca sau.
- Có nút **Tạm dừng / điện thoại**, đồng hồ mức âm, cảnh báo nói quá nhỏ và cờ **Cần nghe lại**. Lượt bị gắn cờ phải được người dùng sửa/xác nhận trước khi tạo hồ sơ.
- File âm thanh tạm bị xóa ngay sau suy luận; audit chỉ lưu metadata, không lưu nội dung transcript.

Mặc định dùng `large-v3-turbo` để ưu tiên độ chính xác. Lần nhận dạng đầu tiên sẽ tải khoảng 1,5 GB vào cache người dùng; các lần sau không tải lại. Có thể cấu hình trước khi chạy backend:

```bat
set STT_MODEL=large-v3-turbo
set STT_DEVICE=auto
set STT_COMPUTE=float16
```

Nếu máy không có CUDA phù hợp, hệ thống tự chuyển sang CPU `int8` (chậm hơn). Để chạy thử nhanh trên CPU có thể đặt `set STT_MODEL=small`, nhưng độ chính xác thuật ngữ y khoa sẽ thấp hơn.

## Deploy Vercel

Repository dùng Vercel Services để phục vụ Next.js và FastAPI trong cùng một deployment/domain. Backend được build bằng `backend/Dockerfile`; bản cloud dùng Whisper `small` CPU/int8 để phù hợp giới hạn RAM, trong khi bản local tiếp tục dùng `large-v3-turbo`.

```bash
npx vercel          # preview
npx vercel --prod   # production
```

SQLite và hồ sơ tạo mới trên Vercel hiện nằm trong `/tmp`, nên chỉ phù hợp demo và có thể mất khi instance được thay. Bản production cần đặt Postgres/object storage theo SRS trước khi dùng dữ liệu thật.

## Mở project bằng Claude Code

Claude Code sẽ tự đọc `CLAUDE.md` ở thư mục gốc để biết kiến trúc, quy tắc Next.js và lệnh kiểm thử. Bấm đúp `open-claude.bat`; lần đầu Claude sẽ yêu cầu bạn tự đăng nhập tài khoản Anthropic trong trình duyệt.

## Tài khoản demo (mật khẩu `demo`)

| Tài khoản | Vai trò |
|---|---|
| `bs.an` | Bác sĩ, điều trị 60 người bệnh |
| `bs.binh` | Bác sĩ, điều trị 21 người bệnh còn lại |
| `admin` | Quản trị: audit log và chấm tự động |

Mở người bệnh không do mình điều trị sẽ phải nhập lý do truy cập khẩn cấp.

## Bật LLM (không bắt buộc)

Mặc định hệ thống chạy bằng quy tắc, không gọi LLM. Để dùng LLM cho bước trích xuất, đặt biến môi trường trước khi chạy backend:

```
set ANTHROPIC_API_KEY=...
```

Tắt hẳn bằng `set COPILOT_OFFLINE=1`. Mọi con số và cảnh báo vẫn do code tính, kể cả khi bật LLM.

## Kiểm thử

```
cd backend
python -m pytest -q            # unit test
python -m app.evaluate         # chấm 81 hồ sơ theo đáp án vàng
```

Hồ sơ và đáp án vàng do cùng một bộ sinh tạo ra, nên điểm chấm chỉ cho thấy pipeline chạy ổn định, chưa chứng minh độ chính xác trên ca thật.

## API chính

| Phương thức | Đường dẫn | Việc |
|---|---|---|
| POST | `/api/auth/login` | Đăng nhập |
| POST | `/api/stt/transcribe` | Nhận dạng một lượt nói Việt–Anh, gắn ca/người nói và độ tin cậy |
| GET | `/api/patients` | Danh sách người bệnh |
| GET | `/api/patients/{id}/summary` | Tóm tắt, cảnh báo, xu hướng xét nghiệm |
| GET | `/api/patients/{id}/sources/{ref}` | Bản ghi gốc |
| POST | `/api/patients/{id}/summary/review` | Xác nhận / yêu cầu sửa tóm tắt |
| GET | `/api/patients/{id}/transcripts[/{tid}]` | Transcript |
| POST | `/api/notes/draft` | Soạn nháp từ transcript có sẵn hoặc văn bản mới |
| POST | `/api/notes/{id}/approve` | Ký duyệt |
| GET | `/api/notes/{id}/fhir` | Xuất FHIR |
| GET | `/api/admin/audit`, `/api/admin/eval` | Audit log, chấm tự động |

Tài liệu API tự sinh: http://localhost:8000/docs
