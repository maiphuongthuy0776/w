import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta, time

from utils.logger import setup_logger

logger = setup_logger(__name__)

GMT7 = timezone(timedelta(hours=7))

# --- Cấu hình (chỉnh trong file này) ---
# Thời điểm công bố điểm thi ĐGNL đợt 1 (theo thông báo chính thức), múi GMT+7
DIEM_DGNL_DOT1_AT = datetime(2026, 6, 6, 8, 30, 0, tzinfo=GMT7)

# Link tra điểm (dán URL đầy đủ khi có, ví dụ "https://...")
TRA_DIEM_URL = "https://thinangluc.vnuhcm.edu.vn/dgnl/search-result-exam"

# Kênh nhận tin đếm ngược mỗi ngày
CHANNEL_IDS = [1509761407535546419]

# Giờ gửi bản đếm ngược mỗi ngày — 8h30 và 22h (GMT+7)
DAILY_POST_TIMES = (
    time(hour=8, minute=30, tzinfo=GMT7),
    time(hour=23, minute=30, tzinfo=GMT7),
)


def _format_delta(target: datetime, now: datetime) -> tuple[str, discord.Color]:
    if now >= target:
        return (
            "Đã qua thời điểm công bố điểm theo lịch đã cấu hình. "
            "Cập nhật `DIEM_DGNL_DOT1_AT` nếu có ngày giờ mới.",
            discord.Color.dark_gray(),
        )
    delta = target - now
    total = int(delta.total_seconds())
    days, r = divmod(total, 86400)
    hours, r = divmod(r, 3600)
    minutes, seconds = divmod(r, 60)
    lines = []
    if days:
        lines.append(f"**{days}** ngày")
    if hours:
        lines.append(f"**{hours}** giờ")
    if minutes:
        lines.append(f"**{minutes}** phút")
    if not lines or (days == 0 and hours == 0 and minutes == 0):
        lines.append(f"**{seconds}** giây")
    desc = "Còn lại: " + ", ".join(lines)
    if days >= 7:
        color = discord.Color.green()
    elif days >= 1:
        color = discord.Color.gold()
    else:
        color = discord.Color.orange()
    return desc, color


def _build_embed() -> discord.Embed:
    now = datetime.now(GMT7)
    target = DIEM_DGNL_DOT1_AT
    date_fmt = target.strftime("%d/%m/%Y %H:%M")
    desc, color = _format_delta(target, now)

    embed = discord.Embed(
        title="Đếm ngược công bố điểm thi ĐGNL đợt 2",
        description=(
            f"**Thời điểm dự kiến (GMT+7):** `{date_fmt}`\n\n"
            f"{desc}"
        ),
        color=color,
    )
    link = TRA_DIEM_URL.strip()
    if link:
        embed.add_field(
            name="Tra điểm",
            value=f"[Mở link tra điểm]({link})",
            inline=False,
        )
    embed.set_footer(text=f"Hôm nay: {now.strftime('%d/%m/%Y %H:%M')} (GMT+7)")
    return embed


class DailyDiemThi(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("[DailyDiemThi] Cog loaded")

    async def cog_load(self) -> None:
        self.daily_dgnl_countdown.start()

    async def cog_unload(self) -> None:
        self.daily_dgnl_countdown.cancel()

    @tasks.loop(time=DAILY_POST_TIMES)
    async def daily_dgnl_countdown(self) -> None:
        embed = _build_embed()
        for cid in CHANNEL_IDS:
            ch = self.bot.get_channel(cid)
            if ch is None:
                try:
                    ch = await self.bot.fetch_channel(cid)
                except Exception as e:
                    logger.warning(f"[DailyDiemThi] Khong tim thay kenh {cid}: {e}")
                    continue
            if not isinstance(ch, discord.abc.Messageable):
                logger.warning(f"[DailyDiemThi] Kenh {cid} khong gui duoc tin nhan")
                continue
            try:
                await ch.send(embed=embed)
                logger.info(f"[DailyDiemThi] Da gui dem nguoc toi kenh {cid}")
            except discord.Forbidden:
                logger.error(f"[DailyDiemThi] Bot khong co quyen gui o kenh {cid}")
            except Exception as e:
                logger.error(f"[DailyDiemThi] Loi gui kenh {cid}: {e}", exc_info=True)

    @daily_dgnl_countdown.before_loop
    async def _before_daily(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DailyDiemThi(bot))
