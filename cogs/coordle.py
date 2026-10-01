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
    "SPAWN_TIMES",
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

SPAWN_TIMES = [
    datetime.time(hour=h, minute=m, tzinfo=datetime.timezone.utc)
    for h in range(24)
    for m in (0, 30)
]


class Coordle(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = getattr(bot, "coordle_db", None) or CoordleDatabase()
        self.active_sessions: Dict[int, CoordleSession] = {}
        self.active_spawn_games: Dict[int, CoordleGameView] = {}

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
        self.periodic_spawn_broadcast.start()

    async def cog_unload(self):
        self.daily_puzzle_broadcast.cancel()
        self.periodic_spawn_broadcast.cancel()

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

    @tasks.loop(time=SPAWN_TIMES)
    async def periodic_spawn_broadcast(self):
        """Automatically posts periodic Co-ordle puzzles every 30 minutes (:00 and :30 UTC)."""
        channels = await self.db.get_all_spawn_channels()
        for cfg in channels:
            guild_id = cfg["guild_id"]
            channel_id = cfg["channel_id"]
            role_id = cfg.get("role_id")
            word_length = cfg.get("word_length") or 5
            max_attempts = cfg.get("max_attempts") or 6
            mode = cfg.get("mode") or "normal"

            channel = self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    continue
            if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
                continue

            try:
                # Expire and conclude previous active game in this channel
                prev_view = self.active_spawn_games.get(channel_id)
                if prev_view and not prev_view.game.game_over:
                    if prev_view.blitz_task:
                        prev_view.blitz_task.cancel()
                    prev_view.game.game_over = True
                    prev_view.game.expired = True
                    prev_view.stop()
                    await prev_view.game.ensure_definition(db=self.db)
                    await prev_view.save_stats()
                    prev_view.update_buttons()
                    prev_embed, prev_file = prev_view.get_embed_and_file()
                    prev_embed.title = f"⌛ Co-ordle ({prev_view.game.word_length} Letters) — Timed Out"
                    prev_embed.colour = discord.Colour.dark_grey()
                    prev_embed.description += (
                        f"\n\n⌛ **Spawn Timed Out**: Concluded to make way for the new puzzle spawn. "
                        f"The mystery word was **`{prev_view.game.target_word}`**."
                    )
                    if prev_view.message:
                        try:
                            await prev_view.message.edit(
                                embed=prev_embed,
                                view=prev_view,
                                attachments=[prev_file] if prev_file else []
                            )
                        except Exception:
                            pass

                # Select word length (4-8, or random if 0 or outside range)
                if not (4 <= word_length <= 8):
                    actual_length = random.randint(4, 8)
                else:
                    actual_length = word_length

                answers, _ = load_words(actual_length)
                if not answers:
                    answers, _ = load_words(5)
                    actual_length = 5

                target_word = random.choice(answers)
                actual_attempts = max(3, min(15, max_attempts))

                game = CoordleGame(
                    target_word=target_word,
                    max_attempts=actual_attempts,
                    guild_id=guild_id,
                    channel_id=channel_id,
                    mode=mode
                )
                view = CoordleGameView(game, cog=self)
                embed, file = view.get_embed_and_file()

                role_mention = f"<@&{role_id}> " if role_id else ""
                content = (
                    f"{role_mention}🎯 **A new {actual_length}-letter Co-ordle has spawned!**\n"
                    f"Join forces to crack the code before the next spawn!"
                )

                msg = await channel.send(
                    content=content,
                    embed=embed,
                    view=view,
                    file=file if file else discord.utils.MISSING
                )
                view.message = msg
                if mode == "blitz":
                    view.start_blitz_watcher()
                self.active_spawn_games[channel_id] = view
            except Exception as e:
                print(f"Failed to broadcast periodic Co-ordle to channel {channel_id}: {e}")

    @periodic_spawn_broadcast.before_loop
    async def before_periodic_spawn(self):
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

    @app_commands.command(name="coordle_spawn_channel", description="Set or remove the channel for periodic Co-ordle game spawns every 30 minutes (Admin).")
    @app_commands.describe(
        action="Configure, remove, or view the periodic spawn channel",
        channel="The text channel for periodic spawns (only for 'set', defaults to current)",
        role="Role to mention when a new puzzle spawns (optional)",
        length="Word length: 4-8 letters, or 0 for Random (default: 5)",
        attempts="Attempts allowed: 3-15 (default: 6)",
        mode="Game mode: Normal (relaxed) or Blitz (5m timer)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="📌 Set Spawn Channel", value="set"),
        app_commands.Choice(name="❌ Remove Spawn Channel", value="remove"),
        app_commands.Choice(name="ℹ️ View Status", value="status")
    ])
    @app_commands.choices(mode=[
        app_commands.Choice(name="⏱️ Normal Mode", value="normal"),
        app_commands.Choice(name="⚡ Blitz Mode", value="blitz")
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def coordle_spawn_channel_cmd(
        self,
        interaction: discord.Interaction,
        action: str,
        channel: Optional[discord.TextChannel] = None,
        role: Optional[discord.Role] = None,
        length: Optional[int] = 5,
        attempts: Optional[int] = 6,
        mode: Optional[str] = "normal"
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

            actual_length = 5 if length is None else length
            if actual_length != 0 and not (4 <= actual_length <= 8):
                await interaction.response.send_message("❌ Word length must be between 4 and 8 (or 0 for Random).", ephemeral=True)
                return

            actual_attempts = 6 if attempts is None else attempts
            if not (3 <= actual_attempts <= 15):
                await interaction.response.send_message("❌ Max attempts must be between 3 and 15.", ephemeral=True)
                return

            actual_mode = mode if mode in ("normal", "blitz") else "normal"
            role_id = role.id if role else None

            await self.db.set_spawn_channel(
                guild_id=guild_id,
                channel_id=target_channel.id,
                role_id=role_id,
                word_length=actual_length,
                max_attempts=actual_attempts,
                mode=actual_mode
            )

            role_str = role.mention if role else "*None (no ping)*"
            len_str = "Random (4-8 letters)" if actual_length == 0 else f"{actual_length} letters"
            mode_str = "⚡ Blitz" if actual_mode == "blitz" else "⏱️ Normal"

            embed = discord.Embed(
                title="✅ Periodic Co-ordle Spawns Configured",
                description=(
                    f"Puzzles will spawn every **30 minutes** (at `:00` and `:30` UTC).\n\n"
                    f"• **Channel**: {target_channel.mention}\n"
                    f"• **Role Tag**: {role_str}\n"
                    f"• **Word Length**: `{len_str}`\n"
                    f"• **Attempts**: `{actual_attempts}`\n"
                    f"• **Mode**: `{mode_str}`\n"
                    f"• **Overlaps**: Active games expire automatically when new puzzles arrive."
                ),
                colour=discord.Colour.green()
            )
            await interaction.response.send_message(embed=embed)

        elif action == "remove":
            await self.db.remove_spawn_channel(guild_id)
            await interaction.response.send_message("✅ Removed periodic Co-ordle spawn schedule for this server.")

        elif action == "status":
            cfg = await self.db.get_spawn_channel(guild_id)
            if not cfg:
                await interaction.response.send_message(
                    "ℹ️ Periodic Co-ordle spawns are currently **not configured** for this server.\n"
                    "Use `/coordle_spawn_channel action:📌 Set Spawn Channel` to configure.",
                    ephemeral=True
                )
                return

            ch = self.bot.get_channel(cfg["channel_id"])
            ch_str = ch.mention if ch else f"<#{cfg['channel_id']}>"
            role_id = cfg.get("role_id")
            role_str = f"<@&{role_id}>" if role_id else "*None (no ping)*"
            word_len = cfg.get("word_length", 5)
            len_str = "Random (4-8 letters)" if word_len == 0 else f"{word_len} letters"
            attempts_val = cfg.get("max_attempts", 6)
            mode_val = cfg.get("mode", "normal")
            mode_str = "⚡ Blitz" if mode_val == "blitz" else "⏱️ Normal"

            embed = discord.Embed(
                title="⚙️ Periodic Co-ordle Spawn Settings",
                description=(
                    f"• **Channel**: {ch_str}\n"
                    f"• **Role Tag**: {role_str}\n"
                    f"• **Schedule**: Every 30 minutes (`:00` & `:30` UTC)\n"
                    f"• **Word Length**: `{len_str}`\n"
                    f"• **Attempts**: `{attempts_val}`\n"
                    f"• **Mode**: `{mode_str}`"
                ),
                colour=discord.Colour.blue()
            )
            await interaction.response.send_message(embed=embed)

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
