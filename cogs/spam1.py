from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import discord
from discord.ext import commands


WARNING_REPEAT_COUNT = 2
TIMEOUT_REPEAT_COUNT = 4
REPEAT_WINDOW = timedelta(seconds=30)
TIMEOUT_DURATION = timedelta(hours=1)

MONITORED_CHANNEL_IDS = {
    1509761407535546419,
    1509764695676944474,
    1509762286523388004,
}


@dataclass
class SpamState:
    last_content: str = ""
    repeat_count: int = 0
    first_repeat_at: datetime | None = None


class Spam1(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._states: dict[tuple[int, int], SpamState] = {}

    @staticmethod
    def _normalize_content(content: str) -> str:
        return " ".join(content.split()).casefold()

    def _state_for(self, message: discord.Message) -> SpamState:
        key = (message.guild.id, message.author.id)
        return self._states.setdefault(key, SpamState())

    @staticmethod
    def _reset_state(state: SpamState) -> None:
        state.last_content = ""
        state.repeat_count = 0
        state.first_repeat_at = None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return

        if message.channel.id not in MONITORED_CHANNEL_IDS:
            return

        content = self._normalize_content(message.content)
        state = self._state_for(message)
        now = discord.utils.utcnow()

        if not content:
            self._reset_state(state)
            return

        # Nếu nội dung khác tin trước đó thì bắt đầu chuỗi mới
        if content != state.last_content:
            state.last_content = content
            state.repeat_count = 1
            state.first_repeat_at = now
            return

        # Nếu cùng nội dung nhưng đã quá 30 giây thì reset chuỗi
        if state.first_repeat_at is None or now - state.first_repeat_at > REPEAT_WINDOW:
            state.last_content = content
            state.repeat_count = 1
            state.first_repeat_at = now
            return

        # Cùng nội dung và vẫn nằm trong 30 giây
        state.repeat_count += 1

        if state.repeat_count == WARNING_REPEAT_COUNT:
            await message.channel.send(
                f"{message.author.mention} vui lòng không spam",
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=False,
                ),
            )
            return

        if state.repeat_count < TIMEOUT_REPEAT_COUNT:
            return

        member = message.author
        if not isinstance(member, discord.Member):
            return

        try:
            await member.timeout(
                TIMEOUT_DURATION,
                reason=f"Spam cùng một nội dung {TIMEOUT_REPEAT_COUNT} lần trong 30 giây",
            )
            await message.channel.send(
                f"{member.mention} đã bị timeout 1 giờ vì spam cùng một nội dung {TIMEOUT_REPEAT_COUNT} lần trong 30 giây.",
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    roles=False,
                    everyone=False,
                ),
            )
        except discord.Forbidden:
            await message.channel.send(
                "Bot không đủ quyền để timeout người dùng này.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            await message.channel.send(
                "Không thể timeout người dùng này lúc này.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        finally:
            self._reset_state(state)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Spam1(bot))
