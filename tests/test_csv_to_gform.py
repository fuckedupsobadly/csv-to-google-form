"""Offline tests: run with `python3 -m unittest` from the repository root."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import csv_to_gform as g  # noqa: E402


def item(qid, title, kind, answers):
    return [qid, title, None, kind, answers]


def opts(*labels, other=False):
    out = [[label] for label in labels]
    if other:
        out.append(["", None, None, None, 1])
    return out


# A small form in the same shape Google serves: 2 pages, every supported question type.
ITEMS = [
    item(1, "Name", g.SHORT, [[1001, None, 1]]),
    item(2, "Age group", g.CHOICE, [[1002, opts("18–24", "25–34", "35+"), 1]]),
    item(3, "Fruits you like", g.CHECKBOX, [[1003, opts("Apples", "Red, dark grapes", "Pears", other=True), 0]]),
    item(4, "Section two", g.SECTION, None),
    item(5, "Satisfaction", g.SCALE, [[1005, opts("1", "2", "3", "4", "5"), 1]]),
    item(6, "Visit date", g.DATE, [[1006, None, 0, None, None, None, None, [0, 1]]]),
    item(7, "Visit time", g.TIME, [[1007, None, 0]]),
    item(8, "Rate us", g.GRID, [[1008, opts("Bad", "OK", "Good"), 0, ["Food"]],
                                [1009, opts("Bad", "OK", "Good"), 0, ["Staff"]]]),
    item(9, "Comments", g.PARAGRAPH, [[1010, None, 0]]),
]
DATA = [None, [None, ITEMS, None, None, None, None, None, None, "Cafe survey", None,
               [None, None, None, 2, None, None, 1]], "/forms", "Cafe survey"]
HTML = ("<html><script>var FB_PUBLIC_LOAD_DATA_ = " + json.dumps(DATA) + ";</script>"
        '<input type="hidden" name="fbzx" value="-123456789"></html>')
URL = "https://docs.google.com/forms/d/e/FORMID123/viewform?usp=send_form"


class ParseForm(unittest.TestCase):
    def setUp(self):
        self.form = g.parse_form(HTML, URL)
        self.q = {q.title: q for q in self.form.questions}

    def test_basics(self):
        self.assertEqual(self.form.form_id, "FORMID123")
        self.assertEqual(self.form.post_url, "https://docs.google.com/forms/d/e/FORMID123/formResponse")
        self.assertEqual(self.form.fbzx, "-123456789")
        self.assertEqual(self.form.page_count, 2)
        self.assertFalse(self.form.collects_email)

    def test_questions(self):
        self.assertEqual(len(self.form.questions), 9)  # 8 questions; section dropped, grid split into 2 rows
        self.assertTrue(self.q["Fruits you like"].has_other)
        self.assertEqual(self.q["Fruits you like"].choices, ["Apples", "Red, dark grapes", "Pears"])
        self.assertEqual(self.q["Satisfaction"].page, 1)
        self.assertIn("Rate us [Food]", self.q)
        self.assertEqual(self.q["Rate us [Staff]"].entry, 1009)
        self.assertTrue(self.q["Visit date"].has_year)
        self.assertFalse(self.q["Visit date"].has_time)


class Matching(unittest.TestCase):
    def test_norm_title(self):
        self.assertEqual(g.norm_title("Q1. Жасыңыз?"), g.norm_title("Жасыңыз?"))
        self.assertEqual(g.norm_title("3) Your name *"), g.norm_title("your name"))
        self.assertEqual(g.norm_title("12 - Age"), "age")

    def test_find_option(self):
        choices = ["18–24", "Yes", "3"]
        self.assertEqual(g.find_option("18-24", choices), "18–24")  # hyphen vs en dash
        self.assertEqual(g.find_option(" yes ", choices), "Yes")
        self.assertEqual(g.find_option("3.0", choices), "3")
        self.assertIsNone(g.find_option("No", choices))

    def test_split_multi(self):
        c = ["Apples", "Red, dark grapes", "Pears"]
        self.assertEqual(g.split_multi("Apples; Pears", c, False), (["Apples", "Pears"], None))
        self.assertEqual(g.split_multi("Red, dark grapes, Apples", c, False), (["Red, dark grapes", "Apples"], None))
        self.assertEqual(g.split_multi("apples,pears", c, False), (["Apples", "Pears"], None))
        self.assertEqual(g.split_multi("Pears, mango, kiwi", c, True), (["Pears"], "mango, kiwi"))
        self.assertEqual(g.split_multi("Apples, mango; Pears", c, True), (["Apples", "Pears"], "mango"))
        with self.assertRaises(ValueError):
            g.split_multi("Apples, mango", c, False)

    def test_match_columns(self):
        form = g.parse_form(HTML, URL)
        header = ["Timestamp", "1. Name", "Age group?", "Fruits you like", "Satisfaction", "Visit date",
                  "Visit time", "Rate us [Food]", "Rate us [Staff]", "Notes"]
        pairs, positional, left_cols, left_qs = g.match_columns(header, form.questions, g.DEFAULT_SKIP)
        self.assertNotIn(0, pairs)                       # timestamp skipped
        self.assertEqual(pairs[1].title, "Name")
        self.assertEqual(pairs[9].title, "Comments")     # the one leftover pair, by position
        self.assertEqual(positional, {9})
        self.assertEqual((left_cols, left_qs), ([], []))


class Cells(unittest.TestCase):
    def setUp(self):
        self.q = {q.title: q for q in g.parse_form(HTML, URL).questions}

    def test_choice_and_other(self):
        self.assertEqual(g.cell_to_fields("35+", self.q["Age group"]), [("entry.1002", "35+")])
        with self.assertRaises(ValueError):
            g.cell_to_fields("70+", self.q["Age group"])
        self.assertEqual(g.cell_to_fields("Apples, mango", self.q["Fruits you like"]),
                         [("entry.1003", "Apples"), ("entry.1003", "__other_option__"),
                          ("entry.1003.other_option_response", "mango")])

    def test_required_and_optional_blank(self):
        with self.assertRaises(ValueError):
            g.cell_to_fields("", self.q["Name"])
        self.assertEqual(g.cell_to_fields("", self.q["Comments"]), [])

    def test_date_and_time(self):
        self.assertEqual(g.cell_to_fields("03.05.2026", self.q["Visit date"]),
                         [("entry.1006_year", "2026"), ("entry.1006_month", "5"), ("entry.1006_day", "3")])
        self.assertEqual(g.cell_to_fields("5/3/2026", self.q["Visit date"], "%m/%d/%Y")[1],
                         ("entry.1006_month", "5"))
        with self.assertRaises(ValueError):
            g.cell_to_fields("5/3/2026", self.q["Visit date"])  # ambiguous without --date-format
        self.assertEqual(g.cell_to_fields("2:05 PM", self.q["Visit time"]),
                         [("entry.1007_hour", "14"), ("entry.1007_minute", "05")])
        duration = g.Question("Time spent", g.TIME, 1011, duration=True)
        self.assertEqual(g.cell_to_fields("0:45", duration),
                         [("entry.1011_hour", "00"), ("entry.1011_minute", "45"), ("entry.1011_second", "00")])

    def test_scale_from_spreadsheet(self):
        self.assertEqual(g.cell_to_fields("4.0", self.q["Satisfaction"]), [("entry.1005", "4")])


class CsvAndLog(unittest.TestCase):
    def test_semicolon_csv_with_commas_inside(self):
        text = 'Name;Fruits\nAida;"Apples, Pears"\nBek;Pears\n'
        self.assertEqual(g.detect_delimiter(text), ";")
        self.assertEqual(g.detect_delimiter('a,b\n"x;y",z\n1,2\n'), ",")

    def test_read_csv_bom_and_cp1251(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.csv")
            with open(p, "wb") as f:
                f.write("Имя,Возраст\nАйгерим,20\n".encode("cp1251"))
            header, rows = g.read_csv(p)
            self.assertEqual(header, ["Имя", "Возраст"])
            self.assertEqual(rows, [["Айгерим", "20"]])

    def test_log_is_per_form_and_remembers_content(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.csv.submitted")
            g.append_log(p, "FORM_A", 1, "aaa")
            g.append_log(p, "FORM_A", 2, "bbb")
            g.append_log(p, "FORM_B", 7, "ccc")
            with open(p, "a") as f:
                f.write("FORM_A\t3\n")  # line written by version 1.0 (no content hash)
            self.assertEqual(g.load_log(p, "FORM_A"), {1: "aaa", 2: "bbb", 3: None})
            self.assertEqual(g.load_log(p, "FORM_B"), {7: "ccc"})
            self.assertEqual(g.load_log(os.path.join(d, "none"), "FORM_A"), {})

    def test_row_key_ignores_surrounding_spaces_only(self):
        self.assertEqual(g.row_key(["a ", " b"]), g.row_key(["a", "b"]))
        self.assertNotEqual(g.row_key(["a", "b"]), g.row_key(["a", "c"]))


class SingleAnswerQuestions(unittest.TestCase):
    def setUp(self):
        self.age = g.Question("Age", g.CHOICE, 1, ["18–24", "25–34", "35+"], required=True)
        self.color = g.Question("Colour", g.CHOICE, 2, ["Red", "Blue"], has_other=True)

    def test_several_answers_in_a_single_choice_question_is_a_clear_error(self):
        with self.assertRaises(ValueError) as cm:
            g.cell_to_fields("18–24; 35+", self.age)
        self.assertIn("only one", str(cm.exception))
        self.assertIn("Checkboxes", str(cm.exception))

    def test_several_answers_are_not_silently_turned_into_other_text(self):
        with self.assertRaises(ValueError):
            g.cell_to_fields("Red; Blue", self.color)
        self.assertEqual(g.cell_to_fields("Purple", self.color),
                         [("entry.2", "__other_option__"), ("entry.2.other_option_response", "Purple")])


class SkippedSections(unittest.TestCase):
    def setUp(self):
        self.name = g.Question("Name", g.SHORT, 1, required=True, page=0)
        self.sat = g.Question("Satisfaction", g.SCALE, 2, ["1", "2", "3"], required=True, page=1)
        self.why = g.Question("Why", g.SHORT, 3, page=1)
        self.pairs = {0: self.name, 1: self.sat, 2: self.why}

    def test_a_wholly_empty_later_section_counts_as_skipped(self):
        fields, pages, errors = g.row_to_payload(["Aida", "", ""], self.pairs)
        self.assertEqual((errors, pages), ([], {0}))

    def test_a_partly_filled_section_still_needs_its_required_answers(self):
        fields, pages, errors = g.row_to_payload(["Aida", "", "because"], self.pairs)
        self.assertEqual([title for title, _ in errors], ["Satisfaction"])

    def test_the_first_section_is_always_required(self):
        fields, pages, errors = g.row_to_payload(["", "2", ""], self.pairs)
        self.assertEqual([title for title, _ in errors], ["Name"])


class ErrorReport(unittest.TestCase):
    def test_rows_are_compressed_into_ranges(self):
        self.assertEqual(g.compress_rows([1, 2, 3, 5, 7, 8]), "1-3, 5, 7-8")

    def test_problems_are_grouped_by_column(self):
        errors = [(n, "Q4", f"bad value {n}") for n in (5, 6, 7, 9)] + [(2, "Q1", "is empty")]
        text = "\n".join(g.format_problems(errors))
        self.assertIn("Q4: 4 rows (5-7, 9)", text)
        self.assertIn("Q1: 1 row (2)", text)
        self.assertEqual(text.count("bad value"), 3)  # at most 3 examples per column


class Throttling(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(g.classify(200, "https://docs.google.com/forms/d/e/X/formResponse", "ok"), "ok")
        self.assertEqual(g.classify(429, "https://docs.google.com/forms/d/e/X/formResponse", ""), "limited")
        self.assertEqual(g.classify(503, "u", ""), "limited")
        self.assertEqual(g.classify(200, "https://www.google.com/sorry/index?continue=x", ""), "limited")
        self.assertEqual(g.classify(200, "u", "<div class='g-recaptcha'>"), "limited")
        self.assertEqual(g.classify(500, "u", ""), "server")
        self.assertEqual(g.classify(400, "u", ""), "rejected")
        self.assertEqual(g.classify(404, "u", ""), "rejected")


class FakeGoogle:
    """Stands in for g.http: serves the mock form and records every POST."""

    def __init__(self, html=HTML, post_statuses=None, fail_on_post=None):
        self.html, self.posts = html, []
        self.post_statuses = list(post_statuses or [])
        self.fail_on_post = fail_on_post  # raise a network error on this POST number (1-based)

    def __call__(self, url, data=None):
        if data is None:
            return 200, URL, self.html
        self.posts.append(dict(p.split("=", 1) for p in data.decode().split("&")))
        if self.fail_on_post == len(self.posts):
            raise OSError("connection reset")
        status = self.post_statuses.pop(0) if self.post_statuses else 200
        if isinstance(status, tuple):  # (status, final_url) to simulate a redirect
            return status[0], status[1], ""
        return status, url, ""


class EndToEnd(unittest.TestCase):
    """Runs main() for real against FakeGoogle; nothing touches the network."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.csv = os.path.join(self.dir.name, "survey.csv")
        example = os.path.join(os.path.dirname(__file__), "..", "example", "survey.csv")
        with open(example, encoding="utf-8") as src, open(self.csv, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        self.real_http, self.real_sleep = g.http, g.time.sleep
        self.slept = []
        g.time.sleep = self.slept.append

    def tearDown(self):
        g.http, g.time.sleep = self.real_http, self.real_sleep
        self.dir.cleanup()

    def run_main(self, fake, *args):
        g.http = fake
        with open(os.devnull, "w") as null:
            out, err = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = null
            try:
                return g.main([URL, self.csv, *args])
            finally:
                sys.stdout, sys.stderr = out, err

    def test_dry_run_sends_nothing(self):
        fake = FakeGoogle()
        self.assertEqual(self.run_main(fake), 0)
        self.assertEqual(fake.posts, [])

    def test_submit_then_resume(self):
        fake = FakeGoogle()
        self.assertEqual(self.run_main(fake, "--submit", "--limit", "1"), 0)
        self.assertEqual(len(fake.posts), 1)
        first = fake.posts[0]
        self.assertEqual(first["entry.1001"], "Aida")
        self.assertEqual(first["pageHistory"], "0%2C1")
        self.assertEqual(first["fbzx"], "-123456789")

        fake2 = FakeGoogle()
        self.assertEqual(self.run_main(fake2, "--submit"), 0)
        self.assertEqual([p["entry.1001"] for p in fake2.posts], ["Bekzat", "Dana", "Erlan"])
        self.assertEqual(self.run_main(FakeGoogle(), "--submit"), 0)  # nothing left, nothing sent

    def test_network_error_does_not_log_the_row(self):
        fake = FakeGoogle(fail_on_post=2)
        self.assertEqual(self.run_main(fake, "--submit"), 1)
        self.assertEqual(set(g.load_log(self.csv + ".submitted", "FORMID123")), {1})

    def test_rejected_row_stops_the_run(self):
        fake = FakeGoogle(post_statuses=[200, 400, 400])
        self.assertEqual(self.run_main(fake, "--submit"), 1)
        self.assertEqual(set(g.load_log(self.csv + ".submitted", "FORMID123")), {1})

    def test_throttling_waits_and_retries_instead_of_stopping(self):
        sorry = (429, "https://www.google.com/sorry/index?continue=x")
        fake = FakeGoogle(post_statuses=[200, 429, sorry, 200, 200, 200])
        self.assertEqual(self.run_main(fake, "--submit"), 0)
        self.assertEqual([p["entry.1001"] for p in fake.posts],
                         ["Aida", "Bekzat", "Bekzat", "Bekzat", "Dana", "Erlan"])
        self.assertEqual(set(g.load_log(self.csv + ".submitted", "FORMID123")), {1, 2, 3, 4})
        self.assertEqual(self.slept[1:3], [60, 120])           # backoff waits before each retry
        self.assertTrue(all(s >= 10 for s in self.slept[3:]))   # and slower pacing afterwards

    def test_throttling_gives_up_after_max_wait(self):
        fake = FakeGoogle(post_statuses=[200] + [429] * 50)
        self.assertEqual(self.run_main(fake, "--submit", "--max-wait", "5"), 1)
        self.assertEqual(set(g.load_log(self.csv + ".submitted", "FORMID123")), {1})
        self.assertLessEqual(sum(self.slept), 5 * 60 + 10)

    def test_changed_csv_is_not_resumed_blindly(self):
        self.assertEqual(self.run_main(FakeGoogle(), "--submit", "--limit", "2"), 0)
        with open(self.csv, encoding="utf-8") as f:
            text = f.read()
        with open(self.csv, "w", encoding="utf-8") as f:
            f.write(text.replace("Bekzat", "Bolat"))  # row 2 changed after it was sent
        fake = FakeGoogle()
        self.assertEqual(self.run_main(fake, "--submit"), 1)
        self.assertEqual(fake.posts, [])
        fake = FakeGoogle()
        self.assertEqual(self.run_main(fake, "--submit", "--restart"), 0)  # new data set: start over
        self.assertEqual(len(fake.posts), 4)

    def test_template_matches_the_form(self):
        out = os.path.join(self.dir.name, "template.csv")
        g.http = FakeGoogle()
        with open(os.devnull, "w") as null:
            stdout, sys.stdout = sys.stdout, null
            try:
                self.assertEqual(g.main([URL, "--template", out]), 0)
            finally:
                sys.stdout = stdout
        with open(out, "rb") as f:
            self.assertTrue(f.read().startswith(b"\xef\xbb\xbf"))  # BOM, so Excel shows Cyrillic correctly
        header, rows = g.read_csv(out)
        form = g.parse_form(HTML, URL)
        pairs, positional, left_cols, left_qs = g.match_columns(header, form.questions)
        self.assertEqual((len(pairs), positional, left_cols, left_qs), (9, set(), [], []))
        self.assertTrue(os.path.exists(out + ".guide.txt"))

    def test_bad_cell_blocks_everything(self):
        with open(self.csv, "a", encoding="utf-8") as f:
            f.write("2026-05-05,Zara,70+,Apples,5,2026-05-05,10:00,Good,Good,\n")
        fake = FakeGoogle()
        self.assertEqual(self.run_main(fake, "--submit"), 1)
        self.assertEqual(fake.posts, [])

    def test_branching_form_retries_with_visited_pages(self):
        form = g.parse_form(HTML, URL)
        g.http = fake = FakeGoogle(post_statuses=[400, 200])
        self.assertEqual(g.submit(form, [("entry.1001", "A")], {0})[0], 200)
        self.assertEqual([p["pageHistory"] for p in fake.posts], ["0%2C1", "0"])

    def test_unreadable_form_is_a_clean_error(self):
        broken = HTML.replace(json.dumps(DATA), "[null, 5]")
        self.assertEqual(self.run_main(FakeGoogle(html=broken)), 2)

    def test_utf16_csv(self):
        with open(self.csv, "w", encoding="utf-16") as f:
            f.write("Name,Age group\nAida,18-24\n")
        self.assertEqual(g.read_csv(self.csv), (["Name", "Age group"], [["Aida", "18-24"]]))


if __name__ == "__main__":
    unittest.main()
