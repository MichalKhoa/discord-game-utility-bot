from __future__ import annotations

import datetime
import random
import time
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from databases.coordle_database import CoordleDatabase
from utils.coordle_logic import (
    ASSETS_DIR,
    DATA_DIR,
    DEFINITION_CACHE,
    ROOT_DIR,
    WORD_CACHE,
    CoordleGame,
    CoordleSession,
    build_rules_embed,
    evaluate_guess,
    fetch_word_definition,
    find_typo_suggestions,
    get_candidate_lemmas,
    get_daily_word,
    load_words,
)
from utils.coordle_views import (
    CoordleGameView,
    CoordleGuessModal,
    CoordleLeaderboardView,
    CoordleSessionLeaderboardView,
    CoordleSessionStartView,
)

__all__ = [
    "ASSETS_DIR",
    "DATA_DIR",
    "DEFINITION_CACHE",
    "ROOT_DIR",
    "WORD_CACHE",
    "Coordle",
    "CoordleGame",
    "CoordleGameView",
    "CoordleGuessModal",
    "CoordleLeaderboardView",
    "CoordleSession",
    "CoordleSessionLeaderboardView",
    "CoordleSessionStartView",
    "build_rules_embed",
    "evaluate_guess",
    "fetch_word_definition",
    "find_typo_suggestions",
    "get_candidate_lemmas",
    "get_daily_word",
    "load_words",
    "setup",
]


class Coordle(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = CoordleDatabase()
        self.active_sessions: Dict[int, CoordleSession] = {}

    def get_active_session(self, channel_id: int) -> Optional[CoordleSession]:
        session = self.active_sessions.get(channel_id)
        if not session:
            return None
        # Inactivity cleanup after 2 hours (7200 seconds)
        if time.time() - session.last_activity > 7200:
            session.is_active = False
            self.active_sessions.pop(channel_id, None)
            return None
        return session

    async def cog_load(self):
        await self.db.init_db()
        self.daily_puzzle_broadcast.start()

    async def cog_unload(self):
        self.daily_puzzle_broadcast.cancel()

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
    async def daily_puzzle_broadcast(self):
        """Automatically posts the daily Co-ordle puzzle at 00:00 UTC in bound channels."""
        channels = await self.db.get_all_daily_channels()
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        for guild_id, channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            try:
                target_word = get_daily_word(guild_id, today_str)
                game = CoordleGame(
                    target_word=target_word,
                    max_attempts=6,
                    guild_id=guild_id,
                    is_daily=True,
                    daily_date_str=today_str
                )
                view = CoordleGameView(game, cog=self)
                embed, file = view.get_embed_and_file()
                msg = await channel.send(
                    f"🌅 **Good morning! The Daily Co-ordle for `{today_str}` has arrived!**\n"
                    f"Work together to solve today's mystery word and preserve your server win streak!",
                    embed=embed,
                    view=view,
                    file=file if file else discord.utils.MISSING
                )
                view.message = msg
            except Exception as e:
                print(f"Failed to broadcast daily Co-ordle to channel {channel_id}: {e}")

    @daily_puzzle_broadcast.before_loop
    async def before_daily_puzzle(self):
        await self.bot.wait_until_ready()

    async def start_game(
        self,
        interaction: discord.Interaction,
        length: int = 5,
        max_attempts: int = 6,
        mode: str = "normal",
        is_daily: bool = False
    ):
        length = max(4, min(8, length))
        max_attempts = max(3, min(15, max_attempts))
        guild_id = interaction.guild_id or (interaction.guild.id if interaction.guild else 0)
        channel_id = interaction.channel_id or (interaction.channel.id if interaction.channel else 0)

        if is_daily:
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            target_word = get_daily_word(guild_id, today_str)
            game = CoordleGame(
                target_word=target_word,
                max_attempts=6,
                host=interaction.user,
                guild_id=guild_id,
                channel_id=channel_id,
                mode="normal",
                is_daily=True,
                daily_date_str=today_str
            )
        else:
            answers, _ = load_words(length)
            if not answers:
                msg = f"❌ No word list available for {length}-letter words."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return

            target_word = random.choice(answers)
            game = CoordleGame(
                target_word=target_word,
                max_attempts=max_attempts,
                host=interaction.user,
                guild_id=guild_id,
                channel_id=channel_id,
                mode=mode
            )

        view = CoordleGameView(game, cog=self)
        embed, file = view.get_embed_and_file()

        if interaction.response.is_done():
            if file:
                msg = await interaction.followup.send(embed=embed, view=view, file=file)
            else:
                msg = await interaction.followup.send(embed=embed, view=view)
            view.message = msg
        else:
            if file:
                await interaction.response.send_message(embed=embed, view=view, file=file)
            else:
                await interaction.response.send_message(embed=embed, view=view)
            try:
                view.message = await interaction.original_response()
            except Exception:
                pass

        if mode == "blitz":
            view.start_blitz_watcher()

    async def show_leaderboard(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or (interaction.guild.id if interaction.guild else 0)
        view = CoordleLeaderboardView(db=self.db, guild_id=guild_id, current_user_id=interaction.user.id)
        embed = await view.build_embed()

        if interaction.response.is_done():
            msg = await interaction.followup.send(embed=embed, view=view)
            view.message = msg
        else:
            await interaction.response.send_message(embed=embed, view=view)
            try:
                view.message = await interaction.original_response()
            except Exception:
                pass

    async def show_stats(self, interaction: discord.Interaction, user: Optional[discord.Member | discord.User] = None):
        target_user = user or interaction.user
        guild_id = interaction.guild_id or (interaction.guild.id if interaction.guild else 0)
        stats = await self.db.get_user_stats(target_user.id, guild_id)
        rank, total = await self.db.get_user_rank(target_user.id, guild_id)

        embed = discord.Embed(
            title=f"📊 Co-ordle Career Stats: {target_user.display_name}",
            colour=discord.Colour.green()
        )
        if target_user.display_avatar:
            embed.set_thumbnail(url=target_user.display_avatar.url)

        if not stats:
            embed.description = f"*{target_user.mention} hasn't participated in any Co-ordle games on this server yet.*"
        else:
            played = stats["games_played"]
            won = stats["games_won"]
            win_rate = (won / played * 100) if played > 0 else 0.0

            rank_text = f"#{rank} of {total}" if rank else "Unranked"
            embed.add_field(name="🏆 Server Rank", value=f"`{rank_text}`", inline=True)
            embed.add_field(name="✨ Total Points", value=f"`{stats['points']:,} pts`", inline=True)
            embed.add_field(name="🎯 Words Solved", value=f"`{stats['words_solved']}`", inline=True)

            embed.add_field(name="🎮 Games Played", value=f"`{played}`", inline=True)
            embed.add_field(name="🏅 Games Won", value=f"`{won}` ({win_rate:.1f}%)", inline=True)
            embed.add_field(name="🔥 Daily Streak", value=f"`{stats.get('current_streak', 0)}` (Max: `{stats.get('max_streak', 0)}`)", inline=True)

            embed.add_field(name="🔤 Total Guesses", value=f"`{stats['total_guesses']}`", inline=True)
            embed.add_field(name="🟩 Greens Found", value=f"`{stats['green_discovered']}`", inline=True)
            embed.add_field(name="🟨 Yellows Found", value=f"`{stats['yellow_discovered']}`", inline=True)

        embed.set_footer(text="Play /coordle or /coordle_daily to climb the server leaderboard!")

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coordle", description="Start a cooperative Wordle game with custom word length, attempts, and mode.")
    @app_commands.describe(
        length="Word length to guess (4-8 letters, default: 5)",
        attempts="Total number of attempts allowed (3-15, default: 6)",
        mode="Game mode: Normal (relaxed 24h timer) or Blitz (speedrun 5m clock +30s/guess, 1.5x points)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="⏱️ Normal Mode (Relaxed 24h timer)", value="normal"),
        app_commands.Choice(name="⚡ Blitz Mode (Speedrun 5m +30s/guess, 1.5x pts)", value="blitz")
    ])
    async def coordle_cmd(
        self,
        interaction: discord.Interaction,
        length: int = 5,
        attempts: int = 6,
        mode: str = "normal"
    ):
        if not (4 <= length <= 8):
            await interaction.response.send_message("❌ Word length must be between 4 and 8 letters.", ephemeral=True)
            return

        if not (3 <= attempts <= 15):
            await interaction.response.send_message("❌ Max attempts must be between 3 and 15.", ephemeral=True)
            return

        await self.start_game(interaction, length=length, max_attempts=attempts, mode=mode)

    @app_commands.command(name="coordle_daily", description="Play today's server-wide Wordle puzzle (resets at 00:00 UTC).")
    async def coordle_daily_cmd(self, interaction: discord.Interaction):
        await self.start_game(interaction, length=5, max_attempts=6, is_daily=True)

    @app_commands.command(name="coordle_daily_channel", description="Set or remove the channel for automated Daily Co-ordle broadcasts (Admin).")
    @app_commands.describe(
        action="Configure or clear the daily broadcast channel",
        channel="The text channel to post daily puzzles into (only for 'set')"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="📌 Set Daily Channel", value="set"),
        app_commands.Choice(name="❌ Remove Daily Channel", value="remove")
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def coordle_daily_channel_cmd(
        self,
        interaction: discord.Interaction,
        action: str,
        channel: Optional[discord.TextChannel] = None
    ):
        if not interaction.guild:
            await interaction.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
            return

        guild_id = interaction.guild.id

        if action == "set":
            target_channel = channel or interaction.channel
            if not isinstance(target_channel, discord.TextChannel):
                await interaction.response.send_message("❌ Please specify a valid text channel.", ephemeral=True)
                return
            await self.db.set_daily_channel(guild_id, target_channel.id)
            await interaction.response.send_message(
                f"✅ **Daily Co-ordle Channel Configured!**\n"
                f"Every day at **00:00 UTC**, today's mystery word puzzle will automatically be posted in {target_channel.mention}."
            )
        else:
            await self.db.remove_daily_channel(guild_id)
            await interaction.response.send_message("✅ Removed automated Daily Co-ordle channel for this server.")

    @app_commands.command(name="coordle_leaderboard", description="View the server's Co-ordle leaderboard and top solvers.")
    async def coordle_leaderboard_cmd(self, interaction: discord.Interaction):
        await self.show_leaderboard(interaction)

    @app_commands.command(name="coordle_stats", description="View your or another player's Co-ordle stats and score.")
    @app_commands.describe(member="The player to view stats for (optional, defaults to yourself)")
    async def coordle_stats_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        await self.show_stats(interaction, user=member)

    @app_commands.command(name="coordle_rules", description="View rules, tile colors, and point scoring for Co-ordle.")
    async def coordle_rules_cmd(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=build_rules_embed())

    session_group = app_commands.Group(name="coordle_session", description="Manage competitive Co-ordle match sessions.")

    @session_group.command(name="start", description="Start a competitive Co-ordle match session in this channel.")
    @app_commands.describe(
        name="Title for this competitive session (default: Competitive Match)",
        rounds="Number of games before session automatically concludes (optional, e.g. 5)"
    )
    async def session_start_cmd(
        self,
        interaction: discord.Interaction,
        name: str = "Competitive Match",
        rounds: Optional[int] = None
    ):
        channel_id = interaction.channel_id
        existing = self.get_active_session(channel_id)
        if existing and existing.is_active:
            await interaction.response.send_message(
                f"⚠️ An active session **`{existing.name}`** is already running in this channel!\n"
                f"View live rankings with `/coordle_session leaderboard` or conclude it with `/coordle_session end`.",
                ephemeral=True
            )
            return

        if rounds is not None and rounds < 1:
            await interaction.response.send_message("❌ Target rounds must be at least 1.", ephemeral=True)
            return

        guild_id = interaction.guild_id or (interaction.guild.id if interaction.guild else 0)
        session = CoordleSession(
            channel_id=channel_id,
            guild_id=guild_id,
            host=interaction.user,
            name=name,
            target_rounds=rounds
        )
        self.active_sessions[channel_id] = session

        target_str = f" • Target: **{rounds} Rounds**" if rounds else " • Target: **Open-ended**"
        embed = discord.Embed(
            title=f"🏆 Competitive Co-ordle Session Started: {session.name}",
            description=(
                f"**Host**: {interaction.user.mention}{target_str}\n\n"
                f"All Co-ordle games played in this channel will automatically count towards this session's leaderboard!\n"
                f"Click **Play Round** below or use `/coordle` to begin competing."
            ),
            colour=discord.Colour.gold()
        )
        embed.set_footer(text="Session tracking active • View rankings with /coordle_session leaderboard")
        view = CoordleSessionStartView(session, self)
        await interaction.response.send_message(embed=embed, view=view)
        try:
            view.message = await interaction.original_response()
        except Exception:
            pass

    @session_group.command(name="leaderboard", description="View the live leaderboard for the active competitive session.")
    async def session_leaderboard_cmd(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        session = self.get_active_session(channel_id)
        if not session or not session.is_active:
            await interaction.response.send_message(
                "❌ No active competitive session in this channel. Start one with `/coordle_session start`!",
                ephemeral=True
            )
            return

        view = CoordleSessionLeaderboardView(session, self)
        embed = session.build_summary_embed(is_final=False)
        await interaction.response.send_message(embed=embed, view=view)
        try:
            view.message = await interaction.original_response()
        except Exception:
            pass

    @session_group.command(name="end", description="End the active competitive session in this channel and crown the champion.")
    async def session_end_cmd(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        session = self.get_active_session(channel_id)
        if not session or not session.is_active:
            await interaction.response.send_message(
                "❌ No active competitive session in this channel to end.",
                ephemeral=True
            )
            return

        is_host = interaction.user.id == session.host.id
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild else False
        if not (is_host or is_admin):
            await interaction.response.send_message("❌ Only the session host or server admins can end this session.", ephemeral=True)
            return

        session.is_active = False
        self.active_sessions.pop(channel_id, None)

        embed = session.build_summary_embed(is_final=True)
        await interaction.response.send_message(
            content=f"🏁 **Competitive session `{session.name}` concluded by {interaction.user.mention}!**",
            embed=embed
        )

    @session_group.command(name="status", description="Check status of the active competitive session in this channel.")
    async def session_status_cmd(self, interaction: discord.Interaction):
        channel_id = interaction.channel_id
        session = self.get_active_session(channel_id)
        if not session or not session.is_active:
            await interaction.response.send_message(
                "ℹ️ No competitive session is currently running in this channel. Start one with `/coordle_session start`!",
                ephemeral=True
            )
            return

        target_str = f"/{session.target_rounds}" if session.target_rounds else ""
        embed = discord.Embed(
            title=f"⚡ Session Active: {session.name}",
            description=(
                f"**Host**: {session.host.mention}\n"
                f"**Rounds Completed**: `{session.rounds_played}{target_str}`\n"
                f"**Active Contenders**: `{len(session.scores)}`\n"
                f"**Created**: <t:{int(session.created_at)}:R>\n\n"
                f"Use `/coordle_session leaderboard` for live standings or `/coordle_session end` to finish."
            ),
            colour=discord.Colour.og_blurple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    print("Coordle cog loaded")
    await bot.add_cog(Coordle(bot))
