"""Cấu hình chung cho test: chạy offline, mọi dữ liệu runtime ghi vào thư mục tạm của hệ điều hành và bị xóa khi xong.

Biến môi trường phải được đặt trước khi import `app`, nên chúng nằm ở đây (pytest nạp conftest trước các file test).
"""
import atexit
import os
import tempfile
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="copilot_test_", ignore_cleanup_errors=True)
atexit.register(_TMP.cleanup)
TMP = Path(_TMP.name)
os.environ["COPILOT_OFFLINE"] = "1"
os.environ["DATABASE_PATH"] = str(TMP / "copilot_test.db")
os.environ["RUNTIME_TRANSCRIPTS"] = str(TMP / "runtime_transcripts")
os.environ["RUNTIME_PATIENTS"] = str(TMP / "runtime_patients")
os.environ.pop("ANTHROPIC_API_KEY", None)
