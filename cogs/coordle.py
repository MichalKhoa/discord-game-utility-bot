import os
import json
import random
import asyncio
from typing import List, Dict, Optional, Tuple, Set, Any
from collections import Counter

import discord
from discord import app_commands
from discord.ext import commands

from databases.coordle_database import CoordleDatabase

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "wordle")

# In-memory dictionary cache: {length: (answers_list, valid_guesses_set)}
WORD_CACHE: Dict[int, Tuple[List[str], Set[str]]] = {}


def load_words(length: int) -> Tuple[List[str], Set[str]]:
    """Loads and caches word lists for a specific length."""
    if length in WORD_CACHE:
        return WORD_CACHE[length]

    guesses_path = os.path.join(DATA_DIR, f"guesses_{length}.json")
    answers_path = os.path.join(DATA_DIR, f"answers_{length}.json")

    guesses: Set[str] = set()
    answers: List[str] = []

    if os.path.exists(guesses_path):
        with open(guesses_path, "r", encoding="utf-8") as f:
            guesses = set(json.load(f))
    if os.path.exists(answers_path):
        with open(answers_path, "r", encoding="utf-8") as f:
            answers = json.load(f)

    if not answers and guesses:
        answers = list(guesses)

    WORD_CACHE[length] = (answers, guesses)
    return answers, guesses


def evaluate_guess(target: str, guess: str) -> List[str]:
    """
    Standard Wordle duplicate handling algorithm:
    'G' = Green (🟩), 'Y' = Yellow (🟨), 'B' = Black/Gray (⬛)
    """
    result = ['B'] * len(target)
    target_counts = Counter(target)

    # 1. Exact matches (Green)
    for i in range(len(target)):
        if guess[i] == target[i]:
            result[i] = 'G'
            target_counts[guess[i]] -= 1

    # 2. Misplaced matches (Yellow)
    for i in range(len(target)):
        if result[i] == 'B' and target_counts.get(guess[i], 0) > 0:
            result[i] = 'Y'
            target_counts[guess[i]] -= 1

    return result


def build_rules_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🟩 Co-ordle — Rules & Scoring Guide",
        description=(
            "**Co-ordle** is a collaborative, server-wide Wordle game where everyone works "
            "together to deduce the secret English word before running out of attempts!\n"
        ),
        colour=discord.Colour.og_blurple()
    )
    embed.add_field(
        name="🎮 How to Play",
        value=(
            "• Click **🔤 Submit Guess** to enter a valid English word matching the puzzle length.\n"
            "• Anyone in the channel can contribute guesses toward the shared board.\n"
            "• Invalid words or wrong lengths receive an ephemeral warning and do **not** cost an attempt.\n"
            "• Use the live **Letter Tracker (QWERTY)** to see discovered and eliminated letters."
        ),
        inline=False
    )
    embed.add_field(
        name="🎨 Tile Color Guide",
        value=(
            "🟩 **Green**: Letter is in the word and in the **exact correct position**.\n"
            "🟨 **Yellow**: Letter is in the word, but in the **wrong position**.\n"
            "⬛ **Black**: Letter is **not in the secret word** at all.\n"
            "*Duplicate letters are strictly handled according to official Wordle rules.*"
        ),
        inline=False
    )
    embed.add_field(
        name="🏅 Point Scoring (Base-5)",
        value=(
            "• 🟩 **New Green Discovered**: `+10 pts` (First time a letter spot is found)\n"
            "• 🟨 **New Yellow Discovered**: `+5 pts` (First time a secret letter is revealed)\n"
            "• 🎯 **Solve Bonus**: `Letters Left to Guess × 5 pts`\n"
            "  *(Tap-in solves with 1 letter left give only `+5 pts` to prevent word stealing; "
            "clutch solves with 5+ letters left give up to `+40 pts`!)*\n"
            "• 🏆 **Team Win Bonus**: `+10 pts` to **all players** who contributed a valid guess!"
        ),
        inline=False
    )
    embed.add_field(
        name="⚡ Helpful Commands",
        value=(
            "`/coordle [length] [attempts]` — Start a custom Co-ordle game\n"
            "`/coordle_leaderboard` — View the top solvers on this server\n"
            "`/coordle_stats [member]` — View your or a friend's career record\n"
            "`/coordle_rules` — Display this rules panel anytime"
        ),
        inline=False
    )
    embed.set_footer(text="Co-ordle | Teamwork beats word stealing!")
    return embed


class CoordleGame:
    def __init__(
        self,
        target_word: str,
        max_attempts: int = 6,
        host: Optional[discord.Member | discord.User] = None,
        guild_id: Optional[int] = None
    ):
        self.target_word: str = target_word.upper()
        self.word_length: int = len(target_word)
        self.max_attempts: int = max_attempts
        self.host: Optional[discord.Member | discord.User] = host
        self.guild_id: int = guild_id or 0
        self.guesses: List[Tuple[str, List[str], str, int]] = []  # (word, pattern, author_name, points_earned)
        self.game_over: bool = False
        self.won: bool = False
        self.solver: Optional[str] = None
        self.surrendered: bool = False

        # Discovery tracking for points
        self.known_green_indices: Set[int] = set()
        self.known_target_chars: Set[str] = set()

        # Player stats during this match: user_id -> dict
        self.participants: Dict[int, Dict[str, Any]] = {}

        # Keyboard letter tracker: char -> 'G', 'Y', 'B'
        self.letter_status: Dict[str, str] = {}

    def submit_guess(self, guess: str, user: discord.Member | discord.User) -> Tuple[bool, str, int]:
        guess = guess.upper()
        eval_result = evaluate_guess(self.target_word, guess)
        player_name = user.display_name
        user_id = user.id

        if user_id not in self.participants:
            self.participants[user_id] = {
                "name": player_name,
                "points": 0,
                "guesses": 0,
                "greens": 0,
                "yellows": 0,
                "won": False,
                "solved": False
            }

        player_data = self.participants[user_id]
        player_data["guesses"] += 1

        # Point calculations (simple base-5):
        # 🟨 New Yellow: +5 pts
        # 🟩 New Green: +10 pts
        letters_to_guess_before = self.word_length - len(self.known_green_indices)
        guess_points = 0
        new_greens = 0
        new_yellows = 0

        # Newly discovered green positions (+10 pts each)
        for i, status in enumerate(eval_result):
            if status == 'G' and i not in self.known_green_indices:
                self.known_green_indices.add(i)
                guess_points += 10
                new_greens += 1
                self.known_target_chars.add(guess[i])

        # Newly discovered yellow letters (+5 pts each)
        for i, status in enumerate(eval_result):
            char = guess[i]
            if status == 'Y' and char not in self.known_target_chars:
                self.known_target_chars.add(char)
                guess_points += 5
                new_yellows += 1

        player_data["greens"] += new_greens
        player_data["yellows"] += new_yellows

        # Keyboard update
        for char, status in zip(guess, eval_result):
            current = self.letter_status.get(char)
            if current != 'G':
                if status == 'G':
                    self.letter_status[char] = 'G'
                elif status == 'Y' and current != 'G':
                    self.letter_status[char] = 'Y'
                elif current is None:
                    self.letter_status[char] = 'B'

        # Check win / loss
        attempt_num = len(self.guesses) + 1
        if guess == self.target_word:
            self.game_over = True
            self.won = True
            self.solver = player_name
            player_data["solved"] = True

            # Anti-sniping solve bonus:
            # Solve Bonus = Letters Left to Guess * 5 pts
            # (A 1-letter tap-in only gives +5 pts to prevent word stealing, while clutch solves give up to +40 pts)
            solve_bonus = letters_to_guess_before * 5
            guess_points += solve_bonus

            # 🏆 Team win bonus for all contributors: +10 pts
            for uid, p in self.participants.items():
                p["won"] = True
                p["points"] += 10

            player_data["points"] += guess_points
            self.guesses.append((guess, eval_result, player_name, guess_points))
            return True, f"🎉 **{player_name}** solved the mystery word: **{self.target_word}**! (+{guess_points} pts)", guess_points

        player_data["points"] += guess_points
        self.guesses.append((guess, eval_result, player_name, guess_points))

        if len(self.guesses) >= self.max_attempts:
            self.game_over = True
            self.won = False
            return True, f"💀 Game Over! The mystery word was **{self.target_word}**.", guess_points

        return False, f"Attempt `{len(self.guesses)}/{self.max_attempts}` (+{guess_points} pts)", guess_points


class CoordleGuessModal(discord.ui.Modal):
    def __init__(self, game_view: "CoordleGameView"):
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

        # Check dictionary
        _, valid_guesses = load_words(self.game_view.game.word_length)
        if valid_guesses and guess not in valid_guesses:
            await interaction.response.send_message(
                f"❌ **{guess.upper()}** is not in the valid dictionary word list!",
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

        # Apply guess
        self.game_view.game.submit_guess(guess, interaction.user)

        # If game concluded, save stats asynchronously
        if self.game_view.game.game_over and self.game_view.cog:
            asyncio.create_task(self.game_view.save_stats())

        self.game_view.update_buttons()
        embed = self.game_view.get_embed()

        await interaction.response.edit_message(embed=embed, view=self.game_view)


class CoordleGameView(discord.ui.View):
    def __init__(self, game: CoordleGame, cog: Optional["Coordle"] = None):
        super().__init__(timeout=600)
        self.game = game
        self.cog = cog
        self.update_buttons()

    def update_buttons(self):
        self.guess_btn.disabled = self.game.game_over
        self.surrender_btn.disabled = self.game.game_over

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
            except Exception as e:
                print(f"Error saving Coordle stats for user {uid}: {e}")

    def get_embed(self) -> discord.Embed:
        if self.game.won:
            color = discord.Colour.green()
            title = f"🟩 Co-ordle ({self.game.word_length} Letters) — Victory!"
        elif self.game.game_over:
            color = discord.Colour.red()
            title = f"⬛ Co-ordle ({self.game.word_length} Letters) — Defeat"
        else:
            color = discord.Colour.gold()
            title = f"🟩 Co-ordle ({self.game.word_length} Letters) — Guess the Word!"

        board_lines = []
        tile_map = {'G': '🟩', 'Y': '🟨', 'B': '⬛'}

        for i, (word, pattern, author, pts) in enumerate(self.game.guesses, 1):
            tiles = "".join(tile_map[p] for p in pattern)
            word_spaced = " ".join(list(word))
            board_lines.append(f"`{i:2d}.` {tiles}  **`{word_spaced}`**  — *{author}* (`+{pts} pts`)")

        # Fill remaining attempt slots
        empty_slot = "⬜" * self.game.word_length
        for i in range(len(self.game.guesses) + 1, self.game.max_attempts + 1):
            board_lines.append(f"`{i:2d}.` {empty_slot}")

        board_text = "\n".join(board_lines)

        # Keyboard letter tracker (QWERTY layout)
        qwerty = [
            "Q W E R T Y U I O P",
            "A S D F G H J K L",
            "Z X C V B N M"
        ]
        keyboard_lines = []
        for row in qwerty:
            row_display = []
            for char in row.split():
                st = self.game.letter_status.get(char)
                if st == 'G':
                    row_display.append(f"🟩{char}")
                elif st == 'Y':
                    row_display.append(f"🟨{char}")
                elif st == 'B':
                    row_display.append(f"~~{char}~~")
                else:
                    row_display.append(char)
            keyboard_lines.append(" ".join(row_display))
        keyboard_text = "\n".join(keyboard_lines)

        desc = [
            f"**Word Length**: `{self.game.word_length}` | **Attempts**: `{len(self.game.guesses)}/{self.game.max_attempts}`",
            "",
            "### 📋 Guess Board",
            board_text,
            "",
            "### ⌨️ Letter Tracker",
            keyboard_text,
        ]

        if self.game.won:
            desc.append(f"\n🎉 **{self.game.solver}** solved the mystery word: **`{self.game.target_word}`** in `{len(self.game.guesses)}` attempts!")
            # Summary of points earned
            pts_summary = ", ".join(f"**{p['name']}**: `+{p['points']} pts`" for p in self.game.participants.values())
            if pts_summary:
                desc.append(f"🏅 **Match Rewards**: {pts_summary}")
        elif self.game.game_over:
            desc.append(f"\n💀 Out of attempts! The mystery word was **`{self.game.target_word}`**.")

        embed = discord.Embed(
            title=title,
            description="\n".join(desc),
            colour=color
        )
        embed.set_footer(text="Scoring: 🟨 +5 | 🟩 +10 | 🎯 Solve: Letters Left × 5 | 🏆 Team Win: +10")
        return embed

    @discord.ui.button(label="Submit Guess", style=discord.ButtonStyle.success, emoji="🔤", row=0)
    async def guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CoordleGuessModal(self))

    @discord.ui.button(label="Rules", style=discord.ButtonStyle.secondary, emoji="📖", row=0)
    async def rules_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_rules_embed(), ephemeral=True)

    @discord.ui.button(label="Surrender", style=discord.ButtonStyle.secondary, emoji="🏳️", row=0)
    async def surrender_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.host and interaction.user.id != self.game.host.id and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Only the host or a server admin can surrender the game.", ephemeral=True)
            return

        self.game.game_over = True
        self.game.surrendered = True
        if self.cog:
            asyncio.create_task(self.save_stats())
        self.update_buttons()
        embed = self.get_embed()
        embed.description += f"\n\n🏳️ Game ended early by {interaction.user.mention}. The word was **`{self.game.target_word}`**."
        await interaction.response.edit_message(embed=embed, view=self)


class Coordle(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = CoordleDatabase()

    async def cog_load(self):
        await self.db.init_db()

    async def start_game(
        self,
        interaction: discord.Interaction,
        length: int = 5,
        max_attempts: int = 6
    ):
        length = max(4, min(8, length))
        max_attempts = max(4, min(12, max_attempts))

        answers, _ = load_words(length)
        if not answers:
            msg = f"❌ No word list available for {length}-letter words."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            return

        target_word = random.choice(answers)
        guild_id = interaction.guild_id or (interaction.guild.id if interaction.guild else 0)
        game = CoordleGame(
            target_word=target_word,
            max_attempts=max_attempts,
            host=interaction.user,
            guild_id=guild_id
        )
        view = CoordleGameView(game, cog=self)
        embed = view.get_embed()

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    async def show_leaderboard(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id or (interaction.guild.id if interaction.guild else 0)
        leaderboard = await self.db.get_leaderboard(guild_id, limit=10)
        user_rank, total_players = await self.db.get_user_rank(interaction.user.id, guild_id)

        embed = discord.Embed(
            title="🏆 Co-ordle Server Leaderboard",
            description=(
                "Compete in cooperative Wordle games to earn points and climb the rankings!\n\n"
                "**Scoring:** 🟨 `+5` | 🟩 `+10` | 🎯 Solve: `Letters Left × 5` | 🏆 Team Win: `+10`\n"
            ),
            colour=discord.Colour.gold()
        )

        medals = ["🥇", "🥈", "🥉"]

        if not leaderboard:
            embed.description += "\n*No games have been recorded yet! Start one with `/coordle` or through `/menu`.*"
        else:
            lines = []
            for idx, entry in enumerate(leaderboard, 1):
                icon = medals[idx - 1] if idx <= 3 else f"`#{idx:2d}`"
                lines.append(
                    f"{icon} **{entry['user_name']}** — **`{entry['points']:,} pts`**\n"
                    f"> 🎯 Solves: `{entry['words_solved']}` | 🏆 Wins: `{entry['games_won']}` | 🧩 Guesses: `{entry['total_guesses']}`"
                )
            embed.description += "\n\n".join(lines)

        footer_text = f"Total Players: {total_players}"
        if user_rank:
            footer_text += f" | Your Rank: #{user_rank}"
        embed.set_footer(text=footer_text)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

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
            embed.add_field(name="🔤 Total Guesses", value=f"`{stats['total_guesses']}`", inline=True)

            embed.add_field(name="🟩 Greens Found", value=f"`{stats['green_discovered']}`", inline=True)
            embed.add_field(name="🟨 Yellows Found", value=f"`{stats['yellow_discovered']}`", inline=True)

        embed.set_footer(text="Play /coordle to climb the server leaderboard!")

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="coordle", description="Start a cooperative Wordle game with custom word length and attempts.")
    @app_commands.describe(
        length="Word length to guess (4-8 letters, default: 5)",
        attempts="Total number of attempts allowed (4-12, default: 6)"
    )
    async def coordle_cmd(
        self,
        interaction: discord.Interaction,
        length: int = 5,
        attempts: int = 6
    ):
        await self.start_game(interaction, length=length, max_attempts=attempts)

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


async def setup(bot: commands.Bot):
    print("Coordle cog loaded")
    await bot.add_cog(Coordle(bot))
