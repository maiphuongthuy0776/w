import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
import asyncio
import config
from utils.logger import setup_logger

logger = setup_logger(__name__)

GMT7 = timezone(timedelta(hours=7))

# =============================================================================
# DANH SÁCH LỊCH GỬI TIN NHẮN TỰ ĐỘNG
# Mỗi entry là một dict với các key:
#   hour        : Giờ gửi (GMT+7, 0-23)
#   minute      : Phút gửi (0-59)
#   message     : Nội dung text (đặt "" nếu chỉ dùng embed)
#   embed_title : Tiêu đề embed (đặt None nếu không dùng embed)
#   embed_desc  : Mô tả embed  (đặt None nếu không dùng embed)
#   embed_color : Màu embed dạng hex, ví dụ 0xe74c3c (None = mặc định)
#   enabled     : True/False để bật/tắt từng lịch
# Kênh nhận tin nhắn được lấy từ config.SCHEDULED_CHANNEL_ID
# =============================================================================
SCHEDULES = [
    # ── TEST: Gửi lúc 00:45 GMT+7 (2 phút nữa) ──────────────────────────
    {
        "hour": 20,
        "minute": 00,
        "message": "https://www.youtube.com/watch?v=SlQR9iu09bQ",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },
    # ── Ví dụ 2: Embed lúc 12:00 trưa ──────────────────────────────────────
    {
        "hour": 2,
        "minute": 0,
        "message": "https://tenor.com/entNMEWm22Q.gif",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },




    
    # ── Thêm lịch mới bên dưới theo cùng định dạng ──────────────────────────
    {
        "hour": 3,
        "minute": 0,
        "message": "https://tenor.com/iRdYComII4B.gif",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },






    {
        "hour": 4,
        "minute": 0,
        "message": "https://tenor.com/sv9iyEGQkI5.gif",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },



   {
        "hour": 5,
        "minute": 1,
        "message": "Where are the Manucians? Let me see your hands! https://youtu.be/611WYDonzTU?si=KPlOmaMSxS7oeQHA",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },


    {
        "hour": 5,
        "minute": 0,
        "message": "https://tenor.com/iS7FIpdqEa6.gif",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },

    {
        "hour": 6,
        "minute": 0,
        "message": "https://tenor.com/bOLE8.gif",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },

    {
        "hour": 7,
        "minute": 0,
        "message": "https://tenor.com/bZsM0.gif",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },

    
    {
        "hour": 10,
        "minute": 0,
        "message": "https://media.discordapp.net/attachments/1439553447384060047/1481426202941198459/image.png?ex=69b3452a&is=69b1f3aa&hm=436a916851ad2ac543f8579ac558b130a6a202bcb79e59816603a8d7dce90d37&=&format=webp&quality=lossless",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },


    
    {
        "hour": 19,
        "minute": 0,
        "message": "https://tenor.com/g6995AkOofB.gif",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },

  

    

   


    {
        "hour": 11,
        "minute": 00,
        "message": "i love u https://cdn.discordapp.com/attachments/1439553447384060047/1480942659697901761/yolo.mp4?ex=69b182d4&is=69b03154&hm=e99668d00d605fa16318a690927be3890962e5de47cb086f166791d4a42c2b3c&",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },

    
    {
        "hour": 15,
        "minute": 00,
        "message": "https://cdn.discordapp.com/attachments/1439553447384060047/1482287072365776965/image.png?ex=69b666e9&is=69b51569&hm=88ed6912f0d638edfb12b4227dde88a53a5c883839a5aca7a7c49cfa75979fff&",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },

    

    {
        "hour": 18,
        "minute": 00,
        "message": "https://media.giphy.com/media/OXt6tCIUlajGsbjhWp/giphy.gif",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },

    
    {
        "hour": 21,
        "minute": 00,
        "message": "https://cdn.discordapp.com/attachments/1439553447384060047/1487443209863823581/1.mp4?ex=69c928f0&is=69c7d770&hm=763107593c8791b43e91aeae3fc824a04a91b9ebce90c46eabf71b90982ecf59&",
        "embed_title": None,
        "embed_desc": None,
        "embed_color": None,
        "enabled": False,   # ← Đổi thành True để bật
    },



]



























































class ScheduledMessages(commands.Cog):
    """Gửi tin nhắn tự động vào các giờ được cài đặt trong SCHEDULES."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sent_today: set = set()
        self._last_reset_day: int = -1
        self.scheduler_loop.start()

    def cog_unload(self):
        self.scheduler_loop.cancel()

    # ── Loop kiểm tra mỗi phút ──────────────────────────────────────────────
    @tasks.loop(minutes=1)
    async def scheduler_loop(self):
        now = datetime.now(GMT7)
        logger.info(
            f"[ScheduledMessages] Tick {now.strftime('%H:%M')} GMT+7 | "
            f"Da gui hom nay: {len(self._sent_today)} lich"
        )

        # Reset trạng thái "đã gửi" khi sang ngày mới
        if now.day != self._last_reset_day:
            self._sent_today.clear()
            self._last_reset_day = now.day
            logger.info(
                f"[ScheduledMessages] Reset trang thai da gui "
                f"(ngay moi: {now.strftime('%d/%m/%Y')})"
            )

        # Lấy danh sách kênh từ config
        channel_ids = config.SCHEDULED_CHANNEL_ID
        if not isinstance(channel_ids, list):
            channel_ids = [channel_ids]

        for entry in SCHEDULES:
            if not entry.get("enabled", True):
                continue

            h, m = entry["hour"], entry["minute"]

            if now.hour != h or now.minute != m:
                continue

            logger.info(
                f"[ScheduledMessages] Khop lich {h:02d}:{m:02d} -- "
                f"bat dau gui vao {len(channel_ids)} kenh"
            )

            for channel_id in channel_ids:
                key = (h, m, channel_id)
                if key in self._sent_today:
                    logger.info(
                        f"[ScheduledMessages] Bo qua kenh {channel_id} (da gui roi)"
                    )
                    continue

                channel = self.bot.get_channel(channel_id)
                if channel is None:
                    logger.warning(
                        f"[ScheduledMessages] Khong tim thay kenh ID={channel_id} "
                        f"(lich {h:02d}:{m:02d}) -- "
                        f"Bot co the chua join server hoac sai ID"
                    )
                    self._sent_today.add(key)
                    continue

                logger.info(
                    f"[ScheduledMessages] Dang gui vao kenh #{channel.name} (ID={channel_id})"
                )
                await self._send_entry(channel, entry)
                self._sent_today.add(key)

    @scheduler_loop.before_loop
    async def before_scheduler(self):
        await self.bot.wait_until_ready()
        now = datetime.now(GMT7)
        seconds_to_next_minute = 60 - now.second

        # Log toàn bộ lịch đang được đăng ký
        enabled = [e for e in SCHEDULES if e.get("enabled", True)]
        disabled = [e for e in SCHEDULES if not e.get("enabled", True)]
        channel_ids = config.SCHEDULED_CHANNEL_ID
        if not isinstance(channel_ids, list):
            channel_ids = [channel_ids]

        logger.info(f"[ScheduledMessages] ══════════════════════════════")
        logger.info(f"[ScheduledMessages] Giờ hiện tại (GMT+7): {now.strftime('%H:%M:%S %d/%m/%Y')}")
        logger.info(f"[ScheduledMessages] Kênh nhận: {channel_ids}")
        logger.info(f"[ScheduledMessages] Tổng lịch: {len(SCHEDULES)} | Bật: {len(enabled)} | Tắt: {len(disabled)}")
        for e in enabled:
            logger.info(f"[ScheduledMessages]   ✅ {e['hour']:02d}:{e['minute']:02d} GMT+7")
        for e in disabled:
            logger.info(f"[ScheduledMessages]   ❌ {e['hour']:02d}:{e['minute']:02d} GMT+7 (disabled)")
        logger.info(f"[ScheduledMessages] Loop bắt đầu sau {seconds_to_next_minute}s (đồng bộ đầu phút)")
        logger.info(f"[ScheduledMessages] ══════════════════════════════")

        await asyncio.sleep(seconds_to_next_minute)

    # ── Hàm gửi một entry ───────────────────────────────────────────────────
    async def _send_entry(self, channel: discord.TextChannel, entry: dict):
        try:
            text         = entry.get("message") or ""
            embed_title  = entry.get("embed_title")
            embed_desc   = entry.get("embed_desc")
            embed_color  = entry.get("embed_color")

            embed = None
            if embed_title is not None or embed_desc is not None:
                color = discord.Color(embed_color) if embed_color else discord.Color.blurple()
                embed = discord.Embed(
                    title=embed_title or "",
                    description=embed_desc or "",
                    color=color,
                    timestamp=datetime.now(timezone.utc),
                )
                embed.set_footer(text="Tin nhắn tự động")

            await channel.send(
                content=text if text else None,
                embed=embed,
            )
            logger.info(
                f"[ScheduledMessages] Đã gửi lịch "
                f"{entry['hour']:02d}:{entry['minute']:02d} → #{channel.name}"
            )
        except Exception as e:
            logger.error(f"[ScheduledMessages] Lỗi khi gửi vào kênh {channel.id}: {e}")

    # ── Command xem danh sách lịch (chỉ owner) ──────────────────────────────
    @commands.command(name="scheduled_list", aliases=["schedulelist", "listschedule"])
    async def scheduled_list(self, ctx: commands.Context):
        allowed_users = [852796371622690856]
        if config.OWNER_ID and config.OWNER_ID.isdigit():
            allowed_users.append(int(config.OWNER_ID))
        if ctx.author.id not in allowed_users:
            await ctx.send("❌ Chỉ owner mới dùng được lệnh này.")
            return

        if not SCHEDULES:
            await ctx.send("📭 Chưa có lịch nào trong `SCHEDULES` của `daily.py`.")
            return

        lines = []
        for i, entry in enumerate(SCHEDULES, start=1):
            status = "✅" if entry.get("enabled", True) else "❌"
            h, m   = entry["hour"], entry["minute"]
            lines.append(f"`{i}.` {status} **{h:02d}:{m:02d}** GMT+7")

        channel_ids = config.SCHEDULED_CHANNEL_ID
        if not isinstance(channel_ids, list):
            channel_ids = [channel_ids]
        ch_str = ", ".join(f"<#{cid}>" for cid in channel_ids)

        embed = discord.Embed(
            title="🕐 Danh sách lịch gửi tin nhắn tự động",
            description="\n".join(lines),
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="📌 Kênh nhận", value=ch_str, inline=False)
        embed.set_footer(text="Chỉnh lịch trong cogs/daily.py → SCHEDULES | Kênh trong config.py → SCHEDULED_CHANNEL_ID")
        await ctx.send(embed=embed)

    # ── Command test gửi tin ngay lập tức ───────────────────────────────────
    @commands.command(name="test_schedule", aliases=["testschedule"])
    async def test_schedule(self, ctx: commands.Context, index: int):
        allowed_users = [852796371622690856]
        if config.OWNER_ID and config.OWNER_ID.isdigit():
            allowed_users.append(int(config.OWNER_ID))
        if ctx.author.id not in allowed_users:
            await ctx.send("❌ Chỉ owner mới dùng được lệnh này.")
            return

        if not SCHEDULES:
            await ctx.send("📭 Chưa có lịch nào trong `SCHEDULES`.")
            return

        if index < 1 or index > len(SCHEDULES):
            await ctx.send(f"❌ Số thứ tự không hợp lệ. Chọn từ 1 đến {len(SCHEDULES)}.")
            return

        entry = SCHEDULES[index - 1]
        h, m = entry["hour"], entry["minute"]
        
        msg = await ctx.send(f"🧪 Đang test lịch `{index}` ({h:02d}:{m:02d})...")

        channel_ids = config.SCHEDULED_CHANNEL_ID
        if not isinstance(channel_ids, list):
            channel_ids = [channel_ids]

        sent_count = 0
        for channel_id in channel_ids:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await self._send_entry(channel, entry)
                sent_count += 1
            else:
                logger.warning(f"[test_schedule] Không tìm thấy kênh ID={channel_id}")

        await ctx.send(f"✅ Đã gửi test lịch `{index}` đến {sent_count}/{len(channel_ids)} kênh!")


async def setup(bot: commands.Bot):
    await bot.add_cog(ScheduledMessages(bot))
