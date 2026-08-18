import os
import asyncio
import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional

from databases.player_database import PlayerDatabase
from utils import google_sync


class BackupSyncCog(commands.Cog):
    """Cog for automated SQLite backups to Google Drive and Google Sheets player sync."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = PlayerDatabase()
        self.last_backup_time: Optional[datetime.datetime] = None
        self.last_backup_status: str = "Never run"
        self.auto_backup_task.start()

    def cog_unload(self):
        self.auto_backup_task.cancel()

    @tasks.loop(hours=24)
    async def auto_backup_task(self):
        """Background daily backup task."""
        try:
            db_path = self.db.db_path
            if not os.path.exists(db_path):
                return

            local_file = await asyncio.to_thread(google_sync.create_local_backup, db_path)
            google_sync.cleanup_local_backups()

            creds = google_sync.get_google_credentials()
            if creds:
                await asyncio.to_thread(google_sync.upload_backup_to_drive, local_file)
                self.last_backup_status = "Success (Local + Google Drive)"
            else:
                self.last_backup_status = "Success (Local only - credentials not configured)"

            self.last_backup_time = datetime.datetime.now()
            print(f"[BackupSync] Automated backup completed: {self.last_backup_status}")
        except Exception as e:
            self.last_backup_status = f"Failed: {e}"
            print(f"[BackupSync] Automated backup error: {e}")

    @auto_backup_task.before_loop
    async def before_auto_backup(self):
        await self.bot.wait_until_ready()

    # ==========================================
    # /backup Command Group
    # ==========================================
    backup_group = app_commands.Group(name="backup", description="Database backup and Google Drive management")

    @backup_group.command(name="now", description="Trigger an immediate database backup to local drive and Google Drive")
    @app_commands.describe(folder_id="Optional Google Drive folder ID override")
    async def backup_now_cmd(self, interaction: discord.Interaction, folder_id: Optional[str] = None):
        await interaction.response.defer(thinking=True)

        db_path = self.db.db_path
        if not os.path.exists(db_path):
            await interaction.followup.send(f"❌ Database file not found at {db_path}.", ephemeral=True)
            return

        try:
            local_backup_file = await asyncio.to_thread(google_sync.create_local_backup, db_path)
            purged_local = google_sync.cleanup_local_backups()

            file_size_kb = os.path.getsize(local_backup_file) / 1024.0

            embed = discord.Embed(
                title="💾 Database Backup Snapshot Created",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Local Snapshot", value=f"{os.path.basename(local_backup_file)}", inline=False)
            embed.add_field(name="Snapshot Size", value=f"{file_size_kb:.2f} KB", inline=True)
            embed.add_field(name="Local Rotated", value=f"{purged_local} old snapshot(s) cleaned", inline=True)

            creds = google_sync.get_google_credentials()
            if creds:
                target_folder = folder_id or google_sync.get_drive_folder_id()
                drive_res = await asyncio.to_thread(
                    google_sync.upload_backup_to_drive,
                    local_backup_file,
                    target_folder
                )
                self.last_backup_time = datetime.datetime.now()
                self.last_backup_status = "Success (Local + Google Drive)"

                drive_link = drive_res.get("drive_link")
                link_text = f"[View in Google Drive]({drive_link})" if drive_link else f"{drive_res.get('file_id')}"
                embed.add_field(name="Google Drive", value=f"✅ Uploaded\n{link_text}", inline=False)
                if drive_res.get("drive_deleted_count", 0) > 0:
                    embed.add_field(name="Drive Rotation", value=f"Cleaned {drive_res['drive_deleted_count']} older backup(s)", inline=True)
            else:
                self.last_backup_time = datetime.datetime.now()
                self.last_backup_status = "Success (Local only)"
                embed.add_field(
                    name="Google Drive",
                    value="⚠️ Skipped (Service Account credentials not found in env or service-account.json)",
                    inline=False
                )

            await interaction.followup.send(embed=embed)
        except Exception as e:
            self.last_backup_status = f"Failed: {e}"
            await interaction.followup.send(f"❌ Backup failed with error: {e}", ephemeral=True)

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
        embed.add_field(name="Google Drive Folder ID", value=f"{google_sync.get_drive_folder_id()}", inline=True)

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
        await interaction.response.defer(thinking=True)

        try:
            creds = google_sync.get_google_credentials()
            if not creds:
                await interaction.followup.send(
                    "❌ Google Service Account not configured. Place service-account.json in project root or set GOOGLE_SERVICE_ACCOUNT_JSON.",
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

    @sheet_group.command(name="pull", description="Import edits made in Google Sheet back into the SQLite database")
    @app_commands.describe(sheet_id="Optional Google Sheet ID override")
    async def sheet_pull_cmd(self, interaction: discord.Interaction, sheet_id: Optional[str] = None):
        await interaction.response.defer(thinking=True)

        try:
            creds = google_sync.get_google_credentials()
            if not creds:
                await interaction.followup.send(
                    "❌ Google Service Account not configured. Place service-account.json in project root or set GOOGLE_SERVICE_ACCOUNT_JSON.",
                    ephemeral=True
                )
                return

            target_id = sheet_id or google_sync.get_sheet_id()
            import_res = await asyncio.to_thread(google_sync.import_players_from_sheet, target_id)

            valid_players = import_res.get("valid_players", [])
            skipped_rows = import_res.get("skipped_rows", [])

            if not valid_players and not skipped_rows:
                await interaction.followup.send("⚠️ Google Sheet appears to be empty or missing data rows.", ephemeral=True)
                return

            updated_count = await self.db.bulk_upsert_players(valid_players)

            embed = discord.Embed(
                title="🔄 Google Sheet Sync Complete",
                description=f"Synchronized database with [{import_res.get('spreadsheet_title', 'Google Sheet')}]({import_res.get('spreadsheet_url', '#')}).",
                color=discord.Color.green() if not skipped_rows else discord.Color.gold()
            )
            embed.add_field(name="Total Rows Read", value=str(import_res.get("total_read", 0)), inline=True)
            embed.add_field(name="Synced Players", value=str(updated_count), inline=True)
            embed.add_field(name="Invalid Rows Skipped", value=str(len(skipped_rows)), inline=True)

            if skipped_rows:
                skip_details = "\n".join(f"• Row {s['row']}: {s['reason']}" for s in skipped_rows[:8])
                if len(skipped_rows) > 8:
                    skip_details += f"\n...and {len(skipped_rows) - 8} more"
                embed.add_field(name="Skipped Row Details", value=skip_details, inline=False)

            embed.set_footer(text="Run /player sync-names to verify in-game names for any new IDs added.")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Google Sheet pull failed: {e}", ephemeral=True)

    @sheet_group.command(name="status", description="Show Google Drive and Google Sheet connection details")
    async def sheet_status_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        creds = google_sync.get_google_credentials()
        sheet_id = google_sync.get_sheet_id()
        folder_id = google_sync.get_drive_folder_id()

        embed = discord.Embed(
            title="🔗 Google Integration Status",
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
        drive_url = f"https://drive.google.com/drive/folders/{folder_id}"

        embed.add_field(name="Google Sheet", value=f"[{sheet_id}]({sheet_url})", inline=False)
        embed.add_field(name="Google Drive Folder", value=f"[{folder_id}]({drive_url})", inline=False)
        embed.add_field(name="Daily Auto-Backup", value=f"🟢 Active ({self.last_backup_status})", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    print("BackupSync cog loaded")
    await bot.add_cog(BackupSyncCog(bot))
