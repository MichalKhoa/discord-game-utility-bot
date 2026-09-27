import unittest
import tempfile
import os
import aiosqlite
from unittest.mock import MagicMock, AsyncMock, patch
import discord

from cogs.rally_countdown import RallyCountdown
from cogs.roast import Roast, ShuffleBag
from cogs.battle_tactics import BattleTactics
from utils.countdown import generate_audio_files
from databases.coordle_database import CoordleDatabase
from databases.wyr_database import QuestionDatabase, Question_Database


class TestRallyCountdownCogs(unittest.IsolatedAsyncioTestCase):
    async def test_prefix_countdown_bounds(self):
        bot = MagicMock()
        cog = RallyCountdown(bot)
        
        # Test out-of-bounds rejected
        for invalid_count in [-5, 0, 61, 999]:
            ctx = MagicMock()
            ctx.send = AsyncMock()
            await cog.prefix_countdown.callback(cog, ctx, count=invalid_count)
            ctx.send.assert_called_once()
            self.assertIn("between 1 and 60 seconds", ctx.send.call_args[0][0])

    async def test_slash_countdown_clamping(self):
        bot = MagicMock()
        cog = RallyCountdown(bot)
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()

        with patch("cogs.rally_countdown.play_voice_countdown", new=AsyncMock()) as mock_play:
            await cog.slash_countdown.callback(cog, interaction, 10)
            interaction.response.send_message.assert_called_once_with("🎙️ Starting 10s voice countdown...")
            mock_play.assert_called_once_with(interaction, 10)

    def test_generate_audio_files_clamping(self):
        with patch("utils.countdown.gtts.gTTS") as mock_gtts, \
             patch("utils.countdown.subprocess.run"):
            mock_tts_instance = MagicMock()
            mock_gtts.return_value = mock_tts_instance
            # Calling with 100 should clamp to 60 (at most 61 files: 0..60)
            generate_audio_files(100)
            self.assertLessEqual(mock_gtts.call_count, 61)


class TestRoastCog(unittest.IsolatedAsyncioTestCase):
    def test_shuffle_bag_reset(self):
        items = ["A", "B", "C"]
        bag = ShuffleBag(items)
        drawn = [bag.get() for _ in range(3)]
        self.assertEqual(sorted(drawn), ["A", "B", "C"])
        # Next draw should reset and continue without raising IndexError
        next_item = bag.get()
        self.assertIn(next_item, items)

    async def test_roast_duel_same_player(self):
        bot = MagicMock()
        cog = Roast(bot)
        member = MagicMock()

        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()
        await cog.roast_duel_slash.callback(cog, interaction, member, member)
        interaction.response.send_message.assert_called_once()
        self.assertIn("can't start a duel with yourself", interaction.response.send_message.call_args[0][0])

    async def test_roast_duel_forbidden_reactions_handled(self):
        bot = MagicMock()
        cog = Roast(bot)
        p1 = MagicMock()
        p2 = MagicMock()

        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()
        mock_msg = MagicMock()
        mock_msg.add_reaction = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "Missing Permissions"))
        interaction.original_response = AsyncMock(return_value=mock_msg)

        # Should complete gracefully without raising Forbidden
        await cog.roast_duel_slash.callback(cog, interaction, p1, p2)
        interaction.response.send_message.assert_called_once()
        mock_msg.add_reaction.assert_called_once()


class TestBattleTacticsCog(unittest.IsolatedAsyncioTestCase):
    async def test_validation_rejects_non_positive_times(self):
        bot = MagicMock()
        cog = BattleTactics(bot)

        # Slash command validation
        interaction = MagicMock()
        interaction.response.send_message = AsyncMock()
        await cog.reinforcement_timing_slash.callback(cog, interaction, 0, 5, 90)
        interaction.response.send_message.assert_called_once()
        self.assertIn("positive integers", interaction.response.send_message.call_args[0][0])

        # Prefix command validation
        ctx = MagicMock()
        ctx.send = AsyncMock()
        await cog.reinforce_prefix.callback(cog, ctx, -10, 5, 90)
        ctx.send.assert_called_once()
        self.assertIn("positive integers", ctx.send.call_args[0][0])


class TestDatabaseLifecycles(unittest.IsolatedAsyncioTestCase):
    async def test_coordle_database_init_idempotence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "coordle_test.db")
            db = CoordleDatabase(db_path)
            # Run init_db multiple times to ensure migration idempotence
            await db.init_db()
            await db.init_db()

            async with aiosqlite.connect(db_path) as conn:
                cursor = await conn.execute("PRAGMA table_info(coordle_stats)")
                cols = [row[1] for row in await cursor.fetchall()]
                self.assertIn("current_streak", cols)
                self.assertIn("max_streak", cols)
                self.assertIn("last_daily_date", cols)

    def test_wyr_database_pep8_alias(self):
        self.assertIs(QuestionDatabase, Question_Database)


if __name__ == "__main__":
    unittest.main()
