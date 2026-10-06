from aiogram import Bot
from aiogram.types import InputMediaPhoto

class TelegramPublisher:
    def __init__(self, bot: Bot, channel_id: str):
        self.bot = bot
        self.channel_id = channel_id

    async def publish(self, listing):
        if not listing.photo_file_ids:
            raise ValueError("E'lon rasmsiz yuborilmaydi")

        caption = listing.render_caption()
        sent = []

        # Telegram albums accept up to 10 media items per group.
        for start in range(0, len(listing.photo_file_ids), 10):
            chunk = listing.photo_file_ids[start:start + 10]
            if len(chunk) == 1:
                msg = await self.bot.send_photo(
                    self.channel_id,
                    chunk[0],
                    caption=caption[:1024],
                )
                sent.append(msg)
            else:
                media = [
                    InputMediaPhoto(
                        media=file_id,
                        caption=caption[:1024] if index == 0 else None,
                    )
                    for index, file_id in enumerate(chunk)
                ]
                msgs = await self.bot.send_media_group(self.channel_id, media)
                sent.extend(msgs)

        return {
            "ok": True,
            "url": self._message_url(sent[0]) if sent else None,
            "count": len(sent),
        }

    def _message_url(self, msg):
        if self.channel_id.startswith("@"):
            return f"https://t.me/{self.channel_id[1:]}/{msg.message_id}"
        return None
