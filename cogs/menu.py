import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks

class Menu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="menu", description="Opens the main menu.")
    async def menu(self, interaction: discord.Interaction):


async def setup(bot: commands.Bot):
    await bot.add_cog(Menu(bot))
