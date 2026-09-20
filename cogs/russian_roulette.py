import os
import asyncio
import random
import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Dict, Optional, Tuple


ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "roulette")


class RussianRouletteGame:
    def __init__(self, chamber_size: int = 6, mode: str = "standard"):
        self.chamber_size = max(2, min(chamber_size, 12))
        self.mode: str = mode  # "standard" (sudden death lobby) or "lms" (battle royale)
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
        self.started = False
        self.game_over = False
        self.winner = None
        self.victim = None
        self.alive_players = list(self.players)
        self.eliminated_players = []
        if self.mode == "lms":
            self.last_action_msg = f"👑 LMS Lobby reset! {len(self.players)} players ready for Battle Royale."
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
            self.last_action_msg = msg

            active_pool = self.alive_players if (self.mode == "lms" and self.started) else self.players
            if len(active_pool) > 1:
                self.turn_index = (self.turn_index + 1) % len(active_pool)

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
                msg = f"🌀💨 *Spin... Spin...* 💥 **BANG!** Cylinder landed on the live round! {player.mention} was eliminated!"

            self.last_action_msg = msg
            return True, msg
        else:
            self.current_chamber += 1
            remaining = self.chamber_size - self.current_chamber + 1
            msg = f"🌀💨 *Spin... Spin...* 💨 ***Click!*** Safe! {player.mention} survived the spin! (`{remaining}` chamber{'s' if remaining != 1 else ''} left)"
            self.last_action_msg = msg

            active_pool = self.alive_players if (self.mode == "lms" and self.started) else self.players
            if len(active_pool) > 1:
                self.turn_index = (self.turn_index + 1) % len(active_pool)

            return False, msg


class RussianRouletteView(discord.ui.View):
    def __init__(self, bot: commands.Bot, host: discord.Member | discord.User, chamber_size: int = 6, mode: str = "standard"):
        super().__init__(timeout=300)
        self.bot = bot
        self.host = host
        self.game = RussianRouletteGame(chamber_size=chamber_size, mode=mode)
        self.game.players.append(host)
        self.game.alive_players.append(host)
        self._is_running: bool = False
        self.update_buttons()

    def update_buttons(self):
        if self._is_running:
            for btn in self.children:
                btn.disabled = True
            return

        is_lms = (self.game.mode == "lms")
        self.trigger_btn.disabled = is_lms or self.game.game_over
        self.spin_btn.disabled = is_lms or self.game.game_over
        self.start_lms_btn.disabled = (not is_lms) or self.game.started or self.game.game_over or (len(self.game.players) < 2)
        self.join_btn.disabled = self.game.started or self.game.game_over
        self.reload_btn.disabled = False
        self.mode_btn.disabled = self.game.started or self.game.game_over
        self.mode_btn.label = "Mode: LMS (Auto)" if is_lms else "Mode: Standard"
        self.mode_btn.style = discord.ButtonStyle.danger if is_lms else discord.ButtonStyle.secondary

    def get_suspense_embed(self, player: discord.Member | discord.User, action_type: str = "pull") -> Tuple[discord.Embed, Optional[discord.File]]:
        spinning_cylinder = " ".join(["💫"] * self.game.chamber_size)
        if action_type == "spin":
            title = "🌀 Spinning Cylinder..."
            desc = (
                f"### Revolver in Motion\n"
                f"`[ {spinning_cylinder} ]`\n"
                f"{player.mention} spins the cylinder with full force...\n\n"
                f"> 🎲 *Whirrrrr... clack-clack-clack...*"
            )
        else:
            title = "🎯 Cocking Hammer..."
            desc = (
                f"### Holding Breath\n"
                f"`[ {spinning_cylinder} ]`\n"
                f"{player.mention} places the barrel and slowly pulls the trigger...\n\n"
                f"> ⏱️ *Silence in the room...*"
            )

        embed = discord.Embed(
            title=title,
            description=desc,
            colour=discord.Colour.gold()
        )
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

        gif_file = None
        if self.game.victim:
            color = discord.Colour.red()
            status_title = "💥 CASUALTY — ELIMINATED" if self.game.mode == "lms" and not self.game.game_over else "💥 GAME OVER — ELIMINATED"
            boom_path = os.path.join(ASSETS_DIR, "boom.gif")
            if os.path.exists(boom_path):
                gif_file = discord.File(boom_path, filename="boom.gif")
        elif self.game.game_over and self.game.winner:
            color = discord.Colour.purple()
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
                color = discord.Colour.gold()
                status_title = "🎲 Russian Roulette"

            if self.game.current_chamber > 1:
                safe_path = os.path.join(ASSETS_DIR, "safe.gif")
                if os.path.exists(safe_path):
                    gif_file = discord.File(safe_path, filename="safe.gif")

        embed = discord.Embed(
            title=status_title,
            description=(
                f"### Cylinder Status\n"
                f"`[ {cylinder_bar} ]`\n"
                f"Current: Chamber `{self.game.current_chamber}/{self.game.chamber_size}` (Odds: `1 in {remaining}`)\n\n"
                f"> {self.game.last_action_msg}"
            ),
            colour=color
        )

        if gif_file:
            embed.set_image(url=f"attachment://{gif_file.filename}")

        if self.game.mode == "lms":
            # LMS Player Rosters
            survivor_list = []
            for i, p in enumerate(self.game.alive_players):
                pointer = "👉 " if (self.game.started and not self.game.game_over and i == (self.game.turn_index % max(1, len(self.game.alive_players)))) else "• "
                survivor_list.append(f"{pointer}**{p.display_name}**")

            if self.game.winner:
                embed.add_field(name="🏆 Winner", value=f"👑 **{self.game.winner.mention}** (Last Man Standing!)", inline=False)
            elif survivor_list:
                embed.add_field(name=f"👥 Survivors ({len(self.game.alive_players)})", value="\n".join(survivor_list), inline=True)

            if self.game.eliminated_players:
                graveyard_list = [f"💀 ~~{p.display_name}~~" for p in self.game.eliminated_players]
                embed.add_field(name=f"🪦 Graveyard ({len(self.game.eliminated_players)})", value="\n".join(graveyard_list), inline=True)
        else:
            # Standard Mode Player Roster
            if total_players > 1:
                player_list = []
                for i, p in enumerate(self.game.players):
                    pointer = "👉 " if (self.game.started and not self.game.game_over and i == self.game.turn_index) else ""
                    player_list.append(f"{pointer}`{i+1}.` {p.display_name}")
                embed.add_field(name=f"👥 Players ({total_players})", value="\n".join(player_list), inline=False)
            else:
                embed.add_field(name="👤 Mode", value="Solo Duel (Choose **Pull Trigger** or **Spin & Fire**)", inline=False)

        mode_text = "Last Man Standing (Auto-Rounds)" if self.game.mode == "lms" else "Standard (Manual)"
        embed.set_footer(text=f"Host: {self.host.display_name} • Mode: {mode_text} • Round {self.game.round_number}")
        return embed, gif_file

    def _check_turn(self, user: discord.Member | discord.User) -> Tuple[bool, Optional[str]]:
        if not self.game.started and len(self.game.players) > 1:
            self.game.started = True

        if len(self.game.players) > 1 and self.game.started:
            current_player = self.game.players[self.game.turn_index]
            if user.id != current_player.id:
                return False, f"⏳ It is {current_player.mention}'s turn to pull the trigger!"
        elif len(self.game.players) == 1:
            if user.id not in [p.id for p in self.game.players]:
                self.game.players = [user]
        return True, None

    async def _execute_turn_with_animation(self, interaction: discord.Interaction, action_type: str):
        user = interaction.user
        allowed, err = self._check_turn(user)
        if not allowed:
            await interaction.response.send_message(err, ephemeral=True)
            return

        for btn in self.children:
            btn.disabled = True

        # Frame 1: Suspense animation
        suspense_embed, gif_file = self.get_suspense_embed(user, action_type=action_type)
        if gif_file:
            await interaction.response.edit_message(embed=suspense_embed, attachments=[gif_file], view=self)
        else:
            await interaction.response.edit_message(embed=suspense_embed, view=self)

        await asyncio.sleep(1.2)

        # Frame 2: Reveal final outcome
        if action_type == "spin":
            is_hit, msg = self.game.spin_and_pull(user)
        else:
            is_hit, msg = self.game.pull_trigger(user)

        self.update_buttons()
        result_embed, result_file = self.get_embed()

        if result_file:
            await interaction.message.edit(embed=result_embed, attachments=[result_file], view=self)
        else:
            await interaction.message.edit(embed=result_embed, attachments=[], view=self)

    async def _run_lms_loop(self, interaction: discord.Interaction):
        """Automated round loop for Last Man Standing mode."""
        self._is_running = True
        self.update_buttons()

        start_embed, start_file = self.get_embed()
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=start_embed, attachments=[start_file] if start_file else [], view=self)
        else:
            await interaction.message.edit(embed=start_embed, attachments=[start_file] if start_file else [], view=self)

        message = interaction.message
        await asyncio.sleep(2.0)

        try:
            while not self.game.game_over and len(self.game.alive_players) > 1:
                current_player = self.game.alive_players[self.game.turn_index % len(self.game.alive_players)]

                # Frame 1: Suspense animation
                suspense_embed, suspense_file = self.get_suspense_embed(current_player, action_type="pull")
                if suspense_file:
                    await message.edit(embed=suspense_embed, attachments=[suspense_file], view=self)
                else:
                    await message.edit(embed=suspense_embed, attachments=[], view=self)

                await asyncio.sleep(1.8)

                # Frame 2: Execute turn
                is_hit, msg = self.game.pull_trigger(current_player)

                outcome_embed, outcome_file = self.get_embed()
                if outcome_file:
                    await message.edit(embed=outcome_embed, attachments=[outcome_file], view=self)
                else:
                    await message.edit(embed=outcome_embed, attachments=[], view=self)

                if self.game.game_over:
                    break

                if is_hit:
                    # Player died! Auto-advance to next round without user interaction
                    await asyncio.sleep(3.2)
                    self.game.start_next_round()
                    round_embed, _ = self.get_embed()
                    await message.edit(embed=round_embed, attachments=[], view=self)
                    await asyncio.sleep(2.0)
                else:
                    # Safe click, pause before next survivor's turn
                    await asyncio.sleep(2.2)

        except (discord.HTTPException, asyncio.CancelledError):
            pass
        finally:
            self._is_running = False
            self.update_buttons()
            final_embed, final_file = self.get_embed()
            try:
                if final_file:
                    await message.edit(embed=final_embed, attachments=[final_file], view=self)
                else:
                    await message.edit(embed=final_embed, attachments=[], view=self)
            except discord.HTTPException:
                pass

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
        await interaction.response.edit_message(embed=embed, attachments=attachments, view=self)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def reload_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.reset()
        self.update_buttons()
        embed, gif_file = self.get_embed()
        attachments = [gif_file] if gif_file else []
        await interaction.response.edit_message(embed=embed, attachments=attachments, view=self)

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
        await interaction.response.edit_message(embed=embed, attachments=attachments, view=self)


class RussianRoulette(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def start_game(self, interaction: discord.Interaction, chamber_size: int = 6, mode: str = "standard"):
        view = RussianRouletteView(self.bot, host=interaction.user, chamber_size=chamber_size, mode=mode)
        embed, gif_file = view.get_embed()
        attachments = [gif_file] if gif_file else []
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, files=attachments, view=view)
        else:
            await interaction.response.send_message(embed=embed, files=attachments, view=view)

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
