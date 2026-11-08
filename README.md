# csv-to-google-form

Submit every row of a CSV file as a response to a Google Form. Free, one Python file, nothing to install.

Google Forms has no "import responses" button. If you collected answers on paper, in interviews, or in another survey tool and want them in the same form as your online responses (so they appear in the Summary charts and the linked Sheet), you have to type them in by hand or pay for an add-on. This script does it for free: it reads your form, checks every row of your CSV against it, and then sends the rows one by one.

```
$ python3 csv_to_gform.py https://forms.gle/AbCdEf123 survey.csv

Form: Cafe survey  (6 questions, 2 page(s))
CSV:  survey.csv  (7 columns, 120 rows)

  1. Name                    -> Name                    [short answer, by title]
  2. Age group               -> Age group               [multiple choice, by title]
  3. Fruits you like         -> Fruits you like         [checkboxes, by title]
  ...

All 120 rows fit the form.
Dry run: nothing was sent. Next: add --submit --limit 1, then check the form's Responses tab.
```

## Features

- **Works with any form and any CSV.** Columns are matched to questions by title (numbering like `Q1.` or `3)`, capital letters, `*` and `?` are ignored), or by position if you prefer.
- **Checks everything before sending anything.** If one cell in row 87 doesn't match the form, you find out before row 1 is sent.
- **Never sends a row twice.** Sent rows are logged; if a run stops halfway, run the same command again and it continues where it stopped.
- **Handles the awkward cases:** checkbox cells with several answers, options that contain commas, "Other" answers, `18-24` vs `18–24`, `4.0` from spreadsheets, semicolon-separated CSVs from Excel, non-UTF-8 files, multi-section forms, Google Sheets exports (the Timestamp column is skipped).
- **Every question type that can hold an answer:** short answer, paragraph, multiple choice, checkboxes, dropdown, linear scale, star rating, multiple-choice grid, checkbox grid, date, date + time, time and duration. All of them have been tested end to end on a live Google Form.
- **No dependencies.** Python 3.9+ standard library only. No API keys, no Google account login.

## Requirements

- Python 3.9 or newer (`python3 --version`).
- A Google Form that anyone with the link can fill in. The script can't fill forms that require signing in (see [Limitations](#limitations)).

## Quick start

**1. Download the script**

```bash
git clone https://github.com/fuckedupsobadly/csv-to-google-form.git
cd csv-to-google-form
```

Or download only [`csv_to_gform.py`](csv_to_gform.py); it is the whole tool.

**2. Get the form's link.** In the form editor, click **Send**, then the link icon, and copy it. Short `forms.gle/...` links work.

**3. Do a dry run.** It reads the form, matches your columns, checks every row, and shows how row 1 will be sent. Nothing is submitted.

```bash
python3 csv_to_gform.py "https://forms.gle/YOUR_FORM" responses.csv
```

**4. Send one row,** then open the form's **Responses** tab and check that it looks right.

```bash
python3 csv_to_gform.py "https://forms.gle/YOUR_FORM" responses.csv --submit --limit 1
```

**5. Send the rest.** Row 1 is already logged, so it won't be sent again.

```bash
python3 csv_to_gform.py "https://forms.gle/YOUR_FORM" responses.csv --submit
```

## Preparing your CSV

One header row, then one row per response. Export from Excel, Google Sheets or LibreOffice with **File → Save as / Download → CSV**.

**Headers.** Use the question titles from the form. Small differences are fine: `Q1. How old are you?` matches `How old are you`. If your headers are something else entirely (`q1`, `age`...) but the columns are in the same order as the questions, add `--by-order`. A `Timestamp` column is ignored automatically; ignore any other column with `--skip "Column name"`.

**Cells.** Write answers exactly as the options appear in the form. Capital letters, extra spaces and dash types don't matter.

| Question type | What to put in the cell | Example |
|---|---|---|
| Short answer, paragraph | Any text | `Great service` |
| Multiple choice, dropdown | One option | `25–34` |
| Checkboxes | Options separated by `;` or `,` | `Apples; Pears` |
| "Other" option | The text itself; anything that isn't an option becomes the "Other" answer | `Apples, mango` |
| Linear scale, rating | The number | `4` |
| Date | `YYYY-MM-DD` or `DD.MM.YYYY` (other formats: `--date-format`). If the question has no year, the year is ignored | `2026-05-03` |
| Date + time | The date, a space, then the time | `2026-05-03 14:30` |
| Time | `HH:MM`, 24-hour or with AM/PM | `14:30`, `2:30 PM` |
| Duration | `H:MM` or `H:MM:SS` | `1:15:00` |
| Grid | One column per row of the grid, titled `Question [Row]` (how Google Sheets exports grids). For a checkbox grid, separate several answers with `,` or `;` | column `Rate us [Food]`, cell `Good` |
| Optional question | Leave the cell empty to skip it | |

Options that contain a comma (`Yes, often`) are fine in checkbox cells: the script matches the form's real options instead of blindly splitting on commas.

A small example is in [`example/survey.csv`](example/survey.csv).

## Options

| Option | What it does |
|---|---|
| `--submit` | Actually send responses. Without it, the script only checks (dry run). |
| `--limit N` | Send at most N rows in this run. Use `--limit 1` for a test. |
| `--delay SEC` | Seconds to wait between responses (default 3). |
| `--by-order` | Pair the 1st column with the 1st question, the 2nd with the 2nd, and so on, ignoring titles. |
| `--skip COLUMN` | Ignore a column. Repeat for several. |
| `--email-column COLUMN` | For forms that ask respondents to type their email: which column has it. Detected automatically if the header is `Email` or `Email Address`. |
| `--date-format FMT` | How dates are written, in Python [strftime codes](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes), e.g. `%d/%m/%Y` or `%m/%d/%Y`. Needed for slash dates, which are ambiguous. |
| `--delimiter CHAR` | CSV separator. Detected automatically (comma, semicolon or tab). |
| `--encoding NAME` | File encoding. Default: UTF-8, falling back to cp1251 (Cyrillic Excel). |

## How it works

A Google Form is a web page that sends answers to `.../formResponse` as fields named `entry.<number>`. The script downloads the form page, reads the questions, options and entry numbers from the data Google embeds in it (`FB_PUBLIC_LOAD_DATA_`), and converts each CSV row into those fields. It then sends them the same way a browser does when someone presses Submit. Google records each one as a normal response, so they show up in the Summary, Individual view and linked Sheet.

Rows that were accepted are written to `<your csv>.submitted` (one line per row, with the form's ID). Keep that file until you're done; delete it only if you deliberately want to send the same rows again.

## Limitations

- **Forms that require a Google sign-in can't be filled.** That includes "Limit to 1 response" and "Collect email addresses: Verified". Turn those settings off while importing, then turn them back on.
- **File-upload questions** can't be filled. If one is required, the form can't be used.
- **Timestamps are the time of import.** Google stamps each response when it arrives; there is no way to set an earlier date. If dates matter, keep them in a question of their own.
- **Each row is sent as-is.** The script doesn't follow "go to section based on answer" logic for you; it sends the answers that are in the row. For forms with branching, leave the cells of skipped sections empty.
- **Answer rules aren't checked in advance.** If a question has response validation ("number between 1 and 10", "must be an email"), a cell that breaks the rule is only caught when Google rejects that row.
- **Google can change its forms.** The script relies on the structure of Google's form page, which isn't an official API. If it stops working, please open an issue. This is also why you should always send one test row first.

## Use it honestly

This tool is for entering **real responses into your own forms**: answers collected on paper, by phone, at an event, or in another tool. Don't use it to submit made-up answers, inflate a survey, or flood someone else's form; that is fraud, and in research it's misconduct.

If the responses are part of a study, say in your methods how they were collected and that they were entered with a script. That's also why the timestamps will all be from the day you imported them.

## Troubleshooting

| Message | What to do |
|---|---|
| `This form requires a Google sign-in` | See [Limitations](#limitations): turn off "Limit to 1 response" and verified email collection while importing. |
| `Columns with no matching question` | Rename the header to the question's title, ignore the column with `--skip`, or use `--by-order`. |
| `'...' is not one of the options` | The cell's text differs from the form's option. Fix the cell, or edit the option in the form. |
| `can't read the date` | Use `YYYY-MM-DD`, or pass `--date-format` (e.g. `%d/%m/%Y`). |
| `Google answered 400` | Google rejected that row. Usually a required question is empty or an answer doesn't fit (e.g. text in a number-validated field). |
| `Google answered 429` | Too many responses too quickly. Wait a few minutes and rerun the same command; use a bigger `--delay`. |
| Text looks garbled | The file's encoding wasn't detected. Try `--encoding cp1251`, `--encoding utf-16` or re-save the file as "CSV UTF-8". |

## Running the tests

```bash
python3 -m unittest discover -s tests
```

The tests use a mock form and need no internet connection.

## License

[MIT](LICENSE). Free to use, change and share.
