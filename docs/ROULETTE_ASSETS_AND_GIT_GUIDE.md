# Russian Roulette Custom Animations & Git Guide

This guide covers:
1. How to procure, format, and add custom animation GIFs to Russian Roulette.
2. How the bot automatically detects and renders these assets.
3. How to stage, commit, and push your changes to GitHub.

---

## 1. Custom GIF Assets for Russian Roulette

The bot automatically checks for local `.gif` files in `assets/roulette/`. If the files exist, it embeds them during gameplay. If they do not exist, it falls back to the clean, code-driven ASCII/emoji animation.

### Required Filenames & Roles:

| Filename | When It Appears | Description / Visual Idea | Recommended Duration |
| :--- | :--- | :--- | :--- |
| `spin.gif` | **Suspense Frame** (1.2s) | Cylinder spinning / hammer cocking | 1.0 – 1.5 seconds (looping) |
| `boom.gif` | **Elimination** (`💥 BANG!`) | Muzzle flash, explosion, gunshot | 1.0 – 2.0 seconds (one-shot/loop) |
| `safe.gif` | **Empty Chamber** (`💨 *Click!*`) | Empty hammer click, puff of smoke | 1.0 – 1.5 seconds |

### Recommended File Specs:
- **Format**: `.gif`
- **Resolution**: 400x225 to 600x338 (16:9) or 400x400 (1:1 square).
- **File Size**: Under 2 MB per file for fast Discord rendering.

---

## 2. Where & How to Procure or Create GIFs

### Method A: Free Repositories (Quickest)
1. Visit [Giphy](https://giphy.com) or [Tenor](https://tenor.com).
2. Search keywords:
   - `revolver cylinder spin`
   - `revolver click` / `dry fire`
   - `pixel art gunshot` / `muzzle flash`
   - `wild west duel shoot`
3. Download the `.gif` and rename it to `spin.gif`, `boom.gif`, or `safe.gif`.
4. Place the file inside the project directory:
   ```
   assets/roulette/spin.gif
   assets/roulette/boom.gif
   assets/roulette/safe.gif
   ```

### Method B: Convert & Crop Any Video (EZGIF)
1. Find any gameplay clip or video on YouTube/Twitch.
2. Go to [ezgif.com/video-to-gif](https://ezgif.com/video-to-gif).
3. Upload clip, trim to 1–2 seconds, crop to focus on the revolver/shot.
4. Use **Optimize GIF** to compress under 2 MB.
5. Save as `assets/roulette/<name>.gif`.

### Method C: Free 2D Game Assets (Pixel Art)
- Check [Itch.io (Free Game Assets)](https://itch.io/game-assets/free/tag-pixel-art) or [OpenGameArt.org](https://opengameart.org) for animated revolver sprites.

---

## 3. How to Commit & Push to GitHub

Whenever you add new assets or make code changes, follow these terminal steps:

### Step 1: Check Modified & Untracked Files
```bash
git status
```

### Step 2: Run Unit Tests
Always ensure all tests pass before committing:
```bash
.venv/bin/python -m unittest discover tests
```

### Step 3: Stage the Files
Stage all new assets and code:
```bash
git add assets/roulette/ cogs/russian_roulette.py tests/test_all.py docs/
```
*(Or stage everything: `git add .`)*

### Step 4: Commit with Conventional Commits
Format your commit message clearly:
```bash
git commit -m "feat(roulette): add custom gif animations and suspense frame"
```

### Step 5: Push to Remote Repository
Push your commit to the `master` branch on GitHub:
```bash
git push origin master
```

---

## 4. Verification & Testing in Discord
1. Start the bot (`.venv/bin/python main.py`).
2. Type `/roulette` or click `🎮 Games` $\rightarrow$ `🎲 Russian Roulette` in the menu.
3. Click **`Pull Trigger`** or **`Spin & Fire`** — verify that:
   - The suspense stage displays `spin.gif` for 1.2s.
   - The final result displays `boom.gif` or `safe.gif`.

