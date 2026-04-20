# XLSForm Syntax Reference

## Question Types

### Basic input

| Type          | Description                       |
| ------------- | --------------------------------- |
| `text`        | Free text answer                  |
| `integer`     | Whole number                      |
| `decimal`     | Number with decimals              |
| `date`        | Date picker                       |
| `time`        | Time picker                       |
| `dateTime`    | Date and time                     |
| `note`        | Display-only text (no input)      |
| `acknowledge` | Checkbox the enumerator must tick |

### Select questions

| Type                                 | Description                                                  |
| ------------------------------------ | ------------------------------------------------------------ |
| `select_one list_name`               | Single choice from a list (choices sheet)                    |
| `select_multiple list_name`          | Multiple choices from a list (choices sheet)                 |
| `select_one_from_file file.csv`      | Single choice from external file — **not** in choices sheet  |
| `select_multiple_from_file file.csv` | Multiple choices from external file — **not** in choices sheet |
| `rank list_name`                     | Rank options in order                                        |

#### External file selects (`_from_file`)

- Supported file types: `.csv`, `.xml`, `.geojson` (note: `.json` is **not** valid — must be `.geojson`)
- The file must have `name` and `label` columns (or configure custom columns via the `parameters` column)
- For `select_multiple_from_file`, the `name` values in the file must not contain spaces
- The file must be **attached to the form at deployment time** in ODK Central / KoboToolbox
- Alternatively, reference an **ODK Central Entity List** — it works like a CSV managed on the server and shared across forms
- These types are **never** listed in the choices sheet; the reference is only in the `type` column of the survey sheet

### Media and location

| Type       | Description     |
| ---------- | --------------- |
| `image`    | Photo capture   |
| `audio`    | Audio recording |
| `video`    | Video recording |
| `geopoint` | GPS coordinates |
| `geotrace` | GPS path        |
| `geoshape` | GPS polygon     |

### Hidden and calculated

| Type        | Description                             |
| ----------- | --------------------------------------- |
| `calculate` | Store computed value (hidden from user) |
| `hidden`    | Store a value set via default (hidden)  |

### Metadata (auto-collected)

| Type          | Description                   |
| ------------- | ----------------------------- |
| `start`       | Start timestamp               |
| `end`         | End timestamp                 |
| `today`       | Today's date                  |
| `deviceid`    | Device identifier             |
| `username`    | Logged-in username            |
| `phonenumber` | SIM phone number              |
| `audit`       | Audit log (time per question) |

### Structure

| Type                          | Description                       |
| ----------------------------- | --------------------------------- |
| `begin_group` / `end_group`   | Group questions together          |
| `begin_repeat` / `end_repeat` | Repeat a set of questions N times |

---

## XPath Functions Reference

### Logic

| Function            | Example                                | Description           |
| ------------------- | -------------------------------------- | --------------------- |
| `if(cond, yes, no)` | `if(${age} < 5, 'child', 'adult')`     | Conditional value     |
| `coalesce(a, b)`    | `coalesce(${q1}, 'Unknown')`           | First non-empty value |
| `not(expr)`         | `not(${consent} = 'yes')`              | Logical NOT           |
| `and`               | `${age} > 18 and ${consent} = 'yes'`   | Logical AND           |
| `or`                | `${sex} = 'male' or ${sex} = 'female'` | Logical OR            |

### Select / choice functions

| Function                    | Example                          | Description                                      |
| --------------------------- | -------------------------------- | ------------------------------------------------ |
| `selected(field, 'val')`    | `selected(${symptoms}, 'fever')` | True if value selected — use for select_multiple |
| `selected-at(field, index)` | `selected-at(${items}, 0)`       | Value at position (0-based)                      |
| `count-selected(field)`     | `count-selected(${symptoms})`    | Number of selected options                       |

### Math

| Function             | Example                     | Description               |
| -------------------- | --------------------------- | ------------------------- |
| `round(num, places)` | `round(${weight} div 2, 1)` | Round to decimal places   |
| `int(num)`           | `int(${decimal_age})`       | Convert to integer        |
| `abs(num)`           | `abs(${diff})`              | Absolute value            |
| `mod(a, b)`          | `mod(${age}, 2)`            | Modulo (remainder)        |
| `min(a, b, ...)`     | `min(${a}, ${b})`           | Minimum                   |
| `max(a, b, ...)`     | `max(${a}, ${b})`           | Maximum                   |
| `sum(nodeset)`       | `sum(${repeat_item})`       | Sum of repeat values      |
| `count(nodeset)`     | `count(${repeat_item})`     | Count of repeat instances |

**Arithmetic operators**: `+`, `-`, `*`, `div`, `mod` — **never use `/` for division** (it is an XPath path separator, not division) and **never use `%`** (not a valid ODK operator). Wrong: `${a} / ${b}`. Correct: `${a} div ${b}`.

### String functions

| Function                   | Example                             | Description             |
| -------------------------- | ----------------------------------- | ----------------------- |
| `concat(a, b, ...)`        | `concat(${name}, ' - ', ${id})`     | Join strings            |
| `string-length(str)`       | `string-length(${text})`            | Length of string        |
| `substr(str, start, len)`  | `substr(${id}, 0, 3)`               | Substring               |
| `contains(str, sub)`       | `contains(${text}, 'malaria')`      | True if contains        |
| `starts-with(str, sub)`    | `starts-with(${id}, 'TPH')`         | True if starts with     |
| `upper-case(str)`          | `upper-case(${name})`               | Uppercase               |
| `lower-case(str)`          | `lower-case(${name})`               | Lowercase               |
| `translate(str, from, to)` | Replace characters                  |                         |
| `regex(str, pattern)`      | `regex(${phone}, '^\+[0-9]{10,}$')` | True if matches pattern |

### Date functions

| Function                 | Example                              | Description         |
| ------------------------ | ------------------------------------ | ------------------- |
| `today()`                | `today()`                            | Current date        |
| `now()`                  | `now()`                              | Current date + time |
| `date(str)`              | `date('2024-01-01')`                 | Parse date string   |
| `format-date(date, fmt)` | `format-date(today(), '%d/%m/%Y')`   | Format a date       |
| `decimal-date-time(dt)`  | Convert dateTime to decimal for math |                     |
| `duration(expr)`         | Elapsed time calculation             |                     |

### Repeat functions

| Function                               | Example                                | Description                             |
| -------------------------------------- | -------------------------------------- | --------------------------------------- |
| `count(nodeset)`                       | `count(${child_repeat})`               | Number of repeat instances              |
| `indexed-repeat(field, repeat, index)` | `indexed-repeat(${name}, ${child}, 1)` | Get value from specific repeat instance |
| `position(..)`                         | `position(..)`                         | Current repeat position (1-based)       |

---

## Common Mistakes to Avoid

1. **Using `/` instead of `div`**: Write `${weight} div ${height}`, not `${weight} / ${height}`
2. **Using `+` to join strings**: Write `concat(${a}, ' ', ${b})`, not `${a} + ' ' + ${b}`
3. **Using `begin group` (with space)**: Prefer `begin_group` (underscore) — more consistent
4. **Missing list name**: `select_one` needs `select_one list_name`, not just `select_one`
5. **Using `=` with select_multiple**: Use `selected(${field}, 'value')` not `${field} = 'value'`
6. **Referencing ${field} that doesn't exist**: Spelling must exactly match the `name` column
7. **Not closing groups**: Every `begin_group` needs a matching `end_group`
8. **Duplicate names**: Every question `name` must be unique across the whole survey sheet
9. **Name starting with a number**: Names must start with a letter or underscore
10. **Spaces or hyphens in names**: Use underscores only: `date_of_birth` not `date-of-birth`
11. **Using `$[field]` instead of `${field}`**: The correct ODK syntax uses curly braces `${}`
12. **Missing `or_other` handling**: If using `select_one list or_other`, add a follow-up text question with `other_id` set, or handle the `other` value manually
13. **`required` column with value `True`**: ODK expects `yes` (not `True` or `1`, though some clients accept these)

---

## Settings Sheet Reference

| Column             | Example                          | Description                          |
| ------------------ | -------------------------------- | ------------------------------------ |
| `form_title`       | Malaria Household Survey         | Display name                         |
| `form_id`          | malaria_hh_2024                  | Unique ID (no spaces)                |
| `default_language` | English (en)                     | Language shown by default            |
| `version`          | 2024010101                       | Version string (often YYYYMMDDNN)    |
| `instance_name`    | `concat(${hh_id}, '-', ${date})` | How submissions are named in server  |
| `public_key`       | (encryption key)                 | For encrypted forms                  |
| `submission_url`   | (server URL)                     | Override default submission endpoint |

---

## Appearance Options

| Appearance        | Applies to                  | Effect                                    |
| ----------------- | --------------------------- | ----------------------------------------- |
| `minimal`         | select_one, select_multiple | Compact dropdown instead of radio buttons |
| `field-list`      | begin_group                 | Show all questions in group on one screen |
| `label`           | begin_group                 | Show group name as a section header       |
| `table-list`      | begin_group                 | Display choices as a grid/table           |
| `no-collapse`     | begin_repeat                | Don't collapse repeat instances           |
| `month-year`      | date                        | Only show month and year picker           |
| `year`            | date                        | Only show year picker                     |
| `numbers`         | text                        | Show numeric keyboard                     |
| `url`             | text                        | URL input with link preview               |
| `ex:intentAction` | any                         | Launch external app                       |
| `draw`            | image                       | Draw/annotate on image                    |
| `annotate`        | image                       | Annotate on captured image                |
| `signature`       | image                       | Capture signature                         |
| `horizontal`      | select_one                  | Show choices side by side                 |
| `likert`          | select_one                  | Likert scale display                      |
| `rating`          | select_one                  | Star rating display                       |
| `autocomplete`    | select_one                  | Searchable dropdown                       |
| `quick`           | select_one                  | Auto-advance after selection              |
| `map`             | select_one                  | Display choices on a map                  |
