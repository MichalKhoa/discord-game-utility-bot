import time
from typing import Dict, Tuple, Optional
import discord
from discord import app_commands
from discord.ext import commands

from utils.roulette_views import RussianRouletteGame, RussianRouletteView, RouletteChallengeView, ASSETS_DIR

__all__ = ["RussianRouletteGame", "RussianRouletteView", "RouletteChallengeView", "ASSETS_DIR", "RussianRoulette", "setup"]


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

    def _validate_duel_target(self, interaction: discord.Interaction, opponent: discord.Member) -> Optional[str]:
        if not interaction.guild:
            return "❌ Duels can only be initiated inside a server channel."
        if opponent.id == interaction.user.id:
            return "❌ You cannot challenge yourself to a duel."
        if opponent.bot:
            return "❌ You cannot challenge a bot to a duel."
        if hasattr(opponent, "status") and opponent.status == discord.Status.offline:
            return f"❌ {opponent.display_name} is offline or invisible. You can only duel online members."
        if self.is_player_muted(interaction.channel_id, interaction.user.id):
            return "❌ You are currently muted from Russian Roulette and cannot start a duel."
        if self.is_player_muted(interaction.channel_id, opponent.id):
            return f"❌ {opponent.display_name} is currently muted from Russian Roulette."
        return None

    async def start_duel(self, interaction: discord.Interaction, opponent: discord.Member, chambers: int = 6, force: bool = False):
        err = self._validate_duel_target(interaction, opponent)
        if err:
            if interaction.response.is_done():
                await interaction.followup.send(err, ephemeral=True)
            else:
                await interaction.response.send_message(err, ephemeral=True)
            return

        if force:
            view = RussianRouletteView(
                self.bot,
                host=interaction.user,
                chamber_size=chambers,
                mode="standard",
                is_duel=True,
                opponent=opponent,
                is_forced_duel=True
            )
            embed, gif_file = view.get_embed()
            attachments = [gif_file] if gif_file else []
            if interaction.response.is_done():
                msg = await interaction.followup.send(embed=embed, files=attachments, view=view, wait=True)
            else:
                await interaction.response.send_message(embed=embed, files=attachments, view=view)
                msg = await interaction.original_response()
            view.message = msg
            view._start_turn_timer()
        else:
            challenge_view = RouletteChallengeView(
                self.bot,
                challenger=interaction.user,
                opponent=opponent,
                chamber_size=chambers
            )
            embed = challenge_view.get_challenge_embed()
            if interaction.response.is_done():
                msg = await interaction.followup.send(content=f"{opponent.mention}", embed=embed, view=challenge_view, wait=True)
            else:
                await interaction.response.send_message(content=f"{opponent.mention}", embed=embed, view=challenge_view)
                msg = await interaction.original_response()
            challenge_view.message = msg

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

    @app_commands.command(name="roulette", description="Start Russian Roulette (Multiplayer Lobby, LMS Battle Royale, or 1v1 Duel)")
    @app_commands.describe(
        chambers="Number of chambers in cylinder (default: 6, min: 2, max: 12)",
        mode="Game mode: Standard (Manual Turns) or LMS (Automated Battle Royale)",
        opponent="Optional player to challenge to a 1v1 duel",
        force="Force duel without acceptance (Challenger must take first 2 pulls!)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Standard (Manual Multiplayer Lobby)", value="standard"),
        app_commands.Choice(name="Last Man Standing (Automated Battle Royale)", value="lms")
    ])
    async def roulette_cmd(
        self,
        interaction: discord.Interaction,
        chambers: int = 6,
        mode: str = "standard",
        opponent: Optional[discord.Member] = None,
        force: bool = False
    ):
        if opponent:
            await self.start_duel(interaction, opponent=opponent, chambers=chambers, force=force)
        else:
            await self.start_game(interaction, chamber_size=chambers, mode=mode)

    @app_commands.command(name="duel", description="Challenge another user to a 1v1 Russian Roulette duel")
    @app_commands.describe(
        opponent="The player to challenge to a duel",
        chambers="Number of chambers in cylinder (default: 6, min: 2, max: 12)",
        force="Force duel without acceptance (Challenger must take first 2 pulls!)"
    )
    async def duel_cmd(
        self,
        interaction: discord.Interaction,
        opponent: discord.Member,
        chambers: int = 6,
        force: bool = False
    ):
        await self.start_duel(interaction, opponent=opponent, chambers=chambers, force=force)


async def setup(bot: commands.Bot):
    print("RussianRoulette cog loaded")
    await bot.add_cog(RussianRoulette(bot))
