"""Helpers Claude uses to apply review decisions to main.tex (shahaf-review branch).

Invariant: for every card, items.json's change["new"] is the text currently in main.tex.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = "/Users/bnyamin/Projects/overleaf/PlanB-shahaf/main.tex"  # review worktree, branch shahaf-review-wt
P = lambda f: os.path.join(HERE, f)

def items():
    return json.load(open(P("items.json")))

def save_items(its, bump=True):
    json.dump(its, open(P("items.json"), "w"), indent=1)
    if bump:
        st = state(); st["items_version"] = st.get("items_version", 0) + 1; st["version"] = st.get("version", 0) + 1
        json.dump(st, open(P("state.json"), "w"))

def state():
    try:
        return json.load(open(P("state.json")))
    except Exception:
        return {"version": 0, "cards": {}}

def set_status(note, status, **extra):
    st = state(); st["cards"][str(note)] = dict(status=status, **extra); st["version"] = st.get("version", 0) + 1
    json.dump(st, open(P("state.json"), "w"))

def card(its, note):
    return next(it for it in its if it["note"] == note)

def replace_change(c, text):
    """Make main.tex hold `text` where change c currently holds c['new']."""
    s = open(MAIN).read()
    cur = c["new"]
    if cur:
        n = s.count(cur)
        assert n == 1, f"current text occurs {n}x: {cur[:70]!r}"
        if text == "":   # delete the whole line(s)
            s = s.replace(cur + "\n", "", 1) if (cur + "\n") in s else s.replace(cur, "", 1)
        else:
            s = s.replace(cur, text, 1)
    else:              # the change had removed text: re-insert after the line before it
        anchor = c["new_before"][-1]
        n = s.count(anchor + "\n")
        assert n == 1, f"anchor occurs {n}x: {anchor[:70]!r}"
        s = s.replace(anchor + "\n", anchor + "\n" + text + "\n", 1)
    open(MAIN, "w").write(s)
    c["new"] = text

def comment_out_note(note_first_line):
    """Comment out the live \\shahaf{...} block starting with this exact line (no-op if already commented)."""
    L = open(MAIN).read().split("\n")
    idx = [i for i, l in enumerate(L) if l == note_first_line]
    if not idx:
        return False
    i = idx[0]; depth = 0
    while True:
        depth += L[i].count("{") - L[i].count("}")
        if not L[i].lstrip().startswith("%"):
            L[i] = "% " + L[i]
        if depth <= 0:
            break
        i += 1
    open(MAIN, "w").write("\n".join(L))
    return True

def uncomment_note(note_first_line):
    L = open(MAIN).read().split("\n")
    idx = [i for i, l in enumerate(L) if l == "% " + note_first_line]
    if not idx:
        return False
    i = idx[0]; depth = 0
    while True:
        if L[i].startswith("% "):
            L[i] = L[i][2:]
        depth += L[i].count("{") - L[i].count("}")
        if depth <= 0:
            break
        i += 1
    open(MAIN, "w").write("\n".join(L))
    return True

def mark_processed(n):
    open(P("processed.txt"), "w").write(str(n))


def reply(it, text):
    """Claude's answer on a card: bump its rev, show the text, and keep it in the card's conversation."""
    import time
    it["rev"] = it.get("rev", 0) + 1
    it["claude_note"] = text
    it.setdefault("replies", []).append({"ts": time.time(), "rev": it["rev"], "text": text})
