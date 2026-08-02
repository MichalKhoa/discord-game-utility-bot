import discord
from discord import app_commands
from discord.ext import commands

import utils.redeem_code

import asyncio
import os
import aiohttp

DOC_ID = '13qeSSMJH3S4ArPj8B3SJ31UajjS5wIqmt8MYYTvBWhE'  # playerID.txt on GDisk
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_PLAYER_IDS = os.path.join(PROJECT_ROOT, "data", "playerIDs.txt")


class CodeRedeem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.redeem_lock = asyncio.Lock()
        self.log_file = os.path.join(PROJECT_ROOT, "data", "redeemed_codes.txt")
        self.running_tasks = set()
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

    def is_code_redeemed(self, code: str) -> bool:
        """Checks if the code exists in the local log file."""
        if not os.path.exists(self.log_file):
            return False
        with open(self.log_file, "r", encoding="utf-8") as f:
            redeemed_list = [line.strip().upper() for line in f.readlines()]
            return code.strip().upper() in redeemed_list

    def log_success(self, code: str):
        """Adds a successfully redeemed code to the log file."""
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"{code.strip().upper()}\n")

    @app_commands.command(name="redeem-for-all", description="Redeem codes (separated by ;) for in-game rewards!")
    @app_commands.describe(gift_code="The code(s) you want to redeem, separated by ;")
    async def redeem(self, interaction: discord.Interaction, gift_code: str):
        await self.redeem_code_for_all(interaction, gift_code)

    @app_commands.command(name="redeem-for-player", description="Redeem codes (separated by ;) for a single player ID!")
    @app_commands.describe(gift_code="The code(s) you want to redeem, separated by ;", player_id="The player's ID (FID)")
    async def redeem_single(self, interaction: discord.Interaction, gift_code: str, player_id: str):
        await self.redeem_code_for_player(interaction, gift_code, player_id)

    async def run_redeem(self, webhook_url, gift_codes, user_id):
        print(f"DEBUG: Starting run_redeem for {gift_codes}")
        async with self.redeem_lock:
            print("DEBUG: Acquired lock")
            try:
                print("DEBUG: Syncing player IDs from Google Doc public export URL")
                await asyncio.to_thread(utils.redeem_code.update_file_from_public_url, DOC_ID, LOCAL_PLAYER_IDS)

                results = []
                for code in gift_codes:
                    print(f"DEBUG: Starting redeem_for_all for {code}")
                    stats = await asyncio.to_thread(utils.redeem_code.redeem_for_all, code, LOCAL_PLAYER_IDS)
                    print(f"DEBUG: Finished redeem_for_all for {code}")
                    results.append(stats)

                    if stats.startswith("✅") or stats.startswith("Giftcode"):
                        self.log_success(code)

                combined_stats = "\n\n".join(results)
                async with aiohttp.ClientSession() as session:
                    webhook = discord.Webhook.from_url(webhook_url, session=session)
                    await webhook.send(f"<@{user_id}>\n" + combined_stats)
            except Exception as e:
                print(f"DEBUG: Exception in run_redeem: {e}")
                async with aiohttp.ClientSession() as session:
                    webhook = discord.Webhook.from_url(webhook_url, session=session)
                    await webhook.send(f"❌ Error during redemption: {e}")
            finally:
                try:
                    async with aiohttp.ClientSession() as session:
                        webhook = discord.Webhook.from_url(webhook_url, session=session)
                        await webhook.delete()
                except Exception as e:
                    print(f"DEBUG: Error deleting webhook: {e}")

    async def redeem_code_for_all(self, interaction: discord.Interaction, gift_code: str):
        print(f"DEBUG: redeem_code_for_all called with {gift_code}")
        try:
            codes = [c.strip().upper() for c in gift_code.split(';') if c.strip()]
            if not codes:
                await interaction.response.send_message("⚠️ No valid codes provided!", ephemeral=True)
                return

            await interaction.response.defer(thinking=True)

            if self.redeem_lock.locked():
                await interaction.followup.send("⚠️ Another redemption is currently in progress. Please try again later!")
                return

            valid_codes = []
            already_redeemed = []
            for code in codes:
                if self.is_code_redeemed(code):
                    already_redeemed.append(code)
                else:
                    valid_codes.append(code)

            if already_redeemed:
                await interaction.followup.send(
                    f"⚠️ The following codes have already been redeemed and will be skipped: {', '.join(already_redeemed)}",
                    ephemeral=True
                )

            if not valid_codes:
                await interaction.followup.send("⚠️ All provided codes have already been redeemed!", ephemeral=True)
                return

            await interaction.followup.send(f"🔢 Redeeming code(s) `{', '.join(valid_codes)}` for everyone. "
                                            f"Process might take longer to finish. I will ping you when done.")

            try:
                channel = interaction.channel
                if channel is None:
                    channel = await self.bot.fetch_channel(interaction.channel_id)

                if isinstance(channel, discord.Thread):
                    parent_channel = channel.parent
                    if parent_channel is None:
                        parent_channel = await self.bot.fetch_channel(channel.parent_id)
                    webhook = await parent_channel.create_webhook(name="GiftCodeRedeemBot")
                    webhook_url = f"{webhook.url}?thread_id={channel.id}"
                elif isinstance(channel, discord.DMChannel):
                    raise ValueError("Cannot run redeem-for-all in Direct Messages. Please run in a server channel.")
                else:
                    webhook = await channel.create_webhook(name="GiftCodeRedeemBot")
                    webhook_url = webhook.url

                print(f"DEBUG: Created webhook {webhook_url}")

                task = asyncio.create_task(self.run_redeem(webhook_url, valid_codes, interaction.user.id))
                self.running_tasks.add(task)
                task.add_done_callback(self.running_tasks.discard)
                print("DEBUG: Task created")
            except Exception as e:
                print(f"DEBUG: Error starting task: {e}")
                import traceback
                traceback.print_exc()
                await interaction.followup.send(f"⚠️ Failed to start redemption process: {e}")
        except Exception as e:
            print(f"DEBUG: Exception in redeem_code_for_all: {e}")
            import traceback
            traceback.print_exc()

    async def redeem_code_for_player(self, interaction: discord.Interaction, gift_code: str, player_id: str):
        print(f"DEBUG: redeem_code_for_player called with {gift_code} for {player_id}")

        codes = [c.strip().upper() for c in gift_code.split(';') if c.strip()]
        if not codes:
            await interaction.response.send_message("⚠️ No valid codes provided!", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            results = []
            for code in codes:
                redeem_result = await asyncio.to_thread(
                    utils.redeem_code.send_signed_post,
                    "gift_code",
                    {"fid": player_id, "cdk": code, "kid": "278"}
                )

                msg = redeem_result.get('msg', '').replace('.', '')
                if msg == "TIMEOUT RETRY":
                    print(f"Retrying single player for code {code}...")
                    retry_result = await asyncio.to_thread(utils.redeem_code.redeem_for_one, player_id, code, "278")
                    if retry_result:
                        redeem_result = retry_result
                        msg = retry_result.get('msg', '').replace('.', '')
                    else:
                        msg = "Failed"

                if "error" in redeem_result:
                    result_message = f"Error: {redeem_result['error']}"
                else:
                    result_message = utils.redeem_code.RESULT_MESSAGES.get(msg, msg or "Failed")

                results.append(f"🎁 **Code**: `{code}` 📊 **Result**: {result_message}")

            combined_results = "\n".join(results)
            await interaction.followup.send(
                f"👤 **Player ID**: `{player_id}` (Kingdom 278)\n" + combined_results
            )
        except Exception as e:
            print(f"DEBUG: Error in redeem_code_for_player: {e}")
            await interaction.followup.send(f"⚠️ Failed to redeem: {e}")


async def setup(bot: commands.Bot):
    print("CodeRedeem cog loaded")
    await bot.add_cog(CodeRedeem(bot))
