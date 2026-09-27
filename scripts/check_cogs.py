import ast
import glob
import os
import sys

def check():
    cog_files = sorted(glob.glob("cogs/*.py"))
    if not cog_files:
        print("No cogs found in cogs/")
        return 0

    errors = 0
    checked = 0
    for path in cog_files:
        name = os.path.basename(path)
        if name.startswith("__"):
            continue
        checked += 1
        try:
            with open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=name)
            has_setup = any(
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "setup"
                for n in tree.body
            )
            if not has_setup:
                print(f"FAIL {name}: missing setup(bot) entry point")
                errors += 1
        except SyntaxError as e:
            print(f"SYNTAX ERROR {name}:{e.lineno}: {e.msg}")
            errors += 1

    if errors == 0:
        print(f"ALL COGS PASS: {checked} cogs verified with valid syntax and setup().")
        return 0
    else:
        print(f"COG CHECK FAILED: {errors} error(s) found.")
        return 1

if __name__ == "__main__":
    sys.exit(check())
