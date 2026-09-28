import os
import asyncio
import inspect
import random
import discord
from discord.ext import commands
from typing import List, Dict, Optional, Tuple


ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "roulette")


class RussianRouletteGame:
    def __init__(self, chamber_size: int = 6, mode: str = "standard", is_forced_duel: bool = False):
        self.chamber_size = max(2, min(chamber_size, 12))
        self.mode: str = mode  # "standard" (sudden death lobby) or "lms" (battle royale)
        self.is_forced_duel: bool = is_forced_duel
        self.forced_pulls_taken: int = 0
        self.players: List[discord.Member | discord.User] = []
        self.alive_players: List[discord.Member | discord.User] = []
        self.eliminated_players: List[discord.Member | discord.User] = []
        self.bullet_chamber: int = random.randint(1, self.chamber_size)
        self.current_chamber: int = 1
        self.turn_index: int = 0
        self.round_number: int = 1
        self.started: bool = False
        self.game_over: bool = False
        self.winner: Optional[discord.Member | discord.User] = None
        self.victim: Optional[discord.Member | discord.User] = None
        self.last_action_msg: str = self._get_initial_action_msg()

    def _get_initial_action_msg(self) -> str:
        if self.mode == "lms":
            return "👑 **Last Man Standing Lobby**! Players join, then Host clicks **Start Battle Royale**."
        return "🔫 Cylinder loaded! Click **Pull Trigger** (sequential) or **Spin & Fire** (randomize)."

    def reset(self):
        self.bullet_chamber = random.randint(1, self.chamber_size)
        self.current_chamber = 1
        self.turn_index = 0
        self.round_number = 1
        self.started = False if len(self.players) <= 1 else True
        self.game_over = False
        self.winner = None
        self.victim = None
        self.alive_players = list(self.players)
        self.eliminated_players = []
        if self.mode == "lms":
            self.last_action_msg = f"👑 LMS Lobby reset! {len(self.players)} players ready for Battle Royale."
        elif len(self.players) == 2:
            self.last_action_msg = f"🔄 Duel rematched! {self.players[0].mention} vs {self.players[1].mention}."
        else:
            self.last_action_msg = f"🔄 Cylinder spun! 1 live round hidden in {self.chamber_size} chambers."

    def start_lms_game(self) -> bool:
        if len(self.players) < 2:
            return False
        self.started = True
        self.alive_players = list(self.players)
        self.eliminated_players = []
        self.round_number = 1
        self.bullet_chamber = random.randint(1, self.chamber_size)
        self.current_chamber = 1
        self.turn_index = 0
        self.game_over = False
        self.winner = None
        self.victim = None
        self.last_action_msg = f"🔥 **Battle Royale Commenced!** {len(self.alive_players)} survivors enter Round 1."
        return True

    def start_next_round(self):
        self.round_number += 1
        self.bullet_chamber = random.randint(1, self.chamber_size)
        self.current_chamber = 1
        self.victim = None
        if self.alive_players:
            self.turn_index = self.turn_index % len(self.alive_players)
        self.last_action_msg = f"🔄 **Round {self.round_number}** begins! Cylinder reloaded for {len(self.alive_players)} survivors."

    def pull_trigger(self, player: discord.Member | discord.User) -> Tuple[bool, str]:
        """Pulls trigger sequentially on the current chamber."""
        chamber = self.current_chamber
        is_hit = (chamber == self.bullet_chamber)

        if is_hit:
            self.victim = player
            if self.mode == "lms":
                if player in self.alive_players:
                    self.alive_players.remove(player)
                if player not in self.eliminated_players:
                    self.eliminated_players.append(player)

                if len(self.alive_players) <= 1:
                    self.game_over = True
                    self.winner = self.alive_players[0] if self.alive_players else None
                    if self.winner:
                        msg = f"💥 **BANG!** Chamber `{chamber}/{self.chamber_size}` fired! {player.mention} was eliminated!\n\n👑 **{self.winner.mention} IS THE LAST MAN STANDING!**"
                    else:
                        msg = f"💥 **BANG!** Chamber `{chamber}/{self.chamber_size}` fired! {player.mention} was eliminated! No survivors remain."
                else:
                    msg = f"💥 **BANG!** Chamber `{chamber}/{self.chamber_size}` fired! {player.mention} was eliminated! (`{len(self.alive_players)}` survivors remain)"
            else:
                self.game_over = True
                if len(self.players) == 2:
                    survivor = self.players[1] if player.id == self.players[0].id else self.players[0]
                    self.winner = survivor
                    msg = f"💥 **BANG!** Chamber `{chamber}/{self.chamber_size}` fired! {player.mention} was eliminated!\n\n🏆 **{survivor.mention} WINS THE DUEL!**"
                else:
                    msg = f"💥 **BANG!** Chamber `{chamber}/{self.chamber_size}` fired! {player.mention} was eliminated!"

            self.last_action_msg = msg
            return True, msg
        else:
            self.current_chamber += 1
            if self.current_chamber > self.chamber_size:
                self.current_chamber = 1
                self.bullet_chamber = random.randint(1, self.chamber_size)

            remaining = self.chamber_size - self.current_chamber + 1
            msg = f"💨 ***Click!*** Chamber `{chamber}/{self.chamber_size}` was empty! {player.mention} survived! (`{remaining}` chamber{'s' if remaining != 1 else ''} left)"

            if self.is_forced_duel and self.forced_pulls_taken < 1:
                self.forced_pulls_taken += 1
                self.turn_index = 0
                msg += f"\n⚠️ **Rule of Force:** {player.mention} survived pull 1/2 and must pull again!"
            elif self.is_forced_duel and self.forced_pulls_taken == 1:
                self.forced_pulls_taken += 1
                self.is_forced_duel = False
                self.turn_index = 1
                opponent = self.players[1] if len(self.players) > 1 else player
                msg += f"\n🛡️ **Rule of Force Satisfied:** {player.mention} survived both pulls! Turn passes to {opponent.mention}!"
            else:
                active_pool = self.alive_players if (self.mode == "lms" and self.started) else self.players
                if len(active_pool) > 1:
                    self.turn_index = (self.turn_index + 1) % len(active_pool)

            self.last_action_msg = msg
            return False, msg

    def spin_and_pull(self, player: discord.Member | discord.User) -> Tuple[bool, str]:
        """Spins the cylinder to a random position and immediately pulls the trigger."""
        self.bullet_chamber = random.randint(1, self.chamber_size)
        self.current_chamber = 1
        is_hit = (self.current_chamber == self.bullet_chamber)

        if is_hit:
            self.victim = player
            if self.mode == "lms":
                if player in self.alive_players:
                    self.alive_players.remove(player)
                if player not in self.eliminated_players:
                    self.eliminated_players.append(player)

                if len(self.alive_players) <= 1:
                    self.game_over = True
                    self.winner = self.alive_players[0] if self.alive_players else None
                    if self.winner:
                        msg = f"🌀💨 *Spin... Spin...* 💥 **BANG!** {player.mention} was eliminated!\n\n👑 **{self.winner.mention} IS THE LAST MAN STANDING!**"
                    else:
                        msg = f"🌀💨 *Spin... Spin...* 💥 **BANG!** {player.mention} was eliminated! No survivors remain."
                else:
                    msg = f"🌀💨 *Spin... Spin...* 💥 **BANG!** {player.mention} was eliminated! (`{len(self.alive_players)}` survivors remain)"
            else:
                self.game_over = True
                if len(self.players) == 2:
                    survivor = self.players[1] if player.id == self.players[0].id else self.players[0]
                    self.winner = survivor
                    msg = f"🌀💨 *Spin... Spin...* 💥 **BANG!** Cylinder landed on the live round! {player.mention} was eliminated!\n\n🏆 **{survivor.mention} WINS THE DUEL!**"
                else:
                    msg = f"🌀💨 *Spin... Spin...* 💥 **BANG!** Cylinder landed on the live round! {player.mention} was eliminated!"

            self.last_action_msg = msg
            return True, msg
        else:
            self.current_chamber += 1
            remaining = self.chamber_size - self.current_chamber + 1
            msg = f"🌀💨 *Spin... Spin...* 💨 ***Click!*** Safe! {player.mention} survived the spin! (`{remaining}` chamber{'s' if remaining != 1 else ''} left)"

            if self.is_forced_duel and self.forced_pulls_taken < 1:
                self.forced_pulls_taken += 1
                self.turn_index = 0
                msg += f"\n⚠️ **Rule of Force:** {player.mention} survived pull 1/2 and must pull again!"
            elif self.is_forced_duel and self.forced_pulls_taken == 1:
                self.forced_pulls_taken += 1
                self.is_forced_duel = False
                self.turn_index = 1
                opponent = self.players[1] if len(self.players) > 1 else player
                msg += f"\n🛡️ **Rule of Force Satisfied:** {player.mention} survived both pulls! Turn passes to {opponent.mention}!"
            else:
                active_pool = self.alive_players if (self.mode == "lms" and self.started) else self.players
                if len(active_pool) > 1:
                    self.turn_index = (self.turn_index + 1) % len(active_pool)

            self.last_action_msg = msg
            return False, msg


class RussianRouletteView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        host: discord.Member | discord.User,
        chamber_size: int = 6,
        mode: str = "standard",
        is_duel: bool = False,
        opponent: Optional[discord.Member | discord.User] = None,
        is_forced_duel: bool = False,
    ):
        super().__init__(timeout=3600)
        self.bot = bot
        self.host = host
        self.is_duel = is_duel
        self.is_forced_duel = is_forced_duel
        self.opponent = opponent
        self.game = RussianRouletteGame(chamber_size=chamber_size, mode=mode, is_forced_duel=is_forced_duel)
        self.game.players.append(host)
        self.game.alive_players.append(host)
        if is_duel and opponent:
            self.game.players.append(opponent)
            self.game.alive_players.append(opponent)
            self.game.started = True
            if is_forced_duel:
                self.game.last_action_msg = (
                    f"⚔️ **FORCED DUEL!** {host.mention} forced {opponent.mention} into Russian Roulette!\n"
                    f"⚠️ **Rule of Force:** {host.mention} must take the **first TWO pulls**!"
                )
            else:
                self.game.last_action_msg = (
                    f"⚔️ **DUEL COMMENCED!** {host.mention} vs {opponent.mention}!\n"
                    f"🎲 {host.mention} takes the first shot."
                )
        self._is_running: bool = False
        self.message: Optional[discord.Message] = None
        self._turn_task: Optional[asyncio.Task] = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self.update_buttons()

    def _start_turn_timer(self):
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
        if self.is_duel and self.game.started and not self.game.game_over:
            self._turn_task = asyncio.create_task(self._turn_timer_coro())

    async def _turn_timer_coro(self):
        try:
            await asyncio.sleep(60.0)
            if self.game.game_over or not self.game.started:
                return
            await self._auto_pull_turn()
        except asyncio.CancelledError:
            pass

    async def _auto_pull_turn(self):
        if self.game.game_over or not self.game.started or len(self.game.players) < 2:
            return
        current_player = self.game.players[self.game.turn_index]
        is_hit, msg = self.game.pull_trigger(current_player)
        if is_hit:
            ch_id = self.message.channel.id if self.message else None
            self._mute_if_eliminated(ch_id, current_player.id)
        self.game.last_action_msg = f"⏱️ *Time's up!* Trigger auto-fired for {current_player.mention}!\n" + msg
        self.update_buttons()
        embed, gif_file = self.get_embed()
        files = [gif_file] if gif_file else []
        await self._repost_view_message(embed=embed, attachments=files)
        if not self.game.game_over:
            self._start_turn_timer()

    async def on_timeout(self):
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
        for btn in self.children:
            btn.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass

    def update_buttons(self):
        if self._is_running:
            for btn in self.children:
                btn.disabled = True
            return

        is_lms = (self.game.mode == "lms")
        self.trigger_btn.disabled = is_lms or self.game.game_over
        self.spin_btn.disabled = is_lms or self.game.game_over

        if self.is_duel:
            self.start_lms_btn.disabled = True
            self.join_btn.disabled = True
            self.mode_btn.disabled = True
            self.reload_btn.disabled = not self.game.game_over
        else:
            self.start_lms_btn.disabled = (not is_lms) or self.game.started or self.game.game_over or (len(self.game.players) < 2)
            self.join_btn.disabled = self.game.started or self.game.game_over
            self.reload_btn.disabled = False
            self.mode_btn.disabled = self.game.started or self.game.game_over
            self.mode_btn.label = "Mode: LMS (Auto)" if is_lms else "Mode: Standard"
            self.mode_btn.style = discord.ButtonStyle.danger if is_lms else discord.ButtonStyle.secondary

    @staticmethod
    def _get_danger_bar(remaining: int, total_length: int = 10) -> Tuple[str, int]:
        pct = int(round((1.0 / max(1, remaining)) * 100))
        filled = min(total_length, max(1, int(round((pct / 100.0) * total_length))))
        empty = total_length - filled
        bar = "█" * filled + "░" * empty
        return bar, pct

    def _mute_if_eliminated(self, channel_id: Optional[int], user_id: int):
        if not channel_id or not self.bot:
            return
        if hasattr(self.bot, "get_cog"):
            cog = self.bot.get_cog("RussianRoulette")
            if cog and hasattr(cog, "mute_player"):
                cog.mute_player(channel_id, user_id, duration_seconds=120.0)

    def get_suspense_embed(self, player: discord.Member | discord.User, action_type: str = "pull") -> Tuple[discord.Embed, Optional[discord.File]]:
        spinning_cylinder = " ".join(["💫"] * self.game.chamber_size)
        if action_type == "spin":
            title = "🌀 Spinning Cylinder..."
            desc = (
                f"### 🎲 Cylinder in Motion\n"
                f"`[ {spinning_cylinder} ]`\n\n"
                f"**Contender:** {player.mention} spins the cylinder with full force...\n"
                f"> 🎲 *Whirrrrr... clack-clack-clack...*"
            )
        else:
            title = "🎯 Cocking Hammer..."
            desc = (
                f"### ⏱️ Holding Breath\n"
                f"`[ {spinning_cylinder} ]`\n\n"
                f"**Contender:** {player.mention} places the barrel and slowly pulls...\n"
                f"> ⏱️ *Silence in the room... mechanism clicks into place...*"
            )

        embed = discord.Embed(
            title=title,
            description=desc,
            colour=discord.Colour.gold()
        )
        if self.bot.user:
            embed.set_author(name="RUSSIAN ROULETTE • SUSPENSE", icon_url=self.bot.user.display_avatar.url)

        footer_mode = "Last Man Standing" if self.game.mode == "lms" else "Standard"
        embed.set_footer(text=f"Round {self.game.round_number} ({footer_mode}) • Calculating outcome...")

        gif_file = None
        spin_gif_path = os.path.join(ASSETS_DIR, "spin.gif")
        if os.path.exists(spin_gif_path):
            gif_file = discord.File(spin_gif_path, filename="spin.gif")
            embed.set_image(url="attachment://spin.gif")

        return embed, gif_file

    def get_embed(self) -> Tuple[discord.Embed, Optional[discord.File]]:
        cylinder = []
        for c in range(1, self.game.chamber_size + 1):
            if c < self.game.current_chamber:
                cylinder.append("⚪")
            elif c == self.game.current_chamber:
                cylinder.append("🎯" if not (self.game.game_over or self.game.victim) else ("💥" if self.game.victim else "⚪"))
            else:
                cylinder.append("⚫")

        cylinder_bar = " ".join(cylinder)
        total_players = len(self.game.players)
        remaining = self.game.chamber_size - self.game.current_chamber + 1
        danger_bar, lethality_pct = self._get_danger_bar(remaining)

        gif_file = None
        if self.game.victim:
            color = discord.Colour.red()
            status_title = f"💥 ELIMINATED — {self.game.victim.display_name.upper()}" if self.game.mode == "lms" and not self.game.game_over else "💥 GAME OVER — ELIMINATED"
            boom_path = os.path.join(ASSETS_DIR, "boom.gif")
            if os.path.exists(boom_path):
                gif_file = discord.File(boom_path, filename="boom.gif")
        elif self.game.game_over and self.game.winner:
            color = discord.Colour.gold()
            status_title = f"👑 BATTLE ROYALE CHAMPION — {self.game.winner.display_name.upper()}"
        elif self.game.game_over:
            color = discord.Colour.red()
            status_title = "💥 GAME OVER — ELIMINATED"
            boom_path = os.path.join(ASSETS_DIR, "boom.gif")
            if os.path.exists(boom_path):
                gif_file = discord.File(boom_path, filename="boom.gif")
        else:
            if self.game.mode == "lms":
                color = discord.Colour.dark_gold()
                status_title = f"👑 Russian Roulette: Last Man Standing (Round {self.game.round_number})"
            else:
                color = discord.Colour.green() if self.game.current_chamber > 1 else discord.Colour.gold()
                status_title = "💨 CLICK! SAFE — CHAMBER EMPTY" if self.game.current_chamber > 1 else "🎲 Russian Roulette"

            if self.game.current_chamber > 1:
                safe_path = os.path.join(ASSETS_DIR, "safe.gif")
                if os.path.exists(safe_path):
                    gif_file = discord.File(safe_path, filename="safe.gif")

        # Description with formatted cylinder & danger bar
        desc_lines = [
            "### 🎯 Cylinder Status",
            f"`[ {cylinder_bar} ]`",
            f"📍 **Chamber:** `{self.game.current_chamber}/{self.game.chamber_size}` • **Lethality:** `[{danger_bar}]` **{lethality_pct}%** (Odds: `1 in {remaining}`)\n",
            f"> {self.game.last_action_msg}"
        ]

        embed = discord.Embed(
            title=status_title,
            description="\n".join(desc_lines),
            colour=color
        )

        if self.bot.user:
            author_tag = f"BATTLE ROYALE • ROUND {self.game.round_number}" if self.game.mode == "lms" else "HIGH STAKES DUEL"
            embed.set_author(name=f"RUSSIAN ROULETTE // {author_tag}", icon_url=self.bot.user.display_avatar.url)

        if gif_file:
            embed.set_image(url=f"attachment://{gif_file.filename}")

        if self.game.mode == "lms":
            survivor_list = []
            for i, p in enumerate(self.game.alive_players):
                is_turn = (self.game.started and not self.game.game_over and i == (self.game.turn_index % max(1, len(self.game.alive_players))))
                pointer = "👉 " if is_turn else "• "
                tag = " *(Holding Barrel)*" if is_turn else ""
                survivor_list.append(f"{pointer}**{p.display_name}**{tag}")

            if self.game.winner:
                embed.add_field(
                    name="🏆 Tournament Champion",
                    value=f"👑 **{self.game.winner.mention}** has outlasted all contenders and won the Battle Royale!",
                    inline=False
                )
            elif survivor_list:
                embed.add_field(name=f"🛡️ Survivors ({len(self.game.alive_players)})", value="\n".join(survivor_list), inline=True)

            if self.game.eliminated_players:
                graveyard_list = [f"💀 ~~{p.display_name}~~" for p in self.game.eliminated_players]
                embed.add_field(name=f"🪦 Fallen ({len(self.game.eliminated_players)})", value="\n".join(graveyard_list), inline=True)
        else:
            if self.is_duel and len(self.game.players) == 2:
                p1, p2 = self.game.players[0], self.game.players[1]
                p1_turn = (self.game.started and not self.game.game_over and self.game.turn_index == 0)
                p2_turn = (self.game.started and not self.game.game_over and self.game.turn_index == 1)

                tag1 = " *(Mandatory Pull 1/2)*" if (p1_turn and self.game.is_forced_duel and self.game.forced_pulls_taken == 0) else \
                       " *(Mandatory Pull 2/2)*" if (p1_turn and self.game.is_forced_duel and self.game.forced_pulls_taken == 1) else \
                       " *(Turn)*" if p1_turn else ""
                tag2 = " *(Turn)*" if p2_turn else ""

                duel_list = [
                    f"{'👉 ' if p1_turn else '• '}**{p1.display_name}** *(Challenger)*{tag1}",
                    f"{'👉 ' if p2_turn else '• '}**{p2.display_name}** *(Opponent)*{tag2}"
                ]
                duel_title = "⚔️ 1v1 Forced Duel" if self.is_forced_duel else "⚔️ 1v1 High-Stakes Duel"
                embed.add_field(name=duel_title, value="\n".join(duel_list), inline=False)
            elif total_players > 1:
                player_list = []
                for i, p in enumerate(self.game.players):
                    is_turn = (self.game.started and not self.game.game_over and i == self.game.turn_index)
                    pointer = "👉 " if is_turn else "• "
                    tag = " *(Turn)*" if is_turn else ""
                    player_list.append(f"{pointer}`{i+1}.` **{p.display_name}**{tag}")
                embed.add_field(name=f"👥 Active Lobby ({total_players}/8)", value="\n".join(player_list), inline=False)
            else:
                embed.add_field(
                    name="👤 Mode: Solo Duel",
                    value="> Test your luck against the revolver.\n> Click **Pull Trigger** (sequential) or **Spin & Fire** (randomize).",
                    inline=False
                )

        mode_text = "Last Man Standing (Auto-Rounds)" if self.game.mode == "lms" else ("Forced Duel" if self.is_forced_duel else ("1v1 Duel" if self.is_duel else "Standard (Manual)"))
        embed.set_footer(text=f"Host: {self.host.display_name} • Mode: {mode_text} • Round {self.game.round_number}")
        return embed, gif_file

    def _check_turn(self, user: discord.Member | discord.User) -> Tuple[bool, Optional[str]]:
        if not self.game.started and len(self.game.players) > 1:
            self.game.started = True

        if len(self.game.players) > 1 and self.game.started:
            current_player = self.game.players[self.game.turn_index]
            if user.id != current_player.id:
                if self.is_forced_duel and self.game.forced_pulls_taken < 2 and current_player.id == self.host.id:
                    pull_num = self.game.forced_pulls_taken + 1
                    return False, f"⚠️ **Rule of Force:** {self.host.mention} must take mandatory pull `{pull_num}/2`!"
                return False, f"⏳ It is {current_player.mention}'s turn to pull the trigger!"
        elif len(self.game.players) == 1:
            if user.id not in [p.id for p in self.game.players]:
                self.game.players = [user]
        return True, None

    async def _safe_edit_message(
        self,
        embed: discord.Embed,
        attachments: Optional[List[discord.File]] = None,
    ):
        async with self._lock:
            files = attachments if attachments is not None else []
            if self.message and hasattr(self.message, "edit"):
                try:
                    res = self.message.edit(embed=embed, attachments=files, view=self)
                    if inspect.isawaitable(res):
                        await res
                    return
                except (discord.NotFound, discord.HTTPException) as e:
                    print(f"[RussianRoulette] Failed to edit message: {e}")
                except Exception:
                    pass

    async def _repost_view_message(
        self,
        interaction: Optional[discord.Interaction] = None,
        embed: Optional[discord.Embed] = None,
        attachments: Optional[List[discord.File]] = None,
    ) -> Optional[discord.Message]:
        async with self._lock:
            if interaction and hasattr(interaction, "response") and not interaction.response.is_done():
                try:
                    res = interaction.response.defer()
                    if inspect.isawaitable(res):
                        await res
                except (discord.NotFound, discord.HTTPException):
                    pass
                except Exception:
                    pass

            channel = (
                (interaction.channel if interaction else None)
                or (self.message.channel if self.message else None)
            )

            msgs_to_delete = []
            seen_ids = set()
            for m in (self.message, getattr(interaction, "message", None)):
                if m and getattr(m, "id", None) not in seen_ids:
                    seen_ids.add(getattr(m, "id", None))
                    msgs_to_delete.append(m)

            for old_msg in msgs_to_delete:
                if hasattr(old_msg, "delete"):
                    try:
                        res = old_msg.delete()
                        if inspect.isawaitable(res):
                            await res
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass
                    except Exception:
                        pass

            files = attachments if attachments is not None else []
            if channel and hasattr(channel, "send"):
                try:
                    res = channel.send(embed=embed, files=files, view=self)
                    if inspect.isawaitable(res):
                        new_msg = await res
                    else:
                        new_msg = res
                    self.message = new_msg
                    return new_msg
                except Exception as e:
                    print(f"[RussianRoulette] Failed to send new message: {e}")

            if interaction:
                await self._safe_edit_view_message(interaction, embed=embed, attachments=attachments)
            elif self.message:
                await self._safe_edit_message(embed=embed, attachments=attachments)
            return self.message

    async def _safe_edit_view_message(
        self,
        interaction: discord.Interaction,
        embed: discord.Embed,
        attachments: Optional[List[discord.File]] = None,
    ):
        files = attachments if attachments is not None else []

        # 1. Prefer interaction.edit_original_response (required for webhook/slash command messages and ephemerals)
        try:
            res = interaction.edit_original_response(embed=embed, attachments=files, view=self)
            if inspect.isawaitable(res):
                await res
            return
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        except Exception:
            pass

        # 2. Try followup.edit_message with interaction.message.id
        try:
            if interaction.message:
                res = interaction.followup.edit_message(interaction.message.id, embed=embed, attachments=files, view=self)
                if inspect.isawaitable(res):
                    await res
                return
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        except Exception:
            pass

        # 3. Direct message.edit fallback (for standard bot messages)
        try:
            if interaction.message:
                res = interaction.message.edit(embed=embed, attachments=files, view=self)
                if inspect.isawaitable(res):
                    await res
                return
        except Exception as e:
            print(f"[RussianRoulette] Failed to edit message: {e}")

    async def _execute_turn_with_animation(self, interaction: discord.Interaction, action_type: str):
        user = interaction.user
        allowed, err = self._check_turn(user)
        if not allowed:
            await interaction.response.send_message(err, ephemeral=True)
            return

        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()

        for btn in self.children:
            btn.disabled = True

        # Frame 1: Suspense animation -> Move down to bottom of chat
        suspense_embed, gif_file = self.get_suspense_embed(user, action_type=action_type)
        files1 = [gif_file] if gif_file else []
        await self._repost_view_message(interaction, embed=suspense_embed, attachments=files1)

        await asyncio.sleep(1.2)

        # Frame 2: Reveal final outcome -> Edit the message at bottom in-place
        if action_type == "spin":
            is_hit, msg = self.game.spin_and_pull(user)
        else:
            is_hit, msg = self.game.pull_trigger(user)

        if is_hit:
            ch_id = interaction.channel_id or (self.message.channel.id if self.message else None)
            self._mute_if_eliminated(ch_id, user.id)

        self.update_buttons()
        result_embed, result_file = self.get_embed()
        files2 = [result_file] if result_file else []

        await self._safe_edit_message(embed=result_embed, attachments=files2)

        if self.is_duel and not self.game.game_over:
            self._start_turn_timer()

    async def _run_lms_loop(self, interaction: discord.Interaction):
        """Automated round loop for Last Man Standing mode."""
        self._is_running = True
        self.update_buttons()

        start_embed, start_file = self.get_embed()
        start_files = [start_file] if start_file else []
        await self._repost_view_message(interaction, embed=start_embed, attachments=start_files)

        await asyncio.sleep(2.0)

        try:
            while not self.game.game_over and len(self.game.alive_players) > 1:
                current_player = self.game.alive_players[self.game.turn_index % len(self.game.alive_players)]

                # Frame 1: Suspense animation -> Move down to bottom of chat
                suspense_embed, suspense_file = self.get_suspense_embed(current_player, action_type="pull")
                files_susp = [suspense_file] if suspense_file else []
                await self._repost_view_message(embed=suspense_embed, attachments=files_susp)

                await asyncio.sleep(1.8)

                # Frame 2: Execute turn -> Edit in place
                is_hit, msg = self.game.pull_trigger(current_player)

                if is_hit:
                    ch_id = interaction.channel_id or (self.message.channel.id if self.message else None)
                    self._mute_if_eliminated(ch_id, current_player.id)

                outcome_embed, outcome_file = self.get_embed()
                files_out = [outcome_file] if outcome_file else []
                await self._safe_edit_message(embed=outcome_embed, attachments=files_out)

                if self.game.game_over:
                    break

                if is_hit:
                    # Player died! Auto-advance to next round without user interaction
                    await asyncio.sleep(3.2)
                    self.game.start_next_round()
                    round_embed, _ = self.get_embed()
                    await self._repost_view_message(embed=round_embed, attachments=[])
                    await asyncio.sleep(2.0)
                else:
                    # Safe click, pause before next survivor's turn
                    await asyncio.sleep(2.2)

        except (discord.HTTPException, asyncio.CancelledError) as e:
            print(f"[RussianRoulette] LMS loop cancelled or HTTP error: {e}")
        finally:
            self._is_running = False
            self.update_buttons()
            final_embed, final_file = self.get_embed()
            files_fin = [final_file] if final_file else []
            await self._safe_edit_message(embed=final_embed, attachments=files_fin)

    @discord.ui.button(label="Pull Trigger", style=discord.ButtonStyle.primary, emoji="🎲", row=0)
    async def trigger_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_turn_with_animation(interaction, action_type="pull")

    @discord.ui.button(label="Spin & Fire", style=discord.ButtonStyle.danger, emoji="🌀", row=0)
    async def spin_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_turn_with_animation(interaction, action_type="spin")

    @discord.ui.button(label="Start Battle Royale", style=discord.ButtonStyle.danger, emoji="🚀", row=0)
    async def start_lms_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("❌ Only the lobby host can start the Battle Royale.", ephemeral=True)
            return

        if len(self.game.players) < 2:
            await interaction.response.send_message("❌ Need at least 2 players to start Last Man Standing.", ephemeral=True)
            return

        success = self.game.start_lms_game()
        if not success:
            await interaction.response.send_message("❌ Cannot start LMS game.", ephemeral=True)
            return

        asyncio.create_task(self._run_lms_loop(interaction))

    @discord.ui.button(label="Join / Leave", style=discord.ButtonStyle.success, emoji="✋", row=1)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        player_ids = [p.id for p in self.game.players]

        if user.id in player_ids:
            if len(self.game.players) > 1:
                self.game.players = [p for p in self.game.players if p.id != user.id]
                self.game.alive_players = [p for p in self.game.alive_players if p.id != user.id]
                self.game.last_action_msg = f"🚪 {user.mention} left the game."
            else:
                await interaction.response.send_message("❌ Host cannot leave solo game.", ephemeral=True)
                return
        else:
            if len(self.game.players) >= 8:
                await interaction.response.send_message("❌ Lobby is full (max 8 players).", ephemeral=True)
                return
            self.game.players.append(user)
            self.game.alive_players.append(user)
            self.game.last_action_msg = f"🎮 {user.mention} joined the roulette lobby!"

        self.update_buttons()
        embed, gif_file = self.get_embed()
        attachments = [gif_file] if gif_file else []
        await self._repost_view_message(interaction, embed=embed, attachments=attachments)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def reload_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_duel and not self.game.game_over:
            await interaction.response.send_message("❌ Cannot reset duel while in progress.", ephemeral=True)
            return
        if self.is_duel and interaction.user.id not in [p.id for p in self.game.players]:
            await interaction.response.send_message("❌ Only duel participants can reset the duel.", ephemeral=True)
            return

        self.game.reset()
        if self.is_duel:
            self.game.started = True
            if self.is_forced_duel:
                self.game.is_forced_duel = True
                self.game.forced_pulls_taken = 0
            self._start_turn_timer()

        self.update_buttons()
        embed, gif_file = self.get_embed()
        attachments = [gif_file] if gif_file else []
        await self._repost_view_message(interaction, embed=embed, attachments=attachments)

    @discord.ui.button(label="Mode: Standard", style=discord.ButtonStyle.secondary, emoji="👑", row=1)
    async def mode_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.started or self.game.game_over:
            await interaction.response.send_message("❌ Cannot change mode once game has started.", ephemeral=True)
            return

        if self.game.mode == "standard":
            self.game.mode = "lms"
            self.game.alive_players = list(self.game.players)
            self.game.last_action_msg = "👑 Switched to **Last Man Standing (Battle Royale)**! Press **Start Battle Royale** when players are ready."
        else:
            self.game.mode = "standard"
            self.game.last_action_msg = "🎲 Switched to **Standard Mode**! Use **Pull Trigger** or **Spin & Fire**."

        self.update_buttons()
        embed, gif_file = self.get_embed()
        attachments = [gif_file] if gif_file else []
        await self._repost_view_message(interaction, embed=embed, attachments=attachments)


class RouletteChallengeView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        challenger: discord.Member | discord.User,
        opponent: discord.Member,
        chamber_size: int = 6,
    ):
        super().__init__(timeout=60)
        self.bot = bot
        self.challenger = challenger
        self.opponent = opponent
        self.chamber_size = chamber_size
        self.message: Optional[discord.Message] = None

    def get_challenge_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="⚔️ Russian Roulette: Duel Challenge!",
            description=(
                f"**{self.challenger.mention}** has challenged **{self.opponent.mention}** to a 1v1 Russian Roulette duel!\n\n"
                f"🎯 **Cylinder:** `{self.chamber_size}` chambers (1 live round)\n"
                f"💀 **Stakes:** Loser is **muted for 2 minutes** in this channel!\n\n"
                f"⏳ {self.opponent.mention}, click **Accept** to face the barrel or **Decline** to forfeit (Expires in 60s)."
            ),
            colour=discord.Colour.orange()
        )
        if self.bot.user:
            embed.set_author(name="RUSSIAN ROULETTE // DUEL INVITATION", icon_url=self.bot.user.display_avatar.url)
        return embed

    async def on_timeout(self):
        for btn in self.children:
            btn.disabled = True
        if self.message:
            embed = discord.Embed(
                title="⏳ Challenge Expired",
                description=f"{self.opponent.mention} did not respond to {self.challenger.mention}'s duel challenge in time.",
                colour=discord.Colour.dark_grey()
            )
            try:
                await self.message.edit(embed=embed, view=self)
            except (discord.NotFound, discord.HTTPException):
                pass

    @discord.ui.button(label="Accept Duel", style=discord.ButtonStyle.success, emoji="⚔️")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ Only the challenged player can accept this duel.", ephemeral=True)
            return

        duel_view = RussianRouletteView(
            self.bot,
            host=self.challenger,
            chamber_size=self.chamber_size,
            mode="standard",
            is_duel=True,
            opponent=self.opponent,
            is_forced_duel=False,
        )
        embed, gif_file = duel_view.get_embed()
        files = [gif_file] if gif_file else []
        await interaction.response.edit_message(content=None, embed=embed, attachments=files, view=duel_view)
        duel_view.message = interaction.message or self.message
        duel_view._start_turn_timer()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="🏳️")
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.opponent.id, self.challenger.id):
            await interaction.response.send_message("❌ Only the challenger or opponent can decline.", ephemeral=True)
            return

        for btn in self.children:
            btn.disabled = True
        decliner = interaction.user
        desc = (
            f"🏳️ {self.opponent.mention} declined {self.challenger.mention}'s challenge."
            if decliner.id == self.opponent.id
            else f"🏳️ {self.challenger.mention} cancelled the duel challenge."
        )
        embed = discord.Embed(
            title="🏳️ Duel Cancelled",
            description=desc,
            colour=discord.Colour.red()
        )
        await interaction.response.edit_message(content=None, embed=embed, attachments=[], view=self)
