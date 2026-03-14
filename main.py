import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands

from databases.wyr_database import Question_Database


class DiscordGameUtilityBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all(), owner_id=210022124423741440)
        self.database = Question_Database()

    async def setup_hook(self):
        await self.database.init_db()
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')

bot = DiscordGameUtilityBot()

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print("Connected to the Question Bank")
    # This manually loads the opus library for Ubuntu
    if not discord.opus.is_loaded():
        try:
            # Common path for Ubuntu 64-bit
            discord.opus.load_opus('libopus.so.0')
            print("✅ Opus library loaded successfully.")
        except Exception as e:
            print(f"❌ Failed to load Opus: {e}")

    print(f'Logged in as {bot.user}')

@bot.event
async def on_connect():
    print(f'Connected to {bot.user.name}')
    for server in bot.guilds:
        print(f"Connected to {server.name} (ID: {server.id})")

@bot.command()
async def ping(ctx):
    await ctx.send("pong")


@bot.command()
@commands.is_owner()
async def sync(ctx):
    # 1. Clear the "thinking" state if it's a long process
    await ctx.send("Syncing... please wait.")

    # 2. Copy the global commands to this specific server
    bot.tree.copy_global_to(guild=ctx.guild)

    # 3. Sync specifically to this server
    synced = await bot.tree.sync(guild=ctx.guild)

    await ctx.send(f"✅ Successfully synced {len(synced)} commands to this server!")

@bot.command()
@commands.is_owner()
async def reload(ctx, extension: str):
    try:
        await bot.reload_extension(f'cogs.{extension}')
        await ctx.send(f'✅ Successfully reloaded `{extension}`')
    except Exception as e:
        await ctx.send(f'❌ Failed to reload `{extension}`\n```python\n{e}\n```')

async def main():
    token = open("token.txt", "r").read().strip()
    async with bot:
        await bot.start(token)

asyncio.run(main())
