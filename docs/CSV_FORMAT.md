# CSV format guide

This page describes exactly what `csv_to_gform.py` accepts: the file, the header row, and what to write in each cell for every type of Google Forms question. Every rule here is what the code actually does.

**The short version:** one header row, then one row per response. Each column is one question, titled like the question in the form. Each cell holds that person's answer, written the same way as the option in the form.

## Contents

1. [Let the tool write the CSV for you](#1-let-the-tool-write-the-csv-for-you)
2. [The file](#2-the-file)
3. [The header row](#3-the-header-row)
4. [Cells: general rules](#4-cells-general-rules)
5. [Cells: each question type](#5-cells-each-question-type)
6. [Forms with several sections](#6-forms-with-several-sections)
7. [A complete example](#7-a-complete-example)
8. [Editing the CSV after some rows were sent](#8-editing-the-csv-after-some-rows-were-sent)
9. [Error messages and what to do](#9-error-messages-and-what-to-do)
10. [Checklist before sending](#10-checklist-before-sending)

---

## 1. Let the tool write the CSV for you

The easiest way to get the format right is to start from a template made from your form:

```bash
python3 csv_to_gform.py "https://forms.gle/YOUR_FORM" --template responses.csv
```

This writes two files:

- `responses.csv`: an empty CSV whose header row matches your form exactly, one column per question, in the form's order.
- `responses.csv.guide.txt`: for every column, the question type, whether it's required, and exactly which answers it accepts. For example:

  ```
  4. "How did you hear about us?": multiple choice, required. Accepts exactly ONE of: Friend | Instagram | Poster | Other.
  5. "Which days do you visit?": checkboxes, optional (leave empty to skip). Accepts one or more of: Mon | Tue | Wed (separate several with ;).
  ```

Open `responses.csv` in Excel, Google Sheets, Numbers or LibreOffice, add one row per response, save it as CSV (see [2.1](#21-file-type-and-how-to-export)), and do a dry run.

---

## 2. The file

### 2.1 File type and how to export

The file must be **CSV** (plain text, `.csv`). Excel `.xlsx`, Numbers `.numbers` and LibreOffice `.ods` files can't be read directly. Export them:

| App | How to save as CSV |
|---|---|
| Excel (Windows) | **File → Save As →** "CSV UTF-8 (Comma delimited) (*.csv)" |
| Excel (Mac) | **File → Save As → File Format:** "CSV UTF-8 (Comma-delimited) (.csv)". Don't pick plain "Comma Separated Values": it uses an old encoding that can't store Cyrillic, Kazakh, Arabic, Chinese or emoji, and those letters turn into `?`. |
| Google Sheets | **File → Download → Comma-separated values (.csv)** |
| Numbers (Mac) | **File → Export To → CSV…**, Text Encoding: **Unicode (UTF-8)** |
| LibreOffice Calc | **File → Save As →** "Text CSV (.csv)", tick *Edit filter settings*, Character set **UTF-8**, Field delimiter `,` |

Only the first sheet/tab is saved in a CSV. If your responses are on another tab, export that one.

### 2.2 Encoding (how letters are stored)

| Encoding | Handled |
|---|---|
| UTF-8, with or without BOM | Yes, automatically (recommended) |
| UTF-16 (Excel "Unicode Text") | Yes, automatically (detected by its BOM) |
| Windows-1251 (Cyrillic Windows/Excel) | Yes, automatically: used when the file isn't valid UTF-8, and the tool prints a note when it does this |
| Anything else (Latin-1, Shift-JIS, ...) | Pass `--encoding NAME`, e.g. `--encoding latin-1` |

If text looks garbled in the dry run's output, the encoding was guessed wrong. Re-save the file as CSV UTF-8, or pass `--encoding`.

### 2.3 Separator

Cells can be separated by a **comma** `,`, **semicolon** `;` or **tab**. The tool picks the one that gives every line the same number of columns. Excel in many countries (Russia, Kazakhstan, Germany, France...) saves CSVs with semicolons, and that's fine. To force one: `--delimiter ";"`.

### 2.4 Quotes, commas and line breaks inside cells

These are standard CSV rules. Spreadsheet apps apply them for you, so you only need them when editing the file in a text editor.

- A cell containing the separator, a double quote `"` or a line break must be wrapped in double quotes:

  ```csv
  Name,Comment
  Aida,"Good, but slow"
  ```
- A double quote inside a quoted cell is written twice:

  ```csv
  Name,Comment
  Aida,"She said ""wow"""
  ```
- A line break inside a quoted cell is kept, which is useful for paragraph answers:

  ```csv
  Name,Comment
  Aida,"First line
  second line"
  ```

If you forget the quotes, the comma splits the cell in two and the row gets an extra column. The dry run reports this as *"has 9 cells but the header has 8 columns"*.

### 2.5 Rows

- **The first line is the header.** Every line after it is one response.
- **Row numbers in messages count responses,** so "row 1" is the first line *after* the header (line 2 of the file).
- **Completely empty lines are ignored,** including lines with only separators or spaces.
- **A row with fewer cells than the header** is treated as if the missing cells were empty.
- **A row with more filled cells than the header** is an error (see the quotes rule above).

---

## 3. The header row

Each column has to be paired with a question. The dry run prints the pairing before anything is sent, so you can check it:

```
  1. Your name     -> Your name     [short answer, by title]
  Age group?       -> Age group     [multiple choice, by title]
  Notes            -> Comments      [paragraph, by position, check this]
```

### 3.1 Matching by title (the normal way)

A column is paired with the question that has the same title. These differences are ignored:

| Ignored | Example: these all match the question `How old are you?` |
|---|---|
| Capital letters | `HOW OLD ARE YOU?` |
| Extra spaces, non-breaking spaces | `How  old are   you?` |
| Numbering at the start: `1.` `1)` `1:` `1 -` `Q1.` `q1)` `Question 1:` | `Q1. How old are you?`, `3) How old are you?` |
| `*` `?` `:` `.` `!` at the end | `How old are you`, `How old are you? *` |
| Dash types (`-` `–` `—`) and curly vs straight quotes | |

These are **not** ignored, so they won't match: different words, typos, missing words, `#1` or `No. 1` as numbering, or a number without punctuation (`1 How old are you`).

The same normalisation is applied to the form's titles, so if the form itself numbers its questions (`1. How old are you?`), a column titled `How old are you` still matches.

**Column order doesn't matter** when matching by title.

### 3.2 Leftover columns are paired by position

Suppose some columns don't match any title and exactly the same number of questions are left without a column. The tool then pairs those leftovers in order and marks each pair **"by position, check this"**. Check those pairs in the dry run. If the counts differ, the run stops and lists the unmatched columns and questions.

### 3.3 Ignoring titles completely: `--by-order`

With `--by-order`, the 1st column goes to the 1st question, the 2nd to the 2nd, and so on. Titles are ignored. The number of columns (after skipped ones) must equal the number of questions, counting each grid row as one question.

### 3.4 Columns that are ignored

- **Timestamp columns** are always ignored: `Timestamp`, `Отметка времени`, `Уақыт белгісі`. Google Sheets exports of form responses start with one.
- Any other column you name with `--skip "Column title"` (repeat it for several columns).
- **Email columns** (`Email`, `Email Address`, `E-mail`, `Адрес электронной почты`, `Электронная почта`, `Электрондық пошта`) are ignored unless the form asks respondents for their email (see [5.13](#513-email-address)).

### 3.5 Questions without a column

- **Optional question:** left blank in every response. The dry run lists these as *"Left blank (optional, no column)"*.
- **Required question:** the run stops with *"Required questions with no column"*.

### 3.6 Things in a form that never need a column

Section headers, title-and-description blocks, images and videos. They hold no answers.

### 3.7 Two questions with the same title

Columns are given to them in order: the first matching column goes to the first such question, the second to the second.

### 3.8 Grid questions: one column per grid row

A grid question has several rows, and each one is its own column, titled `Question title [Row label]`. This is the same format Google Sheets uses when it exports form responses.

For a grid titled `Rate us` with rows `Food` and `Staff`:

```csv
Rate us [Food],Rate us [Staff]
Good,OK
```

---

## 4. Cells: general rules

These apply to every question type.

- **Spaces at the start and end of a cell are ignored.**
- **Matching an option is forgiving.** Case doesn't matter (`yes` = `Yes`), extra spaces don't matter, dash types don't matter (`18-24` = `18–24`), and a whole number written as a decimal is accepted (`4.0` = `4`, which spreadsheets sometimes produce). The answer sent to Google is always the form's own spelling of the option.
- **Everything else must match the option's text,** spelled the same and with the same words. `Yes, often` doesn't match `Yes - often`.
- **An empty cell means "no answer".** That's fine for optional questions, and an error for required ones.

  This matters more than it seems: **Google itself does not check required questions** for submissions like these. It would record a response with a required question left blank. The tool checks every row before sending anything, so blank required answers never get in.
- **The tool doesn't check answer rules** ("response validation": number ranges, regular expressions, minimum length, "must be an email") **in advance**. Make sure your answers satisfy them.

---

## 5. Cells: each question type

### 5.1 Short answer and Paragraph

**Accepts:** any text. Line breaks are allowed inside a quoted cell.

```csv
Name,Comments
Aida,"Great service, would come back"
```

### 5.2 Multiple choice and Dropdown: exactly one answer

**Accepts:** exactly one of the question's options. If the question has an **Other** option, any text that isn't an option becomes the Other answer (see [5.4](#54-the-other-option)).

```csv
Age group
25–34
25-34
 25–34
```
All three are accepted and sent as `25–34`.

**Several answers in one cell is an error,** for example `18–24; 25–34`. A multiple-choice or dropdown question can only hold one answer, so Google could never store both. The error looks like this:

```
row 5: has 2 answers (18–24; 25–34), but this is a multiple choice question that takes only one.
Keep one answer per cell, or change the question to Checkboxes in the form.
```

Fix it one of two ways: keep a single answer in each of those cells, or change the question to **Checkboxes** in the form editor. Change the question type only if it really should allow several answers, because that changes your survey.

### 5.3 Checkboxes: one or more answers

**Accepts:** one or more options in one cell, separated by **`;`** (recommended), **`,`** or a line break. Order doesn't matter, and a repeated option is counted once.

```csv
Fruits you like
Apples
Apples; Pears
"Apples, Pears"
apples;pears
```

**Options that contain a comma are fine.** The tool looks for the form's real options in the text, longest first, instead of blindly splitting on commas. With the options `Red, dark grapes`, `Apples` and `Pears`, the cell `Red, dark grapes, Apples` is read correctly as 2 answers. Using `;` between answers is still the clearest choice.

**Text that isn't an option** becomes the Other answer if the question has Other, and is an error otherwise. Only one piece of Other text is allowed per cell.

**Google Sheets exports** join checkbox answers with `, `. Those exports work as they are.

### 5.4 The "Other" option

Other works for multiple choice and checkboxes when **"Add 'Other'"** is turned on in the form.

- **Multiple choice:** a cell that isn't one of the options is sent as the Other answer, with the whole cell as its text. `Purple` → Other: "Purple".
- **Checkboxes:** each piece of text between separators that isn't an option becomes the Other text. `Apples; mango` → Apples + Other: "mango". Other text can contain commas when it's at the end of the cell: `Pears, mango, kiwi` → Pears + Other: "mango, kiwi".
- **Don't write the word "Other" itself** (or "Басқа" or "Другое") to tick the Other box, unless the form has a normal option with that exact text. Write the person's actual answer instead. If the form has a regular option literally named `Басқа`, writing `Басқа` selects that option.
- **If Other is turned off,** text that isn't an option is an error.

### 5.5 Linear scale and Star rating

**Accepts:** a whole number within the scale, for example `1` to `5` or `0` to `10`.

```csv
Satisfaction,Stars
4,5
4.0,3
```

`4.0` is accepted, `4.5` isn't, and neither is a label like `Very satisfied`. Write the number.

### 5.6 Multiple-choice grid

One column per grid row, titled `Question [Row]` (see [3.8](#38-grid-questions-one-column-per-grid-row)). Each cell holds **one** of the grid's columns.

```csv
Rate us [Food],Rate us [Staff]
Good,OK
```

### 5.7 Checkbox grid

Same layout as the multiple-choice grid, but each cell can hold several of the grid's columns, separated by `;` or `,`.

```csv
Meals by day [Breakfast],Meals by day [Lunch]
"Mon, Wed",Tue
Tue,Mon; Tue; Wed
```

### 5.8 Date

**Accepts** these formats without extra options:

| Format | Example |
|---|---|
| `YYYY-MM-DD` (recommended) | `2026-05-03` |
| `DD.MM.YYYY` | `03.05.2026` |
| `YYYY/MM/DD` | `2026/05/03` |

Both examples mean 3 May 2026.

**Slash dates like `05/03/2026` need `--date-format`,** because they're ambiguous: 5 March or 3 May? Use Python [strptime codes](https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes):

| Your dates look like | Pass |
|---|---|
| `03/05/2026` (day first) | `--date-format "%d/%m/%Y"` |
| `05/03/2026` (month first, US) | `--date-format "%m/%d/%Y"` |
| `3 May 2026` | `--date-format "%d %B %Y"` (English month names) |
| `03-05-26` | `--date-format "%d-%m-%y"` |

With `--date-format`, **every** date and date-time cell must use that format.

**Questions without a year** ("Include year" turned off): still write a full date. The year is ignored. `2000-07-14` is stored as 14 July.

### 5.9 Date with time

For a date question with "Include time" turned on, write the date, a space, then the time:

| Format | Example |
|---|---|
| `YYYY-MM-DD HH:MM` | `2026-05-03 14:30` |
| `YYYY-MM-DD HH:MM:SS` | `2026-05-03 14:30:00` |
| `YYYY-MM-DDTHH:MM` | `2026-05-03T14:30` |
| `DD.MM.YYYY HH:MM` | `03.05.2026 14:30` |
| `YYYY/MM/DD HH:MM` | `2026/05/03 14:30` |

If you leave out the time, `00:00` is sent. With `--date-format`, include the time codes, e.g. `"%d/%m/%Y %H:%M"`.

### 5.10 Time (time of day)

**Accepts:** `HH:MM` in 24-hour time, or with AM/PM. Seconds are optional.

| You write | Stored |
|---|---|
| `14:30` | 14:30 |
| `9:05` | 09:05 |
| `2:30 PM`, `2:30pm`, `2:30 p.m.` | 14:30 |
| `12:15 AM` | 00:15 |
| `14:30:15` | 14:30:15 |

### 5.11 Duration (length of time)

For a time question set to "Duration", write `H:MM:SS` or `H:MM` (seconds default to 0). Hours can go up to 99.

| You write | Stored |
|---|---|
| `1:15:00` | 1 h 15 min 0 s |
| `0:45` | 0 h 45 min 0 s |

### 5.12 File upload

**Can't be filled from a CSV.** Google only accepts uploads from signed-in users in the browser. Leave the column out. If the question is required, the form can't be used with this tool.

### 5.13 Email address

Only relevant if the form's settings ask respondents to type their email ("Collect email addresses: Responder input"). Then the CSV needs an email column, named `Email`, `Email Address` or similar, or chosen with `--email-column "Column title"`. Every row needs an email in it.

If the setting is **"Verified"**, Google requires respondents to sign in, and this tool can't fill the form. The same goes for "Limit to 1 response". Turn these settings off while importing.

---

## 6. Forms with several sections

You don't need to do anything special: one row still holds the answers for every section.

- **Linear forms** (every respondent sees every section) work as they are.
- **Forms with branching** ("Go to section based on answer"): fill in the sections that person would have seen, and leave **all** cells of the sections they skipped empty. The tool sends exactly the answers in the row; it doesn't work out branching rules for you.

**The section rule:** if every cell of a section is empty in a row, the tool treats that section as skipped, the way branching skips it. Its required questions aren't demanded. The first section can never be skipped, and a section with even one answer must have all of its required questions filled.

The dry run tells you when this happens, so an unfinished response in a form without branching doesn't slip through unnoticed:

```
All 110 rows fit the form.
Note: 3 row(s) leave a whole section empty (17, 42, 88); those sections are treated as skipped, ...
```

When sending, the tool first reports every section as visited. If Google refuses that, it retries with only the sections that have answers.

---

## 7. A complete example

**The form** (one section):

| # | Question | Type | Required | Options |
|---|---|---|---|---|
| 1 | Name | Short answer | yes | |
| 2 | Age group | Multiple choice | yes | `18–24`, `25–34`, `35+` |
| 3 | Fruits you like | Checkboxes, with Other | no | `Apples`, `Red, dark grapes`, `Pears` |
| 4 | Satisfaction | Linear scale 1–5 | yes | |
| 5 | Visit date | Date | no | |
| 6 | Rate us | Multiple-choice grid | no | rows `Food`, `Staff`; columns `Bad`, `OK`, `Good` |
| 7 | Comments | Paragraph | no | |

**The CSV** (`responses.csv`):

```csv
Timestamp,1. Name,2. Age group,3. Fruits you like,4. Satisfaction,5. Visit date,Rate us [Food],Rate us [Staff],Comments
2026-05-03 10:15,Aida,18-24,"Apples; Pears",5,2026-05-03,Good,Good,Loved the pears
2026-05-03 12:40,Bekzat,25–34,"Red, dark grapes, Apples",4,03.05.2026,OK,Good,
2026-05-04 09:05,Dana,35+,"Pears, mango",3,,Good,OK,"Slow service, but friendly"
```

**What happens:**

- `Timestamp` is ignored. `1. Name` matches `Name`, because numbering is ignored.
- Aida: `18-24` is matched to the option `18–24`, despite the different dash.
- Bekzat: `Red, dark grapes, Apples` → two answers. The comma inside the first option doesn't split it.
- Dana: `Pears, mango` → `Pears` plus Other: "mango". Her visit date is empty, which is fine because it's optional.
- Bekzat's comment is empty, which is fine because it's optional.

The dry run then shows the pairing and `All 3 rows fit the form.`

---

## 8. Editing the CSV after some rows were sent

The tool records each sent row in `responses.csv.submitted`: the form, the row number, and a fingerprint of the row's content. A rerun skips rows that were already sent, so nothing is sent twice.

If you **change rows that were already sent**, or replace the file with a different set of responses, the next run stops before sending anything:

```
The CSV has changed since an earlier run sent rows to this form: row(s) 1-19 were sent with different content.
```

- **It's a new set of responses:** run again with `--restart`. That forgets the old log and sends every row. Responses already in the form stay there.
- **You corrected rows that were already sent:** the old versions are in the form. Fix or delete them in the form's Responses tab. Then use `--restart` with a CSV that contains only the rows still to send.

Adding new rows **at the end** of the file is always safe: they're simply sent next time.

---

## 9. Error messages and what to do

The dry run groups problems by column, shows which rows are affected, and gives up to three examples per column:

```
Problems in 59 of 110 rows. Nothing was sent.

  4. What affects prices?: 59 rows (5-8, 10, 13, 15-17, ...)
      row 5: has 2 answers (A; B), but this is a multiple choice question that takes only one. ...
```

| Message | Meaning and fix |
|---|---|
| `'X' is not one of the options ('A', 'B', ...)` | The text doesn't match any option. Compare the spelling with the list shown, and correct the cell, or the option in the form. |
| `has N answers (...), but this is a multiple choice question that takes only one` | Several answers in a one-answer question. See [5.2](#52-multiple-choice-and-dropdown-exactly-one-answer). |
| `is empty, but the question is required` | Fill in the cell, or make the question optional in the form. |
| `'X' is not one of the options` (checkboxes) | Part of the cell isn't an option and the question has no Other. Fix the spelling or the separator. |
| `only one 'Other' answer is allowed` | A checkbox cell has two pieces of non-option text. Merge them, or fix a misspelled option. |
| `can't read the date '...'` | Use `YYYY-MM-DD` or pass `--date-format`. See [5.8](#58-date). |
| `can't read the time '...'` | Use `HH:MM` or `H:MM AM`. See [5.10](#510-time-time-of-day). |
| `has 9 cells but the header has 8 columns` | A cell with a comma in it isn't in quotes. See [2.4](#24-quotes-commas-and-line-breaks-inside-cells). |
| `Columns with no matching question` | Rename the column to the question's title, `--skip` it, or use `--template` to get exact titles. |
| `Required questions with no column` | Add a column for that question. |
| `this form asks for an email address` | Add an email column, or turn off email collection. See [5.13](#513-email-address). |
| `The CSV has changed since an earlier run...` | See [section 8](#8-editing-the-csv-after-some-rows-were-sent). |
| Text looks garbled (`Ð¡Ñ–Ð·`, `??????`) | Wrong encoding. Re-save as CSV UTF-8. See [2.2](#22-encoding-how-letters-are-stored). |

---

## 10. Checklist before sending

1. The file is saved as **CSV UTF-8**.
2. The dry run shows every column paired with the right question, and nothing marked "by position" that is wrong.
3. The dry run ends with **"All N rows fit the form."**
4. You sent **one** row with `--submit --limit 1` and checked it in the form's Responses tab.
5. You know that every response will be timestamped with the moment it is sent. If the date matters, keep it in a question of its own.
