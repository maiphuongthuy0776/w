"""
Quét ảnh (Groq vision): nội dung khiêu dâm hoặc lừa đảo (crypto/c casino giả…).
- Tự động: kênh AUTO_SCAN_CHANNEL_IDS mỗi khi có tin mới có ảnh.
- Report: @mention bot (mọi kênh) — chỉ member có một trong REPORT_AUTHOR_ROLE_IDS mới kích hoạt; có thể reply tin cần quét.
- Sau timeout thành công: ghi data/list.json; xóa tin chứa ảnh vi phạm nếu kênh auto-scan HOẶC tin được quét qua report @mention bot.
- !list: xem danh sách vi phạm (chỉ role REPORT_AUTHOR_ROLE_IDS).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
import discord
from discord.ext import commands

import config
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _out(msg: str, kind: str = "info") -> None:
    """In ra console (stdout) ngay + ghi file logs/bot.log qua logger — dễ thấy khi chạy python bot.py."""
    line = f"[clearspmimage] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)
    if kind == "error":
        logger.error(msg)
    elif kind == "warning":
        logger.warning(msg)
    else:
        logger.info(msg)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

MAX_IMAGES_PER_MESSAGE = 4
MAX_IMAGE_BYTES = 3_800_000
TIMEOUT_DURATION = timedelta(hours=600)

# Cooldown giữa 2 lần báo cáo của cùng 1 người (giây)
REPORT_COOLDOWN_SECONDS = 120 * 60  # 120 phút

# Kênh tự quét mỗi tin nhắn mới (đổi sang Channel ID thật nếu 987/123 là placeholder)
AUTO_SCAN_CHANNEL_IDS: frozenset[int] = frozenset({1411520340508807178})

# Chỉ member có một trong các role này mới được @mention bot để quét ảnh (mọi kênh)
REPORT_AUTHOR_ROLE_IDS: frozenset[int] = frozenset({1469581542841122918,
1472560579007746079,1185158470958333953,1484957377135509667,1349964871462158376,1185184103650312234,1185183734153097296})

# Danh sách vi phạm ảnh (ghi sau timeout thành công); !list đọc file này
VIOLATIONS_JSON_PATH = os.path.join("data", "list.json")


_GROQ_TIMEOUT = aiohttp.ClientTimeout(total=120, connect=25, sock_read=90)

_VISION_PROMPT = """You are a Discord image moderator. Inspect the image(s) and reply with ONLY one JSON object—no markdown, no text outside JSON:
{"violation": <true|false>, "type": "<porn|scam|clean>", "reason": "<one short sentence>"}

Set violation=true if ANY image shows:
- Sexual content: nudity, sexual acts, or clearly pornographic imagery/art.
- Scams: fake crypto/airdrop/giveaway promos, fraudulent casino/gambling sites, or pyramid/investment scams visible in text or graphics.

Set violation=false for ordinary photos, harmless memes, games, study content, or legitimate ads with no scam/crypto-fraud signals."""





















@asynccontextmanager
async def _typing_or_skip(channel: discord.abc.Messageable):
    """Hiện trạng thái 'đang nhập'; nếu API typing lỗi thì vẫn chạy scan một lần."""
    try:
        async with channel.typing():
            yield
    except (discord.HTTPException, discord.ClientException, AttributeError, TypeError) as e:
        logger.debug("[clearspmimage] typing không khả dụng: %s", e)
        yield


def _groq_api_key() -> str:
    return (getattr(config, "GROQ_API_KEY", None) or "").strip()


def _channel_matches_auto_scan(channel: discord.abc.GuildChannel | discord.Thread) -> bool:
    """Khớp kênh text hoặc thread con của kênh đó (forum / thread reply)."""
    if channel.id in AUTO_SCAN_CHANNEL_IDS:
        return True
    if isinstance(channel, discord.Thread):
        parent_id = channel.parent_id
        if parent_id is not None and parent_id in AUTO_SCAN_CHANNEL_IDS:
            return True
    return False


def _message_mentions_bot_user(message: discord.Message, bot_user_id: int) -> bool:
    for u in message.mentions:
        if u.id == bot_user_id:
            return True
    for mid in re.findall(r"<@!?(\d+)>", message.content or ""):
        try:
            if int(mid) == bot_user_id:
                return True
        except ValueError:
            continue
    return False


def _member_has_any_role(member: discord.Member, role_ids: frozenset[int]) -> bool:
    return any(r.id in role_ids for r in member.roles)


def _load_violations_from_disk() -> list[dict[str, Any]]:
    path = VIOLATIONS_JSON_PATH
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            v = data.get("violations")
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    except (json.JSONDecodeError, OSError) as e:
        _out(f"Không đọc được {path}: {e}", "warning")
    return []


def _save_violations_to_disk(entries: list[dict[str, Any]]) -> None:
    path = VIOLATIONS_JSON_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"violations": entries}, f, ensure_ascii=False, indent=2)


def _append_violation_record_sync(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Đọc — thêm entry — ghi (gọi trong thread + lock ở caller)."""
    current = _load_violations_from_disk()
    current.append(entry)
    # Giới hạn kích thước file (giữ mới nhất)
    max_keep = 500
    if len(current) > max_keep:
        current = current[-max_keep:]
    _save_violations_to_disk(current)
    return current


def _list_cmd_role_check(ctx: commands.Context) -> bool:
    if not ctx.guild or not isinstance(ctx.author, discord.Member):
        return False
    return _member_has_any_role(ctx.author, REPORT_AUTHOR_ROLE_IDS)


def _author_has_report_role(message: discord.Message) -> bool:
    guild = message.guild
    if guild is None:
        return False
    author = message.author
    if isinstance(author, discord.Member):
        return _member_has_any_role(author, REPORT_AUTHOR_ROLE_IDS)
    m = guild.get_member(author.id)
    return m is not None and _member_has_any_role(m, REPORT_AUTHOR_ROLE_IDS)


def _is_image_attachment(att: discord.Attachment) -> bool:
    ct = (att.content_type or "").lower()
    if ct.startswith("image/"):
        return True
    fn = (att.filename or "").lower()
    if fn.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".jfif", ".bmp")):
        return True
    if ct == "application/octet-stream" and fn:
        return fn.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".jfif", ".bmp"))
    return False


async def _image_urls_from_message(
    message: discord.Message, session: aiohttp.ClientSession
) -> list[tuple[str, str]]:
    """
    Trả về danh sách (mime, base64_data_without_prefix) tối đa MAX_IMAGES_PER_MESSAGE.
    """
    out: list[tuple[str, str]] = []

    for att in message.attachments:
        if len(out) >= MAX_IMAGES_PER_MESSAGE:
            break
        if not _is_image_attachment(att):
            continue
        if att.size and att.size > MAX_IMAGE_BYTES:
            _out(f"Bỏ qua attachment quá lớn: {att.size} bytes", "warning")
            continue
        try:
            data = await att.read()
        except discord.HTTPException as e:
            _out(f"Không đọc được attachment: {e}", "warning")
            continue
        if len(data) > MAX_IMAGE_BYTES:
            continue
        mime = "image/jpeg"
        if att.content_type and att.content_type.startswith("image/"):
            mime = att.content_type.split(";")[0].strip()
        b64 = base64.standard_b64encode(data).decode("ascii")
        out.append((mime, b64))

    for emb in message.embeds:
        if len(out) >= MAX_IMAGES_PER_MESSAGE:
            break
        url = None
        if emb.image and emb.image.url:
            url = emb.image.url
        elif emb.thumbnail and emb.thumbnail.url:
            url = emb.thumbnail.url
        if not url:
            continue
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    continue
                data = await resp.read()
                ct = resp.headers.get("Content-Type", "image/png")
        except Exception as e:
            _out(f"Tải embed image lỗi: {e}", "warning")
            continue
        if len(data) > MAX_IMAGE_BYTES:
            continue
        mime = ct.split(";")[0].strip() if ct else "image/png"
        if not mime.startswith("image/"):
            mime = "image/png"
        b64 = base64.standard_b64encode(data).decode("ascii")
        out.append((mime, b64))

    for sticker in message.stickers:
        if len(out) >= MAX_IMAGES_PER_MESSAGE:
            break
        url = getattr(sticker, "url", None)
        if not url:
            continue
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    continue
                data = await resp.read()
                ct = resp.headers.get("Content-Type", "image/png")
        except Exception as e:
            _out(f"Tải sticker lỗi: {e}", "warning")
            continue
        if len(data) > MAX_IMAGE_BYTES:
            continue
        mime = ct.split(";")[0].strip() if ct else "image/png"
        if not mime.startswith("image/"):
            mime = "image/png"
        b64 = base64.standard_b64encode(data).decode("ascii")
        out.append((mime, b64))

    return out[:MAX_IMAGES_PER_MESSAGE]


def _parse_groq_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    # Bỏ khối ```json ... ```
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        _out(f"Phản hồi Groq không chứa JSON: {text[:300]!r}", "warning")
        return None
    blob = m.group(0)
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        _out(f"Không parse được JSON từ Groq: {text[:200]!r}", "warning")
        return None


async def _groq_vision_scan(
    session: aiohttp.ClientSession, mime_b64_pairs: list[tuple[str, str]]
) -> dict[str, Any] | None:
    api_key = _groq_api_key()
    if not api_key:
        _out("Thiếu GROQ_API_KEY trong .env / config — không gọi được Groq.", "error")
        return None

    user_parts: list[dict[str, Any]] = [{"type": "text", "text": _VISION_PROMPT}]
    for mime, b64 in mime_b64_pairs:
        data_url = f"data:{mime};base64,{b64}"
        user_parts.append({"type": "image_url", "image_url": {"url": data_url}})

    payload = {
        "model": GROQ_VISION_MODEL,
        "messages": [{"role": "user", "content": user_parts}],
        "temperature": 0.1,
        "max_tokens": 256,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        _out(f"Gọi Groq vision model={GROQ_VISION_MODEL} images={len(mime_b64_pairs)}")
        async with session.post(GROQ_API_URL, headers=headers, json=payload) as resp:
            body = await resp.text()
            if resp.status != 200:
                _out(f"Groq HTTP {resp.status}: {body[:500]!r}", "error")
                return None
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
            parsed = _parse_groq_json(content)
            if parsed is not None:
                _out(f"Groq kết quả violation={parsed.get('violation')} type={parsed.get('type')}")
            return parsed
    except Exception as e:
        _out(f"Groq vision exception: {e!r}", "error")
        return None


def _log_scan_task_done(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        try:
            print(f"[clearspmimage] Pipeline task crash: {exc!r}", flush=True)
        except UnicodeEncodeError:
            print(f"[clearspmimage] Pipeline task crash (encode)", flush=True)
        logger.error("[clearspmimage] Pipeline task crash", exc_info=exc)


class ClearSpamImage(commands.Cog):
    """Vision Groq: kênh chỉ định + report @mention."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._seen: set[int] = set()
        self._violations_io_lock = asyncio.Lock()
        # Lưu thời điểm báo cáo cuối cùng của mỗi người: {user_id: datetime}
        self._report_cooldown: dict[int, datetime] = {}

    def _should_auto_scan(self, message: discord.Message) -> bool:
        if message.author.bot:
            return False
        if not message.guild or not message.channel:
            return False
        ch = message.channel
        if isinstance(ch, (discord.abc.GuildChannel, discord.Thread)):
            return _channel_matches_auto_scan(ch)
        return False

    def _should_report_scan(self, message: discord.Message) -> bool:
        if message.author.bot:
            return False
        if not message.guild:
            return False
        if not _author_has_report_role(message):
            return False
        me = self.bot.user
        if me is None:
            return False
        return _message_mentions_bot_user(message, me.id)

    async def _resolve_scan_context(
        self, message: discord.Message
    ) -> tuple[discord.Message, discord.Member | None] | None:
        """
        Trả về (tin cần quét ảnh, member cần timeout nếu vi phạm).
        """
        guild = message.guild
        if guild is None:
            return None

        if self._should_report_scan(message) and message.reference:
            ref = message.reference.resolved
            if ref is None and message.reference.message_id and isinstance(
                message.channel, discord.TextChannel | discord.Thread | discord.VoiceChannel
            ):
                try:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                except (discord.NotFound, discord.HTTPException):
                    ref = None
            if isinstance(ref, discord.Message) and ref.guild and ref.guild.id == guild.id:
                member = ref.author
                m = guild.get_member(member.id)
                if m is None and not member.bot:
                    try:
                        m = await guild.fetch_member(member.id)
                    except (discord.NotFound, discord.HTTPException):
                        m = None
                return ref, m

        member = message.author
        if isinstance(member, discord.Member):
            return message, member
        m = guild.get_member(member.id)
        if m is None and not member.bot:
            try:
                m = await guild.fetch_member(member.id)
            except (discord.NotFound, discord.HTTPException):
                m = None
        return message, m

    async def _run_scan_pipeline(self, trigger_message: discord.Message) -> None:
        if trigger_message.id in self._seen:
            logger.debug(
                f"[clearspmimage] Bỏ qua tin đã xử lý trigger_id={trigger_message.id}"
            )
            return
        self._seen.add(trigger_message.id)
        if len(self._seen) > 2000:
            self._seen.clear()

        guild = trigger_message.guild
        channel = trigger_message.channel
        if guild is None or not isinstance(channel, discord.abc.Messageable):
            _out("Không có guild/kênh hợp lệ cho pipeline.", "warning")
            return

        mode = "report" if self._should_report_scan(trigger_message) else "auto"
        _out(
            f"Pipeline bắt đầu mode={mode} guild={guild.id} "
            f"channel={channel.id} trigger_msg={trigger_message.id} author={trigger_message.author.id}"
        )

        ctx = await self._resolve_scan_context(trigger_message)
        if ctx is None:
            _out("resolve_scan_context trả về None — bỏ qua.", "warning")
            return
        scan_msg, offender_member = ctx
        _out(
            f"Quét tin scan_msg={scan_msg.id} jump={scan_msg.jump_url} "
            f"offender_id={offender_member.id if offender_member else None}"
        )

        async def _do_scan() -> None:
            async with aiohttp.ClientSession(timeout=_GROQ_TIMEOUT) as session:
                pairs = await _image_urls_from_message(scan_msg, session)
                if not pairs:
                    _out(f"Không có ảnh hợp lệ sau lọc (scan_msg={scan_msg.id}) — dừng.")
                    return
                _out(f"Đã chuẩn bị {len(pairs)} ảnh gửi Groq.")
                result = await _groq_vision_scan(session, pairs)

            if not result:
                _out("Groq không trả kết quả hợp lệ — dừng.", "warning")
                return
            violation = bool(result.get("violation"))
            if not violation:
                _out(f"Ảnh sạch (violation=false) scan_msg={scan_msg.id}")
                return

            typ = str(result.get("type", "unknown"))
            reason = str(result.get("reason", "Vi phạm chính sách ảnh."))[:900]
            _out(
                f"VI PHẠM type={typ} scan_msg={scan_msg.id} reason={reason[:120]!r}",
                "warning",
            )

            author_user = scan_msg.author
            mention = author_user.mention

            embed = discord.Embed(
                title="Phát hiện ảnh vi phạm",
                description=reason,
                color=discord.Color.dark_red(),
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(name="Loại", value=typ, inline=True)
            embed.add_field(name="Tin quét", value=f"[Jump]({scan_msg.jump_url})", inline=True)

            allowed = discord.AllowedMentions(users=[author_user], roles=False, everyone=False)
            try:
                await channel.send(
                    content=f"{mention} — ảnh của bạn bị đánh dấu vi phạm (timeout {TIMEOUT_DURATION}).",
                    embed=embed,
                    allowed_mentions=allowed,
                )
                _out("Đã gửi thông báo vi phạm vào kênh.")
            except discord.HTTPException as e:
                _out(f"Không gửi được thông báo: {e}", "error")

            if offender_member is None or offender_member.bot:
                _out("Không timeout (bot hoặc không resolve được member).")
                return
            until = datetime.now(timezone.utc) + TIMEOUT_DURATION
            try:
                await offender_member.timeout(
                    until,
                    reason="[clearspmimage] ảnh: khiêu dâm hoặc scam (Groq vision)",
                )
                _out(f"Đã timeout member={offender_member.id} đến {until.isoformat()}")
            except discord.Forbidden:
                _out("Không đủ quyền timeout member.", "warning")
                return
            except discord.HTTPException as e:
                _out(f"Timeout thất bại: {e}", "warning")
                return

            entry: dict[str, Any] = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "user_id": offender_member.id,
                "username": str(offender_member),
                "display_name": getattr(offender_member, "display_name", None) or "",
                "guild_id": guild.id,
                "message_id": scan_msg.id,
                "channel_id": scan_msg.channel.id,
                "jump_url": scan_msg.jump_url,
                "violation_type": typ,
                "reason": reason,
                "scan_mode": mode,
                "reporter_id": trigger_message.author.id if mode == "report" else None,
            }
            try:
                async with self._violations_io_lock:
                    await asyncio.to_thread(_append_violation_record_sync, entry)
                _out(f"Đã ghi vi phạm vào {VIOLATIONS_JSON_PATH}")
            except Exception as e:
                _out(f"Ghi {VIOLATIONS_JSON_PATH} lỗi: {e!r}", "error")

            scan_ch = scan_msg.channel
            if isinstance(scan_ch, (discord.abc.GuildChannel, discord.Thread)):
                delete_violating_msg = _channel_matches_auto_scan(scan_ch) or mode == "report"
                if delete_violating_msg:
                    try:
                        await scan_msg.delete()
                        _out(
                            f"Đã xóa tin vi phạm msg={scan_msg.id} "
                            f"({'report @mention' if mode == 'report' else 'kênh auto-scan'})"
                        )
                    except discord.Forbidden:
                        _out("Không đủ quyền xóa tin vi phạm.", "warning")
                    except discord.NotFound:
                        _out("Tin vi phạm đã bị xóa trước đó.", "info")
                    except discord.HTTPException as e:
                        _out(f"Xóa tin vi phạm lỗi: {e}", "warning")

        async with _typing_or_skip(channel):
            await _do_scan()

    @commands.command(name="list")
    @commands.check(_list_cmd_role_check)
    async def violations_list(self, ctx: commands.Context) -> None:
        """!list — danh sách người vi phạm ảnh (đã timeout), từ data/list.json."""
        entries = await asyncio.to_thread(_load_violations_from_disk)
        if not entries:
            await ctx.send("Chưa có bản ghi vi phạm nào trong `data/list.json`.")
            return
        recent = list(reversed(entries))[:25]
        lines: list[str] = []
        for i, row in enumerate(recent, start=1):
            uid = row.get("user_id", "?")
            un = str(row.get("username", ""))[:80] or str(uid)
            ts = str(row.get("timestamp_utc", ""))[:19]
            typ_v = str(row.get("violation_type", ""))[:20]
            jump = str(row.get("jump_url", ""))[:120]
            lines.append(f"`{i}.` **{un}** (`{uid}`) — {typ_v} — {ts}\n↳ {jump}")
        body = "\n\n".join(lines)
        if len(entries) > 25:
            body += f"\n\n_(hiển thị 25/{len(entries)} mục mới nhất)_"
        embed = discord.Embed(
            title="Danh sách vi phạm ảnh (clearspmimage)",
            description=body[:4096] or "(trống)",
            color=discord.Color.orange(),
        )
        await ctx.send(embed=embed)

    @violations_list.error
    async def violations_list_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.CheckFailure):
            await ctx.send(
                "Bạn không có quyền dùng `!list`. Chỉ thành viên có một trong các role báo cáo/quét ảnh mới xem được."
            )
            return
        if isinstance(error, commands.CommandInvokeError) and error.original:
            _out(f"!list lỗi: {error.original!r}", "error")
        raise error

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild:
            return

        stickers = getattr(message, "stickers", None) or []
        has_image_hint = (
            bool(message.attachments)
            or any(e.image or e.thumbnail for e in message.embeds)
            or bool(stickers)
        )

        if self._should_auto_scan(message):
            if not has_image_hint:
                return
            _out(
                f"on_message AUTO ch={message.channel.id} "
                f"parent={getattr(message.channel, 'parent_id', None)} "
                f"msg={message.id} att={len(message.attachments)} stickers={len(stickers)}"
            )
            t = asyncio.create_task(self._run_scan_pipeline(message))
            t.add_done_callback(_log_scan_task_done)
            return

        if self._should_report_scan(message):
            if not has_image_hint and not message.reference:
                return

            # Kiểm tra cooldown 120 phút giữa 2 lần báo cáo
            reporter_id = message.author.id
            now = datetime.now(timezone.utc)
            last_report = self._report_cooldown.get(reporter_id)
            if last_report is not None:
                elapsed = (now - last_report).total_seconds()
                if elapsed < REPORT_COOLDOWN_SECONDS:
                    remaining_minutes = int((REPORT_COOLDOWN_SECONDS - elapsed) / 60) + 1
                    remaining_seconds = int(REPORT_COOLDOWN_SECONDS - elapsed)
                    _out(
                        f"Cooldown báo cáo: user={reporter_id} còn {remaining_minutes} phút "
                        f"({remaining_seconds}s) mới được báo cáo lại."
                    )
                    try:
                        await message.reply(
                            f"⏳ Bạn vừa báo cáo gần đây. Vui lòng chờ thêm **{remaining_minutes} phút** "
                            f"trước khi báo cáo lần tiếp theo.",
                            mention_author=True,
                        )
                    except discord.HTTPException:
                        pass
                    return

            # Ghi lại thời điểm báo cáo
            self._report_cooldown[reporter_id] = now
            # Dọn dict để tránh tràn bộ nhớ (giữ tối đa 5000 entry)
            if len(self._report_cooldown) > 5000:
                cutoff = now - timedelta(seconds=REPORT_COOLDOWN_SECONDS)
                self._report_cooldown = {
                    uid: t for uid, t in self._report_cooldown.items() if t > cutoff
                }

            _out(
                f"on_message REPORT kênh={message.channel.id} msg={message.id} "
                f"ref={message.reference.message_id if message.reference else None}"
            )
            t = asyncio.create_task(self._run_scan_pipeline(message))
            t.add_done_callback(_log_scan_task_done)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ClearSpamImage(bot))
    _out(
        f"Cog đã load — auto_channels={sorted(AUTO_SCAN_CHANNEL_IDS)} "
        f"(gồm thread con của các kênh này) report_author_role_ids={sorted(REPORT_AUTHOR_ROLE_IDS)} (@bot)"
    )
    _out(f"Thư mục làm việc: {os.getcwd()} — thêm log file: logs/bot.log")
