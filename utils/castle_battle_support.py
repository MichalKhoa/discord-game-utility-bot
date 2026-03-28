
def time_to_reinforce(opponent_march_time: int, gap_between_rallies: int, user_march_time:int):
    march_difference = user_march_time - opponent_march_time

    if march_difference >= 0:
        if (march_difference >= 60):
            minutes = int(march_difference / 60)
            seconds = march_difference % 60
            if (seconds < gap_between_rallies):
                return (f"You should send garrison when the first to hit rally has {minutes}:{seconds:02d} to "
                        f"{minutes - 1}:{(60 - gap_between_rallies + seconds):02d} left to set off, so you can reinforce between the hits.")

            return (f"You should send garrison when the first to hit rally has {minutes}:{seconds:02d} to "
                    f"{minutes}:{(seconds - gap_between_rallies):02d} left to set off, so you can reinforce between the hits.")
        else:
            return (f"You should send garrison when the first to hit rally has 0:{march_difference:02d} to "
                    f"0:{(march_difference - gap_between_rallies):02d} left to set off, so you can reinforce between the hits.")
    else:
        return (f"You should send garrisson when the rally has already set off "
                f"and will hit in {abs(march_difference)} to {abs(march_difference - gap_between_rallies)}s")

# print(time_to_reinforce(36, 2, 102))