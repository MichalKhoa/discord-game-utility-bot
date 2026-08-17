import discord
from typing import Dict, Any


def format_time(seconds: int) -> str:
    """Formats seconds into MM:SS format."""
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"


def calculate_reinforcement_window(opponent_march_time: int, gap_between_rallies: int, user_march_time: int) -> Dict[str, Any]:
    """
    Calculates the exact time window for sending garrison reinforcement
    between two consecutive incoming enemy rallies.
    """
    march_diff = user_march_time - opponent_march_time

    if march_diff >= 0:
        # User march is longer/equal; must launch before or at Rally 1 departure
        t_before_max = march_diff
        t_before_min = march_diff - gap_between_rallies
        
        if t_before_min >= 0:
            action = (
                f"Send garrison when Rally 1 has between **{format_time(t_before_max)}** "
                f"and **{format_time(t_before_min)}** left before setting off."
            )
            timing_detail = f"Launch {format_time(t_before_min)} to {format_time(t_before_max)} before Rally 1 departs."
        else:
            t_after = abs(t_before_min)
            action = (
                f"Send garrison between **{format_time(t_before_max)}** before Rally 1 sets off "
                f"and **{format_time(t_after)}** after it has set off."
            )
            timing_detail = f"Launch {format_time(t_before_max)} before departure up to {format_time(t_after)} after departure."
    else:
        # User march is shorter; must launch after Rally 1 departs
        t_launch_start = abs(march_diff)
        t_launch_end = abs(march_diff) + gap_between_rallies
        
        rem_hit_start = user_march_time
        rem_hit_end = user_march_time - gap_between_rallies
        
        if rem_hit_end >= 0:
            action = (
                f"Send garrison after Rally 1 sets off, when it has between "
                f"**{format_time(rem_hit_start)}** and **{format_time(rem_hit_end)}** remaining before hit."
            )
            timing_detail = f"Launch {format_time(t_launch_start)} to {format_time(t_launch_end)} after Rally 1 departs."
        else:
            t_after_hit = abs(rem_hit_end)
            action = (
                f"Send garrison when Rally 1 is **{format_time(rem_hit_start)}** before hit "
                f"up to **{format_time(t_after_hit)}** after hit."
            )
            timing_detail = f"Launch {format_time(t_launch_start)} to {format_time(t_launch_end)} after departure."

    return {
        "action": action,
        "timing_detail": timing_detail,
        "march_diff": march_diff,
        "opponent_march": opponent_march_time,
        "gap": gap_between_rallies,
        "user_march": user_march_time,
    }


def time_to_reinforce(opponent_march_time: int, gap_between_rallies: int, user_march_time: int) -> str:
    """Legacy string output helper."""
    calc = calculate_reinforcement_window(opponent_march_time, gap_between_rallies, user_march_time)
    return calc["action"]


def create_reinforcement_embed(opponent_march_time: int, gap_between_rallies: int, user_march_time: int) -> discord.Embed:
    """Creates a formatted tactical embed for castle reinforcement timing."""
    calc = calculate_reinforcement_window(opponent_march_time, gap_between_rallies, user_march_time)
    
    embed = discord.Embed(
        title="🏰 Castle Defense: Reinforcement Timing",
        description=calc["action"],
        colour=discord.Colour.gold()
    )
    
    embed.add_field(
        name="⏱️ Inputs",
        value=(
            f"• Enemy March Time: `{format_time(opponent_march_time)}` ({opponent_march_time}s)\n"
            f"• Gap Between Hits: `{format_time(gap_between_rallies)}` ({gap_between_rallies}s)\n"
            f"• Your March Time: `{format_time(user_march_time)}` ({user_march_time}s)"
        ),
        inline=False
    )
    
    timeline = (
        f"```text\n"
        f" [Rally 1 Departs] ──▶ [Rally 1 Hits @ {format_time(opponent_march_time)}]\n"
        f"                             ▲\n"
        f"                             │ (Garrison arrives here!)\n"
        f"                             ▼\n"
        f" [Rally 2 Departs] ──▶ [Rally 2 Hits @ {format_time(opponent_march_time + gap_between_rallies)}]\n"
        f"```"
    )
    embed.add_field(name="📍 Arrival Target Window", value=timeline, inline=False)
    embed.add_field(name="🎯 Tactical Instruction", value=f"> {calc['timing_detail']}", inline=False)
    embed.set_footer(text="Garrison will land cleanly between Rally 1 and Rally 2.")
    return embed