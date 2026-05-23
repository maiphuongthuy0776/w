import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

import config
from tra_diem_client import tra_diem_sync
from utils.logger import setup_logger

logger = setup_logger(__name__)

def _announce_min_score() -> int:
    return int(getattr(config, "TRADIEM_PUBLIC_ANNOUNCE_MIN", 400))


def _parse_int_score(raw) -> Optional[int]:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", ".")
    try:
        return int(float(s))
    except ValueError:
        return None


def _fmt(raw) -> str:
    if raw is None:
        return "—"
    return str(raw).strip()


def _fmt_ngay_sinh(inner: dict) -> str:
    """Chuỗi ngày sinh hiển thị (dd/mm/yyyy nếu parse được từ API)."""
    for key in (
        "ngaySinh",
        "ngayThangNamSinh",
        "ngaySinhTheoCccd",
        "dateOfBirth",
    ):
        raw = inner.get(key)
        if raw is None:
            continue
        s = str(raw).strip()
        if not s or s in ("0", "null", "None"):
            continue
        if len(s) >= 10 and s[4] == "-" and s[0:4].isdigit():
            try:
                dpart = s[:10]
                return datetime.strptime(dpart, "%Y-%m-%d").strftime("%d/%m/%Y")
            except ValueError:
                return s
        if "/" in s and any(ch.isdigit() for ch in s):
            return s
        if "-" in s and len(s) >= 10 and s[2] == "-":
            try:
                return datetime.strptime(s[:10], "%d-%m-%Y").strftime("%d/%m/%Y")
            except ValueError:
                return s
        return s
    return "—"


def _bot_icon_url(bot_user: Optional[discord.ClientUser]) -> Optional[str]:
    if bot_user is None:
        return None
    return bot_user.display_avatar.url


def _embed_error_lookup(exc: Exception, bot_user: Optional[discord.ClientUser]) -> discord.Embed:
    emb = discord.Embed(
        title="tradiem · Lỗi",
        description=f"Không tra cứu được: `{exc}`",
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_author(name="tradiem", icon_url=_bot_icon_url(bot_user))
    return emb


def _embed_error_api(code, msg: str, bot_user: Optional[discord.ClientUser]) -> discord.Embed:
    emb = discord.Embed(
        title="tradiem · Không có kết quả",
        description=f"Mã `{code}` — {_fmt(msg)}",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_author(name="tradiem", icon_url=_bot_icon_url(bot_user))
    return emb


def _embed_success(inner: dict, bot_user: Optional[discord.ClientUser], footer_suffix: str) -> discord.Embed:
    total_raw = inner.get("diemTongKet")
    total = _parse_int_score(total_raw)
    total_display = _fmt(total_raw)
    ten = _fmt(inner.get("hoVaTen"))

    if total is not None and total >= _announce_min_score():
        color = discord.Color.from_rgb(46, 204, 113)
        accent = "🎉"
        display_name = ten if ten != "—" else "bạn"
        celebration = (
            f"**Chúc mừng {display_name}!** Điểm tổng kết **từ {_announce_min_score()} trở lên** — "
            "thành tích rất tốt, cố gắng tiếp tục phát huy nha!"
        )
    else:
        color = discord.Color.from_rgb(88, 101, 242)
        accent = "📊"
        celebration = "Đây là **điểm tổng kết** theo hồ sơ bạn tra cứu."

    emb = discord.Embed(
        title=f"{accent} Điểm tổng kết",
        description=f"{celebration}\n\n# **{total_display}**",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_author(name="tradiem", icon_url=_bot_icon_url(bot_user))

    sbd = _fmt(inner.get("sbd"))
    ngay_sinh = _fmt_ngay_sinh(inner)
    if ten != "—" or sbd != "—" or ngay_sinh != "—":
        emb.add_field(name="Họ tên", value=ten, inline=True)
        emb.add_field(name="SBD", value=sbd, inline=True)
        emb.add_field(name="Ngày sinh", value=ngay_sinh, inline=True)

    emb.add_field(
        name="Chi tiết môn (tham khảo)",
        value=(
            f"Toán · **{_fmt(inner.get('diemToan'))}**　"
            f"Văn · **{_fmt(inner.get('diemTiengViet'))}**\n"
            f"Anh · **{_fmt(inner.get('diemTiengAnh'))}**　"
            f"KHTN · **{_fmt(inner.get('diemKhoaHocTuNhien'))}**"
        ),
        inline=False,
    )

    emb.set_footer(text=f"Nguồn: thinangluc.vnuhcm.edu.vn · {footer_suffix}")
    return emb


class TraDiem(commands.Cog):
    """Tra cứu điểm thi qua thinangluc.vnuhcm.edu.vn"""

    def __init__(self, bot):
        self.bot = bot
        # Chỉ 1 tra Playwright cùng lúc; tránh nhiều browser → lag / treo máy chủ bot.
        self._tra_mutex = asyncio.Lock()
        self._waiter_count = 0
        self._waiter_count_lock = asyncio.Lock()

    async def _run_tra_sync_queued(
        self,
        notify_queue: Callable[[int], Awaitable[None]],
        work: Callable[[], Awaitable[dict]],
    ) -> dict:
        async with self._waiter_count_lock:
            self._waiter_count += 1
            ahead = self._waiter_count - 1
        try:
            if ahead > 0:
                await notify_queue(ahead)
            async with self._tra_mutex:
                return await work()
        finally:
            async with self._waiter_count_lock:
                self._waiter_count -= 1

    async def _resolve_announce_channel(
        self, ch_id: int
    ) -> Tuple[Optional[discord.abc.Messageable], str]:
        ch = self.bot.get_channel(ch_id)
        if ch is None:
            try:
                ch = await self.bot.fetch_channel(ch_id)
            except discord.HTTPException as e:
                logger.warning("tradiem announce channel not found: %s (%s)", ch_id, e)
                return None, (
                    f"Không truy cập được kênh thông báo (ID `{ch_id}`). "
                    "Kiểm tra bot đã vào đúng server và ID kênh trong config.py."
                )
        if not isinstance(ch, discord.abc.Messageable):
            return None, f"Kênh `{ch_id}` không phải kênh chat."
        if isinstance(ch, discord.abc.GuildChannel):
            me = ch.guild.me
            if me is None:
                return None, "Bot chưa sẵn sàng trong server của kênh thông báo."
            perms = ch.permissions_for(me)
            if not perms.send_messages:
                return None, (
                    f"Bot **thiếu quyền Send Messages** trong {ch.mention}. "
                    "Hãy cấp quyền gửi tin ở kênh đó."
                )
            if not perms.embed_links:
                logger.warning("tradiem announce channel %s: thiếu Embed Links", ch_id)
        return ch, ""

    async def _send_public_high_score(
        self,
        user: discord.abc.User,
        bot_user: Optional[discord.ClientUser],
        inner: dict,
    ) -> Tuple[bool, str]:
        """Gửi embed công khai vào TRADIEM_HIGH_SCORE_CHANNEL_ID."""
        ch_id = getattr(config, "TRADIEM_HIGH_SCORE_CHANNEL_ID", None)
        try:
            ch_id = int(ch_id) if ch_id is not None else None
        except (TypeError, ValueError):
            ch_id = None
        if not ch_id:
            return False, (
                "Chưa cấu hình `TRADIEM_HIGH_SCORE_CHANNEL_ID` trong config.py — "
                "chỉ có tin riêng tư (ephemeral), không đăng kênh công khai."
            )

        ch, err = await self._resolve_announce_channel(ch_id)
        if ch is None:
            return False, err

        ch_label = getattr(ch, "mention", f"<#{ch_id}>")
        emb = _embed_success(inner, bot_user, f"Thông báo công khai · {ch_label}")
        content = f"🎉 **tradiem** · Người tra cứu: {user.mention}"
        try:
            await ch.send(
                content=content,
                embed=emb,
                allowed_mentions=discord.AllowedMentions(users=[user], roles=False, everyone=False),
            )
            logger.info("tradiem public announce sent to channel %s for user %s", ch_id, user.id)
            return True, (
                f"📢 Đã đăng thông báo **công khai** tại {ch_label} "
                f"(điểm từ **{_announce_min_score()}+**). "
                "Tin embed phía trên chỉ **bạn** thấy."
            )
        except discord.HTTPException as e:
            logger.warning("tradiem public announce failed (channel %s): %s", ch_id, e)
            return False, (
                f"Không gửi được vào {ch_label}: `{e}`. "
                "Kiểm tra quyền bot (Send Messages, Embed Links)."
            )

    @app_commands.command(
        name="tradiem",
        description="Tra điểm ĐGNL: kết quả riêng tư; điểm cao đăng thêm vào kênh thông báo (xem config).",
    )
    @app_commands.describe(
        so_bao_danh="CMND/CCCD (theo form web)",
        email="Email đăng ký tra cứu",
    )
    # Tránh lỗi Discord "Unknown Integration" / "Tích hợp không xác định" khi gọi từ DM
    @app_commands.guild_only()
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def tradiem_slash(
        self,
        interaction: discord.Interaction,
        so_bao_danh: str,
        email: str,
    ):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        bot_user = interaction.client.user

        async def _notify_slash(ahead: int) -> None:
            await interaction.followup.send(
                f"⏳ **Hàng chờ tra điểm:** có **{ahead}** yêu cầu đang xử lý trước bạn. "
                "Bot chỉ mở **một** phiên tra cứu cùng lúc để tránh lag.",
                ephemeral=True,
            )

        async def _do_sync() -> dict:
            return await asyncio.to_thread(
                tra_diem_sync,
                so_bao_danh.strip(),
                email.strip(),
            )

        try:
            payload = await self._run_tra_sync_queued(_notify_slash, _do_sync)
        except Exception as e:
            logger.exception("tradiem slash failed")
            await interaction.followup.send(
                embed=_embed_error_lookup(e, bot_user),
                ephemeral=True,
            )
            return

        code = payload.get("code")
        msg = payload.get("msg", "")
        inner = payload.get("data") or {}

        if code != 0:
            await interaction.followup.send(
                embed=_embed_error_api(code, str(msg), bot_user),
                ephemeral=True,
            )
            return

        emb = _embed_success(inner, bot_user, "/tradiem · ephemeral")
        await interaction.followup.send(embed=emb, ephemeral=True)

        total = _parse_int_score(inner.get("diemTongKet"))
        if total is not None and total >= _announce_min_score():
            _, note = await self._send_public_high_score(
                interaction.user, bot_user, inner
            )
            if note:
                await interaction.followup.send(note, ephemeral=True)

    @commands.command(name="tradiem")
    async def tradiem_prefix(
        self,
        ctx: commands.Context,
        so_bao_danh: str,
        email: str,
    ):
        """
        Tra điểm: `!tradiem <số_báo_danh> <email>`
        Ví dụ: `!tradiem 075208003170 minhducle629@gmail.com`
        """

        async def _notify_prefix(ahead: int) -> None:
            await ctx.send(
                f"⏳ **Hàng chờ tra điểm:** có **{ahead}** yêu cầu đang xử lý trước bạn. "
                "Bot chỉ mở **một** phiên tra cứu cùng lúc để tránh lag."
            )

        async def _do_sync() -> dict:
            return await asyncio.to_thread(tra_diem_sync, so_bao_danh, email)

        async with ctx.typing():
            try:
                payload = await self._run_tra_sync_queued(_notify_prefix, _do_sync)
            except Exception as e:
                logger.exception("tradiem prefix failed")
                await ctx.send(embed=_embed_error_lookup(e, self.bot.user))
                return

        code = payload.get("code")
        msg = payload.get("msg", "")
        inner = payload.get("data") or {}

        if code != 0:
            await ctx.send(embed=_embed_error_api(code, str(msg), self.bot.user))
            return

        emb = _embed_success(inner, self.bot.user, "!tradiem")
        await ctx.send(embed=emb)

        total = _parse_int_score(inner.get("diemTongKet"))
        if total is not None and total >= _announce_min_score():
            _, note = await self._send_public_high_score(ctx.author, self.bot.user, inner)
            if note:
                await ctx.send(note)


async def setup(bot):
    await bot.add_cog(TraDiem(bot))
    logger.info("TraDiem cog loaded")
