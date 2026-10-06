import json
import httpx

SYSTEM = '''You are a real-estate listing editor for Uzbekistan. Extract structured fields from the user's Uzbek/Russian property text. Return ONLY valid JSON with keys: title, price, address, description, area, rooms, floor, phone. Never invent missing values. Keep phone as written. Make description concise and professional.'''

async def parse_listing(text: str, api_key: str | None, model: str = "gpt-5.6-mini"):
    if not api_key:
        return {"title":"🏠 Kvartira sotiladi", "description":text}
    payload = {
        "model": model,
        "input": [{"role":"system","content":SYSTEM},{"role":"user","content":text}],
        "text": {"format": {"type":"json_object"}},
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post("https://api.openai.com/v1/responses", headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"}, json=payload)
        r.raise_for_status()
        data = r.json()
    return json.loads(data.get("output_text", "{}").strip())
