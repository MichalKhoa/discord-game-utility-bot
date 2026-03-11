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
        question = await self.bot.database.get_random_wyr_question()

        panel = discord.Embed(
            title="Would you rather...",
            description=f"**A.** {question[0]}\n\n**OR**\n\n**B.** {question[1]}\n\n",
            color=discord.Color.random()
        )
        panel.add_field(name="Votes", value="A: 0 | B: 0")

        view = WyrButtons()

        if interaction.response.is_done():
            message = await interaction.followup.send(embed=panel, view=view, wait=True)
        else:
            await interaction.response.send_message(embed=panel, view=view)
            message = await interaction.original_response()

        view.message = message
        view.update_panel.start()

    @app_commands.command(name="wyr", description="Would you rather? game")
    async def wyr(self, interaction: discord.Interaction):
        await self.start_game(interaction)


class WyrButtons(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
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
