"""Move cards and decisions between the paper and the artifact's database.

Claude cannot reach the artifact's database from Python; it uses the ArtifactData
tool. This script prepares and reads the JSON files that tool sends and saves.

    # paper -> artifact: one JSON file per card, plus meta/paper.json
    python3 "Claude Artifact/bridge.py" export --tex main.tex --out <dir>
        then ArtifactData "batch" with {op: set, collection: "cards", doc_id, file_path}
        for each <dir>/cards/<id>.json (pin if_version for cards that already exist),
        and the same for meta/paper.

    # artifact -> paper: decisions the page wrote
    ArtifactData "list" collection "decisions" with out_dir <dir>
    python3 "Claude Artifact/bridge.py" ingest --tex main.tex --decisions <dir>/decisions
        appends every unhandled decision to .review-cards/queue.jsonl (once), so the
        normal review_lib handling applies; prints the decision ids to mark handled.

The data directory (.review-cards next to the .tex) is the same as for the local
server: proposals.json, state.json, queue.jsonl.
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scan  # noqa: E402
import server  # noqa: E402


def _load(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def cards(tex_path, data):
    with open(tex_path, encoding="utf-8") as fh:
        tex = fh.read()
    st = _load(os.path.join(data, "state.json"), {"cards": {}})
    props = _load(os.path.join(data, "proposals.json"), {})
    out = []
    for t in scan.threads(tex):
        rec = st["cards"].get(t["id"], {})
        if rec.get("status") == "skip":
            rec = {}                       # skips live in the artifact, not here
        p = props.get(t["id"], {})
        status = server.effective(t, rec)
        if status == "pending":
            status = ""                    # the page derives "with Claude" from open decisions
        t.update(status=status, rev=p.get("rev", 0), changes=p.get("changes", []),
                 replies=p.get("replies", []), needs_check=p.get("needs_check"),
                 drafting=p.get("drafting", False))
        out.append(t)
    return out, scan.find_macros(tex)


def export(a):
    cs, macros = cards(a.tex, a.data)
    os.makedirs(os.path.join(a.out, "cards"), exist_ok=True)
    os.makedirs(os.path.join(a.out, "meta"), exist_ok=True)
    for c in cs:
        with open(os.path.join(a.out, "cards", c["id"] + ".json"), "w") as fh:
            json.dump(c, fh)
    with open(os.path.join(a.out, "meta", "paper.json"), "w") as fh:
        json.dump({"tex": os.path.basename(a.tex), "macros": macros}, fh)
    print(json.dumps({"cards": [c["id"] for c in cs], "open": sum(c["open"] for c in cs)}))


def ingest(a):
    seen_path = os.path.join(a.data, "ingested.json")
    seen = set(_load(seen_path, []))
    new = []
    for f in sorted(glob.glob(os.path.join(a.decisions, "*.json"))):
        doc = _load(f, {})
        body = doc.get("data", doc) if isinstance(doc.get("data"), dict) else doc
        did = doc.get("doc_id") or doc.get("id_") or os.path.splitext(os.path.basename(f))[0]
        if body.get("handled") or did in seen:
            continue
        new.append((body.get("ts", 0), did, body))
    new.sort(key=lambda x: x[0])
    with open(os.path.join(a.data, "queue.jsonl"), "a") as fh:
        for _, did, body in new:
            entry = {k: v for k, v in body.items() if k != "handled"}
            entry["decision_doc"] = did
            fh.write(json.dumps(entry) + "\n")
            seen.add(did)
    with open(seen_path, "w") as fh:
        json.dump(sorted(seen), fh)
    print(json.dumps({"queued": [d for _, d, _ in new]}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("export", "ingest"):
        p = sub.add_parser(name)
        p.add_argument("--tex", required=True)
        p.add_argument("--data", help="default: .review-cards next to the .tex")
        if name == "export":
            p.add_argument("--out", required=True)
        else:
            p.add_argument("--decisions", required=True, help="directory of decision JSON files saved by ArtifactData")
    a = ap.parse_args()
    a.tex = os.path.abspath(a.tex)
    a.data = os.path.abspath(a.data or os.path.join(os.path.dirname(a.tex), ".review-cards"))
    os.makedirs(a.data, exist_ok=True)
    cfg = os.path.join(a.data, "config.json")
    if not os.path.exists(cfg):
        with open(cfg, "w") as fh:
            json.dump({"tex": a.tex}, fh)
    if not os.path.exists(os.path.join(a.data, ".gitignore")):
        with open(os.path.join(a.data, ".gitignore"), "w") as fh:
            fh.write("*\n")
    export(a) if a.cmd == "export" else ingest(a)


if __name__ == "__main__":
    main()
