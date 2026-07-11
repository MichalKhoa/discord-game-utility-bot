import random
import discord
from discord import app_commands
from discord.ext import commands

ROASTS = [
    "I'd agree with you but then we'd both be wrong.",
    "You're like a cloud. When you disappear, it's a beautiful day.",
    "You have a face for radio and a voice for silent films.",
    "If I had a dollar for every smart thing you say, I'd be broke.",
    "You are like a software update. Whenever I see you, I think 'not now'.",
    "You're not the dumbest person in the world, but you better hope they don't die.",
    "I'd offer you some advice, but you'd probably find a way to break it.",
    "You make me wish I had more hands, just so I could give your comments more thumbs down.",
    "Your brain has a '404: Not Found' error on standby.",
    "If you were a spice, you’d be flour.",
    "You have a lot of potential, and you'll always have it.",
    "You are the human equivalent of a participation trophy.",
    "If you ran as fast as your mouth, you'd be an Olympic athlete.",
    "You're like a dictionary. You make sense, but you're really boring to listen to.",
    "You bring a lot of value... just by standing still and being quiet.",
    "You bring everyone so much joy... when you leave the room.",
    "I'd explain it to you, but I don't have the time or the crayons.",
    "Your secrets are safe with me. I never listen anyway.",
    "If you were any more simple, we'd have to water you.",
    "You're not stupid; you just have bad luck when you try to think.",
    "Light travels faster than sound. This is why you seem bright until you speak.",
    "If you had another brain cell, it would be lonely.",
    "I've seen plants with better communication skills.",
    "If your brain was made of dynamite, you wouldn't have enough to blow your nose.",
    "You look like a person who claps when the plane lands.",
    "You're the reason they put instructions on shampoo bottles.",
    "You're like a Monday morning. Nobody likes you.",
    "You have a rare gift for making everyone else look extremely smart.",
    "I'm not saying you're lazy, but your spirit animal is a sloth on a rest day.",
    "I'd call you a tool, but even tools are useful.",
    "I envy everyone who hasn't met you.",
    "Your brain is like the Bermuda Triangle. Information goes in, and is never heard from again.",
    "Somewhere out there is a tree tirelessly producing oxygen for you. I think you owe it an apology.",
    "I would roast you, but my mom told me not to burn trash.",
    "If laughter is the best medicine, your face must be curing the world.",
    "You have two brain cells left, and they're fighting for third place.",
    "You look like a before picture.",
    "I can explain it to you, but I can't understand it for you.",
    "It's a shame you can't photoshop your personality.",
    "You're not even a 'has-been.' You're a 'never-was'.",
    "If I gave you a penny for your thoughts, I'd get change back.",
    "I'd say you're a comedian, but comedians are actually funny.",
    "Your only chance of getting a brain cell is if you inhale a dust bunny.",
    "You're proof that evolution can go in reverse.",
    "I'd try to hurt your feelings, but I'm not sure you have the capacity to process them."
]

YO_MAMA_JOKES = [
    "Yo mama's so fat, when she fell she made the Grand Canyon.",
    "Yo mama's so fat, she got stuck in a rotating door.",
    "Yo mama's so fat, when she tried to float in the ocean, Spain claimed her as a new continent.",
    "Yo mama's so fat, when she got hit by a bus, she turned around and said 'Who threw that pebble?'",
    "Yo mama's so old, her birth certificate is written in Roman numerals.",
    "Yo mama's so old, she walked into an antique store and they kept her.",
    "Yo mama's so old, she remembers when the Grand Canyon was just a ditch.",
    "Yo mama's so stupid, she tried to dial 911 on a microwave.",
    "Yo mama's so stupid, she got locked in a grocery store and starved to death.",
    "Yo mama's so stupid, she put a ruler under her pillow to see how long she slept.",
    "Yo mama's so short, she has to use a ladder to look out the cat door.",
    "Yo mama's so short, she has to hang-glide on a Dorito.",
    "Yo mama's so poor, she couldn't afford to pay attention.",
    "Yo mama's so poor, she goes to KFC to lick other people's fingers.",
    "Yo mama's so poor, the ducks throw bread at her.",
    "Yo mama's so poor, she ran down the street with a trash can lid screaming 'stop that plane!'",
    "Yo mama's so lazy, she has a remote control for her remote control.",
    "Yo mama's so lazy, she got a job as a mannequin.",
    "Yo mama's so cheap, she washes disposable paper plates.",
    "Yo mama's so cheap, she returned a free sample.",
    "Yo mama's so slow, it takes her a day to make a 30-minute decision.",
    "Yo mama's so slow, she was late for a 'stay at home' party.",
    "Yo mama's so ugly, when she looks in the mirror, the mirror says 'parental advisory explicit content'.",
    "Yo mama's so ugly, when she walks into a haunted house, she comes out with a job application.",
    "Yo mama's so ugly, she makes onions cry.",
    "Yo mama's so ugly, when she throws a boomerang, it refuses to come back.",
    "Yo mama's so ugly, her birth certificate is an apology letter from the condom factory.",
    "Yo mama's so ugly, the dentist makes her lay face down.",
    "Yo mama's so stupid, she brought a spoon to the Super Bowl.",
    "Yo mama's so stupid, she thought a quarterback was a refund.",
    "Yo mama's so fat, her belt size is Equator.",
    "Yo mama's so fat, she has to use a search warrant to find her keys."
]


class Roast(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="roast", description="Roast a server member!")
    @app_commands.describe(
        member="The member you want to roast (defaults to yourself)"
    )
    async def roast_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        roast_text = random.choice(ROASTS)
        
        embed = discord.Embed(
            description=f"### 🔥 {target.mention}, {roast_text}",
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Roast requested by {interaction.user.name}")
        await interaction.response.send_message(embed=embed)

    @commands.command(name="roast")
    async def roast_prefix(self, ctx: commands.Context, member: discord.Member = None):
        """Roast a member."""
        target = member or ctx.author
        roast_text = random.choice(ROASTS)
        
        embed = discord.Embed(
            description=f"### 🔥 {target.mention}, {roast_text}",
            color=discord.Color.orange()
        )
        embed.set_footer(text=f"Roast requested by {ctx.author.name}")
        await ctx.send(embed=embed)

    @app_commands.command(name="roast-duel", description="Initiate a roast battle between two users!")
    @app_commands.describe(
        player1="The first combatant",
        player2="The second combatant"
    )
    async def roast_duel_slash(self, interaction: discord.Interaction, player1: discord.Member, player2: discord.Member):
        if player1 == player2:
            await interaction.response.send_message("❌ You can't start a duel with yourself!", ephemeral=True)
            return

        roast1 = random.choice(ROASTS)
        roast2 = random.choice(ROASTS)

        embed = discord.Embed(
            title="⚔️ ROAST BATTLE DUEL ⚔️",
            description=f"### {player1.mention} 🆚 {player2.mention}\n\n"
                        f"🔴 **Red Corner:** {player1.mention}\n> ### *\"{roast1}\"*\n\n"
                        f"🔵 **Blue Corner:** {player2.mention}\n> ### *\"{roast2}\"*",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text="React below to vote on who got burned harder!")
        
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        await message.add_reaction("🔴")  # Red Corner
        await message.add_reaction("🔵")  # Blue Corner

    @commands.command(name="roastduel")
    async def roast_duel_prefix(self, ctx: commands.Context, player1: discord.Member, player2: discord.Member):
        """Start a roast duel between two members."""
        if player1 == player2:
            await ctx.send("❌ You can't start a duel with yourself!")
            return

        roast1 = random.choice(ROASTS)
        roast2 = random.choice(ROASTS)

        embed = discord.Embed(
            title="⚔️ ROAST BATTLE DUEL ⚔️",
            description=f"### {player1.mention} 🆚 {player2.mention}\n\n"
                        f"🔴 **Red Corner:** {player1.mention}\n> ### *\"{roast1}\"*\n\n"
                        f"🔵 **Blue Corner:** {player2.mention}\n> ### *\"{roast2}\"*",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text="React below to vote on who got burned harder!")
        
        message = await ctx.send(embed=embed)
        await message.add_reaction("🔴")
        await message.add_reaction("🔵")

    @app_commands.command(name="yomama", description="Tell a classic Yo Mama joke to a server member!")
    @app_commands.describe(
        member="The member you want to direct the joke to (defaults to yourself)"
    )
    async def yomama_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        joke = random.choice(YO_MAMA_JOKES)
        
        embed = discord.Embed(
            description=f"### 👩 {target.mention}, {joke}",
            color=discord.Color.magenta()
        )
        embed.set_footer(text=f"Joke requested by {interaction.user.name}")
        await interaction.response.send_message(embed=embed)

    @commands.command(name="yomama")
    async def yomama_prefix(self, ctx: commands.Context, member: discord.Member = None):
        """Tell a classic Yo Mama joke to a member."""
        target = member or ctx.author
        joke = random.choice(YO_MAMA_JOKES)
        
        embed = discord.Embed(
            description=f"### 👩 {target.mention}, {joke}",
            color=discord.Color.magenta()
        )
        embed.set_footer(text=f"Joke requested by {ctx.author.name}")
        await ctx.send(embed=embed)

async def setup(bot):
    print("Roast cog loaded")
    await bot.add_cog(Roast(bot))
