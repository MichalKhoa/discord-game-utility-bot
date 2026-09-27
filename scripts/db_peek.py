import glob
import os
import sqlite3
import sys

def peek(pattern="data/*.db"):
    files = glob.glob(pattern)
    if not files:
        print(f"No databases found matching pattern: {pattern}")
        return
    for path in sorted(files):
        name = os.path.basename(path)
        print(f"\n[{name}]")
        try:
            con = sqlite3.connect(path)
            cur = con.cursor()
            tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';").fetchall()
            if not tables:
                print("  (no user tables)")
            for (t,) in tables:
                count = cur.execute(f"SELECT COUNT(*) FROM \"{t}\";").fetchone()[0]
                cols = [c[1] for c in cur.execute(f"PRAGMA table_info(\"{t}\");").fetchall()]
                print(f"  {t} ({count} rows) -> [{', '.join(cols)}]")
            con.close()
        except Exception as e:
            print(f"  Error reading {name}: {e}")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/*.db"
    peek(target)
