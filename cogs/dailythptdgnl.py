"""
Đếm ngược kỳ thi THPT và ĐGNL (GMT+7), gửi embed theo lịch.
Chỉnh ngày thi & ID kênh trong phần CẤU HÌNH bên dưới.
"""

from __future__ import annotations

import discord
from discord.ext import commands, tasks
from datetime import datetime, time, timezone, timedelta
from typing import Iterable, Optional, Union

from utils.logger import setup_logger

logger = setup_logger(__name__)

GMT7 = timezone(timedelta(hours=7))

# ─── CẤU HÌNH — sửa tại đây ─────────────────────────────────────────────
# Điền "YYYY-MM-DD" khi có lịch; None = không gửi đếm ngược tự động cho kỳ đó
THPT_EXAM_DATE: Optional[str] = "2026-06-11"
DGNL_EXAM_DATE: Optional[str] = "2027-04-05"

# Cả THPT và ĐGNL đều gửi vào chung các kênh sau (Discord Channel ID)
COUNTDOWN_NOTIFY_CHANNEL_IDS: tuple[int, ...] = (1509761407535546419,1509762286523388004)

# Giờ gửi đếm ngược mỗi ngày (múi giờ +7)
NOTIFY_TIMES_GMT7 = (
    time(8, 0, tzinfo=GMT7),
    time(22, 30, tzinfo=GMT7),
)
































def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s or not str(s).strip():
        return None
    try:
        return datetime.strptime(str(s).strip(), "%Y-%m-%d")
    except ValueError:
        logger.warning("Ngày không hợp lệ (cần YYYY-MM-DD): %r", s)
        return None


def _today_gmt7() -> datetime:
    now_gmt7 = datetime.now(timezone.utc).astimezone(GMT7)
    return now_gmt7.replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)


def _days_until(target_naive: datetime) -> int:
    return (target_naive - _today_gmt7()).days


def _build_countdown_embed(
    title: str,
    exam_label: str,
    target: datetime,
    days_left: int,
) -> discord.Embed:
    ts = datetime.now(timezone.utc)
    if days_left < 0:
        return discord.Embed(
            title=f"🎉 {title}",
            description=f"Kỳ **{exam_label}** đã diễn ra.",
            color=discord.Color.green(),
            timestamp=ts,
        ).set_footer(text="Sự kiện đã qua")

    if days_left == 0:
        return discord.Embed(
            title=f"🔥 HÔM NAY: {exam_label}!",
            description=f"⏰ **Hôm nay** là ngày thi **{exam_label}**. Chúc may mắn! 💪",
            color=discord.Color.red(),
            timestamp=ts,
        ).set_footer(text="Ngày thi")

    if days_left <= 3:
        color, urgency = discord.Color.red(), "🚨 Sắp tới rồi — ôn tập và nghỉ ngơi hợp lý."
    elif days_left <= 7:
        color, urgency = discord.Color.orange(), "⚠️ Còn khoảng một tuần."
    elif days_left <= 30:
        color, urgency = discord.Color.gold(), "📢 Còn dưới một tháng."
    else:
        color, urgency = discord.Color.blue(), "📅 Còn khá lâu — giữ nhịp ôn đều."

    return discord.Embed(
        title=f"⏳ Đếm ngược: {exam_label}",
        description=(
            f"📆 Còn **{days_left}** ngày nữa đến **{exam_label}**.\n\n"
            f"{urgency}\n\n"
            f"🎯 Ngày thi: **{target.strftime('%d/%m/%Y')}** (GMT+7)"
        ),
        color=color,
        timestamp=ts,
    ).set_footer(text="Thông báo 08:00 & 23:00 GMT+7")


def _normalize_channel_ids(ids: Union[int, Iterable[int]]) -> tuple[int, ...]:
    if isinstance(ids, int):
        return (ids,)
    return tuple(int(x) for x in ids)


async def _send_countdown_if_due(
    bot: commands.Bot,
    exam_key: str,
    exam_label: str,
    date_str: Optional[str],
    channel_ids: Union[int, Iterable[int]],
) -> None:
    target = _parse_date(date_str)
    if target is None:
        logger.debug("Bỏ qua %s — chưa cấu hình THPT_EXAM_DATE / DGNL_EXAM_DATE", exam_key)
        return

    days_left = _days_until(target)
    embed = _build_countdown_embed(f"Thi {exam_key}", exam_label, target, days_left)
    for channel_id in _normalize_channel_ids(channel_ids):
        channel = bot.get_channel(channel_id)
        if not channel:
            logger.warning("Không tìm thấy kênh %s cho %s", channel_id, exam_key)
            continue
        try:
            await channel.send(embed=embed)
            logger.info("Đã gửi đếm ngược %s → kênh %s (%s ngày)", exam_key, channel_id, days_left)
        except discord.HTTPException as e:
            logger.error("Lỗi gửi đếm ngược %s kênh %s: %s", exam_key, channel_id, e)


class DailyThptDgnl(commands.Cog):
    """Đếm ngược THPT / ĐGNL + lệnh xem cấu hình."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.countdown_thpt_dgnl.start()

    def cog_unload(self) -> None:
        self.countdown_thpt_dgnl.cancel()

    @tasks.loop(time=list(NOTIFY_TIMES_GMT7))
    async def countdown_thpt_dgnl(self) -> None:
        await _send_countdown_if_due(
            self.bot, "THPT", "THPT Quốc gia", THPT_EXAM_DATE, COUNTDOWN_NOTIFY_CHANNEL_IDS
        )
        await _send_countdown_if_due(
            self.bot, "ĐGNL", "Đánh giá năng lực (ĐGNL)", DGNL_EXAM_DATE, COUNTDOWN_NOTIFY_CHANNEL_IDS
        )

    @countdown_thpt_dgnl.before_loop
    async def before_countdown_thpt_dgnl(self) -> None:
        await self.bot.wait_until_ready()
        logger.info(
            "Đếm ngược THPT/ĐGNL — chạy lúc %s (GMT+7)",
            ", ".join(f"{t.hour:02d}:{t.minute:02d}" for t in NOTIFY_TIMES_GMT7),
        )

    @commands.command(name="xemthongbaothi", aliases=["xemdemnguoc", "thithongbao"])
    async def xem_thong_bao_thi(self, ctx: commands.Context) -> None:
        """Xem kênh, giờ gửi, múi giờ và ngày thi (preview đếm ngược)."""
        chans = ", ".join(f"`{cid}`" for cid in COUNTDOWN_NOTIFY_CHANNEL_IDS)
        lines = [
            "**Múi giờ:** GMT+7 (Việt Nam)",
            f"**Giờ gửi tự động:** {', '.join(f'{t.hour:02d}:{t.minute:02d}' for t in NOTIFY_TIMES_GMT7)} mỗi ngày",
            f"**Kênh chung (THPT + ĐGNL):** {chans}",
            "",
            "**THPT**",
            f"‑ Ngày thi: `{THPT_EXAM_DATE or 'chưa đặt — sửa THPT_EXAM_DATE trong dailythptdgnl.py'}`",
            "",
            "**ĐGNL**",
            f"‑ Ngày thi: `{DGNL_EXAM_DATE or 'chưa đặt — sửa DGNL_EXAM_DATE trong dailythptdgnl.py'}`",
            "",
        ]

        for key, label, date_str in (
            ("THPT", "THPT Quốc gia", THPT_EXAM_DATE),
            ("ĐGNL", "Đánh giá năng lực", DGNL_EXAM_DATE),
        ):
            t = _parse_date(date_str)
            if t is None:
                lines.append(f"**Preview {key}:** chưa có ngày — không gửi embed tự động.")
            else:
                d = _days_until(t)
                lines.append(f"**Preview {key}:** còn **{d}** ngày (tính theo ngày hiện tại GMT+7).")

        embed = discord.Embed(
            title="📋 Thông báo đếm ngược THPT & ĐGNL",
            description="\n".join(lines),
            color=discord.Color.teal(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Chỉnh sửa cấu hình trong cogs/dailythptdgnl.py")
        await ctx.send(embed=embed)

    @commands.command(name="testthongbaothi", aliases=["testdemnguoc"])
    @commands.is_owner()
    async def test_thong_bao_thi(self, ctx: commands.Context, mode: str = "here") -> None:
        """🧪 Gửi embed đếm ngược giống lịch tự động (chỉ owner).
        `!testthongbaothi` — gửi vào kênh bạn gõ lệnh.
        `!testthongbaothi kenh` — gửi vào các kênh COUNTDOWN_NOTIFY_CHANNEL_IDS."""
        m = (mode or "here").strip().lower()
        if m in ("here", "day", "đây"):
            targets: list[discord.abc.Messageable] = [ctx.channel]
            where = "kênh lệnh"
        elif m in ("kenh", "kênh", "channels", "all", "config"):
            targets = []
            missing: list[str] = []
            for cid in COUNTDOWN_NOTIFY_CHANNEL_IDS:
                ch = self.bot.get_channel(cid)
                if isinstance(ch, discord.abc.Messageable):
                    targets.append(ch)
                else:
                    missing.append(str(cid))
            if missing:
                await ctx.send(f"⚠️ Không tìm thấy kênh: {', '.join(missing)}")
            if not targets:
                await ctx.send("Không có kênh hợp lệ để gửi.")
                return
            where = "kênh cấu hình"
        else:
            await ctx.send(
                "Dùng: **`!testthongbaothi`** (gửi ở đây) hoặc **`!testthongbaothi kenh`** (gửi vào kênh thông báo)."
            )
            return

        exams = (
            ("THPT", "THPT Quốc gia", THPT_EXAM_DATE),
            ("ĐGNL", "Đánh giá năng lực (ĐGNL)", DGNL_EXAM_DATE),
        )
        sent = 0
        for ch in targets:
            for exam_key, exam_label, date_str in exams:
                target = _parse_date(date_str)
                if target is None:
                    embed = discord.Embed(
                        title=f"🧪 Test · {exam_key}",
                        description="Chưa cấu hình ngày thi trong `dailythptdgnl.py`.",
                        color=discord.Color.light_grey(),
                    )
                    await ch.send(embed=embed)
                    sent += 1
                    continue
                days_left = _days_until(target)
                embed = _build_countdown_embed(f"Thi {exam_key}", exam_label, target, days_left)
                prev = (embed.footer and embed.footer.text) or ""
                embed.set_footer(text=f"{prev} · 🧪 Test ({where})")
                await ch.send(embed=embed)
                sent += 1

        await ctx.send(
            f"✅ Đã gửi **{sent}** embed tới **{len(targets)}** kênh (`{where}`).",
            delete_after=20,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DailyThptDgnl(bot))
