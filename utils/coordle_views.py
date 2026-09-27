from __future__ import annotations

import asyncio
import datetime
import string
import time
from typing import Optional, Tuple, TYPE_CHECKING

import discord

from databases.coordle_database import CoordleDatabase
from utils.coordle_image import render_coordle_board
from utils.coordle_logic import (
    CoordleGame,
    CoordleSession,
    build_rules_embed,
    find_typo_suggestions,
    load_words,
)

if TYPE_CHECKING:
    from cogs.coordle import Coordle


class CoordleGuessModal(discord.ui.Modal):
    def __init__(self, game_view: CoordleGameView):
        super().__init__(title=f"Co-ordle: {game_view.game.word_length}-Letter Word")
        self.game_view = game_view

        self.guess_input = discord.ui.TextInput(
            label=f"Your Guess ({game_view.game.word_length} Letters)",
            placeholder=f"Type a valid {game_view.game.word_length}-letter English word...",
            min_length=game_view.game.word_length,
            max_length=game_view.game.word_length,
            required=True
        )
        self.add_item(self.guess_input)

    async def on_submit(self, interaction: discord.Interaction):
        guess = self.guess_input.value.strip().lower()

        if self.game_view.game.game_over:
            await interaction.response.send_message("❌ This game has already concluded.", ephemeral=True)
            return

        if len(guess) != self.game_view.game.word_length or not guess.isalpha():
            await interaction.response.send_message(
                f"❌ Guess must be exactly {self.game_view.game.word_length} alphabetical letters.",
                ephemeral=True
            )
            return

        # Check dictionary with fuzzy typo suggestions
        _, valid_guesses = load_words(self.game_view.game.word_length)
        if valid_guesses and guess not in valid_guesses:
            suggestions = find_typo_suggestions(guess, valid_guesses)
            sugg_text = ""
            if suggestions:
                sugg_str = " or ".join(f"**`{s.upper()}`**" for s in suggestions)
                sugg_text = "\n💡 *Did you mean " + sugg_str + "?*"
            await interaction.response.send_message(
                f"❌ **{guess.upper()}** is not in the valid dictionary word list!{sugg_text}",
                ephemeral=True
            )
            return

        # Check duplicate guess
        if any(g[0] == guess.upper() for g in self.game_view.game.guesses):
            await interaction.response.send_message(
                f"⚠️ **{guess.upper()}** has already been guessed in this game!",
                ephemeral=True
            )
            return

        # 15s Turn-taking anti-spam cooldown check (bypassed in blitz mode for intense fast guessing)
        if self.game_view.game.mode != "blitz":
            now = time.time()
            last_guess_time = self.game_view.game.user_cooldowns.get(interaction.user.id, 0)
            time_since = now - last_guess_time
            if time_since < 15.0:
                remaining = int(15.0 - time_since) + 1
                await interaction.response.send_message(
                    f"⏳ **Turn-taking Cooldown**: Please wait **{remaining}s** before submitting another guess so other players can take a turn!",
                    ephemeral=True
                )
                return
            self.game_view.game.user_cooldowns[interaction.user.id] = now

        # Apply guess
        self.game_view.game.submit_guess(guess, interaction.user)

        # If game concluded, ensure definition and save stats asynchronously
        if self.game_view.game.game_over:
            await self.game_view.game.ensure_definition(db=self.game_view.cog.db if self.game_view.cog else None)
            if self.game_view.cog:
                asyncio.create_task(self.game_view.save_stats())

        self.game_view.update_buttons()
        embed, file = self.game_view.get_embed_and_file()

        await interaction.response.edit_message(
            embed=embed,
            view=self.game_view,
            attachments=[file] if file else []
        )


class CoordleGameView(discord.ui.View):
    def __init__(self, game: CoordleGame, cog: Optional[Coordle] = None):
        # 24 hours for standard/daily, or 900s (15m) for blitz view timeout
        view_timeout = 900 if game.mode == "blitz" else 86400
        super().__init__(timeout=view_timeout)
        self.game = game
        self.cog = cog
        self.message: Optional[discord.Message] = None
        self.blitz_task: Optional[asyncio.Task] = None
        self.update_buttons()

    def start_blitz_watcher(self):
        """Starts asynchronous background timer loop for Blitz mode."""
        if self.game.mode == "blitz" and not self.blitz_task:
            self.blitz_task = asyncio.create_task(self._blitz_watcher())

    async def _blitz_watcher(self):
        """Monitors remaining Blitz seconds and triggers game over if clock hits 0."""
        try:
            while not self.game.game_over:
                await asyncio.sleep(2.0)
                remaining = self.game.blitz_expires_at - time.time()
                if remaining <= 0 and not self.game.game_over:
                    self.game.game_over = True
                    self.game.expired = True
                    await self.game.ensure_definition(db=self.cog.db if self.cog else None)
                    if self.cog:
                        await self.save_stats()
                    self.update_buttons()
                    embed, file = self.get_embed_and_file()
                    if self.message:
                        try:
                            await self.message.edit(embed=embed, view=self, attachments=[file] if file else [])
                        except Exception:
                            pass
                    break
        except asyncio.CancelledError:
            pass

    def update_buttons(self):
        self.guess_btn.disabled = self.game.game_over
        self.surrender_btn.disabled = self.game.game_over
        self.share_btn.disabled = not self.game.game_over

    async def on_timeout(self):
        """Handles 12-hour inactivity expiration gracefully."""
        if self.blitz_task:
            self.blitz_task.cancel()
        if not self.game.game_over:
            self.game.game_over = True
            self.game.expired = True
            await self.game.ensure_definition(db=self.cog.db if self.cog else None)
            if self.cog:
                await self.save_stats()
            self.update_buttons()
            embed, file = self.get_embed_and_file()
            embed.title = f"⌛ Co-ordle ({self.game.word_length} Letters) — Expired"
            embed.colour = discord.Colour.dark_grey()
            embed.description += (
                f"\n\n⌛ **Game Expired**: This puzzle was inactive for 24 hours. "
                f"The mystery word was **`{self.game.target_word}`**."
            )
            if self.message:
                try:
                    await self.message.edit(embed=embed, view=self, attachments=[file] if file else [])
                except Exception:
                    pass

    async def save_stats(self):
        if not self.cog or not self.game.guild_id:
            return
        db = self.cog.db
        for uid, p in self.game.participants.items():
            try:
                await db.add_points_and_stats(
                    user_id=uid,
                    guild_id=self.game.guild_id,
                    user_name=p["name"],
                    points=p["points"],
                    game_played=True,
                    game_won=self.game.won,
                    word_solved=p["solved"],
                    guesses=p["guesses"],
                    greens=p["greens"],
                    yellows=p["yellows"]
                )
                # If this was a daily victory, update daily win streak
                if self.game.is_daily and self.game.won and p["guesses"] > 0:
                    await db.update_daily_streak(
                        user_id=uid,
                        guild_id=self.game.guild_id,
                        today_str=self.game.daily_date_str
                    )
            except Exception as e:
                print(f"Error saving Coordle stats for user {uid}: {e}")

        # Update in-memory competitive session if active in this channel
        if self.cog and self.game.channel_id:
            session = self.cog.get_active_session(self.game.channel_id)
            if session and session.is_active:
                channel = self.message.channel if self.message else None
                await session.process_game_end(self.game, channel=channel, cog=self.cog)

    def get_file(self) -> Optional[discord.File]:
        try:
            buf = render_coordle_board(
                guesses=self.game.guesses,
                letter_status=self.game.letter_status,
                word_length=self.game.word_length,
                max_attempts=self.game.max_attempts
            )
            if buf is not None:
                return discord.File(fp=buf, filename="coordle.png")
            return None
        except Exception as e:
            print(f"[Coordle] Error rendering image: {e}")
            return None

    def get_embed(self, has_image: bool = True) -> discord.Embed:
        if self.game.won:
            color = discord.Colour.green()
            prefix = "📅 Daily Co-ordle" if self.game.is_daily else "🟩 Co-ordle"
            title = f"{prefix} ({self.game.word_length} Letters) — Victory!"
        elif self.game.expired:
            color = discord.Colour.dark_grey()
            title = f"⌛ Co-ordle ({self.game.word_length} Letters) — Expired"
        elif self.game.game_over:
            color = discord.Colour.red()
            prefix = "📅 Daily Co-ordle" if self.game.is_daily else "⬛ Co-ordle"
            title = f"{prefix} ({self.game.word_length} Letters) — Defeat"
        else:
            color = discord.Colour.gold()
            if self.game.is_daily:
                title = f"📅 Daily Co-ordle ({self.game.daily_date_str}) — Guess the Word!"
            elif self.game.mode == "blitz":
                title = f"⚡ Co-ordle Blitz ({self.game.word_length} Letters) — Speedrun!"
            else:
                title = f"🟩 Co-ordle ({self.game.word_length} Letters) — Guess the Word!"

        # Status / Timer line
        if self.game.game_over:
            timer_line = "🔒 **Status**: Concluded"
        elif self.game.mode == "blitz":
            timer_line = f"⚡ **Blitz Clock**: <t:{int(self.game.blitz_expires_at)}:R> (+30s/guess)"
        else:
            timer_line = f"⏳ **Expires**: <t:{int(self.game.expires_at)}:R>"

        mode_badge = "⚡ `BLITZ (1.5x PTS)`" if self.game.mode == "blitz" else ("📅 `DAILY PUZZLE`" if self.game.is_daily else "⏱️ `STANDARD`")

        session_badge = ""
        if self.cog and self.game.channel_id:
            session = self.cog.get_active_session(self.game.channel_id)
            if session and session.is_active:
                target_str = f"/{session.target_rounds}" if session.target_rounds else ""
                session_badge = f" | 🏆 **Session**: `{session.name}` (R{session.rounds_played + 1}{target_str})"

        desc = [
            f"**Mode**: {mode_badge} | **Attempts**: `{len(self.game.guesses)}/{self.game.max_attempts}` | {timer_line}{session_badge}"
        ]

        if not has_image:
            # Fallback text board and tracker if image rendering is unavailable
            progress_slots = []
            for idx in range(self.game.word_length):
                if idx in self.game.known_green_indices:
                    progress_slots.append(f"🟩 `{self.game.target_word[idx]}`")
                elif self.game.game_over and not self.game.won:
                    progress_slots.append(f"⬛ `{self.game.target_word[idx]}`")
                else:
                    progress_slots.append("⬜ `_`")
            progress_line = "  ".join(progress_slots)

            yellow_chars = [c for c in string.ascii_uppercase if self.game.letter_status.get(c) == 'Y']
            yellow_str = ", ".join(f"`{c}`" for c in yellow_chars) if yellow_chars else "*None yet*"

            if self.game.won:
                progress_text = f"{progress_line}\n🎯 **Word Discovered!**"
            elif self.game.game_over:
                progress_text = f"{progress_line}\n💀 **Solution**: **`{self.game.target_word}`**"
            else:
                progress_text = f"{progress_line}\n🟨 **Present in Word**: {yellow_str}"

            board_lines = []
            tile_map = {'G': '🟩', 'Y': '🟨', 'B': '⬛'}
            for i, entry in enumerate(self.game.guesses, 1):
                word = entry[0]
                pattern = entry[1]
                author = entry[2]
                pts = entry[3]
                discoveries = entry[4] if len(entry) > 4 else []
                tiles = "".join(tile_map[p] for p in pattern)
                word_spaced = " ".join(list(word))
                found_str = f" • Found {', '.join(discoveries)}" if discoveries else ""
                board_lines.append(f"`{i:2d}.` {tiles}  **`{word_spaced}`**  — *{author}* (`+{pts} pts`{found_str})")

            for i in range(len(self.game.guesses) + 1, self.game.max_attempts + 1):
                board_lines.append(f"`{i:2d}.` {'⬜' * self.game.word_length}")

            board_text = "\n".join(board_lines)

            correct_chars = [c for c in string.ascii_uppercase if self.game.letter_status.get(c) == 'G']
            present_chars = [c for c in string.ascii_uppercase if self.game.letter_status.get(c) == 'Y']
            eliminated_chars = [c for c in string.ascii_uppercase if self.game.letter_status.get(c) == 'B']
            remaining_chars = [c for c in string.ascii_uppercase if c not in self.game.letter_status]

            correct_display = ", ".join(f"`{c}`" for c in correct_chars) if correct_chars else "*None*"
            present_display = ", ".join(f"`{c}`" for c in present_chars) if present_chars else "*None*"
            eliminated_display = " ".join(f"~~{c}~~" for c in eliminated_chars) if eliminated_chars else "*None*"
            remaining_display = " ".join(remaining_chars) if remaining_chars else "*None*"

            qwerty = ["Q W E R T Y U I O P", "A S D F G H J K L", "Z X C V B N M"]
            keyboard_lines = []
            for row in qwerty:
                row_display = []
                for char in row.split():
                    st = self.game.letter_status.get(char)
                    if st == 'G': row_display.append(f"🟩{char}")
                    elif st == 'Y': row_display.append(f"🟨{char}")
                    elif st == 'B': row_display.append(f"~~{char}~~")
                    else: row_display.append(char)
                keyboard_lines.append(" ".join(row_display))
            keyboard_text = "\n".join(keyboard_lines)

            tracker_text = (
                f"🟩 **Correct**: {correct_display}\n"
                f"🟨 **Present**: {present_display}\n"
                f"⬛ **Eliminated**: {eliminated_display}\n"
                f"⬜ **Untried**: {remaining_display}\n\n"
                f"{keyboard_text}"
            )

            desc.extend([
                "",
                "### 🎯 Word Progress",
                progress_text,
                "",
                "### 📋 Guess Board",
                board_text,
                "",
                "### ⌨️ Letter Tracker",
                tracker_text,
            ])

        if self.game.won:
            desc.append(f"\nGood job! Everyone who participated gets **+10** points!")
            desc.append(f"🎉 **{self.game.solver}** solved the mystery word: **`{self.game.target_word}`** in `{len(self.game.guesses)}` attempts!")
            pts_summary = ", ".join(f"**{p['name']}**: `+{p['points']} pts`" for p in self.game.participants.values())
            if pts_summary:
                desc.append(f"🏅 **Match Rewards**: {pts_summary}")
        elif self.game.expired and self.game.mode == "blitz":
            desc.append(f"\n⚡ **Time Expired!** The Blitz clock hit 0. The mystery word was **`{self.game.target_word}`**.")
        elif self.game.game_over and not self.game.expired:
            desc.append(f"\n💀 Out of attempts! The mystery word was **`{self.game.target_word}`**.")

        if self.game.definition:
            desc.append(f"\n💡 **Word Meaning**: {self.game.definition}")

        embed = discord.Embed(
            title=title,
            description="\n".join(desc),
            colour=color
        )
        if has_image:
            embed.set_image(url="attachment://coordle.png")

        embed.set_footer(text="Click 'Submit Guess' to play | Rules: /coordle_rules")
        return embed

    def get_embed_and_file(self) -> Tuple[discord.Embed, Optional[discord.File]]:
        file = self.get_file()
        embed = self.get_embed(has_image=(file is not None))
        return embed, file

    @discord.ui.button(label="Submit Guess", style=discord.ButtonStyle.success, emoji="🔤", row=0)
    async def guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CoordleGuessModal(self))

    @discord.ui.button(label="Rules", style=discord.ButtonStyle.secondary, emoji="📖", row=0)
    async def rules_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_rules_embed(), ephemeral=True)

    @discord.ui.button(label="Share Result", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def share_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        text = self.game.generate_share_text()
        await interaction.response.send_message(
            f"**Share your Co-ordle result:**\n```\n{text}\n```",
            ephemeral=True
        )

    @discord.ui.button(label="Surrender", style=discord.ButtonStyle.secondary, emoji="🏳️", row=0)
    async def surrender_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.host and interaction.user.id != self.game.host.id and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Only the host or a server admin can surrender the game.", ephemeral=True)
            return

        self.game.game_over = True
        self.game.surrendered = True
        if self.blitz_task:
            self.blitz_task.cancel()
        await self.game.ensure_definition(db=self.cog.db if self.cog else None)
        if self.cog:
            asyncio.create_task(self.save_stats())
        self.update_buttons()
        embed, file = self.get_embed_and_file()
        embed.description += f"\n\n🏳️ Game ended early by {interaction.user.mention}. The word was **`{self.game.target_word}`**."
        await interaction.response.edit_message(
            embed=embed,
            view=self,
            attachments=[file] if file else []
        )


class CoordleSessionLeaderboardView(discord.ui.View):
    def __init__(self, session: CoordleSession, cog: Coordle):
        super().__init__(timeout=1800)
        self.session = session
        self.cog = cog
        self.sort_by = "points"
        self.message: Optional[discord.Message] = None
        self.update_buttons()

    def update_buttons(self):
        self.btn_points.style = discord.ButtonStyle.primary if self.sort_by == "points" else discord.ButtonStyle.secondary
        self.btn_solves.style = discord.ButtonStyle.primary if self.sort_by == "solves" else discord.ButtonStyle.secondary
        self.btn_wins.style = discord.ButtonStyle.primary if self.sort_by == "wins" else discord.ButtonStyle.secondary
        self.btn_end.disabled = not self.session.is_active

    @discord.ui.button(label="Points", emoji="🏆", style=discord.ButtonStyle.primary, row=0)
    async def btn_points(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.sort_by = "points"
        self.update_buttons()
        embed = self.session.build_summary_embed(is_final=not self.session.is_active, sort_by=self.sort_by)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Solves", emoji="🎯", style=discord.ButtonStyle.secondary, row=0)
    async def btn_solves(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.sort_by = "solves"
        self.update_buttons()
        embed = self.session.build_summary_embed(is_final=not self.session.is_active, sort_by=self.sort_by)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Wins", emoji="🏅", style=discord.ButtonStyle.secondary, row=0)
    async def btn_wins(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.sort_by = "wins"
        self.update_buttons()
        embed = self.session.build_summary_embed(is_final=not self.session.is_active, sort_by=self.sort_by)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=0)
    async def btn_refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.update_buttons()
        embed = self.session.build_summary_embed(is_final=not self.session.is_active, sort_by=self.sort_by)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="End Session", emoji="🛑", style=discord.ButtonStyle.danger, row=0)
    async def btn_end(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_host = interaction.user.id == self.session.host.id
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild else False
        if not (is_host or is_admin):
            await interaction.response.send_message("❌ Only the session host or server admins can end this session.", ephemeral=True)
            return

        self.session.is_active = False
        if self.session.channel_id in self.cog.active_sessions:
            self.cog.active_sessions.pop(self.session.channel_id, None)

        self.update_buttons()
        embed = self.session.build_summary_embed(is_final=True, sort_by=self.sort_by)
        await interaction.response.edit_message(
            content=f"🛑 **Competitive session `{self.session.name}` concluded by {interaction.user.mention}!**",
            embed=embed,
            view=self
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class CoordleSessionStartView(discord.ui.View):
    def __init__(self, session: CoordleSession, cog: Coordle):
        super().__init__(timeout=86400)
        self.session = session
        self.cog = cog
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="Play Round", emoji="🟩", style=discord.ButtonStyle.success, row=0)
    async def btn_play(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.session.is_active:
            await interaction.response.send_message("❌ This competitive session has already concluded.", ephemeral=True)
            return
        await self.cog.start_game(interaction, length=5, max_attempts=6, mode="normal")

    @discord.ui.button(label="Session Leaderboard", emoji="📊", style=discord.ButtonStyle.primary, row=0)
    async def btn_board(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CoordleSessionLeaderboardView(self.session, self.cog)
        embed = self.session.build_summary_embed(is_final=not self.session.is_active)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="End Session", emoji="🛑", style=discord.ButtonStyle.danger, row=0)
    async def btn_end(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_host = interaction.user.id == self.session.host.id
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild else False
        if not (is_host or is_admin):
            await interaction.response.send_message("❌ Only the session host or server admins can end this session.", ephemeral=True)
            return

        self.session.is_active = False
        if self.session.channel_id in self.cog.active_sessions:
            self.cog.active_sessions.pop(self.session.channel_id, None)

        for item in self.children:
            item.disabled = True
        embed = self.session.build_summary_embed(is_final=True)
        await interaction.response.edit_message(
            content=f"🛑 **Competitive session `{self.session.name}` concluded by {interaction.user.mention}!**",
            embed=embed,
            view=self
        )


class CoordleLeaderboardView(discord.ui.View):
    CATEGORY_META = {
        "points": {
            "title": "🏆 Co-ordle Leaderboard — All-Time Points",
            "color": discord.Colour.gold(),
            "badge": "Points",
            "format": lambda e: f"**`{e.get('points', 0):,} pts`**",
        },
        "solves": {
            "title": "🎯 Co-ordle Leaderboard — Top Solvers",
            "color": discord.Colour.green(),
            "badge": "Words Solved",
            "format": lambda e: f"**`{e.get('words_solved', 0):,} Solves`** ({e.get('points', 0):,} pts)",
        },
        "wins": {
            "title": "🏅 Co-ordle Leaderboard — Most Wins",
            "color": discord.Colour.og_blurple(),
            "badge": "Games Won",
            "format": lambda e: f"**`{e.get('games_won', 0):,} Wins`**",
        },
        "streak": {
            "title": "🔥 Co-ordle Leaderboard — Daily Streaks",
            "color": discord.Colour.orange(),
            "badge": "Daily Streak",
            "format": lambda e: f"**`🔥 {e.get('current_streak', 0)} Streak`** (Max: `{e.get('max_streak', 0)}`)",
        },
    }

    def __init__(self, db: CoordleDatabase, guild_id: int, current_user_id: int):
        super().__init__(timeout=1800)  # 30 minutes
        self.db = db
        self.guild_id = guild_id
        self.current_user_id = current_user_id
        self.category = "points"
        self.page = 0
        self.per_page = 8
        self.total_players = 0
        self.max_pages = 1
        self.message: Optional[discord.Message] = None

    async def initialize(self):
        await self.refresh_data()
        self.update_buttons()

    async def refresh_data(self):
        self.total_players = await self.db.get_total_players(self.guild_id)
        self.max_pages = max(1, (self.total_players + self.per_page - 1) // self.per_page)
        if self.page >= self.max_pages:
            self.page = max(0, self.max_pages - 1)

    def update_buttons(self):
        self.first_btn.disabled = (self.page <= 0)
        self.prev_btn.disabled = (self.page <= 0)
        self.next_btn.disabled = (self.page >= self.max_pages - 1)
        self.last_btn.disabled = (self.page >= self.max_pages - 1)

    async def build_embed(self) -> discord.Embed:
        await self.refresh_data()
        meta = self.CATEGORY_META.get(self.category, self.CATEGORY_META["points"])
        offset = self.page * self.per_page
        entries = await self.db.get_leaderboard(
            guild_id=self.guild_id,
            sort_by=self.category,
            limit=self.per_page,
            offset=offset
        )
        user_rank, _ = await self.db.get_user_rank(self.current_user_id, self.guild_id, sort_by=self.category)
        user_stats = await self.db.get_user_stats(self.current_user_id, self.guild_id)

        embed = discord.Embed(
            title=meta["title"],
            colour=meta["color"]
        )

        embed.description = (
            "Compete in cooperative Wordle games to earn points and climb the rankings!\n"
            "`🟩 +10 pts` • `🟨 +5 pts` • `🎯 Solve: Left×5` • `🏆 Win: +10 pts`\n\n"
        )

        if not entries:
            embed.description += "*No player records found for this server yet! Start a match with `/coordle`.*"
        else:
            lines = []
            num_emojis = {4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}
            for idx_in_page, entry in enumerate(entries):
                rank_num = offset + idx_in_page + 1
                highlight = meta["format"](entry)
                played = entry.get("games_played", 0)
                won = entry.get("games_won", 0)
                win_pct = (won / played * 100) if played > 0 else 0.0

                if rank_num == 1:
                    lines.append(
                        f"🥇 **1st Place**: **{entry['user_name']}** — {highlight}\n"
                        f"> 🎯 Solves: `{entry['words_solved']}` | 🏆 Wins: `{won}` ({win_pct:.0f}%) | 🧩 Guesses: `{entry['total_guesses']}` | 🔥 Streak: `{entry.get('current_streak', 0)}`"
                    )
                elif rank_num == 2:
                    lines.append(
                        f"🥈 **2nd Place**: **{entry['user_name']}** — {highlight}\n"
                        f"> 🎯 Solves: `{entry['words_solved']}` | 🏆 Wins: `{won}` ({win_pct:.0f}%) | 🧩 Guesses: `{entry['total_guesses']}` | 🔥 Streak: `{entry.get('current_streak', 0)}`"
                    )
                elif rank_num == 3:
                    lines.append(
                        f"🥉 **3rd Place**: **{entry['user_name']}** — {highlight}\n"
                        f"> 🎯 Solves: `{entry['words_solved']}` | 🏆 Wins: `{won}` ({win_pct:.0f}%) | 🧩 Guesses: `{entry['total_guesses']}` | 🔥 Streak: `{entry.get('current_streak', 0)}`"
                    )
                else:
                    badge_num = num_emojis.get(rank_num, f"`#{rank_num:2d}`")
                    lines.append(
                        f"{badge_num} **{entry['user_name']}** — {highlight} "
                        f"(🎯 `{entry['words_solved']}` • 🏆 `{won}` • 🔥 `{entry.get('current_streak', 0)}`)"
                    )

            embed.description += "\n\n".join(lines)

        if user_stats:
            u_played = user_stats.get("games_played", 0)
            u_won = user_stats.get("games_won", 0)
            u_win_pct = (u_won / u_played * 100) if u_played > 0 else 0.0
            rank_str = f"#{user_rank}" if user_rank else "Unranked"
            embed.add_field(
                name="👤 Your Server Standing",
                value=(
                    f"**Rank**: `{rank_str}` of `{self.total_players}` | **Points**: `{user_stats['points']:,} pts`\n"
                    f"🎯 Solves: `{user_stats['words_solved']}` | 🏆 Wins: `{u_won}` ({u_win_pct:.0f}%) | 🔥 Streak: `{user_stats.get('current_streak', 0)}`"
                ),
                inline=False
            )
        else:
            embed.add_field(
                name="👤 Your Server Standing",
                value="*You haven't played any Co-ordle games on this server yet! Start with `/coordle`.*",
                inline=False
            )

        embed.set_footer(text=f"Page {self.page + 1}/{max(1, self.max_pages)} • {self.total_players} total players • Use dropdown to change sort")
        self.update_buttons()
        return embed

    @discord.ui.select(
        placeholder="Select Leaderboard Category",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="All-Time Points", value="points", description="Rank by total points accumulated", emoji="🏆", default=True),
            discord.SelectOption(label="Words Solved", value="solves", description="Rank by mystery words solved", emoji="🎯"),
            discord.SelectOption(label="Cooperative Wins", value="wins", description="Rank by team game victories", emoji="🏅"),
            discord.SelectOption(label="Daily Win Streaks", value="streak", description="Rank by active daily Wordle streak", emoji="🔥"),
        ],
        row=0
    )
    async def category_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.category = select.values[0]
        for opt in select.options:
            opt.default = (opt.value == self.category)
        self.page = 0
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="First", emoji="⏮️", style=discord.ButtonStyle.secondary, row=1)
    async def first_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Prev", emoji="◀", style=discord.ButtonStyle.primary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Next", emoji="▶", style=discord.ButtonStyle.primary, row=1)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Last", emoji="⏭️", style=discord.ButtonStyle.secondary, row=1)
    async def last_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.max_pages - 1)
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


__all__ = [
    "CoordleGuessModal",
    "CoordleGameView",
    "CoordleSessionLeaderboardView",
    "CoordleSessionStartView",
    "CoordleLeaderboardView",
]
