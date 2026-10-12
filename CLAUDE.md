# paper-review-cards: how Claude runs it

The cards are the comment threads of a LaTeX paper. A comment is any use of a
one-argument note macro defined in the preamble (`\newcommand{\alice}[1]{...\textcolor...#1...}`);
comments separated only by whitespace and `%` form one thread; one thread is one
card. See `scan.py`. Nothing is generated ahead of time: the server rescans the
`.tex` on every request, so edits to the paper show up on the page by themselves.

## Starting

From the paper's directory (this repo is usually a submodule there):

```bash
python3 paper-review-cards/server.py --tex main.tex          # page at http://localhost:8765/
REVIEW_CARDS_DATA=.review-cards POLL=60 python3 paper-review-cards/wait_queue.py   # in the background
```

The data directory (default `.review-cards/` next to the `.tex`) holds
`config.json`, `state.json`, `queue.jsonl`, `processed.txt` and
`proposals.json`. It ignores itself in git. Never commit it to the paper.

When the watcher exits it prints the new decisions. Handle them (below), then
`R.mark_processed(len(R.queue()))` and start the watcher again.

## Handling a decision

```python
import review_lib as R
R.configure("<paper>/.review-cards")
for e in R.pending(): ...
```

Each entry is `{id, sig, rev, line, decision, instruction, edits, proposed, macro, text, ts}`.
`id` is the thread id. Look the thread up with `R.thread(id)`; if the user edited
the first comment since, the id may no longer exist: find the thread by `line`
and tell the user. `proposed` says whether the card had Claude's changes when
the user decided.

A card with Claude's changes offers Accept / Reject / Edit; a card without them
offers Resolve / Keep / Edit (the edit is then the thread's own lines). Both
offer Ask Claude, Reply in the paper and Skip.

| decision | what to do |
|---|---|
| `change` (Ask Claude) | Do what the instruction says. Edit the paper with `R.propose(id, old, new)` so the edit shows on the card as a change. If it is only a question, change nothing. Always answer with `R.reply(id, text)`, then `R.set_status(id, "review")` (red). |
| `accept` | The card's changes stay. `R.comment_out_thread(id)`, `R.set_status(id, "done")`. |
| `reject` | `R.reject_all(id)` puts the original text back. Then `R.comment_out_thread(id)` and `R.set_status(id, "done")`. |
| `edit`, `proposed` true | `R.replace_change(id, k, edits[k])` for every change, then as for accept. |
| `edit`, `proposed` false | `R.edit_thread(id, edits[0])` replaces the thread's lines with the user's version; then `R.set_status(id, "done", sig=R.thread(id)["sig"])` if it still has live comments. |
| `resolve` | `R.comment_out_thread(id)`, `R.set_status(id, "done")`. |
| `keep` | No change: `R.keep(id)`. The card is done until someone adds to the thread. |
| `reply` | `R.add_comment(id, macro, text)` adds the user's own comment under the thread. The thread now waits for the others, so skip it with its new signature: `R.set_status(id, "skip", sig=R.thread(id)["sig"])`. It comes back when someone answers. |

Skip and unskip never reach Claude: the server records them itself.

Rules:
- Every Claude answer goes through `R.reply`, so the card keeps the conversation.
- Edit the paper only through `R.propose` / `R.replace_change` / `R.edit_thread`;
  they refuse when the text is not found exactly once. Fix such cases by hand
  rather than forcing them.
- Follow the paper's own conventions (its CLAUDE.md if it has one), rebuild it
  after a batch, and do not commit or push unless the user asks.

## Work per card goes to subagents

Hand the work on each card to its own subagent (Sonnet 5.5), all in parallel,
and only verify their results before applying them. This covers every `change`
entry and the proposal round below. Accept, reject, edit, resolve, keep and
reply are mechanical: apply them directly.

A subagent reads the paper (and the code or data it needs) but writes only a JSON
result to the scratchpad: `{"id", "changes": [{"old", "new"}], "reply",
"needs_check"}`. It never writes the `.tex` or the data directory, since parallel
writers race on those files. Claude checks each result (the `old` text occurs
once, numbers match the data), then applies it with `R.propose` and `R.reply`.

## Proposing in advance

When the user asks for proposals, give every open card without changes to a
subagent as above: what the comments ask for and a proposed edit, or "no change
needed" with the reason.
- Mark the cards first with `R.set_meta(id, drafting=True)`; the page shows
  "proposal coming".
- After applying a result, `R.set_meta(id, drafting=False, needs_check=...)`.
  Use `plot`, `experiment`, `data` or `code` when the user must check something
  outside the text; those cards are listed first.
- A card whose proposal is "no change" gets only the reply, and keeps Resolve /
  Keep.

## Developing

`python3 -m unittest discover -s tests` runs the tests. `examples/demo.tex` is a
small paper with every kind of thread; `python3 server.py --tex examples/demo.tex`
shows it (copy it somewhere first if you will click buttons, since the data
directory is created next to the `.tex`).
