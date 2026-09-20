import os
import math
import random
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "roulette")
os.makedirs(ASSETS_DIR, exist_ok=True)

WIDTH = 400
HEIGHT = 240
BG_COLOR = (24, 25, 29, 255)  # Discord dark theme match


def get_font(size: int = 14):
    for path in ["C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def draw_side_profile_revolver(d, gx, gy, hammer_cocked=False, cylinder_phase=0.0):
    # Base palette
    steel_body = (50, 55, 68)
    steel_dark = (26, 28, 34)
    steel_high = (150, 162, 188)
    wood_base = (105, 48, 22)
    wood_dark = (68, 30, 14)

    # 1. Grip (Anatomical Walnut with brass screw)
    grip_pts = [
        (gx - 46, gy - 6),
        (gx - 62, gy + 20),
        (gx - 74, gy + 52),
        (gx - 76, gy + 82),
        (gx - 60, gy + 92),
        (gx - 36, gy + 92),
        (gx - 30, gy + 74),
        (gx - 25, gy + 52),
        (gx - 18, gy + 32),
        (gx - 28, gy + 14),
        (gx - 38, gy + 6)
    ]
    d.polygon(grip_pts, fill=wood_base, outline=wood_dark, width=2)
    # Checkered grip panel
    inlay = [
        (gx - 56, gy + 26),
        (gx - 66, gy + 52),
        (gx - 68, gy + 75),
        (gx - 45, gy + 82),
        (gx - 36, gy + 65),
        (gx - 32, gy + 45)
    ]
    d.polygon(inlay, fill=wood_dark)
    # Brass Medallion
    d.ellipse([gx - 52, gy + 48, gx - 44, gy + 56], fill=(215, 175, 60), outline=(255, 230, 100), width=1)

    # 2. Steel Frame / Receiver
    frame_pts = [
        (gx - 52, gy - 20),
        (gx - 46, gy - 6),
        (gx - 38, gy + 14),
        (gx - 18, gy + 18),
        (gx + 38, gy + 18),
        (gx + 38, gy - 20)
    ]
    d.polygon(frame_pts, fill=steel_body, outline=steel_dark, width=2)
    d.line([gx - 52, gy - 20, gx + 38, gy - 20], fill=steel_high, width=2) # Top strap bevel

    # 3. Trigger Guard & Trigger
    d.arc([gx - 22, gy + 14, gx + 16, gy + 52], start=0, end=180, fill=(75, 84, 102), width=3)
    d.line([gx - 4, gy + 18, gx, gy + 34], fill=(210, 215, 225), width=2) # Curved trigger

    # 4. Cylinder Window & Fluted Cylinder
    d.rectangle([gx - 18, gy - 16, gx + 32, gy + 14], fill=steel_dark)
    cl, ct, cr, cb = gx - 16, gy - 15, gx + 30, gy + 13
    d.rounded_rectangle([cl, ct, cr, cb], radius=3, fill=(42, 46, 56), outline=(105, 118, 138), width=1)

    # Moving Flutes
    flute_step = 10.0
    for i in range(-1, 5):
        fy = ct + 4 + ((i * flute_step + cylinder_phase) % 26)
        if ct + 2 <= fy <= cb - 2:
            d.line([cl + 3, fy, cr - 3, fy], fill=(16, 18, 22), width=3)
            d.line([cl + 3, fy - 1, cr - 3, fy - 1], fill=(85, 95, 114), width=1)

    # 5. Bull Barrel & Full Lug
    bl, br = gx + 38, gx + 140
    d.rectangle([bl, gy - 20, br, gy - 3], fill=steel_body, outline=steel_dark, width=2)
    d.line([bl, gy - 20, br, gy - 20], fill=steel_high, width=2) # Top rib highlight
    # Underlug & Ejector Rod
    d.rectangle([bl, gy - 3, br - 12, gy + 10], fill=(36, 40, 50), outline=(68, 76, 92), width=1)
    d.line([bl + 8, gy + 4, bl + 45, gy + 4], fill=(180, 188, 202), width=2)
    # Front sight blade
    d.polygon([(br - 16, gy - 20), (br - 4, gy - 32), (br - 2, gy - 20)], fill=(32, 36, 44), outline=steel_dark)
    d.line([(br - 12, gy - 23), (br - 5, gy - 30)], fill=(255, 60, 40), width=2) # Red ramp

    # 6. Hammer
    if hammer_cocked:
        d.polygon([(gx - 44, gy - 18), (gx - 60, gy - 34), (gx - 50, gy - 38), (gx - 38, gy - 24)], fill=(140, 150, 168), outline=steel_dark)
        d.line([(gx - 58, gy - 35), (gx - 52, gy - 39)], fill=(240, 245, 255), width=2)
    else:
        d.polygon([(gx - 42, gy - 18), (gx - 54, gy - 28), (gx - 46, gy - 30), (gx - 38, gy - 20)], fill=(110, 120, 135), outline=steel_dark)


def draw_hud_header(d, font, status_text: str, status_color: tuple, pulse_mode: str = "normal", frame_idx: int = 0):
    w = WIDTH
    # Dark header strip
    d.rectangle([0, 0, w, 32], fill=(14, 15, 18))
    d.line([0, 32, w, 32], fill=(45, 48, 58), width=1)

    # Draw animated ECG line on the right side
    ecg_start_x = 220
    ecg_y = 16
    if pulse_mode == "flatline":
        # Solid flatline
        d.line([ecg_start_x, ecg_y, w - 15, ecg_y], fill=(255, 50, 60), width=2)
    elif pulse_mode == "rapid":
        # Rapid tension pulse spikes
        shift = (frame_idx * 14) % 60
        pts = [
            (ecg_start_x, ecg_y),
            (ecg_start_x + 20, ecg_y),
            (ecg_start_x + 28, ecg_y - 12),
            (ecg_start_x + 36, ecg_y + 12),
            (ecg_start_x + 44, ecg_y - 6),
            (ecg_start_x + 52, ecg_y),
            (ecg_start_x + 80, ecg_y),
            (ecg_start_x + 88, ecg_y - 12),
            (ecg_start_x + 96, ecg_y + 12),
            (ecg_start_x + 104, ecg_y - 6),
            (ecg_start_x + 112, ecg_y),
            (w - 15, ecg_y)
        ]
        d.line(pts, fill=(255, 190, 50), width=2)
    else:
        # Calm normal heartbeat
        pts = [
            (ecg_start_x, ecg_y),
            (ecg_start_x + 45, ecg_y),
            (ecg_start_x + 55, ecg_y - 10),
            (ecg_start_x + 65, ecg_y + 10),
            (ecg_start_x + 75, ecg_y - 4),
            (ecg_start_x + 85, ecg_y),
            (w - 15, ecg_y)
        ]
        d.line(pts, fill=(60, 220, 130), width=2)

    # Status text
    d.text((15, 8), status_text, font=font, fill=status_color)


def generate_spin_gif(output_path: str):
    font = get_font(13)
    frames = []
    num_frames = 12

    for f in range(num_frames):
        im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
        d = ImageDraw.Draw(im)

        # Background tactical grid
        for xg in range(0, WIDTH, 35):
            d.line([xg, 32, xg, HEIGHT - 46], fill=(28, 30, 36), width=1)
        for yg in range(32, HEIGHT - 46, 35):
            d.line([0, yg, WIDTH, yg], fill=(28, 30, 36), width=1)

        # Draw HUD header
        draw_hud_header(d, font, "PULSE: 165 BPM [SUSPENSE]", (255, 200, 60), pulse_mode="rapid", frame_idx=f)

        # Subtle breathing motion
        breathe_y = int(math.sin(f * (2 * math.pi / num_frames)) * 2)
        gx, gy = 150, 122 + breathe_y

        # Revolver Layer
        gun_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gun_layer)
        # Fast cylinder phase
        draw_side_profile_revolver(gd, gx, gy, hammer_cocked=True, cylinder_phase=f * 6.5)
        im.alpha_composite(gun_layer)

        # Radar scanner line sweeping across revolver
        sweep_x = int(30 + ((f * 35) % (WIDTH - 60)))
        d.line([sweep_x, 40, sweep_x, HEIGHT - 55], fill=(255, 215, 80, 90), width=2)

        # Radial speed sparks around cylinder
        for s in range(4):
            sa = (f * 45 + s * 90) * math.pi / 180
            cx, cy = gx + 8, gy - 2
            x1 = cx + int(24 * math.cos(sa))
            y1 = cy + int(24 * math.sin(sa))
            x2 = cx + int(36 * math.cos(sa))
            y2 = cy + int(36 * math.sin(sa))
            d.line([x1, y1, x2, y2], fill=(255, 230, 110, 180), width=2)

        # Bottom banner
        d.rounded_rectangle([WIDTH // 2 - 130, HEIGHT - 44, WIDTH // 2 + 130, HEIGHT - 16], radius=6, fill=(35, 34, 40), outline=(210, 175, 70), width=2)
        d.text((WIDTH // 2, HEIGHT - 30), "CYLINDER SPINNING...", font=font, fill=(255, 215, 80), anchor="mm")

        frames.append(im.convert("RGB"))

    frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=100, loop=0)


def generate_boom_gif(output_path: str):
    font = get_font(13)
    frames = []
    num_frames = 14

    for f in range(num_frames):
        im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
        d = ImageDraw.Draw(im)

        # Background grid
        for xg in range(0, WIDTH, 35):
            d.line([xg, 32, xg, HEIGHT - 46], fill=(28, 30, 36), width=1)
        for yg in range(32, HEIGHT - 46, 35):
            d.line([0, yg, WIDTH, yg], fill=(28, 30, 36), width=1)

        # Header status (rapid before shot, flatline after)
        if f == 0:
            draw_hud_header(d, font, "PULSE: 175 BPM [TRIGGER]", (255, 180, 50), pulse_mode="rapid", frame_idx=f)
        else:
            draw_hud_header(d, font, "PULSE: 0 BPM [FLATLINE]", (255, 70, 80), pulse_mode="flatline")

        # Recoil angles and camera shake
        angle = 0.0
        shake_x, shake_y = 0, 0
        if f == 1:
            angle = 18.0
            shake_x, shake_y = random.randint(-5, 5), random.randint(-4, 4)
        elif f == 2:
            angle = 24.0
            shake_x, shake_y = random.randint(-3, 3), random.randint(-3, 3)
        elif 3 <= f <= 6:
            angle = max(0.0, 24.0 - (f - 2) * 5.5)
        else:
            angle = 0.0

        gx, gy = 145 + shake_x, 125 + shake_y
        pivot = (gx - 50, gy + 75)

        # Draw gun on layer and rotate
        gun_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gun_layer)
        draw_side_profile_revolver(gd, gx, gy, hammer_cocked=(f == 0), cylinder_phase=0.0)
        rotated_gun = gun_layer.rotate(angle, resample=Image.BICUBIC, center=pivot)
        im.alpha_composite(rotated_gun)

        # Rotated muzzle coordinates
        rad = math.radians(-angle)
        px, py = pivot
        mx, my = gx + 140, gy - 12
        rot_mx = px + math.cos(rad) * (mx - px) - math.sin(rad) * (my - py)
        rot_my = py + math.sin(rad) * (mx - px) + math.cos(rad) * (my - py)

        # Muzzle blast flash (frames 1 to 3)
        if 1 <= f <= 3:
            fd = ImageDraw.Draw(im)
            scale = 1.0 if f == 1 else (0.75 if f == 2 else 0.45)
            fr = int(70 * scale)
            # Red shockwave ring
            fd.ellipse([rot_mx - fr * 0.4, rot_my - fr * 0.7, rot_mx + fr * 1.8, rot_my + fr * 0.7], fill=(255, 45, 30, 180))
            # Orange fireball
            fd.ellipse([rot_mx - fr * 0.2, rot_my - fr * 0.5, rot_mx + fr * 1.4, rot_my + fr * 0.5], fill=(255, 130, 20))
            # Yellow core
            fd.ellipse([rot_mx, rot_my - fr * 0.35, rot_mx + fr * 1.0, rot_my + fr * 0.35], fill=(255, 235, 60))
            # White hot center
            fd.ellipse([rot_mx + 4, rot_my - fr * 0.2, rot_mx + fr * 0.6, rot_my + fr * 0.2], fill=(255, 255, 255))
            # Directional spikes
            for a in [-35, -20, -5, 10, 25, 40]:
                sa = math.radians(a - angle)
                fd.line([rot_mx + 8, rot_my, rot_mx + int((fr * 1.9) * math.cos(sa)), rot_my + int((fr * 1.9) * math.sin(sa))], fill=(255, 245, 150), width=3)

        # Volumetric smoke clouds and flying sparks
        if 2 <= f <= 11:
            step = f - 2
            sd = ImageDraw.Draw(im)
            # Smoke clouds
            for p in range(7):
                pa = (p * 0.38) - 0.45 - math.radians(angle)
                pdist = 24 + step * 13 + (p % 3) * 6
                sx = rot_mx + int(pdist * math.cos(pa))
                sy = rot_my + int(pdist * math.sin(pa)) - (step * 4)
                sr = 14 + step * 3
                smoke_col = (95 - step * 5, 90 - step * 5, 100 - step * 5)
                sd.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=smoke_col)

            # Flying spark particles
            for sp in range(12):
                spa = math.radians(-angle + (sp * 20 - 45))
                sp_dist = 40 + step * 16 + (sp % 4) * 8
                sp_x = rot_mx + int(sp_dist * math.cos(spa))
                sp_y = rot_my + int(sp_dist * math.sin(spa)) + (step * 2)
                sd.ellipse([sp_x - 2, sp_y - 2, sp_x + 2, sp_y + 2], fill=(255, 220, 80))

        # Bottom banner with impact styling
        border_col = (255, 60, 50) if f % 2 == 0 else (200, 30, 30)
        d.rounded_rectangle([WIDTH // 2 - 130, HEIGHT - 44, WIDTH // 2 + 130, HEIGHT - 16], radius=6, fill=(45, 18, 20), outline=border_col, width=2)
        d.text((WIDTH // 2, HEIGHT - 30), "BANG! ELIMINATED", font=font, fill=(255, 90, 80), anchor="mm")

        frames.append(im.convert("RGB"))

    frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=95, loop=0)


def generate_safe_gif(output_path: str):
    font = get_font(13)
    frames = []
    num_frames = 12

    for f in range(num_frames):
        im = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR)
        d = ImageDraw.Draw(im)

        # Tactical background grid
        for xg in range(0, WIDTH, 35):
            d.line([xg, 32, xg, HEIGHT - 46], fill=(28, 30, 36), width=1)
        for yg in range(32, HEIGHT - 46, 35):
            d.line([0, yg, WIDTH, yg], fill=(28, 30, 36), width=1)

        # Header status (calming heartbeat)
        draw_hud_header(d, font, "PULSE: 72 BPM [SURVIVED]", (60, 225, 130), pulse_mode="normal", frame_idx=f)

        # Hammer strike impact dip
        dip_angle = 0.0
        if f == 1:
            dip_angle = -2.0  # slight downward mechanical shock
        elif f == 2:
            dip_angle = 1.0

        gx, gy = 150, 122
        pivot = (gx - 50, gy + 75)

        # Draw gun
        gun_layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gun_layer)
        # Hammer snaps uncocked on frame 1
        draw_side_profile_revolver(gd, gx, gy, hammer_cocked=(f == 0), cylinder_phase=0.0)
        rotated_gun = gun_layer.rotate(dip_angle, resample=Image.BICUBIC, center=pivot)
        im.alpha_composite(rotated_gun)

        # Hammer spark & tiny puff (frames 1 to 4)
        if 1 <= f <= 4:
            hx, hy = gx - 42, gy - 24
            for s in range(5):
                sa = s * (math.pi / 2.5)
                d.line([hx, hy, hx + int(10 * math.cos(sa)), hy + int(10 * math.sin(sa))], fill=(190, 245, 255), width=2)
        elif 5 <= f <= 8:
            step = f - 4
            hx, hy = gx - 42, gy - 24 - (step * 3)
            d.ellipse([hx - 4 - step, hy - 3, hx + 4 + step, hy + 3], fill=(120, 150, 160))

        # Neon green target lock reticle pulsing around cylinder
        if 2 <= f <= 10:
            pulse_step = f - 2
            cx, cy = gx + 8, gy - 2
            reticle_r = 28 + (pulse_step * 3)
            alpha_col = (50, 220, 130)
            d.ellipse([cx - reticle_r, cy - reticle_r, cx + reticle_r, cy + reticle_r], outline=alpha_col, width=2)
            # Corner reticle markers
            cr = reticle_r + 6
            d.line([cx - cr, cy, cx - cr + 8, cy], fill=alpha_col, width=2)
            d.line([cx + cr - 8, cy, cx + cr, cy], fill=alpha_col, width=2)
            d.line([cx, cy - cr, cx, cy - cr + 8], fill=alpha_col, width=2)
            d.line([cx, cy + cr - 8, cx, cy + cr], fill=alpha_col, width=2)

        # Bottom banner
        d.rounded_rectangle([WIDTH // 2 - 130, HEIGHT - 44, WIDTH // 2 + 130, HEIGHT - 16], radius=6, fill=(18, 40, 26), outline=(50, 205, 120), width=2)
        d.text((WIDTH // 2, HEIGHT - 30), "CLICK! SURVIVED", font=font, fill=(75, 235, 145), anchor="mm")

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
