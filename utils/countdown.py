import os
import subprocess
import time
import asyncio
from pathlib import Path
import gtts
import discord


def generate_audio_files(count: int):
    base_path = Path(__file__).resolve().parent.parent / "audio"
    base_path.mkdir(parents=True, exist_ok=True)

    for i in range(count + 1):
        file_path = base_path / f"audioNumber_{i}.mp3"

        if file_path.exists():
            continue

        print(f"Generating and Optimizing: {file_path.name}")

        # 1. Create a temporary path for the raw gTTS output
        temp_path = base_path / f"temp_{i}.mp3"

        # 2. Generate the raw MP3 via gTTS
        tts = gtts.gTTS(text=str(i), lang="en")
        tts.save(str(temp_path))

        # 3. Use FFmpeg to re-encode for Discord/Ubuntu
        # -ar 48000: Sets sample rate to 48kHz (Discord native)
        # -ac 2: Sets to 2 channels (stereo)
        # -b:a 128k: Sets a constant 128kbps bitrate
        try:
            subprocess.run([
                'ffmpeg', '-y', '-i', str(temp_path),
                '-ar', '48000',
                '-ac', '2',
                '-b:a', '128k',
                str(file_path)
            ], check=True, capture_output=True)

        except subprocess.CalledProcessError as e:
            print(f"FFmpeg Error for {i}: {e.stderr.decode()}")
        finally:
            # 4. Clean up the temporary raw file
            if temp_path.exists():
                os.remove(temp_path)


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





async def play_voice_countdown(interaction_or_ctx, count: int):
    # 1. Setup Paths IMMEDIATELY
    current_file = Path(__file__).resolve()
    audio_dir = current_file.parent.parent / "audio"

    # Ensure the directory actually exists on the OS
    audio_dir.mkdir(parents=True, exist_ok=True)

    print("--- UBUNTU VOICE START ---")

    # 2. Corrected Generation Check
    # Use the absolute path to check for the file
    check_file = audio_dir / f"audioNumber_{count}.mp3"

    if not check_file.exists():
        print(f"Generating files in: {audio_dir}")
        await asyncio.to_thread(generate_audio_files, count)

    user = interaction_or_ctx.user if hasattr(interaction_or_ctx, 'user') else interaction_or_ctx.author
    guild = interaction_or_ctx.guild

    if not user.voice:
        return await interaction_or_ctx.channel.send("❌ Join a voice channel first!")

    if guild.voice_client:
        await guild.voice_client.disconnect(force=True)
        await asyncio.sleep(0.5)

    vc = None
    try:
        vc = await user.voice.channel.connect(timeout=10.0)
        print(f"Connected to {user.voice.channel.name}")

        await asyncio.sleep(1.5)
        start_time = time.perf_counter()
        for i in range(count, -1, -1):
            if not vc.is_connected():
                break

            file_path = audio_dir / f"audioNumber_{i}.mp3"

            if file_path.exists():
                source = discord.FFmpegPCMAudio(str(file_path), before_options="-loglevel panic")

                if vc.is_playing():
                    vc.stop()

                await asyncio.sleep(0.05)
                vc.play(source)
                # print(f"Playing: {file_path.name}")
            # else:
            #     print(f"❌ File not found: {file_path}")

            await asyncio.sleep(0.95)
        end_time = time.perf_counter()
        while vc.is_playing():
            await asyncio.sleep(1)

        result_time = end_time - start_time
        print(f"Countdown to {count} finished in {result_time}s")

    except Exception as e:
        print(f"⚠️ Ubuntu Playback Error: {e}")

    finally:
        if vc and vc.is_connected():
            print("Disconnecting...")
            await vc.disconnect()

# generate_audio_files(10)