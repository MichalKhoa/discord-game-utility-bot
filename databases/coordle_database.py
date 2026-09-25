import os
import aiosqlite
from typing import Optional, List, Dict, Any, Tuple


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
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
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
            cursor = await db.execute("""
                SELECT * FROM coordle_stats
                WHERE user_id = ? AND guild_id = ?
            """, (user_id, guild_id))
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)

    async def get_user_rank(self, user_id: int, guild_id: int) -> Tuple[Optional[int], int]:
        """Returns (rank_1_indexed, total_players) in the guild."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                SELECT user_id, points FROM coordle_stats
                WHERE guild_id = ?
                ORDER BY points DESC, words_solved DESC
            """, (guild_id,))
            rows = await cursor.fetchall()
            total = len(rows)
            for idx, r in enumerate(rows, 1):
                if r[0] == user_id:
                    return idx, total
            return None, total

    async def get_leaderboard(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM coordle_stats
                WHERE guild_id = ?
                ORDER BY points DESC, words_solved DESC, games_won DESC
                LIMIT ?
            """, (guild_id, limit))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
