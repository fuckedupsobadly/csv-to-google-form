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
- **Writes the CSV template for you.** `--template` creates an empty CSV whose columns match your form, plus a guide listing exactly what each column accepts.
- **Waits out Google's limits instead of quitting.** When Google starts refusing submissions because too many arrived too fast, the script pauses (1, 2, 5, 10, 15 minutes...), retries the same row, and slows down for the rest of the run.
- **Never sends a row twice.** Sent rows are logged with a fingerprint of their content. If a run stops halfway, run the same command again and it continues where it stopped. If the CSV was edited in between, it stops and asks instead of guessing.
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

**3. Make a CSV that fits the form.** The easiest way is a template made from your form. It writes `responses.csv`, with the right header, and `responses.csv.guide.txt`, which lists what each column accepts:

```bash
python3 csv_to_gform.py "https://forms.gle/YOUR_FORM" --template responses.csv
```

Fill it in with one row per response, in Excel, Google Sheets or Numbers, and save as **CSV UTF-8**. You can also use a CSV you already have; see [Preparing your CSV](#preparing-your-csv).

**4. Do a dry run.** It reads the form, matches your columns, checks every row, and shows how row 1 will be sent. Nothing is submitted.

```bash
python3 csv_to_gform.py "https://forms.gle/YOUR_FORM" responses.csv
```

**5. Send one row,** then open the form's **Responses** tab and check that it looks right.

```bash
python3 csv_to_gform.py "https://forms.gle/YOUR_FORM" responses.csv --submit --limit 1
```

**6. Send the rest.** Row 1 is already logged, so it won't be sent again. If Google starts limiting submissions partway, the script waits and continues by itself; just leave it running.

```bash
python3 csv_to_gform.py "https://forms.gle/YOUR_FORM" responses.csv --submit
```

## Preparing your CSV

> **The complete rules are in [docs/CSV_FORMAT.md](docs/CSV_FORMAT.md).** That covers file encoding and separators, quoting, how headers are matched, every question type with valid and invalid examples, "Other" answers, dates in every format, forms with sections, editing a CSV after sending, and every error message. This section is the summary.

One header row, then one row per response. Save it as **CSV UTF-8**: in Excel, **File → Save As → CSV UTF-8**. Plain "CSV" in Mac Excel can't store Cyrillic or Kazakh letters.

**Headers.** Use the question titles from the form, or let `--template` write them for you. Small differences are fine: `Q1. How old are you?` matches `How old are you`. If your headers are something else entirely (`q1`, `age`...) but the columns are in the same order as the questions, add `--by-order`. A `Timestamp` column is ignored automatically; ignore any other column with `--skip "Column name"`.

**Cells.** Write answers exactly as the options appear in the form. Capital letters, extra spaces and dash types don't matter.

| Question type | What to put in the cell | Example |
|---|---|---|
| Short answer, paragraph | Any text | `Great service` |
| Multiple choice, dropdown | **Exactly one** option. Several answers in one cell is an error, because the question can only hold one | `25–34` |
| Checkboxes | Options separated by `;` or `,` | `Apples; Pears` |
| "Other" option | The text itself; anything that isn't an option becomes the "Other" answer | `Apples, mango` |
| Linear scale, rating | The number | `4` |
| Date | `YYYY-MM-DD` or `DD.MM.YYYY` (other formats: `--date-format`). If the question has no year, the year is ignored | `2026-05-03` |
| Date + time | The date, a space, then the time | `2026-05-03 14:30` |
| Time | `HH:MM`, 24-hour or with AM/PM | `14:30`, `2:30 PM` |
| Duration | `H:MM` or `H:MM:SS` | `1:15:00` |
| Grid | One column per row of the grid, titled `Question [Row]` (how Google Sheets exports grids). For a checkbox grid, separate several answers with `,` or `;` | column `Rate us [Food]`, cell `Good` |
| Optional question | Leave the cell empty to skip it | |
| Required question | Must be filled. Google itself doesn't enforce this for scripted submissions, so the script checks it for you | |

Options that contain a comma (`Yes, often`) are fine in checkbox cells: the script matches the form's real options instead of blindly splitting on commas.

A small example is in [`example/survey.csv`](example/survey.csv).

## Options

| Option | What it does |
|---|---|
| `--template FILE` | Write an empty CSV whose columns match the form, plus `FILE.guide.txt` describing each column, then stop. No CSV argument needed. |
| `--submit` | Actually send responses. Without it, the script only checks (dry run). |
| `--limit N` | Send at most N rows in this run. Use `--limit 1` for a test. |
| `--delay SEC` | Seconds to wait between responses (default 5). Raised automatically to 10–60 s once Google starts limiting. |
| `--max-wait MIN` | When Google keeps refusing a row, how long to keep waiting and retrying it before stopping (default 60 minutes). Nothing is lost if it stops: rerun later and it continues. |
| `--restart` | Forget which rows were sent to this form earlier. Use it when the CSV is a new set of responses (see [docs/CSV_FORMAT.md §8](docs/CSV_FORMAT.md#8-editing-the-csv-after-some-rows-were-sent)). |
| `--by-order` | Pair the 1st column with the 1st question, the 2nd with the 2nd, and so on, ignoring titles. |
| `--skip COLUMN` | Ignore a column. Repeat for several. |
| `--email-column COLUMN` | For forms that ask respondents to type their email: which column has it. Detected automatically if the header is `Email` or `Email Address`. |
| `--date-format FMT` | How dates are written, in Python [strftime codes](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes), e.g. `%d/%m/%Y` or `%m/%d/%Y`. Needed for slash dates, which are ambiguous. |
| `--delimiter CHAR` | CSV separator. Detected automatically (comma, semicolon or tab). |
| `--encoding NAME` | File encoding. Default: UTF-8, falling back to cp1251 (Cyrillic Excel). |

## How it works

A Google Form is a web page that sends answers to `.../formResponse` as fields named `entry.<number>`. The script downloads the form page, reads the questions, options and entry numbers from the data Google embeds in it (`FB_PUBLIC_LOAD_DATA_`), and converts each CSV row into those fields. It then sends them the same way a browser does when someone presses Submit. Google records each one as a normal response, so they show up in the Summary, Individual view and linked Sheet.

Rows that were accepted are written to `<your csv>.submitted`: the form's ID, the row number and a fingerprint of the row's content. Keep that file until you're done.

**When Google limits you.** Google throttles a computer that sends many responses in a short time: it answers HTTP 429 or 503, or redirects to its "unusual traffic" page. When that happens the script doesn't count the row as sent. It waits 1 minute, then 2, 5, 10 and 15 minutes between retries, tries the same row again, and uses a longer delay between rows for the rest of the run. After `--max-wait` minutes on one row it stops, and running the same command later picks up where it left off. It never tries to get around the limit (no captcha solving, no changing identity); it just waits.

## Limitations

- **Forms that require a Google sign-in can't be filled.** That includes "Limit to 1 response" and "Collect email addresses: Verified". Turn those settings off while importing, then turn them back on.
- **File-upload questions** can't be filled. If one is required, the form can't be used.
- **Timestamps are the time of import.** Google stamps each response when it arrives; there is no way to set an earlier date. If dates matter, keep them in a question of their own.
- **Branching isn't worked out for you.** The script sends the answers that are in the row. For forms with "go to section based on answer", leave every cell of a skipped section empty; a fully empty section is treated as skipped ([details](docs/CSV_FORMAT.md#6-forms-with-several-sections)).
- **Answer rules aren't checked.** If a question has response validation ("number between 1 and 10", "must be an email"), make sure your cells follow it. The script doesn't check those rules, and Google may record the answer anyway.
- **Speed is limited by Google.** A few hundred responses can take a while, because Google throttles fast submissions. The script waits it out automatically.
- **Google can change its forms.** The script relies on the structure of Google's form page, which isn't an official API. If it stops working, please open an issue. This is also why you should always send one test row first.

## Use it honestly

This tool is for entering **real responses into your own forms**: answers collected on paper, by phone, at an event, or in another tool. Don't use it to submit made-up answers, inflate a survey, or flood someone else's form; that is fraud, and in research it's misconduct.

If the responses are part of a study, say in your methods how they were collected and that they were entered with a script. That's also why the timestamps will all be from the day you imported them.

## Troubleshooting

Every error message from the dry run is explained in [docs/CSV_FORMAT.md §9](docs/CSV_FORMAT.md#9-error-messages-and-what-to-do). The common ones:

| Message | What to do |
|---|---|
| `This form requires a Google sign-in` | See [Limitations](#limitations): turn off "Limit to 1 response" and verified email collection while importing. |
| `Columns with no matching question` | Rename the header to the question's title, ignore the column with `--skip`, use `--by-order`, or start from `--template`. |
| `'...' is not one of the options` | The cell's text differs from the form's option. Fix the cell, or edit the option in the form. |
| `has 2 answers (...), but this is a multiple choice question that takes only one` | Keep one answer per cell, or change that question to Checkboxes in the form. |
| `can't read the date` | Use `YYYY-MM-DD`, or pass `--date-format` (e.g. `%d/%m/%Y`). |
| `Google is limiting submissions from this computer` | Not an error: the script is waiting and will retry by itself. Leave it running. |
| `Google is still refusing after 60 min of waiting` | Run the same command again later; it continues from where it stopped. Use a bigger `--delay` next time. |
| `The CSV has changed since an earlier run` | The file was edited or replaced after some rows were sent. For a new set of responses add `--restart`; see [§8](docs/CSV_FORMAT.md#8-editing-the-csv-after-some-rows-were-sent). |
| `Google refused it (HTTP 4xx)` | Check that the form is still public and accepting responses. |
| Text looks garbled | The file's encoding wasn't detected. Re-save the file as "CSV UTF-8", or try `--encoding cp1251` / `--encoding utf-16`. |

## Running the tests

```bash
python3 -m unittest discover -s tests
```

The tests use a mock form and need no internet connection.

## License

[MIT](LICENSE). Free to use, change and share.
