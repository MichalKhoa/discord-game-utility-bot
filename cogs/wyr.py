import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import WyrEmbed
from utils.views import WyrButtons


class Wyr(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def start_game(self, interaction: discord.Interaction):
        await self.start_wyr_game(interaction)

    async def start_wyr_game(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()

        question = await self.bot.database.get_random_wyr_question()
        if not question:
            await interaction.followup.send("❌ No questions available in the database.", ephemeral=True)
            return

        view = WyrButtons(self.bot, self, question)
        embed = view.get_embed()

        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        view.message = message

    @app_commands.command(name="wyr", description="Play 'Would you rather?' with live voting and stats")
    async def wyr(self, interaction: discord.Interaction):
        await self.start_game(interaction)


async def setup(bot: commands.Bot):
    print("Wyr cog loaded")
    await bot.add_cog(Wyr(bot))
