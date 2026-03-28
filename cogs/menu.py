import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import button

from utils.embeds import MainMenuEmbed
from utils.views import MenuButtons


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


async def setup(bot: commands.Bot):
    print("Menu cog loaded")
    await bot.add_cog(Menu(bot))
