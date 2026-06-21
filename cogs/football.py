from datetime import datetime, timedelta, timezone

import aiohttp
import discord
from discord.ext import commands, tasks

from utils.logger import setup_logger


logger = setup_logger(__name__)


# Add your free football-data.org token here later.
FOOTBALL_DATA_TOKEN = "c30b90394a9549839c30fdb0631d7ccb"

FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"
WORLD_CUP_COMPETITION_CODE = "WC"
WORLD_CUP_SEASON = 2026

# Replace these with full Discord channel IDs if 123 / 231 are placeholders.
NOTIFY_CHANNEL_IDS = [1486759905431130175,1509761407535546419]

LOCAL_TZ = timezone(timedelta(hours=7))
NOTIFY_BEFORE = timedelta(minutes=5)
CHECK_INTERVAL_SECONDS = 60
CACHE_REFRESH_INTERVAL = timedelta(minutes=60)
ERROR_RETRY_INTERVAL = timedelta(minutes=5)
REQUEST_TIMEOUT_SECONDS = 20


class Football(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session = None
        self._fixtures = []
        self._sent_fixture_ids = set()
        self._last_fetch_at = None
        self._last_fetch_failed = False
        self._missing_key_logged = False
        self.world_cup_notifier.start()

    def cog_unload(self):
        self.world_cup_notifier.cancel()
        if self._session and not self._session.closed:
            self.bot.loop.create_task(self._session.close())

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def world_cup_notifier(self):
        token = FOOTBALL_DATA_TOKEN.strip()
        if not token:
            if not self._missing_key_logged:
                logger.warning(
                    "[Football] football-data.org token missing. "
                    "Add it to FOOTBALL_DATA_TOKEN in cogs/football.py."
                )
                self._missing_key_logged = True
            return

        self._missing_key_logged = False
        await self._refresh_fixtures_if_needed(token)
        await self._send_due_notifications()

    @world_cup_notifier.before_loop
    async def before_world_cup_notifier(self):
        await self.bot.wait_until_ready()
        logger.info(
            "[Football] World Cup 2026 notifier started. Channels=%s, notify_before=%s minutes",
            NOTIFY_CHANNEL_IDS,
            int(NOTIFY_BEFORE.total_seconds() // 60),
        )

    @commands.command(name="football", aliases=["wc", "worldcup"])
    async def football(self, ctx: commands.Context):
        """Xem cac tran World Cup 2026 trong 24 gio toi."""
        token = FOOTBALL_DATA_TOKEN.strip()
        if not token:
            await ctx.send("Chua cau hinh `FOOTBALL_DATA_TOKEN` trong `cogs/football.py`.")
            return

        async with ctx.typing():
            await self._refresh_fixtures_if_needed(token)
            upcoming = self._fixtures_in_next_24_hours()

        if not upcoming:
            await ctx.send("Khong co tran World Cup 2026 nao trong 24 gio toi.")
            return

        embed = self._build_upcoming_embed(upcoming)
        await ctx.send(embed=embed)
        logger.info(
            "[Football] !football requested by %s (%s), returned %s match(es)",
            ctx.author,
            ctx.author.id,
            len(upcoming),
        )

    async def _session_or_create(self):
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _refresh_fixtures_if_needed(self, token):
        now = datetime.now(timezone.utc)
        retry_after = ERROR_RETRY_INTERVAL if self._last_fetch_failed else CACHE_REFRESH_INTERVAL

        if self._last_fetch_at and now - self._last_fetch_at < retry_after:
            return

        self._last_fetch_at = now
        try:
            fixtures = await self._fetch_world_cup_fixtures(token)
        except Exception as exc:
            self._last_fetch_failed = True
            logger.error("[Football] Failed to refresh fixtures: %s", exc, exc_info=True)
            return

        self._fixtures = fixtures
        self._last_fetch_failed = False
        logger.info("[Football] Cached %s upcoming World Cup 2026 fixture(s)", len(fixtures))

    async def _fetch_world_cup_fixtures(self, token):
        session = await self._session_or_create()
        url = f"{FOOTBALL_DATA_BASE_URL}/competitions/{WORLD_CUP_COMPETITION_CODE}/matches"
        headers = {"X-Auth-Token": token}
        params = {
            "season": WORLD_CUP_SEASON,
        }

        async with session.get(url, headers=headers, params=params) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                raise RuntimeError(f"football-data.org HTTP {response.status}: {data}")

        fixtures = []
        now = datetime.now(timezone.utc)
        for item in data.get("matches", []):
            kickoff = self._parse_kickoff(item.get("utcDate"))
            if kickoff is None or kickoff <= now:
                continue

            status = item.get("status")
            if status not in ("SCHEDULED", "TIMED"):
                continue

            home = self._team_name(item.get("homeTeam") or {})
            away = self._team_name(item.get("awayTeam") or {})
            fixture_id = item.get("id") or f"{home}-{away}-{int(kickoff.timestamp())}"

            fixtures.append(
                {
                    "id": fixture_id,
                    "kickoff": kickoff,
                    "home": home,
                    "away": away,
                    "round": self._round_name(item),
                    "venue": "TBD",
                    "city": "",
                }
            )

        fixtures.sort(key=lambda fixture: fixture["kickoff"])
        return fixtures

    @staticmethod
    def _parse_kickoff(raw_date):
        if not raw_date:
            return None

        kickoff = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        return kickoff.astimezone(timezone.utc)

    @staticmethod
    def _team_name(team_data):
        return team_data.get("shortName") or team_data.get("name") or "TBD"

    @staticmethod
    def _round_name(match_data):
        stage = (match_data.get("stage") or "World Cup 2026").replace("_", " ").title()
        group = match_data.get("group")
        matchday = match_data.get("matchday")

        parts = [stage]
        if group:
            parts.append(group.replace("_", " ").title())
        if matchday:
            parts.append(f"Matchday {matchday}")
        return " - ".join(parts)

    def _fixtures_in_next_24_hours(self):
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=24)
        return [
            fixture
            for fixture in self._fixtures
            if now < fixture["kickoff"] <= end
        ]

    async def _send_due_notifications(self):
        now = datetime.now(timezone.utc)
        window_seconds = NOTIFY_BEFORE.total_seconds()

        for fixture in self._fixtures:
            fixture_id = fixture["id"]
            if fixture_id in self._sent_fixture_ids:
                continue

            seconds_until_kickoff = (fixture["kickoff"] - now).total_seconds()
            if seconds_until_kickoff <= 0:
                continue
            if seconds_until_kickoff > window_seconds:
                break

            await self._notify_channels(fixture)
            self._sent_fixture_ids.add(fixture_id)

    async def _notify_channels(self, fixture):
        embed = self._build_match_embed(fixture)
        content = (
            f"World Cup 2026: {fixture['home']} vs {fixture['away']} "
            f"starts in about 5 minutes."
        )

        for channel_id in NOTIFY_CHANNEL_IDS:
            channel = await self._get_messageable_channel(channel_id)
            if channel is None:
                logger.warning("[Football] Cannot find/send to channel ID=%s", channel_id)
                continue

            try:
                await channel.send(content=content, embed=embed)
                logger.info(
                    "[Football] Sent World Cup notification for fixture %s to channel %s",
                    fixture["id"],
                    channel_id,
                )
            except discord.Forbidden:
                logger.error("[Football] Missing permission to send in channel ID=%s", channel_id)
            except Exception as exc:
                logger.error("[Football] Failed to send to channel ID=%s: %s", channel_id, exc)

    async def _get_messageable_channel(self, channel_id):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None

        if not hasattr(channel, "send"):
            return None
        return channel

    @staticmethod
    def _build_match_embed(fixture):
        kickoff_local = fixture["kickoff"].astimezone(LOCAL_TZ)
        venue = fixture["venue"]
        if fixture["city"]:
            venue = f"{venue}, {fixture['city']}"

        embed = discord.Embed(
            title="World Cup 2026 match reminder",
            description=f"**{fixture['home']} vs {fixture['away']}**",
            color=discord.Color.gold(),
            timestamp=fixture["kickoff"],
        )
        embed.add_field(name="Kickoff", value=kickoff_local.strftime("%H:%M %d/%m/%Y GMT+7"), inline=False)
        embed.add_field(name="Round", value=fixture["round"], inline=True)
        embed.add_field(name="Venue", value=venue, inline=True)
        embed.set_footer(text="Source: football-data.org")
        return embed

    @staticmethod
    def _build_upcoming_embed(fixtures):
        now_local = datetime.now(LOCAL_TZ)
        lines = []
        for index, fixture in enumerate(fixtures[:15], start=1):
            kickoff_local = fixture["kickoff"].astimezone(LOCAL_TZ)
            lines.append(
                f"`{index}.` **{fixture['home']} vs {fixture['away']}**\n"
                f"Time: `{kickoff_local.strftime('%H:%M %d/%m/%Y')} GMT+7`\n"
                f"Round: {fixture['round']}"
            )

        if len(fixtures) > 15:
            lines.append(f"...and {len(fixtures) - 15} more match(es).")

        embed = discord.Embed(
            title="World Cup 2026 - Next 24 hours",
            description="\n\n".join(lines),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(
            text=f"Source: football-data.org | Checked at {now_local.strftime('%H:%M %d/%m/%Y')} GMT+7"
        )
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(Football(bot))
