import httpx

class InstagramPublisher:
    def __init__(self, access_token: str, ig_user_id: str, graph_version: str, bot_token: str):
        self.token = access_token
        self.ig_user_id = ig_user_id
        self.version = graph_version
        self.bot_token = bot_token

    async def _tg_url(self, bot, file_id: str) -> str:
        f = await bot.get_file(file_id)
        return f"https://api.telegram.org/file/bot{self.bot_token}/{f.file_path}"

    async def publish(self, bot, listing):
        if not listing.photo_file_ids:
            raise ValueError("Instagram requires at least one image")
        images = [await self._tg_url(bot, x) for x in listing.photo_file_ids[:10]]
        base = f"https://graph.facebook.com/{self.version}"
        async with httpx.AsyncClient(timeout=60) as client:
            if len(images) == 1:
                r = await client.post(f"{base}/{self.ig_user_id}/media", data={"image_url": images[0], "caption": listing.caption, "access_token": self.token})
                r.raise_for_status()
                creation_id = r.json()["id"]
            else:
                children = []
                for image in images:
                    r = await client.post(f"{base}/{self.ig_user_id}/media", data={"image_url": image, "is_carousel_item": "true", "access_token": self.token})
                    r.raise_for_status()
                    children.append(r.json()["id"])
                r = await client.post(f"{base}/{self.ig_user_id}/media", data={"media_type":"CAROUSEL","children":",".join(children),"caption":listing.caption,"access_token":self.token})
                r.raise_for_status()
                creation_id = r.json()["id"]
            r = await client.post(f"{base}/{self.ig_user_id}/media_publish", data={"creation_id":creation_id,"access_token":self.token})
            r.raise_for_status()
            return {"ok": True, "media_id": r.json()["id"]}
