import json
import os
import sys

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "wordle")
SUPPORTED_LENGTHS = [4, 5, 6, 7, 8]

# Archaic, historical, obsolete, or inappropriate words that must never be target answers
BANNED_ANSWER_WORDS = {
    "thee", "thou", "unto", "chad", "matt",
    "agora", "pupal", "wench", "slave", "lynch", "quoth", "shalt", "smote",
    "wight", "welch", "liege", "knave", "fibre",
    "whilst", "thereof",
}


def check():
    errors = 0
    stats = {}

    for length in SUPPORTED_LENGTHS:
        a_path = os.path.join(ASSETS_DIR, f"answers_{length}.json")
        g_path = os.path.join(ASSETS_DIR, f"guesses_{length}.json")

        if not os.path.exists(a_path):
            print(f"FAIL: Missing answers file: {a_path}")
            errors += 1
            continue

        if not os.path.exists(g_path):
            print(f"FAIL: Missing guesses file: {g_path}")
            errors += 1
            continue

        try:
            with open(a_path, "r", encoding="utf-8") as f:
                answers = json.load(f)
            with open(g_path, "r", encoding="utf-8") as f:
                guesses = json.load(f)
        except Exception as e:
            print(f"FAIL length {length}: JSON read error: {e}")
            errors += 1
            continue

        guesses_set = set(guesses)
        answers_set = set(answers)

        # 1. Non-empty
        if not answers:
            print(f"FAIL length {length}: answers list is empty.")
            errors += 1
        if not guesses:
            print(f"FAIL length {length}: guesses list is empty.")
            errors += 1

        # 2. Length, alpha, lowercase
        bad_answers = [w for w in answers if len(w) != length or not w.isalpha() or not w.islower()]
        if bad_answers:
            print(f"FAIL length {length}: {len(bad_answers)} invalid answer words (e.g. {bad_answers[:5]}).")
            errors += 1

        bad_guesses = [w for w in guesses if len(w) != length or not w.isalpha() or not w.islower()]
        if bad_guesses:
            print(f"FAIL length {length}: {len(bad_guesses)} invalid guess words (e.g. {bad_guesses[:5]}).")
            errors += 1

        # 3. Deduplication & Sorted
        if len(answers) != len(answers_set):
            print(f"FAIL length {length}: duplicate words found in answers.")
            errors += 1
        if answers != sorted(answers):
            print(f"FAIL length {length}: answers list is not sorted alphabetically.")
            errors += 1

        if len(guesses) != len(guesses_set):
            print(f"FAIL length {length}: duplicate words found in guesses.")
            errors += 1
        if guesses != sorted(guesses):
            print(f"FAIL length {length}: guesses list is not sorted alphabetically.")
            errors += 1

        # 4. Answers must be a subset of guesses
        missing_from_guesses = answers_set - guesses_set
        if missing_from_guesses:
            print(f"FAIL length {length}: {len(missing_from_guesses)} answers not in guesses list (e.g. {list(missing_from_guesses)[:5]}).")
            errors += 1

        # 5. Check against banned archaic / obsolete words
        found_banned = answers_set.intersection(BANNED_ANSWER_WORDS)
        if found_banned:
            print(f"FAIL length {length}: banned archaic/obsolete words in answers: {sorted(found_banned)}")
            errors += 1

        stats[length] = (len(answers), len(guesses))

    if errors == 0:
        counts_str = ", ".join(f"{l}: ans={a}/gss={g}" for l, (a, g) in stats.items())
        print(f"ALL WORD LISTS PASS: 5 lengths verified ({counts_str}).")
        return 0
    else:
        print(f"WORD LIST CHECK FAILED: {errors} error(s) found.")
        return 1


if __name__ == "__main__":
    sys.exit(check())
