import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import MainMenuEmbed
from utils.views import MenuButtons

class Menu(commands.Cog):
    """Cog for interactive multi-module main menu."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="menu", description="Opens the main menu.")
    async def menu(self, interaction: discord.Interaction):
        await self.open_menu(interaction)

    async def open_menu(self, interaction: discord.Interaction):
        embed = MainMenuEmbed(self.bot)
        view = MenuButtons(self.bot)

        if interaction.response.is_done():
            msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            await interaction.response.send_message(embed=embed, view=view)
            msg = await interaction.original_response()
        view.message = msg


async def setup(bot: commands.Bot):
    print("Menu cog loaded")
    await bot.add_cog(Menu(bot))
