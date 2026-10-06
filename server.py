"""Review loop server for Shahaf's notes.

GET  /                -> index.html
GET  /api/items       -> items.json (cards; rewritten by Claude when a card is revised)
GET  /api/state       -> state.json ({"version": n, "cards": {note: {"status": ...}}})
GET  /api/queue       -> every decision sent so far (queue.jsonl), for the per-card conversation
POST /api/done        -> append the decision to queue.jsonl, mark the card "pending"
Statuses: pending (yellow, waiting for Claude), done (green), review (red, Claude revised it: look again).
"""
import json, os, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(HERE, f)

def load(f, default):
    try:
        return json.load(open(P(f)))
    except Exception:
        return default

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
            return self._json(load("items.json", []))
        if self.path.startswith("/api/queue"):
            try:
                q = [json.loads(l) for l in open(P("queue.jsonl")) if l.strip()]
            except Exception:
                q = []
            return self._json(q)
        if self.path.startswith("/api/state"):
            return self._json(load("state.json", {"version": 0, "cards": {}}))
        if self.path in ("/", ""):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if not self.path.startswith("/api/done"):
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        msg = json.loads(self.rfile.read(n) or b"{}")
        msg["ts"] = time.time()
        with open(P("queue.jsonl"), "a") as f:
            f.write(json.dumps(msg) + "\n")
        st = load("state.json", {"version": 0, "cards": {}})
        st["cards"][str(msg["note"])] = {"status": "pending", "decision": msg.get("decision")}
        st["version"] = st.get("version", 0) + 1
        json.dump(st, open(P("state.json"), "w"))
        return self._json({"ok": True})

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
