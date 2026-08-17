import discord
from utils.countdown import play_voice_countdown


class RedeemModal(discord.ui.Modal, title='Gift Code'):
    code_input = discord.ui.TextInput(
        label='Enter the Gift Code',
        placeholder='e.g. KINGDOMSTAR',
        min_length=3,
        max_length=30,
        required=True
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog  # Pass the cog so we can call the redeem logic

    async def on_submit(self, interaction: discord.Interaction):
        gift_code = self.code_input.value.strip()

        # Call the helper function we just made in the Cog
        await self.cog.redeem_code_for_all(interaction, gift_code)


class RedeemSingleModal(discord.ui.Modal, title='Redeem for Single Player'):
    code_input = discord.ui.TextInput(
        label='Enter the Gift Code',
        placeholder='e.g. KINGDOMSTAR',
        min_length=3,
        max_length=30,
        required=True
    )
    player_input = discord.ui.TextInput(
        label='Enter the Player ID (FID)',
        placeholder='e.g. 49089798',
        min_length=5,
        max_length=20,
        required=True
    )
    kingdom_input = discord.ui.TextInput(
        label='Kingdom ID (Optional - default: saved/278)',
        placeholder='e.g. 278',
        required=False,
        max_length=10
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        gift_code = self.code_input.value.strip()
        player_id = self.player_input.value.strip()
        kingdom_id = self.kingdom_input.value.strip() or None
        await self.cog.redeem_code_for_player(interaction, gift_code, player_id, kingdom_id)


class SearchPlayerModal(discord.ui.Modal, title='Search / Edit Player'):
    query_input = discord.ui.TextInput(
        label='Enter Player Name, FID, or Alliance',
        placeholder='e.g. HimAlt or 117280427',
        min_length=2,
        max_length=50,
        required=True
    )

    def __init__(self, player_manager_cog):
        super().__init__()
        self.cog = player_manager_cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.search_player(interaction, self.query_input.value.strip())


class CustomCountdownModal(discord.ui.Modal, title='Custom Countdown'):
    seconds_input = discord.ui.TextInput(
        label='Seconds',
        placeholder='Enter number of seconds (e.g. 15)',
        min_length=1,
        max_length=3,
        required=True
    )

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        try:
            seconds = int(self.seconds_input.value.strip())
            if seconds <= 0 or seconds > 60:
                await interaction.response.send_message("❌ Please enter a number between 1 and 60 seconds.", ephemeral=True)
                return
            await interaction.response.send_message(f"🎙️ Starting {seconds}s custom countdown...", ephemeral=True)
            await play_voice_countdown(interaction, seconds)
        except ValueError:
            await interaction.response.send_message("❌ Invalid number entered. Please enter an integer.", ephemeral=True)


# class MessageModal(discord.ui.Modal, title='Send a Message'):
#     message_input = discord.ui.TextInput(
#         label='What do you want to send?',
#         style=discord.TextStyle.paragraph,
#         placeholder='Type your message here...',
#         required=True,
#         max_length=500,
#     )
#
#     async def on_submit(self, interaction: discord.Interaction):
#         mention = f"<@1269222243569897513>"
#         full_message = f"{mention}\n<@{interaction.user.id}> says {self.message_input.value}"
#
#         await interaction.response.send_message(full_message)