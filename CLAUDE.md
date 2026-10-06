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

Each entry is `{id, sig, rev, line, decision, instruction, edits, macro, text, ts}`.
`id` is the thread id. Look the thread up with `R.thread(id)`; if the user edited
the first comment since, the id may no longer exist: find the thread by `line`
and tell the user.

| decision | what to do |
|---|---|
| `change` (Ask Claude) | Do what the instruction says. Edit the paper with `R.propose(id, old, new)` so the edit shows on the card as a change. If it is only a question, change nothing. Always answer with `R.reply(id, text)`, then `R.set_status(id, "review")` (red). |
| `accept` | The card's changes stay. `R.comment_out_thread(id)`, `R.set_status(id, "done")`. |
| `reject` | `R.reject_all(id)` puts the original text back. Then `R.comment_out_thread(id)` and `R.set_status(id, "done")`. |
| `edit` | `R.replace_change(id, k, edits[k])` for every change, then as for accept. |
| `reply` | `R.add_comment(id, macro, text)` adds the user's own comment under the thread. The thread now waits for the others, so skip it with its new signature: `R.set_status(id, "skip", sig=R.thread(id)["sig"])`. It comes back when someone answers. |
| `resolve` | `R.comment_out_thread(id)`, `R.set_status(id, "done")`. |

Skip and unskip never reach Claude: the server records them itself.

Rules:
- Every Claude answer goes through `R.reply`, so the card keeps the conversation.
- Edit the paper only through `R.propose` / `R.replace_change` for text the card
  shows as a change; they refuse when the text is not found exactly once. Fix such
  cases by hand rather than forcing them.
- Follow the paper's own conventions (its CLAUDE.md if it has one), rebuild it
  after a batch, and do not commit or push unless the user asks.

## Developing

`python3 -m unittest discover -s tests` runs the tests. `examples/demo.tex` is a
small paper with every kind of thread; `python3 server.py --tex examples/demo.tex`
shows it (copy it somewhere first if you will click buttons, since the data
directory is created next to the `.tex`).
