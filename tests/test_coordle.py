import io
import unittest
from unittest.mock import MagicMock, AsyncMock
import discord

from cogs.coordle import CoordleGame, CoordleGameView, evaluate_guess
from utils.coordle_image import render_coordle_board


class TestCoordleGameAndBoard(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_user = MagicMock(spec=discord.Member)
        self.mock_user.id = 12345
        self.mock_user.display_name = "PlayerOne"

        self.mock_user_two = MagicMock(spec=discord.Member)
        self.mock_user_two.id = 67890
        self.mock_user_two.display_name = "PlayerTwo"

    def test_evaluate_guess(self):
        # Target: PLANT, Guess: PRANK
        # P: G, R: B, A: G, N: G, K: B
        res = evaluate_guess("PLANT", "PRANK")
        self.assertEqual(res, ["G", "B", "G", "G", "B"])

        # Target: SPEED, Guess: EERIE
        # E: Y, E: Y, R: B, I: B, E: B
        res2 = evaluate_guess("SPEED", "EERIE")
        self.assertEqual(res2, ["Y", "Y", "B", "B", "B"])

    def test_submit_guess_discoveries_and_points(self):
        game = CoordleGame("PLANT", max_attempts=6)

        # 1st guess: PRANK -> P, A, N are new greens (+30 pts)
        over, msg, pts = game.submit_guess("PRANK", self.mock_user)
        self.assertFalse(over)
        self.assertEqual(pts, 30)
        self.assertIn("🟩P", msg)
        self.assertIn("🟩A", msg)
        self.assertIn("🟩N", msg)

        # Verify stored guess structure
        last_guess = game.guesses[-1]
        self.assertEqual(len(last_guess), 5)
        self.assertEqual(last_guess[0], "PRANK")
        self.assertEqual(last_guess[3], 30)
        self.assertEqual(last_guess[4], ["🟩P", "🟩A", "🟩N"])

        # 2nd guess: PAINT -> P, A, N already green, I is black, T is green (+10 pts)
        over, msg, pts = game.submit_guess("PAINT", self.mock_user_two)
        self.assertFalse(over)
        self.assertEqual(pts, 10)
        self.assertIn("🟩T", msg)
        self.assertEqual(game.guesses[-1][4], ["🟩T"])

        # 3rd guess: POINT -> P, N, T already green, O, I black (0 pts)
        over, msg, pts = game.submit_guess("POINT", self.mock_user)
        self.assertFalse(over)
        self.assertEqual(pts, 0)
        self.assertEqual(game.guesses[-1][4], [])

    def test_render_coordle_board_image(self):
        # Test image generation for empty game and with guesses
        buf_empty = render_coordle_board([], {}, word_length=5, max_attempts=6)
        self.assertIsInstance(buf_empty, io.BytesIO)
        self.assertGreater(len(buf_empty.getvalue()), 1000)

        guesses = [
            ("PLAYER", ["B", "B", "B", "Y", "Y", "Y"], "PlayerOne", 3, ["🟨Y", "🟨E", "🟨R"]),
            ("WYVERN", ["G", "G", "G", "G", "G", "G"], "PlayerOne", 15, ["🟩W", "🟩Y", "🟩V", "🟩E", "🟩R", "🟩N", "🎯 Solved!"]),
        ]
        status = {"W": "G", "Y": "G", "V": "G", "E": "G", "R": "G", "N": "G", "P": "B", "L": "B", "A": "B"}
        buf_active = render_coordle_board(guesses, status, word_length=6, max_attempts=6)
        self.assertIsInstance(buf_active, io.BytesIO)
        self.assertGreater(len(buf_active.getvalue()), 1000)

    async def test_get_embed_and_file_image(self):
        game = CoordleGame("PLANT", max_attempts=6)
        view = CoordleGameView(game)

        embed, file = view.get_embed_and_file()
        self.assertIsNotNone(file)
        self.assertEqual(file.filename, "coordle.png")
        self.assertEqual(embed.image.url, "attachment://coordle.png")

    async def test_fallback_text_board_and_tracker(self):
        game = CoordleGame("PLANT", max_attempts=6)
        view = CoordleGameView(game)

        # Before any guesses (fallback text mode)
        embed_init = view.get_embed(has_image=False)
        desc_init = embed_init.description
        self.assertIn("### 🎯 Word Progress", desc_init)
        self.assertIn("⬜ `_`  ⬜ `_`  ⬜ `_`  ⬜ `_`  ⬜ `_`", desc_init)
        self.assertIn("🟨 **Present in Word**: *None yet*", desc_init)
        self.assertIn("🟩 **Correct**: *None*", desc_init)
        self.assertIn("🟨 **Present**: *None*", desc_init)
        self.assertIn("⬛ **Eliminated**: *None*", desc_init)

        # Submit guess with green and yellow
        # Guess: TRAIN -> T (Y), R (B), A (G), I (B), N (Y)
        game.submit_guess("TRAIN", self.mock_user)
        embed_after = view.get_embed(has_image=False)
        desc_after = embed_after.description

        # Word progress should show A green at index 2
        self.assertIn("⬜ `_`  ⬜ `_`  🟩 `A`  ⬜ `_`  ⬜ `_`", desc_after)
        # Present letters should show N, T
        self.assertIn("`N`", desc_after)
        self.assertIn("`T`", desc_after)

        # Guess board row should show discoveries
        self.assertIn("• Found 🟩A, 🟨T, 🟨N", desc_after)

        # Letter tracker should show categories
        self.assertIn("🟩 **Correct**: `A`", desc_after)
        self.assertIn("🟨 **Present**: `N`, `T`", desc_after)
        self.assertIn("⬛ **Eliminated**: ~~I~~ ~~R~~", desc_after)

    async def test_win_embed_word_progress(self):
        game = CoordleGame("PLANT", max_attempts=6)
        view = CoordleGameView(game)

        game.submit_guess("PLANT", self.mock_user)
        self.assertTrue(game.won)
        self.assertTrue(game.game_over)
        self.assertIn("🎯 Solved!", game.guesses[-1][4])

        embed, file = view.get_embed_and_file()
        self.assertIsNotNone(file)
        self.assertIn("Good job! Everyone who participated gets **+10** points!", embed.description)
        self.assertIn("solved the mystery word", embed.description)

        # Share text generation
        share_text = game.generate_share_text()
        self.assertIn("🟩🟩🟩🟩🟩", share_text)

    async def test_loss_embed_word_progress(self):
        game = CoordleGame("PLANT", max_attempts=2)
        view = CoordleGameView(game)

        game.submit_guess("CRANE", self.mock_user)
        game.submit_guess("GHOST", self.mock_user)
        self.assertFalse(game.won)
        self.assertTrue(game.game_over)

        embed = view.get_embed(has_image=False)
        self.assertIn("💀 **Solution**: **`PLANT`**", embed.description)

    async def test_setup_view_attempts_options(self):
        from utils.views import CoordleSetupView
        mock_bot = MagicMock()
        setup_view = CoordleSetupView(mock_bot)
        # Verify select_attempts exists with 10 options spanning 3 to 15 attempts
        attempts_select = setup_view.select_attempts
        self.assertEqual(len(attempts_select.options), 10)
        values = [int(opt.value) for opt in attempts_select.options]
        self.assertEqual(values, [3, 4, 5, 6, 7, 8, 9, 10, 12, 15])

        # Test selecting 3 attempts
        mock_interaction = MagicMock()
        mock_interaction.response = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()
        attempts_select._values = ["3"]
        await setup_view.select_attempts.callback(mock_interaction)
        self.assertEqual(setup_view.selected_attempts, 3)

    async def test_leaderboard_database_sorting_and_pagination(self):
        import tempfile
        import os
        from databases.coordle_database import CoordleDatabase

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_coordle.db")
            db = CoordleDatabase(db_path)
            await db.init_db()

            guild_id = 99999
            # Add 3 players with distinct metrics
            # Player 1: high points (300), 1 solve, 1 win
            await db.add_points_and_stats(101, guild_id, "Alice", points=300, game_played=True, game_won=True, word_solved=True)
            # Player 2: moderate points (150), 5 solves, 1 win, streak 4
            await db.add_points_and_stats(102, guild_id, "Bob", points=150, game_played=True, game_won=True, word_solved=True)
            for _ in range(4):
                await db.add_points_and_stats(102, guild_id, "Bob", word_solved=True)
            await db.update_daily_streak(102, guild_id, "2026-09-24")
            await db.update_daily_streak(102, guild_id, "2026-09-25")
            await db.update_daily_streak(102, guild_id, "2026-09-26")
            await db.update_daily_streak(102, guild_id, "2026-09-27")
            # Player 3: low points (50), 1 solve, 5 wins
            await db.add_points_and_stats(103, guild_id, "Charlie", points=50, game_played=True, game_won=True, word_solved=True)
            for _ in range(4):
                await db.add_points_and_stats(103, guild_id, "Charlie", game_played=True, game_won=True)

            # Test total players
            total = await db.get_total_players(guild_id)
            self.assertEqual(total, 3)

            # Test sorted by points: Alice (300) > Bob (150) > Charlie (50)
            lb_points = await db.get_leaderboard(guild_id, sort_by="points")
            self.assertEqual([p["user_name"] for p in lb_points], ["Alice", "Bob", "Charlie"])

            # Test sorted by solves: Bob (5) > Alice (1) > Charlie (1)
            lb_solves = await db.get_leaderboard(guild_id, sort_by="solves")
            self.assertEqual(lb_solves[0]["user_name"], "Bob")

            # Test sorted by wins: Charlie (5) > Bob (1) > Alice (1)
            lb_wins = await db.get_leaderboard(guild_id, sort_by="wins")
            self.assertEqual(lb_wins[0]["user_name"], "Charlie")

            # Test sorted by streak: Bob (4) > others
            lb_streak = await db.get_leaderboard(guild_id, sort_by="streak")
            self.assertEqual(lb_streak[0]["user_name"], "Bob")
            self.assertEqual(lb_streak[0]["current_streak"], 4)

            # Test ranks across categories
            rank_bob_pts, _ = await db.get_user_rank(102, guild_id, sort_by="points")
            self.assertEqual(rank_bob_pts, 2)
            rank_bob_solves, _ = await db.get_user_rank(102, guild_id, sort_by="solves")
            self.assertEqual(rank_bob_solves, 1)

    async def test_leaderboard_view_rendering_and_interaction(self):
        import tempfile
        import os
        from databases.coordle_database import CoordleDatabase
        from cogs.coordle import CoordleLeaderboardView

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_coordle_view.db")
            db = CoordleDatabase(db_path)
            await db.init_db()

            guild_id = 12345
            for i in range(1, 6):
                await db.add_points_and_stats(i, guild_id, f"Player{i}", points=i * 100, game_played=True, game_won=True, word_solved=True)

            view = CoordleLeaderboardView(db=db, guild_id=guild_id, current_user_id=5)
            embed = await view.build_embed()

            # Verify podium medals
            self.assertIn("🥇 **1st Place**: **Player5**", embed.description)
            self.assertIn("🥈 **2nd Place**: **Player4**", embed.description)
            self.assertIn("🥉 **3rd Place**: **Player3**", embed.description)
            self.assertIn("4️⃣ **Player2**", embed.description)

            # Verify personal standing card
            self.assertTrue(any("Your Server Standing" in f.name for f in embed.fields))
            user_field = [f for f in embed.fields if "Your Server Standing" in f.name][0]
            self.assertIn("Rank**: `#1` of `5`", user_field.value)

            # Test category switch
            mock_select_interaction = MagicMock()
            mock_select_interaction.response = MagicMock()
            mock_select_interaction.response.edit_message = AsyncMock()
            view.category_select._values = ["solves"]
            await view.category_select.callback(mock_select_interaction)
            self.assertEqual(view.category, "solves")
            self.assertEqual(view.page, 0)


if __name__ == "__main__":
    unittest.main()
