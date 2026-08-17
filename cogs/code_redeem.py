import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

import utils.redeem_code

import asyncio
import os
import aiohttp

import databases.player_database
from databases.player_database import PlayerDatabase

DOC_ID = '13qeSSMJH3S4ArPj8B3SJ31UajjS5wIqmt8MYYTvBWhE'  # playerID.txt on GDisk
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_PLAYER_IDS = os.path.join(PROJECT_ROOT, "data", "players.db")
LEGACY_PLAYER_IDS = os.path.join(PROJECT_ROOT, "data", "playerIDs.txt")


def format_time(seconds: float) -> str:
    """Format seconds into readable min/sec string."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def build_batch_progress_embed(
    current_code: str,
    code_index: int,
    total_codes: int,
    processed: int,
    total: int,
    counters: dict,
    elapsed: float
) -> discord.Embed:
    """Builds a dynamic real-time progress embed with visual bar and ETA."""
    percent = (processed / total * 100) if total > 0 else 0
    bar = utils.redeem_code.make_progress_bar(processed, total, length=16)

    if processed > 0 and total > processed:
        rate = processed / max(1.0, elapsed)
        eta_seconds = (total - processed) / max(0.1, rate)
        eta_str = format_time(eta_seconds)
    elif processed >= total and total > 0:
        eta_str = "Finishing..."
    else:
        eta_str = "Calculating..."

    embed = discord.Embed(
        title=f"⏳ Batch Redemption in Progress ({code_index}/{total_codes})",
        colour=discord.Colour.gold()
    )
    embed.description = (
        f"**Active Code**: `{current_code}`\n\n"
        f"`{bar}` **{percent:.1f}%** ({processed}/{total} players)\n\n"
        f"• 🟢 **Success**: `{counters.get('success', 0)}`\n"
        f"• 📦 **Already Claimed**: `{counters.get('already_redeemed', 0)}`\n"
        f"• 🟡 **Wrong Kingdom / Flagged**: `{counters.get('wrong_kingdom', 0)}`\n"
        f"• ⚠️ **Rate Limited**: `{counters.get('rate_limited', 0)}`\n\n"
        f"⏱️ **Elapsed**: `{format_time(elapsed)}`  •  ⏳ **Est. Remaining**: `~{eta_str}`"
    )
    embed.set_footer(text="Live updates every ~4s • You will be pinged when finished.")
    return embed


class ConfirmRedeemView(discord.ui.View):
    def __init__(self, author_id: int, on_confirm, on_cancel=None):
        super().__init__(timeout=90)
        self.author_id = author_id
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This confirmation is only for the command author.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Proceed Anyway", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await self.on_confirm(interaction)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Redemption cancelled.", embed=None, view=self)
        if self.on_cancel:
            await self.on_cancel(interaction)


class CodeRedeem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = PlayerDatabase()
        self.redeem_lock = asyncio.Lock()
        self.running_tasks = set()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.db.init_db()

    @app_commands.command(name="redeem-for-all", description="Redeem codes (separated by ;) for in-game rewards!")
    @app_commands.describe(gift_code="The code(s) you want to redeem, separated by ;")
    async def redeem(self, interaction: discord.Interaction, gift_code: str):
        await self.redeem_code_for_all(interaction, gift_code)

    @app_commands.command(name="redeem-for-player", description="Redeem codes (separated by ;) for a single player ID!")
    @app_commands.describe(
        gift_code="The code(s) you want to redeem, separated by ;",
        player_id="The player's ID (FID)",
        kingdom_id="The Kingdom ID (leave empty to use saved player kingdom or 278)"
    )
    async def redeem_single(self, interaction: discord.Interaction, gift_code: str, player_id: str, kingdom_id: Optional[str] = None):
        await self.redeem_code_for_player(interaction, gift_code, player_id, kingdom_id)

    @app_commands.command(name="redeem-history", description="Check recently redeemed gift codes and timestamps")
    async def redeem_history(self, interaction: discord.Interaction):
        await interaction.response.defer()
        codes = await self.db.get_redeemed_codes(limit=25)
        if not codes:
            await interaction.followup.send("ℹ️ No redeemed codes logged in the database yet.")
            return

        embed = discord.Embed(title="📜 Redeemed Codes History", colour=discord.Colour.gold())
        lines = []
        for c in codes:
            code_str = c.get("code")
            date_str = str(c.get("redeemed_at", "")).split('.')[0]
            lines.append(f"• `{code_str}` — *Redeemed on {date_str}*")
        embed.description = "\n".join(lines)
        await interaction.followup.send(embed=embed)

    async def run_redeem(self, channel: discord.abc.Messageable, gift_codes: List[str], user_id: int):
        print(f"DEBUG: Starting run_redeem for {gift_codes}")
        async with self.redeem_lock:
            print("DEBUG: Acquired lock")
            progress_msg = None
            try:
                await self.db.init_db()

                init_embed = discord.Embed(
                    title="⏳ Initializing Batch Redemption...",
                    description=f"Preparing to redeem `{', '.join(gift_codes)}`...",
                    colour=discord.Colour.gold()
                )
                progress_msg = await channel.send(embed=init_embed)

                results = []
                for idx, code in enumerate(gift_codes, start=1):
                    progress_state = {
                        "current_code": code,
                        "code_index": idx,
                        "total_codes": len(gift_codes),
                        "processed": 0,
                        "total": 0,
                        "counters": {},
                        "elapsed": 0.0,
                    }
                    stop_updater = asyncio.Event()

                    def on_progress(processed, total, counters, is_done, elapsed):
                        progress_state["processed"] = processed
                        progress_state["total"] = total
                        progress_state["counters"] = counters
                        progress_state["elapsed"] = elapsed

                    async def update_display():
                        while not stop_updater.is_set():
                            try:
                                if progress_state["total"] > 0:
                                    embed = build_batch_progress_embed(
                                        current_code=progress_state["current_code"],
                                        code_index=progress_state["code_index"],
                                        total_codes=progress_state["total_codes"],
                                        processed=progress_state["processed"],
                                        total=progress_state["total"],
                                        counters=progress_state["counters"],
                                        elapsed=progress_state["elapsed"]
                                    )
                                    if progress_msg:
                                        await progress_msg.edit(embed=embed)
                            except Exception as e:
                                print(f"Progress update error: {e}")
                            await asyncio.sleep(4.0)

                    updater_task = asyncio.create_task(update_display())

                    try:
                        print(f"DEBUG: Starting redeem_for_all for {code}")
                        stats = await asyncio.to_thread(
                            utils.redeem_code.redeem_for_all,
                            code,
                            LOCAL_PLAYER_IDS,
                            "278",
                            on_progress
                        )
                        print(f"DEBUG: Finished redeem_for_all for {code}")
                        results.append(stats)

                        if stats.startswith("✅") or stats.startswith("Giftcode"):
                            await self.db.log_redeemed_code(code, redeemed_by=user_id)
                    finally:
                        stop_updater.set()
                        updater_task.cancel()

                # Build final summary embed
                final_embed = discord.Embed(
                    title="✅ Batch Redemption Completed!",
                    colour=discord.Colour.green()
                )
                final_embed.description = "\n\n".join(results)
                final_embed.set_footer(text="All player accounts processed successfully.")

                if progress_msg:
                    await progress_msg.edit(embed=final_embed)
                else:
                    await channel.send(embed=final_embed)

                await channel.send(f"<@{user_id}> ✅ Finished redeeming gift code(s): `{', '.join(gift_codes)}`!")

            except Exception as e:
                print(f"DEBUG: Exception in run_redeem: {e}")
                import traceback
                traceback.print_exc()
                err_embed = discord.Embed(
                    title="❌ Redemption Error",
                    description=f"An error occurred during the batch process:\n`{e}`",
                    colour=discord.Colour.red()
                )
                if progress_msg:
                    await progress_msg.edit(embed=err_embed)
                else:
                    await channel.send(embed=err_embed)

    async def _execute_batch_redemption(self, interaction: discord.Interaction, codes: List[str]):
        """Dispatches background redemption task after confirmation."""
        if self.redeem_lock.locked():
            await interaction.followup.send("⚠️ Another redemption is currently in progress. Please try again later!")
            return

        await interaction.followup.send(
            f"🔢 Initiating redemption for `{', '.join(codes)}`.\n"
            f"Live progress updates will appear below and you will be pinged when finished."
        )

        try:
            channel = interaction.channel
            if channel is None:
                channel = await self.bot.fetch_channel(interaction.channel_id)

            task = asyncio.create_task(self.run_redeem(channel, codes, interaction.user.id))
            self.running_tasks.add(task)
            task.add_done_callback(self.running_tasks.discard)
        except Exception as e:
            print(f"DEBUG: Error starting task: {e}")
            await interaction.followup.send(f"⚠️ Failed to start redemption process: {e}")

    async def redeem_code_for_all(self, interaction: discord.Interaction, gift_code: str):
        print(f"DEBUG: redeem_code_for_all called with {gift_code}")
        try:
            codes = [c.strip().upper() for c in gift_code.split(';') if c.strip()]
            if not codes:
                await interaction.response.send_message("⚠️ No valid codes provided!", ephemeral=True)
                return

            await interaction.response.defer(thinking=True)

            # Check database for previously redeemed codes
            already_redeemed = []
            for code in codes:
                info = await self.db.is_code_redeemed(code)
                if info:
                    already_redeemed.append((code, info.get("redeemed_at", "earlier date")))

            if already_redeemed:
                embed = discord.Embed(
                    title="⚠️ Code(s) Already Redeemed Previously",
                    description=(
                        "The following gift code(s) have already been redeemed in the past:\n\n"
                        + "\n".join(f"• **`{c}`** (Redeemed: `{str(d).split('.')[0]}`)" for c, d in already_redeemed)
                        + "\n\n**Do you really want to proceed and redeem again?**"
                    ),
                    colour=discord.Colour.yellow()
                )

                async def on_confirm(btn_interaction: discord.Interaction):
                    await self._execute_batch_redemption(interaction, codes)

                view = ConfirmRedeemView(interaction.user.id, on_confirm=on_confirm)
                await interaction.followup.send(embed=embed, view=view)
                return

            await self._execute_batch_redemption(interaction, codes)

        except Exception as e:
            print(f"DEBUG: Exception in redeem_code_for_all: {e}")
            import traceback
            traceback.print_exc()

    async def _execute_single_redemption(self, interaction: discord.Interaction, codes: List[str], player_id: str, kingdom_id: Optional[str] = None):
        target_kid = kingdom_id
        player_info = await self.db.get_player(player_id)
        if not target_kid:
            if player_info and player_info.get("kid"):
                target_kid = player_info["kid"]
            else:
                target_kid = "278"

        player_name = player_info.get("name") if player_info else ""
        display_name = f" ({player_name})" if player_name else ""

        results = []
        for code in codes:
            redeem_result = await asyncio.to_thread(
                utils.redeem_code.send_signed_post,
                "gift_code",
                {"fid": player_id, "cdk": code, "kid": target_kid}
            )

            msg = redeem_result.get('msg', '').replace('.', '')
            if msg == "TIMEOUT RETRY":
                retry_result = await asyncio.to_thread(utils.redeem_code.redeem_for_one, player_id, code, target_kid)
                if retry_result:
                    redeem_result = retry_result
                    msg = retry_result.get('msg', '').replace('.', '')
                else:
                    msg = "Failed"

            if "error" in redeem_result:
                result_message = f"Error: {redeem_result['error']}"
            else:
                result_message = utils.redeem_code.RESULT_MESSAGES.get(msg, msg or "Failed")
                if msg in ("SUCCESS", "SAME TYPE EXCHANGE", "RECEIVED"):
                    await self.db.log_redeemed_code(code, redeemed_by=interaction.user.id)

            results.append(f"🎁 **Code**: `{code}` 📊 **Result**: {result_message}")

        combined_results = "\n".join(results)
        await interaction.followup.send(
            f"👤 **Player ID**: `{player_id}`{display_name} (Kingdom {target_kid})\n" + combined_results
        )

    async def redeem_code_for_player(self, interaction: discord.Interaction, gift_code: str, player_id: str, kingdom_id: Optional[str] = None):
        print(f"DEBUG: redeem_code_for_player called with {gift_code} for {player_id}")

        codes = [c.strip().upper() for c in gift_code.split(';') if c.strip()]
        if not codes:
            await interaction.response.send_message("⚠️ No valid codes provided!", ephemeral=True)
            return

        await interaction.response.defer(thinking=True)

        try:
            already_redeemed = []
            for code in codes:
                info = await self.db.is_code_redeemed(code)
                if info:
                    already_redeemed.append((code, info.get("redeemed_at", "earlier date")))

            if already_redeemed:
                embed = discord.Embed(
                    title="⚠️ Code(s) Already Redeemed Previously",
                    description=(
                        "The following gift code(s) have already been redeemed in the past:\n\n"
                        + "\n".join(f"• **`{c}`** (Redeemed: `{str(d).split('.')[0]}`)" for c, d in already_redeemed)
                        + "\n\n**Do you really want to proceed for this player?**"
                    ),
                    colour=discord.Colour.yellow()
                )

                async def on_confirm(btn_interaction: discord.Interaction):
                    await self._execute_single_redemption(interaction, codes, player_id, kingdom_id)

                view = ConfirmRedeemView(interaction.user.id, on_confirm=on_confirm)
                await interaction.followup.send(embed=embed, view=view)
                return

            await self._execute_single_redemption(interaction, codes, player_id, kingdom_id)

        except Exception as e:
            print(f"DEBUG: Error in redeem_code_for_player: {e}")
            await interaction.followup.send(f"⚠️ Failed to redeem: {e}")


async def setup(bot: commands.Bot):
    print("CodeRedeem cog loaded")
    await bot.add_cog(CodeRedeem(bot))
