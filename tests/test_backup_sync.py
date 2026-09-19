import os
import sys
import unittest
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import google_sync
from databases.player_database import PlayerDatabase
from cogs.backup_sync import SheetPruneConfirmView


class TestGoogleSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_players.db")
        self.backup_dir = os.path.join(self.temp_dir.name, "backups")

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("CREATE TABLE players (fid TEXT PRIMARY KEY, name TEXT);")
            conn.execute("INSERT INTO players VALUES ('12345', 'PlayerOne');")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_create_local_backup(self):
        backup_file = google_sync.create_local_backup(self.db_path, self.backup_dir)
        self.assertTrue(os.path.exists(backup_file))
        
        conn = sqlite3.connect(backup_file)
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM players WHERE fid = '12345'")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], "PlayerOne")
        finally:
            conn.close()

    def test_cleanup_local_backups(self):
        os.makedirs(self.backup_dir, exist_ok=True)
        for i in range(10):
            p = os.path.join(self.backup_dir, f"players_20260818_12000{i}.db")
            with open(p, "w") as f:
                f.write("dummy")

        purged = google_sync.cleanup_local_backups(self.backup_dir, keep_last_n=3)
        self.assertEqual(purged, 7)
        remaining = [f for f in os.listdir(self.backup_dir) if f.startswith("players_")]
        self.assertEqual(len(remaining), 3)

    def test_get_sheet_id_parsing(self):
        with patch.dict(os.environ, {"GOOGLE_SHEET_ID": "1OST7SFBUbdnpV2Gun0-Xc49dCF1W1c3oE9C5wAwjC7c/edit?gid=0#gid=0"}):
            sheet_id = google_sync.get_sheet_id()
            self.assertEqual(sheet_id, "1OST7SFBUbdnpV2Gun0-Xc49dCF1W1c3oE9C5wAwjC7c")

        with patch.dict(os.environ, {"GOOGLE_SHEET_ID": "https://docs.google.com/spreadsheets/d/abc123xyz456/edit"}):
            sheet_id = google_sync.get_sheet_id()
            self.assertEqual(sheet_id, "abc123xyz456")

    @patch("utils.google_sync.get_google_credentials")
    def test_export_players_to_sheet(self, mock_get_creds):
        mock_get_creds.return_value = MagicMock()
        mock_client = MagicMock()
        mock_sheet = MagicMock()
        mock_worksheet = MagicMock()
        mock_sheet.title = "Test Sheet"
        mock_sheet.url = "https://docs.google.com/spreadsheets/d/test"
        mock_sheet.worksheet.return_value = mock_worksheet
        mock_client.open_by_key.return_value = mock_sheet

        with patch("sys.modules", {**sys.modules, "gspread": MagicMock(authorize=MagicMock(return_value=mock_client))}):
            players = [
                {"fid": "111", "kid": "278", "name": "Hero", "alliance": "NOR", "discord_id": 12345, "status": "ACTIVE", "warning_count": 0, "warning_reason": None, "updated_at": "2026-08-18"}
            ]
            res = google_sync.export_players_to_sheet(players, "dummy_id")
            self.assertEqual(res["total_exported"], 1)

    @patch("utils.google_sync.get_google_credentials")
    def test_import_players_from_sheet(self, mock_get_creds):
        mock_get_creds.return_value = MagicMock()
        mock_client = MagicMock()
        mock_sheet = MagicMock()
        mock_worksheet = MagicMock()
        mock_worksheet.get_all_values.return_value = [
            ["FID", "KID", "Name", "Alliance", "Discord ID", "Status", "Warning Count", "Warning Reason"],
            ["117280427", "278", "Arthur", "NOR", "1234567890", "ACTIVE", "0", ""],
            ["INVALID_FID", "278", "BadUser", "NOR", "", "ACTIVE", "0", ""],
            ["", "", "", "", "", "", "", ""]
        ]
        mock_sheet.worksheet.return_value = mock_worksheet
        mock_client.open_by_key.return_value = mock_sheet

        with patch("sys.modules", {**sys.modules, "gspread": MagicMock(authorize=MagicMock(return_value=mock_client))}):
            res = google_sync.import_players_from_sheet("dummy_id")
            self.assertEqual(len(res["valid_players"]), 1)
            self.assertEqual(res["valid_players"][0]["fid"], "117280427")
            self.assertEqual(res["valid_players"][0]["name"], "Arthur")
            self.assertEqual(len(res["skipped_rows"]), 1)
            self.assertEqual(res["skipped_rows"][0]["row"], 3)



class TestGoogleSyncPrune(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "players.db")
        self.db = PlayerDatabase(db_path=self.db_path)
        await self.db.init_db(auto_migrate=False)

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_missing_fids_detection(self):
        await self.db.upsert_player(fid="1001", name="Player1")
        await self.db.upsert_player(fid="1002", name="Player2")
        await self.db.upsert_player(fid="1003", name="Player3")

        sheet_players = [
            {"fid": "1001", "name": "Player1Updated"},
            {"fid": "1004", "name": "Player4"}
        ]

        db_players = await self.db.get_all_players()
        db_fids_map = {str(p["fid"]): p for p in db_players if p.get("fid")}
        sheet_fids = {str(p["fid"]).strip() for p in sheet_players if p.get("fid")}
        missing_fids = [fid for fid in db_fids_map if fid not in sheet_fids]

        self.assertEqual(set(missing_fids), {"1002", "1003"})

    async def test_prune_confirm_deletes_and_upserts(self):
        await self.db.upsert_player(fid="1001", name="Player1")
        await self.db.upsert_player(fid="1002", name="Player2")

        mock_cog = MagicMock()
        mock_cog.db = self.db

        sheet_players = [{"fid": "1001", "name": "Player1New", "kid": "278", "alliance": "NOR"}]
        missing_fids = ["1002"]

        view = SheetPruneConfirmView(
            cog=mock_cog,
            user_id=42,
            missing_fids=missing_fids,
            valid_players=sheet_players,
            skipped_rows=[],
            sheet_title="Test Sheet",
            sheet_url="https://docs.google.com/test"
        )

        mock_interaction = MagicMock()
        mock_interaction.user.id = 42
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.edit_original_response = AsyncMock()

        # Click Confirm
        await view.confirm_btn.callback(mock_interaction)

        # Verify Player 1002 was deleted from DB
        p1002 = await self.db.get_player("1002")
        self.assertIsNone(p1002)

        # Verify Player 1001 was updated
        p1001 = await self.db.get_player("1001")
        self.assertIsNotNone(p1001)
        self.assertEqual(p1001["name"], "Player1New")

    async def test_prune_cancel_keeps_existing(self):
        await self.db.upsert_player(fid="1001", name="Player1")
        await self.db.upsert_player(fid="1002", name="Player2")

        mock_cog = MagicMock()
        mock_cog.db = self.db

        sheet_players = [{"fid": "1001", "name": "Player1New", "kid": "278", "alliance": "NOR"}]
        missing_fids = ["1002"]

        view = SheetPruneConfirmView(
            cog=mock_cog,
            user_id=42,
            missing_fids=missing_fids,
            valid_players=sheet_players,
            skipped_rows=[],
            sheet_title="Test Sheet",
            sheet_url="https://docs.google.com/test"
        )

        mock_interaction = MagicMock()
        mock_interaction.user.id = 42
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.edit_original_response = AsyncMock()

        # Click Cancel
        await view.cancel_btn.callback(mock_interaction)

        # Verify both players still exist in DB
        p1002 = await self.db.get_player("1002")
        self.assertIsNotNone(p1002)
        p1001 = await self.db.get_player("1001")
        self.assertIsNotNone(p1001)

    async def test_unauthorized_user_blocked(self):
        mock_cog = MagicMock()
        view = SheetPruneConfirmView(
            cog=mock_cog,
            user_id=42,
            missing_fids=["1002"],
            valid_players=[],
            skipped_rows=[],
            sheet_title="Test Sheet",
            sheet_url="https://docs.google.com/test"
        )

        mock_interaction = MagicMock()
        mock_interaction.user.id = 999  # Different user
        mock_interaction.response.send_message = AsyncMock()

        await view.confirm_btn.callback(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()
        self.assertIn("Only the command invoker", mock_interaction.response.send_message.call_args[0][0])


if __name__ == '__main__':
    unittest.main()

