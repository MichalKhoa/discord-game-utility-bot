import os
import json
import random
import asyncio
import time
import hashlib
import datetime
from typing import List, Dict, Optional, Tuple, Set, Any
from collections import Counter

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from databases.coordle_database import CoordleDatabase

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(ROOT_DIR, "assets", "wordle")
DATA_DIR = os.path.join(ROOT_DIR, "data", "wordle")

# In-memory dictionary cache: {length: (answers_list, valid_guesses_set)}
WORD_CACHE: Dict[int, Tuple[List[str], Set[str]]] = {}
# In-memory definition cache: {word: definition_str}
DEFINITION_CACHE: Dict[str, str] = {}


def load_words(length: int) -> Tuple[List[str], Set[str]]:
    """
    Loads and caches word lists for a specific length.
    Checks assets/wordle/ first (immune to Docker volume mounts over data/),
    then data/wordle/, and falls back to GitHub raw fetch if files are missing.
    """
    if length in WORD_CACHE:
        return WORD_CACHE[length]

    search_dirs = [ASSETS_DIR, DATA_DIR]
    guesses: Set[str] = set()
    answers: List[str] = []

    for d in search_dirs:
        g_path = os.path.join(d, f"guesses_{length}.json")
        a_path = os.path.join(d, f"answers_{length}.json")
        if not guesses and os.path.exists(g_path):
            try:
                with open(g_path, "r", encoding="utf-8") as f:
                    guesses = set(json.load(f))
            except Exception:
                pass
        if not answers and os.path.exists(a_path):
            try:
                with open(a_path, "r", encoding="utf-8") as f:
                    answers = json.load(f)
            except Exception:
                pass
        if answers and guesses:
            break

    # Fallback: auto-download from GitHub raw if completely missing in runtime environment
    if not answers or not guesses:
        import urllib.request
        base_url = "https://raw.githubusercontent.com/MichalKhoa/discord-game-utility-bot/master/assets/wordle"
        os.makedirs(ASSETS_DIR, exist_ok=True)
        if not guesses:
            try:
                url = f"{base_url}/guesses_{length}.json"
                req = urllib.request.Request(url, headers={"User-Agent": "DiscordBot/1.0"})
                with urllib.request.urlopen(req, timeout=5) as response:
                    guesses = set(json.loads(response.read().decode("utf-8")))
                    with open(os.path.join(ASSETS_DIR, f"guesses_{length}.json"), "w", encoding="utf-8") as f:
                        json.dump(list(guesses), f)
            except Exception as e:
                print(f"[Coordle] Could not fetch guesses_{length}.json from fallback: {e}")

        if not answers:
            try:
                url = f"{base_url}/answers_{length}.json"
                req = urllib.request.Request(url, headers={"User-Agent": "DiscordBot/1.0"})
                with urllib.request.urlopen(req, timeout=5) as response:
                    answers = json.loads(response.read().decode("utf-8"))
                    with open(os.path.join(ASSETS_DIR, f"answers_{length}.json"), "w", encoding="utf-8") as f:
                        json.dump(answers, f)
            except Exception as e:
                print(f"[Coordle] Could not fetch answers_{length}.json from fallback: {e}")

    if not answers and guesses:
        answers = list(guesses)

    WORD_CACHE[length] = (answers, guesses)
    return answers, guesses


def get_daily_word(guild_id: int, date_str: str) -> str:
    """Generates a deterministic 5-letter mystery word for a guild's daily challenge."""
    answers, _ = load_words(5)
    if not answers:
        return "CRANE"
    seed_str = f"{date_str}-{guild_id}"
    seed_val = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest(), 16)
    return answers[seed_val % len(answers)].upper()


async def fetch_word_definition(word: str, db: Optional[CoordleDatabase] = None) -> Optional[str]:
    """
    Fetches a concise one-line English definition for the given word.
    2-Tier Caching:
    1. RAM Cache (0ms)
    2. SQLite Persistent DB (0.1ms)
    3. External APIs (Datamuse & Free Dictionary API) -> persisted to DB & RAM
    """
    w = word.lower().strip()
    if w in DEFINITION_CACHE:
        return DEFINITION_CACHE[w]

    # Check SQLite Persistent Cache
    if db:
        try:
            cached_db = await db.get_definition(w)
            if cached_db:
                DEFINITION_CACHE[w] = cached_db
                return cached_db
        except Exception:
            pass

    result: Optional[str] = None

    # 1. Try Datamuse API (fast, reliable dictionary metadata)
    try:
        url = f"https://api.datamuse.com/words?sp={w}&md=d&max=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and "defs" in data[0] and data[0]["defs"]:
                        raw_def = data[0]["defs"][0]
                        if "\t" in raw_def:
                            pos, text = raw_def.split("\t", 1)
                            pos_map = {"n": "noun", "v": "verb", "adj": "adjective", "adv": "adverb"}
                            prefix = f"*({pos_map.get(pos, pos)})* " if pos in pos_map else ""
                            result = f"{prefix}{text.strip()}"
                        else:
                            result = raw_def.strip()
    except Exception:
        pass

    # 2. Fallback to Free Dictionary API if Datamuse returned empty
    if not result:
        try:
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data and isinstance(data, list) and "meanings" in data[0]:
                            meaning = data[0]["meanings"][0]
                            part = meaning.get("partOfSpeech", "")
                            defs = meaning.get("definitions", [])
                            if defs and "definition" in defs[0]:
                                text = defs[0]["definition"]
                                prefix = f"*({part})* " if part else ""
                                result = f"{prefix}{text.strip()}"
        except Exception:
            pass

    # 3. Lemmatization Fallback: Try root lemma if inflected form returned no definition
    if not result:
        candidate_lemmas = get_candidate_lemmas(w)
        for lemma in candidate_lemmas:
            # Check SQLite or API for lemma
            lemma_def = None
            if db:
                try:
                    lemma_def = await db.get_definition(lemma)
                except Exception:
                    pass
            if not lemma_def:
                try:
                    url = f"https://api.datamuse.com/words?sp={lemma}&md=d&max=1"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                            if resp.status == 200:
                                d_data = await resp.json()
                                if d_data and "defs" in d_data[0] and d_data[0]["defs"]:
                                    raw = d_data[0]["defs"][0]
                                    if "\t" in raw:
                                        p_pos, p_txt = raw.split("\t", 1)
                                        pos_map = {"n": "noun", "v": "verb", "adj": "adjective", "adv": "adverb"}
                                        pref = f"*({pos_map.get(p_pos, p_pos)})* " if p_pos in pos_map else ""
                                        lemma_def = f"{pref}{p_txt.strip()}"
                                    else:
                                        lemma_def = raw.strip()
                except Exception:
                    pass
            if lemma_def:
                result = f"*(Root: {lemma.upper()})* {lemma_def}"
                break

    if result:
        DEFINITION_CACHE[w] = result
        if db:
            try:
                await db.save_definition(w, result)
            except Exception as e:
                print(f"Failed to persist definition for '{w}' to SQLite: {e}")
        return result

    return None


def find_typo_suggestions(guess: str, valid_words: Set[str], max_suggestions: int = 2) -> List[str]:
    """
    Finds smart typo suggestions using adjacent letter transpositions,
    1-character substitution, and anagram matching.
    Runs in < 5ms for standard Wordle dictionary sizes.
    """
    guess = guess.lower()
    g_len = len(guess)
    suggestions: List[str] = []

    # 1. Adjacent letter swaps (e.g., craen -> crane, teh -> the)
    for i in range(g_len - 1):
        swapped = guess[:i] + guess[i+1] + guess[i] + guess[i+2:]
        if swapped in valid_words and swapped != guess and swapped not in suggestions:
            suggestions.append(swapped)
            if len(suggestions) >= max_suggestions:
                return suggestions

    # 2. 1-character substitution typos (e.g., fjrod -> fjord, wrter -> water)
    for w in valid_words:
        if len(w) == g_len and sum(1 for a, b in zip(guess, w) if a != b) == 1:
            if w not in suggestions:
                suggestions.append(w)
                if len(suggestions) >= max_suggestions:
                    return suggestions

    # 3. Exact anagram match
    guess_sorted = sorted(guess)
    for w in valid_words:
        if len(w) == g_len and sorted(w) == guess_sorted and w != guess and w not in suggestions:
            suggestions.append(w)
            if len(suggestions) >= max_suggestions:
                return suggestions

    return suggestions


def get_candidate_lemmas(word: str) -> List[str]:
    """Generates root candidate forms for inflected words to improve definition lookups."""
    w = word.lower().strip()
    lemmas = []
    if w.endswith("ies") and len(w) > 4:
        lemmas.append(w[:-3] + "y")
    if w.endswith("es") and len(w) > 4:
        lemmas.append(w[:-2])
    if w.endswith("s") and len(w) > 3 and not w.endswith("ss"):
        lemmas.append(w[:-1])
    if w.endswith("ed") and len(w) > 3:
        lemmas.append(w[:-1])  # baked -> bake
        lemmas.append(w[:-2])  # walked -> walk
    if w.endswith("ing") and len(w) > 5:
        lemmas.append(w[:-3])       # jumping -> jump
        lemmas.append(w[:-3] + "e") # baking -> bake
    if w.endswith("er") and len(w) > 4:
        lemmas.append(w[:-1])  # finer -> fine
        lemmas.append(w[:-2])  # faster -> fast
    return [l for l in lemmas if l != w]

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
            "• **15s Anti-Spam Cooldown**: After guessing, wait 15 seconds to let other teammates guess.\n"
            "• Invalid words or wrong lengths receive an ephemeral warning and do **not** cost an attempt.\n"
            "• Use the live **Letter Tracker (QWERTY)** to see discovered and eliminated letters."
        ),
        inline=False
    )
    embed.add_field(
        name="⚡ Game Modes",
        value=(
            "• **Standard Mode**: Take your time (up to 12 hours) to solve the mystery word.\n"
            "• **⚡ Blitz Mode**: Starts with 60 seconds! Each valid guess adds +10s (max 120s). "
            "All points earned get a **1.5x speed multiplier**!\n"
            "• **📅 Daily Co-ordle**: A unique server-wide word of the day that resets at 00:00 UTC. "
            "Win daily puzzles to build your server win streak!"
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
            "`/coordle [length] [attempts] [mode]` — Start a custom Co-ordle game\n"
            "`/coordle_daily` — Play today's server word of the day\n"
            "`/coordle_daily_channel [set/remove]` — Configure automated daily challenge channel (Admin)\n"
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
        guild_id: Optional[int] = None,
        mode: str = "normal",
        is_daily: bool = False,
        daily_date_str: str = ""
    ):
        self.target_word: str = target_word.upper()
        self.word_length: int = len(target_word)
        self.max_attempts: int = max_attempts
        self.host: Optional[discord.Member | discord.User] = host
        self.guild_id: int = guild_id or 0
        self.mode: str = mode.lower()  # "normal" or "blitz"
        self.is_daily: bool = is_daily
        self.daily_date_str: str = daily_date_str or datetime.date.today().strftime("%Y-%m-%d")

        self.guesses: List[Tuple[str, List[str], str, int]] = []  # (word, pattern, author_name, points_earned)
        self.game_over: bool = False
        self.won: bool = False
        self.solver: Optional[str] = None
        self.surrendered: bool = False
        self.expired: bool = False

        # Discovery tracking for points
        self.known_green_indices: Set[int] = set()
        self.known_target_chars: Set[str] = set()

        # Timing: 12-hour expiration for standard games, or 60s running clock for Blitz
        self.created_at: float = time.time()
        self.expires_at: float = self.created_at + 43200  # 12 hours
        self.blitz_expires_at: float = self.created_at + 60.0 if self.mode == "blitz" else 0.0

        # 15s turn-taking cooldown: user_id -> timestamp of last valid guess
        self.user_cooldowns: Dict[int, float] = {}

        # Cached dictionary definition for game-over embed
        self.definition: Optional[str] = None

        # Player stats during this match: user_id -> dict
        self.participants: Dict[int, Dict[str, Any]] = {}

        # Keyboard letter tracker: char -> 'G', 'Y', 'B'
        self.letter_status: Dict[str, str] = {}

    async def ensure_definition(self, db: Optional[CoordleDatabase] = None):
        """Fetches and caches the definition for target word upon game conclusion."""
        if not self.definition:
            self.definition = await fetch_word_definition(self.target_word, db=db)

    def generate_share_text(self) -> str:
        """Generates standard Wordle emoji spoiler grid for sharing."""
        tile_map = {'G': '🟩', 'Y': '🟨', 'B': '⬛'}
        status_icon = "🟩" if self.won else "⬛"
        attempts_str = f"{len(self.guesses)}/{self.max_attempts}" if self.won else "X"
        header = f"🟩 Co-ordle ({self.word_length} Letters) {attempts_str} {status_icon}"
        if self.is_daily:
            header = f"📅 Co-ordle Daily ({self.daily_date_str}) {attempts_str} {status_icon}"
        elif self.mode == "blitz":
            header = f"⚡ Co-ordle Blitz ({self.word_length} Letters) {attempts_str} {status_icon}"

        lines = [header, ""]
        for _, pattern, _, _ in self.guesses:
            lines.append("".join(tile_map[p] for p in pattern))
        return "\n".join(lines)

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

        # Blitz bonus: add 10 seconds to clock (capped at +120s from now)
        if self.mode == "blitz" and not self.game_over:
            self.blitz_expires_at = min(time.time() + 120.0, self.blitz_expires_at + 10.0)

        # Check win / loss
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

            # 1.5x Blitz points multiplier
            if self.mode == "blitz":
                guess_points = int(guess_points * 1.5)

            player_data["points"] += guess_points
            self.guesses.append((guess, eval_result, player_name, guess_points))
            return True, f"🎉 **{player_name}** solved the mystery word: **{self.target_word}**! (+{guess_points} pts)", guess_points

        # 1.5x Blitz points multiplier for clue points
        if self.mode == "blitz":
            guess_points = int(guess_points * 1.5)

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
        embed = self.game_view.get_embed()

        await interaction.response.edit_message(embed=embed, view=self.game_view)


class CoordleGameView(discord.ui.View):
    def __init__(self, game: CoordleGame, cog: Optional["Coordle"] = None):
        # 12 hours for standard/daily, or 150s for blitz view timeout
        view_timeout = 150 if game.mode == "blitz" else 43200
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
                    embed = self.get_embed()
                    if self.message:
                        try:
                            await self.message.edit(embed=embed, view=self)
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
            embed = self.get_embed()
            embed.title = f"⌛ Co-ordle ({self.game.word_length} Letters) — Expired"
            embed.colour = discord.Colour.dark_grey()
            embed.description += (
                f"\n\n⌛ **Game Expired**: This puzzle was inactive for 12 hours. "
                f"The mystery word was **`{self.game.target_word}`**."
            )
            if self.message:
                try:
                    await self.message.edit(embed=embed, view=self)
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

    def get_embed(self) -> discord.Embed:
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

        # Status / Timer line
        if self.game.game_over:
            timer_line = "🔒 **Status**: Concluded"
        elif self.game.mode == "blitz":
            timer_line = f"⚡ **Blitz Clock**: <t:{int(self.game.blitz_expires_at)}:R> (+10s/guess)"
        else:
            timer_line = f"⏳ **Expires**: <t:{int(self.game.expires_at)}:R>"

        mode_badge = "⚡ `BLITZ (1.5x PTS)`" if self.game.mode == "blitz" else ("📅 `DAILY PUZZLE`" if self.game.is_daily else "⏱️ `STANDARD`")

        desc = [
            f"**Mode**: {mode_badge} | **Attempts**: `{len(self.game.guesses)}/{self.game.max_attempts}` | {timer_line}",
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
        elif self.game.expired and self.game.mode == "blitz":
            desc.append(f"\n⚡ **Time Expired!** The Blitz clock hit 0. The mystery word was **`{self.game.target_word}`**.")
        elif self.game.game_over and not self.game.expired:
            desc.append(f"\n💀 Out of attempts! The mystery word was **`{self.game.target_word}`**.")

        # Show definition if available upon game conclusion
        if self.game.definition:
            desc.append(f"\n💡 **Word Meaning**: {self.game.definition}")

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
        embed = self.get_embed()
        embed.description += f"\n\n🏳️ Game ended early by {interaction.user.mention}. The word was **`{self.game.target_word}`**."
        await interaction.response.edit_message(embed=embed, view=self)


class Coordle(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = CoordleDatabase()

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
                embed = view.get_embed()
                msg = await channel.send(
                    f"🌅 **Good morning! The Daily Co-ordle for `{today_str}` has arrived!**\n"
                    f"Work together to solve today's mystery word and preserve your server win streak!",
                    embed=embed,
                    view=view
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
        max_attempts = max(4, min(12, max_attempts))
        guild_id = interaction.guild_id or (interaction.guild.id if interaction.guild else 0)

        if is_daily:
            today_str = datetime.date.today().strftime("%Y-%m-%d")
            target_word = get_daily_word(guild_id, today_str)
            game = CoordleGame(
                target_word=target_word,
                max_attempts=6,
                host=interaction.user,
                guild_id=guild_id,
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
                mode=mode
            )

        view = CoordleGameView(game, cog=self)
        embed = view.get_embed()

        if interaction.response.is_done():
            msg = await interaction.followup.send(embed=embed, view=view)
            view.message = msg
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
                streak = f" | 🔥 Streak: `{entry['current_streak']}`" if entry.get("current_streak") else ""
                lines.append(
                    f"{icon} **{entry['user_name']}** — **`{entry['points']:,} pts`**\n"
                    f"> 🎯 Solves: `{entry['words_solved']}` | 🏆 Wins: `{entry['games_won']}` | 🧩 Guesses: `{entry['total_guesses']}`{streak}"
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
        attempts="Total number of attempts allowed (4-12, default: 6)",
        mode="Game mode: Normal (relaxed) or Blitz (speedrun 60s clock with 1.5x points)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="⏱️ Normal Mode (Relaxed 12h timer)", value="normal"),
        app_commands.Choice(name="⚡ Blitz Mode (Speedrun 60s +10s/guess, 1.5x pts)", value="blitz")
    ])
    async def coordle_cmd(
        self,
        interaction: discord.Interaction,
        length: int = 5,
        attempts: int = 6,
        mode: str = "normal"
    ):
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


async def setup(bot: commands.Bot):
    print("Coordle cog loaded")
    await bot.add_cog(Coordle(bot))
