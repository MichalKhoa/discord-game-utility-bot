import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks


class Menu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="menu", description="Opens the main menu.")
    async def menu(self, interaction: discord.Interaction):
        await self.open_menu(interaction)

    async def open_menu(self, interaction: discord.Interaction):
        # menu_panel = discord.Embed(
        #     title="Choose one of the options below:",
        #     # Use \n to make sure these appear on separate lines
        #     description="🎮 **Games**\n🛠️ **Utilities**",
        #     colour=discord.Colour.brand_red()
        # )

        menu_panel = discord.Embed(
            title="Main Menu",
            description="*Hello there! Select a module below to get started.*",
            colour=discord.Colour.brand_red()
        )

        # Using fields creates a structured grid look
        menu_panel.add_field(
            name="🎮 Games",
            value="> Challenge your friends to\n> interactive mini-games.",
            inline=True
        )
        menu_panel.add_field(
            name="🛠️ Utilities",
            value="> Access powerful server\n> management tools.",
            inline=True
        )

        # Adding a small thumbnail (like your bot's icon) makes it feel branded
        # menu_panel.set_thumbnail(url=self.bot.user.display_avatar.url)

        # A footer adds a nice finishing touch
        menu_panel.set_footer(text="Discord Games & Utility bot", icon_url=self.bot.user.display_avatar.url)

        # Ensure the class name matches exactly: MenuButtons vs Menu_Buttons
        view = MenuButtons(self.bot)

        await interaction.response.send_message(embed=menu_panel, view=view)

class MenuButtons(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=600)
        self.bot = bot

    @discord.ui.button(label="Games", style=discord.ButtonStyle.primary)
    async def games_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        games_menu_panel = discord.Embed(
            title="Choose one the games below:",
            description="⁉️ Would you rather ... ?"
                        "TBA...",
            colour=discord.Colour.og_blurple()
        )
        await interaction.response.edit_message(embed=games_menu_panel, view=GameMenuButtons(self.bot))

    @discord.ui.button(label="Utilities", style=discord.ButtonStyle.primary)
    async def utility_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        utility_menu_panel = discord.Embed(
            title="Choose one of the options below:",
            description="KS Redeem"
                        "TBA"
        )
        await interaction.response.edit_message(embed=utility_menu_panel)

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
        menu_panel = discord.Embed(
            title="Choose one of the options below:",
            description="🎮 **Games**\n🛠️ **Utilities**",
            colour=discord.Colour.brand_red()
        )
        view = MenuButtons(self.bot)
        await interaction.response.edit_message(embed=menu_panel, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Menu(bot))
