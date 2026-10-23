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

BOT_NAME = "ANTI LINK BOT"
OWNER_USERNAME = "ainulbhai"

MUTE_DURATION = 2 * 60 * 60
REPORT_DELETE_DELAY = 180

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

processed_messages = set()
processed_lock = threading.Lock()


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def escape_html(value):
    return html.escape(str(value or "Unknown"))


def get_display_name(user):
    name = " ".join(
        part
        for part in [user.first_name, user.last_name]
        if part
    )
    return name or "Unknown"


def is_group(chat):
    return chat.type in ("group", "supergroup")


def is_private(message):
    return message.chat.type == "private"


def is_human_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")

    except Exception as exc:
        logger.warning(
            "Could not check administrator status: %s",
            exc
        )
        return False


def owner_keyboard():
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            "👑 OWNER",
            url=f"https://t.me/{OWNER_USERNAME}"
        )
    )

    return keyboard


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


def get_message_text(message):
    return message.text or message.caption or ""


def contains_link(message):
    text = get_message_text(message)

    if LINK_PATTERN.search(text):
        return True

    entities = (
        (message.entities or [])
        + (message.caption_entities or [])
    )

    for entity in entities:
        if entity.type in ("url", "text_link"):
            return True

    if re.search(
        r"(?i)(?:^|\s)@[a-z][a-z0-9_]{4,}\b",
        text
    ):
        return True

    return False


def extract_link(message):
    text = get_message_text(message)

    entities = (
        (message.entities or [])
        + (message.caption_entities or [])
    )

    for entity in entities:
        if entity.type == "text_link" and entity.url:
            return entity.url

        if entity.type == "url":
            return text[
                entity.offset:entity.offset + entity.length
            ]

    match = LINK_PATTERN.search(text)

    if match:
        return match.group(0)

    username_match = re.search(
        r"(?i)(?:^|\s)(@[a-z][a-z0-9_]{4,}\b)",
        text
    )

    if username_match:
        return username_match.group(1)

    return "(Link in media caption)"


# ==========================================
# AUTO-DELETE HELPER
# ==========================================

def delete_message_later(chat_id, message_id, delay):
    def worker():
        time.sleep(delay)

        try:
            bot.delete_message(chat_id, message_id)

            logger.info(
                "Deleted message %s from chat %s",
                message_id,
                chat_id
            )

        except Exception as exc:
            logger.warning(
                "Could not delete message %s: %s",
                message_id,
                exc
            )

    threading.Thread(
        target=worker,
        daemon=True
    ).start()


# ==========================================
# MUTE AND UNMUTE
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
        chat_id=chat_id,
        user_id=user_id,
        permissions=permissions,
        until_date=until_date
    )


def unmute_member(chat_id, user_id):
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
        chat_id=chat_id,
        user_id=user_id,
        permissions=permissions,
        until_date=0
    )


# ==========================================
# ADMIN REPORTS
# ==========================================

def send_admin_report(chat_id, report_text, reply_markup=None):
    try:
        administrators = bot.get_chat_administrators(chat_id)

    except Exception:
        logger.exception(
            "Could not retrieve group administrators."
        )
        return

    for admin in administrators:
        user = admin.user

        if user.is_bot:
            continue

        try:
            bot.send_message(
                chat_id=user.id,
                text=report_text,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )

        except Exception as exc:
            logger.warning(
                "Could not send a private report to admin %s: %s",
                user.id,
                exc
            )


# ==========================================
# /START — PRIVATE INBOX ONLY
# ==========================================

@bot.message_handler(
    commands=["start"],
    chat_types=["private"]
)
def start_command(message):
    first_name = escape_html(
        message.from_user.first_name or "Friend"
    )

    text = (
        "🛡️ <b>𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗔𝗡𝗧𝗜 𝗟𝗜𝗡𝗞 𝗕𝗢𝗧</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 Hello, {first_name}!\n"
        f"💎 Welcome to {escape_html(BOT_NAME)}.\n\n"
        "🤖 <b>YOUR GROUP, YOUR RULES!</b> 🛡️\n"
        "🔰 Keep your Telegram group clean, safe & "
        "spam-free with our smart protection system.\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    bot.send_message(
        message.chat.id,
        text,
        disable_web_page_preview=True
    )


# ==========================================
# /HELP — PRIVATE INBOX ONLY
# OWNER BUTTON ONLY HERE
# ==========================================

@bot.message_handler(
    commands=["help"],
    chat_types=["private"]
)
def help_command(message):
    text = (
        "📌 <b>𝗛𝗢𝗪 𝗧𝗢 𝗨𝗦𝗘</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "➊ Add the bot to your group.\n"
        "➋ Promote the bot to Administrator.\n"
        "➌ Give it permission to Delete Messages.\n"
        "➍ Give it permission to Restrict Members.\n"
        "➎ Enjoy automatic link protection! 🚀\n\n"
        "⚙️ <b>Need Help?</b>\n"
        "Add the bot to your group and configure "
        "its settings to get started.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👑 Powered by AB ORGANIZATION\n"
        "🛡️ Your Group's Security Is Our Priority!\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=owner_keyboard(),
        disable_web_page_preview=True
    )


# ==========================================
# /FUTURES — PRIVATE INBOX ONLY
# ==========================================

@bot.message_handler(
    commands=["futures"],
    chat_types=["private"]
)
def futures_command(message):
    text = (
        "✨ <b>𝗕𝗢𝗧 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔗 ➜ Automatically Detect Links\n"
        "🚫 ➜ Delete Unauthorized Links\n"
        "🛡️ ➜ Protect Your Group from Spam\n"
        "⚡ ➜ Fast & Automatic Moderation\n"
        "👮 ➜ Admin-Friendly Management\n"
        "🔒 ➜ Keep Your Community Safe\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    bot.send_message(
        message.chat.id,
        text,
        disable_web_page_preview=True
    )


# ==========================================
# /ID — PRIVATE INBOX ONLY
# ==========================================

@bot.message_handler(
    commands=["id"],
    chat_types=["private"]
)
def id_command(message):
    bot.reply_to(
        message,
        f"🆔 <b>Chat ID:</b> "
        f"<code>{message.chat.id}</code>\n"
        f"👤 <b>Your ID:</b> "
        f"<code>{message.from_user.id}</code>"
    )


# ==========================================
# UNMUTE BUTTON CALLBACK
# ==========================================

@bot.callback_query_handler(
    func=lambda call: (
        call.data and call.data.startswith("unmute:")
    )
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

        if not is_human_admin(chat_id, call.from_user.id):
            bot.answer_callback_query(
                call.id,
                "Only administrators of this group can unmute members.",
                show_alert=True
            )
            return

        unmute_member(chat_id, target_user_id)

        bot.answer_callback_query(
            call.id,
            "Member successfully unmuted."
        )

        try:
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
        except Exception:
            logger.warning(
                "Could not remove the unmute button."
            )

        try:
            target_member = bot.get_chat_member(
                chat_id,
                target_user_id
            )

            target_name = escape_html(
                get_display_name(target_member.user)
            )

        except Exception:
            target_name = "Unknown"

        confirmation_text = (
            "✅ <b>MEMBER UNMUTED</b>\n\n"
            f"👮 <b>Administrator:</b> "
            f"{escape_html(get_display_name(call.from_user))}\n"
            f"👤 <b>User:</b> {target_name}\n"
            f"🆔 <b>Member ID:</b> "
            f"<code>{target_user_id}</code>"
        )

        try:
            confirmation = bot.send_message(
                call.message.chat.id,
                confirmation_text
            )

            delete_message_later(
                confirmation.chat.id,
                confirmation.message_id,
                REPORT_DELETE_DELAY
            )

        except Exception:
            logger.exception(
                "Could not send unmute confirmation."
            )

    except Exception:
        logger.exception(
            "Unmute button operation failed."
        )

        try:
            bot.answer_callback_query(
                call.id,
                "Failed to unmute the member. "
                "Check the bot's permissions.",
                show_alert=True
            )
        except Exception:
            pass


# ==========================================
# ANTI-LINK MODERATION
# GROUPS AND SUPERGROUPS ONLY
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

    if not is_group(chat):
        return

    if not user or user.is_bot:
        return

    key = (chat.id, message.message_id)

    with processed_lock:
        if key in processed_messages:
            return

        processed_messages.add(key)

        if len(processed_messages) > 5000:
            processed_messages.clear()
            processed_messages.add(key)

    if is_human_admin(chat.id, user.id):
        return

    if not contains_link(message):
        return

    link = extract_link(message)

    delete_success = False

    try:
        bot.delete_message(
            chat.id,
            message.message_id
        )
        delete_success = True

    except Exception:
        logger.exception(
            "Could not delete the offending message."
        )

    mute_success = False

    if delete_success:
        try:
            mute_member(
                chat.id,
                user.id,
                int(time.time()) + MUTE_DURATION
            )
            mute_success = True

        except Exception:
            logger.exception(
                "Could not mute the member."
            )

    member_name = escape_html(
        get_display_name(user)
    )

    warning_text = (
        "🛡️ <b>ANTI-LINK SECURITY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{member_name}, your message was deleted,\n"
        "links are not allowed in this group.\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

    try:
        warning = bot.send_message(
            chat.id,
            warning_text,
            disable_web_page_preview=True
        )

        delete_message_later(
            warning.chat.id,
            warning.message_id,
            REPORT_DELETE_DELAY
        )

    except Exception:
        logger.exception(
            "Could not send the group warning."
        )

    username = (
        f"@{escape_html(user.username)}"
        if user.username
        else "Not Set"
    )

    group_title = escape_html(
        chat.title or "Unknown Group"
    )

    report = (
        "🛡️ <b>ANTI-LINK SECURITY REPORT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Name:</b> {member_name}\n"
        f"🔗 <b>Username:</b> {username}\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
        f"👥 <b>Group:</b> {group_title}\n"
        f"🆔 <b>Group ID:</b> <code>{chat.id}</code>\n"
        f"🔗 <b>Link:</b> {escape_html(link)}\n"
        f"🗑️ <b>Message Deleted:</b> "
        f"{'YES' if delete_success else 'NO'}\n"
        f"🔇 <b>2-Hour Mute:</b> "
        f"{'SUCCESS' if mute_success else 'FAILED'}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = None

    if mute_success:
        keyboard = InlineKeyboardMarkup()

        keyboard.add(
            InlineKeyboardButton(
                "🔓 UNMUTE MEMBER",
                callback_data=f"unmute:{chat.id}:{user.id}"
            )
        )

    send_admin_report(
        chat.id,
        report,
        reply_markup=keyboard
    )


# ==========================================
# START THE BOT
# ==========================================

if __name__ == "__main__":
    logger.info("Anti-Link Bot is starting...")

    try:
        bot.remove_webhook()

        bot.infinity_polling(
            skip_pending=True,
            timeout=30,
            long_polling_timeout=30,
            allowed_updates=[
                "message",
                "callback_query"
            ]
        )

    except KeyboardInterrupt:
        logger.info("Bot stopped by the user.")

    except Exception:
        logger.exception(
            "The bot stopped unexpectedly."
        )
        raise
