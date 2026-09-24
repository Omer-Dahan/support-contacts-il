from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    api_id: int = Field(..., alias="TELEGRAM_API_ID")
    api_hash: str = Field(..., alias="TELEGRAM_API_HASH")
    bot_token: str = Field(..., alias="BOT_TOKEN")
    db_path: str = Field(
        default="/home/vm/projects/support-contacts-il/data/sherutplus.db",
        alias="DB_PATH",
    )
    users_db_path: str = Field(
        default="/home/vm/projects/support-contacts-il/data/users.db",
        alias="USERS_DB_PATH",
    )
    admin_chat_id: Optional[int] = Field(default=None, alias="ADMIN_CHAT_ID")

    @field_validator("admin_chat_id", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        return None if v == "" else v


settings = Settings()


def is_admin(user_id: Optional[int]) -> bool:
    if settings.admin_chat_id is None or user_id is None:
        return False
    return user_id == settings.admin_chat_id
