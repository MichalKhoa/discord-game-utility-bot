import discord
from discord.ext import commands, tasks

from utils.embeds import MainMenuEmbed
from utils.modals import RedeemModal, RedeemSingleModal, CustomCountdownModal
from utils.countdown import play_voice_countdown


class MenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="Games", style=discord.ButtonStyle.primary)
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

    @discord.ui.button(label="Utilities", style=discord.ButtonStyle.primary)
    async def utility_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        utility_menu_panel = discord.Embed(
            title="Choose one of the options below:",
            colour=discord.Colour.yellow())
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


class GameMenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="Would you rather ...", style=discord.ButtonStyle.primary)
    async def wyr_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        wyr_cog = self.bot.get_cog("Wyr")

        if wyr_cog:
            await wyr_cog.start_wyr_game(interaction)
        else:
            await interaction.response.send_message("Wyr module error", ephemeral=True)

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary)
    async def return_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = MainMenuEmbed(self.bot)
        view = MenuButtons(self.bot)
        await interaction.response.edit_message(embed=embed, view=view)


class UtilityMenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="Redeem a Gift Code for everyone", style=discord.ButtonStyle.primary)
    async def redeem_for_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redeem_cog = self.bot.get_cog("CodeRedeem")

        if redeem_cog:
            await interaction.response.send_modal(RedeemModal(redeem_cog))
        else:
            await interaction.response.send_message("CodeRedeem module error", ephemeral=True)

    @discord.ui.button(label="Redeem for Single Player", style=discord.ButtonStyle.primary)
    async def redeem_for_player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redeem_cog = self.bot.get_cog("CodeRedeem")

        if redeem_cog:
            await interaction.response.send_modal(RedeemSingleModal(redeem_cog))
        else:
            await interaction.response.send_message("CodeRedeem module error", ephemeral=True)


    # @discord.ui.button(label="Melody is a nerd", style=discord.ButtonStyle.danger)
    # async def dm_melody(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     mention = f"<@1269222243569897513>"
    #     await interaction.response.send_message(f"Hey {mention}, stop being so nerdy!")

    @discord.ui.button(label="Rally Countdown", style=discord.ButtonStyle.primary)
    async def rally_countdown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎙️ Rally Countdown Panel",
            description="Select one of the preset timers below, trigger a custom countdown, or stop the voice client.",
            color=discord.Color.og_blurple()
        )
        await interaction.response.edit_message(embed=embed, view=RallyCountdownView(self.bot))

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary)
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

    @discord.ui.button(label="Custom Countdown", style=discord.ButtonStyle.success, row=1)
    async def custom_countdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomCountdownModal())

    @discord.ui.button(label="Stop / Disconnect", style=discord.ButtonStyle.danger, row=1)
    async def stop_countdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect(force=True)
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