import discord
from discord.ext import commands

from utils.logger import setup_logger

logger = setup_logger(__name__)

MEMBER_MILESTONE = 70000
NOTIFICATION_CHANNEL_IDS = (1509761407535546419,1509762286523388004)


class FiftyKMem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if guild.member_count != MEMBER_MILESTONE:
            return

        embed = discord.Embed(
            title="🎊 Cột mốc 70.000 thành viên!",
            description=(
                f"✨ Xin chào {member.mention}!\n\n"
                f"Bạn chính là **thành viên thứ {MEMBER_MILESTONE:,}** "
                f"của **{guild.name}** — một con số đáng tự hào! 🥳"
            ),
            color=discord.Color.gold(),
        )

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="🏆 Sự Kiện",
            value=f"`{MEMBER_MILESTONE:,}` thành viên đã tin tưởng và tham gia cộng đồng!",
            inline=False,
        )
        embed.add_field(
            name="📅 Ngày tham gia",
            value=discord.utils.format_dt(member.joined_at or discord.utils.utcnow(), style="F"),
            inline=False,
        )
        embed.set_footer(
            text=f"{guild.name} • Cảm ơn bạn đã đồng hành!",
            icon_url=guild.icon.url if guild.icon else None,
        )

        for cid in NOTIFICATION_CHANNEL_IDS:
            channel = self.bot.get_channel(cid)
            if channel is None or not isinstance(channel, discord.abc.Messageable):
                logger.warning("50kmem: không tìm thấy kênh hoặc không gửi được tin nhắn, id=%s", cid)
                continue
            try:
                await channel.send(
                    content="🎉 **Xin chúc mừng!** 🎉",
                    embed=embed,
                )
            except discord.HTTPException as e:
                logger.error("50kmem: gửi kênh %s lỗi: %s", cid, e)


async def setup(bot: commands.Bot):
    await bot.add_cog(FiftyKMem(bot))
