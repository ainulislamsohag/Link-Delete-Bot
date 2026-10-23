import os
import re
import time
import threading
import html
import telebot

from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# ================= CONFIGURATION =================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

BOT_NAME = "ANTI LINK BOT"
OWNER_USERNAME = "ainulbhai"
OWNER_URL = "https://t.me/ainulbhai"

MUTE_DURATION = 2 * 60 * 60
REPORT_DELETE_DELAY = 180

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

processed_messages = set()
processed_lock = threading.Lock()


# ================= LINK DETECTION =================

LINK_PATTERN = re.compile(
    r"(?i)(?:"
    r"https?://\S+|"
    r"www\.\S+|"
    r"t\.me/\S+|"
    r"telegram\.me/\S+|"
    r"telegram\.dog/\S+|"
    r"\b[a-z0-9-]+\.(?:"
    r"com|net|org|info|biz|xyz|site|online|me|io|co|"
    r"app|dev|bd|in|us|uk|top|click|link|live|store|"
    r"shop|tech|cloud|pro|gg|edu|gov|tv|ai|fun|"
    r"website|space|today|world|digital|services"
    r")\b\S*"
    r")"
)


# ================= KEYBOARDS =================

def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2,
    )

    keyboard.row(
        KeyboardButton("➕ Add Bot in group➕")
    )

    keyboard.row(
        KeyboardButton("❓ HOW TO USE ❓"),
        KeyboardButton("📞 Support"),
    )

    return keyboard


def get_add_group_keyboard():
    keyboard = InlineKeyboardMarkup()
    bot_username = bot.get_me().username

    keyboard.add(
        InlineKeyboardButton(
            "➕ ADD BOT TO GROUP ➕",
            url=f"https://t.me/{bot_username}?startgroup=true",
        )
    )

    return keyboard


def get_owner_keyboard():
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            "👑 CONTACT OWNER 👑",
            url=OWNER_URL,
        )
    )

    return keyboard


def get_unmute_keyboard(chat_id, user_id):
    keyboard = InlineKeyboardMarkup()

    keyboard.add(
        InlineKeyboardButton(
            "🔓 UNMUTE MEMBER",
            callback_data=f"unmute:{chat_id}:{user_id}",
        )
    )

    return keyboard


# ================= HELPER FUNCTIONS =================

def get_display_name(user):
    name = user.first_name or "Unknown"

    if user.last_name:
        name += f" {user.last_name}"

    return name


def is_human_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")

    except Exception as error:
        print(
            f"ADMIN CHECK FAILED | Chat: {chat_id} | "
            f"User: {user_id} | Error: {error}"
        )
        return False


def contains_link(message):
    text = message.text or message.caption or ""

    if LINK_PATTERN.search(text):
        return True

    if message.text is not None:
        entities = message.entities or []
    else:
        entities = message.caption_entities or []

    for entity in entities:
        if entity.type in ("url", "text_link"):
            return True

        if entity.type == "mention":
            mention = text[
                entity.offset:entity.offset + entity.length
            ]

            if mention.startswith("@"):
                return True

    return False


def extract_link(message):
    text = message.text or message.caption or ""

    match = LINK_PATTERN.search(text)

    if match:
        return match.group(0)

    if message.text is not None:
        entities = message.entities or []
    else:
        entities = message.caption_entities or []

    for entity in entities:
        if entity.type == "text_link" and entity.url:
            return entity.url

        if entity.type == "url":
            return text[
                entity.offset:entity.offset + entity.length
            ]

        if entity.type == "mention":
            mention = text[
                entity.offset:entity.offset + entity.length
            ]

            if mention.startswith("@"):
                return mention

    return "Link detected"


def delete_message_later(chat_id, message_id, delay):
    def task():
        time.sleep(delay)

        try:
            bot.delete_message(chat_id, message_id)

        except Exception as error:
            print(
                f"SCHEDULED DELETE FAILED | Chat: {chat_id} | "
                f"Message: {message_id} | Error: {error}"
            )

    threading.Thread(target=task, daemon=True).start()


# ================= MUTE MEMBER =================

def mute_member(chat_id, user_id):
    try:
        # Check bot permissions
        bot_id = bot.get_me().id
        bot_member = bot.get_chat_member(chat_id, bot_id)

        if bot_member.status != "administrator":
            print("MUTE ERROR: Bot is not an administrator.")
            return False

        if not getattr(bot_member, "can_restrict_members", False):
            print("MUTE ERROR: Restrict Members permission is disabled.")
            return False

        # Check target member
        target = bot.get_chat_member(chat_id, user_id)

        if target.status in ("administrator", "creator"):
            print("MUTE ERROR: Cannot mute a group admin or owner.")
            return False

        # Mute for 2 hours
        until_date = int(time.time()) + 7200

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

        result = bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
            until_date=until_date,
            use_independent_chat_permissions=True
        )

        print(
            f"MUTE RESULT: {result} | "
            f"Chat: {chat_id} | User: {user_id}"
        )

        return bool(result)

    except Exception as error:
        print(
            f"MUTE ERROR: {type(error).__name__}: {error}"
        )
        return False


# ================= ADMIN REPORT =================

# ================= ADMIN REPORT =================

def send_admin_report(chat_id, user, link, deleted, muted):
    try:
        chat = bot.get_chat(chat_id)

        group_title = html.escape(chat.title or "Unknown Group")
        safe_name = html.escape(get_display_name(user))
        safe_username = html.escape(
            f"@{user.username}" if user.username else "Not Set"
        )
        safe_link = html.escape(link)

        report = (
            "🚨 <b>ANTI LINK BOT REPORT</b> 🚨\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Name:</b> {safe_name}\n"
            f"🧑‍💻 <b>Username:</b> {safe_username}\n"
            f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 <b>Group:</b> {group_title}\n"
            f"🆔 <b>Group ID:</b> <code>{chat_id}</code>\n"
            f"🔗 <b>Detected Link:</b> <code>{safe_link}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🗑️ <b>Message Deleted:</b> "
            f"{'✅ YES' if deleted else '❌ NO'}\n"
            f"🔇 <b>Muted for 2 hours:</b> "
            f"{'✅ SUCCESS' if muted else '❌ FAILED'}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

        bot.send_message(
            chat_id=OWNER_USERNAME,
            text=report,
            reply_markup=get_unmute_keyboard(chat_id, user.id),
        )

        print(
            f"ADMIN REPORT SENT | Owner: @{OWNER_USERNAME} | "
            f"Group: {chat_id} | User: {user.id}"
        )

    except Exception as error:
        print(
            f"ADMIN REPORT FAILED | "
            f"Error Type: {type(error).__name__} | "
            f"Details: {error}"
        )


# ================= START COMMAND =================

@bot.message_handler(
    commands=["start"],
    chat_types=["private"],
)
def start_command(message):
    welcome_text = (
        f"👋 <b>WELCOME TO {BOT_NAME}!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🛡️ Your group protection assistant!\n\n"
        "🔗 Automatically detects and removes links "
        "sent by regular members.\n"
        "🔇 If a link message is deleted successfully, "
        "the bot will try to mute the member for 2 hours.\n\n"
        "👇 <b>Choose an option below:</b>"
    )

    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=get_main_keyboard(),
    )


# ================= ADD BOT BUTTON =================

@bot.message_handler(
    func=lambda message: (
        message.chat.type == "private"
        and message.text == "➕ Add Bot in group➕"
    )
)
def add_bot_button(message):
    text = (
        "➕ <b>ADD ANTI LINK BOT TO YOUR GROUP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>"
        "1️⃣ Click the button below.\n"
        "2️⃣ Select your group.\n"
        "3️⃣ Add the bot as an administrator.\n"
        "4️⃣ Enable Delete Messages and Restrict Members permissions."
        "</blockquote>\n\n"
        "✅ Your group will then be protected by the bot."
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=get_add_group_keyboard(),
    )


# ================= HOW TO USE BUTTON =================

@bot.message_handler(
    func=lambda message: (
        message.chat.type == "private"
        and message.text == "❓ HOW TO USE ❓"
    )
)
def how_to_use_button(message):
    text = (
        "❓ <b>HOW TO USE ANTI LINK BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>"
        "➊ Add the bot to your group.\n"
        "➋ Promote the bot to administrator.\n"
        "➌ Enable these permissions:\n"
        "   • 🗑️ Delete Messages\n"
        "   • 🔇 Restrict Members\n\n"
        "➍ The bot will try to delete link messages "
        "sent by regular members.\n"
        "➎ If deletion succeeds, it will try to mute "
        "the member for 2 hours."
        "</blockquote>\n\n"
        "📌 <b>Important:</b> Group administrators "
        "are exempt from link moderation."
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=get_owner_keyboard(),
    )


# ================= SUPPORT BUTTON =================

@bot.message_handler(
    func=lambda message: (
        message.chat.type == "private"
        and message.text == "📞 Support"
    )
)
def support_button(message):
    support_text = (
        "📞 <b>SUPPORT CENTER</b>\n"
        "──────────────────────────\n\n"
        "💠 <b>If You Face Any Problem:</b>\n\n"
        "<blockquote>"
        "🔴 Don’t worry! Our team is here to assist you.\n"
        "🟠 Contact the owner for help.\n"
        "🟡 Describe your issue clearly so it can be resolved faster."
        "</blockquote>\n\n"
        "✨ Thank you for your patience and trust!\n\n"
        "<b>Contact The Owner Directly -</b>"
    )

    bot.send_message(
        message.chat.id,
        support_text,
        reply_markup=get_owner_keyboard(),
    )


# ================= UNMUTE CALLBACK =================

@bot.callback_query_handler(
    func=lambda call: (
        call.data is not None
        and call.data.startswith("unmute:")
    )
)
def unmute_callback(call):
    try:
        _, chat_id, user_id = call.data.split(":")

        chat_id = int(chat_id)
        user_id = int(user_id)

        # The button is sent privately to the owner.
        # Check the clicking user's admin status in the target group.
        if not is_human_admin(chat_id, call.from_user.id):
            bot.answer_callback_query(
                call.id,
                "⛔ Only group admins can use this button.",
                show_alert=True,
            )
            return

        # Verify that the bot can restrict members.
        bot_member = bot.get_chat_member(
            chat_id,
            bot.get_me().id,
        )

        if (
            bot_member.status != "administrator"
            or not getattr(
                bot_member, "can_restrict_members", False
            )
        ):
            bot.answer_callback_query(
                call.id,
                "❌ The bot needs Restrict Members permission.",
                show_alert=True,
            )
            return

        # Restore standard send permissions.
        # This does not restore any custom permissions set previously.
        bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions={
                "can_send_messages": True,
                "can_send_audios": True,
                "can_send_documents": True,
                "can_send_photos": True,
                "can_send_videos": True,
                "can_send_video_notes": True,
                "can_send_voice_notes": True,
                "can_send_polls": True,
                "can_send_other_messages": True,
                "can_add_web_page_previews": True,
            },
            use_independent_chat_permissions=True,
        )

        bot.answer_callback_query(
            call.id,
            "✅ Member unmuted successfully!",
        )

        confirmation = bot.send_message(
            call.message.chat.id,
            "🔓 <b>MEMBER UNMUTED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"👮 <b>Action by:</b> "
            f"{html.escape(get_display_name(call.from_user))}\n"
            "━━━━━━━━━━━━━━━━━━━━",
        )

        delete_message_later(
            confirmation.chat.id,
            confirmation.message_id,
            REPORT_DELETE_DELAY,
        )

    except Exception as error:
        print(f"UNMUTE FAILED: {error}")

        try:
            bot.answer_callback_query(
                call.id,
                "❌ Could not unmute. Check bot permissions and logs.",
                show_alert=True,
            )
        except Exception:
            pass


# ================= ANTI-LINK MODERATION =================

@bot.message_handler(
    content_types=[
        "text",
        "photo",
        "video",
        "document",
        "animation",
        "audio",
        "voice",
        "video_note",
        "sticker",
    ],
    func=lambda message: (
        message.chat.type in ("group", "supergroup")
    ),
)
def anti_link_moderation(message):
    if not message.from_user or message.from_user.is_bot:
        return

    # Exempt group administrators and the owner.
    if is_human_admin(
        message.chat.id,
        message.from_user.id,
    ):
        return

    if not contains_link(message):
        return

    message_key = (
        message.chat.id,
        message.message_id,
    )

    with processed_lock:
        if message_key in processed_messages:
            return

        processed_messages.add(message_key)

    link = extract_link(message)
    deleted = False
    muted = False

    # Delete the offending message first.
    try:
        bot.delete_message(
            message.chat.id,
            message.message_id,
        )
        deleted = True

    except Exception as error:
        print(
            f"DELETE FAILED | Chat: {message.chat.id} | "
            f"Message: {message.message_id} | Error: {error}"
        )

    # Mute only after successful deletion.
    if deleted:
        muted = mute_member(
            message.chat.id,
            message.from_user.id,
        )

    try:
        warning_text = (
            "🚨 <b>LINK DETECTED!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Member:</b> "
            f"{html.escape(get_display_name(message.from_user))}\n"
            "🔗 Sending links is not allowed here.\n"
            f"🗑️ <b>Message Deleted:</b> "
            f"{'✅ YES' if deleted else '❌ NO'}\n"
            f"🔇 <b>Muted for 2 hours:</b> "
            f"{'✅ YES' if muted else '❌ NO'}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )

        warning = bot.send_message(
            message.chat.id,
            warning_text,
        )

        delete_message_later(
            warning.chat.id,
            warning.message_id,
            REPORT_DELETE_DELAY,
        )

    except Exception as error:
        print(f"WARNING MESSAGE FAILED: {error}")

    send_admin_report(
        message.chat.id,
        message.from_user,
        link,
        deleted,
        muted,
    )


# ================= RUN BOT =================

print(f"{BOT_NAME} is running...")

bot.infinity_polling(
    skip_pending=True,
    timeout=30,
    long_polling_timeout=30,
    )
