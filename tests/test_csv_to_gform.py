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

    def test_log_is_per_form(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.csv.submitted")
            g.append_log(p, "FORM_A", 1)
            g.append_log(p, "FORM_A", 2)
            g.append_log(p, "FORM_B", 7)
            self.assertEqual(g.load_log(p, "FORM_A"), {1, 2})
            self.assertEqual(g.load_log(p, "FORM_B"), {7})
            self.assertEqual(g.load_log(os.path.join(d, "none"), "FORM_A"), set())


if __name__ == "__main__":
    unittest.main()
