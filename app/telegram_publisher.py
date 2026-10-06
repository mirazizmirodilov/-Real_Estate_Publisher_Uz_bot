from aiogram import Bot
from aiogram.types import InputMediaPhoto

class TelegramPublisher:
    def __init__(self, bot: Bot, channel_id: str):
        self.bot = bot
        self.channel_id = channel_id

    async def publish(self, listing):
        caption = listing.caption[:1024]
        if len(listing.photo_file_ids) == 1:
            msg = await self.bot.send_photo(self.channel_id, listing.photo_file_ids[0], caption=caption)
            return {"ok": True, "url": self._message_url(msg)}
        media = [InputMediaPhoto(media=fid, caption=caption if i == 0 else None) for i, fid in enumerate(listing.photo_file_ids[:10])]
        msgs = await self.bot.send_media_group(self.channel_id, media)
        return {"ok": True, "url": self._message_url(msgs[0])}

    def _message_url(self, msg):
        if isinstance(self.channel_id, str) and self.channel_id.startswith("@"):
            return f"https://t.me/{self.channel_id[1:]}/{msg.message_id}"
        return None
