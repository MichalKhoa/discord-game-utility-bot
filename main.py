import os
import asyncio
import discord
from pathlib import Path


async def play_voice_countdown(interaction_or_ctx, count: int):
    print("--- UBUNTU VOICE START ---")

    user = interaction_or_ctx.user if hasattr(interaction_or_ctx, 'user') else interaction_or_ctx.author
    guild = interaction_or_ctx.guild

    if not user.voice:
        return await interaction_or_ctx.channel.send("❌ Join a voice channel first!")

    # 1. Setup Paths (The Linux Way)
    # This gets the directory where countdown.py lives
    current_file = Path(__file__).resolve()
    # Go up one level to Project Root, then into audio
    audio_dir = current_file.parent.parent / "audio"

    # 2. Connection Logic
    if guild.voice_client:
        await guild.voice_client.disconnect(force=True)
        await asyncio.sleep(0.5)

    try:
        vc = await user.voice.channel.connect(timeout=10.0)
        print(f"Connected to {user.voice.channel.name}")

        # Essential: Give Linux a second to initialize the stream
        await asyncio.sleep(1.5)

        for i in range(count):
            if not vc.is_connected():
                break

            # Linux is CASE SENSITIVE. Ensure filenames match exactly.
            file_path = audio_dir / f"audioNumber_{i}.mp3"

            if file_path.exists():
                # On Ubuntu, we don't need 'executable=' because ffmpeg is in /usr/bin/
                source = discord.FFmpegPCMAudio(str(file_path))

                if vc.is_playing():
                    vc.stop()

                vc.play(source)
                print(f"Playing: {file_path.name}")
            else:
                print(f"❌ File not found: {file_path}")

            await asyncio.sleep(1)

    except Exception as e:
        print(f"⚠️ Ubuntu Playback Error: {e}")

    finally:
        if vc and vc.is_connected():
            print("Disconnecting...")
            await vc.disconnect()