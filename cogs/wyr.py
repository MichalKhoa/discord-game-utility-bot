import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks

from utils.embeds import WyrEmbed
from utils.views import WyrButtons


class Wyr(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def start_game(self, interaction: discord.Interaction):
        await self.start_wyr_game(interaction)

    async def start_wyr_game(self, interaction: discord.Interaction):
        # If the interaction was already responded to (from the 'New Question' button)
        # we use followup. If it's a fresh slash command, we defer.
        if not interaction.response.is_done():
            await interaction.response.defer()

        question = await self.bot.database.get_random_wyr_question()

        if not question:
            await interaction.followup.send("No questions available in the database.", ephemeral=True)
            return

        panel = WyrEmbed(question[0], question[1])
        # Pass the bot and this cog instance to the view
        view = WyrButtons(self.bot, self)

        message = await interaction.followup.send(embed=panel, view=view, wait=True)

        view.message = message
        view.update_panel.start()

    @app_commands.command(name="wyr", description="Would you rather? game")
    async def wyr(self, interaction: discord.Interaction):
        await self.start_game(interaction)


async def setup(bot):
    print("Wyr cog loaded")
    await bot.add_cog(Wyr(bot))
