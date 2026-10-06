"""Find the review comments in a LaTeX file and group them into threads.

A comment macro is a one-argument command defined in the preamble whose body
shows its argument as a note, e.g.

    \\newcommand{\\shahaf}[1]{\\ifaddcomments{\\textcolor{blue}{[Shahaf: #1]}}\\fi}

Every use of such a macro after \\begin{document} is a comment, live or
commented out with %. Comments that follow each other with nothing but
whitespace and % signs between them form one thread (e.g. Shahaf, Yarin,
Shahaf), and each thread is one card.

A thread's id comes from its first comment, so it survives edits elsewhere in
the file and replies added under it. Its signature covers all its comments, so
it changes when someone adds a comment to the thread: that is what brings a
skipped card back.

    python3 scan.py main.tex            # summary
    python3 scan.py main.tex --json     # the threads as JSON
"""
import hashlib
import json
import re
import sys

# Bodies that mark a macro as a note rather than a formatting command.
NOTE_HINTS = (r"\textcolor", r"\color", r"\marginpar", r"\todo", r"\ifaddcomments",
              r"\fbox", r"\colorbox", r"\hl", r"\note")


def _balanced(s, i):
    """s[i] == '{'; index just past the matching '}', or None if it never closes."""
    depth = 0
    j = i
    while j < len(s):
        ch = s[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return None


def _split_comment(line):
    """(code, comment) at the first unescaped %; comment is None if there is no %."""
    j = 0
    while j < len(line):
        if line[j] == "\\":
            j += 2
            continue
        if line[j] == "%":
            return line[:j], line[j + 1:]
        j += 1
    return line, None


def find_macros(tex):
    """{name: {"label": ..., "color": ...}} for every one-argument note macro in the preamble."""
    pre = tex.split(r"\begin{document}", 1)[0]
    out = {}
    pat = re.compile(r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?\s*\[1\]\s*\{")
    for line in pre.split("\n"):
        code, _ = _split_comment(line)
        for m in pat.finditer(code):
            end = _balanced(code, m.end() - 1)
            if end is None:
                continue
            body = code[m.end():end - 1]
            if "#1" not in body or not any(h in body for h in NOTE_HINTS):
                continue
            name = m.group(1)
            lab = re.search(r"\[([^\]:#]+?):", body)
            col = re.search(r"\\(?:textcolor|color)\{([^}]+)\}", body)
            out[name] = {"label": lab.group(1).strip() if lab else name,
                         "color": col.group(1) if col else ""}
    return out


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def find_comments(tex, macros):
    """Every use of a note macro after \\begin{document}, in file order."""
    lines = tex.split("\n")
    first = 0
    for k, l in enumerate(lines):
        if l.lstrip().startswith(r"\begin{document}"):
            first = k + 1
            break
    if not macros:
        return []
    name_re = re.compile(r"\\(" + "|".join(sorted(map(re.escape, macros), key=len, reverse=True))
                         + r")(?![A-Za-z])\s*\{")
    # two streams with the same line structure: the code before %, and the text after it
    code, comm, ccol = [], [], []
    for l in lines:
        c, k = _split_comment(l)
        code.append(c)
        comm.append(k if k is not None else "")
        ccol.append(len(c) + 1 if k is not None else None)
    found = []
    for live, stream in ((True, code), (False, comm)):
        offs, pos = [], 0
        for s in stream:
            offs.append(pos)
            pos += len(s) + 1
        text = "\n".join(stream)

        def where(p):
            lo, hi = 0, len(offs) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if offs[mid] <= p:
                    lo = mid
                else:
                    hi = mid - 1
            return lo, p - offs[lo]

        for m in name_re.finditer(text, offs[first] if first < len(offs) else len(text)):
            end = _balanced(text, m.end() - 1)
            l0, c0 = where(m.start())
            if end is None:                       # never closes: keep to the end of its line
                l1 = l0
                c1 = len(stream[l0])
                body = stream[l0][c0:]
            else:
                l1, c1 = where(end)
                body = text[m.end():end - 1]
            if not live:
                # a commented comment must sit in consecutive commented lines
                if any(ccol[k] is None for k in range(l0, l1 + 1)):
                    continue
                c0 += ccol[l0]
                c1 += ccol[l1]
            found.append({"macro": m.group(1), "text": body, "live": live,
                          "line": l0 + 1, "col": c0, "end_line": l1 + 1, "end_col": c1})
    found.sort(key=lambda c: (c["line"], c["col"]))
    return found


def _gap(lines, a, b):
    """The source text between the end of comment a and the start of comment b."""
    l0, c0, l1, c1 = a["end_line"] - 1, a["end_col"], b["line"] - 1, b["col"]
    if (l0, c0) > (l1, c1):
        return "x"                                # overlapping (nested): not a thread neighbour
    if l0 == l1:
        return lines[l0][c0:c1]
    return "\n".join([lines[l0][c0:]] + lines[l0 + 1:l1] + [lines[l1][:c1]])


def _sections(lines):
    """For each line, the section / subsection it belongs to."""
    out, sec, sub = [], "", ""
    pat = re.compile(r"^\s*\\(section|subsection)\*?\{(.*)\}")
    for l in lines:
        m = pat.match(l)
        if m:
            if m.group(1) == "section":
                sec, sub = m.group(2), ""
            else:
                sub = m.group(2)
        out.append(sec + (" / " + sub if sub else ""))
    return out


def threads(tex, macros=None, context=4):
    """The comment threads of a LaTeX source, each with a stable id and a signature."""
    macros = find_macros(tex) if macros is None else macros
    lines = tex.split("\n")
    cs = find_comments(tex, macros)
    groups = []
    for c in cs:
        if groups and not re.sub(r"[\s%]", "", _gap(lines, groups[-1][-1], c)):
            groups[-1].append(c)
        else:
            groups.append([c])
    secs = _sections(lines)
    out, seen = [], {}
    for g in groups:
        head = g[0]["macro"] + ":" + _norm(g[0]["text"])
        tid = hashlib.sha1(head.encode()).hexdigest()[:10]
        seen[tid] = seen.get(tid, 0) + 1
        if seen[tid] > 1:                          # the same first comment twice in the file
            tid = f"{tid}-{seen[tid]}"
        sig = hashlib.sha1("\n".join(c["macro"] + ":" + _norm(c["text"]) for c in g).encode()).hexdigest()[:10]
        l0, l1 = g[0]["line"], g[-1]["end_line"]
        out.append({
            "id": tid, "sig": sig, "open": any(c["live"] for c in g),
            "line": l0, "end_line": l1, "section": secs[l0 - 1],
            "comments": [{k: c[k] for k in ("macro", "text", "live", "line", "col", "end_line", "end_col")} for c in g],
            "before": lines[max(0, l0 - 1 - context):l0 - 1],
            "lines": lines[l0 - 1:l1],
            "after": lines[l1:l1 + context],
        })
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    tex = open(sys.argv[1], encoding="utf-8").read()
    ms = find_macros(tex)
    ts = threads(tex, ms)
    if "--json" in sys.argv:
        print(json.dumps({"macros": ms, "threads": ts}, indent=1))
    else:
        print("macros:", ", ".join(f"\\{k} ({v['label']})" for k, v in ms.items()))
        print(f"{len(ts)} threads, {sum(t['open'] for t in ts)} open, "
              f"{sum(len(t['comments']) for t in ts)} comments")
        for t in ts:
            who = " > ".join(("" if c["live"] else "%") + c["macro"] for c in t["comments"])
            print(f"  {t['id']}  line {t['line']:>5}  {'open    ' if t['open'] else 'resolved'}  {who}")
