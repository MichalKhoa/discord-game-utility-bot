import discord
from discord import app_commands
from discord.ext import commands

from utils.roulette_views import RussianRouletteGame, RussianRouletteView, ASSETS_DIR

__all__ = ["RussianRouletteGame", "RussianRouletteView", "ASSETS_DIR", "RussianRoulette", "setup"]


class RussianRoulette(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def start_game(self, interaction: discord.Interaction, chamber_size: int = 6, mode: str = "standard"):
        view = RussianRouletteView(self.bot, host=interaction.user, chamber_size=chamber_size, mode=mode)
        embed, gif_file = view.get_embed()
        attachments = [gif_file] if gif_file else []
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, files=attachments, view=view)
        else:
            await interaction.response.send_message(embed=embed, files=attachments, view=view)

    @app_commands.command(name="roulette", description="Start Russian Roulette (Standard Sudden Death or Last Man Standing Battle Royale)")
    @app_commands.describe(
        chambers="Number of chambers in cylinder (default: 6, min: 2, max: 12)",
        mode="Game mode: Standard (Manual Turns) or LMS (Automated Battle Royale)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Standard (Manual Multiplayer Lobby)", value="standard"),
        app_commands.Choice(name="Last Man Standing (Automated Battle Royale)", value="lms")
    ])
    async def roulette_cmd(self, interaction: discord.Interaction, chambers: int = 6, mode: str = "standard"):
        await self.start_game(interaction, chamber_size=chambers, mode=mode)


async def setup(bot: commands.Bot):
    print("RussianRoulette cog loaded")
    await bot.add_cog(RussianRoulette(bot))
