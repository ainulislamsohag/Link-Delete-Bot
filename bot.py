import os
import re
import time
import logging
import threading
import html

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


# ==========================================
# CONFIGURATION
# ==========================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise SystemExit(
        "ERROR: BOT_TOKEN environment variable is missing!"
    )

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

MUTE_DURATION = 2 * 60 * 60       # 2 hours
REPORT_DELETE_DELAY = 180         # 3 minutes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# ==========================================
# LINK DETECTION
# ==========================================

LINK_PATTERN = re.compile(
    r"(?i)(?:"
    r"https?://\S+|"
    r"www\.\S+|"
    r"t\.me/\S*|"
    r"telegram\.me/\S*|"
    r"telegram\.dog/\S*|"
    r"tg://\S+|"
    r"(?<![\w@])(?:[a-z0-9-]+\.)+"
    r"(?:com|net|org|info|biz|xyz|top|site|online|"
    r"me|io|co|gg|app|dev|shop|store|live|tech|"
    r"cloud|fun|link|click|pro|vip|website|bd|"
    r"gov|edu|in|uk|us|tv|ly|to|cc|ru|tk)"
    r"(?:/[^\s]*)?"
    r")"
)

processed_messages = set()
processed_lock = threading.Lock()


def escape_html(value):
    return html.escape(str(value or "Unknown"))


def get_display_name(user):
    name = " ".join(
        part for part in [user.first_name, user.last_name] if part
    )
    return name or "Unknown"


def contains_link(message):
    text = message.text or message.caption or ""

    if LINK_PATTERN.search(text):
        return True

    entities = (
        (message.entities or [])
        + (message.caption_entities or [])
    )

    for entity in entities:
        if entity.type in ("url", "text_link"):
            return True

    if re.search(r"(?i)(?:^|\s)@[a-z][a-z0-9_]{4,}\b", text):
        return True

    return False


def is_group(chat):
    return chat.type in ("group", "supergroup")


def is_human_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception as exc:
        logger.warning("Could not check admin status: %s", exc)
        return False


# ==========================================
# MUTE / UNMUTE HELPERS
# ==========================================

def mute_member(chat_id, user_id, until_date):
    permissions = telebot.types.ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )

    bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=permissions,
        until_date=until_date
    )


def unmute_member(chat_id, user_id):
    # This restores common permissions.
    # Change these settings if your group has custom restrictions.
    permissions = telebot.types.ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )

    bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=permissions,
        until_date=0
    )


# ==========================================
# DELETE MESSAGE AFTER A DELAY
# ==========================================

def delete_message_later(chat_id, message_id, delay):
    def worker():
        time.sleep(delay)

        try:
            bot.delete_message(chat_id, message_id)
            logger.info(
                "Deleted report message %s from chat %s",
                message_id,
                chat_id
            )
        except Exception as exc:
            logger.warning(
                "Could not delete report message %s: %s",
                message_id,
                exc
            )

    threading.Thread(target=worker, daemon=True).start()


# ==========================================
# SEND REPORT TO GROUP ADMINS
# Delete each report after 3 minutes
# ==========================================

def send_admin_report(chat_id, report_text, reply_markup=None):
    try:
        administrators = bot.get_chat_administrators(chat_id)
    except Exception as exc:
        logger.error("Could not get group admins: %s", exc)
        return

    for admin in administrators:
        user = admin.user

        if user.is_bot:
            continue

        try:
            sent = bot.send_message(
                user.id,
                report_text,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )

            # Delete this admin's report after 180 seconds.
            delete_message_later(
                sent.chat.id,
                sent.message_id,
                REPORT_DELETE_DELAY
            )

        except Exception as exc:
            logger.info(
                "Could not DM admin %s. They may need to start the bot: %s",
                user.id,
                exc
            )


# ==========================================
# /START
# ==========================================

@bot.message_handler(commands=["start"])
def start_command(message):
    user = message.from_user

    text = (
        "🛡️ <b>ANTI-LINK BOT</b>\n\n"
        "আমি গ্রুপের লিংক শনাক্ত করে নিয়ম ভঙ্গকারী "
        "সদস্যকে মিউট করতে সাহায্য করি।\n\n"
        "➤ আমাকে গ্রুপে অ্যাড করো।\n"
        "➤ Delete Messages ও Restrict Members পারমিশন দাও।\n"
        "➤ রিপোর্ট পেতে গ্রুপের অ্যাডমিনরা আমাকে "
        "ব্যক্তিগত চ্যাটে /start পাঠাবেন।\n\n"
        f"👤 <b>Name:</b> {escape_html(get_display_name(user))}\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>"
    )

    bot.reply_to(message, text)


# ==========================================
# /ID
# ==========================================

@bot.message_handler(commands=["id"])
def id_command(message):
    bot.reply_to(
        message,
        f"🆔 <b>Chat ID:</b> <code>{message.chat.id}</code>\n"
        f"👤 <b>Your ID:</b> <code>{message.from_user.id}</code>"
    )


# ==========================================
# INLINE UNMUTE BUTTON
# ==========================================

@bot.callback_query_handler(
    func=lambda call: call.data and call.data.startswith("unmute:")
)
def unmute_button_callback(call):
    try:
        parts = call.data.split(":")

        if len(parts) != 3:
            bot.answer_callback_query(
                call.id,
                "Invalid request.",
                show_alert=True
            )
            return

        chat_id = int(parts[1])
        target_user_id = int(parts[2])

        # Only an admin of the original group can unmute.
        if not is_human_admin(chat_id, call.from_user.id):
            bot.answer_callback_query(
                call.id,
                "❌ শুধু ওই গ্রুপের অ্যাডমিন আনমিউট করতে পারবেন।",
                show_alert=True
            )
            return

        unmute_member(chat_id, target_user_id)

        bot.answer_callback_query(
            call.id,
            "✅ সদস্যকে আনমিউট করা হয়েছে!"
        )

        # Remove the button to prevent repeated clicks.
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )
        except Exception:
            pass

        # Send a separate confirmation.
        try:
            confirmation = bot.send_message(
                call.message.chat.id,
                "✅ <b>MEMBER UNMUTED</b>\n\n"
                f"👮 <b>Admin:</b> "
                f"{escape_html(get_display_name(call.from_user))}\n"
                f"🆔 <b>Admin ID:</b> "
                f"<code>{call.from_user.id}</code>\n"
                f"🆔 <b>Member ID:</b> "
                f"<code>{target_user_id}</code>"
            )

            # Delete the confirmation after 3 minutes.
            delete_message_later(
                confirmation.chat.id,
                confirmation.message_id,
                REPORT_DELETE_DELAY
            )

        except Exception as exc:
            logger.warning("Could not send confirmation: %s", exc)

    except Exception:
        logger.exception("Unmute button failed")

        try:
            bot.answer_callback_query(
                call.id,
                "❌ আনমিউট করা যায়নি। বটের পারমিশন পরীক্ষা করো।",
                show_alert=True
            )
        except Exception:
            pass


# ==========================================
# ANTI-LINK MODERATION
# ==========================================

@bot.message_handler(
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "audio",
        "voice",
        "video_note",
        "animation",
        "sticker"
    ],
    func=lambda message: True
)
def moderate_message(message):
    chat = message.chat
    user = message.from_user

    # Only moderate groups and supergroups.
    if not is_group(chat):
        return

    if not user or user.is_bot:
        return

    # Prevent duplicate processing.
    key = (chat.id, message.message_id)

    with processed_lock:
        if key in processed_messages:
            return

        processed_messages.add(key)

        if len(processed_messages) > 5000:
            processed_messages.clear()

    # Do not moderate human administrators.
    if is_human_admin(chat.id, user.id):
        return

    # Ignore messages without detected links.
    if not contains_link(message):
        return

    # Delete the offending message.
    try:
        bot.delete_message(chat.id, message.message_id)
    except Exception as exc:
        logger.warning("Could not delete offending message: %s", exc)

    # Mute for two hours.
    mute_until = int(time.time()) + MUTE_DURATION
    mute_success = False

    try:
        mute_member(chat.id, user.id, mute_until)
        mute_success = True
    except Exception as exc:
        logger.error("Could not mute member: %s", exc)

    # Add the unmute button only if muting succeeded.
    keyboard = InlineKeyboardMarkup()

    if mute_success:
        keyboard.add(
            InlineKeyboardButton(
                "🔓 UNMUTE MEMBER",
                callback_data=f"unmute:{chat.id}:{user.id}"
            )
        )

    username = (
        f"@{escape_html(user.username)}"
        if user.username
        else "Not Set"
    )

    group_title = escape_html(chat.title or "Unknown Group")
    member_name = escape_html(get_display_name(user))

    status = (
        "✅ Muted for 2 hours"
        if mute_success
        else "❌ Mute failed — check bot permissions"
    )

    original_text = message.text or message.caption or "[Media message]"

    if len(original_text) > 700:
        original_text = original_text[:700] + "..."

    report = (
        "🚨 <b>ANTI-LINK VIOLATION</b> 🚨\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Group:</b> {group_title}\n"
        f"🆔 <b>Group ID:</b> <code>{chat.id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Name:</b> {member_name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>Message:</b> {escape_html(original_text)}\n"
        f"🛡️ <b>Status:</b> {status}\n"
        "⏳ <b>Mute Duration:</b> 2 hours\n"
        "🗑️ <b>Report deletion:</b> After 3 minutes\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    send_admin_report(
        chat.id,
        report,
        reply_markup=keyboard if mute_success else None
    )


# ==========================================
# START BOT
# ==========================================

if __name__ == "__main__":
    logger.info("Anti-Link Bot is starting...")

    try:
        bot.remove_webhook()

        bot.infinity_polling(
            skip_pending=True,
            timeout=30,
            long_polling_timeout=30,
            allowed_updates=["message", "callback_query"]
        )

    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")

    except Exception:
        logger.exception("Bot stopped unexpectedly.")
        raise
