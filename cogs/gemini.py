from __future__ import annotations

import os
import re

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from utils.logger import setup_logger

logger = setup_logger(__name__)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
MAX_PROMPT_CHARS = 1200
MAX_REPLY_CHARS = 900
SYSTEM_PROMPT = "Bạn là bot Discord nói tiếng Việt.Bạn tên Rambo, trả lời vào ý chính"


def _api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def _api_url() -> str:
    model = os.getenv("GEMINI_MODEL", GEMINI_MODEL).strip() or GEMINI_MODEL
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={_api_key()}"


def _shorten(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    short = "\n".join(lines[:4]) if lines else text.strip()
    return short[:MAX_REPLY_CHARS].strip()


class GeminiChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.timeout = aiohttp.ClientTimeout(total=90, connect=15, sock_read=75)

    async def _ask_gemini(self, prompt: str, author: discord.abc.User) -> str | None:
        if not _api_key():
            return "Chưa có GEMINI_API_KEY trong file .env."

        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": f"Người hỏi: {author.display_name}\nNội dung:\n{prompt[:MAX_PROMPT_CHARS]}",
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1000,
            },
        }

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(_api_url(), json=payload) as resp:
                    if resp.status != 200:
                        logger.error("[GEMINI] HTTP %s: %s", resp.status, await resp.text())
                        return None
                    data = await resp.json()
                    parts = data["candidates"][0]["content"].get("parts", [])
                    answer = "\n".join(part.get("text", "") for part in parts).strip()
                    return _shorten(answer) if answer else None
        except Exception as e:
            logger.error("[GEMINI] Lỗi gọi Gemini: %s", e)
            return None

    @commands.hybrid_command(name="gemini", description="Chat ngắn với Gemini")
    @app_commands.describe(prompt="Nội dung cần hỏi")
    async def gemini(self, ctx: commands.Context, *, prompt: str):
        async with ctx.typing():
            answer = await self._ask_gemini(prompt, ctx.author)
        await ctx.reply(answer or "Gì vậy em guột", mention_author=False)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not self.bot.user:
            return
        if self.bot.user not in message.mentions:
            return

        text = re.sub(rf"<@!?{self.bot.user.id}>", "", message.content).strip()
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            await message.reply(
                "Hỏi gì hỏi đi em guột!",
                mention_author=False,
            )
            return

        try:
            async with message.channel.typing():
                answer = await self._ask_gemini(text, message.author)
        except (discord.ClientException, TypeError, NotImplementedError):
            answer = await self._ask_gemini(text, message.author)

        if not answer:
            await message.reply("Gemini đang lỗi, thử lại sau.", mention_author=False)
            return

        for i, chunk in enumerate(_chunks(answer)):
            if i == 0:
                await message.reply(chunk, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
            else:
                await message.channel.send(chunk, allowed_mentions=discord.AllowedMentions.none())


def _chunks(text: str, size: int = MAX_REPLY_CHARS) -> list[str]:
    if len(text) <= size:
        return [text]
    out: list[str] = []
    current = ""
    for part in text.split("\n"):
        if len(current) + len(part) + 1 > size:
            if current:
                out.append(current)
                current = ""
            while len(part) > size:
                out.append(part[:size])
                part = part[size:]
        current = f"{current}\n{part}".strip() if current else part
    if current:
        out.append(current)
    return out


async def setup(bot: commands.Bot):
    await bot.add_cog(GeminiChat(bot))
