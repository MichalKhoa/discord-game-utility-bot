import os
import aiosqlite
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta


class CoordleDatabase:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(db_dir, "data", "coordle.db")
        else:
            self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS coordle_stats (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    user_name TEXT NOT NULL,
                    points INTEGER DEFAULT 0,
                    games_played INTEGER DEFAULT 0,
                    games_won INTEGER DEFAULT 0,
                    words_solved INTEGER DEFAULT 0,
                    total_guesses INTEGER DEFAULT 0,
                    green_discovered INTEGER DEFAULT 0,
                    yellow_discovered INTEGER DEFAULT 0,
                    current_streak INTEGER DEFAULT 0,
                    max_streak INTEGER DEFAULT 0,
                    last_daily_date TEXT DEFAULT '',
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS coordle_guild_channels (
                    guild_id INTEGER PRIMARY KEY,
                    daily_channel_id INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS coordle_definitions (
                    word TEXT PRIMARY KEY,
                    definition TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Soft column migrations in case table was created earlier
            for col_def in [
                "current_streak INTEGER DEFAULT 0",
                "max_streak INTEGER DEFAULT 0",
                "last_daily_date TEXT DEFAULT ''"
            ]:
                try:
                    await db.execute(f"ALTER TABLE coordle_stats ADD COLUMN {col_def}")
                except Exception:
                    pass

            await db.commit()

    async def get_definition(self, word: str) -> Optional[str]:
        """Retrieves a cached dictionary definition from SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT definition FROM coordle_definitions WHERE word = ?",
                (word.lower().strip(),)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def save_definition(self, word: str, definition: str):
        """Persists a dictionary definition into SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO coordle_definitions (word, definition)
                VALUES (?, ?)
                ON CONFLICT(word) DO UPDATE SET definition = excluded.definition
            """, (word.lower().strip(), definition.strip()))
            await db.commit()

    async def set_daily_channel(self, guild_id: int, channel_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO coordle_guild_channels (guild_id, daily_channel_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET daily_channel_id = excluded.daily_channel_id
            """, (guild_id, channel_id))
            await db.commit()

    async def remove_daily_channel(self, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM coordle_guild_channels WHERE guild_id = ?", (guild_id,))
            await db.commit()

    async def get_daily_channel(self, guild_id: int) -> Optional[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT daily_channel_id FROM coordle_guild_channels WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def get_all_daily_channels(self) -> List[Tuple[int, int]]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT guild_id, daily_channel_id FROM coordle_guild_channels") as cursor:
                rows = await cursor.fetchall()
                return [(r[0], r[1]) for r in rows]

    async def update_daily_streak(self, user_id: int, guild_id: int, today_str: str):
        """Updates win streak for the daily puzzle."""
        today = datetime.strptime(today_str, "%Y-%m-%d").date()
        yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT current_streak, max_streak, last_daily_date FROM coordle_stats WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                return

            cur_streak, max_streak, last_date = row[0] or 0, row[1] or 0, row[2] or ""

            if last_date == today_str:
                return  # Already counted today

            if last_date == yesterday_str:
                new_streak = cur_streak + 1
            else:
                new_streak = 1

            new_max = max(max_streak, new_streak)

            await db.execute("""
                UPDATE coordle_stats
                SET current_streak = ?, max_streak = ?, last_daily_date = ?
                WHERE user_id = ? AND guild_id = ?
            """, (new_streak, new_max, today_str, user_id, guild_id))
            await db.commit()

    async def add_points_and_stats(
        self,
        user_id: int,
        guild_id: int,
        user_name: str,
        points: int = 0,
        game_played: bool = False,
        game_won: bool = False,
        word_solved: bool = False,
        guesses: int = 0,
        greens: int = 0,
        yellows: int = 0
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO coordle_stats (
                    user_id, guild_id, user_name, points,
                    games_played, games_won, words_solved,
                    total_guesses, green_discovered, yellow_discovered
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    user_name = excluded.user_name,
                    points = coordle_stats.points + excluded.points,
                    games_played = coordle_stats.games_played + excluded.games_played,
                    games_won = coordle_stats.games_won + excluded.games_won,
                    words_solved = coordle_stats.words_solved + excluded.words_solved,
                    total_guesses = coordle_stats.total_guesses + excluded.total_guesses,
                    green_discovered = coordle_stats.green_discovered + excluded.green_discovered,
                    yellow_discovered = coordle_stats.yellow_discovered + excluded.yellow_discovered
            """, (
                user_id, guild_id, user_name, points,
                1 if game_played else 0,
                1 if game_won else 0,
                1 if word_solved else 0,
                guesses, greens, yellows
            ))
            await db.commit()

    async def get_user_stats(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM coordle_stats WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_user_rank(self, user_id: int, guild_id: int) -> Tuple[Optional[int], int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM coordle_stats WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                total_row = await cursor.fetchone()
                total = total_row[0] if total_row else 0

            if total == 0:
                return None, 0

            async with db.execute("""
                SELECT COUNT(*) + 1 FROM coordle_stats
                WHERE guild_id = ? AND points > (
                    SELECT COALESCE(points, 0) FROM coordle_stats WHERE user_id = ? AND guild_id = ?
                )
            """, (guild_id, user_id, guild_id)) as cursor:
                rank_row = await cursor.fetchone()
                rank = rank_row[0] if rank_row else None

            return rank, total

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT user_id, user_name, points, games_played, games_won, words_solved, total_guesses, current_streak
                FROM coordle_stats
                WHERE guild_id = ?
                ORDER BY points DESC, words_solved DESC, games_won DESC
                LIMIT ?
            """, (guild_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
