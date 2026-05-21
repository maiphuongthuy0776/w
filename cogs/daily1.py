# -*- coding: utf-8 -*-
"""
Cog: gửi tin quảng cáo tư vấn ngành học vào các kênh cố định mỗi 30 phút.
"""

import discord
from discord.ext import commands, tasks

from utils.logger import setup_logger

logger = setup_logger(__name__)

CHANNEL_1_LINK = (
    "https://discord.com/channels/1184348724999225355/1442515721111212052"
)



# Kênh thứ ba: ID trong tin + gửi tin vào kênh này (đổi 123 thành snowflake thật nếu cần)
EXTRA_CHANNEL_ID = "1112"

# Các kênh nhận bản tin quảng cáo (cùng nội dung)
BROADCAST_CHANNEL_IDS = (1446866616452386856,)


def _ad_message() -> str:
    return (
        "Quảng cáo\n\n"
        f"Kênh 1: {CHANNEL_1_LINK}\n"
    )


async def _resolve_messageable(
    bot: commands.Bot, channel_id: int
) -> discord.abc.Messageable | None:
    ch = bot.get_channel(channel_id)
    if ch is None:
        try:
            ch = await bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            logger.warning(
                "[tinhnang1] Không truy cập được kênh %s: %s",
                channel_id,
                e,
            )
            return None
    if not isinstance(ch, discord.abc.Messageable):
        logger.warning(
            "[tinhnang1] ID %s không phải kênh gửi tin được.",
            channel_id,
        )
        return None
    return ch


class Tinhnang1(commands.Cog):
    """Định kỳ gửi quảng cáo vào các kênh chat."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        if not self.ad_broadcast.is_running():
            self.ad_broadcast.start()
        logger.info(
            "[tinhnang1] Quảng cáo mỗi 30 phút → kênh %s",
            BROADCAST_CHANNEL_IDS,
        )

    async def cog_unload(self) -> None:
        self.ad_broadcast.cancel()

    @tasks.loop(minutes=61)
    async def ad_broadcast(self) -> None:
        text = _ad_message()
        for cid in BROADCAST_CHANNEL_IDS:
            channel = await _resolve_messageable(self.bot, cid)
            if channel is None:
                continue
            try:
                await channel.send(text)
            except discord.HTTPException as e:
                logger.error(
                    "[tinhnang1] Gửi quảng cáo thất bại (kênh %s): %s",
                    cid,
                    e,
                )

    @ad_broadcast.before_loop
    async def before_ad_broadcast(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tinhnang1(bot))
