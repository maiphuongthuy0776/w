import discord
from discord.ext import commands
import config
import os
from datetime import datetime, timezone
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _startup_command_guide_text() -> str:
    try:
        from cogs.game1 import WORD_CHAIN_CHANNEL_IDS as wc_ids
        from cogs.game1 import WCSTOP_VOTES_REQUIRED as wc_stop_votes
    except Exception:
        wc_ids = []
        wc_stop_votes = 4
    wc_line = ", ".join(str(i) for i in wc_ids) if wc_ids else "(cho phép mọi kênh nếu danh sách rỗng)"
    return (
        "\n"
        "========== HƯỚNG DẪN LỆNH (mỗi lần khởi động) ==========\n"
        "Prefix: !\n"
        "— Nối từ tiếng Anh — kênh: cogs/game1.py → WORD_CHAIN_CHANNEL_IDS:\n"
        "    !wcstart [từ]    Mở phiên (1 lần/phiên; cần !wcstop trước khi mở lại)\n"
        f"    !wcstop          Vote dừng phiên — cần {wc_stop_votes} người\n"
        "    (một từ thường trong kênh) Nhập từ khi phiên mở\n"
        "    !wchint          Gợi ý từ tiếp\n"
        "    !wchistory       Từ đã dùng\n"
        "    !wcscore [@user] Điểm\n"
        "    !wcleaderboard   Bảng xếp hạng\n"
        "    !wcstatus        Từ hiện tại / chữ cần nối\n"
        f"    Kênh: {wc_line}\n"
        "— Chủ bot: !sync (sync slash) | !cogs (danh sách cog đã load)\n"
        "— Còn lệnh / và ! khác theo từng module — thử trên server hoặc xem cogs/.\n"
        "========================================================\n"
    )


class MixiBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=discord.Intents.all(),
            help_command=None
        )
        self._logged_startup_guide = False

    async def setup_hook(self):
        # Load cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and filename != '__init__.py':
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f'Loaded extension: {filename}')
                except Exception as e:
                    logger.error(f'Failed to load extension {filename}: {e}')

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logger.info('------')
        if not self._logged_startup_guide:
            self._logged_startup_guide = True
            logger.info(_startup_command_guide_text())

        # Guild sync tức thì cho tất cả server bot đang có mặt
        for guild in self.guilds:
            try:
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                logger.info(f'Guild sync [{guild.name}]: {len(synced)} command(s)')
            except Exception as e:
                logger.error(f'Failed to guild sync [{guild.name}]: {e}')


bot = MixiBot()


# ─── Lệnh sync & debug đặt ngoài class ───────────────────────────────
@bot.command(name="sync")
@commands.is_owner()
async def sync_commands(ctx: commands.Context):
    """!sync — Sync slash commands lên guild hiện tại"""
    global_cmds = bot.tree.get_commands()
    await ctx.send(f"🔍 Tree có **{len(global_cmds)}** commands: {[c.name for c in global_cmds]}")

    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ Đã sync **{len(synced)}** slash command(s) lên guild này!")


@bot.command(name="cogs")
@commands.is_owner()
async def list_cogs(ctx: commands.Context):
    """!cogs — Xem danh sách cogs đã load"""
    loaded = list(bot.cogs.keys())
    await ctx.send(f"📦 Loaded cogs ({len(loaded)}): {loaded}")


if __name__ == '__main__':
    try:
        from utils.playwright_bootstrap import ensure_playwright_ready

        pw_ok, pw_msg = ensure_playwright_ready()
        if pw_ok:
            logger.info("Playwright bootstrap: %s", pw_msg)
        else:
            logger.warning(
                "Playwright bootstrap FAILED (%s) — !tradiem sẽ lỗi cho đến khi cài Chromium",
                pw_msg,
            )
    except Exception as e:
        logger.warning("Playwright bootstrap skipped: %s", e)

    bot.run(config.TOKEN)































