import time
from typing import Dict, Tuple
import discord
from discord import app_commands
from discord.ext import commands

from utils.roulette_views import RussianRouletteGame, RussianRouletteView, ASSETS_DIR

__all__ = ["RussianRouletteGame", "RussianRouletteView", "ASSETS_DIR", "RussianRoulette", "setup"]


class RussianRoulette(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.muted_users: Dict[Tuple[int, int], float] = {}  # (channel_id, user_id) -> expiry_timestamp

    def mute_player(self, channel_id: int, user_id: int, duration_seconds: float = 120.0):
        """Mutes an eliminated player in a specific channel for duration_seconds."""
        now = time.time()
        self.muted_users = {k: exp for k, exp in self.muted_users.items() if exp > now}
        self.muted_users[(channel_id, user_id)] = now + duration_seconds

    def is_player_muted(self, channel_id: int, user_id: int) -> bool:
        """Checks if a player is currently muted in a channel."""
        expiry = self.muted_users.get((channel_id, user_id))
        if not expiry:
            return False
        if time.time() > expiry:
            self.muted_users.pop((channel_id, user_id), None)
            return False
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if self.is_player_muted(message.channel.id, message.author.id):
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

    async def start_game(self, interaction: discord.Interaction, chamber_size: int = 6, mode: str = "standard"):
        view = RussianRouletteView(self.bot, host=interaction.user, chamber_size=chamber_size, mode=mode)
        embed, gif_file = view.get_embed()
        attachments = [gif_file] if gif_file else []
        if interaction.response.is_done():
            msg = await interaction.followup.send(embed=embed, files=attachments, view=view, wait=True)
        else:
            await interaction.response.send_message(embed=embed, files=attachments, view=view)
            msg = await interaction.original_response()
        view.message = msg

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
