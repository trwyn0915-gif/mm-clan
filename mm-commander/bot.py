#!/usr/bin/env python3
"""MM Commander — minimal Rubika Bot API polling bot.

Secrets and owner IDs are supplied only through environment variables.
This first version intentionally supports text commands and safe FAQ replies.
"""
from __future__ import annotations

import json
import logging
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TOKEN = os.environ.get("RUBIKA_BOT_TOKEN", "").strip()
OWNER_IDS = {x.strip() for x in os.environ.get("MM_OWNER_IDS", "").split(",") if x.strip()}
POLL_SECONDS = max(3, int(os.environ.get("POLL_SECONDS", "5")))
BASE_URL = "https://botapi.rubika.ir/v3"

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("mm-commander")


class RubikaAPIError(RuntimeError):
    pass


def api(method: str, payload: dict | None = None) -> dict:
    if not TOKEN:
        raise RubikaAPIError("RUBIKA_BOT_TOKEN is not configured")
    url = f"{BASE_URL}/{TOKEN}/{method}"
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RubikaAPIError(type(exc).__name__) from None

    if result.get("status") != "OK":
        # Do not log response bodies: they may contain private platform data.
        raise RubikaAPIError("Rubika returned a non-OK status")
    return result.get("data") or {}


def send(chat_id: str, text: str, reply_to: str | None = None) -> None:
    payload = {"chat_id": chat_id, "text": text[:4000]}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    api("sendMessage", payload)


def help_text() -> str:
    return (
        "🛡️ پنل MM COMMANDER\n\n"
        "دستورهای عمومی:\n"
        "/start — شروع کار\n"
        "/help — راهنما\n"
        "/myid — نمایش شناسه کاربری شما\n\n"
        "دستورهای مدیر (پس از ثبت شناسه مدیر):\n"
        "/panel — پنل مدیریت\n"
        "/post متن — انتشار اطلاعیه در همین گفتگو\n"
        "/contest عنوان | جایزه | مهلت — اعلام مسابقه\n"
        "/results متن — اعلام نتایج در همین گفتگو\n\n"
        "نسخه اولیه فقط پیام متنی می‌فرستد. ارسال عکس و ویدئو در مرحله بعد اضافه می‌شود."
    )


def handle_update(update: dict) -> None:
    if update.get("type") != "NewMessage":
        return

    msg = update.get("new_message") or {}
    chat_id = update.get("chat_id")
    sender_id = str(msg.get("sender_id") or "")
    text = (msg.get("text") or "").strip()
    message_id = msg.get("message_id")

    if not chat_id or not text:
        return

    command = text.split(maxsplit=1)[0].lower()
    argument = text[len(text.split(maxsplit=1)[0]):].strip() if text else ""

    if command == "/myid":
        send(chat_id, f"شناسه کاربری شما:\n{sender_id}", message_id)
        return

    if command in {"/start", "/help"}:
        send(chat_id, "به MM COMMANDER خوش اومدی! 🛡️\n\n" + help_text(), message_id)
        return

    admin_commands = {"/panel", "/post", "/contest", "/results"}
    if command in admin_commands:
        if not OWNER_IDS:
            send(
                chat_id,
                "هنوز شناسه مدیر در تنظیمات برنامه ثبت نشده. مدیر باید /myid را بزند و شناسه خودش را در تنظیمات محرمانه سرور ثبت کند.",
                message_id,
            )
            return
        if sender_id not in OWNER_IDS:
            send(chat_id, "این دستور فقط برای مدیران اتحادیه فعاله.", message_id)
            return

        if command == "/panel":
            send(chat_id, "🛡️ پنل مدیریت MM\n\n" + help_text(), message_id)
        elif command == "/post":
            if not argument:
                send(chat_id, "متن اطلاعیه را بعد از دستور بنویس.\nنمونه: /post اطلاعیه جدید اتحادیه", message_id)
            else:
                send(chat_id, "📢 اطلاعیه اتحادیه MM\n\n" + argument, message_id)
        elif command == "/contest":
            parts = [part.strip() for part in argument.split("|")]
            if len(parts) != 3 or not all(parts):
                send(chat_id, "قالب درست:\n/contest عنوان مسابقه | جایزه | مهلت", message_id)
            else:
                title, prize, deadline = parts
                send(
                    chat_id,
                    f"🏆 مسابقه جدید اتحادیه MM\n\n🎯 عنوان: {title}\n🎁 جایزه: {prize}\n⏰ مهلت: {deadline}\n\nبرای شرکت، قوانین اعلام‌شده توسط مدیریت را دنبال کنید.",
                    message_id,
                )
        elif command == "/results":
            if not argument:
                send(chat_id, "نتایج را بعد از دستور بنویس.\nنمونه: /results نفر اول: ...", message_id)
            else:
                send(chat_id, "📋 نتایج رسمی اتحادیه MM\n\n" + argument, message_id)
        return

    lowered = text.casefold()
    if any(word in lowered for word in ("قوانین", "قانون", "قوانین گپ")):
        send(chat_id, "📌 برای اطلاع از قوانین و شرایط عضویت، پیام قوانین سنجاق‌شده گپ اتحادیه MM را مطالعه کن.", message_id)
    elif any(word in lowered for word in ("پشتیبانی", "کمک", "مشکل")):
        send(chat_id, "برای پیگیری موضوع، جزئیات مشکلت رو برای پشتیبانی اتحادیه MM بفرست.", message_id)


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set RUBIKA_BOT_TOKEN as an environment variable.")
    if not OWNER_IDS:
        log.warning("MM_OWNER_IDS is empty; admin commands are disabled until configured.")

    try:
        me = api("getMe")
        log.info("Connected to Rubika Bot API.")
    except RubikaAPIError as exc:
        raise SystemExit(f"Bot connection failed: {exc}") from None

    offset_id: str | None = None
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
