import os
import math
import random
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "roulette")
os.makedirs(ASSETS_DIR, exist_ok=True)

WIDTH = 400
HEIGHT = 240
BG_COLOR = (24, 25, 29, 255)  # Discord dark theme match


def get_font(size: int = 15):
    for path in ["C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_spin_gif(output_path: str):
    font = get_font(15)
    frames = []
    num_frames = 12
    cx, cy = WIDTH // 2, 105
    radius = 56

    for f in range(num_frames):
        im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(im)

        # Outer speed blur streaks
        for s in range(6):
            streak_angle = (f * 30 + s * 60) * math.pi / 180
            r1 = radius + 8
            r2 = radius + 18 + (s % 3) * 6
            x1 = cx + int(r1 * math.cos(streak_angle))
            y1 = cy + int(r1 * math.sin(streak_angle))
            x2 = cx + int(r2 * math.cos(streak_angle + 0.2))
            y2 = cy + int(r2 * math.sin(streak_angle + 0.2))
            draw.line([x1, y1, x2, y2], fill=(210, 180, 80, 140), width=2)

        # Cylinder outer body
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(52, 55, 64), outline=(200, 170, 70), width=3)
        # Cylinder inner bevel
        draw.ellipse([cx - (radius - 5), cy - (radius - 5), cx + (radius - 5), cy + (radius - 5)], outline=(75, 80, 94), width=2)

        # Center extractor pin
        draw.ellipse([cx - 13, cy - 13, cx + 13, cy + 13], fill=(28, 30, 35), outline=(230, 200, 100), width=2)
        draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(210, 180, 80))

        # 6 Chambers revolving
        angle_offset = (f * (360 / num_frames)) * (math.pi / 180)
        for i in range(6):
            a = angle_offset + i * (math.pi / 3)
            ch_x = cx + int(35 * math.cos(a))
            ch_y = cy + int(35 * math.sin(a))

            if i == 0:
                # Live round brass casing
                draw.ellipse([ch_x - 11, ch_y - 11, ch_x + 11, ch_y + 11], fill=(235, 190, 50), outline=(255, 240, 130), width=2)
                # Primer center
                draw.ellipse([ch_x - 4, ch_y - 4, ch_x + 4, ch_y + 4], fill=(185, 140, 25), outline=(255, 245, 160), width=1)
            else:
                # Empty chamber hole
                draw.ellipse([ch_x - 10, ch_y - 10, ch_x + 10, ch_y + 10], fill=(18, 19, 22), outline=(80, 85, 98), width=1)
                draw.ellipse([ch_x - 6, ch_y - 6, ch_x + 6, ch_y + 6], fill=(10, 11, 13))

        # Ratchet notches on cylinder edge
        for i in range(12):
            na = angle_offset + i * (math.pi / 6)
            nx1 = cx + int((radius - 4) * math.cos(na))
            ny1 = cy + int((radius - 4) * math.sin(na))
            nx2 = cx + int(radius * math.cos(na))
            ny2 = cy + int(radius * math.sin(na))
            draw.line([nx1, ny1, nx2, ny2], fill=(150, 130, 50), width=2)

        # Label container & text
        draw.rounded_rectangle([cx - 120, HEIGHT - 46, cx + 120, HEIGHT - 16], radius=6, fill=(35, 36, 42), outline=(200, 170, 70), width=2)
        draw.text((cx, HEIGHT - 31), "CYLINDER SPINNING...", font=font, fill=(255, 215, 80), anchor="mm")

        frames.append(im.convert("RGB"))

    frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=100, loop=0)


def generate_boom_gif(output_path: str):
    font = get_font(15)
    frames = []
    num_frames = 12
    cx, cy = WIDTH // 2, 105

    for f in range(num_frames):
        # Shake offset for explosive impact
        shake_x = random.randint(-5, 5) if (0 <= f <= 4) else 0
        shake_y = random.randint(-4, 4) if (0 <= f <= 4) else 0

        im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(im)

        fx_cx = cx + shake_x
        fx_cy = cy + shake_y

        if 0 <= f <= 3:
            # Initial explosive blast wave & flash
            blast_r = 30 + f * 22
            # Outer blast shockwave
            draw.ellipse([fx_cx - blast_r - 25, fx_cy - blast_r - 25, fx_cx + blast_r + 25, fx_cy + blast_r + 25], fill=(240, 40, 30, 170))
            # Orange fireball
            draw.ellipse([fx_cx - blast_r, fx_cy - blast_r, fx_cx + blast_r, fx_cy + blast_r], fill=(255, 130, 20))
            # Yellow fireball core
            draw.ellipse([fx_cx - (blast_r - 18), fx_cy - (blast_r - 18), fx_cx + (blast_r - 18), fx_cy + (blast_r - 18)], fill=(255, 240, 80))
            # White blast core
            draw.ellipse([fx_cx - 22, fx_cy - 22, fx_cx + 22, fx_cy + 22], fill=(255, 255, 255))

            # Jagged flash spikes
            spikes = 14
            for s in range(spikes):
                sa = (s * (2 * math.pi / spikes)) + (f * 0.35)
                slen = blast_r + 25 + (s % 3) * 18
                sx = fx_cx + int(slen * math.cos(sa))
                sy = fx_cy + int(slen * math.sin(sa))
                draw.line([fx_cx, fx_cy, sx, sy], fill=(255, 250, 150), width=3)
        elif 4 <= f <= 7:
            # Expanding smoke and fire particles
            step = f - 3
            for p in range(8):
                pa = p * (math.pi / 4) + step * 0.2
                dist = 45 + step * 16
                px = fx_cx + int(dist * math.cos(pa))
                py = fx_cy + int(dist * math.sin(pa))
                pr = 22 + step * 4
                smoke_col = (180 - step * 25, 60, 50) if p % 2 == 0 else (95, 90, 95)
                draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=smoke_col)

            # Fiery center
            core_r = max(12, 36 - step * 7)
            draw.ellipse([fx_cx - core_r, fx_cy - core_r, fx_cx + core_r, fx_cy + core_r], fill=(255, 110, 30))

            # Flying spark embers
            for sp in range(16):
                spa = sp * (math.pi / 8) + 0.15
                spdist = 65 + step * 20 + (sp % 4) * 8
                spx = fx_cx + int(spdist * math.cos(spa))
                spy = fx_cy + int(spdist * math.sin(spa))
                draw.ellipse([spx - 3, spy - 3, spx + 3, spy + 3], fill=(255, 230, 90))
        else:
            # Residual smoke cloud and fading embers
            step = f - 7
            for p in range(6):
                pa = p * (math.pi / 3) + 0.5
                dist = 68 + step * 10
                px = fx_cx + int(dist * math.cos(pa))
                py = fx_cy + int(dist * math.sin(pa)) - (step * 7)
                pr = max(14, 30 - step * 3)
                draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(68, 64, 72))

        # Bottom banner with impact styling
        border_col = (255, 60, 50) if f % 2 == 0 else (210, 30, 30)
        draw.rounded_rectangle([cx - 120, HEIGHT - 46, cx + 120, HEIGHT - 16], radius=6, fill=(50, 20, 20), outline=border_col, width=2)
        draw.text((cx, HEIGHT - 31), "BANG! ELIMINATED", font=font, fill=(255, 90, 80), anchor="mm")

        frames.append(im.convert("RGB"))

    frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=100, loop=0)


def generate_safe_gif(output_path: str):
    font = get_font(15)
    frames = []
    num_frames = 12
    cx, cy = WIDTH // 2, 105
    radius = 54

    for f in range(num_frames):
        im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(im)

        # Pulse wave for safe result
        if 1 <= f <= 8:
            pulse_r = radius + f * 9
            draw.ellipse([cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r], outline=(50, 205, 120), width=2)

        # Cylinder body
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(48, 52, 60), outline=(50, 190, 120), width=3)

        # Center pin
        draw.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], fill=(26, 28, 32), outline=(50, 205, 120), width=2)

        # Empty chambers
        for i in range(6):
            a = -math.pi / 2 + i * (math.pi / 3)
            ch_x = cx + int(34 * math.cos(a))
            ch_y = cy + int(34 * math.sin(a))
            draw.ellipse([ch_x - 10, ch_y - 10, ch_x + 10, ch_y + 10], fill=(16, 17, 20), outline=(65, 70, 80), width=1)
            draw.ellipse([ch_x - 6, ch_y - 6, ch_x + 6, ch_y + 6], fill=(10, 11, 13))

        # Top chamber under hammer indicator
        top_x = cx + int(34 * math.cos(-math.pi / 2))
        top_y = cy + int(34 * math.sin(-math.pi / 2))
        draw.ellipse([top_x - 11, top_y - 11, top_x + 11, top_y + 11], outline=(60, 230, 140), width=2)

        # Hammer strike spark and puff of smoke
        if 1 <= f <= 3:
            for sp in range(6):
                sa = sp * (math.pi / 3)
                draw.line([top_x, top_y, top_x + int(12 * math.cos(sa)), top_y + int(12 * math.sin(sa))], fill=(190, 245, 255), width=2)
        elif 4 <= f <= 9:
            step = f - 3
            puff_y = top_y - (step * 5)
            draw.ellipse([top_x - 6 - step, puff_y - 4, top_x + 6 + step, puff_y + 4], fill=(130, 155, 165))

        # Bottom banner with calming emerald styling
        draw.rounded_rectangle([cx - 120, HEIGHT - 46, cx + 120, HEIGHT - 16], radius=6, fill=(20, 44, 30), outline=(50, 205, 120), width=2)
        draw.text((cx, HEIGHT - 31), "CLICK! SURVIVED", font=font, fill=(75, 235, 145), anchor="mm")

        frames.append(im.convert("RGB"))

    frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=100, loop=0)


def main():
    spin_path = os.path.join(ASSETS_DIR, "spin.gif")
    boom_path = os.path.join(ASSETS_DIR, "boom.gif")
    safe_path = os.path.join(ASSETS_DIR, "safe.gif")

    print(f"Generating Russian Roulette GIF assets in {ASSETS_DIR}...")
    generate_spin_gif(spin_path)
    print(f"  -> Generated {spin_path} ({os.path.getsize(spin_path)} bytes)")

    generate_boom_gif(boom_path)
    print(f"  -> Generated {boom_path} ({os.path.getsize(boom_path)} bytes)")

    generate_safe_gif(safe_path)
    print(f"  -> Generated {safe_path} ({os.path.getsize(safe_path)} bytes)")
    print("Done generating all roulette GIF assets.")


if __name__ == "__main__":
    main()
