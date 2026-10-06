import asyncio
import logging
import os
import time

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, Update

from .config import get_settings
from .models import Listing
from .ai_parser import parse_listing
from .telegram_publisher import TelegramPublisher
from .instagram_publisher import InstagramPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

settings = get_settings()
bot = Bot(settings.bot_token)
dp = Dispatcher()
tg_pub = TelegramPublisher(bot, settings.channel_id)
ig_pub = (
    InstagramPublisher(
        settings.meta_access_token,
        settings.ig_user_id,
        settings.meta_graph_version,
        settings.bot_token,
    )
    if settings.meta_access_token and settings.ig_user_id
    else None
)

# In-memory sessions. The bot is designed for one/few operators; Render may restart
# a free instance, so an external DB can be added later if persistent drafts are needed.
pending: dict[int, Listing] = {}
last_activity: dict[int, float] = {}
publish_tasks: dict[int, asyncio.Task] = {}
session_locks: dict[int, asyncio.Lock] = {}


def allowed(uid: int) -> bool:
    return not settings.allowed_user_ids or uid in settings.allowed_user_ids


def get_lock(uid: int) -> asyncio.Lock:
    if uid not in session_locks:
        session_locks[uid] = asyncio.Lock()
    return session_locks[uid]


def touch(uid: int, delay: float | None = None) -> None:
    last_activity[uid] = time.monotonic()
    task = publish_tasks.get(uid)
    if task is None or task.done():
        publish_tasks[uid] = asyncio.create_task(wait_for_inactivity(uid, delay))


async def wait_for_inactivity(uid: int, delay: float | None = None):
    delay = float(delay if delay is not None else settings.auto_publish_seconds)
    logger.info("AUTO_WAIT uid=%s delay=%.1f", uid, delay)
    try:
        while True:
            started = last_activity.get(uid)
            if started is None or uid not in pending:
                return
            remaining = delay - (time.monotonic() - started)
            if remaining > 0:
                await asyncio.sleep(remaining)
                continue
            async with get_lock(uid):
                if uid in pending and last_activity.get(uid) == started:
                    logger.info("AUTO_TRIGGER uid=%s photos=%s", uid, len(pending[uid].photo_file_ids))
                    await publish_listing(uid)
            return
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("AUTO_PUBLISH_CRASH uid=%s", uid)
        try:
            await bot.send_message(uid, "❌ Avtomatik joylashda ichki xatolik yuz berdi. /publish ni sinab ko‘ring.")
        except Exception:
            logger.exception("Could not send error message")
    finally:
        publish_tasks.pop(uid, None)


async def publish_listing(uid: int) -> bool:
    listing = pending.get(uid)
    if not listing:
        return False

    status = ["🚀 E'lon joylanmoqda..."]
    logger.info(
        "PUBLISH_START uid=%s channel=%s photos=%s",
        uid, settings.channel_id, len(listing.photo_file_ids)
    )

    try:
        # Keep the draft until Telegram confirms success.
        result = await tg_pub.publish(listing)
        status.append(
            f"Telegram kanal: ✅ {result.get('url') or 'joylandi'}"
        )
        pending.pop(uid, None)
        last_activity.pop(uid, None)
    except Exception as exc:
        logger.exception("TELEGRAM_PUBLISH_FAILED uid=%s", uid)
        status.append(f"Telegram kanal: ❌ {type(exc).__name__}: {exc}")
        status.append("Draft saqlandi. /publish bilan qayta urinishingiz mumkin.")
        await bot.send_message(uid, "\n".join(status))
        return False

    if ig_pub:
        try:
            await ig_pub.publish(bot, listing)
            status.append("Instagram: ✅")
        except Exception as exc:
            logger.exception("INSTAGRAM_PUBLISH_FAILED uid=%s", uid)
            status.append(f"Instagram: ❌ {type(exc).__name__}: {exc}")
    else:
        status.append("Instagram: ⚪ Meta API hali ulanmagan")

    status.append("OLX Uzbekistan: ⚪ Rasmiy API access tasdiqlanmagan")
    status.append("BirBir / Egasi / Joymee: ⚪ Rasmiy avtomatik integratsiya tasdiqlanmagan")

    try:
        await bot.send_message(uid, "\n".join(status))
    except Exception:
        logger.exception("Could not send publish result to user")
    return True


@dp.message(CommandStart())
async def start(message: Message):
    uid = message.from_user.id
    if not allowed(uid):
        return
    try:
        chat = await bot.get_chat(settings.channel_id)
        channel_ok = f"✅ {chat.title or settings.channel_id}"
    except Exception as exc:
        channel_ok = f"❌ {type(exc).__name__}: {exc}"

    await message.answer(
        "🏠 <b>Real Estate Publisher</b>\n\n"
        "📸 Rasmlarni yuboring → 📝 tavsifni yuboring → men avtomatik joylayman.\n\n"
        f"📢 Kanal: {channel_ok}\n"
        f"⏱ Avtomatik publish: {settings.auto_publish_seconds} soniya\n\n"
        "Buyruqlar:\n"
        "/publish — hozir joylash\n"
        "/cancel — draftni bekor qilish\n"
        "/status — bot holatini tekshirish",
        parse_mode="HTML",
    )


@dp.message(Command("status"))
async def status(message: Message):
    uid = message.from_user.id
    if not allowed(uid):
        return
    draft = pending.get(uid)
    try:
        chat = await bot.get_chat(settings.channel_id)
        channel = f"✅ {chat.title or settings.channel_id}"
    except Exception as exc:
        channel = f"❌ {type(exc).__name__}: {exc}"
    await message.answer(
        f"🤖 Bot: ✅\n"
        f"📢 Kanal: {channel}\n"
        f"📸 Draft rasmlar: {len(draft.photo_file_ids) if draft else 0}\n"
        f"📝 Tavsif: {'✅' if draft and (draft.description or draft.caption) else '❌'}\n"
        f"📦 AI: {'✅' if settings.openai_api_key else '⚪ ulanmagan'}"
    )


@dp.message(Command("cancel"))
async def cancel(message: Message):
    uid = message.from_user.id
    if not allowed(uid):
        return
    pending.pop(uid, None)
    last_activity.pop(uid, None)
    task = publish_tasks.pop(uid, None)
    if task and not task.done():
        task.cancel()
    await message.answer("🗑 Joriy draft bekor qilindi.")


@dp.message(Command("publish"))
async def manual_publish(message: Message):
    uid = message.from_user.id
    if not allowed(uid):
        return
    if not pending.get(uid) or not pending[uid].photo_file_ids:
        await message.answer("❌ Hali e'lon uchun rasm yo‘q.")
        return
    await message.answer("🚀 Majburiy publish boshlandi...")
    async with get_lock(uid):
        await publish_listing(uid)


@dp.message(F.photo)
async def photo(message: Message):
    uid = message.from_user.id
    if not allowed(uid):
        return

    item = pending.setdefault(uid, Listing(user_id=uid))
    item.photo_file_ids.append(message.photo[-1].file_id)
    logger.info(
        "PHOTO_RECEIVED uid=%s count=%s media_group=%s",
        uid, len(item.photo_file_ids), message.media_group_id
    )

    if message.caption:
        item.caption = message.caption
        try:
            data = await parse_listing(message.caption, settings.openai_api_key, settings.openai_model)
            for key, value in data.items():
                if hasattr(item, key) and value:
                    setattr(item, key, str(value))
        except Exception:
            logger.exception("PHOTO_CAPTION_PARSE_FAILED uid=%s", uid)
            item.description = message.caption

    # Telegram media groups arrive as several photo updates. A short debounce
    # is enough for albums; ordinary single-photo workflows keep the normal delay.
    delay = 3 if message.media_group_id else settings.auto_publish_seconds
    touch(uid, delay)
    await message.answer(
        f"📸 {len(item.photo_file_ids)} ta rasm qabul qilindi. "
        f"{delay} soniya ichida boshqa xabar kelmasa avtomatik joylayman."
    )


@dp.message(F.text & ~F.text.startswith("/"))
async def text(message: Message):
    uid = message.from_user.id
    if not allowed(uid):
        return

    item = pending.setdefault(uid, Listing(user_id=uid))
    item.caption = message.text
    logger.info("TEXT_RECEIVED uid=%s chars=%s photos=%s", uid, len(message.text or ""), len(item.photo_file_ids))

    try:
        data = await parse_listing(message.text, settings.openai_api_key, settings.openai_model)
        for key, value in data.items():
            if hasattr(item, key) and value:
                setattr(item, key, str(value))
    except Exception:
        logger.exception("TEXT_PARSE_FAILED uid=%s", uid)
        item.description = message.text

    if item.photo_file_ids:
        touch(uid, settings.auto_publish_seconds)
        await message.answer(
            f"✅ Tavsif qabul qilindi. {len(item.photo_file_ids)} ta rasm bor. "
            f"{settings.auto_publish_seconds} soniyadan keyin avtomatik joylanadi."
        )
    else:
        await message.answer("📸 Avval rasmlarni yuboring.")


app = FastAPI()


@app.get("/")
async def health():
    return {"ok": True, "service": "real-estate-publisher-bot", "status": "live"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update_data = await request.json()
    logger.info(
        "WEBHOOK_UPDATE update_id=%s type=%s",
        update_data.get("update_id"),
        "message" if update_data.get("message") else "other",
    )
    update = Update.model_validate(update_data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.on_event("startup")
async def startup():
    base = os.getenv("WEBHOOK_BASE_URL", "").rstrip("/")
    if not base:
        base = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not base:
        logger.error("WEBHOOK URL IS NOT CONFIGURED")
        return

    webhook_url = f"{base}/telegram/webhook"
    await bot.set_webhook(webhook_url, allowed_updates=dp.resolve_used_update_types())
    info = await bot.get_webhook_info()
    logger.info(
        "WEBHOOK_SET url=%s pending=%s last_error=%s",
        info.url, info.pending_update_count, info.last_error_message
    )
    try:
        chat = await bot.get_chat(settings.channel_id)
        logger.info("CHANNEL_OK id=%s title=%s", chat.id, chat.title)
    except Exception:
        logger.exception("CHANNEL_CHECK_FAILED channel=%s", settings.channel_id)


@app.on_event("shutdown")
async def shutdown():
    for task in publish_tasks.values():
        if not task.done():
            task.cancel()
    await bot.delete_webhook()
    await bot.session.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
