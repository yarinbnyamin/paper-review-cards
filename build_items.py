"""Build items.json (the review cards) from two versions of main.tex.

usage:  python build_items.py BASE_COMMIT REVIEW_COMMIT [--keep-state]
  BASE_COMMIT    commit with Shahaf's notes still live (e.g. main before the pass)
  REVIEW_COMMIT  commit where the edits were applied and the notes commented out
Writes items.json and old.tex (the base text, used to find each note's first line).
Without --keep-state, state.json / queue.jsonl / processed.txt are reset.

One card = one \\shahaf note. A changed hunk belongs to the note it contains, else to
the nearest note after it in the BASE text (within 6 lines), else before it.
Edits far from their note need an entry in OVERRIDE (base line of the hunk -> note line).
"""
import difflib, json, os, re, subprocess, sys

REPO = "/Users/bnyamin/Projects/overleaf/PlanB-shahaf"
HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda f: os.path.join(HERE, f)
# hunk start line in BASE -> note line in BASE (first pass, 2026-10-05; base 4ff0341, review b192ec7)
OVERRIDE = {199: 190, 409: 298, 462: 456, 727: 723, 779: 880, 417: 418}
LIVE_PARTIAL = {723, 880, 1039}     # notes only partly handled: kept live
MARK = "@@NOTE@@"

def show(commit):
    return subprocess.run(["git", "-C", REPO, "show", f"{commit}:main.tex"],
                          capture_output=True, text=True, check=True).stdout

def is_note(l):
    return re.match(r"\s*(%\s*)?\\shahaf\{", l) is not None

def block_end(L, k):
    depth = 0
    while k < len(L):
        depth += L[k].count("{") - L[k].count("}"); k += 1
        if depth <= 0: break
    return k

def note_text(A, n):
    i, depth, out = n - 1, 0, []
    while True:
        out.append(A[i]); depth += A[i].count("{") - A[i].count("}")
        if depth <= 0: break
        i += 1
    t = " ".join(x.strip() for x in out)
    t = re.sub(r"^\\shahaf\{", "", t)
    return t[:-1] if t.endswith("}") else t

def section(A, line):
    sec = sub = ""
    for k in range(line):
        m = re.match(r"\\section\{([^}]*)\}", A[k])
        if m: sec, sub = m.group(1), ""
        m = re.match(r"\\subsection\{([^}]*)\}", A[k])
        if m: sub = m.group(1)
    return sec + (" / " + sub if sub else "")

def ctx(L, start, step, note_start, n=12):
    out, k = [], start
    while 0 <= k < len(L) and len(out) < n:
        l = L[k]
        if is_note(l):
            if k == note_start: out.append(MARK)
            k = block_end(L, k) if step > 0 else k + step
            continue
        if l.lstrip().startswith("%"):
            k += step; continue
        out.append(l); k += step
    return out[::-1] if step < 0 else out

def main():
    base, rev = sys.argv[1], sys.argv[2]
    A, B = show(base).split("\n"), show(rev).split("\n")
    open(P("old.tex"), "w").write("\n".join(A))
    sm = difflib.SequenceMatcher(None, A, B, autojunk=False)
    items = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal": continue
        old, new = A[i1:i2], B[j1:j2]
        if old and len(old) == len(new) and all(n == "% " + o for o, n in zip(old, new)):
            continue                                   # only a note being commented out
        inside = [k for k in range(i1, i2) if re.match(r"\s*\\shahaf\{", A[k])]
        if inside: note = inside[0] + 1
        else:
            nx = next((k for k in range(i2, min(len(A), i2 + 6)) if re.match(r"\s*\\shahaf\{", A[k])), None)
            if nx is None:
                nx = next((k for k in range(i1 - 1, max(-1, i1 - 6), -1) if re.match(r"\s*\\shahaf\{", A[k])), None)
            note = None if nx is None else nx + 1
        note = OVERRIDE.get(i1 + 1, note)
        o = [x for x in old if not is_note(x)]; nw = [x for x in new if not is_note(x)]
        if note is None or (not o and not nw): continue
        tgt = A[note - 1]
        n_new = next((k for k, l in enumerate(B) if l == tgt or l == "% " + tgt), None)
        it = items.setdefault(note, dict(note=note, section=section(A, note), comment=note_text(A, note),
                                         changes=[], partial=note in LIVE_PARTIAL,
                                         note_new=None if n_new is None else n_new + 1))
        c = dict(line=i1 + 1, old="\n".join(o), new="\n".join(nw))
        c["old_before"] = ctx(A, i1 - 1, -1, note - 1); c["old_after"] = ctx(A, i2, 1, note - 1)
        c["new_before"] = ctx(B, j1 - 1, -1, n_new); c["new_after"] = ctx(B, j2, 1, n_new)
        c["mark_in_change"] = any(x == tgt for x in old)
        c["near"] = c["mark_in_change"] or MARK in c["old_before"] + c["old_after"]
        it["changes"].append(c)
    out = sorted(items.values(), key=lambda x: x["note"])
    json.dump(out, open(P("items.json"), "w"), indent=1)
    if "--keep-state" not in sys.argv:
        json.dump({"version": 0, "cards": {}}, open(P("state.json"), "w"))
        open(P("queue.jsonl"), "w").close(); open(P("processed.txt"), "w").write("0")
    far = [(it["note"], c["line"]) for it in out for c in it["changes"] if not c["near"]]
    print(f"{len(out)} cards, {sum(len(i['changes']) for i in out)} changes; far from their note: {far}")

if __name__ == "__main__":
    main()
