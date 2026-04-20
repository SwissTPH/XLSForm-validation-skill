# XLSForm Checker

A Claude Code skill that validates ODK XLSForms and returns plain-English feedback for non-technical health researchers.

Built from **Research Informatics** at **Swiss TPH** to help field teams debug clinical-trial surveys without needing a data manager in the loop.

## What it does

Given an `.xlsx` XLSForm, the skill reports:

- **Exactly where** each problem is (sheet, row, column, cell reference)
- **What went wrong** in plain English (no XPath jargon)
- **How to fix it** — concrete, copy-pasteable suggestions

Typical issues caught:

- Syntax errors in `relevant` / `constraint` / `calculation` expressions
- Missing or duplicate variable names
- Choice-list references that don't match any `list_name` on the `choices` sheet
- Required columns missing from `survey` / `choices` / `settings` sheets
- Broken `${var}` references (unknown variable, used before defined, out of repeat scope)
- Invalid `type` values and malformed select question types
- Label/hint columns missing for the configured language(s)
- Unsupported ODK functions
- Settings sheet issues (missing `form_id`, `version`, form title)
- Common "silent failure" patterns that `pyxform` accepts but ODK Central later rejects

## How it works

```
XLSForm (.xlsx)
      │
      ▼
┌──────────────────────┐
│   pyxform validate   │  ← core syntax / schema check
└──────────────────────┘
      │
      ▼
┌──────────────────────┐
│  check_xlsform.py    │  ← ~10 extra quality checks pyxform misses
└──────────────────────┘
      │
      ▼
┌──────────────────────┐
│   Claude interprets  │  ← structured output → plain-English report
└──────────────────────┘
      │
      ▼
  Actionable feedback
```

- **Core engine:** [`pyxform`](https://github.com/XLSForm/pyxform) — the same validator ODK Central uses.
- **Wrapper:** `check_xlsform.py` — a lightweight Python script that adds rule-based checks `pyxform` does not cover (e.g. silent-failure cases, scope issues inside repeat groups, SwissTPH naming conventions).
- **Output layer:** Claude translates the structured checker output into researcher-friendly guidance.

## Requirements

- Claude Code
- Python 3 with:
  - `pyxform`
  - `openpyxl` (pulled in by `pyxform`)

## Usage

Drop this skill folder into your Claude Code skills directory, then ask Claude something like:

> Can you check my XLSForm? It's a malaria household survey and I'm trying to deploy it to ODK Central. The file is at `/path/to/my/doc/malaria_survey.xlsx`.

Claude will run the validation pipeline and return a report you can act on directly.

## License

CC0 1.0 Universal license

## Maintainer

Jiayu Wang, Swiss TPH — `jiayu.wang@swisstph.ch`
