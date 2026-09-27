import asyncio
import os
import importlib
import logging
import sys

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("DiscordGameUtilityBot")

# Reconfigure stdout/stderr to use UTF-8 to prevent UnicodeEncodeErrors on some terminals
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import discord
from discord import app_commands
from discord.ext import commands

import databases.wyr_database
from databases.wyr_database import Question_Database
from databases.player_database import PlayerDatabase
from databases.coordle_database import CoordleDatabase


class DiscordGameUtilityBot(commands.Bot):
    def __init__(self):
        owner_id_env = os.environ.get("OWNER_ID", "210022124423741440")
        owner_id = int(owner_id_env) if owner_id_env.isdigit() else 210022124423741440
        super().__init__(
            command_prefix=commands.when_mentioned_or("n!"),
            intents=discord.Intents.all(),
            owner_id=owner_id,
        )
        self.wyr_db = Question_Database()
        self.database = self.wyr_db  # backward compatibility
        self.player_db = PlayerDatabase()
        self.coordle_db = CoordleDatabase()

    async def setup_hook(self):
        await self.wyr_db.init_db(seed_defaults=True)
        await self.player_db.init_db()
        await self.coordle_db.init_db()
        cogs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cogs')
        for filename in os.listdir(cogs_dir):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f"Loaded extension: {filename}")
                except Exception as e:
                    logger.error(f"Failed to load extension {filename}: {e}")

bot = DiscordGameUtilityBot()

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user.name}')
    logger.info("Connected to the Question Bank")
    # This manually loads the opus library for Ubuntu
    if not discord.opus.is_loaded():
        try:
            # Common path for Ubuntu 64-bit
            discord.opus.load_opus('libopus.so.0')
            logger.info("✅ Opus library loaded successfully.")
        except Exception as e:
            logger.warning(f"Opus not loaded via libopus.so.0: {e}")

    try:
        import davey
        logger.info("✅ Davey library is installed and available for voice E2EE.")
    except ImportError:
        logger.warning("⚠️ Davey library is NOT installed. Voice connection might fail.")

    logger.info(f'Bot ready: {bot.user}')

@bot.event
async def on_connect():
    logger.info(f'Connected to Discord Gateway as {bot.user.name}')
    for server in bot.guilds:
        logger.info(f"Connected to {server.name} (ID: {server.id})")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.NotOwner):
        await ctx.send("❌ Only the bot owner can use this command.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You do not have the required permissions to run this command.")
    else:
        print(f"Command error in {ctx.command}: {error}")
        await ctx.send(f"❌ Error: {error}")

@bot.command()
async def ping(ctx):
    await ctx.send("pong")



@bot.command()
@commands.guild_only()
async def sync(ctx: commands.Context, guilds: commands.Greedy[discord.Object], spec: str = None) -> None:
    """Syncs slash commands to Discord.

    Usage:
        !sync         -> Syncs all global commands.
        !sync ~       -> Syncs commands to the current guild.
        !sync *       -> Copies global commands to the current guild and syncs.
        !sync ^       -> Clears all commands from the current guild and syncs.
        !sync [guild] -> Syncs all commands to a specific guild ID.
    """
    is_owner = await ctx.bot.is_owner(ctx.author)
    is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
    if not (is_owner or is_admin):
        await ctx.send("❌ You do not have permission to run this command. (Requires Bot Owner or Server Administrator)")
        return

    if not guilds:
        if spec == "~":
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "*":
            ctx.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await ctx.bot.tree.sync(guild=ctx.guild)
        elif spec == "^":
            ctx.bot.tree.clear_commands(guild=ctx.guild)
            await ctx.bot.tree.sync(guild=ctx.guild)
            synced = []
        else:
            synced = await ctx.bot.tree.sync()

        mode = "globally" if spec is None else "to the current guild"
        await ctx.send(f"✅ Synced {len(synced)} commands {mode}.")
        return

    ret = 0
    for guild in guilds:
        try:
            await ctx.bot.tree.sync(guild=guild)
        except discord.HTTPException as e:
            print(f"Failed to sync for guild {guild.id}: {e}")
        else:
            ret += 1

    await ctx.send(f"✅ Synced the command tree to {ret}/{len(guilds)} guilds.")

@bot.command()
@commands.is_owner()
async def reload(ctx, extension: str):
    """Reloads a specific cog extension."""
    try:
        await bot.reload_extension(f'cogs.{extension}')
        await ctx.send(f'✅ Successfully reloaded `{extension}`')
    except Exception as e:
        await ctx.send(f'❌ Failed to reload `{extension}`\n```python\n{e}\n```')

@bot.command()
@commands.is_owner()
async def reload_util(ctx, util_name: str):
    """Reloads a utility module. Note: Cogs using this util must also be reloaded."""
    try:
        # Construct the full module path, e.g., 'utils.redeem_code'
        module_path = f'utils.{util_name}'
        module = importlib.import_module(module_path)
        importlib.reload(module)
        await ctx.send(f'✅ Successfully reloaded utility `{util_name}`. \n'
                       f'⚠️ Remember to reload cogs that depend on this utility!')
    except Exception as e:
        await ctx.send(f'❌ Failed to reload utility `{util_name}`\n```python\n{e}\n```')

lock_file_handle = None

def acquire_lock():
    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".bot.lock")
    global lock_file_handle
    try:
        import fcntl
        # Open lock file. Keep file handle open for the duration of the process.
        lock_file_handle = open(lock_path, "w")
        fcntl.lockf(lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file_handle.write(str(os.getpid()))
        lock_file_handle.flush()
    except ImportError:
        # Fallback for Windows using msvcrt
        try:
            import msvcrt
            lock_file_handle = open(lock_path, "a+")
            lock_file_handle.seek(0)
            msvcrt.locking(lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
            lock_file_handle.seek(0)
            lock_file_handle.truncate()
            lock_file_handle.write(str(os.getpid()))
            lock_file_handle.flush()
        except (ImportError, OSError):
            logger.error("❌ Another instance of the bot is already running (Windows lock failed). Exiting.")
            sys.exit(1)
    except (IOError, OSError):
        logger.error("❌ Another instance of the bot is already running (failed to acquire file lock). Exiting.")
        sys.exit(1)

async def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        token_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.txt")
        if os.path.exists(token_path):
            with open(token_path, "r") as f:
                token = f.read().strip()
                
    if not token:
        logger.error("❌ Error: No Discord token found. Please set the DISCORD_TOKEN environment variable or create token.txt.")
        sys.exit(1)
        
    async with bot:
        await bot.start(token)

if __name__ == '__main__':
    acquire_lock()
    asyncio.run(main())
