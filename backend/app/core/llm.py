"""LLM là tùy chọn. Không có ANTHROPIC_API_KEY thì hệ thống chạy chế độ offline (rule-based),
mọi kiểm chứng và cờ an toàn vẫn hoạt động y như nhau vì chúng không phụ thuộc LLM."""
from __future__ import annotations

import json
import os
import re

MODEL = os.getenv("COPILOT_MODEL", "claude-sonnet-5-5")


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY")) and os.getenv("COPILOT_OFFLINE") != "1"


def complete_json(system: str, user: str, max_tokens: int = 4000):
    """Gọi LLM và trả về JSON đã parse; lỗi thì trả None để pipeline rơi về chế độ offline."""
    if not available():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        m = re.search(r"\{.*\}|\[.*\]", text, flags=re.S)
        return json.loads(m.group(0)) if m else None
    except Exception as exc:  # mạng, khóa sai, JSON hỏng... -> offline
        print(f"[llm] fallback offline: {exc}")
        return None
