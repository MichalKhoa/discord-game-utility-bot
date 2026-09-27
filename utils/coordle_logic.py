from __future__ import annotations

import os
import json
import random
import time
import hashlib
import datetime
import difflib
import math
import re
import string
from collections import Counter
from typing import List, Dict, Optional, Tuple, Set, Any, TYPE_CHECKING

import aiohttp
import discord

from databases.coordle_database import CoordleDatabase

if TYPE_CHECKING:
    from cogs.coordle import Coordle

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
            "• Use the live **Word Progress** and categorized **Letter Tracker** to see discovered, misplaced, and eliminated letters."
        ),
        inline=False
    )
    embed.add_field(
        name="⚡ Game Modes",
        value=(
            "• **Standard Mode**: Take your time (up to 24 hours) to solve the mystery word.\n"
            "• **⚡ Blitz Mode**: Starts with 5 minutes (300s)! Each valid guess adds +30s (max 10 mins). "
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
            "`/coordle_session [start/leaderboard/end]` — Host competitive match session\n"
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
        daily_date_str: str = "",
        channel_id: Optional[int] = None
    ):
        self.target_word: str = target_word.upper()
        self.word_length: int = len(target_word)
        self.max_attempts: int = max_attempts
        self.host: Optional[discord.Member | discord.User] = host
        self.guild_id: int = guild_id or 0
        self.channel_id: int = channel_id or 0
        self.mode: str = mode.lower()  # "normal" or "blitz"
        self.is_daily: bool = is_daily
        self.daily_date_str: str = daily_date_str or datetime.date.today().strftime("%Y-%m-%d")

        self.guesses: List[Tuple[str, List[str], str, int, List[str]]] = []  # (word, pattern, author_name, points_earned, discoveries)
        self.game_over: bool = False
        self.won: bool = False
        self.solver: Optional[str] = None
        self.surrendered: bool = False
        self.expired: bool = False

        # Discovery tracking for points
        self.known_green_indices: Set[int] = set()
        self.known_target_chars: Set[str] = set()

        # Timing: 24-hour expiration for standard games, or 300s running clock for Blitz
        self.created_at: float = time.time()
        self.expires_at: float = self.created_at + 86400  # 24 hours
        self.blitz_expires_at: float = self.created_at + 300.0 if self.mode == "blitz" else 0.0

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
        for entry in self.guesses:
            pattern = entry[1]
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
        discoveries: List[str] = []

        # Newly discovered green positions (+10 pts each)
        for i, status in enumerate(eval_result):
            if status == 'G' and i not in self.known_green_indices:
                self.known_green_indices.add(i)
                guess_points += 10
                new_greens += 1
                self.known_target_chars.add(guess[i])
                discoveries.append(f"🟩{guess[i]}")

        # Newly discovered yellow letters (+5 pts each)
        for i, status in enumerate(eval_result):
            char = guess[i]
            if status == 'Y' and char not in self.known_target_chars:
                self.known_target_chars.add(char)
                guess_points += 5
                new_yellows += 1
                discoveries.append(f"🟨{char}")

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

        # Blitz bonus: add 30 seconds to clock (capped at +600s / 10m from now)
        if self.mode == "blitz" and not self.game_over:
            self.blitz_expires_at = min(time.time() + 600.0, self.blitz_expires_at + 30.0)

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
            discoveries.append("🎯 Solved!")
            self.guesses.append((guess, eval_result, player_name, guess_points, discoveries))
            return True, f"🎉 **{player_name}** solved the mystery word: **{self.target_word}**! (+{guess_points} pts)", guess_points

        # 1.5x Blitz points multiplier for clue points
        if self.mode == "blitz":
            guess_points = int(guess_points * 1.5)

        player_data["points"] += guess_points
        self.guesses.append((guess, eval_result, player_name, guess_points, discoveries))

        if len(self.guesses) >= self.max_attempts:
            self.game_over = True
            self.won = False
            return True, f"💀 Game Over! The mystery word was **{self.target_word}**.", guess_points

        discovery_msg = f" (Found {', '.join(discoveries)})" if discoveries else ""
        return False, f"Attempt `{len(self.guesses)}/{self.max_attempts}` (+{guess_points} pts{discovery_msg})", guess_points


class CoordleSession:
    def __init__(
        self,
        channel_id: int,
        guild_id: int,
        host: discord.Member | discord.User,
        name: str = "Competitive Match",
        target_rounds: Optional[int] = None
    ):
        self.channel_id: int = channel_id
        self.guild_id: int = guild_id
        self.host: discord.Member | discord.User = host
        self.name: str = name.strip() if name and name.strip() else "Competitive Match"
        self.target_rounds: Optional[int] = target_rounds
        self.rounds_played: int = 0
        self.created_at: float = time.time()
        self.last_activity: float = time.time()
        self.is_active: bool = True
        self.scores: Dict[int, Dict[str, Any]] = {}

    def record_game_results(self, game: "CoordleGame"):
        self.rounds_played += 1
        self.last_activity = time.time()

        for uid, p in game.participants.items():
            if uid not in self.scores:
                self.scores[uid] = {
                    "user_id": uid,
                    "user_name": p["name"],
                    "points": 0,
                    "words_solved": 0,
                    "games_won": 0,
                    "total_guesses": 0,
                    "greens": 0,
                    "yellows": 0,
                }
            self.scores[uid]["points"] += p["points"]
            if p.get("solved"):
                self.scores[uid]["words_solved"] += 1
            if p.get("won"):
                self.scores[uid]["games_won"] += 1
            self.scores[uid]["total_guesses"] += p["guesses"]
            self.scores[uid]["greens"] += p.get("greens", 0)
            self.scores[uid]["yellows"] += p.get("yellows", 0)

    def get_leaderboard(self, sort_by: str = "points") -> List[Dict[str, Any]]:
        entries = list(self.scores.values())
        if sort_by == "solves":
            entries.sort(key=lambda x: (x["words_solved"], x["points"], x["games_won"]), reverse=True)
        elif sort_by == "wins":
            entries.sort(key=lambda x: (x["games_won"], x["points"], x["words_solved"]), reverse=True)
        else:
            entries.sort(key=lambda x: (x["points"], x["words_solved"], x["games_won"]), reverse=True)
        return entries

    def build_summary_embed(self, is_final: bool = False, sort_by: str = "points") -> discord.Embed:
        meta_titles = {
            "points": "All-Time Points",
            "solves": "Words Solved",
            "wins": "Games Won"
        }
        title_prefix = "🏁 Competitive Session Concluded" if is_final else "🏆 Competitive Session Leaderboard"
        embed = discord.Embed(
            title=f"{title_prefix}: {self.name}",
            colour=discord.Colour.gold() if is_final else discord.Colour.og_blurple()
        )

        target_str = f"/{self.target_rounds}" if self.target_rounds else ""
        status_str = "Concluded" if is_final else "In Progress"
        embed.description = (
            f"**Host**: {self.host.mention} | **Status**: `{status_str}` | **Rounds Played**: `{self.rounds_played}{target_str}`\n"
            f"*Sorting by: **{meta_titles.get(sort_by, 'Points')}***\n\n"
        )

        entries = self.get_leaderboard(sort_by=sort_by)
        if not entries:
            embed.description += "*No points scored yet in this session! Submit guesses in `/coordle` games in this channel.*"
            return embed

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        num_emojis = {4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"}

        for idx, entry in enumerate(entries, 1):
            highlight = f"**`{entry['points']:,} pts`**"
            if sort_by == "solves":
                highlight = f"**`{entry['words_solved']} solves`** ({entry['points']:,} pts)"
            elif sort_by == "wins":
                highlight = f"**`{entry['games_won']} wins`** ({entry['points']:,} pts)"

            if idx == 1:
                prefix = "🥇 **Session Champion**" if is_final else "🥇 **1st Place**"
                lines.append(
                    f"{prefix}: **{entry['user_name']}** — {highlight}\n"
                    f"> 🎯 Solves: `{entry['words_solved']}` | 🏆 Wins: `{entry['games_won']}` | 🧩 Guesses: `{entry['total_guesses']}` | 🟩 `{entry['greens']}` 🟨 `{entry['yellows']}`"
                )
            elif idx in (2, 3):
                medal = medals[idx - 1]
                place_str = "2nd Place" if idx == 2 else "3rd Place"
                lines.append(
                    f"{medal} **{place_str}: {entry['user_name']}** — {highlight}\n"
                    f"> 🎯 Solves: `{entry['words_solved']}` | 🏆 Wins: `{entry['games_won']}` | 🧩 Guesses: `{entry['total_guesses']}`"
                )
            else:
                badge = num_emojis.get(idx, f"`#{idx:2d}`")
                lines.append(f"{badge} **{entry['user_name']}** — {highlight} (🎯 `{entry['words_solved']}` • 🏆 `{entry['games_won']}`)")

        embed.description += "\n\n".join(lines)
        footer_msg = "Final Results • GG to all contenders!" if is_final else "Play /coordle in this channel to climb the session board!"
        embed.set_footer(text=f"{len(entries)} Contenders • {footer_msg}")
        return embed

    async def process_game_end(self, game: "CoordleGame", channel: Optional[discord.abc.Messageable] = None, cog: Optional["Coordle"] = None):
        self.record_game_results(game)
        # Check if target round count reached
        if self.target_rounds and self.rounds_played >= self.target_rounds:
            self.is_active = False
            if cog and self.channel_id in cog.active_sessions:
                cog.active_sessions.pop(self.channel_id, None)
            if channel and hasattr(channel, "send"):
                try:
                    embed = self.build_summary_embed(is_final=True)
                    await channel.send(
                        content=f"🏁 **The competitive session `{self.name}` has reached its target of {self.target_rounds} rounds!**",
                        embed=embed
                    )
                except Exception as e:
                    print(f"Error broadcasting session finale: {e}")


__all__ = [
    "ROOT_DIR",
    "ASSETS_DIR",
    "DATA_DIR",
    "WORD_CACHE",
    "DEFINITION_CACHE",
    "load_words",
    "get_daily_word",
    "fetch_word_definition",
    "find_typo_suggestions",
    "get_candidate_lemmas",
    "evaluate_guess",
    "build_rules_embed",
    "CoordleGame",
    "CoordleSession",
]
