import os
import time

import gtts
import asyncio
import discord

def generate_audio_files(count: int):
    if not os.path.exists("../audio"):
        os.makedirs("../audio")

    for i in range(0, count):
        if os.path.exists("../audio/audioNumber_" + str(i) + ".mp3"):
            continue
        textToConvert = f'{i}'.lower()
        audio = gtts.gTTS(text=textToConvert, lang="en", )
        filePath = f"../audio/audioNumber_{i}.mp3"
        audio.save(filePath)


# def play_audio(count):
#     if not pygame.mixer.get_init():
#         pygame.mixer.init()
#
#     if not os.path.exists("../audio/audioNumber_" + str(count) + ".mp3"):
#         generate_audio_files(count)
#
#     for i in range(0, count):
#         pygame.mixer.music.load(f"../audio/audioNumber_{i}.mp3")
#         pygame.mixer.music.play()
#
#         time.sleep(1)
#
#         pygame.mixer.music.stop()
#
#
# def play_fast_sequence(count, interval=1):
#     if not os.path.exists("../audio/audioNumber_" + str(count) + ".mp3"):
#         generate_audio_files(count)
#
#     pygame.mixer.init()
#     # Create multiple channels so sounds can overlap if they run long
#     channels = [pygame.mixer.Channel(i) for i in range(8)]
#
#     for i in range(0, count):
#         sound = pygame.mixer.Sound(f"../audio/audioNumber_{i}.mp3")
#         # Use modulo to cycle through channels
#         channels[i % 2].play(sound)
#
#         # This interval controls the "speed" of the sequence
#         time.sleep(interval)


import os
import asyncio
import discord

import os
import asyncio
import discord


async def play_voice_countdown(interaction_or_ctx, count: int):
    print("--- STARTING RALLY COUNTDOWN ---")

    # 1. Setup Context
    user = interaction_or_ctx.user if hasattr(interaction_or_ctx, 'user') else interaction_or_ctx.author
    guild = interaction_or_ctx.guild

    if not user.voice:
        return await interaction_or_ctx.channel.send("❌ Join a voice channel first!")

    # 2. Define Paths relative to this file
    # This file is in /utils, so ".." goes to the Project Root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, ".."))

    audio_dir = os.path.join(project_root, "audio")
    ffmpeg_exe = os.path.join(project_root, "ffmpeg.exe")

    # Debug: Ensure FFmpeg exists
    if not os.path.exists(ffmpeg_exe):
        print(f"❌ CRITICAL: ffmpeg.exe not found at {ffmpeg_exe}")
        return await interaction_or_ctx.channel.send("⚠️ Bot Error: FFmpeg is missing from the server.")

    # 3. Handle Voice Connection
    if guild.voice_client:
        await guild.voice_client.disconnect(force=True)
        await asyncio.sleep(0.5)

    try:
        vc = await user.voice.channel.connect(timeout=10.0)
        print(f"Connected to {user.voice.channel.name}")

        # Give Discord a second to open the audio stream
        await asyncio.sleep(1.5)

        for i in range(count):
            if not vc.is_connected():
                break

            # Adjust this filename if your files are named differently (e.g., 'Number_0.mp3')
            file_path = os.path.join(audio_dir, f"audioNumber_{i}.mp3")

            if os.path.exists(file_path):
                # We pass the 'executable' path directly here
                source = discord.FFmpegPCMAudio(file_path, executable=ffmpeg_exe)

                if vc.is_playing():
                    vc.stop()

                vc.play(source)
                print(f"Playing: audioNumber_{i}.mp3")
            else:
                print(f"⚠️ Missing file: {file_path}")

            await asyncio.sleep(1)  # Seconds between numbers

    except Exception as e:
        print(f"⚠️ Playback Error: {e}")

    finally:
        if vc and vc.is_connected():
            print("Finished countdown. Disconnecting.")
            await vc.disconnect()