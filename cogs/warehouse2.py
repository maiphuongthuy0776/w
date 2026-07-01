"""Kho từ khoá tuỳ chỉnh (global pool): !them1 <từ> <nội dung>.

Tính năng:
  !them1 <từ> <nội dung>  — thêm / cập nhật từ khoá (chỉ role được phép)
  !xoa1  <từ>             — xoá từ khoá (chỉ role được phép)
  !dskho1                  — danh sách từ khoá (chỉ role được phép)

Khi người dùng có role được theo dõi nhắn tin chứa từ khoá bất kỳ đâu trong câu,
bot tự động trả nội dung.

Tất cả server dùng chung một kho (global pool).
Chỉ thành viên có WAREHOUSE_ROLE_IDS mới thêm/xoá/xem danh sách.
Lưu trữ: MongoDB (collection warehouse2_keywords).
"""

from __future__ import annotations

import config
import discord
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional, Dict, Any, List
from utils.logger import setup_logger

logger = setup_logger(__name__)

MONGO_COLLECTION = "warehouse2_keywords"

# Guild ID cố định cho global pool — tất cả server dùng chung một kho
_GLOBAL_GUILD_ID = 0

# Role được phép dùng lệnh
WAREHOUSE_ROLE_IDS: set[int] = {
    1469579723196727441,1484957377135509667,1472560579007746079, 1241969973086388244,
}

# Chỉ tự động theo dõi / trả lời keyword từ thành viên có các role này
WATCHED_ROLE_IDS: set[int] = {
    1469579723196727441,1484957377135509667,1472560579007746079, 1241969973086388244,
}


def _member_allowed(member: discord.Member) -> bool:
    role_ids = {r.id for r in member.roles}
    return bool(role_ids & WAREHOUSE_ROLE_IDS)


def _member_watched(member: discord.Member) -> bool:
    role_ids = {r.id for r in member.roles}
    return bool(role_ids & WATCHED_ROLE_IDS)


class Warehouse2(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._mongo: Optional[AsyncIOMotorClient] = None
        self._db = None
        self._cache: Dict[str, str] = {}

    async def cog_load(self) -> None:
        if not config.MONGO_URI:
            logger.warning("[WAREHOUSE2] MONGO_URI chưa được cấu hình — tắt")
            return

        self._mongo = AsyncIOMotorClient(
            config.MONGO_URI,
            tls=True,
            tlsAllowInvalidCertificates=True,
            serverSelectionTimeoutMS=10_000,
        )
        self._db = self._mongo[config.MONGO_DB_NAME]

        await self._db[MONGO_COLLECTION].create_index(
            [("guild_id", 1), ("keyword", 1)],
            unique=True,
        )

        await self._rebuild_cache()

        logger.info(
            "[WAREHOUSE2] MongoDB đã kết nối — db=%s, collection=%s, cache=%d từ",
            config.MONGO_DB_NAME,
            MONGO_COLLECTION,
            len(self._cache),
        )

    async def cog_unload(self) -> None:
        if self._mongo:
            self._mongo.close()
            self._mongo = None
            self._db = None

        self._cache.clear()

    # ─── Cache ────────────────────────────────────────────────────────────

    async def _rebuild_cache(self) -> None:
        if self._db is None:
            return

        self._cache.clear()
        cur = self._db[MONGO_COLLECTION].find({"guild_id": _GLOBAL_GUILD_ID})

        async for doc in cur:
            kw = str(doc.get("keyword", "")).lower().strip()
            content = str(doc.get("content", "")).strip()

            if kw and content:
                self._cache[kw] = content

    # ─── Helpers DB ───────────────────────────────────────────────────────

    async def _get(self, keyword: str) -> Optional[Dict[str, Any]]:
        if self._db is None:
            return None

        return await self._db[MONGO_COLLECTION].find_one(
            {
                "guild_id": _GLOBAL_GUILD_ID,
                "keyword": keyword.lower().strip(),
            }
        )

    async def _upsert(self, keyword: str, content: str, author_id: int) -> None:
        from datetime import datetime, timezone

        if self._db is None:
            return

        now = datetime.now(timezone.utc)
        kw = keyword.lower().strip()
        ct = content.strip()

        doc = {
            "guild_id": _GLOBAL_GUILD_ID,
            "keyword": kw,
            "content": ct,
            "updated_by": author_id,
            "updated_at": now,
        }

        await self._db[MONGO_COLLECTION].update_one(
            {
                "guild_id": _GLOBAL_GUILD_ID,
                "keyword": kw,
            },
            {
                "$set": doc,
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

        self._cache[kw] = ct

    async def _delete(self, keyword: str) -> int:
        if self._db is None:
            return 0

        kw = keyword.lower().strip()

        result = await self._db[MONGO_COLLECTION].delete_one(
            {
                "guild_id": _GLOBAL_GUILD_ID,
                "keyword": kw,
            }
        )

        if result.deleted_count:
            self._cache.pop(kw, None)

        return result.deleted_count

    async def _list_all(self) -> List[Dict[str, Any]]:
        if self._db is None:
            return []

        cur = (
            self._db[MONGO_COLLECTION]
            .find({"guild_id": _GLOBAL_GUILD_ID})
            .sort("keyword", 1)
        )

        return await cur.to_list(length=500)

    # ─── Lệnh !them1 ──────────────────────────────────────────────────────

    @commands.command(name="them1")
    async def them1_keyword(
        self,
        ctx: commands.Context,
        keyword: str,
        *,
        content: str,
    ) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        try:
            await ctx.message.delete()
        except Exception:
            pass

        if not _member_allowed(ctx.author):
            logger.info("[WAREHOUSE2] %s không có role → bỏ qua !them1", ctx.author)
            return

        if self._db is None:
            await ctx.send("⚠️ Chưa cấu hình MongoDB. Không thể lưu.")
            return

        kw = keyword.lower().strip()
        ct = content.strip()

        if not kw or not ct:
            await ctx.send(
                "❌ Cú pháp: `!them1 <từ> <nội dung>`\n"
                "Ví dụ: `!them1 abc tôi là abc`",
                delete_after=8,
            )
            return

        await self._upsert(kw, ct, ctx.author.id)

        await ctx.send(
            f"✅ Đã lưu: từ khoá `{discord.utils.escape_markdown(kw)}` → "
            f"`{discord.utils.escape_markdown(ct[:200])}`"
            + ("…" if len(ct) > 200 else ""),
            delete_after=8,
        )

        logger.info("[WAREHOUSE2] upsert keyword=%s by=%s", kw, ctx.author.id)

    @them1_keyword.error
    async def them1_error(self, ctx: commands.Context, error: Exception) -> None:
        try:
            await ctx.message.delete()
        except Exception:
            pass

        if isinstance(error, commands.MissingRequiredArgument):
            if isinstance(ctx.author, discord.Member) and _member_allowed(ctx.author):
                await ctx.send(
                    "❌ Thiếu tham số. Cú pháp: `!them1 <từ> <nội dung>`\n"
                    "Ví dụ: `!them1 abc tôi là abc`",
                    delete_after=8,
                )
            return

        raise error

    # ─── Lệnh !xoa1 ───────────────────────────────────────────────────────

    @commands.command(name="xoa1")
    async def xoa1_keyword(self, ctx: commands.Context, keyword: str) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        try:
            await ctx.message.delete()
        except Exception:
            pass

        if not _member_allowed(ctx.author):
            logger.info("[WAREHOUSE2] %s không có role → bỏ qua !xoa1", ctx.author)
            return

        if self._db is None:
            await ctx.send("⚠️ Chưa cấu hình MongoDB.")
            return

        kw = keyword.lower().strip()
        deleted = await self._delete(kw)

        if deleted:
            await ctx.send(
                f"🗑️ Đã xoá từ khoá `{discord.utils.escape_markdown(kw)}`.",
                delete_after=8,
            )
            logger.info("[WAREHOUSE2] delete keyword=%s by=%s", kw, ctx.author.id)
        else:
            await ctx.send(
                f"⚠️ Không tìm thấy từ khoá `{discord.utils.escape_markdown(kw)}`.",
                delete_after=8,
            )

    @xoa1_keyword.error
    async def xoa1_error(self, ctx: commands.Context, error: Exception) -> None:
        try:
            await ctx.message.delete()
        except Exception:
            pass

        if isinstance(error, commands.MissingRequiredArgument):
            if isinstance(ctx.author, discord.Member) and _member_allowed(ctx.author):
                await ctx.send(
                    "❌ Thiếu tên. Cú pháp: `!xoa1 <từ>`\n"
                    "Ví dụ: `!xoa1 abc`",
                    delete_after=8,
                )
            return

        raise error

    # ─── Lệnh !dskho1 ────────────────────────────────────────────────────

    @commands.command(name="dskho1")
    async def dskho1(self, ctx: commands.Context) -> None:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            return

        try:
            await ctx.message.delete()
        except Exception:
            pass

        if not _member_allowed(ctx.author):
            return

        if not self._cache:
            await ctx.send(
                "📭 Kho từ khoá đang trống. Dùng `!them1 <từ> <nội dung>` để thêm.",
                delete_after=10,
            )
            return

        lines: List[str] = []

        for i, (kw, ct) in enumerate(sorted(self._cache.items()), 1):
            display_ct = ct[:100] + ("…" if len(ct) > 100 else "")
            lines.append(
                f"`{i}.` **{discord.utils.escape_markdown(kw)}** → "
                f"{discord.utils.escape_markdown(display_ct)}"
            )

        header = f"📦 **Kho từ khoá (global)** ({len(lines)} mục):\n"
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

    # ─── Tra cứu tự động khi nhắn tin ────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if message.guild is None:
            return

        if not isinstance(message.author, discord.Member):
            return

        # Chỉ theo dõi tin nhắn từ thành viên có role được chỉ định
        if not _member_watched(message.author):
            return

        if not self._cache:
            return

        content = message.content.strip()

        if not content or content.startswith("!"):
            return

        lowered_content = content.lower()

        matched: Optional[str] = None

        # Ưu tiên keyword dài nhất để tránh match thiếu chính xác
        for kw in sorted(self._cache, key=len, reverse=True):
            if kw in lowered_content:
                matched = kw
                break

        if matched is None:
            return

        reply = self._cache[matched]

        try:
            await message.channel.send(reply)
        except discord.HTTPException as e:
            logger.error("[WAREHOUSE2] Lỗi gửi: %s", e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Warehouse2(bot))
