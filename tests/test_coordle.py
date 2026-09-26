import io
import unittest
from unittest.mock import MagicMock
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


if __name__ == "__main__":
    unittest.main()
