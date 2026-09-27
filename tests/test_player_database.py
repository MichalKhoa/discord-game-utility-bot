import os
import sqlite3
import tempfile
import unittest

from databases.player_database import PlayerDatabase
from databases.wyr_database import Question_Database
from utils.embeds import WyrEmbed


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
            bar_a, bar_b, pct_a, pct_b = WyrEmbed.calculate_bar(3, 1)
            self.assertEqual(pct_a, 75)
            self.assertEqual(pct_b, 25)
            self.assertIn("█", bar_a)


if __name__ == "__main__":
    unittest.main()
