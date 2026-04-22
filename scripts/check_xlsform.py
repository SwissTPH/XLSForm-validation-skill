#!/usr/bin/env python3
"""
XLSForm Checker Script
Runs pyxform validation and performs additional quality checks
beyond what pyxform catches.

Usage:
    python check_xlsform.py <path_to_xlsform.xlsx>
"""

import sys
import json
import re
import tempfile
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    print(json.dumps({"error": "pandas not installed. Run: pip install pandas openpyxl"}))
    sys.exit(1)

try:
    from pyxform.xls2xform import xls2xform_convert
    from pyxform.errors import PyXFormError
    PYXFORM_AVAILABLE = True
except ImportError:
    PYXFORM_AVAILABLE = False


def run_pyxform_validation(xlsform_path: Path):
    """Run pyxform and return errors and warnings."""
    if not PYXFORM_AVAILABLE:
        return {"valid": None, "errors": [], "warnings": [],
                "note": "pyxform not installed. Run: pip install pyxform"}

    with tempfile.NamedTemporaryFile(suffix=".xml", delete=True) as tmp:
        tmp_xform = Path(tmp.name)

    errors = []
    warnings = []
    valid = False

    try:
        result_warnings = xls2xform_convert(
            xlsform_path=str(xlsform_path),
            xform_path=str(tmp_xform),
            validate=False,
            pretty_print=False,
        )
        valid = True
        if result_warnings:
            warnings = result_warnings if isinstance(result_warnings, list) else [str(result_warnings)]
    except PyXFormError as e:
        errors = [str(e)]
    except Exception as e:
        errors = [f"Unexpected error: {str(e)}"]

    return {"valid": valid, "errors": errors, "warnings": warnings}


def load_sheets(xlsform_path: Path):
    """Load survey, choices, and settings sheets from the XLSForm."""
    sheets = {}
    try:
        xl = pd.ExcelFile(xlsform_path, engine="openpyxl")
        for sheet in xl.sheet_names:
            if sheet.lower() in ("survey", "choices", "settings"):
                df = xl.parse(sheet, dtype=str).fillna("")
                sheets[sheet.lower()] = df
    except Exception as e:
        return None, str(e)
    return sheets, None


def extra_checks(sheets: dict):
    """
    Perform quality checks that pyxform does not catch.
    Returns a list of issues: {severity, sheet, row, column, message, suggestion}
    """
    issues = []
    survey = sheets.get("survey")
    choices = sheets.get("choices")

    if survey is None:
        issues.append({
            "severity": "High",
            "sheet": "survey",
            "row": None,
            "column": None,
            "message": "No 'survey' sheet found in this file.",
            "suggestion": "Make sure your file has a sheet named exactly 'survey'."
        })
        return issues

    survey_cols = [c.lower() for c in survey.columns]

    # --- Collect valid question names ---
    name_col = next((c for c in survey.columns if c.lower() == "name"), None)
    type_col = next((c for c in survey.columns if c.lower() == "type"), None)
    label_col = next((c for c in survey.columns if "label" in c.lower()), None)
    required_col = next((c for c in survey.columns if c.lower() == "required"), None)
    relevant_col = next((c for c in survey.columns if c.lower() == "relevant"), None)
    constraint_col = next((c for c in survey.columns if c.lower() == "constraint"), None)
    calculation_col = next((c for c in survey.columns if c.lower() == "calculation"), None)
    constraint_msg_col = next((c for c in survey.columns if "constraint_message" in c.lower()), None)
    hint_col = next((c for c in survey.columns if "hint" in c.lower()), None)
    appearance_col = next((c for c in survey.columns if c.lower() == "appearance"), None)

    # Build choice list names from choices sheet
    valid_choice_lists = set()
    if choices is not None:
        list_name_col = next((c for c in choices.columns if c.lower() == "list_name"), None)
        if list_name_col:
            valid_choice_lists = set(choices[list_name_col].dropna().unique())

    # Structural types — these rows have names for readability but are not question
    # variables. Their names don't need to be globally unique and cannot be referenced
    # with ${name} in expressions.
    STRUCTURAL_TYPES = {
        "begin_group", "end_group", "begin group", "end group",
        "begin_repeat", "end_repeat", "begin repeat", "end repeat",
    }

    # Build name registry — for XPath validation and duplicate detection.
    # ODK Central requires all *question* names to be globally unique. Structural
    # rows (begin_group etc.) are excluded: their names are cosmetic labels only.
    valid_names = set()
    name_first_seen = {}  # name -> first Excel row number (questions only)

    # Names of select_multiple questions — used to detect = instead of selected()
    select_multiple_names = set()

    if name_col and type_col:
        for idx, row in survey.iterrows():
            nm = str(row[name_col]).strip() if name_col else ""
            qt = str(row[type_col]).strip().lower() if type_col else ""
            if nm:
                valid_names.add(nm)
                if qt not in STRUCTURAL_TYPES and nm not in name_first_seen:
                    name_first_seen[nm] = idx + 2  # Excel row (1-indexed + header)
                if qt.startswith("select_multiple") or qt.startswith("select multiple"):
                    select_multiple_names.add(nm)

    # All label and hint columns (including multi-language variants like label::English(en))
    label_hint_cols = [c for c in survey.columns
                       if c.lower().startswith("label") or c.lower().startswith("hint")]

    # Track begin/end group/repeat balance
    group_stack = []

    for idx, row in survey.iterrows():
        row_num = idx + 2  # Excel row (1-indexed + header)
        q_type = row[type_col].strip() if type_col else ""
        q_name = row[name_col].strip() if name_col else ""
        q_label = row[label_col].strip() if label_col else ""
        q_required = row[required_col].strip() if required_col else ""
        q_relevant = row[relevant_col].strip() if relevant_col else ""
        q_constraint = row[constraint_col].strip() if constraint_col else ""
        q_calculation = row[calculation_col].strip() if calculation_col else ""
        q_constraint_msg = row[constraint_msg_col].strip() if constraint_msg_col else ""

        # Skip empty rows
        if not q_type and not q_name:
            continue

        # --- Check 0: Duplicate question name (globally unique) ---
        # ODK Central requires all question names to be unique across the entire survey,
        # even across different groups. ${field_name} references must be unambiguous.
        # Structural rows (begin_group / end_group etc.) are excluded — their names are
        # cosmetic and may intentionally match the paired opening/closing row.
        if q_name and q_type.lower() not in STRUCTURAL_TYPES and q_name in name_first_seen and name_first_seen[q_name] != row_num:
            issues.append({
                "severity": "High",
                "sheet": "survey",
                "row": row_num,
                "column": "name",
                "message": (
                    f"Duplicate name '{q_name}': this name is already used at row {name_first_seen[q_name]}. "
                    f"ODK Central requires every question name to be unique across the entire survey — "
                    f"even across different groups — because ${{{q_name}}} references must be unambiguous."
                ),
                "suggestion": (
                    f"Rename one of the two '{q_name}' questions. "
                    f"For example, add a suffix like '{q_name}_2', or choose a more specific name."
                )
            })

        # --- Check 1: Invalid characters in name ---
        if q_name and re.search(r'[\s\-/\\()&%$#@!]', q_name):
            issues.append({
                "severity": "High",
                "sheet": "survey",
                "row": row_num,
                "column": "name",
                "message": f"'{q_name}' contains invalid characters (spaces, hyphens, or special symbols).",
                "suggestion": "Use only letters, numbers, and underscores. E.g., 'date_of_birth' not 'date of birth'."
            })

        # --- Check 2: Name starts with a number ---
        if q_name and re.match(r'^\d', q_name):
            issues.append({
                "severity": "High",
                "sheet": "survey",
                "row": row_num,
                "column": "name",
                "message": f"'{q_name}' starts with a number.",
                "suggestion": "Question names must start with a letter or underscore."
            })

        # --- Check 3: select_one / select_multiple referencing non-existent choice list ---
        if q_type.startswith("select_one") or q_type.startswith("select_multiple"):
            parts = q_type.split()
            is_from_file = "_from_file" in q_type

            if is_from_file:
                # select_one_from_file / select_multiple_from_file load from an external file
                # or an ODK Central Entity List — never from the choices sheet.
                # Validate the file extension.
                if len(parts) >= 2:
                    filename = parts[-1]
                    ext = Path(filename).suffix.lower()
                    valid_extensions = {".csv", ".xml", ".geojson"}
                    if ext == ".json":
                        issues.append({
                            "severity": "High",
                            "sheet": "survey",
                            "row": row_num,
                            "column": "type",
                            "message": f"'{filename}' uses a .json extension, but GeoJSON files must use .geojson.",
                            "suggestion": "Rename the file to use the .geojson extension."
                        })
                    elif ext not in valid_extensions:
                        issues.append({
                            "severity": "High",
                            "sheet": "survey",
                            "row": row_num,
                            "column": "type",
                            "message": f"'{filename}' has an unsupported extension '{ext}'. External select files must be .csv, .xml, or .geojson.",
                            "suggestion": "Use a .csv file for choice lists, .geojson for geographic features, or .xml for structured data."
                        })
                    else:
                        # Valid extension — remind about deployment requirement
                        issues.append({
                            "severity": "Low",
                            "sheet": "survey",
                            "row": row_num,
                            "column": "type",
                            "message": f"'{q_name}' loads choices from external file '{filename}'. This file is not validated here.",
                            "suggestion": f"Make sure '{filename}' is attached to the form when deploying to ODK Central or KoboToolbox. If using an ODK Central Entity List, the list must exist on the server."
                        })
            else:
                # Regular select_one / select_multiple — check choices sheet
                if len(parts) >= 2:
                    list_ref = parts[1].split(" or_other")[0]
                    if valid_choice_lists and list_ref not in valid_choice_lists:
                        issues.append({
                            "severity": "High",
                            "sheet": "survey",
                            "row": row_num,
                            "column": "type",
                            "message": f"Choice list '{list_ref}' is referenced in type but not found in the choices sheet.",
                            "suggestion": f"Add a list named '{list_ref}' in the choices sheet, or fix the spelling in the type column."
                        })

        # --- Check 4: Missing label for visible questions ---
        non_label_types = {"note", "calculate", "hidden", "begin_group", "end_group",
                           "begin group", "end group", "begin_repeat", "end_repeat",
                           "begin repeat", "end repeat"}
        metadata_types = {"start", "end", "today", "deviceid", "subscriberid",
                          "simserial", "phonenumber", "username", "email", "audit"}
        if q_type and q_type.lower() not in non_label_types and q_type.lower() not in metadata_types:
            if not q_label:
                issues.append({
                    "severity": "Medium",
                    "sheet": "survey",
                    "row": row_num,
                    "column": "label",
                    "message": f"Question '{q_name}' (type: {q_type}) has no label.",
                    "suggestion": "Add a label so interviewers and respondents know what this question is asking."
                })

        # --- Check 5a: Non-standard value in required column ---
        # ODK's only documented value is 'yes' (or 'no'). Values like true(), True, 1
        # may work in some clients but are not officially supported and can behave
        # differently across ODK Central, KoboToolbox, and other platforms.
        NON_STANDARD_REQUIRED = {"true()", "true", "1", "false()", "false", "0"}
        if q_required and q_required.lower() in NON_STANDARD_REQUIRED:
            suggested = "yes" if q_required.lower() in ("true()", "true", "1") else "no"
            issues.append({
                "severity": "Low",
                "sheet": "survey",
                "row": row_num,
                "column": "required",
                "message": (
                    f"The required column contains '{q_required}' — the only officially documented "
                    f"ODK value is 'yes' (or 'no'). '{q_required}' may work in some clients but "
                    f"is not guaranteed to behave consistently across platforms."
                ),
                "suggestion": f"Change '{q_required}' to '{suggested}'."
            })

        # --- Check 5b: begin group / end group with space instead of underscore ---
        # 'begin group' and 'begin repeat' (with a space) work in most ODK clients
        # but the official recommended syntax uses an underscore: begin_group, end_group.
        SPACED_STRUCTURAL = {
            "begin group": "begin_group",
            "end group":   "end_group",
            "begin repeat": "begin_repeat",
            "end repeat":   "end_repeat",
        }
        if q_type.lower() in SPACED_STRUCTURAL:
            issues.append({
                "severity": "Low",
                "sheet": "survey",
                "row": row_num,
                "column": "type",
                "message": (
                    f"The type '{q_type}' uses a space — the official ODK syntax uses an underscore. "
                    f"'{q_type}' works in most clients but is not the recommended format."
                ),
                "suggestion": f"Change '{q_type}' to '{SPACED_STRUCTURAL[q_type.lower()]}'."
            })

        # --- Check 5: Required question without constraint_message ---
        if q_required.lower() in ("yes", "true", "1") and q_constraint and not q_constraint_msg:
            issues.append({
                "severity": "Low",
                "sheet": "survey",
                "row": row_num,
                "column": "constraint_message",
                "message": f"Question '{q_name}' has a constraint but no constraint_message.",
                "suggestion": "Add a constraint_message to explain to the user what value is expected."
            })

        # --- Check 6: XPath references to non-existent fields ---
        for expr_col_name, expr_val in [("relevant", q_relevant), ("constraint", q_constraint), ("calculation", q_calculation)]:
            if expr_val:
                # Find all ${field_name} references
                refs = re.findall(r'\$\{([^}]+)\}', expr_val)
                for ref in refs:
                    if valid_names and ref not in valid_names:
                        issues.append({
                            "severity": "High",
                            "sheet": "survey",
                            "row": row_num,
                            "column": expr_col_name,
                            "message": f"'{expr_col_name}' references ${{'{ref}'}} which does not exist as a question name.",
                            "suggestion": f"Check the spelling of '{ref}' — it must exactly match a 'name' value in the survey sheet."
                        })

        # --- Check 6b: Square brackets instead of curly braces — $[field] vs ${field} ---
        # In relevant/constraint/calculation: pyxform passes but ODK Validate (Java layer)
        # rejects it with a cryptic "Couldn't understand the expression" message.
        # In label/hint: the form deploys fine but the app shows the literal text
        # "$[field]" instead of the actual field value — a silent display bug.
        for expr_col_name, expr_val in [("relevant", q_relevant), ("constraint", q_constraint), ("calculation", q_calculation)]:
            if expr_val:
                bad_refs = re.findall(r'\$\[([^\]]+)\]', expr_val)
                for bad_ref in bad_refs:
                    issues.append({
                        "severity": "High",
                        "sheet": "survey",
                        "row": row_num,
                        "column": expr_col_name,
                        "message": (
                            f"The {expr_col_name} expression contains '$[{bad_ref}]' — "
                            f"square brackets are not valid ODK syntax. "
                            f"ODK will reject this form with a confusing error message."
                        ),
                        "suggestion": (
                            f"Change $[{bad_ref}] to ${{{bad_ref}}}. "
                            f"Field references in ODK always use curly braces: ${{field_name}}."
                        )
                    })

        for col_name in label_hint_cols:
            cell_val = str(row.get(col_name, "")).strip()
            if cell_val:
                bad_refs = re.findall(r'\$\[([^\]]+)\]', cell_val)
                for bad_ref in bad_refs:
                    issues.append({
                        "severity": "High",
                        "sheet": "survey",
                        "row": row_num,
                        "column": col_name,
                        "message": (
                            f"The {col_name} column contains '$[{bad_ref}]' — "
                            f"square brackets are not valid ODK syntax for field references. "
                            f"The form will deploy, but the app will show the literal text "
                            f"'$[{bad_ref}]' instead of the actual value of '{bad_ref}'."
                        ),
                        "suggestion": (
                            f"Change $[{bad_ref}] to ${{{bad_ref}}}. "
                            f"Field references in ODK always use curly braces: ${{field_name}}."
                        )
                    })

        # --- Check 6c: ${field} inside HTML tags in labels / hints ---
        # XLSForm labels and hints support some HTML styling (e.g. <span>, <b>, <font>).
        # But when ${field_name} appears inside an HTML tag — either inside a tag's
        # attribute area (<span style="...${x}...">) or between an opening and closing
        # tag (<span>${x}</span>) — ODK does NOT perform variable substitution. The
        # respondent sees the literal text "${field_name}". pyxform silently accepts
        # this and reports no warning, so this check catches it explicitly.
        for col_name in label_hint_cols:
            cell_val = str(row.get(col_name, "")).strip()
            if not cell_val or '${' not in cell_val or '<' not in cell_val:
                continue
            flagged_refs_in_cell = set()
            for ref_match in re.finditer(r'\$\{([^}]+)\}', cell_val):
                ref_name = ref_match.group(1)
                if ref_name in flagged_refs_in_cell:
                    continue
                text_before = cell_val[:ref_match.start()]
                text_after = cell_val[ref_match.end():]

                # Case A: inside an HTML tag's attribute area
                # (unclosed '<' before the reference with no intervening '>')
                last_lt = text_before.rfind('<')
                last_gt = text_before.rfind('>')
                inside_attr = last_lt >= 0 and last_lt > last_gt

                # Case B: wrapped between an opening tag and a closing tag
                wrapped_tag = None
                if not inside_attr:
                    open_match = re.search(
                        r'<([a-zA-Z][a-zA-Z0-9]*)(?:\s[^>]*)?>[^<]*$', text_before
                    )
                    close_match = re.search(
                        r'^[^<]*</([a-zA-Z][a-zA-Z0-9]*)\s*>', text_after
                    )
                    if open_match and close_match:
                        wrapped_tag = open_match.group(1)

                if inside_attr or wrapped_tag:
                    flagged_refs_in_cell.add(ref_name)
                    if wrapped_tag:
                        where = f"inside an HTML <{wrapped_tag}> tag"
                    else:
                        where = "inside an HTML tag's attribute"
                    issues.append({
                        "severity": "High",
                        "sheet": "survey",
                        "row": row_num,
                        "column": col_name,
                        "message": (
                            f"The {col_name} column contains ${{{ref_name}}} {where}. "
                            f"ODK does not substitute ${{...}} references that are wrapped "
                            f"in HTML — the app will show the literal text '${{{ref_name}}}' "
                            f"instead of the actual value of '{ref_name}'. "
                            f"pyxform does NOT warn about this."
                        ),
                        "suggestion": (
                            f"Move ${{{ref_name}}} outside of the HTML tag. For example, "
                            f"replace '<span style=\"...\">${{{ref_name}}}</span>' with "
                            f"'${{{ref_name}}}' on its own, or use ODK's supported markdown "
                            f"syntax for styling (e.g. **bold**, _italic_, # heading) which "
                            f"does not interfere with variable substitution."
                        )
                    })

        # --- Check 7: Common XPath mistakes ---
        for expr_col_name, expr_val in [("relevant", q_relevant), ("constraint", q_constraint), ("calculation", q_calculation)]:
            if expr_val:
                # Using = instead of selected() when referencing a select_multiple field.
                # ${field} = 'value' works only when exactly one option is selected.
                # When multiple options are selected the stored value is space-separated
                # (e.g. "fever cough"), so = 'fever' will silently return false.
                # This is not a hard error — flag as Medium warning.
                refs = re.findall(r'\$\{([^}]+)\}', expr_val)
                for ref in refs:
                    if ref in select_multiple_names:
                        eq_pattern = re.compile(
                            r'(\$\{' + re.escape(ref) + r'\}\s*[!]?=|[!]?=\s*\$\{' + re.escape(ref) + r'\})'
                        )
                        if eq_pattern.search(expr_val):
                            issues.append({
                                "severity": "Medium",
                                "sheet": "survey",
                                "row": row_num,
                                "column": expr_col_name,
                                "message": (
                                    f"The {expr_col_name} expression uses '${{{{ref}}}}' with '=' but '{ref}' is a "
                                    f"select_multiple question. "
                                    f"This works only if the respondent picks exactly one option — if they pick "
                                    f"more than one, the comparison will silently fail."
                                ).replace("{ref}", ref),
                                "suggestion": (
                                    f"Use selected(${{{ref}}}, 'value') instead of ${{{ref}}} = 'value'. "
                                    f"The selected() function correctly checks whether a specific option was chosen, "
                                    f"regardless of how many options were selected."
                                )
                            })

                # Using / instead of div for division.
                # / is a valid XPath path separator (e.g. instance('x')/root/item) so we
                # only flag it when it appears between two operands that look like numbers
                # or ${field} references, which unambiguously means division was intended.
                # At runtime, ODK silently produces an empty or wrong result — no error shown.
                div_pattern = re.compile(
                    r'(\$\{[^}]+\}|\d+\.?\d*)\s*/\s*(\$\{[^}]+\}|\d+\.?\d*)'
                )
                for m in div_pattern.finditer(expr_val):
                    issues.append({
                        "severity": "High",
                        "sheet": "survey",
                        "row": row_num,
                        "column": expr_col_name,
                        "message": (
                            f"The {expr_col_name} expression uses '/' for division "
                            f"(near: '{m.group(0)}'). "
                            f"In ODK, '/' is not a division operator — it is a path separator used "
                            f"in XPath. The calculation will silently produce a wrong or empty result."
                        ),
                        "suggestion": (
                            f"Replace '/' with 'div'. "
                            f"For example: '{m.group(1).strip()} div {m.group(2).strip()}'. "
                            f"ODK arithmetic operators: + - * div mod."
                        )
                    })

                # Using % instead of mod for modulo.
                mod_pattern = re.compile(
                    r'(\$\{[^}]+\}|\d+\.?\d*)\s*%\s*(\$\{[^}]+\}|\d+\.?\d*)'
                )
                for m in mod_pattern.finditer(expr_val):
                    issues.append({
                        "severity": "High",
                        "sheet": "survey",
                        "row": row_num,
                        "column": expr_col_name,
                        "message": (
                            f"The {expr_col_name} expression uses '%' for modulo "
                            f"(near: '{m.group(0)}'). "
                            f"'%' is not a valid ODK operator and will cause an error."
                        ),
                        "suggestion": (
                            f"Replace '%' with 'mod'. "
                            f"For example: '{m.group(1).strip()} mod {m.group(2).strip()}'."
                        )
                    })

                # String concatenation with + instead of concat()
                if re.search(r"'\s*\+|\\+\s*'", expr_val):
                    issues.append({
                        "severity": "Medium",
                        "sheet": "survey",
                        "row": row_num,
                        "column": expr_col_name,
                        "message": f"Possible string concatenation with '+' in {expr_col_name} of '{q_name}'.",
                        "suggestion": "Use concat() for string joining: concat('text', ${field}, ' more text')"
                    })

        # --- Check 8: begin/end group/repeat balance ---
        if q_type.lower() in ("begin_group", "begin group", "begin_repeat", "begin repeat"):
            group_stack.append((q_name or q_type, row_num))
        elif q_type.lower() in ("end_group", "end group", "end_repeat", "end repeat"):
            if group_stack:
                group_stack.pop()
            # If stack is empty and we get an end — pyxform will catch this

    # Unclosed groups
    for (grp_name, grp_row) in group_stack:
        issues.append({
            "severity": "High",
            "sheet": "survey",
            "row": grp_row,
            "column": "type",
            "message": f"Group/repeat '{grp_name}' (started at row {grp_row}) is never closed with a matching end_group or end_repeat.",
            "suggestion": "Add an 'end_group' or 'end_repeat' row after the last question in this group."
        })

    # --- Choices sheet checks ---
    if choices is not None:
        list_name_col = next((c for c in choices.columns if c.lower() == "list_name"), None)
        name_col_ch = next((c for c in choices.columns if c.lower() == "name"), None)
        label_col_ch = next((c for c in choices.columns if "label" in c.lower()), None)

        if list_name_col and name_col_ch:
            # Duplicate choice names within a list
            seen = {}
            for idx, row in choices.iterrows():
                row_num = idx + 2
                lst = row[list_name_col].strip()
                nm = row[name_col_ch].strip()
                if not lst or not nm:
                    continue
                key = (lst, nm)
                if key in seen:
                    issues.append({
                        "severity": "High",
                        "sheet": "choices",
                        "row": row_num,
                        "column": "name",
                        "message": f"Choice name '{nm}' appears more than once in list '{lst}' (first at row {seen[key]}).",
                        "suggestion": f"Each choice in a list must have a unique name. Rename or remove the duplicate."
                    })
                else:
                    seen[key] = row_num

            # Missing labels in choices
            if label_col_ch:
                for idx, row in choices.iterrows():
                    row_num = idx + 2
                    nm = row[name_col_ch].strip()
                    lbl = row[label_col_ch].strip()
                    if nm and not lbl:
                        issues.append({
                            "severity": "Medium",
                            "sheet": "choices",
                            "row": row_num,
                            "column": "label",
                            "message": f"Choice '{nm}' in list '{row[list_name_col].strip()}' has no label.",
                            "suggestion": "Add a label so the option is readable in the survey app."
                        })

    return issues


def polishing_suggestions(sheets: dict):
    """
    Provide polishing ideas to improve the form beyond correctness.
    Returns a list of suggestion strings.
    """
    suggestions = []
    survey = sheets.get("survey")
    settings = sheets.get("settings")

    if survey is None:
        return suggestions

    cols = [c.lower() for c in survey.columns]

    # --- Check for hint column ---
    if not any("hint" in c for c in cols):
        suggestions.append(
            "**Add a 'hint' column**: Hints appear as grey text under questions in the app. "
            "They're very useful for explaining units (e.g., 'Enter weight in kg'), date formats, or instructions for sensitive questions."
        )

    # --- Check for constraint_message ---
    has_constraints = any(
        "constraint" in c and "message" not in c for c in cols
    )
    has_constraint_msg = any("constraint_message" in c for c in cols)
    if has_constraints and not has_constraint_msg:
        suggestions.append(
            "**Add a 'constraint_message' column**: You have constraints defined but no messages. "
            "When a respondent enters an invalid value, this message tells them what's expected — e.g., 'Age must be between 0 and 120'."
        )

    # --- Check language columns ---
    label_langs = [c for c in survey.columns if c.lower().startswith("label::")]
    if len(label_langs) > 1:
        # Check if hint has same languages
        hint_langs = [c for c in survey.columns if c.lower().startswith("hint::")]
        if len(hint_langs) < len(label_langs):
            suggestions.append(
                f"**Translate hint column**: You have labels in {len(label_langs)} languages but hints may be missing some translations. "
                "Consider adding hint translations so all language users get the same guidance."
            )
    elif not label_langs:
        suggestions.append(
            "**Consider adding language support**: If your form will be used in multiple languages, "
            "rename 'label' to 'label::English (en)' and add 'label::French (fr)' (or other languages) as additional columns."
        )

    # --- Check for required column ---
    if not any(c == "required" for c in cols):
        suggestions.append(
            "**Add a 'required' column**: Mark key questions as required (value: 'yes') so enumerators cannot skip critical data."
        )

    # --- Check settings sheet ---
    if settings is not None:
        settings_row = settings.iloc[0] if len(settings) > 0 else None
        if settings_row is not None:
            # Check version
            version_col = next((c for c in settings.columns if c.lower() == "version"), None)
            if not version_col or not str(settings_row.get(version_col, "")).strip():
                suggestions.append(
                    "**Add a form version in the settings sheet**: A version (e.g., '2024010101') helps track which version of the form data was collected with — important for research data quality."
                )
            # Check instance_name
            instance_col = next((c for c in settings.columns if c.lower() == "instance_name"), None)
            if not instance_col or not str(settings_row.get(instance_col, "")).strip():
                suggestions.append(
                    "**Set an instance_name in settings**: This controls how submitted records are named in your server. "
                    "Example: concat(${participant_id}, '-', ${date_of_interview}) makes each submission easy to identify."
                )
    else:
        suggestions.append(
            "**Add a 'settings' sheet**: Include form_title, form_id, default_language, and version. "
            "This is important for deploying the form correctly to ODK Central or KoboToolbox."
        )

    # --- Check for long labels ---
    label_col = next((c for c in survey.columns if c.lower() == "label" or c.lower().startswith("label::")), None)
    if label_col:
        long_labels = survey[survey[label_col].str.len() > 200]
        if len(long_labels) > 0:
            suggestions.append(
                f"**Shorten long question labels** ({len(long_labels)} labels exceed 200 characters): "
                "Very long labels are hard to read on small screens. Move extra context to the 'hint' column."
            )

    # --- Check for appearance column ---
    if not any(c == "appearance" for c in cols):
        suggestions.append(
            "**Consider an 'appearance' column**: Appearance options improve usability. "
            "Examples: 'minimal' (compact dropdowns), 'field-list' (show all questions in a group on one screen), "
            "'month-year' (date picker for month/year only), 'numbers' (numeric keyboard for text fields)."
        )

    return suggestions


def explain_pyxform_errors(errors: list, sheets: dict) -> list:
    """
    Translate each raw pyxform error into a plain-English explanation with row locations.
    Returns a list of dicts: {raw, plain_english, locations}
    """
    if not errors:
        return []

    survey = sheets.get("survey") if sheets else None

    explained = []

    for error_text in errors:
        plain = None
        locations = []

        # --- Pattern: Duplicate name ---
        # pyxform 4.x (name collision):   "[row : N] ... the 'name' value 'X' is invalid. Questions ... must be unique"
        # pyxform 4.x (reference collision): "[row : N] ... Reference variables names must be unique ... The name 'X' appears more than once."
        # pyxform older: "There are two survey elements named 'X'"
        m = re.search(r"The [Nn]ame '([^']+)' appears more than once", error_text)
        if not m:
            m = re.search(r"the 'name' value '([^']+)' is invalid.*unique", error_text, re.IGNORECASE | re.DOTALL)
        if not m:
            m = re.search(r"[Tt]here are two survey elements named '([^']+)'", error_text)
        if not m:
            m = re.search(r"[Dd]uplicate.*?'([^']+)'", error_text)
        if not m:
            m = re.search(r"'([^']+)' already exists", error_text)
        if m:
            dup_name = m.group(1).strip()
            plain = (
                f"Two questions in your survey share the same name '{dup_name}'. "
                f"ODK uses question names as variable names in your exported data — each must be unique, "
                f"just like column names in a spreadsheet. "
                f"Find both rows named '{dup_name}' below and rename one of them "
                f"(e.g. add a suffix like '{dup_name}_2', or use a more descriptive name)."
            )
            if survey is not None:
                name_col = next((c for c in survey.columns if c.lower() == "name"), None)
                if name_col:
                    matches = survey[survey[name_col].str.strip() == dup_name]
                    for idx in matches.index:
                        locations.append(f"survey sheet, row {idx + 2}: name = '{dup_name}'")

        # --- Pattern: Unknown question type ---
        if plain is None:
            m = re.search(r"[Uu]nknown question type '?([^'\n]+)'?", error_text)
            if m:
                bad_type = m.group(1).strip()
                plain = (
                    f"The type '{bad_type}' is not a recognised ODK question type. "
                    f"Common valid types are: text, integer, decimal, date, select_one <list_name>, "
                    f"select_multiple <list_name>, note, calculate, image, geopoint, begin_group / end_group, begin_repeat / end_repeat. "
                    f"Check for typos — the type must be spelled exactly as shown."
                )
                if survey is not None:
                    type_col = next((c for c in survey.columns if c.lower() == "type"), None)
                    if type_col:
                        matches = survey[survey[type_col].str.strip() == bad_type]
                        for idx in matches.index:
                            locations.append(f"survey sheet, row {idx + 2}: type = '{bad_type}'")

        # --- Pattern: List name not in choices ---
        if plain is None:
            m = re.search(r"[Ll]ist name not in choices:?\s*'?([^\n']+)'?", error_text)
            if m:
                bad_list = m.group(1).strip()
                plain = (
                    f"The choice list '{bad_list}' is referenced in the survey sheet but no choices with "
                    f"that list_name exist in the choices sheet. "
                    f"Go to your choices sheet and add rows with list_name = '{bad_list}', each with a name and label. "
                    f"Or, if it's a typo, fix the spelling in the type column of the survey sheet."
                )
                if survey is not None:
                    type_col = next((c for c in survey.columns if c.lower() == "type"), None)
                    if type_col:
                        matches = survey[survey[type_col].str.contains(bad_list, na=False, regex=False)]
                        for idx in matches.index:
                            locations.append(f"survey sheet, row {idx + 2}: references list '{bad_list}'")

        # --- Pattern: Unmatched begin / end group or repeat ---
        if plain is None:
            if re.search(r"[Uu]nmatched begin|[Mm]issing end|begin without.*end|end without.*begin", error_text, re.IGNORECASE):
                plain = (
                    "A group or repeat section is opened with begin_group (or begin_repeat) but is never closed "
                    "with a matching end_group (or end_repeat), or an end appears without a matching begin. "
                    "Every begin_group must be paired with exactly one end_group, and every begin_repeat with one end_repeat. "
                    "Count your begin and end rows carefully — they must balance."
                )
                if survey is not None:
                    type_col = next((c for c in survey.columns if c.lower() == "type"), None)
                    if type_col:
                        begins = survey[survey[type_col].str.lower().str.startswith("begin", na=False)]
                        ends = survey[survey[type_col].str.lower().str.startswith("end", na=False)]
                        locations.append(
                            f"Found {len(begins)} begin_group/begin_repeat rows and {len(ends)} end_group/end_repeat rows — these counts must match."
                        )

        # --- Pattern: $[field] square-bracket typo (ODK Validate error) ---
        if plain is None:
            square_refs = re.findall(r'\$\[([^\]]+)\]', error_text)
            if square_refs or (
                re.search(r"[Cc]ouldn't understand the expression", error_text) and '$[' in error_text
            ):
                if square_refs:
                    fixes = ", ".join(f"$[{r}] → ${{{r}}}" for r in square_refs)
                    plain = (
                        f"A field reference uses square brackets instead of curly braces: {fixes}. "
                        f"ODK requires curly braces for all field references. "
                        f"Find the relevant, constraint, or calculation column that contains this expression and correct the brackets."
                    )
                else:
                    plain = (
                        "A formula contains '$[...]' — square brackets are not valid ODK syntax for field references. "
                        "ODK requires curly braces: ${field_name}. "
                        "Find the relevant, constraint, or calculation column with '$[' and change it to '${...}'."
                    )
                if survey is not None:
                    for col_name in ["relevant", "constraint", "calculation"]:
                        col = next((c for c in survey.columns if c.lower() == col_name), None)
                        if col is not None:
                            matches = survey[survey[col].str.contains(r'\$\[', na=False, regex=True)]
                            for idx in matches.index:
                                locations.append(f"survey sheet, row {idx + 2}: {col_name} column")

        # --- Pattern: XPath / formula syntax error ---
        if plain is None:
            if re.search(r"[Xx][Pp]ath|formula|expression|invalid.*syntax|syntax.*error", error_text, re.IGNORECASE):
                plain = (
                    "There is a syntax error in a formula (in a relevant, constraint, or calculation column). "
                    "Common causes: using '/' instead of 'div' for division, mismatched parentheses, "
                    "or a ${field_name} reference that doesn't match any question name. "
                    f"Technical detail from validator: {error_text.strip()}"
                )

        # --- Pattern: Missing required column ---
        if plain is None:
            m = re.search(r"[Mm]issing required column[:\s]*'?([^\n']+)'?", error_text)
            if m:
                col_name = m.group(1).strip()
                plain = (
                    f"Your survey sheet is missing the required column '{col_name}'. "
                    f"Every XLSForm must have at minimum: a 'type' column, a 'name' column, and a 'label' column. "
                    f"Add a column named exactly '{col_name}' to the survey sheet."
                )

        # --- Fallback: show raw error with a plain wrapper ---
        if plain is None:
            plain = (
                f"The form validator reported: \"{error_text.strip()}\". "
                "This is a technical message. Check the row locations listed below, "
                "or share this error message for help identifying the cause."
            )

        explained.append({
            "raw": error_text.strip(),
            "plain_english": plain,
            "locations": locations
        })

    return explained


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python check_xlsform.py <path_to_xlsform.xlsx>"}))
        sys.exit(1)

    xlsform_path = Path(sys.argv[1])
    if not xlsform_path.exists():
        print(json.dumps({"error": f"File not found: {xlsform_path}"}))
        sys.exit(1)

    result = {
        "file": str(xlsform_path),
        "pyxform": {},
        "errors_explained": [],
        "extra_issues": [],
        "polishing": [],
    }

    # Step 1: Load sheets
    sheets, load_error = load_sheets(xlsform_path)
    if load_error:
        result["error"] = f"Could not read file: {load_error}"
        print(json.dumps(result, indent=2))
        sys.exit(1)

    # Step 2: Pyxform validation
    result["pyxform"] = run_pyxform_validation(xlsform_path)

    # Step 3: Translate pyxform errors into plain English with row locations
    result["errors_explained"] = explain_pyxform_errors(
        result["pyxform"].get("errors", []), sheets
    )

    # Step 4: Extra checks (run regardless of pyxform result)
    result["extra_issues"] = extra_checks(sheets)

    # Step 5: Polishing suggestions (only if pyxform passed)
    if result["pyxform"].get("valid"):
        result["polishing"] = polishing_suggestions(sheets)

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
