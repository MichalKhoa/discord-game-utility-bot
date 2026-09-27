import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import aiohttp
import io
from typing import Optional, List

from databases.player_database import PlayerDatabase
import utils.redeem_code
from utils.embeds import PlayerStatsEmbed
from utils.modals import (
    PlayerEditModal,
    PlayerAddModal,
    PlayerBatchAddModal,
)
from utils.views import (
    ConfirmActionView,
    PlayerListView,
    FlaggedPlayersView,
)

__all__ = [
    "PlayerEditModal",
    "PlayerAddModal",
    "PlayerBatchAddModal",
    "ConfirmActionView",
    "PlayerListView",
    "FlaggedPlayersView",
    "PlayerManager",
    "setup",
]


class PlayerManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = getattr(bot, "player_db", None) or PlayerDatabase()

    player_group = app_commands.Group(name="player", description="Manage game player IDs and kingdoms")

    async def player_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for player name or FID."""
        players = await self.db.search_players(current, limit=25)
        choices = []
        for p in players:
            name = p.get("name") or "NoName"
            fid = p.get("fid")
            kid = p.get("kid", "278")
            alliance = f"[{p.get('alliance')}] " if p.get("alliance") else ""
            label = f"{alliance}{name} ({fid} - K{kid})"[:100]
            choices.append(app_commands.Choice(name=label, value=fid))
        return choices

    @player_group.command(name="list", description="View all registered players with pagination and alliance filters")
    @app_commands.describe(
        alliance="Filter by alliance tag (e.g. NOR, OvO, RKF)",
        kingdom="Filter by kingdom ID (e.g. 278, 305)",
        status="Filter by status (ACTIVE, FLAGGED, DISABLED)"
    )
    async def list_players(
        self,
        interaction: discord.Interaction,
        alliance: Optional[str] = None,
        kingdom: Optional[str] = None,
        status: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        players = await self.db.get_all_players(status=status, alliance=alliance, kingdom=kingdom)
        if not players:
            await interaction.followup.send("⚠️ No players found matching the given filters.", ephemeral=True)
            return

        view = PlayerListView(self.db, players, alliance_filter=alliance)
        await interaction.followup.send(embed=view.get_embed(), view=view, ephemeral=True)

    @player_group.command(name="edit", description="Edit any player ID, Kingdom, Name, or Alliance with live verification")
    @app_commands.describe(player="Search by Player Name or FID to edit")
    @app_commands.autocomplete(player=player_autocomplete)
    async def edit_player(self, interaction: discord.Interaction, player: str):
        player_data = await self.db.get_player(player)
        if not player_data:
            # Fallback search by query
            results = await self.db.search_players(player, limit=1)
            if results:
                player_data = results[0]

        if not player_data:
            await interaction.response.send_message(f"❌ Player `{player}` not found.", ephemeral=True)
            return

        modal = PlayerEditModal(self.db, player_data)
        await interaction.response.send_modal(modal)

    @player_group.command(name="add", description="Add a new player ID with real-time API verification")
    async def add_player(self, interaction: discord.Interaction):
        modal = PlayerAddModal(self.db)
        await interaction.response.send_modal(modal)

    async def do_search_player(self, interaction: discord.Interaction, query: str):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        results = await self.db.search_players(query, limit=10)
        if not results:
            await interaction.followup.send(f"⚠️ No players found matching `{query}`.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🔍 Search Results for '{query[:50]}'", colour=discord.Colour.og_blurple())
        for p in results:
            status = p.get("status", "ACTIVE")
            badge = "🟢" if status == "ACTIVE" else ("🟡" if status == "FLAGGED" else "🔴")
            warning = f"\n⚠️ Reason: `{p.get('warning_reason')}`" if p.get("warning_reason") else ""
            name_val = f"{badge} {p.get('name') or 'Unknown'} ({p.get('alliance') or 'No Alliance'})"[:256]
            info_val = f"• FID: `{p.get('fid')}`\n• Kingdom: `K{p.get('kid')}`\n• Status: `{status}` ({p.get('warning_count', 0)} strikes){warning}"[:1024]
            embed.add_field(
                name=name_val,
                value=info_val,
                inline=False
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @player_group.command(name="search", description="Search for a player by FID, Name, or Alliance")
    @app_commands.describe(query="Name, FID, or Alliance to search")
    async def search_player_cmd(self, interaction: discord.Interaction, query: str):
        await self.do_search_player(interaction, query)

    async def search_player(self, interaction: discord.Interaction, query: str):
        """Callable helper for modals and UI views."""
        await self.do_search_player(interaction, query)

    @player_group.command(name="flagged", description="View all flagged and disabled players needing attention")
    async def flagged_players(self, interaction: discord.Interaction):
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

    @player_group.command(name="unflag", description="Clear strikes and restore player to ACTIVE status")
    @app_commands.describe(player="Search by Player Name or FID to unflag")
    @app_commands.autocomplete(player=player_autocomplete)
    async def unflag_player_cmd(self, interaction: discord.Interaction, player: str):
        success = await self.db.unflag_player(player)
        if success:
            await interaction.response.send_message(f"✅ Cleared warnings for FID `{player}`. Status reset to 🟢 **ACTIVE**.")
        else:
            await interaction.response.send_message(f"❌ Player `{player}` not found.", ephemeral=True)

    @player_group.command(name="prune-flagged", description="Remove dead or disabled player IDs exceeding strike limit")
    @app_commands.describe(min_strikes="Minimum number of strikes to prune (default: 3)")
    async def prune_flagged_cmd(self, interaction: discord.Interaction, min_strikes: int = 3):
        await interaction.response.defer(ephemeral=True)
        deleted_count = await self.db.prune_flagged(min_strikes=min_strikes)
        await interaction.followup.send(f"🧹 Pruned **{deleted_count}** player(s) with ≥ {min_strikes} strikes / DISABLED status.", ephemeral=True)

    async def do_player_stats(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        try:
            stats = await self.db.get_stats()
            embed = PlayerStatsEmbed(stats)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching player statistics: `{e}`", ephemeral=True)

    @player_group.command(name="stats", description="View total player statistics and kingdom breakdown")
    async def player_stats_cmd(self, interaction: discord.Interaction):
        await self.do_player_stats(interaction)

    async def player_stats(self, interaction: discord.Interaction):
        """Callable helper for UI views."""
        await self.do_player_stats(interaction)

    async def do_export_csv(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        csv_data = await self.db.export_csv()
        file = discord.File(io.BytesIO(csv_data.encode('utf-8')), filename="player_ids.csv")
        await interaction.followup.send("📥 Here is the current player export:", file=file, ephemeral=True)

    @player_group.command(name="export", description="Export all player IDs as a CSV spreadsheet")
    async def export_player_csv_cmd(self, interaction: discord.Interaction):
        await self.do_export_csv(interaction)

    async def export_csv_cmd(self, interaction: discord.Interaction):
        """Callable helper for UI views."""
        await self.do_export_csv(interaction)

    @player_group.command(name="import", description="Import players from an attached CSV or text file")
    @app_commands.describe(
        file="CSV or TXT file to import",
        default_kingdom="Default Kingdom ID for entries without KID (default: 278)"
    )
    async def import_file_cmd(self, interaction: discord.Interaction, file: discord.Attachment, default_kingdom: Optional[str] = "278"):
        if not (file.filename.endswith(".csv") or file.filename.endswith(".txt")):
            await interaction.response.send_message("❌ Please upload a `.csv` or `.txt` file.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8", errors="replace")

        default_kid = str(default_kingdom or "278").strip()
        players = self.db.parse_raw_player_text(content, default_kingdom=default_kid)
        if not players:
            await interaction.followup.send("❌ No valid player IDs found in the uploaded file.", ephemeral=True)
            return

        imported_count = await self.db.bulk_upsert_players(players)
        alliances = {p.get("alliance") for p in players if p.get("alliance")}
        alliance_summary = f" across **{len(alliances)}** alliance(s)" if alliances else ""

        embed = discord.Embed(
            title="✅ File Import Complete",
            description=f"Successfully imported/updated **{imported_count}** player ID(s){alliance_summary}.",
            colour=discord.Colour.green()
        )
        if alliances:
            embed.add_field(name="Alliances Included", value=", ".join(f"`{a}`" for a in sorted(alliances)[:10]), inline=False)
        embed.set_footer(text="Use /player sync-names to populate in-game nicknames and verify accounts.")
        await interaction.followup.send(embed=embed)

    @player_group.command(name="batch-add", description="Paste multi-line player IDs and alliances into the registry")
    @app_commands.describe(
        text="Optional: direct multi-line text (e.g. # ALLIANCE\\nFID KID Name). If empty, opens paste modal",
        default_kingdom="Default Kingdom ID for entries without KID (default: 278)"
    )
    async def batch_add_cmd(self, interaction: discord.Interaction, text: Optional[str] = None, default_kingdom: Optional[str] = "278"):
        if text:
            await interaction.response.defer(thinking=True)
            default_kid = str(default_kingdom or "278").strip()
            players = self.db.parse_raw_player_text(text, default_kingdom=default_kid)
            if not players:
                await interaction.followup.send("❌ No valid player IDs found in the submitted text.", ephemeral=True)
                return
            imported_count = await self.db.bulk_upsert_players(players)
            alliances = {p.get("alliance") for p in players if p.get("alliance")}
            alliance_summary = f" across **{len(alliances)}** alliance(s)" if alliances else ""
            embed = discord.Embed(
                title="✅ Batch Players Added / Updated",
                description=f"Successfully processed **{imported_count}** player ID(s){alliance_summary}.",
                colour=discord.Colour.green()
            )
            if alliances:
                embed.add_field(name="Alliances Included", value=", ".join(f"`{a}`" for a in sorted(alliances)[:10]), inline=False)
            embed.set_footer(text="Use /player sync-names to populate in-game names and verify accounts.")
            await interaction.followup.send(embed=embed)
        else:
            modal = PlayerBatchAddModal(self.db)
            if default_kingdom:
                modal.default_kid_input.default = str(default_kingdom).strip()
            await interaction.response.send_modal(modal)

    async def do_sync_doc(self, interaction: discord.Interaction, doc_id_or_url: Optional[str] = None, default_kingdom: Optional[str] = "278"):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)
        default_kid = str(default_kingdom or "278").strip()

        target = (doc_id_or_url or "13qeSSMJH3S4ArPj8B3SJ31UajjS5wIqmt8MYYTvBWhE").strip()
        if target.startswith("http://") or target.startswith("https://"):
            if "docs.google.com/document/d/" in target:
                try:
                    target_id = target.split("/d/")[1].split("/")[0]
                    url = f"https://docs.google.com/document/d/{target_id}/export?format=txt"
                except Exception:
                    url = target
            else:
                url = target
        else:
            url = f"https://docs.google.com/document/d/{target}/export?format=txt"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"❌ Failed to fetch document. HTTP Status: `{resp.status}`", ephemeral=True)
                        return
                    content = await resp.text()
        except Exception as e:
            await interaction.followup.send(f"❌ Error downloading document: `{e}`", ephemeral=True)
            return

        players = self.db.parse_raw_player_text(content, default_kingdom=default_kid)
        if not players:
            await interaction.followup.send("⚠️ Document downloaded, but no valid player IDs were found in the content.", ephemeral=True)
            return

        imported_count = await self.db.bulk_upsert_players(players)
        alliances = {p.get("alliance") for p in players if p.get("alliance")}

        embed = discord.Embed(
            title="🔄 Google Doc / Remote Sync Complete",
            colour=discord.Colour.green()
        )
        embed.add_field(name="Source", value=f"`{target[:40]}`", inline=True)
        embed.add_field(name="Players Synced", value=str(imported_count), inline=True)
        embed.add_field(name="Alliances Found", value=str(len(alliances)), inline=True)
        if alliances:
            embed.add_field(name="Alliances", value=", ".join(f"`{a}`" for a in sorted(alliances)[:15]), inline=False)
        embed.set_footer(text="Database successfully updated from remote document.")
        await interaction.followup.send(embed=embed)

    @player_group.command(name="sync-doc", description="Sync player list directly from a public Google Doc or text URL")
    @app_commands.describe(
        doc_id_or_url="Google Doc ID or public plain text URL (leave empty to use default Doc ID)",
        default_kingdom="Default Kingdom ID (default: 278)"
    )
    async def sync_doc_app_cmd(self, interaction: discord.Interaction, doc_id_or_url: Optional[str] = None, default_kingdom: Optional[str] = "278"):
        await self.do_sync_doc(interaction, doc_id_or_url, default_kingdom)

    async def sync_doc_cmd(self, interaction: discord.Interaction, doc_id_or_url: Optional[str] = None, default_kingdom: Optional[str] = "278"):
        """Callable helper for UI views."""
        await self.do_sync_doc(interaction, doc_id_or_url, default_kingdom)

    @player_group.command(name="sync-names", description="Auto-sync in-game nicknames and kingdoms concurrently from Century Games API")
    @app_commands.describe(
        alliance="Optional: only sync players in this alliance",
        concurrency="Number of parallel API requests (default: 8, max: 15)"
    )
    async def sync_names_cmd(self, interaction: discord.Interaction, alliance: Optional[str] = None, concurrency: Optional[int] = 8):
        await interaction.response.defer(thinking=True)

        if alliance:
            players = await self.db.get_all_players(alliance=alliance)
        else:
            players = await self.db.get_active_players()

        if not players:
            await interaction.followup.send("❌ No players found to sync.", ephemeral=True)
            return

        total = len(players)
        concurrency_limit = max(1, min(concurrency or 8, 15))
        sem = asyncio.Semaphore(concurrency_limit)

        status_msg = await interaction.followup.send(f"🔄 Syncing {total} player names with {concurrency_limit} concurrent workers... (0%)")

        completed = 0
        updated = 0
        unchanged = 0
        failed = 0
        changes_log = []
        lock = asyncio.Lock()

        async def worker(player_dict: dict):
            nonlocal completed, updated, unchanged, failed
            fid = str(player_dict.get("fid", "")).strip()
            current_name = str(player_dict.get("name", "")).strip()
            current_kid = str(player_dict.get("kid", "278")).strip()

            async with sem:
                info = await discord.utils.maybe_coroutine(
                    utils.redeem_code.fetch_player_info, fid, current_kid
                )

            async with lock:
                completed += 1
                if info.get("success"):
                    new_name = info.get("nickname", "").strip()
                    new_kid = info.get("kid", current_kid).strip()

                    if new_name and (new_name != current_name or new_kid != current_kid):
                        await self.db.update_player_name_and_kid(fid, new_name, new_kid)
                        updated += 1
                        changes_log.append(f"`{fid}`: `{current_name or 'N/A'}` ➔ **{new_name}** (K{new_kid})")
                    else:
                        unchanged += 1
                else:
                    failed += 1

                if completed % 15 == 0 or completed == total:
                    percent = int((completed / total) * 100)
                    try:
                        await status_msg.edit(content=f"🔄 Syncing player names... **{completed}/{total}** ({percent}%) [⚡ {concurrency_limit} workers]")
                    except Exception:
                        pass

        tasks = [asyncio.create_task(worker(p)) for p in players]
        await asyncio.gather(*tasks)

        embed = discord.Embed(
            title="⚡ In-Game Player Name Sync Complete",
            colour=discord.Colour.green()
        )
        embed.add_field(name="Total Checked", value=str(total), inline=True)
        embed.add_field(name="✏️ Names Updated", value=str(updated), inline=True)
        embed.add_field(name="Unchanged / Failed", value=f"{unchanged} / {failed}", inline=True)

        if changes_log:
            sample_changes = "\n".join(changes_log[:15])
            if len(changes_log) > 15:
                sample_changes += f"\n...and {len(changes_log) - 15} more"
            embed.add_field(name="Recent Updates", value=sample_changes, inline=False)

        await status_msg.edit(content=None, embed=embed)

    @player_group.command(name="batch-edit", description="Mass update Kingdom ID or Alliance tag for multiple players")
    @app_commands.describe(
        new_kingdom="New Kingdom ID to apply",
        new_alliance="New Alliance tag to apply",
        target_alliance="Filter: apply to all members of this current alliance",
        fids="Filter: comma or space separated list of Player IDs (FIDs)"
    )
    async def batch_edit_cmd(
        self,
        interaction: discord.Interaction,
        new_kingdom: Optional[str] = None,
        new_alliance: Optional[str] = None,
        target_alliance: Optional[str] = None,
        fids: Optional[str] = None
    ):
        if not new_kingdom and not new_alliance:
            await interaction.response.send_message("❌ Specify at least one change: `new_kingdom` or `new_alliance`.", ephemeral=True)
            return

        if not target_alliance and not fids:
            await interaction.response.send_message("❌ Specify a target: `target_alliance` or `fids`.", ephemeral=True)
            return

        fid_list = [f.strip() for f in fids.replace(',', ' ').split() if f.strip().isdigit()] if fids else None

        await interaction.response.defer(thinking=True)
        changes = []
        if new_kingdom:
            k_count = await self.db.batch_update_kingdom(new_kid=new_kingdom, alliance=target_alliance, fids=fid_list)
            changes.append(f"• Set Kingdom to **K{new_kingdom}** for **{k_count}** player(s)")
        if new_alliance:
            a_count = await self.db.batch_update_alliance(new_alliance=new_alliance, fids=fid_list, current_alliance=target_alliance)
            changes.append(f"• Set Alliance to **[{new_alliance}]** for **{a_count}** player(s)")

        embed = discord.Embed(
            title="✅ Batch Player Update Complete",
            description="\n".join(changes),
            colour=discord.Colour.green()
        )
        await interaction.followup.send(embed=embed)

    @player_group.command(name="batch-delete", description="Mass delete or disable players by alliance or list of FIDs")
    @app_commands.describe(
        alliance="Alliance tag to target",
        fids="Comma or space separated list of Player IDs (FIDs)",
        action="delete (hard remove) or disable (set status to DISABLED)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Disable (Set status to DISABLED)", value="disable"),
        app_commands.Choice(name="Delete (Permanently remove from DB)", value="delete")
    ])
    async def batch_delete_cmd(
        self,
        interaction: discord.Interaction,
        alliance: Optional[str] = None,
        fids: Optional[str] = None,
        action: str = "disable"
    ):
        if not alliance and not fids:
            await interaction.response.send_message("❌ Specify at least one target: `alliance` or `fids`.", ephemeral=True)
            return

        fid_list = [f.strip() for f in fids.replace(',', ' ').split() if f.strip().isdigit()] if fids else None
        target_desc = f"Alliance `[{alliance}]`" if alliance else f"`{len(fid_list)}` specific FID(s)"
        if alliance and fid_list:
            target_desc = f"Alliance `[{alliance}]` and `{len(fid_list)}` FID(s)"

        is_delete = (action == "delete")
        action_verb = "permanently DELETE" if is_delete else "DISABLE"

        embed = discord.Embed(
            title=f"⚠️ Confirm Batch {action.capitalize()}",
            description=f"Are you sure you want to **{action_verb}** players matching {target_desc}?",
            colour=discord.Colour.red() if is_delete else discord.Colour.orange()
        )

        async def on_confirm(btn_interaction: discord.Interaction):
            if is_delete:
                count = await self.db.batch_delete_players(fids=fid_list, alliance=alliance)
                res_msg = f"🗑️ Permanently removed **{count}** player(s) from the database."
            else:
                count = await self.db.batch_set_status(new_status="DISABLED", fids=fid_list, alliance=alliance)
                res_msg = f"🔴 Marked **{count}** player(s) as **DISABLED**."

            done_embed = discord.Embed(
                title=f"✅ Batch {action.capitalize()} Completed",
                description=res_msg,
                colour=discord.Colour.green()
            )
            await btn_interaction.followup.send(embed=done_embed, ephemeral=True)

        view = ConfirmActionView(interaction.user.id, on_confirm=on_confirm)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    print("PlayerManager cog loaded")
    await bot.add_cog(PlayerManager(bot))

