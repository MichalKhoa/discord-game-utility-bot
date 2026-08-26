import os
import asyncio
import random
import discord
from discord import app_commands
from discord.ext import commands
from typing import List, Dict, Optional, Tuple


ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "roulette")


class RussianRouletteGame:
    def __init__(self, chamber_size: int = 6):
        self.chamber_size = max(2, min(chamber_size, 12))
        self.players: List[discord.Member | discord.User] = []
        self.bullet_chamber: int = random.randint(1, self.chamber_size)
        self.current_chamber: int = 1
        self.turn_index: int = 0
        self.started: bool = False
        self.game_over: bool = False
        self.winner: Optional[discord.Member | discord.User] = None
        self.victim: Optional[discord.Member | discord.User] = None
        self.last_action_msg: str = "🔫 Cylinder loaded! Click **Pull Trigger** (sequential) or **Spin & Fire** (randomize)."

    def reset(self):
        self.bullet_chamber = random.randint(1, self.chamber_size)
        self.current_chamber = 1
        self.turn_index = 0
        self.game_over = False
        self.winner = None
        self.victim = None
        self.last_action_msg = f"🔄 Cylinder spun! 1 live round hidden in {self.chamber_size} chambers."

    def pull_trigger(self, player: discord.Member | discord.User) -> Tuple[bool, str]:
        """Pulls trigger sequentially on the current chamber."""
        chamber = self.current_chamber
        is_hit = (chamber == self.bullet_chamber)

        if is_hit:
            self.game_over = True
            self.victim = player
            msg = f"💥 **BANG!** Chamber `{chamber}/{self.chamber_size}` fired! {player.mention} was eliminated!"
            self.last_action_msg = msg
            return True, msg
        else:
            self.current_chamber += 1
            remaining = self.chamber_size - self.current_chamber + 1
            msg = f"💨 ***Click!*** Chamber `{chamber}/{self.chamber_size}` was empty! {player.mention} survived! (`{remaining}` chamber{'s' if remaining != 1 else ''} left)"
            self.last_action_msg = msg

            if len(self.players) > 1:
                self.turn_index = (self.turn_index + 1) % len(self.players)

            return False, msg

    def spin_and_pull(self, player: discord.Member | discord.User) -> Tuple[bool, str]:
        """Spins the cylinder to a random position and immediately pulls the trigger."""
        self.bullet_chamber = random.randint(1, self.chamber_size)
        self.current_chamber = 1
        is_hit = (self.current_chamber == self.bullet_chamber)

        if is_hit:
            self.game_over = True
            self.victim = player
            msg = f"🌀💨 *Spin... Spin...* 💥 **BANG!** Cylinder landed on the live round! {player.mention} was eliminated!"
            self.last_action_msg = msg
            return True, msg
        else:
            self.current_chamber += 1
            remaining = self.chamber_size - self.current_chamber + 1
            msg = f"🌀💨 *Spin... Spin...* 💨 ***Click!*** Safe! {player.mention} survived the spin! (`{remaining}` chamber{'s' if remaining != 1 else ''} left)"
            self.last_action_msg = msg

            if len(self.players) > 1:
                self.turn_index = (self.turn_index + 1) % len(self.players)

            return False, msg


class RussianRouletteView(discord.ui.View):
    def __init__(self, bot: commands.Bot, host: discord.Member | discord.User, chamber_size: int = 6):
        super().__init__(timeout=300)
        self.bot = bot
        self.host = host
        self.game = RussianRouletteGame(chamber_size=chamber_size)
        self.game.players.append(host)
        self.update_buttons()

    def update_buttons(self):
        self.trigger_btn.disabled = self.game.game_over
        self.spin_btn.disabled = self.game.game_over
        self.join_btn.disabled = self.game.started or self.game.game_over

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
        embed.set_footer(text="Calculating outcome...")

        gif_file = None
        spin_gif_path = os.path.join(ASSETS_DIR, "spin.gif")
        if os.path.exists(spin_gif_path):
            gif_file = discord.File(spin_gif_path, filename="spin.gif")
            embed.set_image(url="attachment://spin.gif")

        return embed, gif_file

    def get_embed(self) -> Tuple[discord.Embed, Optional[discord.File]]:
        # Build cylinder visual
        cylinder = []
        for c in range(1, self.game.chamber_size + 1):
            if c < self.game.current_chamber:
                cylinder.append("⚪")  # Empty spent
            elif c == self.game.current_chamber:
                cylinder.append("🎯" if not self.game.game_over else ("💥" if self.game.victim else "⚪"))
            else:
                cylinder.append("⚫")  # Unspent

        cylinder_bar = " ".join(cylinder)
        total_players = len(self.game.players)
        remaining = self.game.chamber_size - self.game.current_chamber + 1

        gif_file = None
        if self.game.game_over:
            color = discord.Colour.red()
            status_title = "💥 GAME OVER — ELIMINATED"
            boom_path = os.path.join(ASSETS_DIR, "boom.gif")
            if os.path.exists(boom_path):
                gif_file = discord.File(boom_path, filename="boom.gif")
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

        if total_players > 1:
            player_list = []
            for i, p in enumerate(self.game.players):
                pointer = "👉 " if (self.game.started and not self.game.game_over and i == self.game.turn_index) else ""
                player_list.append(f"{pointer}`{i+1}.` {p.display_name}")
            embed.add_field(name=f"👥 Players ({total_players})", value="\n".join(player_list), inline=False)
        else:
            embed.add_field(name="👤 Mode", value="Solo Duel (Choose **Pull Trigger** or **Spin & Fire**)", inline=False)

        embed.set_footer(text=f"Host: {self.host.display_name} • 🎲 Pull Trigger = Sequential | 🌀 Spin & Fire = Reset to 1/{self.game.chamber_size}")
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

        # Disable buttons temporarily during suspense
        for btn in self.children:
            btn.disabled = True

        # Frame 1: Suspense animation
        suspense_embed, gif_file = self.get_suspense_embed(user, action_type=action_type)
        if gif_file:
            await interaction.response.edit_message(embed=suspense_embed, attachments=[gif_file], view=self)
        else:
            await interaction.response.edit_message(embed=suspense_embed, view=self)

        # Suspense pause for dramatic timing
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

    @discord.ui.button(label="Pull Trigger", style=discord.ButtonStyle.primary, emoji="🎲", row=0)
    async def trigger_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_turn_with_animation(interaction, action_type="pull")

    @discord.ui.button(label="Spin & Fire", style=discord.ButtonStyle.danger, emoji="🌀", row=0)
    async def spin_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_turn_with_animation(interaction, action_type="spin")

    @discord.ui.button(label="Join / Leave", style=discord.ButtonStyle.success, emoji="✋", row=0)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        player_ids = [p.id for p in self.game.players]

        if user.id in player_ids:
            if len(self.game.players) > 1:
                self.game.players = [p for p in self.game.players if p.id != user.id]
                self.game.last_action_msg = f"🚪 {user.mention} left the game."
            else:
                await interaction.response.send_message("❌ Host cannot leave solo game.", ephemeral=True)
                return
        else:
            if len(self.game.players) >= 8:
                await interaction.response.send_message("❌ Lobby is full (max 8 players).", ephemeral=True)
                return
            self.game.players.append(user)
            self.game.last_action_msg = f"🎮 {user.mention} joined the roulette lobby!"

        self.update_buttons()
        embed, gif_file = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def reload_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.reset()
        self.update_buttons()
        embed, gif_file = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class RussianRoulette(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def start_game(self, interaction: discord.Interaction, chamber_size: int = 6):
        view = RussianRouletteView(self.bot, host=interaction.user, chamber_size=chamber_size)
        embed, gif_file = view.get_embed()
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="roulette", description="Start an interactive Russian Roulette game (Solo or Multiplayer)")
    @app_commands.describe(chambers="Number of chambers in cylinder (default: 6, min: 2, max: 12)")
    async def roulette_cmd(self, interaction: discord.Interaction, chambers: int = 6):
        await self.start_game(interaction, chamber_size=chambers)


async def setup(bot: commands.Bot):
    print("RussianRoulette cog loaded")
    await bot.add_cog(RussianRoulette(bot))
