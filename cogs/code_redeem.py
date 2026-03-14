import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands

from utils.redeem_code import update_file_if_needed, redeem_for_all

DOC_ID = '13qeSSMJH3S4ArPj8B3SJ31UajjS5wIqmt8MYYTvBWhE' #playerID.txt on the GDisk

class CodeRedeem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Create a lock specifically for this Cog
        self.redeem_lock = asyncio.Lock()
        self.log_file = "redeemed_codes.txt"

    def is_code_redeemed(self, code: str) -> bool:
        """Checks if the code exists in the local log file."""
        if not os.path.exists(self.log_file):
            return False
        with open(self.log_file, "r") as f:
            redeemed_list = [line.strip() for line in f.readlines()] # .strip() removes newlines
            return code in redeemed_list

    def log_success(self, code: str):
        """Adds a successfully redeemed code to the log file."""
        with open(self.log_file, "a") as f:
            f.write(f"{code}\n")

    @app_commands.command(name="redeem-for-all", description="Redeem a code for in-game rewards!")
    @app_commands.describe(giftCode="The code you want to redeem")
    async def redeem(self, interaction: discord.Interaction, giftCode: str):
        await self.redeem_code_for_all(interaction, giftCode)

    async def redeem_code_for_all(self, interaction: discord.Interaction, giftCode: str):
        await interaction.response.defer(thinking=True)

        # Check if the lock is already held
        if self.redeem_lock.locked():
            await interaction.followup.send("⚠️ Another redemption is currently in progress. Please try again later!", ephemeral=True)

        # This 'async with' ensures only ONE person executes the block below at a time
        async with self.redeem_lock:
            try:
                if self.is_code_redeemed(giftCode):
                    await interaction.followup.send(f"⚠️ Code {giftCode} has already been redeemed!", ephemeral=True)
                    return
                await asyncio.to_thread(update_file_if_needed, DOC_ID, "playerIDs.txt")
                stats = await asyncio.to_thread(redeem_for_all, giftCode)
                await interaction.followup.send(f"✅ Done!\n{stats}")
                self.log_success(giftCode)
            except Exception as e:
                await interaction.followup.send(f"❌ Error: {e}")

async def setup(bot: commands.Bot):
    print("CodeRedeem cog loaded")
    await bot.add_cog(CodeRedeem(bot))


