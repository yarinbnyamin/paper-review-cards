# Running the review cards as a Claude artifact

Instead of the local server and page, the cards can live in a private artifact
on claude.ai: a page with the same cards and buttons, whose decisions are saved
in the artifact's own database. Claude still does the work locally, with the
same `scan.py` and `review_lib.py`.

## When to use it

| | Local page (`server.py`) | Artifact |
|---|---|---|
| Setup | `python3 server.py --tex main.tex` | nothing to run; open a claude.ai link, also on a phone |
| Sharing with co-authors | they need the repo and the server | share the artifact from its Share menu |
| Where the paper's text is | only on your machine | on claude.ai (private unless you share it) |
| Edits to the paper | the page rescans the `.tex` on every refresh | Claude uploads the cards again after every change |
| Reaching Claude | the watcher wakes Claude when you press Done | tell Claude, or let it check on a timer |

Keep an unpublished or anonymous submission on the local page unless you are
fine with its text on claude.ai.

## How it works

```
main.tex --scan.py--> bridge.py export --> ArtifactData batch --> cards, meta  --+
                                                                                |  the page
main.tex <--review_lib.py-- .review-cards/queue.jsonl <-- bridge.py ingest <-- decisions, skips
```

The artifact's database has four collections:

| collection | written by | what |
|---|---|---|
| `meta/paper` | Claude | the file name and the comment macros (label, colour) |
| `cards/<thread id>` | Claude | one card per thread, the same fields the local server serves |
| `decisions/<auto id>` | the page | one per Done; Claude sets `handled: true` after applying it |
| `skips/<thread id>` | the page | Skip and Unskip; a skipped card comes back when its thread's `sig` changes |

The page is built from `index.html` by `build_page.py`, so it always has the
local page's look and logic; only the transport differs. "With Claude" (yellow)
is shown while a card has an unhandled decision.

## Steps for Claude

Everything below runs from the paper's directory, with this repo as the
`paper-review-cards` submodule. The data directory is `.review-cards/` next to
the `.tex`, the same as for the local page.

1. **Build and publish the page** (once, and again whenever `index.html` changes):
   ```bash
   python3 "paper-review-cards/Claude Artifact/build_page.py" <scratchpad>/review-cards.html
   ```
   Publish that file with the Artifact tool, `capabilities: {"db": {}}`, as a
   private artifact. Keep its URL; later publishes of the same file update it.

2. **Upload the cards:**
   ```bash
   python3 "paper-review-cards/Claude Artifact/bridge.py" export --tex main.tex --out <scratchpad>/sync
   ```
   Then one `ArtifactData` batch (up to 50 writes each): `set` on `meta`/`paper`
   and on `cards`/`<id>` for every file in `<scratchpad>/sync/cards/`, with
   `file_path`. Cards that already exist need their `if_version`: read it with
   `ArtifactData list` on `cards` first. Delete card documents whose thread no
   longer exists.

3. **Collect decisions** (when the user says so, or on a timer):
   `ArtifactData list` on `decisions` with `out_dir: <scratchpad>/dl`, then
   ```bash
   python3 "paper-review-cards/Claude Artifact/bridge.py" ingest --tex main.tex --decisions <scratchpad>/dl/decisions
   ```
   It appends the unhandled decisions to `.review-cards/queue.jsonl` (each one
   once) and prints their ids.

4. **Apply them** exactly as for the local page (`CLAUDE.md`, "Handling a
   decision"), one subagent per card for the work that needs thought.

5. **Write back:** set `handled: true` on each applied decision
   (`ArtifactData update`, pinned to its version), then repeat step 2 so the
   cards show the new text, replies and statuses.

## Status

A prototype, tried on `examples/demo.tex`: the page builds, publishes and
receives the cards. The full loop through a real decision (page → Claude →
paper → page) has not been run end to end yet.
