import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import review_lib as R  # noqa: E402
import scan  # noqa: E402
import server  # noqa: E402

PRE = ("\\documentclass{article}\n"
       "\\newcommand{\\alice}[1]{\\textcolor{blue}{[Alice: #1]}}\n"
       "\\newcommand{\\bob}[1]{\\textcolor{violet}{[Bob: #1]}}\n"
       "\\begin{document}\n")


class Lib(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.tex = os.path.join(self.dir, "main.tex")
        data = os.path.join(self.dir, ".review-cards")
        os.makedirs(data)
        with open(os.path.join(data, "config.json"), "w") as fh:
            json.dump({"tex": self.tex}, fh)
        R.configure(data)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def write(self, body):
        with open(self.tex, "w") as fh:
            fh.write(PRE + body + "\n\\end{document}\n")

    def body(self):
        return R.read_tex()[len(PRE):]

    def test_comment_out_whole_line_thread(self):
        self.write("Text.\n\\alice{a\nsecond line}\n\\bob{b}\nMore.")
        tid = R.threads()[0]["id"]
        self.assertEqual(R.comment_out_thread(tid), 2)
        self.assertIn("% \\alice{a\n% second line}\n% \\bob{b}\nMore.", self.body())
        t = R.thread(tid)
        self.assertFalse(t["open"])
        self.assertEqual(len(t["comments"]), 2)

    def test_comment_out_inline(self):
        self.write("Text \\alice{x} more text.")
        tid = R.threads()[0]["id"]
        R.comment_out_thread(tid)
        self.assertIn("Text more text.\n% \\alice{x}", self.body())
        self.assertFalse(R.thread(tid)["open"])

    def test_add_comment_joins_thread_and_changes_sig(self):
        self.write("Text.\n\\alice{why?}\nMore.")
        t0 = R.threads()[0]
        R.add_comment(t0["id"], "bob", "because")
        t1 = R.thread(t0["id"])
        self.assertEqual([c["macro"] for c in t1["comments"]], ["alice", "bob"])
        self.assertNotEqual(t0["sig"], t1["sig"])

    def test_propose_and_reject(self):
        self.write("The policy is trained for 50 epochs.\n\\alice{how chosen?}")
        tid = R.threads()[0]["id"]
        R.propose(tid, "for 50 epochs.", "for at most 50 epochs, with early stopping.")
        self.assertIn("at most 50 epochs", self.body())
        R.reject_all(tid)
        self.assertIn("trained for 50 epochs.", self.body())

    def test_propose_refuses_ambiguous_text(self):
        self.write("same.\nsame.\n\\alice{x}")
        with self.assertRaises(ValueError):
            R.propose(R.threads()[0]["id"], "same.", "other.")

    def test_skip_reopens_when_thread_changes(self):
        self.write("Text.\n\\alice{why?}\nMore.")
        t = R.threads()[0]
        rec = {"status": "skip", "sig": t["sig"]}
        self.assertEqual(server.effective(t, rec), "skip")
        R.add_comment(t["id"], "bob", "a new reply")
        self.assertEqual(server.effective(R.thread(t["id"]), rec), "reopened")

    def test_resolved_thread_is_done(self):
        self.write("% \\alice{old}")
        self.assertEqual(server.effective(R.threads()[0], {}), "done")

    def test_keep_is_done_until_thread_changes(self):
        self.write("Text.\n\\alice{why?}\nMore.")
        t = R.threads()[0]
        R.keep(t["id"])
        rec = R.state()["cards"][t["id"]]
        self.assertEqual(server.effective(t, rec), "done")
        R.add_comment(t["id"], "bob", "new point")
        self.assertEqual(server.effective(R.thread(t["id"]), rec), "reopened")

    def test_edit_thread_replaces_its_lines(self):
        self.write("Text.\n\\alice{why?}\n\\bob{because}\nMore.")
        tid = R.threads()[0]["id"]
        R.edit_thread(tid, "\\alice{why? (rephrased)}\n\\bob{because}")
        self.assertIn("Text.\n\\alice{why? (rephrased)}\n\\bob{because}\nMore.", self.body())

    def test_set_meta_badges(self):
        self.write("\\alice{x}")
        tid = R.threads()[0]["id"]
        R.set_meta(tid, needs_check="data", drafting=True)
        self.assertEqual(R.proposals()[tid]["needs_check"], "data")
        R.set_meta(tid, needs_check="", drafting=False)
        self.assertIsNone(R.proposals()[tid]["needs_check"])


if __name__ == "__main__":
    unittest.main()
