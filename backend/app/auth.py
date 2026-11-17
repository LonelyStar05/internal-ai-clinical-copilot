"""Đăng nhập demo, phân quyền theo vai trò và theo bác sĩ điều trị.

Prototype dùng tài khoản demo + token cố định. Bản triển khai thay bằng SSO của bệnh viện.
"""
from __future__ import annotations

import os

from fastapi import Depends, Header, HTTPException

from . import assignments

# Tên hiển thị không còn ghi "(điều trị)": ai điều trị người bệnh nào giờ do bảng phân công quyết định.
USERS = {
    "bs.an":   {"password": "demo", "role": "doctor", "name": "BS. Nguyễn An", "token": "demo-bs-an"},
    "bs.binh": {"password": "demo", "role": "doctor", "name": "BS. Trần Bình", "token": "demo-bs-binh"},
    "admin":   {"password": "demo", "role": "admin",  "name": "Quản trị hệ thống", "token": "demo-admin"},
}
TOKENS = {u["token"]: {"username": k, **u} for k, u in USERS.items()}
if os.getenv("COPILOT_DEMO_TOKENS") == "0":  # tắt tài khoản demo khi triển khai thật
    TOKENS = {}


def login(username: str, password: str) -> dict:
    u = USERS.get(username)
    if not u or u["password"] != password:
        raise HTTPException(401, "Sai tài khoản hoặc mật khẩu")
    return {"token": u["token"], "username": username, "role": u["role"], "name": u["name"]}


def current_user(authorization: str = Header(default="")) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    u = TOKENS.get(token)
    if not u:
        raise HTTPException(401, "Chưa đăng nhập")
    return u


def require_doctor(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "doctor":
        raise HTTPException(403, "Chỉ bác sĩ được xem dữ liệu người bệnh")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Chỉ quản trị")
    return user


def require_staff(user: dict = Depends(current_user)) -> dict:
    """Bác sĩ hoặc quản trị (luồng tiếp nhận bàn giao)."""
    if user["role"] not in ("doctor", "admin"):
        raise HTTPException(403, "Không có quyền")
    return user


def _assignment(pid: str) -> dict:
    try:
        return assignments.current(pid)
    except assignments.AssignError as e:
        raise HTTPException(e.status, str(e)) from None


def can_access(user: dict, pid: str, emergency_reason: str | None = None) -> tuple[bool, bool]:
    """(được phép, là truy cập khẩn cấp). Bác sĩ đang được phân công luôn được đọc (kể cả khi chưa bấm tiếp nhận);
    bác sĩ khác, kể cả bác sĩ cũ đã bị chuyển hồ sơ, cần lý do khẩn cấp (break-the-glass)."""
    if _assignment(pid)["doctor"] == user["username"]:
        return True, False
    if emergency_reason and len(emergency_reason.strip()) >= 10:
        return True, True
    return False, False


def write_block_reason(user: dict, pid: str) -> str | None:
    """None nếu được ghi. Chỉ bác sĩ đang phụ trách VÀ đã tiếp nhận hồ sơ mới được ghi.
    Truy cập khẩn cấp luôn chỉ đọc; bác sĩ cũ mất quyền ghi ngay khi hồ sơ được chuyển."""
    a = _assignment(pid)
    if a["doctor"] != user["username"]:
        return "Chỉ bác sĩ điều trị được thực hiện thao tác này. Truy cập khẩn cấp chỉ cho xem."
    if a["status"] != "accepted":
        return "Hồ sơ mới được phân công cho bạn. Bấm “Tiếp nhận hồ sơ” trước khi thao tác ghi."
    return None


def can_write(user: dict, pid: str) -> bool:
    return write_block_reason(user, pid) is None
