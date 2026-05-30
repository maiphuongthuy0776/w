from datetime import timedelta

import discord
from discord.ext import commands

from utils.logger import setup_logger

logger = setup_logger(__name__)

_MESSAGEABLE_GUILD = (discord.TextChannel, discord.Thread, discord.VoiceChannel)

# --- Cấu hình — chỉnh trực tiếp trong file này ---
# Khớp không phân biệt hoa thường (substring trong tin + chữ trong embed). List rỗng = tắt lọc.
BANNED_WORDS: list[str] = [
    "testbot11","BHHAHAHA","yoooooo watch the girl in vc BHHAHAHA","yoooooo watch","https://discord.com/channels/1184348724999225355/1411448689192603669","trong trường hợp nhóm này bị điều tra","tôi khẳng định mình không liên quan tới nhóm", 
]

# Timeout (phút) — Discord tối đa ~40320 phút (~28 ngày).
BANNED_WORD_TIMEOUT_MINUTES = 36036 

# Thông báo kênh tự xóa sau N giây.
BANNED_WORD_NOTIFY_DELETE_AFTER = 4.0


def _banned_terms() -> list[str]:
    return [w.strip().lower() for w in BANNED_WORDS if isinstance(w, str) and w.strip()]


def _should_bypass(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or member.guild_permissions.manage_messages


def _message_plain_text(message: discord.Message) -> str:
    parts = []
    if message.content and message.content.strip():
        parts.append(message.content.strip())
    for em in message.embeds:
        if em.title:
            parts.append(em.title)
        if em.description:
            parts.append(em.description)
        for f in em.fields:
            if f.name:
                parts.append(f.name)
            if f.value:
                parts.append(f.value)
    return "\n".join(parts).strip()


def _find_banned_matches(text: str, banned: list[str]) -> list[str]:
    """Trả về danh sách mục trong cấu hình đã khớp (không trùng lặp, giữ thứ tự xuất hiện)."""
    if not text or not banned:
        return []
    lower = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    for term in banned:
        if term in lower and term not in seen:
            found.append(term)
            seen.add(term)
    return found


class BannedWords(commands.Cog):
    """Chặn từ/cụm cấm: xóa tin, timeout, thông báo (tự xóa), ghi log rõ nội dung vi phạm."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        banned = _banned_terms()
        if not banned:
            return

        member = message.author
        if not isinstance(member, discord.Member):
            return
        if _should_bypass(member):
            return

        text = _message_plain_text(message)
        if not text:
            return

        matches = _find_banned_matches(text, banned)
        if not matches:
            return

        channel = message.channel
        if not isinstance(channel, _MESSAGEABLE_GUILD):
            return

        minutes = BANNED_WORD_TIMEOUT_MINUTES
        delete_after = BANNED_WORD_NOTIFY_DELETE_AFTER
        preview_log = text.replace("\n", " ")[:800]
        # Log đầy đủ: từ cấm khớp + bản xem trước tin (để điều tra)
        logger.warning(
            "[BANNED_WORDS] Vi phạm — user_id=%s user=%s guild_id=%s channel_id=%s "
            "matched_terms=%s message_preview=%r",
            member.id,
            member,
            message.guild.id,
            channel.id,
            matches,
            preview_log,
        )

        try:
            await message.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            logger.error(
                "[BANNED_WORDS] Không xóa được tin — guild=%s channel=%s user=%s matched=%s",
                message.guild.id,
                channel.id,
                member.id,
                matches,
            )
            return

        terms_display = ", ".join(f"`{discord.utils.escape_markdown(m)}`" for m in matches)
        notice = (
            f"{member.mention} — Tin chứa từ/cụm cấm: {terms_display}. "
            f"Đã timeout **{minutes}** phút."
        )

        try:
            await channel.send(notice, delete_after=delete_after)
        except discord.HTTPException as e:
            logger.error("[BANNED_WORDS] Không gửi được thông báo kênh: %s", e)

        if member.guild_permissions.administrator:
            logger.info(
                "[BANNED_WORDS] Bỏ qua timeout — %s là Admin (tin đã xóa, matched=%s)",
                member.id,
                matches,
            )
            return

        try:
            await member.timeout(
                timedelta(minutes=minutes),
                reason=f"[Từ cấm] Khớp: {', '.join(matches)} — nội dung (rút gọn): {preview_log[:200]}",
            )
            logger.info(
                "[BANNED_WORDS] Đã timeout %s phút — user=%s matched=%s",
                minutes,
                member.id,
                matches,
            )
        except discord.Forbidden:
            logger.error(
                "[BANNED_WORDS] Không timeout được user=%s — cần quyền Moderate Members / vai trò cao hơn bot",
                member.id,
            )
        except Exception as e:
            logger.error("[BANNED_WORDS] Lỗi timeout user=%s: %s", member.id, e)


async def setup(bot: commands.Bot):
    if not bot.intents.message_content:
        logger.warning(
            "[BANNED_WORDS] Bật intent message_content (code + Developer Portal) để lọc từ cấm."
        )
    n = len(_banned_terms())
    logger.info(
        "[BANNED_WORDS] Đã load | %s từ/cụm | timeout=%s phút | thông báo xóa sau %ss",
        n,
        BANNED_WORD_TIMEOUT_MINUTES,
        BANNED_WORD_NOTIFY_DELETE_AFTER,
    )
    await bot.add_cog(BannedWords(bot))
