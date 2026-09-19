import os
import io
import asyncio
import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, Union, List, Dict, Any

from databases.player_database import PlayerDatabase
from utils import google_sync


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


class BackupSyncCog(commands.Cog):
    """Cog for automated SQLite backups to Discord channels, Google Drive, and Google Sheets sync."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = PlayerDatabase()
        self.last_backup_time: Optional[datetime.datetime] = None
        self.last_backup_status: str = "Never run"
        self.auto_backup_task.start()

    def cog_unload(self):
        self.auto_backup_task.cancel()

    async def get_backup_channel(self) -> Optional[discord.TextChannel]:
        """Resolves the configured Discord backup channel."""
        cid_str = os.getenv("BACKUP_CHANNEL_ID") or await self.db.get_setting("backup_channel_id")
        if not cid_str:
            return None
        try:
            cid = int(cid_str)
            channel = self.bot.get_channel(cid)
            if not channel:
                channel = await self.bot.fetch_channel(cid)
            return channel if isinstance(channel, discord.TextChannel) else None
        except Exception:
            return None

    @tasks.loop(hours=24)
    async def auto_backup_task(self):
        """Background daily backup task (posts to Discord channel + local snapshot)."""
        try:
            db_path = self.db.db_path
            if not os.path.exists(db_path):
                return

            local_file = await asyncio.to_thread(google_sync.create_local_backup, db_path)
            purged = google_sync.cleanup_local_backups()
            file_size_kb = os.path.getsize(local_file) / 1024.0

            players = await self.db.get_all_players()
            status_parts = [f"Local Snapshot ({file_size_kb:.1f} KB)"]

            channel = await self.get_backup_channel()
            if channel:
                embed = discord.Embed(
                    title="💾 Daily Automated Database Backup",
                    description=f"Snapshot taken at <t:{int(datetime.datetime.now().timestamp())}:F>",
                    color=discord.Color.green(),
                    timestamp=datetime.datetime.now()
                )
                embed.add_field(name="File Name", value=f"{os.path.basename(local_file)}", inline=True)
                embed.add_field(name="Database Size", value=f"{file_size_kb:.2f} KB", inline=True)
                embed.add_field(name="Total Players", value=str(len(players)), inline=True)
                embed.set_footer(text="Download this .db file anytime to restore or inspect data.")

                with open(local_file, "rb") as f:
                    discord_file = discord.File(f, filename=os.path.basename(local_file))
                    await channel.send(embed=embed, file=discord_file)
                status_parts.append(f"Posted to #{channel.name}")

            self.last_backup_status = "Success (" + " + ".join(status_parts) + ")"
            self.last_backup_time = datetime.datetime.now()
            print(f"[BackupSync] Automated backup completed: {self.last_backup_status}")
        except Exception as e:
            self.last_backup_status = f"Failed: {e}"
            print(f"[BackupSync] Automated backup error: {e}")

    @auto_backup_task.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # Core Logic Methods (Callable by slash & buttons)
    # ==========================================
    async def do_backup_now(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)

        db_path = self.db.db_path
        if not os.path.exists(db_path):
            await interaction.followup.send(f"❌ Database file not found at {db_path}.", ephemeral=True)
            return

        try:
            local_backup_file = await asyncio.to_thread(google_sync.create_local_backup, db_path)
            purged_local = google_sync.cleanup_local_backups()
            file_size_kb = os.path.getsize(local_backup_file) / 1024.0
            players = await self.db.get_all_players()

            target_channel = channel or await self.get_backup_channel() or interaction.channel

            embed = discord.Embed(
                title="💾 Database Backup Snapshot",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="File Name", value=f"{os.path.basename(local_backup_file)}", inline=True)
            embed.add_field(name="Size", value=f"{file_size_kb:.2f} KB", inline=True)
            embed.add_field(name="Total Players", value=str(len(players)), inline=True)
            embed.add_field(name="Local Retention", value=f"Rotated {purged_local} old snapshot(s)", inline=False)
            embed.set_footer(text="Download this .db file anytime to inspect or restore SQLite data.")

            with open(local_backup_file, "rb") as f:
                discord_file = discord.File(f, filename=os.path.basename(local_backup_file))
                
                if target_channel and target_channel.id != interaction.channel_id:
                    await target_channel.send(embed=embed, file=discord_file)
                    await interaction.followup.send(
                        f"✅ Backup created and posted to {target_channel.mention} ({os.path.basename(local_backup_file)})."
                    )
                else:
                    await interaction.followup.send(embed=embed, file=discord_file)

            self.last_backup_time = datetime.datetime.now()
            self.last_backup_status = f"Success (Posted to #{getattr(target_channel, 'name', 'current')})"
        except Exception as e:
            self.last_backup_status = f"Failed: {e}"
            await interaction.followup.send(f"❌ Backup failed with error: {e}", ephemeral=True)

    async def do_export_sheet(self, interaction: discord.Interaction, sheet_id: Optional[str] = None):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)

        try:
            creds = google_sync.get_google_credentials()
            if not creds:
                await interaction.followup.send(
                    "❌ Google Service Account not configured.\nPlace service-account.json in project root or set GOOGLE_SERVICE_ACCOUNT_JSON.",
                    ephemeral=True
                )
                return

            players = await self.db.get_all_players()
            if not players:
                await interaction.followup.send("⚠️ No players found in the database to export.", ephemeral=True)
                return

            target_id = sheet_id or google_sync.get_sheet_id()
            res = await asyncio.to_thread(google_sync.export_players_to_sheet, players, target_id)

            embed = discord.Embed(
                title="📊 Google Sheet Export Complete",
                description=f"Exported **{res['total_exported']}** player records to Google Sheet.",
                color=discord.Color.green()
            )
            embed.add_field(name="Spreadsheet", value=f"[{res['spreadsheet_title']}]({res['spreadsheet_url']})", inline=False)
            embed.add_field(name="Sheet ID", value=f"{target_id}", inline=False)
            embed.set_footer(text="You can now edit rows directly in Google Sheets, then run /sheet pull to sync back.")

            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Google Sheet export failed: {e}", ephemeral=True)

    async def do_pull_sheet(
        self,
        interaction: discord.Interaction,
        sheet_id: Optional[str] = None,
        prune: bool = False
    ):
        if not interaction.response.is_done():
            await interaction.response.defer(thinking=True)

        try:
            creds = google_sync.get_google_credentials()
            if not creds:
                await interaction.followup.send(
                    "❌ Google Service Account not configured.\nPlace service-account.json in project root or set GOOGLE_SERVICE_ACCOUNT_JSON.",
                    ephemeral=True
                )
                return

            target_id = sheet_id or google_sync.get_sheet_id()
            import_res = await asyncio.to_thread(google_sync.import_players_from_sheet, target_id)

            valid_players = import_res.get("valid_players", [])
            skipped_rows = import_res.get("skipped_rows", [])
            sheet_title = import_res.get("spreadsheet_title", "Google Sheet")
            sheet_url = import_res.get("spreadsheet_url", "#")
            total_read = import_res.get("total_read", 0)

            if not valid_players and not skipped_rows:
                await interaction.followup.send("⚠️ Google Sheet appears to be empty or missing data rows.", ephemeral=True)
                return

            # Safety guardrail: abort if sheet has 0 valid players to prevent emptying database
            if prune and not valid_players:
                await interaction.followup.send(
                    "⚠️ Google Sheet contains 0 valid player records. Pruning aborted to prevent emptying database.",
                    ephemeral=True
                )
                return

            # Identify missing FIDs
            db_players = await self.db.get_all_players()
            db_fids_map = {str(p["fid"]): p for p in db_players if p.get("fid")}
            sheet_fids = {str(p["fid"]).strip() for p in valid_players if p.get("fid")}
            missing_fids = [fid for fid in db_fids_map if fid not in sheet_fids]

            # If pruning requested and missing IDs exist, prompt confirmation
            if prune and missing_fids:
                preview_lines = []
                for fid in missing_fids[:10]:
                    p = db_fids_map[fid]
                    p_name = p.get("name") or "Unknown"
                    p_alliance = f"[{p.get('alliance')}] " if p.get("alliance") else ""
                    preview_lines.append(f"• `{fid}`: {p_alliance}{p_name}")
                if len(missing_fids) > 10:
                    preview_lines.append(f"...and {len(missing_fids) - 10} more player(s)")
                preview_text = "\n".join(preview_lines)

                confirm_embed = discord.Embed(
                    title="⚠️ Confirm Player Deletion (Sheet Prune)",
                    description=(
                        f"**{len(missing_fids)}** player(s) exist in the database but are **missing from Google Sheet**.\n\n"
                        f"If confirmed, these records will be **permanently deleted** from SQLite, "
                        f"and **{len(valid_players)}** player(s) from Google Sheet will be synchronized.\n\n"
                        f"💾 *A local backup snapshot will be saved automatically before deletion.*"
                    ),
                    color=discord.Color.red() if len(missing_fids) > 10 else discord.Color.orange()
                )
                confirm_embed.add_field(
                    name=f"Players to Delete ({len(missing_fids)} total)",
                    value=preview_text,
                    inline=False
                )
                confirm_embed.set_footer(text="Click 'Confirm Delete' to delete missing IDs or 'Cancel' to keep them.")

                view = SheetPruneConfirmView(
                    cog=self,
                    user_id=interaction.user.id,
                    missing_fids=missing_fids,
                    valid_players=valid_players,
                    skipped_rows=skipped_rows,
                    sheet_title=sheet_title,
                    sheet_url=sheet_url
                )
                view.message = await interaction.followup.send(embed=confirm_embed, view=view)
                return

            # Non-prune sync or prune with 0 missing IDs
            updated_count = await self.db.bulk_upsert_players(valid_players)

            embed = discord.Embed(
                title="🔄 Google Sheet Sync Complete",
                description=f"Synchronized database with [{sheet_title}]({sheet_url}).",
                color=discord.Color.green() if not skipped_rows else discord.Color.gold()
            )
            embed.add_field(name="Total Rows Read", value=str(total_read), inline=True)
            embed.add_field(name="Synced Players", value=str(updated_count), inline=True)
            embed.add_field(name="Invalid Rows Skipped", value=str(len(skipped_rows)), inline=True)

            if prune and not missing_fids:
                embed.add_field(name="Pruning", value="✅ No missing players detected. Database matches sheet.", inline=False)
            elif not prune and missing_fids:
                embed.add_field(
                    name="ℹ️ Untracked in Sheet",
                    value=f"**{len(missing_fids)}** player(s) in DB are not in sheet.\nRun `/sheet pull prune:True` to delete them.",
                    inline=False
                )

            if skipped_rows:
                skip_details = "\n".join(f"• Row {s['row']}: {s['reason']}" for s in skipped_rows[:8])
                if len(skipped_rows) > 8:
                    skip_details += f"\n...and {len(skipped_rows) - 8} more"
                embed.add_field(name="Skipped Row Details", value=skip_details, inline=False)

            embed.set_footer(text="Run /player sync-names to verify in-game names for any new IDs added.")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Google Sheet pull failed: {e}", ephemeral=True)

    async def do_sheet_status(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        creds = google_sync.get_google_credentials()
        sheet_id = google_sync.get_sheet_id()

        embed = discord.Embed(
            title="🔗 Google Sheet Integration Status",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Credentials Status",
            value="🟢 Connected" if creds else "🔴 Not Configured (service-account.json missing)",
            inline=False
        )
        if creds and hasattr(creds, 'service_account_email'):
            embed.add_field(name="Service Account Email", value=f"{creds.service_account_email}", inline=False)

        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        embed.add_field(name="Google Sheet", value=f"[{sheet_id}]({sheet_url})", inline=False)

        backup_channel = await self.get_backup_channel()
        channel_str = f"{backup_channel.mention}" if backup_channel else "None configured (/backup set-channel)"
        embed.add_field(name="Discord Backup Channel", value=channel_str, inline=False)
        embed.add_field(name="Daily Auto-Backup", value=f"🟢 Active ({self.last_backup_status})", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # /backup Command Group
    # ==========================================
    backup_group = app_commands.Group(name="backup", description="Database backup and archive management")

    @backup_group.command(name="set-channel", description="Set the Discord channel for automated and manual database backups")
    @app_commands.describe(channel="The text channel where database backup files should be posted")
    async def backup_set_channel_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        await self.db.set_setting("backup_channel_id", str(channel.id))

        embed = discord.Embed(
            title="✅ Backup Channel Configured",
            description=f"Automated daily backups and /backup now will post .db snapshots to {channel.mention}.",
            color=discord.Color.green()
        )
        embed.add_field(name="Channel Name", value=f"#{channel.name}", inline=True)
        embed.add_field(name="Channel ID", value=f"{channel.id}", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @backup_group.command(name="now", description="Trigger an immediate database backup and upload .db file to Discord")
    @app_commands.describe(channel="Optional target channel to post the backup file to")
    async def backup_now_cmd(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        await self.do_backup_now(interaction, channel)

    @backup_group.command(name="list", description="List local database backups and backup health")
    async def backup_list_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "backups")
        files = []
        if os.path.exists(backup_dir):
            files = [
                f for f in os.listdir(backup_dir)
                if f.startswith("players_") and f.endswith(".db")
            ]
            files.sort(reverse=True)

        channel = await self.get_backup_channel()
        channel_str = f"{channel.mention} ({channel.id})" if channel else "None configured (use /backup set-channel)"

        embed = discord.Embed(
            title="📂 Database Backups Status",
            color=discord.Color.blue()
        )
        embed.add_field(name="Last Run Status", value=self.last_backup_status, inline=False)
        embed.add_field(
            name="Last Backup Time",
            value=self.last_backup_time.strftime("%Y-%m-%d %H:%M:%S UTC") if self.last_backup_time else "Never",
            inline=True
        )
        embed.add_field(name="Target Backup Channel", value=channel_str, inline=False)

        if files:
            file_list_str = "\n".join(f"• {f}" for f in files[:10])
            embed.add_field(name=f"Local Files ({len(files)} total)", value=file_list_str, inline=False)
        else:
            embed.add_field(name="Local Files", value="No local backup files found.", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # /sheet Command Group
    # ==========================================
    sheet_group = app_commands.Group(name="sheet", description="Google Sheets two-way synchronization for players")

    @sheet_group.command(name="export", description="Export all players from SQLite database to Google Sheet")
    @app_commands.describe(sheet_id="Optional Google Sheet ID override")
    async def sheet_export_cmd(self, interaction: discord.Interaction, sheet_id: Optional[str] = None):
        await self.do_export_sheet(interaction, sheet_id)

    @sheet_group.command(name="pull", description="Import edits made in Google Sheet back into the SQLite database")
    @app_commands.describe(
        sheet_id="Optional Google Sheet ID override",
        prune="Delete players in database that are missing from Google Sheet (prompts for confirmation)"
    )
    async def sheet_pull_cmd(
        self,
        interaction: discord.Interaction,
        sheet_id: Optional[str] = None,
        prune: bool = False
    ):
        await self.do_pull_sheet(interaction, sheet_id=sheet_id, prune=prune)

    @sheet_group.command(name="status", description="Show Google Sheet connection details")
    async def sheet_status_cmd(self, interaction: discord.Interaction):
        await self.do_sheet_status(interaction)


async def setup(bot: commands.Bot):
    print("BackupSync cog loaded")
    await bot.add_cog(BackupSyncCog(bot))
