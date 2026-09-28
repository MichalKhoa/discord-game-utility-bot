import io
import unittest
from unittest.mock import MagicMock, AsyncMock
import discord

from cogs.coordle import (
    CoordleGame,
    CoordleGameView,
    CoordleSession,
    CoordleSessionLeaderboardView,
    CoordleSessionStartView,
    evaluate_guess,
)
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

    def test_yellow_to_green_upgrade_points(self):
        # Target: PLANT
        game = CoordleGame("PLANT", max_attempts=6)

        # 1st guess: TRAIN
        # T: Y (+5 pts), R: B, A: G (+10 pts fresh), I: B, N: Y (+5 pts)
        # Total points: 20 pts
        over, msg, pts = game.submit_guess("TRAIN", self.mock_user)
        self.assertFalse(over)
        self.assertEqual(pts, 20)
        self.assertEqual(game.known_yellow_chars, {"T", "N"})
        self.assertEqual(game.known_target_chars, {"T", "A", "N"})
        self.assertEqual(game.known_green_indices, {2})
        self.assertEqual(game.guesses[-1][4], ["🟩A", "🟨T", "🟨N"])

        # 2nd guess: SLANT
        # S: B, L: G (+10 pts fresh), A: G (already green: 0 pts),
        # N: G (+5 pts upgrade from yellow), T: G (+5 pts upgrade from yellow)
        # Total points: 10 + 5 + 5 = 20 pts
        over, msg, pts = game.submit_guess("SLANT", self.mock_user_two)
        self.assertFalse(over)
        self.assertEqual(pts, 20)
        self.assertEqual(game.known_yellow_chars, set())
        self.assertEqual(game.known_green_indices, {1, 2, 3, 4})
        self.assertEqual(game.guesses[-1][4], ["🟩L", "🟩N", "🟩T"])

        # 3rd guess: PLANT (Solve!)
        # P: G (+10 pts fresh)
        # Letters left before solve = 1 -> solve bonus = 1 * 5 = 5 pts
        # Guess points = 10 (P) + 5 (solve bonus) = 15 pts
        over, msg, pts = game.submit_guess("PLANT", self.mock_user)
        self.assertTrue(over)
        self.assertTrue(game.won)
        self.assertEqual(pts, 15)
        # PlayerOne: 20 (guess 1) + 15 (guess 3) + 10 (win bonus) = 45 pts
        self.assertEqual(game.participants[self.mock_user.id]["points"], 45)
        # PlayerTwo: 20 (guess 2) + 10 (win bonus) = 30 pts
        self.assertEqual(game.participants[self.mock_user_two.id]["points"], 30)

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

    def test_word_lists_integrity(self):
        from scripts.check_word_lists import check
        self.assertEqual(check(), 0)


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


class TestCoordleSession(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mock_host = MagicMock(spec=discord.Member)
        self.mock_host.id = 11111
        self.mock_host.display_name = "HostUser"
        self.mock_host.mention = "<@11111>"

        self.mock_user_a = MagicMock(spec=discord.Member)
        self.mock_user_a.id = 22222
        self.mock_user_a.display_name = "Alice"
        self.mock_user_a.mention = "<@22222>"

        self.mock_user_b = MagicMock(spec=discord.Member)
        self.mock_user_b.id = 33333
        self.mock_user_b.display_name = "Bob"
        self.mock_user_b.mention = "<@33333>"

    def test_session_scoring_and_ranking(self):
        session = CoordleSession(channel_id=100, guild_id=200, host=self.mock_host, name="Weekend Cup", target_rounds=3)
        self.assertEqual(session.name, "Weekend Cup")
        self.assertEqual(session.target_rounds, 3)
        self.assertEqual(session.rounds_played, 0)
        self.assertTrue(session.is_active)

        # Mock game 1: Alice gets 40 pts, solves word. Bob gets 15 pts.
        game1 = CoordleGame("APPLE")
        game1.participants = {
            22222: {"name": "Alice", "points": 40, "guesses": 2, "greens": 3, "yellows": 1, "won": True, "solved": True},
            33333: {"name": "Bob", "points": 15, "guesses": 1, "greens": 1, "yellows": 1, "won": True, "solved": False},
        }
        session.record_game_results(game1)
        self.assertEqual(session.rounds_played, 1)

        # Mock game 2: Bob gets 50 pts, solves word. Alice gets 10 pts.
        game2 = CoordleGame("BERRY")
        game2.participants = {
            22222: {"name": "Alice", "points": 10, "guesses": 1, "greens": 1, "yellows": 0, "won": True, "solved": False},
            33333: {"name": "Bob", "points": 50, "guesses": 2, "greens": 4, "yellows": 0, "won": True, "solved": True},
        }
        session.record_game_results(game2)
        self.assertEqual(session.rounds_played, 2)

        # Points: Bob has 65 (15+50), Alice has 50 (40+10) -> Bob 1st
        lb_points = session.get_leaderboard(sort_by="points")
        self.assertEqual([e["user_name"] for e in lb_points], ["Bob", "Alice"])

        # Solves: Bob and Alice both have 1 solve. Bob has more points -> Bob 1st
        lb_solves = session.get_leaderboard(sort_by="solves")
        self.assertEqual(lb_solves[0]["user_name"], "Bob")

        # Wins: Bob and Alice both have 2 wins.
        lb_wins = session.get_leaderboard(sort_by="wins")
        self.assertEqual(lb_wins[0]["user_name"], "Bob")

        # Verify summary embeds
        embed_progress = session.build_summary_embed(is_final=False, sort_by="points")
        self.assertIn("🏆 Competitive Session Leaderboard: Weekend Cup", embed_progress.title)
        self.assertIn("Rounds Played**: `2/3`", embed_progress.description)
        self.assertIn("🥇 **1st Place**: **Bob**", embed_progress.description)
        self.assertIn("🥈 **2nd Place: Alice**", embed_progress.description)

        embed_final = session.build_summary_embed(is_final=True, sort_by="points")
        self.assertIn("🏁 Competitive Session Concluded: Weekend Cup", embed_final.title)
        self.assertIn("🥇 **Session Champion**: **Bob**", embed_final.description)

    async def test_session_target_rounds_auto_end(self):
        session = CoordleSession(channel_id=100, guild_id=200, host=self.mock_host, name="Quick Match", target_rounds=2)
        mock_cog = MagicMock()
        mock_cog.active_sessions = {100: session}
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()

        game = CoordleGame("CRANE")
        game.participants = {22222: {"name": "Alice", "points": 20, "guesses": 1, "greens": 2, "yellows": 0, "won": True, "solved": True}}

        # Round 1 - should not conclude
        await session.process_game_end(game, channel=mock_channel, cog=mock_cog)
        self.assertEqual(session.rounds_played, 1)
        self.assertTrue(session.is_active)
        self.assertIn(100, mock_cog.active_sessions)
        mock_channel.send.assert_not_called()

        # Round 2 - reaches target 2 -> should conclude and broadcast
        await session.process_game_end(game, channel=mock_channel, cog=mock_cog)
        self.assertEqual(session.rounds_played, 2)
        self.assertFalse(session.is_active)
        self.assertNotIn(100, mock_cog.active_sessions)
        mock_channel.send.assert_called_once()
        sent_kwargs = mock_channel.send.call_args[1]
        self.assertIn("reached its target of 2 rounds", sent_kwargs["content"])

    async def test_session_leaderboard_view_interactions(self):
        session = CoordleSession(channel_id=100, guild_id=200, host=self.mock_host, name="Test Cup")
        session.scores = {
            22222: {"user_id": 22222, "user_name": "Alice", "points": 30, "words_solved": 1, "games_won": 1, "total_guesses": 2, "greens": 2, "yellows": 1}
        }
        mock_cog = MagicMock()
        mock_cog.active_sessions = {100: session}
        view = CoordleSessionLeaderboardView(session, mock_cog)

        # Test switching categories: Solves, Wins, Points, Refresh
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()

        await view.btn_solves.callback(mock_interaction)
        self.assertEqual(view.sort_by, "solves")
        mock_interaction.response.edit_message.assert_called()

        await view.btn_wins.callback(mock_interaction)
        self.assertEqual(view.sort_by, "wins")

        await view.btn_points.callback(mock_interaction)
        self.assertEqual(view.sort_by, "points")

        await view.btn_refresh.callback(mock_interaction)

        # Test end button by unauthorized user
        mock_unauth = MagicMock(spec=discord.Interaction)
        mock_unauth.user = self.mock_user_a
        mock_unauth.guild = MagicMock()
        mock_unauth.user.guild_permissions.manage_guild = False
        mock_unauth.response = MagicMock()
        mock_unauth.response.send_message = AsyncMock()

        await view.btn_end.callback(mock_unauth)
        self.assertTrue(session.is_active)
        mock_unauth.response.send_message.assert_called_with("❌ Only the session host or server admins can end this session.", ephemeral=True)

        # Test end button by host
        mock_host_interaction = MagicMock(spec=discord.Interaction)
        mock_host_interaction.user = self.mock_host
        mock_host_interaction.guild = MagicMock()
        mock_host_interaction.response = MagicMock()
        mock_host_interaction.response.edit_message = AsyncMock()

        await view.btn_end.callback(mock_host_interaction)
        self.assertFalse(session.is_active)
        self.assertNotIn(100, mock_cog.active_sessions)
        mock_host_interaction.response.edit_message.assert_called()

    async def test_session_start_view_interactions(self):
        session = CoordleSession(channel_id=100, guild_id=200, host=self.mock_host, name="Test Cup")
        mock_cog = MagicMock()
        mock_cog.active_sessions = {100: session}
        mock_cog.start_game = AsyncMock()
        view = CoordleSessionStartView(session, mock_cog)

        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.user = self.mock_host
        mock_interaction.response = MagicMock()
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.response.edit_message = AsyncMock()

        # Play Round button
        await view.btn_play.callback(mock_interaction)
        mock_cog.start_game.assert_called_once_with(mock_interaction, length=5, max_attempts=6, mode="normal")

        # Session Leaderboard button
        await view.btn_board.callback(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()
        self.assertTrue(mock_interaction.response.send_message.call_args[1]["ephemeral"])

        # End Session button
        await view.btn_end.callback(mock_interaction)
        self.assertFalse(session.is_active)
        self.assertNotIn(100, mock_cog.active_sessions)


if __name__ == "__main__":
    unittest.main()
