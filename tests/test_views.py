import os
import tempfile
import threading
import sqlite3
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import discord

from utils.castle_battle_support import (
    format_time,
    calculate_reinforcement_window,
    create_reinforcement_embed,
    time_to_reinforce,
)
from utils.views import (
    MenuButtons,
    GameMenuButtons,
    PlayerMenuButtons,
    UtilityMenuButtons,
)
from databases.player_database import PlayerDatabase
from cogs.russian_roulette import RussianRouletteGame, RussianRouletteView, RouletteChallengeView, ASSETS_DIR, RussianRoulette
from cogs.code_redeem import CodeRedeem, ConfirmAbortModal
from cogs.player_manager import FlaggedPlayersView, PlayerListView
from utils.redeem_code import redeem_for_all


class TestBattleSupport(unittest.TestCase):
    def test_format_time(self):
        self.assertEqual(format_time(0), "00:00")
        self.assertEqual(format_time(59), "00:59")
        self.assertEqual(format_time(60), "01:00")
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(120), "02:00")
        self.assertEqual(format_time(3599), "59:59")

    def test_calculate_reinforcement_window_longer_march(self):
        # User march = 120s, enemy = 100s, gap = 10s -> march_diff = 20s
        res = calculate_reinforcement_window(opponent_march_time=100, gap_between_rallies=10, user_march_time=120)
        self.assertEqual(res["march_diff"], 20)
        self.assertIn("00:20", res["action"])
        self.assertIn("00:10", res["action"])
        self.assertIn("00:10", res["timing_detail"])

    def test_calculate_reinforcement_window_equal_march(self):
        # User march = 100s, enemy = 100s, gap = 10s -> march_diff = 0s
        res = calculate_reinforcement_window(opponent_march_time=100, gap_between_rallies=10, user_march_time=100)
        self.assertEqual(res["march_diff"], 0)
        self.assertIn("00:00", res["action"])

    def test_calculate_reinforcement_window_shorter_march(self):
        # User march = 80s, enemy = 100s, gap = 10s -> march_diff = -20s
        res = calculate_reinforcement_window(opponent_march_time=100, gap_between_rallies=10, user_march_time=80)
        self.assertEqual(res["march_diff"], -20)
        self.assertIn("00:20", res["timing_detail"])

    def test_create_reinforcement_embed(self):
        embed = create_reinforcement_embed(opponent_march_time=100, gap_between_rallies=10, user_march_time=120)
        self.assertIsInstance(embed, discord.Embed)
        self.assertEqual(embed.title, "🏰 Castle Defense: Reinforcement Timing")
        self.assertEqual(len(embed.fields), 3)

    def test_time_to_reinforce_legacy(self):
        res = time_to_reinforce(100, 10, 120)
        self.assertIsInstance(res, str)
        self.assertIn("Send garrison", res)


class TestMenuViews(unittest.IsolatedAsyncioTestCase):
    async def test_menu_views_instantiation(self):
        mock_bot = MagicMock()
        v_main = MenuButtons(mock_bot)
        self.assertEqual(len(v_main.children), 3)

        v_game = GameMenuButtons(mock_bot)
        self.assertEqual(len(v_game.children), 4)

        v_player = PlayerMenuButtons(mock_bot)
        self.assertGreaterEqual(len(v_player.children), 5)

        v_util = UtilityMenuButtons(mock_bot)
        self.assertGreaterEqual(len(v_util.children), 4)

    async def test_russian_roulette_gameplay(self):
        game = RussianRouletteGame(chamber_size=6)
        mock_user = MagicMock()
        mock_user.id = 12345
        mock_user.mention = "@Player1"
        mock_user.display_name = "Player1"
        game.players.append(mock_user)

        # Pull trigger until live round
        hits = 0
        for _ in range(6):
            is_hit, msg = game.pull_trigger(mock_user)
            if is_hit:
                hits += 1
                break
        self.assertEqual(hits, 1)
        self.assertTrue(game.game_over)

        # Reset
        game.reset()
        self.assertFalse(game.game_over)
        self.assertEqual(game.current_chamber, 1)

        # Test spin_and_pull
        is_hit, msg = game.spin_and_pull(mock_user)
        self.assertIn(mock_user.mention, msg)

        # Test RussianRouletteView
        mock_bot = MagicMock()
        view = RussianRouletteView(mock_bot, host=mock_user, chamber_size=6)
        embed, gif_file = view.get_embed()
        self.assertIn("Russian Roulette", embed.title)
        self.assertIsNone(gif_file)

        suspense_embed, suspense_file = view.get_suspense_embed(mock_user, action_type="spin")
        self.assertIn("Spinning Cylinder", suspense_embed.title)
        if suspense_file and hasattr(suspense_file, "fp") and suspense_file.fp:
            suspense_file.fp.close()

    async def test_russian_roulette_lms_mode(self):
        # Check procedural GIF assets exist and are non-empty
        for fname in ["spin.gif", "boom.gif", "safe.gif"]:
            fpath = os.path.join(ASSETS_DIR, fname)
            self.assertTrue(os.path.exists(fpath), f"Missing asset {fname}")
            self.assertGreater(os.path.getsize(fpath), 1000, f"Asset {fname} too small")

        # Setup 3 mock players
        p1, p2, p3 = MagicMock(), MagicMock(), MagicMock()
        for i, p in enumerate([p1, p2, p3], 1):
            p.id = 1000 + i
            p.mention = f"@Player{i}"
            p.display_name = f"Player{i}"

        # Initialize game in LMS mode
        game = RussianRouletteGame(chamber_size=6, mode="lms")
        self.assertEqual(game.mode, "lms")

        # < 2 players cannot start LMS
        game.players.append(p1)
        self.assertFalse(game.start_lms_game())

        # Add remaining players and start
        game.players.extend([p2, p3])
        self.assertTrue(game.start_lms_game())
        self.assertEqual(len(game.alive_players), 3)
        self.assertEqual(game.round_number, 1)

        # Eliminate first player in Round 1
        curr_player = game.alive_players[0]
        # Force hit on current chamber
        game.bullet_chamber = game.current_chamber
        is_hit, msg = game.pull_trigger(curr_player)
        self.assertTrue(is_hit)
        self.assertFalse(game.game_over)
        self.assertEqual(len(game.alive_players), 2)
        self.assertEqual(len(game.eliminated_players), 1)
        self.assertIn(curr_player, game.eliminated_players)

        # Start Round 2 automatically
        game.start_next_round()
        self.assertEqual(game.round_number, 2)
        self.assertEqual(game.current_chamber, 1)
        self.assertIsNone(game.victim)

        # Eliminate second player in Round 2
        second_player = game.alive_players[0]
        game.bullet_chamber = game.current_chamber
        is_hit, msg = game.pull_trigger(second_player)
        self.assertTrue(is_hit)
        self.assertTrue(game.game_over)
        self.assertEqual(len(game.alive_players), 1)
        self.assertEqual(game.winner, game.alive_players[0])
        self.assertIn("LAST MAN STANDING", msg)

        # Test LMS View and button states
        mock_bot = MagicMock()
        view = RussianRouletteView(mock_bot, host=p1, chamber_size=6, mode="lms")
        self.assertTrue(view.trigger_btn.disabled)  # disabled in LMS
        self.assertTrue(view.start_lms_btn.disabled)  # only 1 player initially

        # Join second player
        view.game.players.append(p2)
        view.game.alive_players.append(p2)
        view.update_buttons()
        self.assertFalse(view.start_lms_btn.disabled)  # enabled with 2+ players

        # Embed reflects LMS status
        embed, gif_file = view.get_embed()
        self.assertIn("Last Man Standing", embed.title)
        self.assertIn("Survivors", [f.name for f in embed.fields if "Survivors" in f.name][0])
        if gif_file and hasattr(gif_file, "fp") and gif_file.fp:
            gif_file.fp.close()

    async def test_russian_roulette_execute_turn_animation(self):
        mock_bot = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 55555
        mock_user.mention = "@SoloPlayer"
        mock_user.display_name = "SoloPlayer"

        view = RussianRouletteView(mock_bot, host=mock_user, chamber_size=6, mode="standard")

        interaction = MagicMock()
        interaction.user = mock_user
        interaction.response = MagicMock()
        interaction.response.is_done = MagicMock(return_value=False)
        interaction.response.edit_message = AsyncMock()
        interaction.edit_original_response = AsyncMock()
        interaction.message = MagicMock()
        interaction.message.edit = AsyncMock()

        await view._execute_turn_with_animation(interaction, action_type="pull")

        # Verify frame 1 used interaction.response.edit_message
        self.assertTrue(interaction.response.edit_message.called)
        # Verify frame 2 used edit_original_response (fixes webhook message bug)
        self.assertTrue(interaction.edit_original_response.called)

    async def test_russian_roulette_mute_and_listener(self):
        mock_bot = MagicMock()
        cog = RussianRoulette(mock_bot)

        # 1. Test mute_player & is_player_muted
        channel_id = 999
        user_id = 12345
        cog.mute_player(channel_id=channel_id, user_id=user_id, duration_seconds=120.0)

        self.assertTrue(cog.is_player_muted(channel_id, user_id))
        self.assertFalse(cog.is_player_muted(channel_id, 99999))
        self.assertFalse(cog.is_player_muted(888, user_id))

        # 2. Test expiration
        cog.mute_player(channel_id=channel_id, user_id=user_id, duration_seconds=-1.0)
        self.assertFalse(cog.is_player_muted(channel_id, user_id))

        # 3. Test on_message listener deletes muted user message
        cog.mute_player(channel_id=channel_id, user_id=user_id, duration_seconds=120.0)

        msg_muted = MagicMock()
        msg_muted.guild = MagicMock()
        msg_muted.author = MagicMock()
        msg_muted.author.bot = False
        msg_muted.author.id = user_id
        msg_muted.channel = MagicMock()
        msg_muted.channel.id = channel_id
        msg_muted.delete = AsyncMock()

        await cog.on_message(msg_muted)
        msg_muted.delete.assert_awaited_once()

        # 4. Test on_message ignores unmuted user
        msg_other = MagicMock()
        msg_other.guild = MagicMock()
        msg_other.author = MagicMock()
        msg_other.author.bot = False
        msg_other.author.id = 88888
        msg_other.channel = MagicMock()
        msg_other.channel.id = channel_id
        msg_other.delete = AsyncMock()

        await cog.on_message(msg_other)
        msg_other.delete.assert_not_called()

        # 5. Test on_message ignores bot message
        msg_bot = MagicMock()
        msg_bot.guild = MagicMock()
        msg_bot.author = MagicMock()
        msg_bot.author.bot = True
        msg_bot.author.id = user_id
        msg_bot.channel = MagicMock()
        msg_bot.channel.id = channel_id
        msg_bot.delete = AsyncMock()

        await cog.on_message(msg_bot)
        msg_bot.delete.assert_not_called()

        # 6. Test on_message ignores DM
        msg_dm = MagicMock()
        msg_dm.guild = None
        msg_dm.delete = AsyncMock()
        await cog.on_message(msg_dm)
        msg_dm.delete.assert_not_called()

        # 7. Test RussianRouletteView calls mute on elimination
        mock_bot.get_cog.return_value = cog
        mock_user = MagicMock()
        mock_user.id = 77777
        view = RussianRouletteView(mock_bot, host=mock_user, chamber_size=6)
        view._mute_if_eliminated(channel_id=555, user_id=mock_user.id)
        self.assertTrue(cog.is_player_muted(555, mock_user.id))

    async def test_russian_roulette_duels_and_challenges(self):
        mock_bot = MagicMock()
        cog = RussianRoulette(mock_bot)

        challenger = MagicMock(spec=discord.Member)
        challenger.id = 1001
        challenger.display_name = "Challenger"
        challenger.mention = "<@1001>"
        challenger.bot = False
        challenger.status = discord.Status.online

        opponent = MagicMock(spec=discord.Member)
        opponent.id = 1002
        opponent.display_name = "Opponent"
        opponent.mention = "<@1002>"
        opponent.bot = False
        opponent.status = discord.Status.online

        interaction = MagicMock()
        interaction.guild = MagicMock()
        interaction.channel_id = 999
        interaction.user = challenger

        # 1. Validation tests
        # A. Self challenge
        self.assertIn("cannot challenge yourself", cog._validate_duel_target(interaction, challenger))

        # B. Bot challenge
        bot_target = MagicMock(spec=discord.Member)
        bot_target.id = 1003
        bot_target.bot = True
        self.assertIn("cannot challenge a bot", cog._validate_duel_target(interaction, bot_target))

        # C. Offline opponent
        offline_target = MagicMock(spec=discord.Member)
        offline_target.id = 1004
        offline_target.bot = False
        offline_target.status = discord.Status.offline
        self.assertIn("offline or invisible", cog._validate_duel_target(interaction, offline_target))

        # D. Challenger muted
        cog.mute_player(999, challenger.id, 120.0)
        self.assertIn("You are currently muted", cog._validate_duel_target(interaction, opponent))
        cog.muted_users.clear()

        # E. Opponent muted
        cog.mute_player(999, opponent.id, 120.0)
        self.assertIn("is currently muted", cog._validate_duel_target(interaction, opponent))
        cog.muted_users.clear()

        # F. Valid target
        self.assertIsNone(cog._validate_duel_target(interaction, opponent))

        # 2. Challenge view acceptance
        challenge_view = RouletteChallengeView(mock_bot, challenger=challenger, opponent=opponent, chamber_size=6)
        embed = challenge_view.get_challenge_embed()
        self.assertIn("Duel Challenge", embed.title)

        # Other user cannot accept
        other_interaction = MagicMock()
        other_interaction.user.id = 9999
        other_interaction.response = AsyncMock()
        await challenge_view.accept_btn.callback(other_interaction)
        other_interaction.response.send_message.assert_awaited_once()

        # Opponent accepts
        opp_interaction = MagicMock()
        opp_interaction.user.id = opponent.id
        opp_interaction.response = AsyncMock()
        opp_interaction.message = MagicMock()
        await challenge_view.accept_btn.callback(opp_interaction)
        opp_interaction.response.edit_message.assert_awaited_once()

        # 3. Forced Duel: Rule of Force (Challenger must take first 2 pulls)
        forced_game = RussianRouletteGame(chamber_size=6, is_forced_duel=True)
        forced_game.players = [challenger, opponent]
        forced_game.bullet_chamber = 6  # live round in chamber 6

        # Pull 1: Challenger pulls chamber 1 (empty) -> must pull again!
        is_hit, msg = forced_game.pull_trigger(challenger)
        self.assertFalse(is_hit)
        self.assertEqual(forced_game.forced_pulls_taken, 1)
        self.assertEqual(forced_game.turn_index, 0)  # Still challenger's turn!
        self.assertIn("Rule of Force", msg)

        # Pull 2: Challenger pulls chamber 2 (empty) -> passes to opponent!
        is_hit, msg = forced_game.pull_trigger(challenger)
        self.assertFalse(is_hit)
        self.assertEqual(forced_game.forced_pulls_taken, 2)
        self.assertEqual(forced_game.turn_index, 1)  # Passes to opponent!
        self.assertIn("Rule of Force Satisfied", msg)

        # Pull 3: Opponent pulls chamber 3 (empty) -> passes to challenger!
        is_hit, msg = forced_game.pull_trigger(opponent)
        self.assertFalse(is_hit)
        self.assertEqual(forced_game.turn_index, 0)  # Back to challenger!

        # 4. Duel View turn checks and auto pull
        duel_view = RussianRouletteView(mock_bot, host=challenger, chamber_size=6, is_duel=True, opponent=opponent, is_forced_duel=True)
        duel_view.game.bullet_chamber = 1  # Hit on first chamber for auto-pull test
        mock_bot.get_cog.return_value = cog
        duel_view.message = MagicMock()
        duel_view.message.channel.id = 999
        duel_view.message.edit = AsyncMock()

        await duel_view._auto_pull_turn()
        self.assertTrue(duel_view.game.game_over)
        self.assertEqual(duel_view.game.victim.id, challenger.id)
        self.assertTrue(cog.is_player_muted(999, challenger.id))

    async def test_run_redeem_handles_forbidden_channel_send(self):
        mock_bot = MagicMock()
        mock_bot.get_user.return_value = None
        mock_bot.fetch_user = AsyncMock(return_value=None)

        with tempfile.TemporaryDirectory() as tmpdir:
            cog = CodeRedeem(mock_bot)
            cog.db = PlayerDatabase(os.path.join(tmpdir, "test_cog.db"))
            await cog.db.init_db(auto_migrate=False)

            # Mock channel where .send raises Forbidden
            mock_channel = AsyncMock()
            mock_channel.send.side_effect = discord.Forbidden(
                response=MagicMock(status=403, reason="Forbidden"),
                message="Missing Access"
            )

            # Patch redeem_for_all to return a success status string
            with patch("utils.redeem_code.redeem_for_all", return_value="✅ Redeemed for 10 players"):
                # run_redeem should complete gracefully without raising Forbidden
                await cog.run_redeem(mock_channel, ["TESTCODE123"], 99999)

            # Check that code was logged in database despite channel send failure
            logged = await cog.db.is_code_redeemed("TESTCODE123")
            self.assertIsNotNone(logged)

    def test_stop_current_redemption(self):
        mock_bot = MagicMock()
        cog = CodeRedeem(mock_bot)
        
        # When not running, returns False
        self.assertFalse(cog.stop_current_redemption())

        # When event is set up
        cog.current_cancel_event = threading.Event()
        self.assertTrue(cog.stop_current_redemption())
        self.assertTrue(cog.current_cancel_event.is_set())

    def test_redeem_for_all_cancel_event(self):
        cancel_evt = threading.Event()
        cancel_evt.set()  # Cancel immediately

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_cancel.db")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE players (fid TEXT PRIMARY KEY, kid TEXT, name TEXT, status TEXT DEFAULT 'ACTIVE')")
            conn.execute("INSERT INTO players (fid, kid, name) VALUES ('111', '278', 'P1')")
            conn.execute("INSERT INTO players (fid, kid, name) VALUES ('222', '278', 'P2')")
            conn.commit()
            conn.close()

            result = redeem_for_all("CANCELCODE", file_path=db_path, cancel_event=cancel_evt)
            self.assertIn("Process Cancelled by User", result)

    async def test_confirm_abort_modal(self):
        mock_on_confirm = AsyncMock()
        modal = ConfirmAbortModal(on_confirm=mock_on_confirm)

        # Test invalid confirmation input
        mock_interaction_invalid = MagicMock()
        mock_interaction_invalid.response = AsyncMock()
        modal.confirmation._value = "no"
        modal.reason._value = "testing"
        await modal.on_submit(mock_interaction_invalid)
        mock_interaction_invalid.response.send_message.assert_called_once()
        self.assertIn("Abort cancelled", mock_interaction_invalid.response.send_message.call_args[0][0])
        mock_on_confirm.assert_not_called()

        # Test valid confirmation input
        mock_interaction_valid = MagicMock()
        mock_interaction_valid.response = AsyncMock()
        modal.confirmation._value = "ABORT"
        modal.reason._value = "wrong code"
        await modal.on_submit(mock_interaction_valid)
        mock_on_confirm.assert_called_once_with(mock_interaction_valid, reason="wrong code")

    async def test_flagged_players_view(self):
        mock_db = MagicMock()
        mock_players = [
            {"fid": f"1000{i}", "kid": "278", "name": f"FlaggedPlayer{i}", "status": "FLAGGED", "warning_reason": "Role Not Exist", "warning_count": 2}
            for i in range(20)
        ]
        view = FlaggedPlayersView(mock_db, mock_players)
        self.assertEqual(view.max_pages, 3)
        self.assertEqual(view.page, 0)
        self.assertTrue(view.prev_btn.disabled)
        self.assertFalse(view.next_btn.disabled)

        embed = view.get_embed()
        self.assertIn("Flagged / Problematic Players", embed.title)
        self.assertIn("FlaggedPlayer0", embed.description)
        self.assertIn("Page 1 of 3", embed.footer.text)

    async def test_player_list_view_filter(self):
        mock_db = MagicMock()
        mock_players = [
            {"fid": "1001", "kid": "278", "name": "PlayerA", "alliance": "NOR", "status": "ACTIVE", "warning_count": 0},
            {"fid": "1002", "kid": "278", "name": "PlayerB", "alliance": "OvO", "status": "FLAGGED", "warning_count": 1},
            {"fid": "1003", "kid": "278", "name": "PlayerC", "alliance": "NOR", "status": "DISABLED", "warning_count": 3},
        ]
        view = PlayerListView(mock_db, mock_players)
        self.assertEqual(len(view.players), 3)

        # Test filter callback for alliance
        mock_interaction = MagicMock()
        mock_interaction.data = {"values": ["ALLIANCE_NOR"]}
        mock_interaction.response = AsyncMock()
        await view.filter_callback(mock_interaction)
        self.assertEqual(len(view.players), 2)
        self.assertIn("Alliance [NOR]", view.alliance_filter)

        # Test filter callback for FLAGGED
        mock_interaction.data = {"values": ["STATUS_FLAGGED"]}
        await view.filter_callback(mock_interaction)
        self.assertEqual(len(view.players), 1)
        self.assertEqual(view.players[0]["fid"], "1002")


if __name__ == "__main__":
    unittest.main()
