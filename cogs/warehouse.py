"""Kho từ khoá tuỳ chỉnh: !them <tên> <link>, sau đó gõ <tên> để bot trả link.

Tính năng:
  !them  <tên> <link>  — thêm / cập nhật từ khoá (chỉ role được phép)
  !xoa   <tên>         — xoá từ khoá (chỉ role được phép)
  <tên>                — gõ tên thì bot trả link (chỉ user có role hoặc là chủ channel)

Chỉ thành viên có WAREHOUSE_ROLE_IDS mới thấy kết quả.
Người không có role và không phải chủ kênh: bot im lặng (không phản hồi gì).
Lưu trữ: MongoDB (collection warehouse_keywords).
"""

from __future__ import annotations

import config
import discord
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional, Dict, Any, List
from utils.logger import setup_logger

logger = setup_logger(__name__)

MONGO_COLLECTION = "warehouse_keywords"

# ===== CẤU HÌNH ROLE =====
# Thay 123 và 321 bằng ID role thật của server bạn
WAREHOUSE_ROLE_IDS: set[int] = {1469581542841122918,1241969973086388244,1472560579007746079}


def _member_allowed(member: discord.Member) -> bool:
    """Kiểm tra user có role được phép hay không."""
    role_ids = {r.id for r in member.roles}
    return bool(role_ids & WAREHOUSE_ROLE_IDS)


def _is_channel_owner(ctx: commands.Context) -> bool:
    """Kiểm tra user có phải chủ channel không (owner của server hoặc có manage_channels)."""
    if not isinstance(ctx.author, discord.Member):
        return False
    channel = ctx.channel
    # Chủ server luôn được
    if ctx.guild and ctx.guild.owner_id == ctx.author.id:
        return True
    # Có quyền manage_channels trên kênh này
    if isinstance(channel, discord.TextChannel):
        perms = channel.permissions_for(ctx.author)
        return perms.manage_channels
    return False


def _user_can_view(ctx: commands.Context) -> bool:
    """Trả về True nếu user được xem kết quả tra cứu."""
    if not isinstance(ctx.author, discord.Member):
        return False
    return _member_allowed(ctx.author) or _is_channel_owner(ctx)


class Warehouse(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._mongo: Optional[AsyncIOMotorClient] = None
        self._db = None

    async def cog_load(self) -> None:
        if not config.MONGO_URI:
            logger.warning("[WAREHOUSE] MONGO_URI chưa được cấu hình — tính năng kho từ khoá bị tắt")
            return
        self._mongo = AsyncIOMotorClient(
            config.MONGO_URI,
            tls=True,
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=10_000,
        )
        self._db = self._mongo[config.MONGO_DB_NAME]
        await self._db[MONGO_COLLECTION].create_index(
            [("guild_id", 1), ("keyword", 1)], unique=True
        )
        logger.info(
            "[WAREHOUSE] MongoDB đã kết nối — db=%s, collection=%s",
            config.MONGO_DB_NAME,
            MONGO_COLLECTION,
        )

    async def cog_unload(self) -> None:
        if self._mongo:
            self._mongo.close()
            self._mongo = None
            self._db = None

    # ─── Helpers DB ───────────────────────────────────────────────────────────

    async def _get(self, guild_id: int, keyword: str) -> Optional[Dict[str, Any]]:
        if self._db is None:
            return None
        return await self._db[MONGO_COLLECTION].find_one(
            {"guild_id": guild_id, "keyword": keyword.lower().strip()}
        )

    async def _upsert(self, guild_id: int, keyword: str, link: str, author_id: int) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        doc = {
            "guild_id": guild_id,
            "keyword": keyword.lower().strip(),
            "link": link.strip(),
            "updated_by": author_id,
            "updated_at": now,
        }
        await self._db[MONGO_COLLECTION].update_one(
            {"guild_id": guild_id, "keyword": keyword.lower().strip()},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )

    async def _delete(self, guild_id: int, keyword: str) -> int:
        if self._db is None:
            return 0
        result = await self._db[MONGO_COLLECTION].delete_one(
            {"guild_id": guild_id, "keyword": keyword.lower().strip()}
        )
        return result.deleted_count

    async def _list_all(self, guild_id: int) -> List[Dict[str, Any]]:
        if self._db is None:
            return []
        cur = self._db[MONGO_COLLECTION].find({"guild_id": guild_id}).sort("keyword", 1)
        return await cur.to_list(length=500)

    # ─── Lệnh !them ───────────────────────────────────────────────────────────

    @commands.command(name="them")
    async def them_keyword(self, ctx: commands.Context, keyword: str, *, link: str) -> None:
        """!them <tên> <link> — thêm hoặc cập nhật từ khoá vào kho."""
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        # Xoá lệnh của người dùng ngay lập tức (im lặng với người ngoài)
        try:
            await ctx.message.delete()
        except Exception:
            pass

        if not _member_allowed(ctx.author):
            # Im lặng với người không có quyền
            logger.info(
                "[WAREHOUSE] %s không có role → bỏ qua lệnh !them",
                ctx.author,
            )
            return

        if self._db is None:
            await ctx.send("⚠️ Chưa cấu hình MongoDB. Không thể lưu từ khoá.")
            return

        kw = keyword.lower().strip()
        lk = link.strip()
        if not kw or not lk:
            await ctx.send("❌ Cú pháp: `!them <tên> <link>`\nVí dụ: `!them tiki tiki.vn`")
            return

        await self._upsert(ctx.guild.id, kw, lk, ctx.author.id)
        await ctx.send(
            f"✅ Đã lưu: gõ `{discord.utils.escape_markdown(kw)}` → bot sẽ trả về `{discord.utils.escape_markdown(lk)}`",
            delete_after=8,
        )
        logger.info(
            "[WAREHOUSE] upsert guild=%s keyword=%s link=%s by=%s",
            ctx.guild.id, kw, lk, ctx.author.id,
        )

    @them_keyword.error
    async def them_error(self, ctx: commands.Context, error: Exception) -> None:
        try:
            await ctx.message.delete()
        except Exception:
            pass
        if isinstance(error, commands.MissingRequiredArgument):
            if _member_allowed(ctx.author):
                await ctx.send(
                    "❌ Thiếu tham số. Cú pháp: `!them <tên> <link>`\nVí dụ: `!them tiki tiki.vn`",
                    delete_after=8,
                )
            return
        raise error

    # ─── Lệnh !xoa ────────────────────────────────────────────────────────────

    @commands.command(name="xoa")
    async def xoa_keyword(self, ctx: commands.Context, keyword: str) -> None:
        """!xoa <tên> — xoá từ khoá khỏi kho."""
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        try:
            await ctx.message.delete()
        except Exception:
            pass

        if not _member_allowed(ctx.author):
            logger.info(
                "[WAREHOUSE] %s không có role → bỏ qua lệnh !xoa",
                ctx.author,
            )
            return

        if self._db is None:
            await ctx.send("⚠️ Chưa cấu hình MongoDB.")
            return

        kw = keyword.lower().strip()
        deleted = await self._delete(ctx.guild.id, kw)
        if deleted:
            await ctx.send(
                f"🗑️ Đã xoá từ khoá `{discord.utils.escape_markdown(kw)}` khỏi kho.",
                delete_after=8,
            )
            logger.info(
                "[WAREHOUSE] delete guild=%s keyword=%s by=%s",
                ctx.guild.id, kw, ctx.author.id,
            )
        else:
            await ctx.send(
                f"⚠️ Không tìm thấy từ khoá `{discord.utils.escape_markdown(kw)}` trong kho.",
                delete_after=8,
            )

    @xoa_keyword.error
    async def xoa_error(self, ctx: commands.Context, error: Exception) -> None:
        try:
            await ctx.message.delete()
        except Exception:
            pass
        if isinstance(error, commands.MissingRequiredArgument):
            if _member_allowed(ctx.author):
                await ctx.send(
                    "❌ Thiếu tên. Cú pháp: `!xoa <tên>`\nVí dụ: `!xoa tiki`",
                    delete_after=8,
                )
            return
        raise error

    # ─── Lệnh !dskho ──────────────────────────────────────────────────────────

    @commands.command(name="dskho")
    async def dskho(self, ctx: commands.Context) -> None:
        """!dskho — xem danh sách tất cả từ khoá đã lưu trong kho."""
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        try:
            await ctx.message.delete()
        except Exception:
            pass

        if not _member_allowed(ctx.author):
            return

        if self._db is None:
            await ctx.send("⚠️ Chưa cấu hình MongoDB.", delete_after=8)
            return

        rows = await self._list_all(ctx.guild.id)
        if not rows:
            await ctx.send("📭 Kho từ khoá đang trống. Dùng `!them <tên> <link>` để thêm.", delete_after=10)
            return

        lines: List[str] = []
        for i, r in enumerate(rows, 1):
            kw = str(r.get("keyword", "?"))
            lk = str(r.get("link", ""))
            lines.append(f"`{i}.` **{discord.utils.escape_markdown(kw)}** → {lk}")

        header = f"📦 **Kho từ khoá** ({len(rows)} mục):\n"
        chunk: List[str] = []
        size = len(header)

        for line in lines:
            extra = len(line) + 1
            if chunk and size + extra > 1900:
                await ctx.send(header + "\n".join(chunk), delete_after=30)
                chunk = [line]
                size = len(header) + len(line)
            else:
                chunk.append(line)
                size += extra

        if chunk:
            await ctx.send(header + "\n".join(chunk), delete_after=30)

    # ─── Tra cứu tự động khi gõ tên ──────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Lắng nghe tin nhắn thường (không phải lệnh !). Nếu khớp từ khoá → trả link."""
        # Bỏ qua bot
        if message.author.bot:
            return
        # Chỉ trong server
        if message.guild is None or not isinstance(message.author, discord.Member):
            return
        # Bỏ qua nếu DB chưa sẵn
        if self._db is None:
            return

        content = message.content.strip()

        # Bỏ qua nếu là lệnh (bắt đầu bằng !)
        if content.startswith("!"):
            return

        # Chỉ xét tin nhắn ngắn (tên từ khoá thường ngắn)
        if len(content) > 64 or " " in content:
            return

        kw = content.lower()
        doc = await self._get(message.guild.id, kw)
        if doc is None:
            return

        # Kiểm tra quyền xem
        # Tạo giả ctx-like object để dùng lại hàm _user_can_view
        # Ta kiểm tra trực tiếp tại đây
        author = message.author
        channel = message.channel

        has_role = _member_allowed(author)
        is_owner = False
        if message.guild and message.guild.owner_id == author.id:
            is_owner = True
        elif isinstance(channel, discord.TextChannel):
            perms = channel.permissions_for(author)
            is_owner = perms.manage_channels

        if not has_role and not is_owner:
            # Im lặng
            return

        link = str(doc.get("link", "")).strip()
        if not link:
            return

        try:
            await message.channel.send(link)
        except discord.HTTPException as e:
            logger.error("[WAREHOUSE] Lỗi gửi link: %s", e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Warehouse(bot))
