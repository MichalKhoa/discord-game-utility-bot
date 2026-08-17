import discord
from discord.ext import commands


class MainMenuEmbed(discord.Embed):
    def __init__(self, bot: commands.Bot):
        # Store the bot first!
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

        # Now this will work because self.bot exists
        if self.bot.user:
            self.set_footer(
                text="Discord Games & Utility bot",
                icon_url=self.bot.user.display_avatar.url
            )


class WyrEmbed(discord.Embed):
    def __init__(self, question_a: str, question_b: str):
        # Initialize the parent discord.Embed class
        super().__init__(
            title="Would you rather...",
            description=f"**A.** {question_a}\n\n**OR**\n\n**B.** {question_b}\n\n",
            color=discord.Color.random()
        )
        # Add the initial field
        self.add_field(name="Votes", value="A: 0 | B: 0")