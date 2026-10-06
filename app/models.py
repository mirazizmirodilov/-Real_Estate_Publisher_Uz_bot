from dataclasses import dataclass, field

@dataclass
class Listing:
    user_id: int
    caption: str = ""
    photo_file_ids: list[str] = field(default_factory=list)
    title: str = ""
    price: str = ""
    address: str = ""
    description: str = ""
    area: str = ""
    rooms: str = ""
    floor: str = ""
    phone: str = ""

    def render_caption(self) -> str:
        parts = [self.title or "🏠 Kvartira sotiladi"]
        if self.address: parts.append(f"📍 {self.address}")
        if self.rooms: parts.append(f"🚪 Xonalar: {self.rooms}")
        if self.area: parts.append(f"📐 Maydon: {self.area}")
        if self.floor: parts.append(f"🏢 Qavat: {self.floor}")
        if self.price: parts.append(f"💰 Narx: {self.price}")
        if self.description: parts.append(f"\n{self.description}")
        if self.phone: parts.append(f"\n📞 {self.phone}")
        return "\n".join(parts)[:4096]
