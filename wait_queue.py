"""Block until queue.jsonl has entries beyond processed.txt's count; then print them and exit."""
import json, os, sys, time
POLL = float(os.environ.get("POLL", 60))  # seconds between checks
HERE = os.path.dirname(os.path.abspath(__file__))
q, p = os.path.join(HERE, "queue.jsonl"), os.path.join(HERE, "processed.txt")
while True:
    done = int(open(p).read().strip() or 0) if os.path.exists(p) else 0
    lines = open(q).read().splitlines() if os.path.exists(q) else []
    if len(lines) > done:
        lines = open(q).read().splitlines()
        for l in lines[done:]:
            print(l)
        sys.exit(0)
    time.sleep(POLL)
