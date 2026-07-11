import asyncio
import importlib

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import button

import utils.countdown
from utils.countdown import play_voice_countdown
from utils.views import RallyCountdownView

importlib.reload(utils.countdown)

class RallyCountdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rally-countdown")
    async def slash_countdown(self, interaction: discord.Interaction, count: int):
        await interaction.response.send_message(f"🎙️ Joining voice for {count}s countdown...")
        # Call the helper function we made above
        await play_voice_countdown(interaction, count)

    @commands.command(name="rally")
    async def prefix_countdown(self, ctx: commands.Context, count: int = 10):
        await ctx.send(f"🎙️ Starting {count}s voice countdown...")
        await play_voice_countdown(ctx, count)

    @app_commands.command(name="rally-menu", description="Opens the Rally Countdown interactive menu.")
    async def rally_menu_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎙️ Rally Countdown Panel",
            description="Select one of the preset timers below, trigger a custom countdown, or stop the voice client.",
            color=discord.Color.og_blurple()
        )
        await interaction.response.send_message(embed=embed, view=RallyCountdownView(self.bot))

    @commands.command(name="rallymenu")
    async def rally_menu_prefix(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎙️ Rally Countdown Panel",
            description="Select one of the preset timers below, trigger a custom countdown, or stop the voice client.",
            color=discord.Color.og_blurple()
        )
        await ctx.send(embed=embed, view=RallyCountdownView(self.bot))

async def setup(bot):
    print("RallyCountdown cog loaded")
    await bot.add_cog(RallyCountdown(bot))