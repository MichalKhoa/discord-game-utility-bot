import asyncio
import os

import discord
from discord import app_commands
from discord.ext import commands

import database
from database import Question_Database


class DiscordGameUtilityBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
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

@bot.event
async def on_connect():
    print(f'Connected to {bot.user.name}')
    for server in bot.guilds:
        print(f"Connected to {server.name} (ID: {server.id})")

@bot.command()
async def ping(ctx):
    await ctx.send("pong")

@bot.command()
@commands.is_owner
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("Tree synced!")

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
