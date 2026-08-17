import discord
from discord import app_commands
from discord.ext import commands

from utils.castle_battle_support import create_reinforcement_embed, time_to_reinforce


class BattleTactics(commands.Cog):
    """Cog for tactical combat tools, castle defense, and reinforcement timing."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="reinforcement-timing",
        description="Calculate exact timing to land garrison reinforcements between two enemy rallies"
    )
    @app_commands.describe(
        opponent_march_time="Enemy march time in seconds (e.g. 120)",
        gap_between_rallies="Seconds between the two enemy rally hits (e.g. 5)",
        user_march_time="Your reinforcement march time in seconds (e.g. 95)"
    )
    async def reinforcement_timing_slash(
        self,
        interaction: discord.Interaction,
        opponent_march_time: int,
        gap_between_rallies: int,
        user_march_time: int
    ):
        if opponent_march_time <= 0 or gap_between_rallies <= 0 or user_march_time <= 0:
            await interaction.response.send_message(
                "❌ All march and gap times must be positive integers.",
                ephemeral=True
            )
            return

        embed = create_reinforcement_embed(opponent_march_time, gap_between_rallies, user_march_time)
        await interaction.response.send_message(embed=embed)

    @commands.command(name="reinforce")
    async def reinforce_prefix(
        self,
        ctx: commands.Context,
        opponent_march_time: int,
        gap_between_rallies: int,
        user_march_time: int
    ):
        """Prefix command for calculating reinforcement timing."""
        if opponent_march_time <= 0 or gap_between_rallies <= 0 or user_march_time <= 0:
            await ctx.send("❌ All times must be positive integers.")
            return

        embed = create_reinforcement_embed(opponent_march_time, gap_between_rallies, user_march_time)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    print("BattleTactics cog loaded")
    await bot.add_cog(BattleTactics(bot))
