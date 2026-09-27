import asyncio
import io
import math
import os
from typing import Optional, List, Dict, Any, Union, TYPE_CHECKING

import aiosqlite
import discord
from discord.ext import commands

from databases.player_database import PlayerDatabase
from utils import google_sync
from utils.embeds import MainMenuEmbed, PlayerStatsEmbed
from utils.modals import (
    PlayerAddModal,
    PlayerBatchAddModal,
    SearchPlayerModal,
)

if TYPE_CHECKING:
    from cogs.player_manager import PlayerManager
    from cogs.backup_sync import BackupSyncCog
    from utils.views import MenuButtons

__all__ = [
    "ConfirmActionView",
    "PlayerListView",
    "FlaggedPlayersView",
    "PlayerMenuButtons",
    "ImportDataView",
    "GoogleSheetMenuButtons",
    "SheetPruneConfirmView",
]


class ConfirmActionView(discord.ui.View):
    def __init__(self, author_id: int, on_confirm, prompt: str = "Proceed with this batch action?"):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.on_confirm = on_confirm
        self.prompt = prompt

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This confirmation is only for the command author.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await self.on_confirm(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Action cancelled.", embed=None, view=self)


class PlayerListView(discord.ui.View):
    def __init__(self, db: PlayerDatabase, players: List[dict], alliance_filter: Optional[str] = None, page: int = 0):
        super().__init__(timeout=1800)
        self.db = db
        self.all_players = players
        self.players = players
        self.alliance_filter = alliance_filter
        self.page = page
        self.per_page = 15
        self.max_pages = max(1, (len(players) + self.per_page - 1) // self.per_page)
        self._build_filter_dropdown()
        self.update_buttons()

    def _build_filter_dropdown(self):
        # Extract unique alliances from roster
        alliances = sorted({p["alliance"].strip().upper() for p in self.all_players if p.get("alliance") and p["alliance"].strip()})

        options = [
            discord.SelectOption(label="All Players", value="ALL", emoji="🌐", description=f"Total {len(self.all_players)} registered players"),
            discord.SelectOption(label="Active Only", value="STATUS_ACTIVE", emoji="🟢", description="Accounts in good standing"),
            discord.SelectOption(label="Flagged Only", value="STATUS_FLAGGED", emoji="🟡", description="Accounts with warnings or errors"),
            discord.SelectOption(label="Disabled Only", value="STATUS_DISABLED", emoji="🔴", description="Inactive or disabled accounts"),
        ]

        for a in alliances[:18]:
            count = sum(1 for p in self.all_players if (p.get("alliance") or "").strip().upper() == a)
            options.append(discord.SelectOption(label=f"Alliance [{a}]", value=f"ALLIANCE_{a}", emoji="🛡️", description=f"{count} member(s)"))

        if len(options) > 1:
            select = discord.ui.Select(
                placeholder="🔍 Filter by Alliance or Status...",
                options=options,
                row=0,
                custom_id="select_player_filter"
            )
            select.callback = self.filter_callback
            self.add_item(select)

    async def filter_callback(self, interaction: discord.Interaction):
        selected = interaction.data["values"][0]
        if selected == "ALL":
            self.players = self.all_players
            self.alliance_filter = None
        elif selected == "STATUS_ACTIVE":
            self.players = [p for p in self.all_players if p.get("status", "ACTIVE") == "ACTIVE" and p.get("warning_count", 0) == 0]
            self.alliance_filter = "Active Only"
        elif selected == "STATUS_FLAGGED":
            self.players = [p for p in self.all_players if (p.get("status") == "FLAGGED" or p.get("warning_count", 0) > 0) and p.get("status") != "DISABLED"]
            self.alliance_filter = "Flagged Only"
        elif selected == "STATUS_DISABLED":
            self.players = [p for p in self.all_players if p.get("status") == "DISABLED"]
            self.alliance_filter = "Disabled Only"
        elif selected.startswith("ALLIANCE_"):
            tag = selected[len("ALLIANCE_"):]
            self.players = [p for p in self.all_players if (p.get("alliance") or "").strip().upper() == tag]
            self.alliance_filter = f"Alliance [{tag}]"

        self.page = 0
        self.max_pages = max(1, (len(self.players) + self.per_page - 1) // self.per_page)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    def update_buttons(self):
        self.prev_btn.disabled = (self.page <= 0)
        self.next_btn.disabled = (self.page >= self.max_pages - 1)

    def get_embed(self) -> discord.Embed:
        start_idx = self.page * self.per_page
        end_idx = min(start_idx + self.per_page, len(self.players))
        page_items = self.players[start_idx:end_idx]

        filter_str = f" • Filter: `{self.alliance_filter}`" if self.alliance_filter else ""
        embed = discord.Embed(
            title=f"📋 Registered Players ({len(self.players)} shown / {len(self.all_players)} total){filter_str}",
            colour=discord.Colour.blurple()
        )

        if not page_items:
            embed.description = "No players found matching this criteria."
            return embed

        lines = []
        for i, p in enumerate(page_items, start=start_idx + 1):
            name = p.get("name") or "Unknown"
            fid = p.get("fid")
            kid = p.get("kid", "278")
            alliance = f"[{p.get('alliance')}] " if p.get("alliance") else ""
            status = p.get("status", "ACTIVE")

            if status == "DISABLED":
                badge = "🔴"
            elif status == "FLAGGED" or (p.get("warning_count", 0) > 0):
                badge = "🟡"
            else:
                badge = "🟢"

            lines.append(f"`{i:2d}.` {badge} {alliance}**{name}** — FID: `{fid}` (K{kid})")

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Page {self.page + 1} of {self.max_pages} • 🟢 Active | 🟡 Flagged | 🔴 Disabled")
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="btn_prev", row=1)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="btn_next", row=1)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="btn_player_refresh", row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.all_players = await self.db.get_all_players()
        self.players = self.all_players
        self.alliance_filter = None
        self.page = 0
        self.max_pages = max(1, (len(self.players) + self.per_page - 1) // self.per_page)
        self.update_buttons()
        await interaction.edit_original_response(embed=self.get_embed(), view=self)


class FlaggedPlayersView(discord.ui.View):
    def __init__(self, db: PlayerDatabase, players: List[dict], page: int = 0):
        super().__init__(timeout=1800)
        self.db = db
        self.players = players
        self.page = page
        self.per_page = 8
        self.max_pages = max(1, (len(players) + self.per_page - 1) // self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = (self.page <= 0)
        self.next_btn.disabled = (self.page >= self.max_pages - 1)

    def get_embed(self) -> discord.Embed:
        start_idx = self.page * self.per_page
        end_idx = min(start_idx + self.per_page, len(self.players))
        page_items = self.players[start_idx:end_idx]

        embed = discord.Embed(
            title=f"⚠️ Flagged / Problematic Players ({len(self.players)} total)",
            colour=discord.Colour.orange()
        )

        if not page_items:
            embed.description = "✅ No players are currently flagged or disabled."
            return embed

        lines = []
        for i, p in enumerate(page_items, start=start_idx + 1):
            name = p.get("name") or "Unknown"
            fid = p.get("fid")
            kid = p.get("kid", "278")
            status = p.get("status", "FLAGGED")
            badge = "🔴" if status == "DISABLED" else "🟡"
            reason = p.get("warning_reason") or "Verification failed / API redemption error"
            if len(reason) > 100:
                reason = reason[:97] + "..."
            strikes = p.get("warning_count", 0)
            lines.append(
                f"`{i:2d}.` {badge} **{name}** (`{fid}` | K{kid}) — `{strikes} strikes`\n> ⚠️ *{reason}*"
            )

        embed.description = "\n\n".join(lines)
        embed.set_footer(
            text=f"Page {self.page + 1} of {self.max_pages} • 🟡 Flagged | 🔴 Disabled • Use /player unflag to restore"
        )
        return embed

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="btn_flagged_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="btn_flagged_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="btn_flagged_refresh")
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.players = await self.db.get_flagged_players()
        self.max_pages = max(1, (len(self.players) + self.per_page - 1) // self.per_page)
        if self.page >= self.max_pages:
            self.page = max(0, self.max_pages - 1)
        self.update_buttons()
        await interaction.edit_original_response(embed=self.get_embed(), view=self)


class PlayerMenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot
        self.db = PlayerDatabase()

    @discord.ui.button(label="Player List", style=discord.ButtonStyle.primary, emoji="📋", row=0)
    async def view_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        players = await self.db.get_all_players()
        if not players:
            await interaction.followup.send("⚠️ No registered players found in database.", ephemeral=True)
            return
        view = PlayerListView(self.db, players)
        await interaction.followup.send(embed=view.get_embed(), view=view, ephemeral=True)

    @discord.ui.button(label="Add Player", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def add_player_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerAddModal(self.db))

    @discord.ui.button(label="Flagged", style=discord.ButtonStyle.danger, emoji="⚠️", row=0)
    async def flagged_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        flagged = await self.db.get_flagged_players()
        if not flagged:
            embed = discord.Embed(
                title="✅ Flagged Players",
                description="No players are currently flagged or disabled. All registered accounts are active and in good standing.",
                colour=discord.Colour.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        view = FlaggedPlayersView(self.db, flagged)
        await interaction.followup.send(embed=view.get_embed(), view=view, ephemeral=True)

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.secondary, emoji="📊", row=0)
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        try:
            stats = await self.db.get_stats()
            embed = PlayerStatsEmbed(stats)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching player statistics: `{e}`", ephemeral=True)

    @discord.ui.button(label="Import / Export", style=discord.ButtonStyle.primary, emoji="📥", row=1)
    async def import_export_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📥 Player Import & Export",
            description="Import multiple player accounts or export current database records.",
            colour=discord.Colour.teal()
        )
        embed.add_field(
            name="📝 Batch Paste",
            value="> Paste text lines with format `FID [Kingdom] [Name]`.",
            inline=False
        )
        embed.add_field(
            name="📁 Upload File",
            value="> Upload a `.csv` or `.txt` player list file.",
            inline=False
        )
        embed.add_field(
            name="📥 Export CSV",
            value="> Download all registered accounts as a CSV spreadsheet.",
            inline=False
        )
        await interaction.response.edit_message(embed=embed, view=ImportDataView(self.bot))

    @discord.ui.button(label="Search / Edit", style=discord.ButtonStyle.secondary, emoji="🔍", row=1)
    async def search_player_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pm_cog = self.bot.get_cog("PlayerManager")
        if pm_cog:
            await interaction.response.send_modal(SearchPlayerModal(pm_cog))
        else:
            await interaction.response.send_message("PlayerManager module error", ephemeral=True)

    @discord.ui.button(label="Google Sheets", style=discord.ButtonStyle.success, emoji="📊", row=1)
    async def sheet_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📊 Google Sheets & Database Backup",
            description="Sync player rosters with Google Sheets/Docs and manage database backups.",
            colour=discord.Colour.green()
        )
        embed.add_field(
            name="📤 Export to Sheet",
            value="> Overwrites Google Sheet with current player database.",
            inline=False
        )
        embed.add_field(
            name="📥 Pull from Sheet",
            value="> Reads edits from Google Sheet and updates database.",
            inline=False
        )
        embed.add_field(
            name="📄 Sync Google Doc",
            value="> Imports raw player list from Google Doc URL.",
            inline=False
        )
        embed.add_field(
            name="💾 Backup DB Now",
            value="> Creates instant SQLite snapshot and posts to backup channel.",
            inline=False
        )
        await interaction.response.edit_message(embed=embed, view=GoogleSheetMenuButtons(self.bot))

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary, emoji="◀", row=1)
    async def return_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from utils.views import MenuButtons
        embed = MainMenuEmbed(self.bot)
        view = MenuButtons(self.bot)
        await interaction.response.edit_message(embed=embed, view=view)


class ImportDataView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot
        self.db = PlayerDatabase()

    @discord.ui.button(label="Batch Paste", style=discord.ButtonStyle.success, emoji="📝", row=0)
    async def batch_import_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerBatchAddModal(self.db))

    @discord.ui.button(label="Upload File", style=discord.ButtonStyle.success, emoji="📁", row=0)
    async def import_file_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📁 **Ready for file upload!**\nPlease attach and send your `.csv` or `.txt` file in this channel within 60 seconds (or use `/player import`).",
            ephemeral=True
        )

        def check(m: discord.Message):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel_id and len(m.attachments) > 0

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            return

        file = msg.attachments[0]
        if not (file.filename.endswith(".csv") or file.filename.endswith(".txt")):
            await interaction.followup.send("❌ Uploaded file must be a `.csv` or `.txt` file.", ephemeral=True)
            return

        try:
            content_bytes = await file.read()
            content = content_bytes.decode("utf-8", errors="replace")
            players = self.db.parse_raw_player_text(content, default_kingdom="278")
            if not players:
                await interaction.followup.send("❌ No valid player IDs found in the file.", ephemeral=True)
                return

            imported_count = await self.db.bulk_upsert_players(players)
            alliances = {p.get("alliance") for p in players if p.get("alliance")}
            alliance_summary = f" across **{len(alliances)}** alliance(s)" if alliances else ""

            embed = discord.Embed(
                title="✅ File Import Complete",
                description=f"Successfully imported/updated **{imported_count}** player ID(s){alliance_summary} from `{file.filename}`.",
                colour=discord.Colour.green()
            )
            if alliances:
                embed.add_field(name="Alliances Included", value=", ".join(f"`{a}`" for a in sorted(alliances)[:10]), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error processing file: `{e}`", ephemeral=True)

    @discord.ui.button(label="Export CSV", style=discord.ButtonStyle.secondary, emoji="📥", row=0)
    async def export_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        pm_cog = self.bot.get_cog("PlayerManager")
        if pm_cog and hasattr(pm_cog, "do_export_csv"):
            await pm_cog.do_export_csv(interaction)
        elif pm_cog and callable(getattr(pm_cog, "export_csv_cmd", None)):
            await pm_cog.export_csv_cmd(interaction)
        else:
            try:
                db = PlayerDatabase()
                csv_data = await db.export_csv()
                file = discord.File(io.BytesIO(csv_data.encode('utf-8')), filename="player_ids.csv")
                await interaction.followup.send("📥 Here is the current player export:", file=file, ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Failed to export CSV: `{e}`", ephemeral=True)

    @discord.ui.button(label="Return to Players", style=discord.ButtonStyle.secondary, emoji="◀", row=1)
    async def return_to_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        player_menu_panel = discord.Embed(
            title="👥 Player Registry & Management",
            description="Manage game player accounts, kingdom IDs, and warning flags.",
            colour=discord.Colour.teal()
        )
        player_menu_panel.add_field(
            name="📋 View List & ⚠️ Flagged",
            value="> Browse active player accounts, warning strikes, and stats.",
            inline=False
        )
        player_menu_panel.add_field(
            name="➕ Add / 🔍 Search / 📥 Import & Export",
            value="> Register accounts, edit profiles, batch import, or export data.",
            inline=False
        )
        player_menu_panel.add_field(
            name="📊 Google Sheets & Cloud Backup",
            value="> Sync rosters with Google Sheets and manage backups.",
            inline=False
        )
        await interaction.response.edit_message(embed=player_menu_panel, view=PlayerMenuButtons(self.bot))


class GoogleSheetMenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="Export to Sheet", style=discord.ButtonStyle.success, emoji="📤", row=0)
    async def export_sheet_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)
        cog = self.bot.get_cog("BackupSyncCog")
        if cog:
            await cog.do_export_sheet(interaction)
        else:
            await interaction.followup.send("❌ `BackupSync` module not loaded. Check bot logs.", ephemeral=True)

    @discord.ui.button(label="Pull from Sheet", style=discord.ButtonStyle.primary, emoji="📥", row=0)
    async def pull_sheet_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)
        cog = self.bot.get_cog("BackupSyncCog")
        if cog:
            await cog.do_pull_sheet(interaction)
        else:
            await interaction.followup.send("❌ `BackupSync` module not loaded. Check bot logs.", ephemeral=True)

    @discord.ui.button(label="Sync Google Doc", style=discord.ButtonStyle.secondary, emoji="📄", row=0)
    async def sync_doc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)
        pm_cog = self.bot.get_cog("PlayerManager")
        if pm_cog:
            await pm_cog.sync_doc_cmd(interaction)
        else:
            await interaction.followup.send("❌ `PlayerManager` module not loaded.", ephemeral=True)

    @discord.ui.button(label="Backup DB Now", style=discord.ButtonStyle.primary, emoji="💾", row=1)
    async def backup_now_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)
        cog = self.bot.get_cog("BackupSyncCog")
        if cog:
            await cog.do_backup_now(interaction)
        else:
            await interaction.followup.send("❌ `BackupSync` module not loaded. Check bot logs.", ephemeral=True)

    @discord.ui.button(label="Sheet Status", style=discord.ButtonStyle.secondary, emoji="🔗", row=1)
    async def sheet_status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        cog = self.bot.get_cog("BackupSyncCog")
        if cog:
            await cog.do_sheet_status(interaction)
        else:
            await interaction.followup.send("❌ `BackupSync` module not loaded. Check bot logs.", ephemeral=True)

    @discord.ui.button(label="Return to Players", style=discord.ButtonStyle.secondary, emoji="◀", row=2)
    async def return_to_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        player_menu_panel = discord.Embed(
            title="👥 Player Registry & Management",
            description="Manage game player accounts, kingdom IDs, and warning flags.",
            colour=discord.Colour.teal()
        )
        player_menu_panel.add_field(
            name="📋 Player List & ⚠️ Flagged",
            value="> Browse active player accounts, review warning strikes, and view stats.",
            inline=False
        )
        player_menu_panel.add_field(
            name="➕ Add / 🔍 Search / 📥 Import & Export",
            value="> Register accounts, edit profiles, batch paste, file import, or CSV export.",
            inline=False
        )
        player_menu_panel.add_field(
            name="📊 Google Sheets & Cloud Backup",
            value="> Sync rosters with Google Sheets and manage backups.",
            inline=False
        )
        await interaction.response.edit_message(embed=player_menu_panel, view=PlayerMenuButtons(self.bot))


class SheetPruneConfirmView(discord.ui.View):
    """Interactive confirmation view for pruning missing IDs during Google Sheet pull."""

    def __init__(
        self,
        cog: "BackupSyncCog",
        user_id: int,
        missing_fids: List[str],
        valid_players: List[Dict[str, Any]],
        skipped_rows: List[Dict[str, Any]],
        sheet_title: str,
        sheet_url: str
    ):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.user_id = user_id
        self.missing_fids = missing_fids
        self.valid_players = valid_players
        self.skipped_rows = skipped_rows
        self.sheet_title = sheet_title
        self.sheet_url = sheet_url
        self.message: Optional[Union[discord.Message, discord.WebhookMessage]] = None

    @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command invoker can confirm this action.", ephemeral=True)
            return

        await interaction.response.defer()
        for child in self.children:
            child.disabled = True

        try:
            # ponytail: single local backup before destructive prune; cloud drive upload handled by daily task
            backup_file = await asyncio.to_thread(google_sync.create_local_backup, self.cog.db.db_path)
            google_sync.cleanup_local_backups()
            backup_name = os.path.basename(backup_file)

            deleted_count = await self.cog.db.batch_delete_players(fids=self.missing_fids)
            synced_count = await self.cog.db.bulk_upsert_players(self.valid_players)

            embed = discord.Embed(
                title="🗑️ Google Sheet Prune & Sync Complete",
                description=f"Pruned missing records and synchronized with [{self.sheet_title}]({self.sheet_url}).",
                color=discord.Color.green()
            )
            embed.add_field(name="🗑️ Players Deleted", value=str(deleted_count), inline=True)
            embed.add_field(name="🔄 Players Synced", value=str(synced_count), inline=True)
            embed.add_field(name="⚠️ Invalid Rows Skipped", value=str(len(self.skipped_rows)), inline=True)
            embed.add_field(name="💾 Safety Backup Snapshot", value=f"`{backup_name}` (saved to `data/backups/`)", inline=False)
            embed.set_footer(text="Database updated. Run /player list to view current roster.")

            if self.message:
                await self.message.edit(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        except Exception as e:
            err_msg = f"❌ Error during prune operation: {e}"
            if self.message:
                await self.message.edit(content=err_msg, view=None)
            else:
                await interaction.followup.send(err_msg, ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command invoker can cancel this action.", ephemeral=True)
            return

        await interaction.response.defer()
        for child in self.children:
            child.disabled = True

        try:
            synced_count = await self.cog.db.bulk_upsert_players(self.valid_players)
            embed = discord.Embed(
                title="🛡️ Pruning Cancelled (Safe Sync Applied)",
                description=f"No players were deleted. Synchronized **{synced_count}** player(s) from [{self.sheet_title}]({self.sheet_url}).",
                color=discord.Color.blue()
            )
            embed.add_field(name="Synced Players", value=str(synced_count), inline=True)
            embed.add_field(name="Kept in DB (Not in Sheet)", value=str(len(self.missing_fids)), inline=True)
            embed.set_footer(text="Existing database records were preserved.")

            if self.message:
                await self.message.edit(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        except Exception as e:
            err_msg = f"❌ Error during sync: {e}"
            if self.message:
                await self.message.edit(content=err_msg, view=None)
            else:
                await interaction.followup.send(err_msg, ephemeral=True)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
