import os
import sys
import unittest
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import google_sync


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


if __name__ == '__main__':
    unittest.main()
