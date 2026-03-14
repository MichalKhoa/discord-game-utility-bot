import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import button


class Menu(commands.Cog):
    """

    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="menu", description="Opens the main menu.")
    async def menu(self, interaction: discord.Interaction):
        await self.open_menu(interaction)

    async def open_menu(self, interaction: discord.Interaction):
        embed = MainMenuEmbed(self.bot)
        view = MenuButtons(self.bot)

        await interaction.response.send_message(embed=embed, view=view)


class MainMenuEmbed(discord.Embed):
    def __init__(self, bot: commands.Bot):
        # Store the bot first!
        self.bot = bot

        super().__init__(
            title="Main Menu",
            description="*Hello there! Select a module below to get started.*",
            colour=discord.Colour.brand_red()
        )

        self.add_field(
            name="🎮 Games",
            value="> Challenge your friends to\n> interactive mini-games.",
            inline=True
        )
        self.add_field(
            name="🛠️ Utilities",
            value="> Access powerful server\n> management tools.",
            inline=True
        )

        # Now this will work because self.bot exists
        if self.bot.user:
            self.set_footer(
                text="Discord Games & Utility bot",
                icon_url=self.bot.user.display_avatar.url
            )


class MenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=600)
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
            value="> **A new KS gift code has been released?**\nRedeem it for everyone now (Please take note, that the process might take some time to finish.)"
        )
        await interaction.response.edit_message(embed=utility_menu_panel, view=UtilityMenuButtons(self.bot))


class GameMenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=600)
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
        super().__init__(timeout=600)
        self.bot = bot

    @discord.ui.button(label="Redeem a Gift Code for everyone", style=discord.ButtonStyle.primary)
    async def redeem_for_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redeem_cog = self.bot.get_cog("CodeRedeem")

        if redeem_cog:
            await interaction.response.send_modal(RedeemModal(redeem_cog))
        else:
            await interaction.response.send_message("CodeRedeem module error", ephemeral=True)


    # @discord.ui.button(label="Melody is a nerd", style=discord.ButtonStyle.danger)
    # async def dm_melody(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     mention = f"<@1269222243569897513>"
    #     await interaction.response.send_message(f"Hey {mention}, stop being so nerdy!")


    @discord.ui.button(label="Tag Melody with a message", style=discord.ButtonStyle.danger)
    async def tag_melody(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(MessageModal())


    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary)
    async def return_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = MainMenuEmbed(self.bot)
        view = MenuButtons(self.bot)
        await interaction.response.edit_message(embed=embed, view=view)


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


class MessageModal(discord.ui.Modal, title='Send a Message'):
    message_input = discord.ui.TextInput(
        label='What do you want to send?',
        style=discord.TextStyle.paragraph,
        placeholder='Type your message here...',
        required=True,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        mention = f"<@1269222243569897513>"
        full_message = f"{mention}\n{self.message_input.value}"

        await interaction.response.send_message(full_message)


async def setup(bot: commands.Bot):
    print("Menu cog loaded")
    await bot.add_cog(Menu(bot))
