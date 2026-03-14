import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import button

from utils import countdown
from utils.countdown import play_voice_countdown


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

async def setup(bot):
    print("RallyCountdown cog loaded")
    await bot.add_cog(RallyCountdown(bot))