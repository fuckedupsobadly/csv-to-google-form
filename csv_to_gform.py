#!/usr/bin/env python3
"""csv-to-google-form: submit each row of a CSV file as a response to a Google Form.

Free, one file, no dependencies (Python 3.8+ standard library only).

    python3 csv_to_gform.py FORM_URL data.csv                     # dry run: checks everything, sends nothing
    python3 csv_to_gform.py FORM_URL data.csv --submit --limit 1  # send the first row, then check the form
    python3 csv_to_gform.py FORM_URL data.csv --submit            # send the rest

See README.md for the full guide.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

__version__ = "1.0.0"
USER_AGENT = f"csv-to-google-form/{__version__} (Python urllib)"

# Item type codes used inside Google's FB_PUBLIC_LOAD_DATA_ blob.
SHORT, PARAGRAPH, CHOICE, DROPDOWN, CHECKBOX, SCALE = 0, 1, 2, 3, 4, 5
INFO, GRID, SECTION, DATE, TIME, IMAGE, VIDEO, UPLOAD = 6, 7, 8, 9, 10, 11, 12, 13
RATING = 18
LAYOUT_ONLY = {INFO, SECTION, IMAGE, VIDEO}
TYPE_NAMES = {
    SHORT: "short answer", PARAGRAPH: "paragraph", CHOICE: "multiple choice",
    DROPDOWN: "dropdown", CHECKBOX: "checkboxes", SCALE: "linear scale", GRID: "grid row",
    DATE: "date", TIME: "time", UPLOAD: "file upload", RATING: "rating",
}

# Column headers skipped by default (Google Sheets exports start with a timestamp).
DEFAULT_SKIP = ["Timestamp", "Отметка времени", "Уақыт белгісі"]
EMAIL_HEADERS = ["Email", "Email Address", "E-mail", "Адрес электронной почты",
                 "Электронная почта", "Электрондық пошта", "Электрондық пошта мекенжайы"]

SEPARATORS = ";,\n"  # how several checkbox answers may be joined inside one cell
DATE_FORMATS = [
    "%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
    "%d.%m.%Y", "%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S", "%Y/%m/%d", "%Y/%m/%d %H:%M",
]


class FormError(Exception):
    """The form can't be read or can't be filled by this tool."""


@dataclass(eq=False)
class Question:
    title: str              # grid rows are titled "Grid title [Row label]", like Google Sheets exports
    kind: int
    entry: int
    choices: list = field(default_factory=list)
    has_other: bool = False
    required: bool = False
    page: int = 0
    has_time: bool = False  # date questions only
    has_year: bool = True   # date questions only

    @property
    def multi(self) -> bool:
        return self.kind in (CHECKBOX, GRID)


@dataclass
class Form:
    title: str
    form_id: str
    post_url: str
    fbzx: str | None
    page_count: int
    questions: list
    collects_email: bool


# ---------------------------------------------------------------- text matching

_FOLD = str.maketrans({"–": "-", "—": "-", "‒": "-", "−": "-", " ": " ", "’": "'", "‘": "'"})
_NUMBERING = re.compile(r"^\s*(?:q(?:uestion)?\s*)?\d+\s*[.):\-]\s*", re.I)


def fold(s: str) -> str:
    """Lower-case and unify dashes/quotes without changing the string's length."""
    s = s.translate(_FOLD)
    return "".join(c.lower() if len(c.lower()) == 1 else c for c in s)


def canon(s: str) -> str:
    return re.sub(r"\s+", " ", fold(s)).strip()


def norm_title(s: str) -> str:
    """'Q1. How old are you? *' and 'how old are you' compare equal."""
    s = _NUMBERING.sub("", canon(s))
    return s.rstrip(" *?:.!").strip()


def find_option(value: str, choices: list) -> str | None:
    """Return the form's exact label for value, tolerating case, dash and spacing differences."""
    if value in choices:
        return value
    c = canon(value)
    for ch in choices:
        if canon(ch) == c:
            return ch
    if re.fullmatch(r"-?\d+\.0+", value.strip()):  # spreadsheets turn 3 into 3.0
        return find_option(value.strip().split(".")[0], choices)
    return None


def split_multi(cell: str, choices: list, has_other: bool) -> tuple[list, str | None]:
    """Split a checkbox cell into the form's options, plus any 'Other' text.

    Matching is option-aware, so an option that itself contains a comma
    ("Yes, often") is not torn apart by the separator.
    """
    whole = find_option(cell, choices)
    if whole is not None:
        return [whole], None

    s = cell.strip()
    low = fold(s)
    folded = sorted(((fold(o), o) for o in choices if o), key=lambda p: len(p[0]), reverse=True)

    def skip_separators(i: int) -> int:
        while i < len(s) and (s[i] in SEPARATORS or s[i].isspace()):
            i += 1
        return i

    def option_at(i: int):
        for lo, label in folded:
            if low.startswith(lo, i):
                end = i + len(lo)
                rest = low[end:].lstrip(" ")
                if not rest or rest[0] in SEPARATORS:
                    return label, end
        return None

    picked, other, i = [], None, skip_separators(0)
    while i < len(s):
        hit = option_at(i)
        if hit:
            if hit[0] not in picked:
                picked.append(hit[0])
            i = skip_separators(hit[1])
            continue
        # Unknown text runs up to the next separator that is followed by a real option.
        end = next((k for k in range(i, len(s))
                    if s[k] in SEPARATORS and option_at(skip_separators(k))), len(s))
        chunk = s[i:end].strip(" " + SEPARATORS)
        if not has_other:
            raise ValueError(f"'{chunk}' is not one of the options")
        if other is not None:
            raise ValueError(f"only one 'Other' answer is allowed, found '{other}' and '{chunk}'")
        other, i = chunk, skip_separators(end)
    return picked, other


# ---------------------------------------------------------------- reading the form

def http(url: str, data: bytes | None = None) -> tuple[int, str, str]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, e.read().decode("utf-8", "replace")


def view_url(url: str) -> str:
    url = url.strip()
    if re.match(r"https?://forms\.gle/", url):
        url = http(url)[1]
    m = re.search(r"docs\.google\.com/forms/(?:u/\d+/)?d/(e/)?([\w-]+)", url)
    if not m:
        raise FormError("That doesn't look like a Google Form link. Use the link from Send -> link icon.")
    return f"https://docs.google.com/forms/d/{m.group(1) or ''}{m.group(2)}/viewform"


def _labels(ans: list) -> tuple[list, bool]:
    raw = ans[1] if len(ans) > 1 and ans[1] else []
    labels = [c[0] for c in raw if c and c[0]]
    has_other = any(len(c) > 4 and c[4] for c in raw)
    return labels, has_other


def parse_form(html: str, final_url: str) -> Form:
    m = re.search(r"FB_PUBLIC_LOAD_DATA_\s*=\s*(.*?);\s*</script>", html, re.S)
    if not m:
        raise FormError("Couldn't find the form's questions on the page. Is the link right and the form public?")
    data = json.loads(m.group(1))
    body = data[1]
    settings = body[10] if len(body) > 10 and body[10] else []

    questions, page = [], 0
    for item in body[1] or []:
        kind, title = item[3], (item[1] or "").strip()
        if kind == SECTION:
            page += 1
        if kind in LAYOUT_ONLY or len(item) < 5 or not item[4]:
            continue
        if kind == GRID:
            for ans in item[4]:
                row = ans[3][0] if len(ans) > 3 and ans[3] else ""
                labels, _ = _labels(ans)
                questions.append(Question(f"{title} [{row}]", kind, ans[0], labels,
                                          required=bool(ans[2]), page=page))
            continue
        ans = item[4][0]
        labels, has_other = _labels(ans)
        q = Question(title, kind, ans[0], labels, has_other, bool(len(ans) > 2 and ans[2]), page)
        if kind == DATE and len(ans) > 7 and ans[7]:
            q.has_time = bool(ans[7][0])
            q.has_year = bool(ans[7][1]) if len(ans[7]) > 1 else True
        questions.append(q)

    form_id = re.search(r"/forms/d/(?:e/)?([\w-]+)", final_url).group(1)
    fbzx = re.search(r'name="fbzx" value="(-?\d+)"', html)
    return Form(
        title=(body[8] if len(body) > 8 and body[8] else data[3] if len(data) > 3 else "") or "",
        form_id=form_id,
        post_url=final_url.split("?")[0].rsplit("/", 1)[0] + "/formResponse",
        fbzx=fbzx.group(1) if fbzx else None,
        page_count=page + 1,
        questions=questions,
        collects_email=len(settings) > 6 and settings[6] == 3,
    )


def load_form(url: str) -> Form:
    status, final_url, html = http(view_url(url))
    if "accounts.google.com" in final_url:
        raise FormError("This form requires a Google sign-in (Settings -> 'Limit to 1 response' or "
                        "'Collect verified emails'). Turn that off while importing, then turn it back on.")
    if "closedform" in final_url:
        raise FormError("This form is not accepting responses. Turn 'Accepting responses' on first.")
    if status != 200:
        raise FormError(f"Google returned HTTP {status} for the form link.")
    return parse_form(html, final_url)


# ---------------------------------------------------------------- reading the CSV

def detect_delimiter(text: str) -> str:
    """Pick the delimiter that gives the most, and consistent, columns (Excel in many locales uses ';')."""
    best, best_width = ",", 0
    for d in (",", ";", "\t"):
        try:
            rows = [r for r in csv.reader(io.StringIO(text[:65536]), delimiter=d) if r][:20]
        except csv.Error:
            continue
        if len(rows) > 1:
            rows = rows[:-1]  # the sample may cut the last line in half
        widths = {len(r) for r in rows}
        if len(widths) == 1 and min(widths) > best_width:
            best, best_width = d, min(widths)
    return best


def read_csv(path: str, encoding: str | None = None, delimiter: str | None = None):
    with open(path, "rb") as f:
        raw = f.read()
    if encoding:
        text = raw.decode(encoding)
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1251")
            print("Note: the file isn't UTF-8, read it as cp1251. If text looks wrong, pass --encoding.")
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter or detect_delimiter(text)))
    if not rows:
        raise FormError("The CSV file is empty.")
    return [h.strip() for h in rows[0]], rows[1:]


# ---------------------------------------------------------------- columns -> questions

def match_columns(header: list, questions: list, skip=(), by_order: bool = False):
    """Pair CSV columns with questions. Returns (pairs, positional, unmatched_cols, unmatched_questions).

    pairs maps column index -> Question. Columns are matched by title first; if the same number of
    columns and questions are left over, those are paired in order and listed in `positional`.
    """
    skip_keys = {norm_title(s) for s in skip}
    cols = [i for i, h in enumerate(header) if norm_title(h) not in skip_keys]
    pairs, positional = {}, set()

    if by_order:
        if len(cols) != len(questions):
            raise FormError(f"--by-order needs one column per question: the CSV has {len(cols)} "
                            f"columns (after skipping), the form has {len(questions)} questions.")
        return dict(zip(cols, questions)), set(cols), [], []

    free = list(questions)
    for i in cols:
        key = norm_title(header[i])
        q = next((q for q in free if norm_title(q.title) == key), None)
        if q is not None:
            pairs[i] = q
            free.remove(q)
    left = [i for i in cols if i not in pairs]
    if left and len(left) == len(free):
        for i, q in zip(left, free):
            pairs[i] = q
            positional.add(i)
        left, free = [], []
    return pairs, positional, left, free


# ---------------------------------------------------------------- cells -> form fields

def parse_date(value: str, fmt: str | None) -> dt.datetime:
    for f in [fmt] if fmt else DATE_FORMATS:
        try:
            return dt.datetime.strptime(value.strip(), f)
        except ValueError:
            pass
    hint = f"doesn't match --date-format {fmt}" if fmt else "use YYYY-MM-DD or DD.MM.YYYY, or pass --date-format"
    raise ValueError(f"can't read the date '{value}' ({hint})")


def parse_time(value: str) -> tuple[int, int, int | None]:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp]\.?[Mm]\.?)?", value.strip())
    if not m:
        raise ValueError(f"can't read the time '{value}' (use HH:MM)")
    hour, minute = int(m.group(1)), int(m.group(2))
    if m.group(4):
        hour = hour % 12 + (12 if m.group(4)[0] in "Pp" else 0)
    return hour, minute, int(m.group(3)) if m.group(3) else None


def cell_to_fields(value: str, q: Question, date_format: str | None = None) -> list:
    """Turn one CSV cell into (name, value) pairs for the POST. Raises ValueError if it doesn't fit."""
    key = f"entry.{q.entry}"
    value = value.strip()
    if not value:
        if q.required:
            raise ValueError("is empty, but the question is required")
        return []

    if q.kind in (SHORT, PARAGRAPH):
        return [(key, value)]
    if q.kind == UPLOAD:
        raise ValueError("file-upload questions can't be filled from a CSV")
    if q.kind == DATE:
        d = parse_date(value, date_format)
        out = ([(key + "_year", str(d.year))] if q.has_year else [])
        out += [(key + "_month", str(d.month)), (key + "_day", str(d.day))]
        if q.has_time:
            out += [(key + "_hour", f"{d.hour:02d}"), (key + "_minute", f"{d.minute:02d}")]
        return out
    if q.kind == TIME:
        h, m, s = parse_time(value)
        out = [(key + "_hour", f"{h:02d}"), (key + "_minute", f"{m:02d}")]
        return out + ([(key + "_second", f"{s:02d}")] if s is not None else [])

    if q.multi:
        picked, other = split_multi(value, q.choices, q.has_other)
    else:
        opt = find_option(value, q.choices)
        if opt is None and q.kind == RATING and not q.choices and value.isdigit():
            opt = value
        if opt is None and not q.has_other:
            shown = ", ".join(f"'{c}'" for c in q.choices[:8]) + (", ..." if len(q.choices) > 8 else "")
            raise ValueError(f"'{value}' is not one of the options ({shown})")
        picked, other = ([opt], None) if opt is not None else ([], value)

    out = [(key, p) for p in picked]
    if other is not None:
        out += [(key, "__other_option__"), (key + ".other_option_response", other)]
    return out


def row_to_payload(row: list, pairs: dict, email_col: int | None = None, date_format: str | None = None):
    """Returns (fields, pages_answered, errors) for one CSV row."""
    fields, pages, errors = [], {0}, []
    for i, q in pairs.items():
        cell = row[i] if i < len(row) else ""
        try:
            f = cell_to_fields(cell, q, date_format)
        except ValueError as e:
            errors.append(f"{q.title[:50]!r} {e}")
            continue
        fields += f
        if f:
            pages.add(q.page)
    if email_col is not None:
        email = row[email_col].strip() if email_col < len(row) else ""
        if not email:
            errors.append("email address is empty, but the form collects emails")
        fields.append(("emailAddress", email))
    return fields, pages, errors


# ---------------------------------------------------------------- sending

def submit(form: Form, fields: list, pages: set) -> int:
    """POST one response. Returns the HTTP status of the last attempt (200 = recorded)."""
    all_pages = ",".join(map(str, range(form.page_count)))
    visited = ",".join(map(str, sorted(pages)))
    extra = [("fvv", "1")] + ([("fbzx", form.fbzx)] if form.fbzx else [])
    status = 0
    # Linear forms want every page listed; forms with branching want only the pages visited.
    # A rejected attempt (400) records nothing, so trying the second history is safe.
    for history in dict.fromkeys([all_pages, visited]):
        body = urllib.parse.urlencode(fields + extra + [("pageHistory", history)]).encode()
        status = http(form.post_url, body)[0]
        if status != 400:
            break
    return status


def load_log(path: str, form_id: str) -> set:
    try:
        with open(path, encoding="utf-8") as f:
            return {int(n) for fid, n in (line.split() for line in f if line.strip()) if fid == form_id}
    except FileNotFoundError:
        return set()


def append_log(path: str, form_id: str, row_number: int) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{form_id}\t{row_number}\n")


# ---------------------------------------------------------------- command line

def find_column(header: list, names: list) -> int | None:
    keys = {norm_title(n) for n in names}
    return next((i for i, h in enumerate(header) if norm_title(h) in keys), None)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="csv_to_gform.py",
        description="Submit each row of a CSV file as a response to a Google Form. "
                    "Runs as a dry run unless you pass --submit.")
    ap.add_argument("form_url", help="the form's public link (docs.google.com/forms/... or forms.gle/...)")
    ap.add_argument("csv_file", help="CSV with a header row; one row = one response")
    ap.add_argument("--submit", action="store_true", help="actually send responses (default: dry run)")
    ap.add_argument("--limit", type=int, metavar="N", help="send at most N rows in this run")
    ap.add_argument("--delay", type=float, default=3.0, metavar="SEC",
                    help="seconds to wait between responses (default: 3)")
    ap.add_argument("--by-order", action="store_true",
                    help="pair columns with questions by position instead of by title")
    ap.add_argument("--skip", action="append", default=[], metavar="COLUMN",
                    help="ignore this column (repeatable); 'Timestamp' is always ignored")
    ap.add_argument("--email-column", metavar="COLUMN",
                    help="column with respondents' emails, for forms that ask for one")
    ap.add_argument("--date-format", metavar="FMT", help="how dates are written, e.g. %%d/%%m/%%Y")
    ap.add_argument("--delimiter", metavar="CHAR", help="CSV delimiter (default: detected)")
    ap.add_argument("--encoding", metavar="NAME", help="CSV encoding (default: UTF-8, then cp1251)")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    try:
        form = load_form(args.form_url)
        header, rows = read_csv(args.csv_file, args.encoding, args.delimiter)
    except (FormError, OSError, UnicodeDecodeError, urllib.error.URLError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Email column: used if the form asks for an email, otherwise ignored.
    email_col = (find_column(header, [args.email_column]) if args.email_column
                 else find_column(header, EMAIL_HEADERS))
    if args.email_column and email_col is None:
        print(f"Error: no column named {args.email_column!r}.", file=sys.stderr)
        return 2
    if form.collects_email and email_col is None:
        print("Error: this form asks for an email address. Add an email column or pass --email-column.",
              file=sys.stderr)
        return 2
    skip = DEFAULT_SKIP + args.skip + ([header[email_col]] if email_col is not None else [])
    if not form.collects_email:
        email_col = None

    try:
        pairs, positional, left_cols, left_qs = match_columns(header, form.questions, skip, args.by_order)
    except FormError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    print(f"Form: {form.title or form.form_id}  ({len(form.questions)} questions, {form.page_count} page(s))")
    print(f"CSV:  {args.csv_file}  ({len(header)} columns, {len(rows)} rows)\n")
    for i, q in sorted(pairs.items()):
        how = "by position, check this" if i in positional else "by title"
        print(f"  {header[i][:40]:40} -> {q.title[:40]:40} [{TYPE_NAMES.get(q.kind, q.kind)}, {how}]")

    problems = []
    if left_cols:
        problems.append("Columns with no matching question: " + ", ".join(repr(header[i]) for i in left_cols)
                        + "\n  Rename them to match the form, ignore them with --skip, or use --by-order.")
    required_left = [q for q in left_qs if q.required]
    if required_left:
        problems.append("Required questions with no column: " + ", ".join(repr(q.title) for q in required_left))
    if any(q.kind == UPLOAD and q.required for q in form.questions):
        problems.append("The form has a required file-upload question, which can't be filled from a CSV.")
    if problems:
        print("\n" + "\n".join(problems), file=sys.stderr)
        return 1
    optional_left = [q for q in left_qs if not q.required]
    if optional_left:
        print("\n  Left blank (optional, no column): " + ", ".join(repr(q.title[:40]) for q in optional_left))

    # Check every row before sending anything.
    payloads, errors = [], []
    for n, row in enumerate(rows, 1):
        if not any(c.strip() for c in row):
            continue
        if len(row) > len(header) and any(c.strip() for c in row[len(header):]):
            errors.append(f"row {n}: has more cells than the header")
            continue
        fields, pages, errs = row_to_payload(row, pairs, email_col, args.date_format)
        errors += [f"row {n}: {e}" for e in errs]
        payloads.append((n, fields, pages))
    if errors:
        print(f"\n{len(errors)} problem(s) found. Nothing was sent.\n", file=sys.stderr)
        print("\n".join("  " + e for e in errors[:40]), file=sys.stderr)
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more", file=sys.stderr)
        return 1
    print(f"\nAll {len(payloads)} rows fit the form.")

    if not args.submit:
        if payloads:
            n, fields, _ = payloads[0]
            print(f"\nRow {n} would be sent as:")
            names = {f"entry.{q.entry}": q.title for q in pairs.values()}
            for name, value in fields:
                base = name.split(".other_option_response")[0].split("_")[0]
                print(f"  {names.get(base, name)[:40]:40} = {value}")
        print("\nDry run: nothing was sent. Next: add --submit --limit 1, then check the form's Responses tab.")
        return 0

    log_path = args.csv_file + ".submitted"
    done = load_log(log_path, form.form_id)
    todo = [p for p in payloads if p[0] not in done]
    if args.limit is not None:
        todo = todo[:args.limit]
    if done:
        print(f"{len(done)} row(s) were already sent to this form earlier; skipping them.")
    if not todo:
        print("Nothing left to send.")
        return 0

    sent = 0
    for k, (n, fields, pages) in enumerate(todo):
        try:
            status = submit(form, fields, pages)
        except urllib.error.URLError as e:
            status = f"network error ({e.reason})"
        if status != 200:
            print(f"\nrow {n}: Google answered {status}. Stopped; {sent} sent in this run.", file=sys.stderr)
            if status == 400:
                print("  Google rejected the answers. Check the row against the form.", file=sys.stderr)
            elif status == 429:
                print("  Too many requests. Wait a while, then run the same command again.", file=sys.stderr)
            print("  Rows already sent are logged and will be skipped next time.", file=sys.stderr)
            return 1
        append_log(log_path, form.form_id, n)
        sent += 1
        print(f"row {n} sent ({len(done) + sent}/{len(payloads)})")
        if k < len(todo) - 1:
            time.sleep(args.delay)
    print(f"\nDone: {sent} sent in this run, {len(done) + sent}/{len(payloads)} in total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
