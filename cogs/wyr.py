import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks

class Wyr(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def start_game(self, interaction: discord.Interaction):
        await self.start_wyr_game(interaction)

    async def start_wyr_game(self, interaction: discord.Interaction):
        # If the interaction was already responded to (from the 'New Question' button)
        # we use followup. If it's a fresh slash command, we defer.
        if not interaction.response.is_done():
            await interaction.response.defer()

        question = await self.bot.database.get_random_wyr_question()

        if not question:
            await interaction.followup.send("No questions available in the database.", ephemeral=True)
            return

        panel = WyrEmbed(question[0], question[1])
        # Pass the bot and this cog instance to the view
        view = WyrButtons(self.bot, self)

        message = await interaction.followup.send(embed=panel, view=view, wait=True)

        view.message = message
        view.update_panel.start()

    @app_commands.command(name="wyr", description="Would you rather? game")
    async def wyr(self, interaction: discord.Interaction):
        await self.start_game(interaction)


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


class WyrButtons(discord.ui.View):
    def __init__(self, bot, cog_instance): # Accept bot and cog
        super().__init__(timeout=300)
        self.bot = bot
        self.cog = cog_instance
        self.voter_A = set()
        self.voter_B = set()
        self.message = None

    @discord.ui.button(label="A", style=discord.ButtonStyle.primary, custom_id="wyr_a")
    async def button_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.voter_B:
            self.voter_B.remove(interaction.user.id)
        self.voter_A.add(interaction.user.id)
        await interaction.response.defer()

    @discord.ui.button(label="B", style=discord.ButtonStyle.primary, custom_id="wyr_b")
    async def button_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.voter_A:
            self.voter_A.remove(interaction.user.id)
        self.voter_B.add(interaction.user.id)
        await interaction.response.defer()

    @discord.ui.button(label="New question", style=discord.ButtonStyle.secondary, custom_id="new_question")
    async def new_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Stop the current background loop before starting a new one
        self.update_panel.stop()

        # Disable current buttons so people don't click twice while loading
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        # Call the start_game method from the Cog
        await self.cog.start_wyr_game(interaction)

    @tasks.loop(seconds=3)
    async def update_panel(self):
        if self.message:
            try:
                panel = self.message.embeds[0]
                panel.set_field_at(0, name="Votes", value=f"A: {len(self.voter_A)} | B: {len(self.voter_B)}")
                await self.message.edit(embed=panel)
            except Exception as e:
                print(f"Loop error: {e}")
                self.update_panel.stop()

    async def on_timeout(self):
        self.update_panel.stop()
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)

async def setup(bot):
    print("Wyr cog loaded")
    await bot.add_cog(Wyr(bot))
