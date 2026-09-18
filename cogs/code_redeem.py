import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List, Set

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
        self.pending_or_running_codes: Set[str] = set()

    def cog_unload(self):
        if hasattr(self, "auto_scan_loop") and self.auto_scan_loop.is_running():
            self.auto_scan_loop.cancel()

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
        if not self.auto_scan_loop.is_running():
            self.auto_scan_loop.start()
        asyncio.create_task(self._initial_startup_scan())

    async def _initial_startup_scan(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)
        try:
            await self.scan_and_redeem(days=7)
        except Exception as e:
            print(f"DEBUG: Error in initial startup scan: {e}")

    @tasks.loop(minutes=30)
    async def auto_scan_loop(self):
        await self.bot.wait_until_ready()
        try:
            await self.scan_and_redeem(days=1)
        except Exception as e:
            print(f"DEBUG: Error in auto_scan_loop: {e}")

    async def get_notification_channel(self, preferred_channel: Optional[discord.abc.Messageable] = None) -> Optional[discord.abc.Messageable]:
        """Resolves optimal channel for posting redemption progress and alerts."""
        cid_str = await self.db.get_setting("redeem_alert_channel_id")
        if cid_str and cid_str.isdigit():
            ch = self.bot.get_channel(int(cid_str))
            if not ch:
                try:
                    ch = await self.bot.fetch_channel(int(cid_str))
                except Exception:
                    pass
            if ch and hasattr(ch, "send"):
                return ch

        if preferred_channel and hasattr(preferred_channel, "guild") and preferred_channel.guild:
            if hasattr(preferred_channel, "permissions_for"):
                perms = preferred_channel.permissions_for(getattr(preferred_channel.guild, "me", None))
                if asyncio.iscoroutine(perms):
                    perms = await perms
                if getattr(perms, "send_messages", False):
                    return preferred_channel

        for guild in getattr(self.bot, "guilds", []):
            for ch in getattr(guild, "text_channels", []):
                perms = ch.permissions_for(getattr(guild, "me", None))
                if asyncio.iscoroutine(perms):
                    perms = await perms
                if getattr(perms, "send_messages", False) and "bot" in getattr(ch, "name", "").lower():
                    return ch

        return preferred_channel

    async def auto_redeem_codes(
        self,
        codes: List[str],
        source_message: Optional[discord.Message] = None,
        source_title: str = "Announcement"
    ):
        """Automatically initiates batch redemption for new unredeemed codes."""
        unredeemed = []
        for c in codes:
            c_clean = c.strip().upper()
            if not c_clean or c_clean in self.pending_or_running_codes:
                continue
            is_done = await self.db.is_code_redeemed(c_clean)
            if not is_done and c_clean not in unredeemed:
                unredeemed.append(c_clean)

        if not unredeemed:
            return

        for c in unredeemed:
            self.pending_or_running_codes.add(c)

        pref_ch = getattr(source_message, "channel", None) if source_message else None
        target_channel = await self.get_notification_channel(pref_ch)
        if not target_channel:
            target_channel = pref_ch

        owner_id = getattr(self.bot, "owner_id", None) or 210022124423741440

        alert_embed = discord.Embed(
            title="🎁 New Gift Code Auto-Redemption Triggered!",
            description=(
                f"**Detected Code(s)**: `{', '.join(unredeemed)}`\n"
                f"**Source**: {source_title}\n\n"
                f"⚡ **Automated batch redemption dispatched for all active players!**"
            ),
            colour=discord.Colour.green()
        )
        if source_message and hasattr(source_message, "jump_url"):
            alert_embed.add_field(name="🔗 Source Message", value=f"[Jump to Announcement]({source_message.jump_url})", inline=False)

        try:
            if target_channel and hasattr(target_channel, "send"):
                await target_channel.send(embed=alert_embed)
        except Exception as e:
            print(f"DEBUG: Failed to send auto-redeem alert embed: {e}")

        async def _execute_and_clean():
            try:
                await self.run_redeem(target_channel, unredeemed, user_id=owner_id)
            finally:
                for c in unredeemed:
                    self.pending_or_running_codes.discard(c)

        task = asyncio.create_task(_execute_and_clean())
        self.running_tasks.add(task)
        task.add_done_callback(self.running_tasks.discard)

    async def scan_and_redeem(self, days: int = 7) -> List[str]:
        """Scans watched channels for unredeemed codes and automatically redeems them."""
        watched = await self.db.get_watched_channels(default_channels=utils.code_detector.WATCHED_CHANNELS)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        found_codes = []

        for ch_id in watched:
            ch = self.bot.get_channel(ch_id)
            if not ch:
                try:
                    ch = await self.bot.fetch_channel(ch_id)
                except Exception:
                    continue

            perms = ch.permissions_for(ch.guild.me) if getattr(ch, "guild", None) else None
            if perms and not perms.read_message_history:
                continue

            try:
                async for msg in ch.history(limit=100, after=cutoff):
                    full_text = getattr(msg, "content", "") or ""
                    for emb in getattr(msg, "embeds", []):
                        if emb.title:
                            full_text += f"\n{emb.title}"
                        if emb.description:
                            full_text += f"\n{emb.description}"
                        for f in emb.fields:
                            full_text += f"\n{f.name} {f.value}"

                    candidates = utils.code_detector.extract_candidate_codes(full_text)
                    for code in candidates:
                        if code not in found_codes:
                            is_logged = await self.db.is_code_redeemed(code)
                            if not is_logged and code not in self.pending_or_running_codes:
                                found_codes.append(code)
            except Exception as e:
                print(f"DEBUG: Error scanning history in channel {ch_id}: {e}")

        if found_codes:
            print(f"DEBUG: scan_and_redeem found new unredeemed codes: {found_codes}")
            await self.auto_redeem_codes(found_codes, source_title=f"Background Channel Scan ({days}d)")

        return found_codes

    @commands.Cog.listener("on_message")
    async def on_announcement_message(self, message: discord.Message):
        if self.bot.user and message.author.id == self.bot.user.id:
            return
        await utils.code_detector.process_announcement_message(
            message,
            self.bot,
            self.db,
            auto_redeem_callback=self.auto_redeem_codes
        )

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
    @app_commands.describe(
        days="Number of past days to scan (1 to 90, default: 30)",
        auto_redeem="Automatically start batch redemption if new codes are found (default: True)"
    )
    async def scan_history_cmd(
        self,
        interaction: discord.Interaction,
        days: Optional[int] = 30,
        auto_redeem: Optional[bool] = True
    ):
        await interaction.response.defer(thinking=True)

        days = max(1, min(days or 30, 90))
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)

        new_codes_found = []
        already_redeemed_found = []
        channel_status = []

        watched = await self.db.get_watched_channels(default_channels=utils.code_detector.WATCHED_CHANNELS)
        for ch_id in watched:
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
                value=f"{codes_str}",
                inline=False
            )
            if auto_redeem:
                embed.add_field(
                    name="⚡ Automated Action",
                    value="Automatic batch redemption has started for all active players!",
                    inline=False
                )
            else:
                embed.add_field(
                    name="⚡ Quick Action",
                    value="*(Click button below to redeem)*",
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
            if auto_redeem:
                await interaction.followup.send(embed=embed)
                await self.auto_redeem_codes(new_codes_found, source_title=f"Manual Scan ({days} Days)")
            else:
                combined_code = ";".join(new_codes_found)
                view = utils.code_detector.DetectedCodeView(combined_code, self.bot)
                await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="redeem-set-channel", description="Set the Discord channel for automated gift code alerts & progress")
    @app_commands.describe(channel="The text channel where redemption updates should be posted")
    async def redeem_set_channel_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        is_owner = await self.bot.is_owner(interaction.user)
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild else False
        if not (is_owner or is_admin):
            await interaction.response.send_message("❌ You need `Manage Server` permissions to run this command.", ephemeral=True)
            return

        await self.db.set_setting("redeem_alert_channel_id", str(channel.id))
        embed = discord.Embed(
            title="✅ Redemption Alert Channel Configured",
            description=f"Automated gift code detections and redemption progress will post to {channel.mention}.",
            colour=discord.Colour.green()
        )
        await interaction.response.send_message(embed=embed)

    watch_group = app_commands.Group(name="redeem-watch-channel", description="Manage channels watched for gift codes")

    @watch_group.command(name="add", description="Add an announcement channel to watch for new gift codes")
    @app_commands.describe(channel="The channel to watch")
    async def watch_channel_add(self, interaction: discord.Interaction, channel: discord.TextChannel):
        is_owner = await self.bot.is_owner(interaction.user)
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild else False
        if not (is_owner or is_admin):
            await interaction.response.send_message("❌ You need `Manage Server` permissions to run this command.", ephemeral=True)
            return

        await self.db.add_watched_channel(channel.id, default_channels=utils.code_detector.WATCHED_CHANNELS)
        perms = channel.permissions_for(channel.guild.me) if channel.guild else None
        view_ok = perms.view_channel if perms else False
        read_ok = perms.read_message_history if perms else False
        perm_warning = ""
        if not (view_ok and read_ok):
            perm_warning = f"\n⚠️ **Warning**: Bot is missing permissions in {channel.mention}: `View Channel`={view_ok}, `Read History`={read_ok}."

        embed = discord.Embed(
            title="✅ Watched Channel Added",
            description=f"{channel.mention} (`{channel.id}`) is now monitored for gift codes.{perm_warning}",
            colour=discord.Colour.green()
        )
        await interaction.response.send_message(embed=embed)

    @watch_group.command(name="remove", description="Remove a channel from watched channels")
    @app_commands.describe(channel="The channel to stop watching")
    async def watch_channel_remove(self, interaction: discord.Interaction, channel: discord.TextChannel):
        is_owner = await self.bot.is_owner(interaction.user)
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild else False
        if not (is_owner or is_admin):
            await interaction.response.send_message("❌ You need `Manage Server` permissions to run this command.", ephemeral=True)
            return

        await self.db.remove_watched_channel(channel.id, default_channels=utils.code_detector.WATCHED_CHANNELS)
        embed = discord.Embed(
            title="🗑️ Watched Channel Removed",
            description=f"{channel.mention} (`{channel.id}`) was removed from watched channels.",
            colour=discord.Colour.orange()
        )
        await interaction.response.send_message(embed=embed)

    @watch_group.command(name="list", description="List all channels currently watched for gift codes")
    async def watch_channel_list(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        watched = await self.db.get_watched_channels(default_channels=utils.code_detector.WATCHED_CHANNELS)
        lines = []
        for cid in sorted(watched):
            ch = self.bot.get_channel(cid)
            if not ch:
                try:
                    ch = await self.bot.fetch_channel(cid)
                except Exception:
                    pass

            if ch:
                perms = ch.permissions_for(ch.guild.me) if getattr(ch, "guild", None) else None
                if perms and perms.view_channel and perms.read_message_history:
                    status = "✅ Accessible"
                elif perms and not perms.view_channel:
                    status = "❌ Missing `View Channel`"
                elif perms and not perms.read_message_history:
                    status = "⚠️ Missing `Read History`"
                else:
                    status = "⚠️ Check Permissions"
                g_name = ch.guild.name if getattr(ch, "guild", None) else "Unknown Server"
                lines.append(f"• <#{cid}> (`{cid}`) [{g_name}]: {status}")
            else:
                lines.append(f"• Channel ID `{cid}`: ❌ Channel Not Found / Inaccessible")

        alert_cid = await self.db.get_setting("redeem_alert_channel_id")
        alert_str = f"<#{alert_cid}>" if alert_cid else "Auto-detected / Bot channel"

        embed = discord.Embed(
            title="📡 Watched Announcement Channels",
            description="\n".join(lines) or "No channels configured.",
            colour=discord.Colour.gold()
        )
        embed.add_field(name="📢 Results / Progress Channel", value=alert_str, inline=False)
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
