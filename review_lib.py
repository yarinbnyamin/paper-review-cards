"""Helpers Claude uses to act on review cards.

The cards are the comment threads of the paper (see scan.py); this module is
how Claude answers them. It finds the data directory from, in order: the
`data` argument of configure(), $REVIEW_CARDS_DATA, ./.review-cards.

    import review_lib as R
    R.configure("/path/to/paper/.review-cards")
    t = R.thread(tid)                      # the card's thread, as the page shows it
    R.propose(tid, old, new)               # edit the paper and record the edit on the card
    R.reply(tid, "what I did / the answer") # Claude's message on the card
    R.set_status(tid, "review")            # red: the user looks again

Invariant: for every recorded change, its `new` text occurs exactly once in the
paper, so later decisions (accept / reject / edit) can find it. The functions
here refuse to edit when that does not hold, rather than guess.
"""
import json
import os
import time

import scan

DATA = None


def configure(data=None):
    global DATA
    DATA = os.path.abspath(data or os.environ.get("REVIEW_CARDS_DATA") or ".review-cards")
    return DATA


def P(f):
    if DATA is None:
        configure()
    return os.path.join(DATA, f)


def _load(f, default):
    try:
        with open(P(f)) as fh:
            return json.load(fh)
    except Exception:
        return default


def _dump(f, obj):
    tmp = P(f) + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=1)
    os.replace(tmp, P(f))


def tex_path():
    return _load("config.json", {})["tex"]


def read_tex():
    with open(tex_path(), encoding="utf-8") as fh:
        return fh.read()


def write_tex(s):
    with open(tex_path(), "w", encoding="utf-8") as fh:
        fh.write(s)


# ----- cards -----------------------------------------------------------------

def threads():
    return scan.threads(read_tex())


def thread(tid):
    for t in threads():
        if t["id"] == tid:
            return t
    raise KeyError(f"no thread {tid!r} in {tex_path()}")


def proposals():
    return _load("proposals.json", {})


def _card(props, tid):
    return props.setdefault(tid, {"rev": 0, "changes": [], "replies": []})


def state():
    return _load("state.json", {"version": 0, "cards": {}})


def set_status(tid, status, **extra):
    st = state()
    st["cards"][tid] = dict(status=status, **extra)
    st["version"] = st.get("version", 0) + 1
    _dump("state.json", st)


def set_meta(tid, needs_check=None, drafting=None):
    """Card badges: needs_check ("plot", "experiment", "data", "code" or free text; "" clears it),
    drafting=True while a proposal is being prepared."""
    props = proposals()
    c = _card(props, tid)
    if needs_check is not None:
        c["needs_check"] = needs_check or None
    if drafting is not None:
        c["drafting"] = bool(drafting)
    _dump("proposals.json", props)


def keep(tid):
    """Keep: no change to the paper; the card is done until someone adds to the thread."""
    set_status(tid, "done", sig=thread(tid)["sig"])


def reply(tid, text):
    """Claude's message on the card: kept in its conversation, and the card is revised (rev + 1)."""
    props = proposals()
    c = _card(props, tid)
    c["rev"] += 1
    c["replies"].append({"ts": time.time(), "rev": c["rev"], "text": text})
    _dump("proposals.json", props)


# ----- the queue ---------------------------------------------------------------

def queue():
    try:
        with open(P("queue.jsonl")) as fh:
            return [json.loads(l) for l in fh if l.strip()]
    except FileNotFoundError:
        return []


def processed():
    try:
        with open(P("processed.txt")) as fh:
            return int(fh.read().strip() or 0)
    except FileNotFoundError:
        return 0


def pending():
    """The decisions not handled yet, in order."""
    return queue()[processed():]


def mark_processed(n):
    with open(P("processed.txt"), "w") as fh:
        fh.write(str(n))


# ----- edits to the paper --------------------------------------------------------

def _once(s, text):
    n = s.count(text)
    if n != 1:
        raise ValueError(f"text occurs {n} times in the paper, expected once: {text[:70]!r}")


def propose(tid, old, new):
    """Replace `old` (exactly once in the paper) by `new`, and record the change on card tid."""
    s = read_tex()
    _once(s, old)
    write_tex(s.replace(old, new, 1))
    props = proposals()
    _card(props, tid)["changes"].append({"old": old, "new": new})
    _dump("proposals.json", props)


def replace_change(tid, k, text):
    """Make the paper hold `text` where change k of card tid currently holds its `new` text."""
    props = proposals()
    c = _card(props, tid)["changes"][k]
    s = read_tex()
    if c["new"]:
        _once(s, c["new"])
        if text == "" and c["new"] + "\n" in s:
            s = s.replace(c["new"] + "\n", "", 1)   # deleting whole lines leaves no blank line
        else:
            s = s.replace(c["new"], text, 1)
    else:
        anchor = c.get("anchor")
        if not anchor:
            raise ValueError("change removed its text and has no anchor line; re-insert it by hand")
        _once(s, anchor + "\n")
        s = s.replace(anchor + "\n", anchor + "\n" + text + "\n", 1)
    write_tex(s)
    c["new"] = text
    _dump("proposals.json", props)


def reject_all(tid):
    """Put back the original text of every change on card tid (last change first)."""
    for k in reversed(range(len(proposals().get(tid, {}).get("changes", [])))):
        replace_change(tid, k, proposals()[tid]["changes"][k]["old"])


def _comment_lines(text):
    return "\n".join("% " + l if l.strip() and not l.lstrip().startswith("%") else l
                     for l in text.split("\n"))


def comment_out_thread(tid):
    """Comment out every live comment of the thread (it is then resolved). Returns how many."""
    t = thread(tid)
    L = read_tex().split("\n")
    n = 0
    for c in reversed([c for c in t["comments"] if c["live"]]):
        l0, c0, l1, c1 = c["line"] - 1, c["col"], c["end_line"] - 1, c["end_col"]
        if not L[l0][:c0].strip() and not L[l1][c1:].strip():
            for i in range(l0, l1 + 1):                       # the comment fills its own lines
                if L[i].strip():
                    L[i] = "% " + L[i]
        else:                                                 # inline: move it to its own commented line
            body = "\n".join([L[l0][c0:]] + L[l0 + 1:l1] + [L[l1][:c1]]) if l1 > l0 else L[l0][c0:c1]
            rest = (L[l0][:c0].rstrip() + " " + L[l1][c1:].lstrip()).rstrip()
            L[l0:l1 + 1] = [rest] + _comment_lines(body).split("\n")
        n += 1
    write_tex("\n".join(L))
    return n


def edit_thread(tid, text):
    """Replace the thread's lines (as the card shows them) by `text`: the user's own version."""
    t = thread(tid)
    L = read_tex().split("\n")
    if L[t["line"] - 1:t["end_line"]] != t["lines"]:
        raise ValueError("the thread's lines changed since the card was built")
    L[t["line"] - 1:t["end_line"]] = text.split("\n")
    write_tex("\n".join(L))


def add_comment(tid, macro, text):
    """Add \\macro{text} as a new line right after the thread, so it joins the thread."""
    t = thread(tid)
    L = read_tex().split("\n")
    L.insert(t["end_line"], "\\" + macro + "{" + text + "}")
    write_tex("\n".join(L))
