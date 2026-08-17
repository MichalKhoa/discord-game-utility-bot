import os
import unittest
import tempfile
import hashlib
from utils.castle_battle_support import format_time, calculate_reinforcement_window
from utils.redeem_code import encode_data, classify, KS_ENCRYPT_KEY
from databases.player_database import PlayerDatabase


class TestBattleSupport(unittest.TestCase):
    def test_format_time(self):
        self.assertEqual(format_time(0), "00:00")
        self.assertEqual(format_time(65), "01:05")
        self.assertEqual(format_time(120), "02:00")
        self.assertEqual(format_time(3599), "59:59")

    def test_calculate_reinforcement_window_longer_march(self):
        res = calculate_reinforcement_window(opponent_march_time=100, gap_between_rallies=10, user_march_time=120)
        self.assertEqual(res["march_diff"], 20)
        self.assertIn("00:20", res["action"])
        self.assertIn("00:10", res["action"])

    def test_calculate_reinforcement_window_shorter_march(self):
        res = calculate_reinforcement_window(opponent_march_time=100, gap_between_rallies=10, user_march_time=80)
        self.assertEqual(res["march_diff"], -20)
        self.assertIn("00:20", res["timing_detail"])


class TestRedeemUtils(unittest.TestCase):
    def test_encode_data(self):
        payload = {"fid": "12345", "cdk": "GIFT2026", "time": "1700000000"}
        signed = encode_data(payload)
        self.assertIn("sign", signed)
        expected_str = f"cdk=GIFT2026&fid=12345&time=1700000000{KS_ENCRYPT_KEY}"
        expected_hash = hashlib.md5(expected_str.encode()).hexdigest()
        self.assertEqual(signed["sign"], expected_hash)

    def test_classify_status(self):
        self.assertEqual(classify({"msg": "SUCCESS", "err_code": 0}), "SUCCESS")
        self.assertEqual(classify({"msg": "RECEIVED", "err_code": 40008}), "RECEIVED")
        self.assertEqual(classify({"msg": "TIME ERROR", "err_code": 40007}), "TIME ERROR")
        self.assertEqual(classify({"msg": "CDK NOT FOUND", "err_code": 40014}), "CDK NOT FOUND")
        self.assertEqual(classify({"msg": "TOO FREQUENT", "err_code": 40019}), "TOO FREQUENT")
        self.assertEqual(classify({"msg": "Role not exist", "err_code": 40001}), "ROLE NOT EXIST")


class TestCodeDetector(unittest.TestCase):
    def test_extract_candidate_codes(self):
        from utils.code_detector import extract_candidate_codes, WATCHED_CHANNELS

        # Check watched channel IDs
        self.assertIn(1374889273077272636, WATCHED_CHANNELS)
        self.assertIn(1374888983812902993, WATCHED_CHANNELS)
        self.assertIn(1374888701204758599, WATCHED_CHANNELS)

        # Explicit gift code format
        text1 = "🎉 New Gift Code Available!\nGift Code: **KINGSHOT2026**\nValid until Aug 25"
        self.assertEqual(extract_candidate_codes(text1), ["KINGSHOT2026"])

        # CDK format
        text2 = "CDK: WOSSUMMER24\nClaim fast!"
        self.assertEqual(extract_candidate_codes(text2), ["WOSSUMMER24"])

        # Backticks format
        text3 = "Here is your code: `HAPPYWEEKEND` for all players!"
        self.assertEqual(extract_candidate_codes(text3), ["HAPPYWEEKEND"])

        # Arrows format
        text4 = "Use code >> VALENTINE2026 << in game"
        self.assertEqual(extract_candidate_codes(text4), ["VALENTINE2026"])

        # Filter ignored words & URLs
        text5 = "Join our DISCORD server at https://discord.gg/century for ANNOUNCEMENT"
        self.assertEqual(extract_candidate_codes(text5), [])



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


if __name__ == '__main__':
    unittest.main()
