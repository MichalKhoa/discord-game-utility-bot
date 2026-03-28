import discord


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


class MessageModal(discord.ui.Modal, title='Send a Message'):
    message_input = discord.ui.TextInput(
        label='What do you want to send?',
        style=discord.TextStyle.paragraph,
        placeholder='Type your message here...',
        required=True,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        mention = f"<@1269222243569897513>"
        full_message = f"{mention}\n{self.message_input.value}"

        await interaction.response.send_message(full_message)