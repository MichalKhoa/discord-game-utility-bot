import os
import io
from typing import List, Dict, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont


# Visual Palette (matching Discord dark theme & Co-ordle reference)
COLOR_BG = (43, 45, 49, 255)         # Discord dark background #2B2D31
COLOR_TEXT_WHITE = (242, 243, 245)   # #F2F3F5
COLOR_TEXT_MUTED = (160, 165, 174)   # #A0A5AE
COLOR_TEXT_DARK = (30, 31, 34)       # #1E1F22

# Tile colors
COLOR_TILE_GREEN = (78, 155, 88)     # #4E9B58 (Correct)
COLOR_TILE_YELLOW = (227, 168, 63)   # #E3A83F (Present)
COLOR_TILE_DARK = (58, 60, 69)       # #3A3C45 (Absent/Eliminated)
COLOR_TILE_EMPTY = (40, 42, 46)      # #282A2E (Empty slot)
COLOR_TILE_BORDER = (75, 78, 86)     # Outline for empty slots

# Keyboard colors
COLOR_KB_BG = (35, 36, 40)           # #232428 (Container)
COLOR_KEY_WHITE = (242, 243, 245)    # White key
COLOR_KEY_DARK = (48, 50, 56)        # Eliminated key
COLOR_KEY_TEXT_MUTED = (110, 115, 125)

# Badge colors
COLOR_BADGE_BG = (88, 101, 242, 50)  # Blurple 20%
COLOR_BADGE_TEXT = (201, 205, 251)   # Light blurple


def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Finds system font across Windows and Linux, falling back to default."""
    candidates = []
    windir = os.environ.get("WINDIR", "C:\\Windows")
    if bold:
        candidates.extend([
            os.path.join(windir, "Fonts", "segoeuib.ttf"),
            os.path.join(windir, "Fonts", "arialbd.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ])
    else:
        candidates.extend([
            os.path.join(windir, "Fonts", "segoeui.ttf"),
            os.path.join(windir, "Fonts", "arial.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ])

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def render_coordle_board(
    guesses: List[Tuple[str, List[str], str, int, Optional[List[str]]]],
    letter_status: Dict[str, str],
    word_length: int = 5,
    max_attempts: int = 6,
) -> io.BytesIO:
    """
    Renders the Co-ordle game board and keyboard into a PNG in-memory bytes buffer.
    """
    tile_size = 38
    tile_gap = 5
    tile_radius = 5

    # Layout measurements
    padding = 16
    row_height = tile_size + 8
    num_display_rows = max(len(guesses), 1)

    board_width = padding * 2 + word_length * (tile_size + tile_gap) + 260
    board_width = max(board_width, 480)

    # Keyboard measurements
    kb_key_w = 30
    kb_key_h = 36
    kb_gap = 4
    kb_padding = 8
    kb_width = 10 * kb_key_w + 9 * kb_gap + kb_padding * 2
    kb_height = 3 * kb_key_h + 2 * kb_gap + kb_padding * 2

    board_width = max(board_width, kb_width + padding * 2)

    board_height = (
        padding +
        num_display_rows * row_height +
        16 +
        kb_height +
        padding
    )

    img = Image.new("RGBA", (board_width, board_height), COLOR_BG)
    draw = ImageDraw.Draw(img)

    font_tile = get_font(20, bold=True)
    font_num = get_font(16, bold=True)
    font_badge = get_font(15, bold=False)
    font_pts = get_font(16, bold=True)
    font_kb = get_font(16, bold=True)

    y_cursor = padding

    # 1. Render Guess Rows
    if not guesses:
        # Initial empty row showing word slots
        x_cursor = padding
        draw.text((x_cursor, y_cursor + 9), "1.", fill=COLOR_TEXT_MUTED, font=font_num)
        x_cursor += 30

        for _ in range(word_length):
            box = [x_cursor, y_cursor, x_cursor + tile_size, y_cursor + tile_size]
            draw.rounded_rectangle(box, radius=tile_radius, fill=COLOR_TILE_EMPTY, outline=COLOR_TILE_BORDER, width=2)
            x_cursor += tile_size + tile_gap

        y_cursor += row_height
    else:
        for i, entry in enumerate(guesses, 1):
            word = entry[0]
            pattern = entry[1]
            author = entry[2]
            pts = entry[3]
            discoveries = entry[4] if len(entry) > 4 and entry[4] else []
            is_solved = any("Solved" in d for d in discoveries)

            x_cursor = padding

            # Row number (e.g. "1.")
            num_text = f"{i}."
            draw.text((x_cursor, y_cursor + 9), num_text, fill=COLOR_TEXT_MUTED, font=font_num)
            x_cursor += 30

            # Letter tiles
            for ch, status in zip(word, pattern):
                if status == "G":
                    bg = COLOR_TILE_GREEN
                elif status == "Y":
                    bg = COLOR_TILE_YELLOW
                else:
                    bg = COLOR_TILE_DARK

                # Draw rounded tile
                box = [x_cursor, y_cursor, x_cursor + tile_size, y_cursor + tile_size]
                draw.rounded_rectangle(box, radius=tile_radius, fill=bg)

                # Center letter
                bbox = font_tile.getbbox(ch)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                tx = x_cursor + (tile_size - text_w) / 2 - bbox[0]
                ty = y_cursor + (tile_size - text_h) / 2 - bbox[1]
                draw.text((tx, ty), ch, fill=COLOR_TEXT_WHITE, font=font_tile)

                x_cursor += tile_size + tile_gap

            # Author badge
            x_cursor += 8
            badge_text = f"@{author}"
            badge_bbox = font_badge.getbbox(badge_text)
            bw = badge_bbox[2] - badge_bbox[0] + 12
            bh = 24
            by = y_cursor + (tile_size - bh) / 2
            draw.rounded_rectangle([x_cursor, by, x_cursor + bw, by + bh], radius=4, fill=COLOR_BADGE_BG)
            draw.text((x_cursor + 6, by + 3), badge_text, fill=COLOR_BADGE_TEXT, font=font_badge)
            x_cursor += bw + 10

            # Points
            pts_text = f"+{pts}" if pts > 0 else "+0"
            pts_color = COLOR_TEXT_WHITE if pts > 0 else COLOR_TEXT_MUTED
            draw.text((x_cursor, y_cursor + 9), pts_text, fill=pts_color, font=font_pts)

            y_cursor += row_height

    y_cursor += 12

    # 2. Render Keyboard
    kb_x = padding
    kb_box = [kb_x, y_cursor, kb_x + kb_width, y_cursor + kb_height]
    draw.rounded_rectangle(kb_box, radius=8, fill=COLOR_KB_BG)

    qwerty_rows = [
        "Q W E R T Y U I O P".split(),
        "A S D F G H J K L".split(),
        "Z X C V B N M".split()
    ]

    kb_y = y_cursor + kb_padding

    for r_idx, row in enumerate(qwerty_rows):
        row_w = len(row) * kb_key_w + (len(row) - 1) * kb_gap
        # Center row horizontally inside keyboard container
        row_x = kb_x + (kb_width - row_w) / 2

        for ch in row:
            st = letter_status.get(ch)
            if st == "G":
                key_bg = COLOR_TILE_GREEN
                key_fg = COLOR_TEXT_WHITE
            elif st == "Y":
                key_bg = COLOR_TILE_YELLOW
                key_fg = COLOR_TEXT_WHITE
            elif st == "B":
                key_bg = COLOR_KEY_DARK
                key_fg = COLOR_KEY_TEXT_MUTED
            else:
                key_bg = COLOR_KEY_WHITE
                key_fg = COLOR_TEXT_DARK

            kbox = [row_x, kb_y, row_x + kb_key_w, kb_y + kb_key_h]
            draw.rounded_rectangle(kbox, radius=4, fill=key_bg)

            kbbox = font_kb.getbbox(ch)
            kw = kbbox[2] - kbbox[0]
            kh = kbbox[3] - kbbox[1]
            kx = row_x + (kb_key_w - kw) / 2 - kbbox[0]
            ky = kb_y + (kb_key_h - kh) / 2 - kbbox[1]
            draw.text((kx, ky), ch, fill=key_fg, font=font_kb)

            row_x += kb_key_w + kb_gap

        kb_y += kb_key_h + kb_gap

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
