import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List

import utils.redeem_code
import utils.code_detector

import asyncio
import threading
import datetime
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


class ConfirmAbortModal(discord.ui.Modal, title="🛑 Confirm Abort Redemption"):
    confirmation = discord.ui.TextInput(
        label="Type 'ABORT' to confirm stopping",
        placeholder="ABORT",
        required=True,
        max_length=10,
        style=discord.TextStyle.short
    )
    reason = discord.ui.TextInput(
        label="Reason for stopping (Optional)",
        placeholder="e.g. wrong code or pausing",
        required=False,
        max_length=100,
        style=discord.TextStyle.short
    )

    def __init__(self, on_confirm):
        super().__init__()
        self.on_confirm = on_confirm

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation.value.strip().upper() != "ABORT":
            await interaction.response.send_message(
                "❌ Abort cancelled: You must type `ABORT` in the confirmation box.",
                ephemeral=True
            )
            return

        reason_str = self.reason.value.strip() if self.reason.value else None
        await self.on_confirm(interaction, reason=reason_str)


class BatchProgressView(discord.ui.View):
    """View with a button to open abort confirmation modal."""
    def __init__(self, author_id: int, on_stop):
        super().__init__(timeout=7200)
        self.author_id = author_id
        self.on_stop = on_stop

    @discord.ui.button(label="Stop Redemption", style=discord.ButtonStyle.danger, emoji="🛑")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_owner = await interaction.client.is_owner(interaction.user)
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild else False
        if interaction.user.id != self.author_id and not (is_owner or is_admin):
            await interaction.response.send_message("❌ Only the command author or server admins can stop this redemption.", ephemeral=True)
            return

        async def handle_modal_confirm(modal_interaction: discord.Interaction, reason: Optional[str] = None):
            button.disabled = True
            button.label = "Stopping..."
            try:
                if interaction.message:
                    await interaction.message.edit(view=self)
            except Exception:
                pass
            await self.on_stop(modal_interaction, reason=reason)

        modal = ConfirmAbortModal(on_confirm=handle_modal_confirm)
        await interaction.response.send_modal(modal)


class CodeRedeem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = PlayerDatabase()
        self.redeem_lock = asyncio.Lock()
        self.running_tasks = set()
        self.current_cancel_event: Optional[threading.Event] = None
        self.active_author_id: Optional[int] = None
        self.stopped_by_user: Optional[discord.abc.User] = None
        self.stop_reason: Optional[str] = None

    def stop_current_redemption(self, user: Optional[discord.abc.User] = None, reason: Optional[str] = None) -> bool:
        """Signals active batch redemption to abort."""
        if self.current_cancel_event and not self.current_cancel_event.is_set():
            self.stopped_by_user = user
            self.stop_reason = reason
            self.current_cancel_event.set()
            return True
        return False

    @commands.Cog.listener()
    async def on_ready(self):
        await self.db.init_db()

    @commands.Cog.listener("on_message")
    async def on_announcement_message(self, message: discord.Message):
        if self.bot.user and message.author.id == self.bot.user.id:
            return
        await utils.code_detector.process_announcement_message(message, self.bot, self.db)

    @app_commands.command(name="redeem-for-all", description="Redeem codes (separated by ;) for in-game rewards!")
    @app_commands.describe(gift_code="The code(s) you want to redeem, separated by ;")
    async def redeem(self, interaction: discord.Interaction, gift_code: str):
        await self.redeem_code_for_all(interaction, gift_code)

    @app_commands.command(name="redeem-stop", description="Stop the currently active batch redemption process")
    async def stop_redeem_cmd(self, interaction: discord.Interaction):
        if not self.redeem_lock.locked() or not self.current_cancel_event:
            await interaction.response.send_message("ℹ️ No batch redemption is currently running.", ephemeral=True)
            return

        is_owner = await self.bot.is_owner(interaction.user)
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild else False
        if interaction.user.id != self.active_author_id and not (is_owner or is_admin):
            await interaction.response.send_message("❌ Only the command author or server admins can stop this redemption.", ephemeral=True)
            return

        async def handle_modal_confirm(modal_interaction: discord.Interaction, reason: Optional[str] = None):
            stopped = self.stop_current_redemption(user=modal_interaction.user, reason=reason)
            reason_msg = f" (Reason: `{reason}`)" if reason else ""
            if stopped:
                await modal_interaction.response.send_message(f"🛑 Batch redemption is being stopped by {modal_interaction.user.mention}{reason_msg}...")
            else:
                await modal_interaction.response.send_message("ℹ️ Redemption is already stopping or finished.", ephemeral=True)

        modal = ConfirmAbortModal(on_confirm=handle_modal_confirm)
        await interaction.response.send_modal(modal)

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

    @app_commands.command(
        name="redeem-scan-history",
        description="Scan watched announcement channels for gift codes posted in recent history"
    )
    @app_commands.describe(days="Number of past days to scan (1 to 90, default: 30)")
    async def scan_history_cmd(self, interaction: discord.Interaction, days: Optional[int] = 30):
        await interaction.response.defer(thinking=True)

        days = max(1, min(days or 30, 90))
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

        new_codes_found = []
        already_redeemed_found = []
        channel_status = []

        for ch_id in utils.code_detector.WATCHED_CHANNELS:
            channel = self.bot.get_channel(ch_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(ch_id)
                except Exception as e:
                    channel_status.append(f"• <#{ch_id}>: ❌ Inaccessible (`{e}`)")
                    continue

            # Check permissions
            perms = channel.permissions_for(channel.guild.me) if channel.guild else None
            if perms and not perms.read_message_history:
                channel_status.append(f"• <#{ch_id}>: ❌ Missing `Read Message History` permission")
                continue

            try:
                msg_count = 0
                async for msg in channel.history(limit=200, after=cutoff):
                    msg_count += 1
                    full_text = msg.content or ""
                    for emb in msg.embeds:
                        if emb.title:
                            full_text += f"\n{emb.title}"
                        if emb.description:
                            full_text += f"\n{emb.description}"
                        for f in emb.fields:
                            full_text += f"\n{f.name} {f.value}"

                    extracted = utils.code_detector.extract_candidate_codes(full_text)
                    for code in extracted:
                        is_logged = await self.db.is_code_redeemed(code)
                        if is_logged:
                            if code not in already_redeemed_found:
                                already_redeemed_found.append(code)
                        else:
                            if code not in new_codes_found:
                                new_codes_found.append(code)

                channel_status.append(f"• <#{ch_id}>: ✅ Scanned {msg_count} messages")
            except Exception as e:
                channel_status.append(f"• <#{ch_id}>: ⚠️ Error scanning history (`{e}`)")

        embed = discord.Embed(
            title=f"🔍 Announcement History Scan ({days} Days)",
            colour=discord.Colour.green() if new_codes_found else discord.Colour.gold()
        )

        embed.add_field(
            name="📡 Channel Access Status",
            value="\n".join(channel_status) or "No channels configured",
            inline=False
        )

        if new_codes_found:
            codes_str = ", ".join(f"`{c}`" for c in new_codes_found)
            embed.add_field(
                name="🎁 New Unredeemed Codes Detected",
                value=f"{codes_str}\n*(Click button below to redeem)*",
                inline=False
            )
        else:
            embed.add_field(
                name="🎁 New Unredeemed Codes",
                value="None found in scanned window.",
                inline=False
            )

        if already_redeemed_found:
            embed.add_field(
                name="📦 Previously Redeemed Codes Found",
                value=", ".join(f"`{c}`" for c in already_redeemed_found),
                inline=False
            )

        if new_codes_found:
            combined_code = ";".join(new_codes_found)
            view = utils.code_detector.DetectedCodeView(combined_code, self.bot)
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)


    async def send_with_webhook_fallback(
        self,
        channel: discord.abc.Messageable,
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        bot_name: str = "GiftCodeRedeemBot",
        user_id: Optional[int] = None
    ):
        """Attempts sending via channel webhook for custom bot identity; gracefully falls back to channel.send() and DM."""
        if hasattr(channel, "create_webhook") and not isinstance(channel, (discord.DMChannel, discord.GroupChannel)):
            try:
                webhook = None
                if isinstance(channel, discord.Thread):
                    parent = channel.parent or await self.bot.fetch_channel(channel.parent_id)
                    webhook = await parent.create_webhook(name=bot_name)
                    webhook_url = f"{webhook.url}?thread_id={channel.id}"
                else:
                    webhook = await channel.create_webhook(name=bot_name)
                    webhook_url = webhook.url

                async with aiohttp.ClientSession() as session:
                    wh = discord.Webhook.from_url(webhook_url, session=session)
                    await wh.send(content=content, embed=embed)

                if webhook:
                    try:
                        await webhook.delete()
                    except Exception:
                        pass
                return
            except Exception as wh_err:
                print(f"DEBUG: Webhook delivery failed ({wh_err}), falling back to direct channel message.")

        # Fallback to direct channel send
        try:
            await channel.send(content=content, embed=embed)
        except (discord.Forbidden, discord.HTTPException) as pe:
            print(f"DEBUG: Channel send failed ({pe}).")
            if user_id:
                try:
                    user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                    if user:
                        await user.send(content=content, embed=embed)
                except Exception as dm_err:
                    print(f"DEBUG: DM delivery failed ({dm_err}).")

    async def run_redeem(
        self,
        channel: discord.abc.Messageable,
        gift_codes: List[str],
        user_id: int,
        interaction: Optional[discord.Interaction] = None
    ):
        print(f"DEBUG: Starting run_redeem for {gift_codes}")
        async with self.redeem_lock:
            print("DEBUG: Acquired lock")
            self.current_cancel_event = threading.Event()
            self.active_author_id = user_id
            self.stopped_by_user = None
            progress_msg = None

            async def handle_stop(btn_interaction: discord.Interaction, reason: Optional[str] = None):
                stopped = self.stop_current_redemption(user=btn_interaction.user, reason=reason)
                reason_msg = f" (Reason: `{reason}`)" if reason else ""
                if stopped:
                    await btn_interaction.response.send_message(f"🛑 Stopping batch redemption{reason_msg}...", ephemeral=True)
                else:
                    await btn_interaction.response.send_message("ℹ️ Redemption is already stopping or finished.", ephemeral=True)

            progress_view = BatchProgressView(author_id=user_id, on_stop=handle_stop)

            try:
                await self.db.init_db()

                init_embed = discord.Embed(
                    title="⏳ Initializing Batch Redemption...",
                    description=f"Preparing to redeem `{', '.join(gift_codes)}`...",
                    colour=discord.Colour.gold()
                )

                if interaction:
                    try:
                        progress_msg = await interaction.followup.send(embed=init_embed, view=progress_view, wait=True)
                    except Exception as ie:
                        print(f"DEBUG: Interaction followup send failed ({ie}), trying channel.send")

                if progress_msg is None:
                    try:
                        progress_msg = await channel.send(embed=init_embed, view=progress_view)
                    except (discord.Forbidden, discord.HTTPException) as pe:
                        print(f"DEBUG: Channel send failed ({pe}), continuing batch redemption in background...")

                results = []
                was_cancelled = False
                for idx, code in enumerate(gift_codes, start=1):
                    if self.current_cancel_event.is_set():
                        was_cancelled = True
                        break

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
                                if progress_state["total"] > 0 and progress_msg:
                                    embed = build_batch_progress_embed(
                                        current_code=progress_state["current_code"],
                                        code_index=progress_state["code_index"],
                                        total_codes=progress_state["total_codes"],
                                        processed=progress_state["processed"],
                                        total=progress_state["total"],
                                        counters=progress_state["counters"],
                                        elapsed=progress_state["elapsed"]
                                    )
                                    await progress_msg.edit(embed=embed, view=progress_view)
                            except (discord.Forbidden, discord.NotFound, discord.HTTPException) as e:
                                print(f"DEBUG: Progress update notice: {e}")
                            except Exception as e:
                                print(f"DEBUG: Progress update error: {e}")
                            await asyncio.sleep(4.0)

                    updater_task = asyncio.create_task(update_display())

                    try:
                        print(f"DEBUG: Starting redeem_for_all for {code}")
                        stats = await asyncio.to_thread(
                            utils.redeem_code.redeem_for_all,
                            code,
                            LOCAL_PLAYER_IDS,
                            "278",
                            on_progress,
                            self.current_cancel_event
                        )
                        print(f"DEBUG: Finished redeem_for_all for {code}")
                        results.append(stats)

                        if stats.startswith("✅") or stats.startswith("Giftcode") or stats.startswith("⏹️"):
                            await self.db.log_redeemed_code(code, redeemed_by=user_id)

                        if self.current_cancel_event.is_set() or "⏹️" in stats:
                            was_cancelled = True
                            break
                    finally:
                        stop_updater.set()
                        updater_task.cancel()

                # Disable button
                for item in progress_view.children:
                    item.disabled = True

                # Build final summary embed
                if was_cancelled or self.current_cancel_event.is_set():
                    stopped_by_str = f" by {self.stopped_by_user.mention}" if self.stopped_by_user else ""
                    if self.stop_reason:
                        stopped_by_str += f" (Reason: `{self.stop_reason}`)"
                    final_embed = discord.Embed(
                        title=f"🛑 Batch Redemption Stopped{stopped_by_str}",
                        colour=discord.Colour.orange()
                    )
                    final_embed.description = "\n\n".join(results) or "Redemption was stopped before completion."
                    final_embed.set_footer(text="Redemption stopped by user request.")
                else:
                    final_embed = discord.Embed(
                        title="✅ Batch Redemption Completed!",
                        colour=discord.Colour.green()
                    )
                    final_embed.description = "\n\n".join(results)
                    final_embed.set_footer(text="All player accounts processed successfully.")

                if progress_msg:
                    try:
                        await progress_msg.edit(embed=final_embed, view=progress_view)
                    except Exception:
                        await self.send_with_webhook_fallback(channel, embed=final_embed, user_id=user_id)
                else:
                    await self.send_with_webhook_fallback(channel, embed=final_embed, user_id=user_id)

                status_word = "stopped" if (was_cancelled or self.current_cancel_event.is_set()) else "finished"
                await self.send_with_webhook_fallback(
                    channel,
                    content=f"<@{user_id}> 📢 Batch redemption for `{', '.join(gift_codes)}` {status_word}!",
                    user_id=user_id
                )

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
                    try:
                        await progress_msg.edit(embed=err_embed, view=None)
                    except Exception:
                        await self.send_with_webhook_fallback(channel, embed=err_embed, user_id=user_id)
                else:
                    await self.send_with_webhook_fallback(channel, embed=err_embed, user_id=user_id)
            finally:
                self.current_cancel_event = None
                self.active_author_id = None
                self.stopped_by_user = None
                self.stop_reason = None

    async def _execute_batch_redemption(self, interaction: discord.Interaction, codes: List[str]):
        """Dispatches background redemption task after confirmation."""
        if self.redeem_lock.locked():
            await interaction.followup.send("⚠️ Another redemption is currently in progress. Please try again later!")
            return

        try:
            channel = interaction.channel
            if channel is None:
                channel = await self.bot.fetch_channel(interaction.channel_id)

            task = asyncio.create_task(self.run_redeem(channel, codes, interaction.user.id, interaction=interaction))
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
