import asyncio
import logging
import os

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, Update

from .config import get_settings
from .models import Listing
from .ai_parser import parse_listing
from .telegram_publisher import TelegramPublisher
from .instagram_publisher import InstagramPublisher

logging.basicConfig(level=logging.INFO)
settings = get_settings()
bot = Bot(settings.bot_token)
dp = Dispatcher()
tg_pub = TelegramPublisher(bot, settings.channel_id)
ig_pub = InstagramPublisher(settings.meta_access_token, settings.ig_user_id, settings.meta_graph_version, settings.bot_token) if settings.meta_access_token and settings.ig_user_id else None
pending: dict[int, Listing] = {}

def allowed(uid: int) -> bool:
    return not settings.allowed_user_ids or uid in settings.allowed_user_ids

async def schedule_publish(uid: int):
    await asyncio.sleep(settings.auto_publish_seconds)
    if pending.get(uid):
        await publish_listing(uid)

async def publish_listing(uid: int):
    listing = pending.pop(uid, None)
    if not listing:
        return
    status = ["🚀 E'lon joylanmoqda..."]
    try:
        r = await tg_pub.publish(listing)
        status.append(f"Telegram kanal: {'✅' if r['ok'] else '❌'} {r.get('url') or ''}".strip())
    except Exception as e:
        logging.exception("Telegram publish failed")
        status.append(f"Telegram kanal: ❌ {e}")
    if ig_pub:
        try:
            await ig_pub.publish(bot, listing)
            status.append("Instagram: ✅")
        except Exception as e:
            logging.exception("Instagram publish failed")
            status.append(f"Instagram: ❌ {e}")
    else:
        status.append("Instagram: ⚪ Meta API ma'lumotlari ulanmagan")
    status.append("OLX Uzbekistan: ⚪ Rasmiy API access tasdiqlanmagan")
    status.append("BirBir / Egasi / Joymee: ⚪ Rasmiy avtomatik integratsiya tasdiqlanmagan")
    await bot.send_message(uid, "\n".join(status))

@dp.message(CommandStart())
async def start(message: Message):
    if not allowed(message.from_user.id): return
    await message.answer("🏠 Uy e'lonini yuboring.\n\nBir nechta rasmlarni ketma-ket yuboring va oxirgi rasmga tavsifni yozing. Men ma'lumotlarni AI orqali tartiblayman va avtomatik joylayman.")

@dp.message(Command("cancel"))
async def cancel(message: Message):
    pending.pop(message.from_user.id, None)
    await message.answer("🗑 Joriy e'lon bekor qilindi.")

@dp.message(F.photo)
async def photo(message: Message):
    uid = message.from_user.id
    if not allowed(uid): return
    item = pending.setdefault(uid, Listing(user_id=uid))
    item.photo_file_ids.append(message.photo[-1].file_id)
    if message.caption:
        item.caption = message.caption
        try:
            data = await parse_listing(message.caption, settings.openai_api_key, settings.openai_model)
            for key, value in data.items():
                if hasattr(item, key) and value:
                    setattr(item, key, str(value))
        except Exception:
            logging.exception("AI parsing failed; using raw caption")
            item.description = message.caption
    await message.answer(f"📸 {len(item.photo_file_ids)} ta rasm qabul qilindi. Tavsif olindi — avtomatik joylash uchun yana {settings.auto_publish_seconds} soniya kutaman.")
    asyncio.create_task(schedule_publish(uid))

@dp.message(F.text & ~F.text.startswith("/"))
async def text(message: Message):
    uid = message.from_user.id
    if not allowed(uid): return
    item = pending.setdefault(uid, Listing(user_id=uid))
    item.caption = message.text
    try:
        data = await parse_listing(message.text, settings.openai_api_key, settings.openai_model)
        for key, value in data.items():
            if hasattr(item, key) and value:
                setattr(item, key, str(value))
    except Exception:
        item.description = message.text
    if item.photo_file_ids:
        asyncio.create_task(schedule_publish(uid))
        await message.answer("✅ Ma'lumot qabul qilindi. E'lon avtomatik joylanadi.")
    else:
        await message.answer("Endi rasmlarni yuboring.")

app = FastAPI()

@app.get("/")
async def health():
    return {"ok": True, "service": "real-estate-publisher-bot"}

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.on_event("startup")
async def startup():
    base = os.getenv("WEBHOOK_BASE_URL", "").rstrip("/")
    if not base:
        base = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if base:
        await bot.set_webhook(f"{base}/telegram/webhook")

@app.on_event("shutdown")
async def shutdown():
    await bot.delete_webhook()
    await bot.session.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
