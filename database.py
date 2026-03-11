import aiosqlite
import asyncio

class Question_Database:
    async def init_db(self):
        async with aiosqlite.connect('question_bank.db') as db:
            await db.execute('''
                             CREATE TABLE IF NOT EXISTS wyr_questions (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                option_a TEXT NOT NULL,
                                option_b TEXT NOT NULL,
                                rating TEXT DEFAULT 'SFW'
                            )''')

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

            await db.commit()

    async def add_wyr_question(option_a: str, option_b: str, tag_list: list[str], rating: str = 'SFW',):
        async with aiosqlite.connect('question_bank.db') as db:
            question = await db.execute(
                "INSERT INTO wyr_questions (option_a, option_b, rating) "
                "VALUES (?, ?, ?)", (option_a, option_b, rating))

            question_id = question.lastrowid

            for tag in tag_list:
                await db.execute("INSERT OR IGNORE INTO tags (tag_name)VALUES (?)", tag)

                tag_obj = db.execute("SELECT id FROM tags WHERE tag_name = (?)", tag)

                tag_row = await tag_obj.fetchone()
                tag_id = tag_row[0]

                await db.execute("INSERT or IGNORE INTO question_tags (question_id, tag_)"
                                 "VALUES (?, ?)" (question_id, tag_id))

            await db.commit()

    async def get_random_wyr_question(self):
        async with aiosqlite.connect('question_bank.db') as db:
            cursor = await db.execute(
                "SELECT option_a, option_b FROM wyr_questions WHERE rating = 'SFW' ORDER BY RANDOM() LIMIT 1"
            )
            options = await cursor.fetchone()
            # print(f'{options[0]}, {options[1]}')
            option_A = options[0]
            option_B = options[1]
            if option_A and option_B:
                return [option_A, option_B]
            return None

