#!/usr/bin/env python3
"""MM Commander — Rubika polling bot with optional AI chat and consent-based memory."""
from __future__ import annotations

import json
import logging
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from memory_store import clear_chat, initialize as initialize_memory, recent_messages, save_message
from personality import BOT_NAME, build_messages

TOKEN = os.environ.get("RUBIKA_BOT_TOKEN", "").strip()
OWNER_IDS = {x.strip() for x in os.environ.get("MM_OWNER_IDS", "").split(",") if x.strip()}
AI_CHAT_IDS = {x.strip() for x in os.environ.get("MM_AI_CHAT_IDS", "").split(",") if x.strip()}
MEMORY_CHAT_IDS = {x.strip() for x in os.environ.get("MM_MEMORY_CHAT_IDS", "").split(",") if x.strip()}
AI_API_KEY = os.environ.get("MM_AI_API_KEY", "").strip()
AI_BASE_URL = os.environ.get("MM_AI_BASE_URL", "http://localhost:11434/v1").rstrip("/")
AI_MODEL = os.environ.get("MM_AI_MODEL", "qwen2.5:1.5b").strip()
POLL_SECONDS = max(3, int(os.environ.get("POLL_SECONDS", "5")))
AI_COOLDOWN_SECONDS = max(10, int(os.environ.get("MM_AI_COOLDOWN_SECONDS", "15")))
BASE_URL = "https://botapi.rubika.ir/v3"
_last_ai_reply: dict[str, float] = {}
BOT_ID = ""

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("mm-commander")


class RubikaAPIError(RuntimeError):
    pass


class AIServiceError(RuntimeError):
    pass


def _post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url, data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AIServiceError(type(exc).__name__) from None
    if not isinstance(result, dict):
        raise AIServiceError("Invalid service response")
    return result


def api(method: str, payload: dict | None = None) -> dict:
    if not TOKEN:
        raise RubikaAPIError("RUBIKA_BOT_TOKEN is not configured")
    result = _post_json(f"{BASE_URL}/{TOKEN}/{method}", payload or {})
    if result.get("status") != "OK":
        raise RubikaAPIError("Rubika returned a non-OK status")
    return result.get("data") or {}


def send(chat_id: str, text: str, reply_to: str | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text[:4000]}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    api("sendMessage", payload)


def ask_ai(chat_id: str, user_id: str, display_name: str, user_text: str) -> str:
    if not AI_MODEL:
        raise AIServiceError("AI service is not configured")
    history = recent_messages(chat_id, 12) if chat_id in MEMORY_CHAT_IDS else []
    messages = build_messages(history, f"{display_name}: {user_text}")
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.85,
        "max_tokens": 220,
    }
    ai_headers = {"Authorization": f"Bearer {AI_API_KEY}"} if AI_API_KEY else {}
    result = _post_json(
        f"{AI_BASE_URL}/chat/completions",
        payload,
        ai_headers,
    )
    try:
        answer = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise AIServiceError("Invalid chat completion response") from None
    if not isinstance(answer, str) or not answer.strip():
        raise AIServiceError("Empty AI response")
    answer = answer.strip()[:3800]
    if chat_id in MEMORY_CHAT_IDS:
        save_message(chat_id, user_id, display_name, "member", user_text)
        save_message(chat_id, "assistant", BOT_NAME, "assistant", answer)
    return answer


def help_text() -> str:
    return (
        "🛡️ پنل MM COMMANDER\n\n"
        "دستورهای عمومی:\n"
        "/start — شروع کار\n"
        "/help — راهنما\n"
        "/myid — نمایش شناسه کاربری شما\n"
        "/chatid — نمایش شناسه همین گفتگو\n"
        "/forget — پاک‌کردن حافظه ذخیره‌شده همین گپ (فقط مدیر)\n\n"
        "دستورهای مدیر:\n"
        "/panel — پنل مدیریت\n"
        "/post متن — انتشار اطلاعیه در همین گفتگو\n"
        "/contest عنوان | جایزه | مهلت — اعلام مسابقه\n"
        "/results متن — اعلام نتایج در همین گفتگو\n\n"
        "گفت‌وگوی هوشمند فقط در گپ‌هایی فعال است که مدیر در MM_AI_CHAT_IDS مجاز کرده باشد. "
        "ذخیره تاریخچه فقط در گپ‌های جداگانه MM_MEMORY_CHAT_IDS فعال می‌شود."
    )


def handle_update(update: dict) -> None:
    if update.get("type") != "NewMessage":
        return
    msg = update.get("new_message") or {}
    chat_id = str(update.get("chat_id") or "")
    sender_id = str(msg.get("sender_id") or "")
    text = (msg.get("text") or "").strip()
    message_id = msg.get("message_id")
    if not chat_id or not text or (BOT_ID and sender_id == BOT_ID):
        return

    display_name = str(msg.get("sender_name") or msg.get("first_name") or "عضو")[:100]
    command = text.split(maxsplit=1)[0].lower()
    argument = text[len(text.split(maxsplit=1)[0]):].strip()

    if command == "/myid":
        send(chat_id, f"شناسه کاربری شما:\n{sender_id}", message_id)
        return
    if command == "/chatid":
        send(chat_id, f"شناسه این گفتگو:\n{chat_id}", message_id)
        return
    if command in {"/start", "/help"}:
        send(chat_id, "به MM COMMANDER خوش اومدی! 🛡️\n\n" + help_text(), message_id)
        return

    admin_commands = {"/panel", "/post", "/contest", "/results", "/forget"}
    if command in admin_commands:
        if not OWNER_IDS:
            send(chat_id, "شناسه مدیر هنوز در تنظیمات محرمانه برنامه ثبت نشده.", message_id)
            return
        if sender_id not in OWNER_IDS:
            send(chat_id, "این دستور فقط برای مدیران اتحادیه فعاله.", message_id)
            return
        if command == "/panel":
            send(chat_id, "🛡️ پنل مدیریت MM\n\n" + help_text(), message_id)
        elif command == "/forget":
            clear_chat(chat_id)
            send(chat_id, "حافظه ذخیره‌شده این گپ پاک شد. 🧹", message_id)
        elif command == "/post":
            send(chat_id, "📢 اطلاعیه اتحادیه MM\n\n" + argument if argument else "متن اطلاعیه را بعد از دستور بنویس.", message_id)
        elif command == "/contest":
            parts = [part.strip() for part in argument.split("|")]
            if len(parts) != 3 or not all(parts):
                send(chat_id, "قالب درست:\n/contest عنوان مسابقه | جایزه | مهلت", message_id)
            else:
                title, prize, deadline = parts
                send(chat_id, f"🏆 مسابقه جدید اتحادیه MM\n\n🎯 عنوان: {title}\n🎁 جایزه: {prize}\n⏰ مهلت: {deadline}", message_id)
        elif command == "/results":
            send(chat_id, "📋 نتایج رسمی اتحادیه MM\n\n" + argument if argument else "نتایج را بعد از دستور بنویس.", message_id)
        return

    lowered = text.casefold()
    if any(word in lowered for word in ("قوانین", "قانون", "قوانین گپ")):
        send(chat_id, "📌 برای اطلاع از قوانین و شرایط عضویت، پیام قوانین سنجاق‌شده گپ اتحادیه MM را مطالعه کن.", message_id)
        return
    if any(word in lowered for word in ("پشتیبانی", "کمک", "مشکل")) and chat_id not in AI_CHAT_IDS:
        send(chat_id, "برای پیگیری موضوع، جزئیات مشکلت رو برای پشتیبانی اتحادیه MM بفرست.", message_id)
        return

    if chat_id not in AI_CHAT_IDS:
        return
    now = time.monotonic()
    if now - _last_ai_reply.get(chat_id, 0.0) < AI_COOLDOWN_SECONDS:
        return
    _last_ai_reply[chat_id] = now
    try:
        answer = ask_ai(chat_id, sender_id, display_name, text)
        send(chat_id, answer, message_id)
    except AIServiceError as exc:
        log.warning("AI response unavailable: %s", exc)
        if str(exc) == "AI service is not configured":
            send(chat_id, "مغز هوش مصنوعی من هنوز به سرویس پاسخ‌گویی وصل نشده؛ مدیر باید تنظیمات محرمانه AI را تکمیل کند.", message_id)


def main() -> None:
    global BOT_ID
    if not TOKEN:
        raise SystemExit("Set RUBIKA_BOT_TOKEN as an environment variable.")
    if not OWNER_IDS:
        log.warning("MM_OWNER_IDS is empty; admin commands are disabled.")
    if MEMORY_CHAT_IDS:
        initialize_memory()
        log.info("Consent-configured local memory is enabled for %d chat(s).", len(MEMORY_CHAT_IDS))
    if AI_CHAT_IDS and not AI_MODEL:
        log.warning("AI chats are enabled but MM_AI_MODEL is missing.")
    try:
        me = api("getMe")
        BOT_ID = str(me.get("user_id") or me.get("bot_id") or "")
        log.info("Connected to Rubika Bot API.")
    except RubikaAPIError as exc:
        raise SystemExit(f"Bot connection failed: {exc}") from None

    offset_id: str | None = None

    # Ignore updates that were already waiting before this launch.
    # This prevents the bot from replying to hours-old chat messages on startup.
    try:
        while True:
            pending = {"limit": 50}
            if offset_id:
                pending["offset_id"] = offset_id
            data = api("getUpdates", pending)
            updates = data.get("updates", [])
            next_offset = data.get("next_offset_id")
            if next_offset:
                offset_id = next_offset
            if not updates or len(updates) < 50 or not next_offset:
                break
            log.info("Skipping %d old pending update(s).", len(updates))
    except RubikaAPIError as exc:
        log.warning("Could not clear old pending updates: %s", exc)

    log.info("MM Commander polling loop started.")
    while True:
        try:
            payload = {"limit": 50}
            if offset_id:
                payload["offset_id"] = offset_id
            data = api("getUpdates", payload)
            for update in data.get("updates", []):
                try:
                    handle_update(update)
                except RubikaAPIError as exc:
                    log.warning("Could not process one update: %s", exc)
                except Exception as exc:
                    log.warning("Could not process one update: %s", type(exc).__name__)
            offset_id = data.get("next_offset_id") or offset_id
        except RubikaAPIError as exc:
            log.warning("Polling error: %s", exc)
            time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            log.info("MM Commander stopped.")
            break
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
