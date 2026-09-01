from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class UserSession:
    """מצב חיפוש/ניווט נוכחי של משתמש בודד, בזיכרון בלבד (לא נשמר בין הפעלות)."""

    results: list[dict[str, Any]] = field(default_factory=list)
    page: int = 0
    origin_label: str = ""
    category: Optional[str] = None
    last_query: Optional[str] = None
    awaiting_export_query: bool = False


user_states: dict[int, UserSession] = {}


def get_session(chat_id: int) -> UserSession:
    if chat_id not in user_states:
        user_states[chat_id] = UserSession()
    return user_states[chat_id]
