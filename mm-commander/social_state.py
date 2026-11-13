"""Opt-in, rate-limited virtual social activity helpers."""
from __future__ import annotations

import random
from datetime import datetime

DAILY_LINES = {
    "morning": [
        "صبح بخیررر MM! کی بیداره؟ 😂",
        "صبح همگی بخیر؛ من آماده‌ام ببینم امروز چه خبراییه 🛡️",
    ],
    "breakfast": [
        "من برم یه صبحونه خیالی بزنم و برگردم 😂",
    ],
    "night": [
        "بچه‌ها شب شده؛ من می‌رم روی حالت استراحت مجازی. شب‌تون بخیر 🌙",
        "من فعلاً خاموشی نمایشی می‌زنم؛ گپ رو به شما می‌سپارم 😂",
    ],
}

def scheduled_line(now: datetime | None = None) -> str | None:
    """Return a possible routine line; caller must enforce per-chat cooldown and opt-in."""
    now = now or datetime.now()
    hour = now.hour
    if 7 <= hour < 10 and random.random() < 0.20:
        return random.choice(DAILY_LINES["morning"])
    if 10 <= hour < 12 and random.random() < 0.08:
        return random.choice(DAILY_LINES["breakfast"])
    if hour >= 22 or hour < 1:
        if random.random() < 0.15:
            return random.choice(DAILY_LINES["night"])
    return None
