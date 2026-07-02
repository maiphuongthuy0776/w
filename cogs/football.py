from __future__ import annotations

from datetime import datetime, timedelta, timezone

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import ui

from utils.logger import setup_logger


logger = setup_logger(__name__)


# Add your free football-data.org token here later.
FOOTBALL_DATA_TOKEN = "c30b90394a9549839c30fdb0631d7ccb"

FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"
WORLD_CUP_COMPETITION_CODE = "WC"
WORLD_CUP_SEASON = 2026

# Replace these with full Discord channel IDs if 123 / 231 are placeholders.
NOTIFY_CHANNEL_IDS = [1486759905431130175, 1509761407535546419]

LOCAL_TZ = timezone(timedelta(hours=7))
PREDICTION_OPEN_BEFORE = timedelta(minutes=1380)
NOTIFY_BEFORE = PREDICTION_OPEN_BEFORE
CHECK_INTERVAL_SECONDS = 180
CACHE_REFRESH_INTERVAL = timedelta(minutes=60)
ERROR_RETRY_INTERVAL = timedelta(minutes=5)
REQUEST_TIMEOUT_SECONDS = 20

# How often to check for finished matches to announce predictions
RESULT_CHECK_INTERVAL = timedelta(minutes=10)

def _prediction_window_status(fixture: dict) -> tuple[bool, str | None]:
    """Return whether prediction is currently allowed for this fixture."""
    now = datetime.now(timezone.utc)
    seconds_until_kickoff = (fixture["kickoff"] - now).total_seconds()
    open_seconds = PREDICTION_OPEN_BEFORE.total_seconds()
    open_minutes = int(open_seconds // 60)
    kickoff_local = fixture["kickoff"].astimezone(LOCAL_TZ)
    open_at_local = (fixture["kickoff"] - PREDICTION_OPEN_BEFORE).astimezone(LOCAL_TZ)

    if seconds_until_kickoff <= 0:
        return (
            False,
            (
                f"Trận **{fixture['home']} vs {fixture['away']}** đã bắt đầu, "
                "không thể dự đoán nữa."
            ),
        )

    if seconds_until_kickoff > open_seconds:
        return (
            False,
            (
                f"Chưa mở dự đoán cho trận **{fixture['home']} vs {fixture['away']}**.\n"
                f"Chỉ được dự đoán trong **{open_minutes} phút** trước khi trận bắt đầu.\n"
                f"Dự đoán mở lúc: `{open_at_local.strftime('%H:%M %d/%m/%Y GMT+7')}`.\n"
                f"Giờ bóng lăn: `{kickoff_local.strftime('%H:%M %d/%m/%Y GMT+7')}`."
            ),
        )

    return True, None


# --------------------------------------------------------------------------- #
#  Prediction UI                                                              #
# --------------------------------------------------------------------------- #

class PredictModal(ui.Modal, title="Dự đoán tỷ số trận đấu"):
    """Modal nhập tỷ số dự đoán."""

    home_score = ui.TextInput(
        label="Bàn thắng đội nhà",
        placeholder="Ví dụ: 2",
        min_length=1,
        max_length=2,
        required=True,
    )
    away_score = ui.TextInput(
        label="Bàn thắng đội khách",
        placeholder="Ví dụ: 1",
        min_length=1,
        max_length=2,
        required=True,
    )

    def __init__(self, fixture: dict, predictions: dict):
        super().__init__()
        self.fixture = fixture

        # predictions: {fixture_id: {user_id: (home, away)}}
        self.predictions = predictions

        self.title = f"Dự đoán: {fixture['home']} vs {fixture['away']}"

    async def on_submit(self, interaction: discord.Interaction):
        fid = self.fixture["id"]
        user_id = interaction.user.id

        allowed, reason = _prediction_window_status(self.fixture)

        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        # Chặn nếu user đã dự đoán trận này rồi
        if fid in self.predictions and user_id in self.predictions[fid]:
            old_h, old_a = self.predictions[fid][user_id]
            await interaction.response.send_message(
                (
                    "Bạn đã dự đoán trận này rồi, không thể dự đoán lại.\n"
                    f"Dự đoán của bạn: **{self.fixture['home']} {old_h} - {old_a} {self.fixture['away']}**"
                ),
                ephemeral=True,
            )
            return

        try:
            h = int(self.home_score.value.strip())
            a = int(self.away_score.value.strip())

            if h < 0 or a < 0:
                raise ValueError

        except ValueError:
            await interaction.response.send_message(
                "Tỷ số không hợp lệ. Vui lòng nhập số nguyên không âm.",
                ephemeral=True,
            )
            return

        if fid not in self.predictions:
            self.predictions[fid] = {}

        # Lưu dự đoán duy nhất của user cho trận này
        self.predictions[fid][user_id] = (h, a)

        await interaction.response.send_message(
            f"Bạn đã dự đoán **{self.fixture['home']} {h} - {a} {self.fixture['away']}**. Chúc may mắn!",
            ephemeral=True,
        )

        logger.info(
            "[Football] %s (%s) predicted %s %d-%d %s",
            interaction.user,
            interaction.user.id,
            self.fixture["home"],
            h,
            a,
            self.fixture["away"],
        )


class PredictButton(ui.Button):
    def __init__(self, fixture: dict, predictions: dict):
        super().__init__(
            label="Dự đoán tỷ số",
            style=discord.ButtonStyle.primary,
            emoji="⚽",
            custom_id=f"predict_{fixture['id']}",
        )
        self.fixture = fixture
        self.predictions = predictions

    async def callback(self, interaction: discord.Interaction):
        fid = self.fixture["id"]
        user_id = interaction.user.id

        allowed, reason = _prediction_window_status(self.fixture)

        if not allowed:
            await interaction.response.send_message(reason, ephemeral=True)
            return

        # Chặn ngay khi bấm nút nếu user đã dự đoán trận này
        if fid in self.predictions and user_id in self.predictions[fid]:
            old_h, old_a = self.predictions[fid][user_id]
            await interaction.response.send_message(
                (
                    "Bạn đã dự đoán trận này rồi, không thể dự đoán lại.\n"
                    f"Dự đoán của bạn: **{self.fixture['home']} {old_h} - {old_a} {self.fixture['away']}**"
                ),
                ephemeral=True,
            )
            return

        modal = PredictModal(fixture=self.fixture, predictions=self.predictions)
        await interaction.response.send_modal(modal)


class PredictView(ui.View):
    def __init__(self, fixture: dict, predictions: dict):
        # timeout=None so button stays alive until bot restarts
        super().__init__(timeout=None)
        self.add_item(PredictButton(fixture=fixture, predictions=predictions))


# --------------------------------------------------------------------------- #
#  Cog                                                                        #
# --------------------------------------------------------------------------- #

class Football(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session = None
        self._fixtures = []
        self._sent_fixture_ids: set = set()
        self._last_fetch_at = None
        self._last_fetch_failed = False
        self._missing_key_logged = False

        # {fixture_id: {user_id: (home_goals, away_goals)}}
        self._predictions: dict[str, dict[int, tuple[int, int]]] = {}

        # fixture_ids for which we already announced winners
        self._announced_results: set = set()

        # fixture_ids that are currently in-play / finished for result polling
        self._tracked_for_result: set = set()

        self.world_cup_notifier.start()
        self.result_checker.start()

    def cog_unload(self):
        self.world_cup_notifier.cancel()
        self.result_checker.cancel()

        if self._session and not self._session.closed:
            self.bot.loop.create_task(self._session.close())

    # ----------------------------------------------------------------------- #
    #  Notification loop                                                      #
    # ----------------------------------------------------------------------- #

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

    # ----------------------------------------------------------------------- #
    #  Result-checking loop                                                   #
    # ----------------------------------------------------------------------- #

    @tasks.loop(seconds=int(RESULT_CHECK_INTERVAL.total_seconds()))
    async def result_checker(self):
        if not self._tracked_for_result:
            return

        token = FOOTBALL_DATA_TOKEN.strip()
        if not token:
            return

        still_pending = set()

        for fixture_id in list(self._tracked_for_result):
            if fixture_id in self._announced_results:
                continue

            result = await self._fetch_match_result(token, fixture_id)

            if result is None:
                still_pending.add(fixture_id)
                continue

            # result = {"home": int, "away": int, "home_name": str, "away_name": str}
            await self._announce_prediction_results(fixture_id, result)
            self._announced_results.add(fixture_id)

        self._tracked_for_result = still_pending

    @result_checker.before_loop
    async def before_result_checker(self):
        await self.bot.wait_until_ready()

    # ----------------------------------------------------------------------- #
    #  Commands                                                               #
    # ----------------------------------------------------------------------- #

    @commands.command(name="football", aliases=["wc", "worldcup"])
    async def football(self, ctx: commands.Context):
        """Xem các trận World Cup 2026 trong 24 giờ tới."""
        token = FOOTBALL_DATA_TOKEN.strip()

        if not token:
            await ctx.send("Chưa cấu hình `FOOTBALL_DATA_TOKEN` trong `cogs/football.py`.")
            return

        async with ctx.typing():
            await self._refresh_fixtures_if_needed(token)
            upcoming = self._fixtures_in_next_24_hours()

        if not upcoming:
            await ctx.send("Không có trận World Cup 2026 nào trong 24 giờ tới.")
            return

        embed = self._build_upcoming_embed(upcoming)
        await ctx.send(embed=embed)

        logger.info(
            "[Football] !football requested by %s (%s), returned %s match(es)",
            ctx.author,
            ctx.author.id,
            len(upcoming),
        )

    @commands.command(name="predict", aliases=["dudoan"])
    async def predict_cmd(self, ctx: commands.Context, *, match_number: int = None):
        """Dự đoán tỷ số trận World Cup 2026 trong 24 giờ tới.

        Chỉ được dự đoán trong 15 phút trước khi trận bắt đầu.
        Dùng: !predict <số thứ tự trận> xem số thứ tự bằng !football
        """
        token = FOOTBALL_DATA_TOKEN.strip()

        if not token:
            await ctx.send("Chưa cấu hình `FOOTBALL_DATA_TOKEN`.")
            return

        async with ctx.typing():
            await self._refresh_fixtures_if_needed(token)
            upcoming = self._fixtures_in_next_24_hours()

        if not upcoming:
            await ctx.send("Không có trận World Cup 2026 nào trong 24 giờ tới.")
            return

        if match_number is None or not (1 <= match_number <= len(upcoming)):
            embed = self._build_upcoming_embed(upcoming)
            embed.set_footer(
                text="Dùng !predict <số> để chọn trận | Source: football-data.org"
            )
            await ctx.send("Chọn trận muốn dự đoán:", embed=embed)
            return

        fixture = upcoming[match_number - 1]
        fid = fixture["id"]
        user_id = ctx.author.id

        allowed, reason = _prediction_window_status(fixture)

        if not allowed:
            await ctx.send(f"{ctx.author.mention}, {reason}")
            return

        # Chặn luôn ở command nếu user đã từng dự đoán trận này
        if fid in self._predictions and user_id in self._predictions[fid]:
            old_h, old_a = self._predictions[fid][user_id]
            await ctx.send(
                (
                    f"{ctx.author.mention}, bạn đã dự đoán trận này rồi, không thể dự đoán lại.\n"
                    f"Dự đoán của bạn: **{fixture['home']} {old_h} - {old_a} {fixture['away']}**"
                )
            )
            return

        view = PredictView(fixture=fixture, predictions=self._predictions)
        embed = self._build_match_embed(fixture)
        embed.title = f"Dự đoán: {fixture['home']} vs {fixture['away']}"

        await ctx.send(embed=embed, view=view)

    @commands.command(name="showwc", aliases=["showpredict", "showdudoan"])
    async def showwc(self, ctx: commands.Context, *, match_number: int = None):
        """Xem dự đoán của mọi người cho trận World Cup 2026 trong 24 giờ tới.

        Dùng: !showwc <số thứ tự trận> xem số thứ tự bằng !football
        """
        token = FOOTBALL_DATA_TOKEN.strip()

        if not token:
            await ctx.send("Chưa cấu hình `FOOTBALL_DATA_TOKEN`.")
            return

        async with ctx.typing():
            await self._refresh_fixtures_if_needed(token)
            upcoming = self._fixtures_in_next_24_hours()

        if not upcoming:
            await ctx.send("Không có trận World Cup 2026 nào trong 24 giờ tới.")
            return

        if match_number is None or not (1 <= match_number <= len(upcoming)):
            embed = self._build_upcoming_embed(upcoming)
            embed.set_footer(
                text="Dùng !showwc <số> để xem dự đoán trận đó | Source: football-data.org"
            )
            await ctx.send("Chọn trận muốn xem dự đoán:", embed=embed)
            return

        fixture = upcoming[match_number - 1]
        embed = self._build_predictions_embed(fixture, match_number)
        await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())

    # ----------------------------------------------------------------------- #
    #  Internal helpers                                                       #
    # ----------------------------------------------------------------------- #

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

    async def _fetch_match_result(self, token: str, fixture_id) -> dict | None:
        """Fetch result for a specific match by ID. Returns None if not finished."""
        session = await self._session_or_create()
        url = f"{FOOTBALL_DATA_BASE_URL}/matches/{fixture_id}"
        headers = {"X-Auth-Token": token}

        try:
            async with session.get(url, headers=headers) as response:
                if response.status >= 400:
                    return None

                data = await response.json(content_type=None)

        except Exception as exc:
            logger.error("[Football] Error fetching result for %s: %s", fixture_id, exc)
            return None

        status = data.get("status", "")

        if status not in ("FINISHED",):
            return None

        score = data.get("score", {})
        full_time = score.get("fullTime") or {}
        home_goals = full_time.get("home")
        away_goals = full_time.get("away")

        if home_goals is None or away_goals is None:
            return None

        home_name = self._team_name(data.get("homeTeam") or {})
        away_name = self._team_name(data.get("awayTeam") or {})

        return {
            "home": int(home_goals),
            "away": int(away_goals),
            "home_name": home_name,
            "away_name": away_name,
        }

    async def _announce_prediction_results(self, fixture_id, result: dict):
        """Gửi thông báo kết quả và người dự đoán đúng."""
        preds = self._predictions.get(fixture_id, {})
        correct_users = []
        near_users = []

        for user_id, (ph, pa) in preds.items():
            if ph == result["home"] and pa == result["away"]:
                correct_users.append((user_id, ph, pa))

            elif (ph - pa) == (result["home"] - result["away"]):
                near_users.append((user_id, ph, pa))

        home_name = result["home_name"]
        away_name = result["away_name"]
        actual = f"**{home_name} {result['home']} - {result['away']} {away_name}**"

        lines = [f"Kết quả chính thức: {actual}\n"]

        if preds:
            lines.append(f"Tổng số người dự đoán: **{len(preds)}**")

        if correct_users:
            mentions = ", ".join(f"<@{uid}>" for uid, _, _ in correct_users)
            lines.append(f"\n🏆 **Dự đoán chính xác tỷ số:** {mentions}")

        else:
            lines.append("\nKhông có ai dự đoán chính xác tỷ số.")

        if near_users:
            mentions = ", ".join(f"<@{uid}>" for uid, _, _ in near_users)
            lines.append(f"✅ **Dự đoán đúng hiệu số:** {mentions}")

        if not preds:
            lines.append("Không có ai tham gia dự đoán trận này.")

        embed = discord.Embed(
            title=f"⚽ Kết quả dự đoán: {home_name} vs {away_name}",
            description="\n".join(lines),
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="World Cup 2026 | football-data.org")

        for channel_id in NOTIFY_CHANNEL_IDS:
            channel = await self._get_messageable_channel(channel_id)

            if channel is None:
                continue

            try:
                await channel.send(embed=embed)
                logger.info(
                    "[Football] Announced prediction results for fixture %s in channel %s",
                    fixture_id,
                    channel_id,
                )

            except Exception as exc:
                logger.error(
                    "[Football] Failed to announce results in channel %s: %s",
                    channel_id,
                    exc,
                )

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

            # Start tracking this match for result announcements
            if fixture_id not in self._announced_results:
                self._tracked_for_result.add(fixture_id)

    async def _notify_channels(self, fixture):
        embed = self._build_match_embed(fixture)

        content = (
            f"World Cup 2026: {fixture['home']} vs {fixture['away']} "
            f"còn khoảng {int(NOTIFY_BEFORE.total_seconds() // 60)} phút nữa bắt đầu. "
            "Dự đoán tỷ số đã mở!"
        )

        view = PredictView(fixture=fixture, predictions=self._predictions)

        for channel_id in NOTIFY_CHANNEL_IDS:
            channel = await self._get_messageable_channel(channel_id)

            if channel is None:
                logger.warning("[Football] Cannot find/send to channel ID=%s", channel_id)
                continue

            try:
                await channel.send(content=content, embed=embed, view=view)
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

    def _build_predictions_embed(self, fixture, match_number: int):
        kickoff_local = fixture["kickoff"].astimezone(LOCAL_TZ)
        preds = self._predictions.get(fixture["id"], {})

        embed = discord.Embed(
            title=f"Dự đoán trận {match_number}: {fixture['home']} vs {fixture['away']}",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Kickoff",
            value=kickoff_local.strftime("%H:%M %d/%m/%Y GMT+7"),
            inline=False,
        )
        embed.add_field(name="Round", value=fixture["round"], inline=False)

        if not preds:
            embed.description = "Chưa có ai dự đoán trận này."
        else:
            lines = []

            for index, (user_id, (home_goals, away_goals)) in enumerate(preds.items(), start=1):
                lines.append(
                    f"`{index}.` <@{user_id}> dự đoán: "
                    f"**{fixture['home']} {home_goals} - {away_goals} {fixture['away']}**"
                )

            embed.description = "\n".join(lines)
            embed.set_footer(text=f"Tổng số dự đoán: {len(preds)}")

        return embed

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

        embed.add_field(
            name="Kickoff",
            value=kickoff_local.strftime("%H:%M %d/%m/%Y GMT+7"),
            inline=False,
        )
        embed.add_field(name="Round", value=fixture["round"], inline=True)
        embed.add_field(name="Venue", value=venue, inline=True)
        embed.set_footer(
            text=(
                "Source: football-data.org | "
                f"Chỉ được dự đoán trong {int(PREDICTION_OPEN_BEFORE.total_seconds() // 60)} phút trước giờ bóng lăn!"
            )
        )

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
            text=(
                "Source: football-data.org | "
                f"Checked at {now_local.strftime('%H:%M %d/%m/%Y')} GMT+7"
            )
        )

        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(Football(bot))
