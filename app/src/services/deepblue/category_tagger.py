"""Lightweight keyword-based category tagger for DeepBlue messages."""

import re

POOL_KEYWORDS = {
    "pool", "spa", "chlorine", "ph", "alkalinity", "cya", "cyanuric", "calcium",
    "phosphate", "dosing", "dose", "shock", "pump", "filter", "heater", "sanitizer",
    "chemical", "chemistry", "ppm", "skimmer", "vacuum", "brush", "cartridge",
    "gallon", "gallons", "impeller", "motor", "valve", "jandy", "pentair", "hayward",
    "polaris", "cleaner", "booster", "salt", "cell", "chlorinator", "gas heater",
    "bather", "lsi", "langelier", "algae", "bromine", "cya", "stabilizer",
    "muriatic", "acid", "bicarb", "calcium chloride", "temperature", "flow rate",
    "pressure", "backwash", "ozone", "uv", "inspection", "violation", "emd",
}

BUSINESS_KEYWORDS = {
    "customer", "client", "invoice", "estimate", "quote", "payment", "billing",
    "email", "send", "broadcast", "announcement", "tech", "technician", "route",
    "schedule", "appointment", "visit", "case", "job", "work order", "rate",
    "price", "pricing", "margin", "profit", "commercial", "residential",
    "contract", "terms", "warranty", "refund", "credit", "statement", "receipt",
    "mailing address", "billing address", "property manager", "contact",
}

OFF_TOPIC_KEYWORDS = {
    "story", "novel", "poem", "homework", "recipe", "workout", "movie", "song",
    "vacation", "travel", "joke", "riddle", "game", "sports score", "news",
    "weather", "horoscope", "dream", "meme", "tiktok", "instagram", "tweet",
}


_OFF_TOPIC_RESPONSE_PATTERNS = [
    "focused on pool service",
    "i can help with pool service",
    "outside of pool service",
    "business assistant for sapphire",
    "i'm here to help with pool",
]


def classify_prompt(prompt: str) -> str:
    """Return category: pool_service | business_ops | off_topic | unknown."""
    if not prompt:
        return "unknown"
    lower = prompt.lower()
    # Count keyword matches
    pool_hits = sum(1 for kw in POOL_KEYWORDS if kw in lower)
    biz_hits = sum(1 for kw in BUSINESS_KEYWORDS if kw in lower)
    off_hits = sum(1 for kw in OFF_TOPIC_KEYWORDS if kw in lower)

    if off_hits >= 2 and pool_hits == 0 and biz_hits == 0:
        return "off_topic"
    if pool_hits >= biz_hits and pool_hits > 0:
        return "pool_service"
    if biz_hits > 0:
        return "business_ops"
    return "unknown"


def detect_off_topic_response(response_text: str) -> bool:
    """Check if the assistant's response indicates an off-topic refusal."""
    if not response_text:
        return False
    lower = response_text.lower()
    return any(pat in lower for pat in _OFF_TOPIC_RESPONSE_PATTERNS)
