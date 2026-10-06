"""Block until the page has sent decisions Claude has not handled yet; print them and exit.

    REVIEW_CARDS_DATA=/path/to/paper/.review-cards POLL=60 python3 wait_queue.py

Run it in the background: its exit is what wakes Claude. It checks every POLL
seconds (default 60), so decisions sent within the same minute arrive together.
"""
import os
import sys
import time

DATA = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("REVIEW_CARDS_DATA", ".review-cards"))
POLL = float(os.environ.get("POLL", 60))
q, p = os.path.join(DATA, "queue.jsonl"), os.path.join(DATA, "processed.txt")
while True:
    done = int(open(p).read().strip() or 0) if os.path.exists(p) else 0
    lines = open(q).read().splitlines() if os.path.exists(q) else []
    if len(lines) > done:
        for l in lines[done:]:
            print(l)
        sys.exit(0)
    time.sleep(POLL)
