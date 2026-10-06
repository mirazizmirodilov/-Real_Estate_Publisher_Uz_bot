import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Settings:
    bot_token: str
    channel_id: str
    openai_api_key: str | None
    openai_model: str
    meta_access_token: str | None
    ig_user_id: str | None
    meta_graph_version: str
    allowed_user_ids: set[int]
    auto_publish_seconds: int

def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    channel = os.getenv("CHANNEL_ID", "").strip()
    if not token or not channel:
        raise RuntimeError("BOT_TOKEN and CHANNEL_ID are required")
    ids = {int(x.strip()) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()}
    return Settings(
        bot_token=token,
        channel_id=channel,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-mini"),
        meta_access_token=os.getenv("META_ACCESS_TOKEN") or None,
        ig_user_id=os.getenv("IG_USER_ID") or None,
        meta_graph_version=os.getenv("META_GRAPH_VERSION", "v24.0"),
        allowed_user_ids=ids,
        auto_publish_seconds=int(os.getenv("AUTO_PUBLISH_SECONDS", "8")),
    )
