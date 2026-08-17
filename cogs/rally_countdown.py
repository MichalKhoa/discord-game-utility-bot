import asyncio
import importlib

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import button

import utils.countdown
from utils.countdown import play_voice_countdown, get_or_connect_vc, stop_voice
from utils.views import RallyCountdownView

importlib.reload(utils.countdown)

class RallyCountdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="rally-countdown", description="Starts a voice countdown for rallies.")
    async def slash_countdown(self, interaction: discord.Interaction, count: int):
        await interaction.response.send_message(f"🎙️ Starting {count}s voice countdown...")
        await play_voice_countdown(interaction, count)

    @commands.command(name="rally")
    async def prefix_countdown(self, ctx: commands.Context, count: int = 10):
        await ctx.send(f"🎙️ Starting {count}s voice countdown...")
        await play_voice_countdown(ctx, count)

    @app_commands.command(name="rally-join", description="Pre-connects the bot to your voice channel for instant countdowns.")
    async def slash_join(self, interaction: discord.Interaction):
        vc, err = await get_or_connect_vc(interaction)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
        else:
            await interaction.response.send_message(f"🎙️ Connected to **{vc.channel.name}**! Instant countdowns ready.", ephemeral=True)

    @commands.command(name="join")
    async def prefix_join(self, ctx: commands.Context):
        vc, err = await get_or_connect_vc(ctx)
        if err:
            await ctx.send(err)
        else:
            await ctx.send(f"🎙️ Connected to **{vc.channel.name}**! Instant countdowns ready.")

    @app_commands.command(name="rally-stop", description="Disconnects the bot from the voice channel.")
    async def slash_stop(self, interaction: discord.Interaction):
        stopped = await stop_voice(interaction)
        if stopped:
            await interaction.response.send_message("⏹️ Disconnected from voice channel.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)

    @commands.command(name="stop", aliases=["leave"])
    async def prefix_stop(self, ctx: commands.Context):
        stopped = await stop_voice(ctx)
        if stopped:
            await ctx.send("⏹️ Disconnected from voice channel.")
        else:
            await ctx.send("❌ Bot is not connected to a voice channel.")

    @app_commands.command(name="rally-menu", description="Opens the Rally Countdown interactive menu.")
    async def rally_menu_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎙️ Rally Countdown Panel",
            description="Select a preset timer, join voice in advance, trigger a custom countdown, or disconnect.",
            color=discord.Color.og_blurple()
        )
        await interaction.response.send_message(embed=embed, view=RallyCountdownView(self.bot))

    @commands.command(name="rallymenu")
    async def rally_menu_prefix(self, ctx: commands.Context):
        embed = discord.Embed(
            title="🎙️ Rally Countdown Panel",
            description="Select a preset timer, join voice in advance, trigger a custom countdown, or disconnect.",
            color=discord.Color.og_blurple()
        )
        await ctx.send(embed=embed, view=RallyCountdownView(self.bot))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Auto-disconnects if all human members leave the voice channel."""
        if member.bot:
            return

        guild = member.guild
        vc = guild.voice_client
        if not vc or not vc.is_connected() or not vc.channel:
            return

        # Check if the member left the bot's channel
        if before.channel == vc.channel and after.channel != vc.channel:
            # Count remaining non-bot members
            humans = [m for m in vc.channel.members if not m.bot]
            if len(humans) == 0:
                print(f"Voice channel '{vc.channel.name}' in '{guild.name}' is empty. Auto-disconnecting bot.")
                await stop_voice(guild)


async def setup(bot):
    print("RallyCountdown cog loaded")
    await bot.add_cog(RallyCountdown(bot))