"""Review-cards server: one card per comment thread of a LaTeX paper.

    python3 server.py --tex main.tex [--data .review-cards] [--port 8765]

GET  /                -> index.html
GET  /api/items       -> the cards: the paper's comment threads (scanned from the
                         .tex on every request) merged with Claude's proposed
                         changes and replies (proposals.json) and their status
GET  /api/meta        -> the comment macros found in the preamble (label, colour)
GET  /api/state       -> {"version": n, "tex_mtime": t, ...}; the page polls it
GET  /api/queue       -> every decision sent so far, for the per-card conversation
POST /api/done        -> append a decision for Claude to queue.jsonl, mark the card pending
POST /api/skip        -> skip a card (no Claude involved); it comes back if its thread changes
POST /api/unskip      -> undo a skip

Statuses: pending (yellow, with Claude), review (red, Claude answered: check
again), done (green), skip (grey), reopened (skipped or kept, but the thread has
changed since). A thread whose comments are all commented out counts as done unless it
is pending or under review.
"""
import argparse
import json
import os
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

import scan

HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = None


def P(f):
    return os.path.join(ARGS.data, f)


def load(f, default):
    try:
        with open(P(f)) as fh:
            return json.load(fh)
    except Exception:
        return default


def dump(f, obj):
    tmp = P(f) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh)
    os.replace(tmp, P(f))


def effective(t, rec):
    """The status the page shows for thread t, given its stored record."""
    s = rec.get("status", "")
    if s == "skip":
        return "skip" if rec.get("sig") == t["sig"] else "reopened"
    if s in ("pending", "review"):
        return s
    if not t["open"]:
        return "done"
    if s == "done" and rec.get("sig"):          # kept as is: done until the thread changes
        return "done" if rec["sig"] == t["sig"] else "reopened"
    return ""                                   # live comments and no open decision: to do


def items():
    with open(ARGS.tex, encoding="utf-8") as fh:
        tex = fh.read()
    st = load("state.json", {"version": 0, "cards": {}})
    props = load("proposals.json", {})
    out = []
    for t in scan.threads(tex):
        p = props.get(t["id"], {})
        t.update(status=effective(t, st["cards"].get(t["id"], {})), rev=p.get("rev", 0),
                 changes=p.get("changes", []), replies=p.get("replies", []),
                 needs_check=p.get("needs_check"), drafting=p.get("drafting", False))
        out.append(t)
    return out


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=HERE, **k)

    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/items"):
            return self._json(items())
        if self.path.startswith("/api/meta"):
            with open(ARGS.tex, encoding="utf-8") as fh:
                tex = fh.read()
            return self._json({"tex": os.path.basename(ARGS.tex), "macros": scan.find_macros(tex)})
        if self.path.startswith("/api/state"):
            st = load("state.json", {"version": 0, "cards": {}})
            st["tex_mtime"] = os.path.getmtime(ARGS.tex)   # edits to the paper refresh the page too
            st["props_mtime"] = os.path.getmtime(P("proposals.json")) if os.path.exists(P("proposals.json")) else 0
            return self._json(st)
        if self.path.startswith("/api/queue"):
            try:
                with open(P("queue.jsonl")) as fh:
                    return self._json([json.loads(l) for l in fh if l.strip()])
            except FileNotFoundError:
                return self._json([])
        if self.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        msg = json.loads(self.rfile.read(n) or b"{}")
        st = load("state.json", {"version": 0, "cards": {}})
        tid = str(msg.get("id", ""))
        if self.path.startswith("/api/done"):
            msg["ts"] = time.time()
            with open(P("queue.jsonl"), "a") as fh:
                fh.write(json.dumps(msg) + "\n")
            st["cards"][tid] = {"status": "pending", "decision": msg.get("decision")}
        elif self.path.startswith("/api/skip"):
            st["cards"][tid] = {"status": "skip", "sig": msg.get("sig"), "ts": time.time()}
        elif self.path.startswith("/api/unskip"):
            st["cards"].pop(tid, None)
        else:
            return self._json({"error": "not found"}, 404)
        st["version"] = st.get("version", 0) + 1
        dump("state.json", st)
        return self._json({"ok": True})

    def log_message(self, *a):
        pass


def main():
    global ARGS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tex", required=True, help="the paper's main .tex file")
    ap.add_argument("--data", help="where decisions and state are kept (default: .review-cards next to the .tex)")
    ap.add_argument("--port", type=int, default=8765)
    ARGS = ap.parse_args()
    ARGS.tex = os.path.abspath(ARGS.tex)
    ARGS.data = os.path.abspath(ARGS.data or os.path.join(os.path.dirname(ARGS.tex), ".review-cards"))
    os.makedirs(ARGS.data, exist_ok=True)
    if not os.path.exists(P(".gitignore")):          # the data never belongs in the paper's repository
        with open(P(".gitignore"), "w") as fh:
            fh.write("*\n")
    with open(P("config.json"), "w") as fh:
        json.dump({"tex": ARGS.tex}, fh)
    print(f"paper-review-cards: {ARGS.tex}\n  data: {ARGS.data}\n  http://localhost:{ARGS.port}/")
    ThreadingHTTPServer(("127.0.0.1", ARGS.port), H).serve_forever()


if __name__ == "__main__":
    main()
