import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks

class Wyr(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="wyr", description="Would you rather? game")
    async def wyr(self, interaction: discord.Interaction):
        question = await self.bot.database.get_random_wyr_question()

        panel = discord.Embed(
            title="Would you rather...",
            description=f"**A.** {question[0]}\n\n**OR**\n\n**B.** {question[1]}\n\n",
            color=discord.Color.random()
        )
        panel.add_field(name="Votes", value="A: 0 | B: 0")

        view = WyrButtons()

        # 1. Send the initial message
        await interaction.response.send_message(embed=panel, view=view)

        # 2. Get the actual message object so the View can edit it later
        view.message = await interaction.original_response()

        # 3. Start the loop
        view.update_panel.start()


class WyrButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)  # Set a timeout so the loop doesn't run forever
        self.voter_A = set()
        self.voter_B = set()
        self.message = None  # This will be set after the message is sent

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

    @tasks.loop(seconds=3)
    async def update_panel(self):
        if self.message:
            try:
                panel = self.message.embeds[0] # type: ignore
                panel.set_field_at(0, name="Votes", value=f"A: {len(self.voter_A)} | B: {len(self.voter_B)}")

                await self.message.edit(embed=panel)
            except Exception as e:
                print(f"Loop error: {e}")
                self.update_panel.stop()

    async def on_timeout(self):
        self.update_panel.stop()
        # Optional: Disable buttons when the poll ends
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(view=self)

async def setup(bot):
    print("Wyr cog loaded")
    await bot.add_cog(Wyr(bot))