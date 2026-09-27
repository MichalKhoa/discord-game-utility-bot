import unittest
from unittest.mock import MagicMock, AsyncMock

from cogs.player_manager import (
    PlayerManager,
    PlayerEditModal as CogPlayerEditModal,
    PlayerAddModal as CogPlayerAddModal,
    PlayerBatchAddModal as CogPlayerBatchAddModal,
    ConfirmActionView as CogConfirmActionView,
    PlayerListView as CogPlayerListView,
    FlaggedPlayersView as CogFlaggedPlayersView,
)
from cogs.code_redeem import CodeRedeem
from utils.modals import (
    SearchPlayerModal,
    PlayerEditModal as UtilPlayerEditModal,
    PlayerAddModal as UtilPlayerAddModal,
    PlayerBatchAddModal as UtilPlayerBatchAddModal,
)
from utils.embeds import PlayerStatsEmbed
from utils.views import (
    PlayerMenuButtons,
    ConfirmActionView as UtilConfirmActionView,
    PlayerListView as UtilPlayerListView,
    FlaggedPlayersView as UtilFlaggedPlayersView,
)


class TestPlayerSearchAndCallables(unittest.IsolatedAsyncioTestCase):
    async def test_search_player_and_modal(self):
        bot = MagicMock()
        pm = PlayerManager(bot)
        pm.db = MagicMock()
        pm.db.search_players = AsyncMock(return_value=[
            {"fid": "12345", "kid": "278", "name": "Arthur", "alliance": "NOR", "status": "ACTIVE", "warning_count": 0, "warning_reason": None}
        ])

        # Test search_player is directly callable
        self.assertTrue(callable(getattr(pm, "search_player", None)))
        mock_interaction = MagicMock()
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.defer = AsyncMock()
        mock_interaction.followup.send = AsyncMock()

        await pm.search_player(mock_interaction, "Arthur")
        mock_interaction.followup.send.assert_called_once()
        embed = mock_interaction.followup.send.call_args[1]["embed"]
        self.assertIn("Arthur", embed.fields[0].name)

        # Test SearchPlayerModal submission
        modal = SearchPlayerModal(pm)
        modal.query_input = MagicMock()
        modal.query_input.value = "Arthur"

        modal_interaction = MagicMock()
        modal_interaction.response.is_done.return_value = False
        modal_interaction.response.defer = AsyncMock()
        modal_interaction.followup.send = AsyncMock()

        await modal.on_submit(modal_interaction)
        modal_interaction.followup.send.assert_called_once()

    async def test_all_ui_cog_methods_are_callable(self):
        bot = MagicMock()
        pm = PlayerManager(bot)
        cr = CodeRedeem(bot)

        self.assertTrue(callable(getattr(pm, "search_player", None)))
        self.assertTrue(callable(getattr(pm, "do_search_player", None)))
        self.assertTrue(callable(getattr(pm, "player_stats", None)))
        self.assertTrue(callable(getattr(pm, "export_csv_cmd", None)))
        self.assertTrue(callable(getattr(pm, "sync_doc_cmd", None)))
        self.assertTrue(callable(getattr(cr, "redeem_history", None)))

    async def test_player_stats_embed_and_button(self):
        # 1. Empty stats embed
        empty_embed = PlayerStatsEmbed({"total": 0})
        self.assertIn("No players registered", empty_embed.description)

        # 2. Populated stats embed
        sample_stats = {
            "total": 10,
            "active": 8,
            "flagged": 1,
            "disabled": 1,
            "kingdoms": [{"kid": "278", "count": 10}],
            "alliances": [{"alliance": "NOR", "count": 7}, {"alliance": "OvO", "count": 3}]
        }
        pop_embed = PlayerStatsEmbed(sample_stats)
        self.assertEqual(len(pop_embed.fields), 5)
        self.assertIn("10", pop_embed.fields[0].value)

        # 3. PlayerMenuButtons stats_btn callback
        bot = MagicMock()
        view = PlayerMenuButtons(bot)
        view.db = MagicMock()
        view.db.get_stats = AsyncMock(return_value=sample_stats)

        mock_inter = MagicMock()
        mock_inter.response.is_done.return_value = False
        mock_inter.response.defer = AsyncMock()
        mock_inter.followup.send = AsyncMock()

        # Call stats_btn callback
        await view.stats_btn.callback(mock_inter)
        mock_inter.response.defer.assert_called_once_with(ephemeral=True)
        mock_inter.followup.send.assert_called_once()
        sent_embed = mock_inter.followup.send.call_args[1]["embed"]
        self.assertIsInstance(sent_embed, PlayerStatsEmbed)
        self.assertIn("10", sent_embed.fields[0].value)

    def test_ui_component_extraction_and_reexports(self):
        self.assertIs(CogPlayerEditModal, UtilPlayerEditModal)
        self.assertIs(CogPlayerAddModal, UtilPlayerAddModal)
        self.assertIs(CogPlayerBatchAddModal, UtilPlayerBatchAddModal)
        self.assertIs(CogConfirmActionView, UtilConfirmActionView)
        self.assertIs(CogPlayerListView, UtilPlayerListView)
        self.assertIs(CogFlaggedPlayersView, UtilFlaggedPlayersView)


TestPlayerManagerCog = TestPlayerSearchAndCallables


if __name__ == "__main__":
    unittest.main()
