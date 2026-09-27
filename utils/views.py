import discord
import asyncio
import re
from typing import Optional, List, TYPE_CHECKING
from discord.ext import commands, tasks

from utils.embeds import MainMenuEmbed
from utils.modals import (
    RedeemModal,
    RedeemSingleModal,
    CustomCountdownModal,
    ConfirmAbortModal,
)
from utils.countdown import play_voice_countdown, get_or_connect_vc, stop_voice
from utils.player_views import (
    ConfirmActionView,
    PlayerListView,
    FlaggedPlayersView,
    PlayerMenuButtons,
    ImportDataView,
    GoogleSheetMenuButtons,
    SheetPruneConfirmView,
)

if TYPE_CHECKING:
    from cogs.code_redeem import CodeRedeem

__all__ = [
    # Base View
    "BaseView",
    # Navigation & Games
    "MenuButtons",
    "GameMenuButtons",
    "CoordleSetupView",
    "WyrButtons",
    # Utilities & Redemption
    "UtilityMenuButtons",
    "ConfirmRedeemView",
    "BatchProgressView",
    "RallyCountdownView",
    # Player & Sheet Management (re-exported)
    "ConfirmActionView",
    "PlayerListView",
    "FlaggedPlayersView",
    "PlayerMenuButtons",
    "ImportDataView",
    "GoogleSheetMenuButtons",
    "SheetPruneConfirmView",
]


class BaseView(discord.ui.View):
    """Base interactive view with automatic button disabling and message editing on timeout."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return not self.is_finished()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass


class MenuButtons(BaseView):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="Games", style=discord.ButtonStyle.primary, emoji="🎮")
    async def games_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        games_menu_panel = discord.Embed(
            title="🎮 Interactive Party & Mini-Games",
            description="Choose a mini-game to play with your friends or alliance members:",
            colour=discord.Colour.og_blurple()
        )
        games_menu_panel.add_field(
            name="🤷 Would you rather ...",
            value="> Pick between impossible scenarios and see live community vote splits.",
            inline=False
        )
        games_menu_panel.add_field(
            name="🎲 Russian Roulette",
            value="> Turn-based revolver luck challenge. Play solo or test your luck in a multiplayer lobby!",
            inline=False
        )
        games_menu_panel.add_field(
            name="🟩 Co-ordle (Wordle)",
            value="> Cooperative word-guessing puzzle with custom word lengths and attempts!",
            inline=False
        )
        await interaction.response.edit_message(embed=games_menu_panel, view=GameMenuButtons(self.bot))

    @discord.ui.button(label="Players", style=discord.ButtonStyle.primary, emoji="👥")
    async def players_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        player_menu_panel = discord.Embed(
            title="👥 Player Registry & Management",
            description="Manage game player accounts, kingdom IDs, and warning flags.",
            colour=discord.Colour.teal()
        )
        player_menu_panel.add_field(
            name="📋 Player List & ⚠️ Flagged",
            value="> Browse active player accounts, review warning strikes, and view stats.",
            inline=False
        )
        player_menu_panel.add_field(
            name="➕ Add / 🔍 Search / 📥 Import & Export",
            value="> Register accounts, edit profiles, batch paste, file import, or CSV export.",
            inline=False
        )
        player_menu_panel.add_field(
            name="📊 Google Sheets & Cloud Backup",
            value="> Sync rosters with Google Sheets and manage database backups.",
            inline=False
        )
        await interaction.response.edit_message(embed=player_menu_panel, view=PlayerMenuButtons(self.bot))

    @discord.ui.button(label="Utilities", style=discord.ButtonStyle.primary, emoji="🛠️")
    async def utility_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        utility_menu_panel = discord.Embed(
            title="Choose one of the options below:",
            colour=discord.Colour.yellow())
        utility_menu_panel.add_field(
            name="🪙 Redeem codes for everyone",
            value="> Redeem gift code for all registered accounts with verification.",
            inline=False
        )
        utility_menu_panel.add_field(
            name="👤 Redeem code for one player",
            value="> Redeem gift code for a single player ID instantly.",
            inline=False
        )
        utility_menu_panel.add_field(
            name="📜 Redeem History",
            value="> Check recently redeemed codes and timestamps.",
            inline=False
        )
        utility_menu_panel.add_field(
            name="🎙️ Rally Countdown Panel",
            value="> Open the interactive voice countdown panel for rallies.",
            inline=False
        )
        await interaction.response.edit_message(embed=utility_menu_panel, view=UtilityMenuButtons(self.bot))


class GameMenuButtons(BaseView):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="Would You Rather?", style=discord.ButtonStyle.primary, emoji="🤷", row=0)
    async def wyr_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        wyr_cog = self.bot.get_cog("Wyr")
        if wyr_cog:
            await wyr_cog.start_wyr_game(interaction)
        else:
            await interaction.response.send_message("❌ Wyr game module not loaded.", ephemeral=True)

    @discord.ui.button(label="Russian Roulette", style=discord.ButtonStyle.danger, emoji="🎲", row=0)
    async def roulette_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        rr_cog = self.bot.get_cog("RussianRoulette")
        if rr_cog:
            await rr_cog.start_game(interaction)
        else:
            await interaction.response.send_message("❌ RussianRoulette game module not loaded.", ephemeral=True)

    @discord.ui.button(label="Co-ordle (Wordle)", style=discord.ButtonStyle.success, emoji="🟩", row=0)
    async def coordle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CoordleSetupView(self.bot)
        await interaction.response.edit_message(embed=view.get_setup_embed(), view=view)

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary, emoji="◀", row=1)
    async def return_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = MainMenuEmbed(self.bot)
        view = MenuButtons(self.bot)
        await interaction.response.edit_message(embed=embed, view=view)


class CoordleSetupView(BaseView):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=86400)
        self.bot = bot
        self.selected_length = 5
        self.selected_attempts = 6
        self.selected_mode = "normal"

    def get_setup_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🟩 Co-ordle Setup & Settings",
            description=(
                "Configure your cooperative Wordle game settings below, then click **Start Co-ordle**:\n"
                "Anyone in the channel can contribute guesses toward solving the shared puzzle!"
            ),
            colour=discord.Colour.green()
        )
        embed.add_field(name="🔡 Word Length", value=f"`{self.selected_length} Letters`", inline=True)
        embed.add_field(name="🎯 Max Attempts", value=f"`{self.selected_attempts} Attempts`", inline=True)
        mode_text = "⚡ Blitz (Speedrun, 1.5x pts)" if self.selected_mode == "blitz" else "⏱️ Normal (Relaxed)"
        embed.add_field(name="🎮 Mode", value=f"`{mode_text}`", inline=True)
        embed.set_footer(text="Co-ordle | Modifiable word length & attempt count")
        return embed

    @discord.ui.select(
        placeholder="Select Word Length (Default: 5)",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="4 Letters", value="4", description="Quick 4-letter puzzle"),
            discord.SelectOption(label="5 Letters", value="5", description="Classic standard Wordle", default=True),
            discord.SelectOption(label="6 Letters", value="6", description="6-letter challenge"),
            discord.SelectOption(label="7 Letters", value="7", description="7-letter word puzzle"),
            discord.SelectOption(label="8 Letters", value="8", description="Long 8-letter brain teaser"),
        ],
        row=0
    )
    async def select_length(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_length = int(select.values[0])
        for opt in select.options:
            opt.default = (opt.value == select.values[0])
        await interaction.response.edit_message(embed=self.get_setup_embed(), view=self)

    @discord.ui.select(
        placeholder="Select Max Attempts (Default: 6)",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="3 Attempts", value="3", description="🔥 Sudden Death / Expert", emoji="💀"),
            discord.SelectOption(label="4 Attempts", value="4", description="Hardcore difficulty", emoji="⚡"),
            discord.SelectOption(label="5 Attempts", value="5", description="Challenging puzzle", emoji="🎯"),
            discord.SelectOption(label="6 Attempts", value="6", description="Standard Wordle rules (Default)", default=True, emoji="🟩"),
            discord.SelectOption(label="7 Attempts", value="7", description="Extra attempt buffer", emoji="👍"),
            discord.SelectOption(label="8 Attempts", value="8", description="Relaxed casual play", emoji="🌱"),
            discord.SelectOption(label="9 Attempts", value="9", description="Generous attempts", emoji="🏖️"),
            discord.SelectOption(label="10 Attempts", value="10", description="Cooperative party mode", emoji="🎉"),
            discord.SelectOption(label="12 Attempts", value="12", description="Beginner friendly", emoji="👥"),
            discord.SelectOption(label="15 Attempts", value="15", description="Mega party free-for-all", emoji="🌟"),
        ],
        row=1
    )
    async def select_attempts(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_attempts = int(select.values[0])
        for opt in select.options:
            opt.default = (opt.value == select.values[0])
        await interaction.response.edit_message(embed=self.get_setup_embed(), view=self)

    @discord.ui.button(label="Start Co-ordle", style=discord.ButtonStyle.success, emoji="🚀", row=2)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        coordle_cog = self.bot.get_cog("Coordle")
        if coordle_cog:
            await coordle_cog.start_game(
                interaction,
                length=self.selected_length,
                max_attempts=self.selected_attempts,
                mode=self.selected_mode
            )
        else:
            await interaction.response.send_message("❌ Coordle game module not loaded.", ephemeral=True)

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.primary, emoji="🏆", row=2)
    async def leaderboard_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        coordle_cog = self.bot.get_cog("Coordle")
        if coordle_cog:
            await coordle_cog.show_leaderboard(interaction)
        else:
            await interaction.response.send_message("❌ Coordle game module not loaded.", ephemeral=True)

    @discord.ui.button(label="Mode: Normal", style=discord.ButtonStyle.secondary, emoji="⏱️", row=2)
    async def mode_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_mode == "normal":
            self.selected_mode = "blitz"
            button.label = "Mode: Blitz"
            button.emoji = "⚡"
            button.style = discord.ButtonStyle.danger
        else:
            self.selected_mode = "normal"
            button.label = "Mode: Normal"
            button.emoji = "⏱️"
            button.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(embed=self.get_setup_embed(), view=self)

    @discord.ui.button(label="Rules", style=discord.ButtonStyle.secondary, emoji="📖", row=2)
    async def rules_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.coordle import build_rules_embed
        await interaction.response.send_message(embed=build_rules_embed(), ephemeral=True)

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary, emoji="◀", row=2)
    async def return_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        games_menu_panel = discord.Embed(
            title="🎮 Interactive Party & Mini-Games",
            description="Choose a mini-game to play with your friends or alliance members:",
            colour=discord.Colour.og_blurple()
        )
        games_menu_panel.add_field(
            name="🤷 Would you rather ...",
            value="> Pick between impossible scenarios and see live community vote splits.",
            inline=False
        )
        games_menu_panel.add_field(
            name="🎲 Russian Roulette",
            value="> Turn-based revolver luck challenge. Play solo or test your luck in a multiplayer lobby!",
            inline=False
        )
        games_menu_panel.add_field(
            name="🟩 Co-ordle (Wordle)",
            value="> Cooperative word-guessing puzzle with custom word lengths and attempts!",
            inline=False
        )
        await interaction.response.edit_message(embed=games_menu_panel, view=GameMenuButtons(self.bot))


class UtilityMenuButtons(BaseView):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="Redeem for Everyone", style=discord.ButtonStyle.primary, emoji="🪙", row=0)
    async def redeem_for_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redeem_cog = self.bot.get_cog("CodeRedeem")
        if redeem_cog:
            await interaction.response.send_modal(RedeemModal(redeem_cog))
        else:
            await interaction.response.send_message("CodeRedeem module error", ephemeral=True)

    @discord.ui.button(label="Redeem for Single Player", style=discord.ButtonStyle.primary, emoji="👤", row=0)
    async def redeem_for_player_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redeem_cog = self.bot.get_cog("CodeRedeem")
        if redeem_cog:
            await interaction.response.send_modal(RedeemSingleModal(redeem_cog))
        else:
            await interaction.response.send_message("CodeRedeem module error", ephemeral=True)

    @discord.ui.button(label="Redeem History", style=discord.ButtonStyle.secondary, emoji="📜", row=1)
    async def redeem_history_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        redeem_cog = self.bot.get_cog("CodeRedeem")
        if redeem_cog:
            await redeem_cog.redeem_history(interaction)
        else:
            await interaction.response.send_message("CodeRedeem module error", ephemeral=True)

    @discord.ui.button(label="Rally Countdown", style=discord.ButtonStyle.primary, emoji="🎙️", row=1)
    async def rally_countdown_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎙️ Rally Countdown Panel",
            description="Select one of the preset timers below, trigger a custom countdown, or stop the voice client.",
            color=discord.Color.og_blurple()
        )
        await interaction.response.edit_message(embed=embed, view=RallyCountdownView(self.bot))

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary, emoji="◀", row=2)
    async def return_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = MainMenuEmbed(self.bot)
        view = MenuButtons(self.bot)
        await interaction.response.edit_message(embed=embed, view=view)


class ConfirmRedeemView(BaseView):
    def __init__(self, author_id: int, on_confirm, on_cancel=None):
        super().__init__(timeout=90)
        self.author_id = author_id
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel
        self.value = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not await super().interaction_check(interaction):
            return False
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


class BatchProgressView(BaseView):
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


class WyrButtons(BaseView):
    def __init__(self, bot: commands.Bot, cog_instance, question_data: dict):
        super().__init__(timeout=43200)
        self.bot = bot
        self.cog = cog_instance
        self.question_data = question_data
        self.question_id = question_data.get("id") if isinstance(question_data, dict) else None
        if isinstance(question_data, dict):
            self.option_a = question_data.get("option_a", "")
            self.option_b = question_data.get("option_b", "")
            self.global_a = question_data.get("votes_a", 0)
            self.global_b = question_data.get("votes_b", 0)
        elif isinstance(question_data, (list, tuple)):
            self.option_a = question_data[0]
            self.option_b = question_data[1]
            self.global_a = 0
            self.global_b = 0
        else:
            self.option_a = ""
            self.option_b = ""
            self.global_a = 0
            self.global_b = 0

        self.voter_A = set()
        self.voter_B = set()
        self.message = None

    def get_embed(self) -> discord.Embed:
        from utils.embeds import WyrEmbed
        return WyrEmbed(
            question_a=self.option_a,
            question_b=self.option_b,
            count_a=len(self.voter_A),
            count_b=len(self.voter_B),
            global_a=self.global_a + len(self.voter_A),
            global_b=self.global_b + len(self.voter_B)
        )

    @discord.ui.button(label="Option A", style=discord.ButtonStyle.primary, emoji="🅰️", custom_id="wyr_a")
    async def button_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in self.voter_A:
            self.voter_A.remove(user_id)
        else:
            if user_id in self.voter_B:
                self.voter_B.remove(user_id)
            self.voter_A.add(user_id)
            if self.question_id and hasattr(self.bot, 'database') and hasattr(self.bot.database, 'record_wyr_vote'):
                asyncio.create_task(self.bot.database.record_wyr_vote(self.question_id, 'A'))

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Option B", style=discord.ButtonStyle.primary, emoji="🅱️", custom_id="wyr_b")
    async def button_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in self.voter_B:
            self.voter_B.remove(user_id)
        else:
            if user_id in self.voter_A:
                self.voter_A.remove(user_id)
            self.voter_B.add(user_id)
            if self.question_id and hasattr(self.bot, 'database') and hasattr(self.bot.database, 'record_wyr_vote'):
                asyncio.create_task(self.bot.database.record_wyr_vote(self.question_id, 'B'))

        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="New Question", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="new_question")
    async def new_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await self.cog.start_wyr_game(interaction)


class RallyCountdownView(BaseView):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=43200)
        self.bot = bot

    @discord.ui.button(label="6s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_6(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 6s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 6)

    @discord.ui.button(label="8s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_8(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 8s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 8)

    @discord.ui.button(label="10s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 10s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 10)

    @discord.ui.button(label="12s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_12(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 12s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 12)

    @discord.ui.button(label="14s", style=discord.ButtonStyle.primary, row=0)
    async def seconds_14(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎙️ Starting 14s countdown...", ephemeral=True)
        await play_voice_countdown(interaction, 14)

    @discord.ui.button(label="Join Voice", style=discord.ButtonStyle.success, row=1)
    async def join_voice_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc, err = await get_or_connect_vc(interaction)
        if err:
            await interaction.response.send_message(err, ephemeral=True)
        else:
            await interaction.response.send_message(f"🎙️ Connected to **{vc.channel.name}**! Instant countdowns ready.", ephemeral=True)

    @discord.ui.button(label="Custom Countdown", style=discord.ButtonStyle.primary, row=1)
    async def custom_countdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomCountdownModal())

    @discord.ui.button(label="Stop / Disconnect", style=discord.ButtonStyle.danger, row=1)
    async def stop_countdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        stopped = await stop_voice(interaction)
        if stopped:
            await interaction.response.send_message("⏹️ Stopped countdown and disconnected.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bot is not connected to a voice channel.", ephemeral=True)

    @discord.ui.button(label="Return", style=discord.ButtonStyle.secondary, row=1)
    async def return_to_utilities(self, interaction: discord.Interaction, button: discord.ui.Button):
        utility_menu_panel = discord.Embed(
            title="Choose one of the options below:",
            colour=discord.Colour.yellow()
        )
        utility_menu_panel.add_field(
            name="🪙 Redeem codes for everyone",
            value="> **A new KS gift code has been released?**\nRedeem it for everyone now (Please take note, that the process might take some time to finish.)",
            inline=False
        )
        utility_menu_panel.add_field(
            name="👤 Redeem code for one player",
            value="> Redeem a KS gift code for a single player ID instantly.",
            inline=False
        )
        utility_menu_panel.add_field(
            name="🎙️ Rally Countdown Panel",
            value="> Open the interactive voice countdown panel for rallies.",
            inline=False
        )
        await interaction.response.edit_message(embed=utility_menu_panel, view=UtilityMenuButtons(self.bot))