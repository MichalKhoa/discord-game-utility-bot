import os
import aiosqlite
import asyncio
from typing import Optional, List, Dict, Any


DEFAULT_QUESTIONS = [
    ("Always have 100% battery on every device", "Never have to sleep again"),
    ("Be able to teleport anywhere instantly", "Be able to fly at 200 mph"),
    ("Win every game you play", "Never get lag or ping spikes again"),
    ("Have infinite in-game gold in every game", "Always unlock the rarest cosmetic skins instantly"),
    ("Have the ability to speak every human language", "Be able to communicate with all animals"),
    ("Never have to wait in any line or traffic again", "Never have to clean or do chores again"),
    ("Be able to freeze time for 10 seconds anytime", "Be able to rewind time by 10 seconds anytime"),
    ("Live in a futuristic cyber city", "Live in a medieval fantasy kingdom with magic"),
    ("Always know when someone is lying", "Always get away with any lie"),
    ("Have unlimited high-speed fiber internet everywhere", "Free top-tier gourmet food for life"),
    ("Lead a top #1 global gaming alliance", "Be the undisputed best solo player in the world"),
    ("Instantly master every musical instrument", "Instantly master every programming language"),
]


class WyrQuestion(dict):
    """Backwards-compatible dictionary for WYR questions supporting both index and key access."""
    def __getitem__(self, item):
        if isinstance(item, int):
            return [self.get("option_a", ""), self.get("option_b", "")][item]
        return super().__getitem__(item)


class Question_Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.db_path = os.path.join(db_dir, 'data', 'wyr_question_bank.db')
        else:
            self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    async def init_db(self, seed_defaults: bool = False):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS wyr_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    option_a TEXT NOT NULL,
                    option_b TEXT NOT NULL,
                    rating TEXT DEFAULT 'SFW',
                    votes_a INTEGER DEFAULT 0,
                    votes_b INTEGER DEFAULT 0
                )''')

            # Migration: ensure votes_a and votes_b exist
            cursor = await db.execute("PRAGMA table_info(wyr_questions)")
            cols = [row[1] for row in await cursor.fetchall()]
            if 'votes_a' not in cols:
                await db.execute("ALTER TABLE wyr_questions ADD COLUMN votes_a INTEGER DEFAULT 0")
            if 'votes_b' not in cols:
                await db.execute("ALTER TABLE wyr_questions ADD COLUMN votes_b INTEGER DEFAULT 0")

            await db.execute('''
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tag_name TEXT NOT NULL UNIQUE
                )''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS question_tags (
                    question_id INTEGER NOT NULL,
                    tag_id INTEGER NOT NULL,
                    PRIMARY KEY (question_id, tag_id),
                    FOREIGN KEY (question_id) REFERENCES wyr_questions (id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE
                )''')

            if seed_defaults:
                cursor = await db.execute("SELECT COUNT(*) FROM wyr_questions")
                count = (await cursor.fetchone())[0]
                if count == 0:
                    for opt_a, opt_b in DEFAULT_QUESTIONS:
                        await db.execute(
                            "INSERT INTO wyr_questions (option_a, option_b, rating, votes_a, votes_b) VALUES (?, ?, 'SFW', 0, 0)",
                            (opt_a, opt_b)
                        )

            await db.commit()

    async def add_wyr_question(self, option_a: str, option_b: str, tag_list: list[str], rating: str = 'SFW'):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO wyr_questions (option_a, option_b, rating, votes_a, votes_b) VALUES (?, ?, ?, 0, 0)",
                (option_a, option_b, rating)
            )
            question_id = cursor.lastrowid

            for tag in tag_list:
                await db.execute("INSERT OR IGNORE INTO tags (tag_name) VALUES (?)", (tag,))
                cursor_tag = await db.execute("SELECT id FROM tags WHERE tag_name = ?", (tag,))
                tag_row = await cursor_tag.fetchone()
                if tag_row:
                    tag_id = tag_row[0]
                    await db.execute(
                        "INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)",
                        (question_id, tag_id)
                    )

            await db.commit()

    async def get_random_wyr_question(self) -> Optional[WyrQuestion]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, option_a, option_b, votes_a, votes_b FROM wyr_questions WHERE rating = 'SFW' ORDER BY RANDOM() LIMIT 1"
            )
            row = await cursor.fetchone()
            if row:
                return WyrQuestion(
                    id=row[0],
                    option_a=row[1],
                    option_b=row[2],
                    votes_a=row[3] or 0,
                    votes_b=row[4] or 0
                )
            return None

    async def record_wyr_vote(self, question_id: int, choice: str) -> None:
        """Increments vote count for choice 'A' or 'B'."""
        col = "votes_a" if choice.upper() == "A" else "votes_b"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE wyr_questions SET {col} = {col} + 1 WHERE id = ?", (question_id,))
            await db.commit()
