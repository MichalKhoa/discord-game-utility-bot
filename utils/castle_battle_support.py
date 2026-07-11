def time_to_reinforce(opponent_march_time: int, gap_between_rallies: int, user_march_time: int) -> str:
    march_difference = user_march_time - opponent_march_time

    if march_difference >= 0:
        # User march is longer; must send before opponent sets off
        t_max = march_difference
        t_min = march_difference - gap_between_rallies
        
        if t_min >= 0:
            return (f"You should send garrison when the first to hit rally has between "
                    f"{t_max // 60}:{t_max % 60:02d} and {t_min // 60}:{t_min % 60:02d} "
                    f"left to set off, so you can reinforce between the hits.")
        else:
            t_min_after = abs(t_min)
            return (f"You should send garrison when the first to hit rally has between "
                    f"{t_max // 60}:{t_max % 60:02d} left to set off and "
                    f"{t_min_after // 60}:{t_min_after % 60:02d} after setting off, "
                    f"so you can reinforce between the hits.")
    else:
        # User march is shorter; must send after opponent sets off
        t_max_rem = user_march_time
        t_min_rem = user_march_time - gap_between_rallies
        
        if t_min_rem >= 0:
            return (f"You should send garrison when the first to hit rally has already set off and will hit in "
                    f"{t_max_rem // 60}:{t_max_rem % 60:02d} to {t_min_rem // 60}:{t_min_rem % 60:02d}, "
                    f"so you can reinforce between the hits.")
        else:
            t_min_after = abs(t_min_rem)
            return (f"You should send garrison when the first to hit rally has already set off and will hit in "
                    f"{t_max_rem // 60}:{t_max_rem % 60:02d} to {t_min_after // 60}:{t_min_after % 60:02d} after hitting, "
                    f"so you can reinforce between the hits.")