import subprocess
import sys

def run():
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short", "-o", "pythonpath=."]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        summary = [line for line in lines if "passed" in line or "failed" in line]
        print(f"GATE PASS: {summary[-1] if summary else 'OK'}")
    else:
        print("GATE FAIL:")
        print(res.stdout[-1500:] if len(res.stdout) > 1500 else res.stdout)
        if res.stderr:
            print(res.stderr[-500:])
    sys.exit(res.returncode)

if __name__ == "__main__":
    run()
