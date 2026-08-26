import discord
from discord.ext import commands


class MainMenuEmbed(discord.Embed):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        super().__init__(
            title="Main Menu",
            description="*Hello there! Select a module below to get started.*",
            colour=discord.Colour.brand_red()
        )

        self.add_field(
            name="🎮 Games",
            value="> Challenge your friends to\n> interactive mini-games.",
            inline=True
        )
        self.add_field(
            name="👥 Players",
            value="> Manage player IDs,\n> kingdoms & registry.",
            inline=True
        )
        self.add_field(
            name="🛠️ Utilities",
            value="> Code redemption,\n> countdowns & tools.",
            inline=True
        )

        if self.bot.user:
            self.set_footer(
                text="Discord Games & Utility bot",
                icon_url=self.bot.user.display_avatar.url
            )


class WyrEmbed(discord.Embed):
    def __init__(self, question_a: str, question_b: str, count_a: int = 0, count_b: int = 0, global_a: int = 0, global_b: int = 0):
        super().__init__(
            title="🤷 Would You Rather...",
            colour=discord.Colour.blurple()
        )
        bar_a, bar_b, pct_a, pct_b = self.calculate_bar(count_a, count_b)
        total = count_a + count_b

        self.description = (
            f"**🅰️ Option A**\n> **{question_a}**\n"
            f"`{bar_a}` **{pct_a}%** ({count_a} vote{'s' if count_a != 1 else ''})\n\n"
            f"**🅱️ Option B**\n> **{question_b}**\n"
            f"`{bar_b}` **{pct_b}%** ({count_b} vote{'s' if count_b != 1 else ''})"
        )

        global_total = global_a + global_b
        if global_total > 0:
            g_pct_a = int(round((global_a / global_total) * 100))
            g_pct_b = 100 - g_pct_a
            self.set_footer(text=f"Total Session Votes: {total} • Global: A {g_pct_a}% vs B {g_pct_b}% ({global_total} total)")
        else:
            self.set_footer(text=f"Total Session Votes: {total} • Cast your vote below!")

    @staticmethod
    def calculate_bar(count_a: int, count_b: int, total_length: int = 12):
        total = count_a + count_b
        if total == 0:
            return "░" * total_length, "░" * total_length, 0, 0
        pct_a = int(round((count_a / total) * 100))
        pct_b = 100 - pct_a
        filled_a = int(round((count_a / total) * total_length))
        filled_b = total_length - filled_a
        bar_a = "█" * filled_a + "░" * (total_length - filled_a)
        bar_b = "█" * filled_b + "░" * (total_length - filled_b)
        return bar_a, bar_b, pct_a, pct_b