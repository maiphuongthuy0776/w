import random
import discord
from discord.ext import commands

class Tag(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.responses = [
            "gì vậy em guột", 
        ]

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.author == self.bot.user:
            return
        if not message.guild:
            return

        if self.bot.user in message.mentions:
            response = random.choice(self.responses)
            try:
                await message.reply(response)
            except Exception:
                pass

async def setup(bot):
    await bot.add_cog(Tag(bot))
