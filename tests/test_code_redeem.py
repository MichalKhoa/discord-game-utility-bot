import os
import hashlib
import asyncio
import tempfile
import sqlite3
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import discord

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
    KS_ENCRYPT_KEY,
)
from utils.code_detector import (
    extract_candidate_codes,
    extract_validity_info,
    create_detected_code_embed,
    process_announcement_message,
    WATCHED_CHANNELS,
    IGNORED_WORDS,
)
from databases.player_database import PlayerDatabase
from cogs.code_redeem import CodeRedeem, DEFAULT_AUTO_REDEEM_CHANNEL_ID
from utils.modals import ConfirmAbortModal as UtilConfirmAbortModal
from utils.views import (
    ConfirmRedeemView as UtilConfirmRedeemView,
    BatchProgressView as UtilBatchProgressView,
    ConfirmRedeemView,
    BatchProgressView,
)
from utils.modals import ConfirmAbortModal


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


class TestAutoRedeemSystem(unittest.IsolatedAsyncioTestCase):
    async def test_watched_channels_crud(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_watched.db")
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)

            default_chans = {111, 222}
            # Initially returns default
            chans = await db.get_watched_channels(default_channels=default_chans)
            self.assertEqual(chans, {111, 222})

            # Add channel
            chans = await db.add_watched_channel(333, default_channels=default_chans)
            self.assertIn(333, chans)
            self.assertIn(111, chans)

            # Persisted
            loaded = await db.get_watched_channels(default_channels=default_chans)
            self.assertIn(333, loaded)

            # Remove channel
            chans = await db.remove_watched_channel(111, default_channels=default_chans)
            self.assertNotIn(111, chans)
            self.assertIn(333, chans)

    async def test_process_announcement_message_auto_redeem_callback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_proc.db")
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)

            mock_bot = MagicMock()
            mock_msg = MagicMock(spec=discord.Message)
            mock_msg.channel = MagicMock()
            mock_msg.channel.id = 1374889273077272636  # in default WATCHED_CHANNELS
            mock_msg.content = "New gift code available: `FRESHCODE2026`! Enjoy!"
            mock_msg.embeds = []
            mock_msg.author = MagicMock()
            mock_msg.author.display_name = "GameAdmin"
            mock_msg.author.display_avatar.url = "http://example.com/avatar.png"

            auto_callback = AsyncMock()
            codes = await process_announcement_message(
                mock_msg,
                mock_bot,
                db,
                auto_redeem_callback=auto_callback
            )
            self.assertEqual(codes, ["FRESHCODE2026"])
            auto_callback.assert_called_once_with(["FRESHCODE2026"], mock_msg)

    async def test_process_announcement_message_filters_already_redeemed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_proc2.db")
            db = PlayerDatabase(db_path)
            await db.init_db(auto_migrate=False)
            await db.log_redeemed_code("OLDCODE999")

            mock_bot = MagicMock()
            mock_msg = MagicMock(spec=discord.Message)
            mock_msg.channel = MagicMock()
            mock_msg.channel.id = 1374889273077272636
            mock_msg.content = "Code: `OLDCODE999`"
            mock_msg.embeds = []

            auto_callback = AsyncMock()
            codes = await process_announcement_message(
                mock_msg,
                mock_bot,
                db,
                auto_redeem_callback=auto_callback
            )
            self.assertEqual(codes, [])
            auto_callback.assert_not_called()

    async def test_auto_redeem_codes_dispatches_run_redeem(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_bot = MagicMock()
            mock_bot.owner_id = 12345
            cog = CodeRedeem(mock_bot)
            cog.db = PlayerDatabase(os.path.join(tmpdir, "test_auto.db"))
            await cog.db.init_db(auto_migrate=False)

            with patch.object(cog, "run_redeem", new_callable=AsyncMock) as mock_run:
                mock_channel = AsyncMock()
                mock_msg = MagicMock()
                mock_msg.channel = mock_channel
                mock_msg.jump_url = "https://discord.com/msg/1"

                await cog.auto_redeem_codes(["AUTOTESTCODE"], source_message=mock_msg)
                await asyncio.sleep(0.05)

                mock_run.assert_called_once()
                self.assertEqual(mock_run.call_args[0][1], ["AUTOTESTCODE"])

    async def test_scan_and_redeem_finds_history_codes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_bot = MagicMock()
            cog = CodeRedeem(mock_bot)
            cog.db = PlayerDatabase(os.path.join(tmpdir, "test_scan.db"))
            await cog.db.init_db(auto_migrate=False)

            # Mock watched channel
            mock_channel = MagicMock()
            mock_channel.id = 1374889273077272636
            perms = MagicMock()
            perms.read_message_history = True
            mock_channel.permissions_for.return_value = perms

            # Mock message in history
            mock_hist_msg = MagicMock()
            mock_hist_msg.content = "Latest gift code: `SCANTEST123`"
            mock_hist_msg.embeds = []

            async def async_iter(*args, **kwargs):
                yield mock_hist_msg

            mock_channel.history = MagicMock(side_effect=async_iter)
            mock_bot.get_channel.return_value = mock_channel

            with patch.object(cog, "auto_redeem_codes", new_callable=AsyncMock) as mock_auto:
                found = await cog.scan_and_redeem(days=3)
                self.assertIn("SCANTEST123", found)
                mock_auto.assert_called_once_with(["SCANTEST123"], source_title="Background Channel Scan (3d)")

    async def test_redeem_channel_commands(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_bot = MagicMock()
            mock_bot.is_owner = AsyncMock(return_value=True)
            cog = CodeRedeem(mock_bot)
            cog.db = PlayerDatabase(os.path.join(tmpdir, "test_cmds.db"))
            await cog.db.init_db(auto_migrate=False)

            # Test set-channel
            mock_ch = MagicMock(spec=discord.TextChannel)
            mock_ch.id = 55555
            mock_ch.mention = "<#55555>"
            mock_interaction = MagicMock(spec=discord.Interaction)
            mock_interaction.user = MagicMock()
            mock_interaction.response.send_message = AsyncMock()

            await cog.redeem_set_channel_cmd.callback(cog, mock_interaction, mock_ch)
            saved = await cog.db.get_setting("redeem_alert_channel_id")
            self.assertEqual(saved, "55555")

            # Test watch-channel add
            await cog.watch_channel_add.callback(cog, mock_interaction, mock_ch)
            watched = await cog.db.get_watched_channels()
            self.assertIn(55555, watched)

            # Test watch-channel remove
            await cog.watch_channel_remove.callback(cog, mock_interaction, mock_ch)
            watched = await cog.db.get_watched_channels()
            self.assertNotIn(55555, watched)

    async def test_get_notification_channel_resolution(self):
        self.assertEqual(DEFAULT_AUTO_REDEEM_CHANNEL_ID, 1374873047127035981)
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_bot = MagicMock()
            mock_ch_default = MagicMock(spec=discord.TextChannel)
            mock_ch_default.id = DEFAULT_AUTO_REDEEM_CHANNEL_ID
            mock_ch_default.send = AsyncMock()

            def get_channel_side_effect(cid):
                if cid == DEFAULT_AUTO_REDEEM_CHANNEL_ID:
                    return mock_ch_default
                return None

            mock_bot.get_channel = MagicMock(side_effect=get_channel_side_effect)
            mock_bot.fetch_channel = AsyncMock(return_value=None)
            mock_bot.guilds = []

            cog = CodeRedeem(mock_bot)
            cog.db = PlayerDatabase(os.path.join(tmpdir, "test_channel.db"))
            await cog.db.init_db(auto_migrate=False)

            # 1. Without setting, resolves DEFAULT_AUTO_REDEEM_CHANNEL_ID
            resolved = await cog.get_notification_channel()
            self.assertEqual(resolved, mock_ch_default)

            # 2. When custom setting configured, resolves custom channel
            mock_ch_custom = MagicMock(spec=discord.TextChannel)
            mock_ch_custom.id = 999999
            mock_ch_custom.send = AsyncMock()

            def get_channel_with_custom(cid):
                if cid == 999999:
                    return mock_ch_custom
                if cid == DEFAULT_AUTO_REDEEM_CHANNEL_ID:
                    return mock_ch_default
                return None

            mock_bot.get_channel = MagicMock(side_effect=get_channel_with_custom)
            await cog.db.set_setting("redeem_alert_channel_id", "999999")
            resolved_custom = await cog.get_notification_channel()
            self.assertEqual(resolved_custom, mock_ch_custom)

    def test_extract_candidate_codes_preserves_casing(self):
        text = "Check out the new gift code: `JPHolidaySEP` and >>Hangul2025<<!"
        codes = extract_candidate_codes(text)
        self.assertIn("JPHolidaySEP", codes)
        self.assertIn("Hangul2025", codes)

    def test_redeem_for_one_casing_fallback(self):
        import utils.redeem_code as rc
        def mock_post(endpoint, data, **kwargs):
            if data.get("cdk") == "vip777":
                return {"msg": "CDK NOT FOUND.", "err_code": 40014}
            elif data.get("cdk") == "VIP777":
                return {"msg": "SUCCESS", "err_code": 20000}
            return {"msg": "CDK NOT FOUND.", "err_code": 40014}

        with patch.object(rc, "send_signed_post", side_effect=mock_post) as m_post:
            res = rc.redeem_for_one("111", "vip777", "278")
            self.assertEqual(res.get("msg"), "SUCCESS")
            self.assertEqual(m_post.call_count, 2)

    def test_redeem_for_one_preserved_success_no_fallback(self):
        import utils.redeem_code as rc
        with patch.object(rc, "send_signed_post", return_value={"msg": "SUCCESS", "err_code": 20000}) as m_post:
            res = rc.redeem_for_one("111", "JPHolidaySEP", "278")
            self.assertEqual(res.get("msg"), "SUCCESS")
            self.assertEqual(m_post.call_count, 1)

    def test_redeem_for_all_casing_fallback(self):
        import utils.redeem_code as rc
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "players.db")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE players (fid TEXT PRIMARY KEY, kid TEXT, status TEXT)")
            conn.execute("INSERT INTO players VALUES ('101', '278', 'ACTIVE')")
            conn.execute("INSERT INTO players VALUES ('102', '278', 'ACTIVE')")
            conn.commit()
            conn.close()

            calls = []
            def mock_redeem(fid, kid, cdk, **kwargs):
                calls.append((fid, cdk))
                if cdk == "vip777":
                    return "CDK NOT FOUND"
                return "SUCCESS"

            with patch.object(rc, "redeem_once", side_effect=mock_redeem):
                result = rc.redeem_for_all("vip777", file_path=db_path, default_kingdom="278")
                self.assertIn("Process Complete", result)
                # Player 101 tried 'vip777' then 'VIP777', Player 102 tried 'VIP777' directly
                self.assertEqual(calls, [('101', 'vip777'), ('101', 'VIP777'), ('102', 'VIP777')])


class TestCodeRedeemCog(unittest.IsolatedAsyncioTestCase):
    def test_ui_component_extraction_and_reexports(self):
        import cogs.code_redeem as cr

        self.assertIs(cr.ConfirmAbortModal, UtilConfirmAbortModal)
        self.assertIs(cr.ConfirmRedeemView, UtilConfirmRedeemView)
        self.assertIs(cr.BatchProgressView, UtilBatchProgressView)
        self.assertIn("ConfirmAbortModal", cr.__all__)
        self.assertIn("ConfirmRedeemView", cr.__all__)
        self.assertIn("BatchProgressView", cr.__all__)

    async def test_confirm_redeem_view(self):
        mock_confirm = AsyncMock()
        mock_cancel = AsyncMock()
        view = ConfirmRedeemView(author_id=123, on_confirm=mock_confirm, on_cancel=mock_cancel)

        # interaction_check - unauthorized
        inter_unauth = MagicMock()
        inter_unauth.user.id = 999
        inter_unauth.response.send_message = AsyncMock()
        self.assertFalse(await view.interaction_check(inter_unauth))
        inter_unauth.response.send_message.assert_called_once()

        # interaction_check - authorized
        inter_auth = MagicMock()
        inter_auth.user.id = 123
        self.assertTrue(await view.interaction_check(inter_auth))

        # confirm button
        inter_btn = MagicMock()
        inter_btn.response.edit_message = AsyncMock()
        await view.confirm_btn.callback(inter_btn)
        self.assertTrue(view.value)
        mock_confirm.assert_called_once_with(inter_btn)

        # cancel button
        view2 = ConfirmRedeemView(author_id=123, on_confirm=mock_confirm, on_cancel=mock_cancel)
        inter_cancel = MagicMock()
        inter_cancel.response.edit_message = AsyncMock()
        await view2.cancel_btn.callback(inter_cancel)
        self.assertFalse(view2.value)
        mock_cancel.assert_called_once_with(inter_cancel)

    async def test_batch_progress_view_and_modal(self):
        mock_stop = AsyncMock()
        view = BatchProgressView(author_id=123, on_stop=mock_stop)

        # Non-author, non-admin cannot stop
        inter_unauth = MagicMock()
        inter_unauth.user.id = 999
        inter_unauth.guild = MagicMock()
        inter_unauth.user.guild_permissions.manage_guild = False
        inter_unauth.client.is_owner = AsyncMock(return_value=False)
        inter_unauth.response.send_message = AsyncMock()
        inter_unauth.response.send_modal = AsyncMock()

        await view.stop_button.callback(inter_unauth)
        inter_unauth.response.send_message.assert_called_once()
        inter_unauth.response.send_modal.assert_not_called()

        # Author can stop -> triggers modal
        inter_auth = MagicMock()
        inter_auth.user.id = 123
        inter_auth.guild = MagicMock()
        inter_auth.client.is_owner = AsyncMock(return_value=False)
        inter_auth.response.send_modal = AsyncMock()

        await view.stop_button.callback(inter_auth)
        inter_auth.response.send_modal.assert_called_once()
        modal = inter_auth.response.send_modal.call_args[0][0]
        self.assertIsInstance(modal, ConfirmAbortModal)

    async def test_confirm_abort_modal_submission(self):
        mock_on_confirm = AsyncMock()
        modal = ConfirmAbortModal(on_confirm=mock_on_confirm)

        # Invalid text
        mock_inter_bad = MagicMock()
        mock_inter_bad.response.send_message = AsyncMock()
        modal.confirmation._value = "cancel"
        modal.reason._value = "testing"
        await modal.on_submit(mock_inter_bad)
        mock_inter_bad.response.send_message.assert_called_once()
        mock_on_confirm.assert_not_called()

        # Valid text ABORT
        mock_inter_ok = MagicMock()
        mock_inter_ok.response.send_message = AsyncMock()
        modal.confirmation._value = "ABORT"
        modal.reason._value = "test abort"
        await modal.on_submit(mock_inter_ok)
        mock_on_confirm.assert_called_once_with(mock_inter_ok, reason="test abort")


if __name__ == "__main__":
    unittest.main()
