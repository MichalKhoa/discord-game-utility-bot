import re
import discord
from typing import List, Set, Optional

WATCHED_CHANNELS: Set[int] = {
    1374889273077272636,
    1374888983812902993,
    1374888701204758599,
}

# Known non-code keywords to reject
IGNORED_WORDS: Set[str] = {
    "DISCORD", "UPDATE", "KINGDOM", "ANNOUNCEMENT", "WHITEOUT", "SURVIVAL",
    "CHANNEL", "TWITTER", "FACEBOOK", "YOUTUBE", "REDDIT", "INSTAGRAM",
    "CENTURY", "KINGSHOT", "OFFICIAL", "MAINTENANCE", "REWARDS", "VERSION",
    "PLEASE", "THANKS", "SERVER", "SYSTEM", "NOTICE", "EVENTS", "GOOGLE",
    "AVAILABLE", "VALID", "UNTIL", "REDEEM", "CLAIM", "EXPIRE", "EXPIRED",
    "NEWEST", "LATEST", "ACTIVE", "FOLLOW", "COMMUNITY", "SURVEY", "WINNER"
}

EXPLICIT_PATTERNS = [
    r"(?:gift\s*code|cdk|code|coupon)[^\w\n]*?(?:[:=\-–—>]|\bis\b|\bhere\b)[^\w\n]*?([A-Za-z0-9_]{5,30})",
    r"(?:gift\s*code|cdk|code|coupon)\s*:\s*[`\*\_]*([A-Za-z0-9_]{5,30})",
    r">>\s*([A-Za-z0-9_]{5,30})\s*<<",
    r"`([A-Za-z0-9_]{5,30})`",
]


def extract_candidate_codes(text: str) -> List[str]:
    """
    Extracts potential gift codes from announcement text.
    Deduplicates and filters out common announcement keywords and URLs.
    """
    if not text:
        return []

    # Strip URLs to avoid parsing URL components as codes
    clean_text = re.sub(r'https?://\S+', '', text)
    found_codes: List[str] = []

    # 1. Search for explicit matches (e.g. "Gift Code: XYZ123" or `XYZ123`)
    for pattern in EXPLICIT_PATTERNS:
        matches = re.findall(pattern, clean_text, flags=re.IGNORECASE)
        for m in matches:
            code = m.strip().strip("`*_").upper()
            if len(code) >= 5 and code not in IGNORED_WORDS and code not in found_codes:
                found_codes.append(code)

    return found_codes


def extract_validity_info(text: str) -> Optional[str]:
    """Extracts expiration or validity date/time string from announcement text if present."""
    if not text:
        return None
    pattern = r"(?:valid\s*until|valid\s*thru|valid\s*through|expires\s*at|expires|expiration\s*date|expiration|deadline)[^\w\n]*?(?:[:=\-–—>]|\bis\b)[^\w\n]*?([^\n\r]+)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        val = match.group(1).strip().strip("`*_").strip()
        if val and len(val) <= 80:
            return val
    return None


def create_detected_code_embed(code: str, message: discord.Message, validity: Optional[str] = None) -> discord.Embed:
    """Builds an alert embed when a new gift code is detected in announcement channels."""
    if validity is None and message:
        full_text = message.content or ""
        for emb in message.embeds:
            if emb.title:
                full_text += f"\n{emb.title}"
            if emb.description:
                full_text += f"\n{emb.description}"
            for f in emb.fields:
                full_text += f"\n{f.name} {f.value}"
        validity = extract_validity_info(full_text)

    embed = discord.Embed(
        title="🎁 New Official Gift Code Detected!",
        description=f"**Code**: `{code}`\n\nDetected in announcement channel <#{message.channel.id}>.",
        colour=discord.Colour.green()
    )
    if message.author:
        embed.set_author(name=f"Source: {message.author.display_name}", icon_url=message.author.display_avatar.url)

    if validity:
        embed.add_field(name="📅 Valid Until", value=f"**{validity}**", inline=False)

    snippet = message.content[:200] + ("..." if len(message.content) > 200 else "")
    if snippet:
        embed.add_field(name="📢 Announcement Snippet", value=f"> {snippet}", inline=False)

    embed.add_field(
        name="⚡ Quick Action",
        value="Click **Redeem for All Players** below to dispatch batch redemption immediately.",
        inline=False
    )
    embed.set_footer(text="Kingshot Gift Code Auto-Detector")
    return embed


class DetectedCodeView(discord.ui.View):
    """Interactive view allowing 1-click batch redemption for detected codes."""
    def __init__(self, code: str, bot: discord.Client):
        super().__init__(timeout=3600)  # Active for 1 hour
        self.code = code
        self.bot = bot

    @discord.ui.button(label="Redeem for All Players", style=discord.ButtonStyle.success, emoji="🎁")
    async def redeem_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions (must have Manage Guild or Administrator, or be bot owner)
        is_owner = await self.bot.is_owner(interaction.user)
        is_admin = interaction.user.guild_permissions.manage_guild if interaction.guild else False
        if not (is_owner or is_admin):
            await interaction.response.send_message(
                "❌ You must have `Manage Server` permissions to trigger batch redemption.",
                ephemeral=True
            )
            return

        # Disable button to prevent duplicate clicks
        button.disabled = True
        button.label = "Redeeming Started..."
        await interaction.response.edit_message(view=self)

        # Get CodeRedeem cog and dispatch redemption
        code_redeem_cog = self.bot.get_cog("CodeRedeem")
        if not code_redeem_cog:
            await interaction.followup.send("❌ Error: `CodeRedeem` cog is not currently loaded.", ephemeral=True)
            return

        await code_redeem_cog._execute_batch_redemption(interaction, [self.code])


async def process_announcement_message(message: discord.Message, bot: discord.Client, db) -> List[str]:
    """
    Checks incoming message against watched announcement channels,
    extracts unredeemed codes, and posts interactive 1-click redeem alert.
    """
    if message.channel.id not in WATCHED_CHANNELS:
        return []

    full_text = message.content or ""
    for emb in message.embeds:
        if emb.title:
            full_text += f"\n{emb.title}"
        if emb.description:
            full_text += f"\n{emb.description}"
        for f in emb.fields:
            full_text += f"\n{f.name} {f.value}"

    candidates = extract_candidate_codes(full_text)
    if not candidates:
        return []

    unredeemed_found = []
    for code in candidates:
        already_redeemed = await db.is_code_redeemed(code)
        if not already_redeemed:
            unredeemed_found.append(code)
            embed = create_detected_code_embed(code, message)
            view = DetectedCodeView(code, bot)
            try:
                await message.channel.send(embed=embed, view=view)
            except (discord.Forbidden, discord.HTTPException) as e:
                print(f"DEBUG: Failed to send detected code embed to channel {message.channel.id}: {e}")

    return unredeemed_found
