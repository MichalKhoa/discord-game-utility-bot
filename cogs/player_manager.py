import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import io
from typing import Optional, List

from databases.player_database import PlayerDatabase
import utils.redeem_code


class PlayerEditModal(discord.ui.Modal):
    def __init__(self, db: PlayerDatabase, player_data: dict):
        super().__init__(title=f"Edit Player: {player_data.get('name') or player_data.get('fid')}")
        self.db = db
        self.original_fid = str(player_data.get("fid", ""))

        self.fid_input = discord.ui.TextInput(
            label="Player ID (FID)",
            default=self.original_fid,
            min_length=5,
            max_length=20,
            required=True
        )
        self.kid_input = discord.ui.TextInput(
            label="Kingdom ID (KID)",
            default=str(player_data.get("kid", "278")),
            min_length=1,
            max_length=10,
            required=True
        )
        self.name_input = discord.ui.TextInput(
            label="In-Game Name (IGN)",
            default=str(player_data.get("name", "")),
            max_length=50,
            required=False
        )
        self.alliance_input = discord.ui.TextInput(
            label="Alliance Tag",
            default=str(player_data.get("alliance", "")),
            max_length=20,
            required=False
        )

        self.add_item(self.fid_input)
        self.add_item(self.kid_input)
        self.add_item(self.name_input)
        self.add_item(self.alliance_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        new_fid = self.fid_input.value.strip()
        new_kid = self.kid_input.value.strip()
        new_name = self.name_input.value.strip()
        new_alliance = self.alliance_input.value.strip()

        if not new_fid.isdigit():
            await interaction.followup.send("❌ Error: Player ID (FID) must be numbers only.", ephemeral=True)
            return

        # Perform live API verification
        is_valid, verify_msg = await discord.utils.maybe_coroutine(
            utils.redeem_code.verify_player, new_fid, new_kid
        )

        if not is_valid:
            embed = discord.Embed(
                title="⚠️ API Verification Warning",
                description=(
                    f"The Century Games API returned an issue with this ID:\n"
                    f"**Reason**: `{verify_msg}`\n\n"
                    f"Would you still like to force save, or fix the details?"
                ),
                colour=discord.Colour.red()
            )
            # Save anyway with FLAGGED status if invalid
            if new_fid != self.original_fid and self.original_fid:
                await self.db.delete_player(self.original_fid)

            await self.db.upsert_player(
                fid=new_fid,
                kid=new_kid,
                name=new_name,
                alliance=new_alliance,
                status="FLAGGED",
                warning_count=1,
                warning_reason=verify_msg
            )
            await interaction.followup.send(
                f"⚠️ Saved with warning! FID `{new_fid}` in Kingdom `{new_kid}` flagged: `{verify_msg}`",
                ephemeral=True
            )
            return

        # Delete old record if FID was changed
        if new_fid != self.original_fid and self.original_fid:
            await self.db.delete_player(self.original_fid)

        await self.db.upsert_player(
            fid=new_fid,
            kid=new_kid,
            name=new_name,
            alliance=new_alliance,
            status="ACTIVE",
            warning_count=0,
            warning_reason=None
        )

        embed = discord.Embed(
            title="✅ Player Updated & Verified",
            colour=discord.Colour.green()
        )
        embed.add_field(name="Player Name", value=new_name or "N/A", inline=True)
        embed.add_field(name="FID", value=f"`{new_fid}`", inline=True)
        embed.add_field(name="Kingdom", value=f"`{new_kid}`", inline=True)
        embed.add_field(name="Alliance", value=new_alliance or "None", inline=True)
        embed.add_field(name="Status", value="🟢 ACTIVE (Verified)", inline=True)
        await interaction.followup.send(embed=embed)


class PlayerAddModal(discord.ui.Modal, title="Add New Player"):
    fid_input = discord.ui.TextInput(
        label="Player ID (FID)",
        placeholder="e.g. 117280427",
        min_length=5,
        max_length=20,
        required=True
    )
    kid_input = discord.ui.TextInput(
        label="Kingdom ID (KID)",
        placeholder="Default: 278",
        default="278",
        min_length=1,
        max_length=10,
        required=True
    )
    name_input = discord.ui.TextInput(
        label="In-Game Name (IGN)",
        placeholder="e.g. HimAlt",
        max_length=50,
        required=False
    )
    alliance_input = discord.ui.TextInput(
        label="Alliance Tag",
        placeholder="e.g. NOR",
        max_length=20,
        required=False
    )

    def __init__(self, db: PlayerDatabase):
        super().__init__()
        self.db = db

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        fid = self.fid_input.value.strip()
        kid = self.kid_input.value.strip() or "278"
        name = self.name_input.value.strip()
        alliance = self.alliance_input.value.strip()

        if not fid.isdigit():
            await interaction.followup.send("❌ Error: Player ID (FID) must be numbers only.", ephemeral=True)
            return

        is_valid, verify_msg = await discord.utils.maybe_coroutine(
            utils.redeem_code.verify_player, fid, kid
        )

        status = "ACTIVE" if is_valid else "FLAGGED"
        warning_count = 0 if is_valid else 1
        warning_reason = None if is_valid else verify_msg

        await self.db.upsert_player(
            fid=fid,
            kid=kid,
            name=name,
            alliance=alliance,
            status=status,
            warning_count=warning_count,
            warning_reason=warning_reason
        )

        if is_valid:
            embed = discord.Embed(title="✅ Player Added & Verified", colour=discord.Colour.green())
            embed.add_field(name="IGN", value=name or "N/A", inline=True)
            embed.add_field(name="FID", value=f"`{fid}`", inline=True)
            embed.add_field(name="Kingdom", value=f"`{kid}`", inline=True)
            embed.add_field(name="Alliance", value=alliance or "None", inline=True)
            embed.add_field(name="Status", value="🟢 ACTIVE", inline=True)
            await interaction.followup.send(embed=embed)
        else:
            embed = discord.Embed(title="⚠️ Player Added with Warning", colour=discord.Colour.yellow())
            embed.add_field(name="IGN", value=name or "N/A", inline=True)
            embed.add_field(name="FID", value=f"`{fid}`", inline=True)
            embed.add_field(name="Kingdom", value=f"`{kid}`", inline=True)
            embed.add_field(name="API Warning", value=f"`{verify_msg}`", inline=False)
            await interaction.followup.send(embed=embed)


class PlayerListView(discord.ui.View):
    def __init__(self, db: PlayerDatabase, players: List[dict], alliance_filter: Optional[str] = None, page: int = 0):
        super().__init__(timeout=300)
        self.db = db
        self.players = players
        self.alliance_filter = alliance_filter
        self.page = page
        self.per_page = 15
        self.max_pages = max(1, (len(players) + self.per_page - 1) // self.per_page)
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = (self.page <= 0)
        self.next_btn.disabled = (self.page >= self.max_pages - 1)

    def get_embed(self) -> discord.Embed:
        start_idx = self.page * self.per_page
        end_idx = min(start_idx + self.per_page, len(self.players))
        page_items = self.players[start_idx:end_idx]

        filter_str = f" • Filter: `{self.alliance_filter}`" if self.alliance_filter else ""
        embed = discord.Embed(
            title=f"📋 Registered Players ({len(self.players)} total){filter_str}",
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

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="btn_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="btn_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)


class PlayerManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = PlayerDatabase()

    player_group = app_commands.Group(name="player", description="Manage game player IDs and kingdoms")

    async def cog_load(self):
        await self.db.init_db()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.db.init_db()

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

    @player_group.command(name="search", description="Search for a player by FID, Name, or Alliance")
    @app_commands.describe(query="Name, FID, or Alliance to search")
    async def search_player(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        results = await self.db.search_players(query, limit=10)
        if not results:
            await interaction.followup.send(f"⚠️ No players found matching `{query}`.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🔍 Search Results for '{query}'", colour=discord.Colour.og_blurple())
        for p in results:
            status = p.get("status", "ACTIVE")
            badge = "🟢" if status == "ACTIVE" else ("🟡" if status == "FLAGGED" else "🔴")
            warning = f"\n⚠️ Reason: `{p.get('warning_reason')}`" if p.get("warning_reason") else ""
            embed.add_field(
                name=f"{badge} {p.get('name') or 'Unknown'} ({p.get('alliance') or 'No Alliance'})",
                value=f"• FID: `{p.get('fid')}`\n• Kingdom: `K{p.get('kid')}`\n• Status: `{status}` ({p.get('warning_count', 0)} strikes){warning}",
                inline=False
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

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

        embed = discord.Embed(
            title=f"⚠️ Flagged / Problematic Players ({len(flagged)} total)",
            description="These players failed API redemption or were flagged. Use `/player edit` to fix them.",
            colour=discord.Colour.orange()
        )

        lines = []
        for p in flagged[:25]:
            status = p.get("status")
            badge = "🔴" if status == "DISABLED" else "🟡"
            reason = p.get("warning_reason") or "Unknown error"
            strikes = p.get("warning_count", 0)
            lines.append(f"{badge} **{p.get('name') or p.get('fid')}** (`{p.get('fid')}` | K{p.get('kid')}) — `{strikes} strikes`\n> ⚠️ *{reason}*")

        embed.description = "\n\n".join(lines)
        await interaction.followup.send(embed=embed, ephemeral=True)

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

    @player_group.command(name="stats", description="View total player statistics and kingdom breakdown")
    async def player_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        stats = await self.db.get_stats()
        if stats["total"] == 0:
            embed = discord.Embed(
                title="📊 Player Registry Statistics",
                description="⚠️ No players registered in the database yet.\nUse `/player add` or click **Add Player** to register IDs.",
                colour=discord.Colour.gold()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(title="📊 Player Registry Statistics", colour=discord.Colour.gold())
        embed.add_field(name="Total Players", value=str(stats["total"]), inline=True)
        embed.add_field(name="🟢 Active", value=str(stats["active"]), inline=True)
        embed.add_field(name="🟡 Flagged / 🔴 Disabled", value=f"{stats['flagged']} / {stats['disabled']}", inline=True)

        k_breakdown = "\n".join(f"• Kingdom **{k['kid']}**: {k['count']} players" for k in stats["kingdoms"])
        embed.add_field(name="Top Kingdoms", value=k_breakdown or "None", inline=False)

        a_breakdown = "\n".join(f"• **{a['alliance']}**: {a['count']} players" for a in stats["alliances"])
        embed.add_field(name="Top Alliances", value=a_breakdown or "None", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @player_group.command(name="export", description="Export all player IDs as a CSV spreadsheet")
    async def export_csv_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        csv_data = await self.db.export_csv()
        file = discord.File(io.BytesIO(csv_data.encode('utf-8')), filename="player_ids.csv")
        await interaction.followup.send("📥 Here is the current player export:", file=file, ephemeral=True)

    @player_group.command(name="import", description="Import players from an attached CSV or text file")
    @app_commands.describe(file="CSV or TXT file to import")
    async def import_file_cmd(self, interaction: discord.Interaction, file: discord.Attachment):
        if not (file.filename.endswith(".csv") or file.filename.endswith(".txt")):
            await interaction.response.send_message("❌ Please upload a `.csv` or `.txt` file.", ephemeral=True)
            return

        await interaction.response.defer()
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8", errors="replace")

        imported_count = 0
        players_to_insert = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.replace(',', ' ').split() if p.strip()]
            if not parts or not parts[0].isdigit():
                continue
            fid = parts[0]
            kid = parts[1] if len(parts) > 1 and parts[1].isdigit() and int(parts[1]) <= 999999 else "278"
            name = parts[2] if len(parts) > 2 else ""
            players_to_insert.append({
                "fid": fid,
                "kid": kid,
                "name": name,
                "alliance": "",
                "status": "ACTIVE",
                "warning_count": 0,
                "warning_reason": None
            })

        if players_to_insert:
            imported_count = await self.db.bulk_upsert_players(players_to_insert)

        await interaction.followup.send(f"✅ Imported/Updated **{imported_count}** player IDs.")

    @player_group.command(name="sync-names", description="Auto-sync in-game nicknames and kingdoms from Century Games API")
    @app_commands.describe(alliance="Optional: only sync players in this alliance")
    async def sync_names_cmd(self, interaction: discord.Interaction, alliance: Optional[str] = None):
        await interaction.response.defer(thinking=True)

        if alliance:
            players = await self.db.get_all_players(alliance=alliance)
        else:
            players = await self.db.get_active_players()

        if not players:
            await interaction.followup.send("❌ No players found to sync.", ephemeral=True)
            return

        total = len(players)
        updated = 0
        unchanged = 0
        failed = 0
        changes_log = []

        status_msg = await interaction.followup.send(f"🔄 Syncing {total} player names from Century Games API... (0%)")

        for idx, p in enumerate(players):
            fid = str(p.get("fid", "")).strip()
            current_name = str(p.get("name", "")).strip()
            current_kid = str(p.get("kid", "278")).strip()

            info = await discord.utils.maybe_coroutine(
                utils.redeem_code.fetch_player_info, fid, current_kid
            )

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

            if (idx + 1) % 10 == 0 or idx + 1 == total:
                percent = int(((idx + 1) / total) * 100)
                try:
                    await status_msg.edit(content=f"🔄 Syncing player names... **{idx + 1}/{total}** ({percent}%)")
                except Exception:
                    pass

            await asyncio.sleep(0.3)

        embed = discord.Embed(
            title="✅ In-Game Player Name Sync Complete",
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


async def setup(bot: commands.Bot):
    print("PlayerManager cog loaded")
    await bot.add_cog(PlayerManager(bot))
