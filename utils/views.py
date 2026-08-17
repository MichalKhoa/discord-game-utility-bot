import discord
from discord.ext import commands, tasks

from utils.embeds import MainMenuEmbed
from utils.modals import RedeemModal, RedeemSingleModal, CustomCountdownModal, SearchPlayerModal
from utils.countdown import play_voice_countdown, get_or_connect_vc, stop_voice
from databases.player_database import PlayerDatabase
from cogs.player_manager import PlayerAddModal, PlayerBatchAddModal, PlayerListView


class MenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="Games", style=discord.ButtonStyle.primary, emoji="🎮")
    async def games_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        games_menu_panel = discord.Embed(
            title="Choose one the games below:",
            colour=discord.Colour.og_blurple())
        games_menu_panel.add_field(
            name="🤷 Would you rather ...",
            value="> **The ultimate icebreaker!**\nPick between two impossible scenarios and see if your friends agree. Perfect for starting debates!",
            inline=True
        )
        await interaction.response.edit_message(embed=games_menu_panel, view=GameMenuButtons(self.bot))

    @discord.ui.button(label="Players", style=discord.ButtonStyle.primary, emoji="👥")
    async def players_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        player_menu_panel = discord.Embed(
            title="👥 Player Registry & Management",
            description="Manage game player accounts, kingdom IDs, and warning flags.",
            colour=discord.Colour.teal()
        )
        player_menu_panel.add_field(
            name="📋 View Player List",
            value="> Browse all registered players with pagination and filters.",
            inline=False
        )
        player_menu_panel.add_field(
            name="➕ Add / 📝 Batch Import / 🔍 Search & Edit",
            value="> Register single players, paste multi-line batches, or search/edit.",
            inline=False
        )
        player_menu_panel.add_field(
            name="⚠️ Flagged / 📊 Stats / 📥 Export",
            value="> Review problematic accounts, kingdom stats, or download CSV.",
            inline=False
        )
        await interaction.response.edit_message(embed=player_menu_panel, view=PlayerMenuButtons(self.bot))

    @discord.ui.button(label="Utilities", style=discord.ButtonStyle.primary, emoji="🛠️")
    async def utility_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        utility_menu_panel = discord.Embed(
            title="Choose one of the options below:",
            colour=discord.Colour.yellow())
        utility_menu_panel.add_field(
            name="🪙 Redeem codes for everyone",
            value="> Redeem gift code for all registered accounts with verification.",
            inline=False
        )
        utility_menu_panel.add_field(
            name="👤 Redeem code for one player",
            value="> Redeem gift code for a single player ID instantly.",
            inline=False
        )
        utility_menu_panel.add_field(
            name="📜 Redeem History",
            value="> Check recently redeemed codes and timestamps.",
            inline=False
        )
        utility_menu_panel.add_field(
            name="🎙️ Rally Countdown Panel",
            value="> Open the interactive voice countdown panel for rallies.",
            inline=False
        )
        await interaction.response.edit_message(embed=utility_menu_panel, view=UtilityMenuButtons(self.bot))


class PlayerMenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot
        self.db = PlayerDatabase()

    @discord.ui.button(label="View Player List", style=discord.ButtonStyle.primary, emoji="📋", row=0)
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

    @discord.ui.button(label="Batch Import", style=discord.ButtonStyle.success, emoji="📝", row=0)
    async def batch_import_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerBatchAddModal(self.db))

    @discord.ui.button(label="Search / Edit", style=discord.ButtonStyle.primary, emoji="🔍", row=0)
    async def search_player_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pm_cog = self.bot.get_cog("PlayerManager")
        if pm_cog:
            await interaction.response.send_modal(SearchPlayerModal(pm_cog))
        else:
            await interaction.response.send_message("PlayerManager module error", ephemeral=True)

    @discord.ui.button(label="Flagged Players", style=discord.ButtonStyle.danger, emoji="⚠️", row=1)
    async def flagged_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pm_cog = self.bot.get_cog("PlayerManager")
        if pm_cog:
            await pm_cog.flagged_players(interaction)
        else:
            await interaction.response.send_message("PlayerManager module error", ephemeral=True)

    @discord.ui.button(label="Player Stats", style=discord.ButtonStyle.secondary, emoji="📊", row=1)
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pm_cog = self.bot.get_cog("PlayerManager")
        if pm_cog:
            await pm_cog.player_stats(interaction)
        else:
            await interaction.response.send_message("PlayerManager module error", ephemeral=True)

    @discord.ui.button(label="Export CSV", style=discord.ButtonStyle.secondary, emoji="📥", row=1)
    async def export_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pm_cog = self.bot.get_cog("PlayerManager")
        if pm_cog:
            await pm_cog.export_csv_cmd(interaction)
        else:
            await interaction.response.send_message("PlayerManager module error", ephemeral=True)

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary, emoji="◀", row=2)
    async def return_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = MainMenuEmbed(self.bot)
        view = MenuButtons(self.bot)
        await interaction.response.edit_message(embed=embed, view=view)


class UtilityMenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="Redeem for Everyone", style=discord.ButtonStyle.primary, emoji="🪙", row=0)
    async def redeem_for_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redeem_cog = self.bot.get_cog("CodeRedeem")
        if redeem_cog:
            await interaction.response.send_modal(RedeemModal(redeem_cog))
        else:
            await interaction.response.send_message("CodeRedeem module error", ephemeral=True)

    @discord.ui.button(label="Redeem for Single Player", style=discord.ButtonStyle.primary, emoji="👤", row=0)
    async def redeem_for_player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redeem_cog = self.bot.get_cog("CodeRedeem")
        if redeem_cog:
            await interaction.response.send_modal(RedeemSingleModal(redeem_cog))
        else:
            await interaction.response.send_message("CodeRedeem module error", ephemeral=True)

    @discord.ui.button(label="Redeem History", style=discord.ButtonStyle.secondary, emoji="📜", row=1)
    async def redeem_history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redeem_cog = self.bot.get_cog("CodeRedeem")
        if redeem_cog:
            await redeem_cog.redeem_history(interaction)
        else:
            await interaction.response.send_message("CodeRedeem module error", ephemeral=True)

    @discord.ui.button(label="Rally Countdown", style=discord.ButtonStyle.primary, emoji="🎙️", row=1)
    async def rally_countdown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎙️ Rally Countdown Panel",
            description="Select one of the preset timers below, trigger a custom countdown, or stop the voice client.",
            color=discord.Color.og_blurple()
        )
        await interaction.response.edit_message(embed=embed, view=RallyCountdownView(self.bot))

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary, emoji="◀", row=2)
    async def return_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = MainMenuEmbed(self.bot)
        view = MenuButtons(self.bot)
        await interaction.response.edit_message(embed=embed, view=view)


class WyrButtons(discord.ui.View):
    def __init__(self, bot, cog_instance): # Accept bot and cog
        super().__init__(timeout=43200)
        self.bot = bot
        self.cog = cog_instance
        self.voter_A = set()
        self.voter_B = set()
        self.message = None

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary, custom_id="wyr_a")
    async def button_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.voter_B:
            self.voter_B.remove(interaction.user.id)
        self.voter_A.add(interaction.user.id)
        await interaction.response.defer()

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary, custom_id="wyr_b")
    async def button_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.voter_A:
            self.voter_A.remove(interaction.user.id)
        self.voter_B.add(interaction.user.id)
        await interaction.response.defer()

    @discord.ui.button(label="New question", style=discord.ButtonStyle.secondary, custom_id="new_question")
    async def new_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Stop the current background loop before starting a new one
        self.update_panel.stop()

        # Disable current buttons so people don't click twice while loading
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        # Call the start_game method from the Cog
        await self.cog.start_wyr_game(interaction)

    @tasks.loop(seconds=3)
    async def update_panel(self):
        if self.message:
            try:
                panel = self.message.embeds[0]
                panel.set_field_at(0, name="Votes", value=f"A: {len(self.voter_A)} | B: {len(self.voter_B)}")
                await self.message.edit(embed=panel)
            except Exception as e:
                print(f"Loop error: {e}")
                self.update_panel.stop()

    async def on_timeout(self):
        self.update_panel.stop()
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)


class RallyCountdownView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="6s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_6(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 6s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 6)

    @discord.ui.button(label="8s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_8(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 8s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 8)

    @discord.ui.button(label="10s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 10s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 10)

    @discord.ui.button(label="12s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_12(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 12s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 12)

    @discord.ui.button(label="14s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_14(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 14s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 14)

    @discord.ui.button(label="Join Voice", style=discord.ButtonStyle.success, row=1)
    async def join_voice_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, err = await get_or_connect_vc(interaction)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
        else:
            await interaction.response.send_message(f"🎙️ Connected to **{vc.channel.name}**! Instant countdowns ready.", ephemeral=True)

    @discord.ui.button(label="Custom Countdown", style=discord.ButtonStyle.primary, row=1)
    async def custom_countdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomCountdownModal())

    @discord.ui.button(label="Stop / Disconnect", style=discord.ButtonStyle.danger, row=1)
    async def stop_countdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        stopped = await stop_voice(interaction)
        if stopped:
            await interaction.response.send_message("⏹️ Stopped countdown and disconnected.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary, row=1)
    async def return_to_utilities(self, interaction: discord.Interaction, button: discord.ui.Button):
        utility_menu_panel = discord.Embed(
            title="Choose one of the options below:",
            colour=discord.Colour.yellow()
        )
        utility_menu_panel.add_field(
            name="🪙 Redeem codes for everyone",
            value="> **A new KS gift code has been released?**\nRedeem it for everyone now (Please take note, that the process might take some time to finish.)",
            inline=False
        )
        utility_menu_panel.add_field(
            name="👤 Redeem code for one player",
            value="> Redeem a KS gift code for a single player ID instantly.",
            inline=False
        )
        utility_menu_panel.add_field(
            name="🎙️ Rally Countdown Panel",
            value="> Open the interactive voice countdown panel for rallies.",
            inline=False
        )
        await interaction.response.edit_message(embed=utility_menu_panel, view=UtilityMenuButtons(self.bot))