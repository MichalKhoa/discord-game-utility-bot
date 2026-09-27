import re
from typing import Optional, TYPE_CHECKING
import discord
from utils.countdown import play_voice_countdown
from databases.player_database import PlayerDatabase
import utils.redeem_code

if TYPE_CHECKING:
    from cogs.player_manager import PlayerManager
    from cogs.code_redeem import CodeRedeem


class RedeemModal(discord.ui.Modal, title='Gift Code'):
    code_input = discord.ui.TextInput(
        label='Enter the Gift Code',
        placeholder='e.g. KINGDOMSTAR',
        min_length=3,
        max_length=30,
        required=True
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog  # Pass the cog so we can call the redeem logic

    async def on_submit(self, interaction: discord.Interaction):
        gift_code = self.code_input.value.strip()

        # Call the helper function we just made in the Cog
        await self.cog.redeem_code_for_all(interaction, gift_code)


class RedeemSingleModal(discord.ui.Modal, title='Redeem for Single Player'):
    code_input = discord.ui.TextInput(
        label='Enter the Gift Code',
        placeholder='e.g. KINGDOMSTAR',
        min_length=3,
        max_length=30,
        required=True
    )
    player_input = discord.ui.TextInput(
        label='Enter the Player ID (FID)',
        placeholder='e.g. 49089798',
        min_length=5,
        max_length=20,
        required=True
    )
    kingdom_input = discord.ui.TextInput(
        label='Kingdom ID (Optional - default: saved/278)',
        placeholder='e.g. 278',
        required=False,
        max_length=10
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        gift_code = self.code_input.value.strip()
        player_id = self.player_input.value.strip()
        kingdom_id = self.kingdom_input.value.strip() or None
        await self.cog.redeem_code_for_player(interaction, gift_code, player_id, kingdom_id)


class ConfirmAbortModal(discord.ui.Modal, title="🛑 Confirm Abort Redemption"):
    confirmation = discord.ui.TextInput(
        label="Type 'ABORT' to confirm stopping",
        placeholder="ABORT",
        required=True,
        max_length=10,
        style=discord.TextStyle.short
    )
    reason = discord.ui.TextInput(
        label="Reason for stopping (Optional)",
        placeholder="e.g. wrong code or pausing",
        required=False,
        max_length=100,
        style=discord.TextStyle.short
    )

    def __init__(self, on_confirm):
        super().__init__()
        self.on_confirm = on_confirm

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation.value.strip().upper() != "ABORT":
            await interaction.response.send_message(
                "❌ Abort cancelled: You must type `ABORT` in the confirmation box.",
                ephemeral=True
            )
            return

        reason_str = self.reason.value.strip() if self.reason.value else None
        await self.on_confirm(interaction, reason=reason_str)


class SearchPlayerModal(discord.ui.Modal, title='Search / Edit Player'):
    query_input = discord.ui.TextInput(
        label='Enter Player Name, FID, or Alliance',
        placeholder='e.g. HimAlt or 117280427',
        min_length=2,
        max_length=50,
        required=True
    )

    def __init__(self, player_manager_cog):
        super().__init__()
        self.cog = player_manager_cog

    async def on_submit(self, interaction: discord.Interaction):
        query = self.query_input.value.strip()
        if hasattr(self.cog, "do_search_player"):
            await self.cog.do_search_player(interaction, query)
        elif callable(getattr(self.cog, "search_player", None)):
            await self.cog.search_player(interaction, query)
        elif hasattr(getattr(self.cog, "search_player", None), "callback"):
            await self.cog.search_player.callback(self.cog, interaction, query)
        else:
            await interaction.response.send_message("❌ Player search handler not found.", ephemeral=True)


class CustomCountdownModal(discord.ui.Modal, title='Custom Countdown'):
    seconds_input = discord.ui.TextInput(
        label='Seconds',
        placeholder='Enter number of seconds (e.g. 15)',
        min_length=1,
        max_length=3,
        required=True
    )

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        try:
            seconds = int(self.seconds_input.value.strip())
            if seconds <= 0 or seconds > 60:
                await interaction.response.send_message("❌ Please enter a number between 1 and 60 seconds.", ephemeral=True)
                return
            await interaction.response.send_message(f"🎙️ Starting {seconds}s custom countdown...", ephemeral=True)
            await play_voice_countdown(interaction, seconds)
        except ValueError:
            await interaction.response.send_message("❌ Invalid number entered. Please enter an integer.", ephemeral=True)


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


class PlayerBatchAddModal(discord.ui.Modal, title="Batch Add / Paste Players"):
    data_input = discord.ui.TextInput(
        label="Player List (Multi-line)",
        style=discord.TextStyle.paragraph,
        placeholder="# NOR\n117280427 278 Player1\n117280428 278 Player2\n# OvO\n118999999 Player3",
        required=True,
        max_length=4000
    )
    default_kid_input = discord.ui.TextInput(
        label="Default Kingdom ID",
        default="278",
        min_length=1,
        max_length=10,
        required=False
    )

    def __init__(self, db: PlayerDatabase):
        super().__init__()
        self.db = db

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        raw_text = self.data_input.value.strip()
        default_kid = self.default_kid_input.value.strip() or "278"

        players = self.db.parse_raw_player_text(raw_text, default_kingdom=default_kid)
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


# class MessageModal(discord.ui.Modal, title='Send a Message'):
#     message_input = discord.ui.TextInput(
#         label='What do you want to send?',
#         style=discord.TextStyle.paragraph,
#         placeholder='Type your message here...',
#         required=True,
#         max_length=500,
#     )
#
#     async def on_submit(self, interaction: discord.Interaction):
#         mention = f"<@1269222243569897513>"
#         full_message = f"{mention}\n<@{interaction.user.id}> says {self.message_input.value}"
#
#         await interaction.response.send_message(full_message)