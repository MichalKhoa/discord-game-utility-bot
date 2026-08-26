import os
import io
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import tempfile
import hashlib
import discord

from utils.castle_battle_support import (
    format_time,
    calculate_reinforcement_window,
    create_reinforcement_embed,
    time_to_reinforce
)
from utils.redeem_code import (
    encode_data,
    classify,
    get_headers,
    make_progress_bar,
    fetch_player_info,
    verify_player,
    flag_player_sync,
    unflag_player_sync,
    load_proxies,
    ProxyPool,
    KS_ENCRYPT_KEY
)
from utils.code_detector import (
    extract_candidate_codes,
    extract_validity_info,
    create_detected_code_embed,
    process_announcement_message,
    WATCHED_CHANNELS,
    IGNORED_WORDS
)
from databases.player_database import PlayerDatabase
from databases.wyr_database import Question_Database


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


class TestRedeemUtils(unittest.TestCase):
    def test_encode_data(self):
        payload = {"fid": "12345", "cdk": "GIFT2026", "time": "1700000000"}
        signed = encode_data(payload)
        self.assertIn("sign", signed)
        expected_str = f"cdk=GIFT2026&fid=12345&time=1700000000{KS_ENCRYPT_KEY}"
        expected_hash = hashlib.md5(expected_str.encode()).hexdigest()
        self.assertEqual(signed["sign"], expected_hash)

    def test_classify_all_codes(self):
        test_cases = [
            ({"msg": "SUCCESS", "err_code": 0}, "SUCCESS"),
            ({"msg": "RECEIVED", "err_code": 40008}, "RECEIVED"),
            ({"msg": "SAME TYPE EXCHANGE", "err_code": 40011}, "SAME TYPE EXCHANGE"),
            ({"msg": "TIME ERROR", "err_code": 40007}, "TIME ERROR"),
            ({"msg": "CDK NOT FOUND", "err_code": 40014}, "CDK NOT FOUND"),
            ({"msg": "USED", "err_code": 40005}, "USED"),
            ({"msg": "TIMEOUT RETRY", "err_code": 40004}, "TIMEOUT RETRY"),
            ({"msg": "TOO FREQUENT", "err_code": 40019}, "TOO FREQUENT"),
            ({"msg": "USER INFO ERROR", "err_code": 40020}, "USER INFO ERROR"),
            ({"msg": "Role not exist", "err_code": 40001}, "ROLE NOT EXIST"),
            ({"msg": "STOVE_LV ERROR", "err_code": 40006}, "STOVE_LV ERROR"),
            ({"msg": "RECHARGE_MONEY ERROR", "err_code": 40017}, "RECHARGE_MONEY ERROR"),
            ({"msg": "RECHARGE_MONEY_VIP ERROR", "err_code": 40018}, "RECHARGE_MONEY_VIP ERROR"),
            ({"msg": "sign error", "err_code": 40000}, "SIGN ERROR"),
            ({"msg": "NOT LOGIN", "err_code": 40002}, "NOT LOGIN"),
            ("not a dict", "Invalid response format"),
            ({"msg": "CUSTOM_ERROR"}, "CUSTOM_ERROR"),
        ]
        for payload, expected in test_cases:
            self.assertEqual(classify(payload), expected)

    def test_get_headers(self):
        headers = get_headers()
        self.assertIn("user-agent", headers)
        self.assertIn("sec-ch-ua", headers)
        self.assertIn("origin", headers)

    def test_make_progress_bar(self):
        self.assertEqual(make_progress_bar(0, 10, length=10), "░░░░░░░░░░")
        self.assertEqual(make_progress_bar(5, 10, length=10), "█████░░░░░")
        self.assertEqual(make_progress_bar(10, 10, length=10), "██████████")
        self.assertEqual(make_progress_bar(0, 0, length=10), "░░░░░░░░░░")

    @patch("utils.redeem_code.send_signed_post")
    def test_fetch_player_info_success(self, mock_post):
        mock_post.return_value = {
            "msg": "SUCCESS",
            "err_code": 0,
            "data": {
                "nickname": "TestLord",
                "fid": "12345",
                "kid": "278",
                "stove_lv": 30
            }
        }
        res = fetch_player_info("12345", "278")
        self.assertTrue(res["success"])
        self.assertEqual(res["nickname"], "TestLord")
        self.assertEqual(res["stove_lv"], 30)

    @patch("utils.redeem_code.send_signed_post")
    def test_fetch_player_info_not_found(self, mock_post):
        mock_post.return_value = {
            "msg": "ROLE NOT EXIST",
            "err_code": 40001,
            "data": None
        }
        res = fetch_player_info("99999", "278")
        self.assertFalse(res["success"])

    @patch("utils.redeem_code.send_signed_post")
    def test_verify_player_success(self, mock_post):
        mock_post.return_value = {
            "msg": "SUCCESS",
            "err_code": 0,
            "data": {"nickname": "KingHero", "fid": "11111", "kid": "278"}
        }
        valid, msg = verify_player("11111", "278")
        self.assertTrue(valid)
        self.assertIn("KingHero", msg)

    def test_flag_and_unflag_sync(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_sync.db")
            # Create table
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                conn.execute('''
                    CREATE TABLE players (
                        fid TEXT PRIMARY KEY,
                        kid TEXT,
                        name TEXT,
                        alliance TEXT,
                        discord_id INTEGER,
                        status TEXT DEFAULT 'ACTIVE',
                        warning_count INTEGER DEFAULT 0,
                        warning_reason TEXT,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP
                    )
                ''')
                conn.execute("INSERT INTO players (fid, kid, name, status) VALUES ('123', '278', 'Player1', 'ACTIVE')")
                conn.commit()

            # Flag player
            flag_player_sync("123", "RATE_LIMITED", db_path=db_path, threshold=3)
            with sqlite3.connect(db_path) as conn:
                row = conn.execute("SELECT status, warning_count, warning_reason FROM players WHERE fid = '123'").fetchone()
                self.assertEqual(row[0], "FLAGGED")
                self.assertEqual(row[1], 1)
                self.assertEqual(row[2], "RATE_LIMITED")

            # Unflag player
            unflag_player_sync("123", db_path=db_path)
            with sqlite3.connect(db_path) as conn:
                row = conn.execute("SELECT status, warning_count, warning_reason FROM players WHERE fid = '123'").fetchone()
                self.assertEqual(row[0], "ACTIVE")
                self.assertEqual(row[1], 0)
                self.assertIsNone(row[2])

    def test_proxy_pool_rotation(self):
        proxies = ["http://1.1.1.1:8080", "http://2.2.2.2:8080"]
        pool = ProxyPool(proxies)
        
        p1, h1 = pool.get_proxy_and_headers()
        p2, h2 = pool.get_proxy_and_headers()
        p3, h3 = pool.get_proxy_and_headers()

        self.assertEqual(p1, "http://1.1.1.1:8080")
        self.assertEqual(p2, "http://2.2.2.2:8080")
        self.assertEqual(p3, "http://1.1.1.1:8080")
        # Ensure header bound to proxy is consistent
        self.assertEqual(h1, pool.headers_map["http://1.1.1.1:8080"])
        self.assertEqual(h3, pool.headers_map["http://1.1.1.1:8080"])

    def test_load_proxies_env(self):
        with patch.dict(os.environ, {"PROXY_LIST": "http://proxy1:8080, http://proxy2:8080"}):
            loaded = load_proxies()
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0], "http://proxy1:8080")
            self.assertEqual(loaded[1], "http://proxy2:8080")


class TestCodeDetector(unittest.TestCase):
    def test_watched_channels(self):
        self.assertIn(1374889273077272636, WATCHED_CHANNELS)
        self.assertIn(1374888983812902993, WATCHED_CHANNELS)
        self.assertIn(1374888701204758599, WATCHED_CHANNELS)

    def test_extract_candidate_codes_all_formats(self):
        # Format 1: 🎁 Gift Code: OFFICIALSTORE08011
        t_official = "🎁 Gift Code: OFFICIALSTORE08011 \nHave a great weekend!"
        self.assertEqual(extract_candidate_codes(t_official), ["OFFICIALSTORE08011"])

        # Format 1b: 🎁 **Gift Code:** OFFICIALSTORE08011
        t_bold = "🎁 **Gift Code:** OFFICIALSTORE08011"
        self.assertEqual(extract_candidate_codes(t_bold), ["OFFICIALSTORE08011"])

        # Format 1c: Gift Code: **KINGSHOT2026**
        t1 = "Gift Code: **KINGSHOT2026**\nClaim before August!"
        self.assertEqual(extract_candidate_codes(t1), ["KINGSHOT2026"])

        # Format 2: CDK: XYZ
        t2 = "CDK: `WOSSUMMER`"
        self.assertEqual(extract_candidate_codes(t2), ["WOSSUMMER"])

        # Format 3: Backticks
        t3 = "Here is a code: `VALENTINE2026` for all members"
        self.assertEqual(extract_candidate_codes(t3), ["VALENTINE2026"])

        # Format 4: >> CODE <<
        t4 = "Redeem >> EASTER2026 << in game settings"
        self.assertEqual(extract_candidate_codes(t4), ["EASTER2026"])

        # Deduplication
        t5 = "Gift Code: `GIFT50` and also CDK: GIFT50"
        self.assertEqual(extract_candidate_codes(t5), ["GIFT50"])

        # Ignore noise & URLs
        t6 = "Visit our DISCORD at https://discord.gg/test for ANNOUNCEMENT and UPDATE"
        self.assertEqual(extract_candidate_codes(t6), [])

    def test_extract_validity_info(self):
        text = "🎁 Gift Code: HAPPYEMOJIDAY \n📅 Valid Until: July 21st, 23:59 (UTC+0)"
        validity = extract_validity_info(text)
        self.assertEqual(validity, "July 21st, 23:59 (UTC+0)")

        text2 = "**Gift Code:** ABCDE\n**Expires:** 2026-09-01"
        self.assertEqual(extract_validity_info(text2), "2026-09-01")

        text3 = "No expiration date provided"
        self.assertIsNone(extract_validity_info(text3))

    def test_create_detected_code_embed(self):
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.channel = MagicMock()
        mock_msg.channel.id = 1374889273077272636
        mock_msg.author = MagicMock()
        mock_msg.author.display_name = "Kingshot Announcer"
        mock_msg.author.display_avatar.url = "https://example.com/avatar.png"
        mock_msg.content = "🎁 Gift Code: HAPPYEMOJIDAY \n📅 Valid Until: July 21st, 23:59 (UTC+0)"
        mock_msg.embeds = []

        embed = create_detected_code_embed("HAPPYEMOJIDAY", mock_msg)
        self.assertIsInstance(embed, discord.Embed)
        self.assertIn("HAPPYEMOJIDAY", embed.description)
        field_names = [f.name for f in embed.fields]
        self.assertIn("📅 Valid Until", field_names)
        validity_field = next(f for f in embed.fields if f.name == "📅 Valid Until")
        self.assertIn("July 21st, 23:59 (UTC+0)", validity_field.value)


class TestPlayerDatabase(unittest.IsolatedAsyncioTestCase):
    async def test_player_database_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_players.db")
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)

            # Insert player
            await db.upsert_player(fid="99999", kid="278", name="OldName", alliance="ALPHA")
            p = await db.get_player("99999")
            self.assertIsNotNone(p)
            self.assertEqual(p["name"], "OldName")
            self.assertEqual(p["alliance"], "ALPHA")

            # Update name and kingdom
            await db.update_player_name_and_kid("99999", "NewName", "300")
            p_updated = await db.get_player("99999")
            self.assertEqual(p_updated["name"], "NewName")
            self.assertEqual(p_updated["kid"], "300")

            # Warning and strikes
            flagged = await db.flag_player("99999", "TEST_ERROR")
            self.assertEqual(flagged["warning_count"], 1)
            self.assertEqual(flagged["status"], "FLAGGED")

            # Unflag
            await db.unflag_player("99999")
            p_unflagged = await db.get_player("99999")
            self.assertEqual(p_unflagged["warning_count"], 0)
            self.assertEqual(p_unflagged["status"], "ACTIVE")

            # Stats
            stats = await db.get_stats()
            self.assertEqual(stats["total"], 1)
            self.assertEqual(stats["active"], 1)

    async def test_bulk_upsert_and_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_bulk.db")
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)

            players_data = [
                {"fid": "1001", "kid": "278", "name": "Alice", "alliance": "NOR"},
                {"fid": "1002", "kid": "278", "name": "Bob", "alliance": "NOR"},
                {"fid": "1003", "kid": "279", "name": "Charlie", "alliance": "SOL"},
            ]
            count = await db.bulk_upsert_players(players_data)
            self.assertEqual(count, 3)

            # Filter by alliance
            nor_players = await db.get_all_players(alliance="NOR")
            self.assertEqual(len(nor_players), 2)

            # Filter by kingdom
            k279_players = await db.get_all_players(kingdom="279")
            self.assertEqual(len(k279_players), 1)
            self.assertEqual(k279_players[0]["name"], "Charlie")

            # Search players
            search_res = await db.search_players("Ali")
            self.assertEqual(len(search_res), 1)
            self.assertEqual(search_res[0]["fid"], "1001")

            # Alliances list
            alliances = await db.get_alliances()
            self.assertEqual(alliances, ["NOR", "SOL"])

            # Delete player
            del_ok = await db.delete_player("1001")
            self.assertTrue(del_ok)
            self.assertIsNone(await db.get_player("1001"))

    async def test_redeemed_codes_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_codes.db")
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)

            # Not redeemed initially
            self.assertIsNone(await db.is_code_redeemed("SUMMER2026"))

            # Log code
            await db.log_redeemed_code("SUMMER2026", redeemed_by=123456, success_count=50, total_attempted=55)

            # Check redeemed
            entry = await db.is_code_redeemed("SUMMER2026")
            self.assertIsNotNone(entry)
            self.assertEqual(entry["code"], "SUMMER2026")
            self.assertEqual(entry["success_count"], 50)

            # History list
            history = await db.get_redeemed_codes()
            self.assertEqual(len(history), 1)

    async def test_csv_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_csv.db")
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)

            await db.upsert_player(fid="5001", kid="278", name="Exporter", alliance="VIP")
            csv_str = await db.export_csv()
            self.assertIn("fid,kid,name,alliance", csv_str)
            self.assertIn("5001,278,Exporter,VIP", csv_str)

    async def test_dynamic_column_migration(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_migration.db")
            import sqlite3
            # Create old schema table missing new columns
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE players (fid TEXT PRIMARY KEY, kid TEXT, name TEXT)")
                conn.execute("INSERT INTO players (fid, kid, name) VALUES ('777', '278', 'LegacyPlayer')")
                conn.commit()

            # Init DB should auto-migrate missing columns (alliance, discord_id, status, warning_count, etc.)
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)

            player = await db.get_player("777")
            self.assertIsNotNone(player)
            self.assertEqual(player["name"], "LegacyPlayer")
            self.assertEqual(player["status"], "ACTIVE")
            self.assertEqual(player["warning_count"], 0)

    def test_parse_raw_player_text(self):
        sample_text = """
        # Alliance Alpha
        10001 278 PlayerOne
        10002 305 PlayerTwo
        # Alliance Beta
        10003 PlayerThree
        10004,278,PlayerFour
        #
        10005
        invalid_line
        """
        players = PlayerDatabase.parse_raw_player_text(sample_text, default_kingdom="278")
        self.assertEqual(len(players), 5)
        self.assertEqual(players[0]["fid"], "10001")
        self.assertEqual(players[0]["kid"], "278")
        self.assertEqual(players[0]["name"], "PlayerOne")
        self.assertEqual(players[0]["alliance"], "Alliance Alpha")

        self.assertEqual(players[1]["fid"], "10002")
        self.assertEqual(players[1]["kid"], "305")
        self.assertEqual(players[1]["alliance"], "Alliance Alpha")

        self.assertEqual(players[2]["fid"], "10003")
        self.assertEqual(players[2]["kid"], "278")
        self.assertEqual(players[2]["name"], "PlayerThree")
        self.assertEqual(players[2]["alliance"], "Alliance Beta")

        self.assertEqual(players[3]["fid"], "10004")
        self.assertEqual(players[3]["kid"], "278")

        self.assertEqual(players[4]["fid"], "10005")
        self.assertEqual(players[4]["kid"], "278")

    async def test_batch_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_batch.db")
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)

            # Insert sample players
            players = [
                {"fid": "2001", "kid": "278", "name": "P1", "alliance": "NOR"},
                {"fid": "2002", "kid": "278", "name": "P2", "alliance": "NOR"},
                {"fid": "2003", "kid": "278", "name": "P3", "alliance": "OvO"},
                {"fid": "2004", "kid": "300", "name": "P4", "alliance": "RKF"},
            ]
            await db.bulk_upsert_players(players)

            # Test batch_update_kingdom by alliance
            k_count = await db.batch_update_kingdom(new_kid="999", alliance="NOR")
            self.assertEqual(k_count, 2)
            p1 = await db.get_player("2001")
            self.assertEqual(p1["kid"], "999")

            # Test batch_update_alliance by FIDs
            a_count = await db.batch_update_alliance(new_alliance="LEGEND", fids=["2003", "2004"])
            self.assertEqual(a_count, 2)
            p3 = await db.get_player("2003")
            self.assertEqual(p3["alliance"], "LEGEND")

            # Test batch_set_status
            s_count = await db.batch_set_status(new_status="DISABLED", alliance="NOR")
            self.assertEqual(s_count, 2)
            p2 = await db.get_player("2002")
            self.assertEqual(p2["status"], "DISABLED")

            # Test batch_delete_players by FID
            d_count = await db.batch_delete_players(fids=["2001"])
            self.assertEqual(d_count, 1)
            self.assertIsNone(await db.get_player("2001"))

    async def test_csv_export_import_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_roundtrip.db")
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)

            # Insert initial players
            await db.upsert_player(fid="3001", kid="278", name="Original One", alliance="NOR")
            await db.upsert_player(fid="3002", kid="305", name="Original Two", alliance="OvO")

            # Export to CSV
            csv_data = await db.export_csv()

            # Append a new player to the CSV text
            modified_csv = csv_data + "\n3003,278,New Guy,NOR,ACTIVE,0,\n"

            # Parse and re-import
            parsed = db.parse_raw_player_text(modified_csv)
            self.assertEqual(len(parsed), 3)
            self.assertEqual(parsed[2]["fid"], "3003")
            self.assertEqual(parsed[2]["name"], "New Guy")
            self.assertEqual(parsed[2]["alliance"], "NOR")

            await db.bulk_upsert_players(parsed)
            all_players = await db.get_all_players()
            self.assertEqual(len(all_players), 3)




class TestWyrDatabase(unittest.IsolatedAsyncioTestCase):
    async def test_wyr_database_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_wyr.db")
            db = Question_Database(db_path)
            await db.init_db()

            # Empty returns None
            self.assertIsNone(await db.get_random_wyr_question())

            # Add question with tags
            await db.add_wyr_question("Eat pizza everyday", "Eat tacos everyday", ["food", "lifestyle"], rating="SFW")

            # Fetch random question
            q = await db.get_random_wyr_question()
            self.assertIsNotNone(q)
            self.assertEqual(q[0], "Eat pizza everyday")
            self.assertEqual(q[1], "Eat tacos everyday")

            # Test vote recording
            await db.record_wyr_vote(q["id"], "A")
            q_after = await db.get_random_wyr_question()
            self.assertEqual(q_after["votes_a"], 1)
            self.assertEqual(q_after["votes_b"], 0)

            # Test WyrEmbed progress bar calculation
            from utils.embeds import WyrEmbed
            bar_a, bar_b, pct_a, pct_b = WyrEmbed.calculate_bar(3, 1)
            self.assertEqual(pct_a, 75)
            self.assertEqual(pct_b, 25)
            self.assertIn("█", bar_a)


class TestMenuViews(unittest.TestCase):
    def test_menu_views_instantiation(self):
        from utils.views import MenuButtons, GameMenuButtons, PlayerMenuButtons, UtilityMenuButtons
        mock_bot = MagicMock()
        v_main = MenuButtons(mock_bot)
        self.assertEqual(len(v_main.children), 3)

        v_game = GameMenuButtons(mock_bot)
        self.assertEqual(len(v_game.children), 3)

        v_player = PlayerMenuButtons(mock_bot)
        self.assertGreaterEqual(len(v_player.children), 5)

        v_util = UtilityMenuButtons(mock_bot)
        self.assertGreaterEqual(len(v_util.children), 4)

    def test_russian_roulette_gameplay(self):
        from cogs.russian_roulette import RussianRouletteGame
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
        from cogs.russian_roulette import RussianRouletteView
        mock_bot = MagicMock()
        view = RussianRouletteView(mock_bot, host=mock_user, chamber_size=6)
        embed, gif_file = view.get_embed()
        self.assertIn("Russian Roulette", embed.title)
        self.assertIsNone(gif_file)

        suspense_embed, suspense_file = view.get_suspense_embed(mock_user, action_type="spin")
        self.assertIn("Spinning Cylinder", suspense_embed.title)


class TestCodeRedeemCog(unittest.IsolatedAsyncioTestCase):
    async def test_run_redeem_handles_forbidden_channel_send(self):
        from cogs.code_redeem import CodeRedeem
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

    async def test_stop_current_redemption(self):
        from cogs.code_redeem import CodeRedeem
        mock_bot = MagicMock()
        cog = CodeRedeem(mock_bot)
        
        # When not running, returns False
        self.assertFalse(cog.stop_current_redemption())

        # When event is set up
        import threading
        cog.current_cancel_event = threading.Event()
        self.assertTrue(cog.stop_current_redemption())
        self.assertTrue(cog.current_cancel_event.is_set())

    def test_redeem_for_all_cancel_event(self):
        from utils.redeem_code import redeem_for_all
        import threading
        cancel_evt = threading.Event()
        cancel_evt.set()  # Cancel immediately

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "test_cancel.db")
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE players (fid TEXT PRIMARY KEY, kid TEXT, name TEXT, status TEXT DEFAULT 'ACTIVE')")
            conn.execute("INSERT INTO players (fid, kid, name) VALUES ('111', '278', 'P1')")
            conn.execute("INSERT INTO players (fid, kid, name) VALUES ('222', '278', 'P2')")
            conn.commit()
            conn.close()

            result = redeem_for_all("CANCELCODE", file_path=db_path, cancel_event=cancel_evt)
            self.assertIn("Process Cancelled by User", result)

    async def test_confirm_abort_modal(self):
        from cogs.code_redeem import ConfirmAbortModal
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


    def test_flagged_players_view(self):
        from cogs.player_manager import FlaggedPlayersView
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

    def test_player_list_view_filter(self):
        from cogs.player_manager import PlayerListView
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
        import asyncio
        asyncio.run(view.filter_callback(mock_interaction))
        self.assertEqual(len(view.players), 2)
        self.assertIn("Alliance [NOR]", view.alliance_filter)

        # Test filter callback for FLAGGED
        mock_interaction.data = {"values": ["STATUS_FLAGGED"]}
        asyncio.run(view.filter_callback(mock_interaction))
        self.assertEqual(len(view.players), 1)
        self.assertEqual(view.players[0]["fid"], "1002")


if __name__ == '__main__':
    unittest.main()



