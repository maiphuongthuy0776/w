import discord
from discord.ext import commands
from utils.logger import setup_logger

logger = setup_logger(__name__)

WELCOME_CHANNEL_ID = 1474535485488631911
GUIDE_LINK = "https://discord.com/channels/1184348724999225355/1184348725632581713"


class Instruct(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = self.bot.get_channel(WELCOME_CHANNEL_ID)
        if channel is None:
            logger.warning(f"Không tìm thấy kênh với ID {WELCOME_CHANNEL_ID}")
            return

        embed = discord.Embed(
            title="Chào mừng bạn mới! 🎉",
            description=(
                f"Xin chào {member.mention}! 👋\n\n"
                f"Kênh hướng: {GUIDE_LINK} \n\n"
                f"kênh chat chính https://discord.com/channels/1184348724999225355/1509761407535546419 \n\n"
                f"kenh chat phụ https://discord.com/channels/1184348724999225355/1509762286523388004 \n\n"
                
            ),
            color=discord.Color.green(),
        )
        await channel.send(content=member.mention, embed=embed)
        logger.info(f"Đã gửi hướng dẫn cho thành viên mới: {member} trong kênh {channel.name}")


async def setup(bot):
    await bot.add_cog(Instruct(bot))
