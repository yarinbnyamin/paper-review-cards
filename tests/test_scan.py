import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import scan  # noqa: E402

PRE = r"""\documentclass{article}
\newif\ifaddcomments\addcommentstrue
\newcommand{\commentout}[1]{ }
\newcommand{\bcens}{\textsc{BC-ens}\xspace}
\newcommand{\emphx}[1]{\textbf{#1}}
\newcommand{\todo}[1]{\ifaddcomments{\textcolor{red}{[TODO: #1]}}\fi}
\newcommand{\alice}[1]{\ifaddcomments{\textcolor{blue}{[Alice: #1]}}\fi}
\newcommand{\aliceextra}[1]{\ifaddcomments{\textcolor{brown}{[Alice, later: #1]}}\fi}
\newcommand{\bob}[1]{\textcolor{violet}{[Bob: #1]}}
\begin{document}
"""


def th(body):
    return scan.threads(PRE + body + "\n\\end{document}\n")


class Macros(unittest.TestCase):
    def test_detects_note_macros_only(self):
        ms = scan.find_macros(PRE)
        self.assertEqual(set(ms), {"todo", "alice", "aliceextra", "bob"})
        self.assertEqual(ms["alice"], {"label": "Alice", "color": "blue"})
        self.assertEqual(ms["aliceextra"]["label"], "Alice, later")
        self.assertEqual(ms["bob"]["color"], "violet")


class Comments(unittest.TestCase):
    def test_prefix_macro_not_confused(self):
        t = th(r"Text.\aliceextra{later} and \alice{now}.")
        names = [c["macro"] for x in t for c in x["comments"]]
        self.assertEqual(sorted(names), ["alice", "aliceextra"])

    def test_multiline_and_nested_braces(self):
        t = th("A sentence.\n\\alice{one {nested} brace,\nsecond line with $x_{1}$ and 50\\% done}\nNext.")
        self.assertEqual(len(t), 1)
        c = t[0]["comments"][0]
        self.assertEqual((c["line"], c["end_line"]), (12, 13))
        self.assertIn("50\\% done", c["text"])

    def test_commented_comment_found_and_resolved(self):
        t = th("Text.\n% \\alice{old note\n% over two lines}\nMore text.")
        self.assertEqual(len(t), 1)
        self.assertFalse(t[0]["open"])
        self.assertFalse(t[0]["comments"][0]["live"])

    def test_inline_comment_after_text(self):
        t = th(r"Text. % \bob{an aside}")
        self.assertEqual(t[0]["comments"][0]["macro"], "bob")
        self.assertFalse(t[0]["open"])

    def test_preamble_not_scanned(self):
        self.assertEqual(th("No comments here."), [])


class Threads(unittest.TestCase):
    def test_adjacent_comments_form_one_thread(self):
        t = th("Para.\n\\alice{question}\n\\bob{answer}\n% \\alice{follow-up}\n\nNext para.")
        self.assertEqual(len(t), 1)
        self.assertEqual([c["macro"] for c in t[0]["comments"]], ["alice", "bob", "alice"])
        self.assertTrue(t[0]["open"])

    def test_text_between_splits_threads(self):
        t = th("\\alice{one}\nA sentence.\n\\bob{two}")
        self.assertEqual(len(t), 2)

    def test_same_line_neighbours_join(self):
        t = th(r"Text \alice{a} \bob{b} more.")
        self.assertEqual(len(t), 1)

    def test_id_stable_and_sig_changes_on_reply(self):
        a = th("Intro.\n\\alice{why?}\nEnd.")
        b = th("Intro text changed.\n\\alice{why?}\n\\bob{because}\nEnd.")
        self.assertEqual(a[0]["id"], b[0]["id"])
        self.assertNotEqual(a[0]["sig"], b[0]["sig"])

    def test_sig_ignores_commenting_out(self):
        a = th("\\alice{fix this}")
        b = th("% \\alice{fix this}")
        self.assertEqual((a[0]["id"], a[0]["sig"]), (b[0]["id"], b[0]["sig"]))

    def test_duplicate_first_comment_gets_distinct_ids(self):
        t = th("\\todo{check}\nText.\n\\todo{check}")
        self.assertEqual(len({x["id"] for x in t}), 2)

    def test_section_and_context(self):
        t = th("\\section{Results}\n\\subsection{Main}\nLine a.\n\\alice{hm}\nLine b.")
        self.assertEqual(t[0]["section"], "Results / Main")
        self.assertEqual(t[0]["before"][-1], "Line a.")
        self.assertEqual(t[0]["after"][0], "Line b.")


if __name__ == "__main__":
    unittest.main()
