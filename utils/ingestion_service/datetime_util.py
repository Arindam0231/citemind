import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage
import re
from typing import Any
from agent.llm_utils import llm_service, llm_exec_with_retry


DATETIME_KEYWORDS = [
    "date",
    "time",
    "datetime",
    "timestamp",
    "created_at",
    "updated_at",
    "day",
    "week",
    "month",
    "year",
    "dt",
]

# ─────────────────────────────────────────────
# STEP 1: Detect if column NAMES are datetimes (wide/pivoted table)
# ─────────────────────────────────────────────


def _split_columns_by_datetime_name(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """
    Deterministically splits columns into (datetime_cols, id_cols)
    based on whether the column NAME itself looks like a date.
    """
    datetime_cols = []
    id_cols = []

    for col in df.columns:
        parsed = False
        try:
            pd.to_datetime(str(col))
            datetime_cols.append(col)
            parsed = True
        except Exception:
            pass

        if not parsed:
            id_cols.append(col)

    return datetime_cols, id_cols


def _llm_resolve_ambiguous_column_names(
    ambiguous_cols: list[str], target_format: str
) -> dict:
    """
    For column names pandas couldn't parse (e.g. 'week_3_2023', 'Q1_2023'),
    ask LLM if they are dates and get standardized versions.
    """
    if not ambiguous_cols:
        return {}

    prompt = f"""
These are column names from a dataframe that pandas could NOT parse as dates:
{ambiguous_cols}

For each column name, determine if it represents a date or time period 
(e.g. week numbers, quarters, named months, fiscal periods, etc.)

If YES → return the standardized date string in format: {target_format}
If NO  → return JSON null (not the string "null", actual null)

Rules:
- Return ONLY a valid JSON object, no explanation, no markdown, no code fences
- Keys must be the original column names exactly as provided
- Values must be date strings in format {target_format} or JSON null
- Reasoning must be no more than 2 sentences total, covering all columns

Return in this exact structure:
{{
    "response": {{"week_3_2023": "2023-01-16", "product_name": null}},
    "reasoning": "week_3_2023 represents the 3rd week of 2023 which maps to 2023-01-16. product_name is clearly a descriptive label not a date."
}}
"""
    response = llm_service([HumanMessage(content=prompt)])
    # TODO log response["reasoning"] for debugging
    response = (
        response["response"]
        if isinstance(response, dict) and "response" in response
        else {}
    )
    return {k: v for k, v in response.items() if v is not None}


def handle_wide_datetime_columns(
    df: pd.DataFrame, target_format: str = "%Y-%m-%d"
) -> tuple[pd.DataFrame, dict]:
    """
    If the dataframe is wide/pivoted (column names are dates),
    standardize column names and melt into long format.
    Returns (processed_df, report)
    """
    report = {"wide_format_detected": False}
    datetime_cols, id_cols = _split_columns_by_datetime_name(df)
    # Ask LLM about the ambiguous ones (id_cols might contain weird date formats)
    llm_resolved = _llm_resolve_ambiguous_column_names(id_cols, target_format)
    # Merge: pandas-detected + LLM-resolved
    all_datetime_cols = datetime_cols + list(llm_resolved.keys())
    true_id_cols = [c for c in id_cols if c not in llm_resolved]
    print("Initial datetime cols detected by pandas:", datetime_cols)
    print(all_datetime_cols, true_id_cols)

    # If datetime columns outnumber id columns → wide/pivoted table
    if len(all_datetime_cols) > len(true_id_cols):
        report["wide_format_detected"] = True
        report["id_cols"] = true_id_cols
        report["datetime_cols_found"] = all_datetime_cols

        # TODO: Build rename map and melt via LLM execution
        try:
            df, rename_map = _build_rename_and_melt_via_llm(
                df=df,
                datetime_cols=datetime_cols,
                llm_resolved=llm_resolved,
                true_id_cols=true_id_cols,
                all_datetime_cols=all_datetime_cols,
                target_format=target_format,
            )
        except Exception as e:
            print(
                f"[handle_wide_datetime_columns] LLM path failed: {e}, using fallback."
            )
            df, rename_map = _fallback_rename_and_melt(
                df=df,
                datetime_cols=datetime_cols,
                llm_resolved=llm_resolved,
                true_id_cols=true_id_cols,
                all_datetime_cols=all_datetime_cols,
                target_format=target_format,
            )

        report["melted_to_long"] = True
        report["rename_map"] = rename_map

    return df, report


def _build_rename_and_melt_via_llm(
    df: pd.DataFrame,
    datetime_cols: list,
    llm_resolved: dict,
    true_id_cols: list,
    all_datetime_cols: list,
    target_format: str,
) -> tuple[pd.DataFrame, dict]:

    # Pre-compute mixed column metadata so LLM sees exactly what
    # label text exists alongside each date — no data loss
    date_pattern = r"(\d{4}-\d{2}(?:-\d{2})?|[A-Za-z]{3,9}\s\d{4}|Q[1-4]\s?\d{4}|\d{4})"
    mixed_col_metadata = {}
    for col in all_datetime_cols:
        match = re.search(date_pattern, str(col))
        if match:
            label = re.sub(date_pattern, "", str(col)).strip(" _-")
            mixed_col_metadata[col] = {
                "extracted_date": match.group(),
                "label_text": label if label else None,
            }

    messages = [
        HumanMessage(
            content=f"""You are a Python data engineering assistant.

DataFrame columns     : {list(df.columns)}
datetime_cols         : {datetime_cols}
llm_resolved          : {llm_resolved}
true_id_cols          : {true_id_cols}
all_datetime_cols     : {all_datetime_cols}
target_format         : '{target_format}'

IMPORTANT - Mixed column metadata (date + extra label text detected per column):
{mixed_col_metadata}

This metadata shows every datetime column, the raw date portion extracted from it,
and the non-date label text found alongside it (e.g. 'Revenue', 'Budget', 'Actual').
Your function MUST preserve this label text — it is not noise, it is a dimension.
Zero data loss: every piece of information in the original column name must appear
in the output DataFrame, either as the 'date' column or the 'label' column.

Task:
Write a Python function called `build_rename_and_melt(df, datetime_cols, llm_resolved, true_id_cols, all_datetime_cols, target_format)` that:
1. Builds `rename_map` using the mixed_col_metadata above:
   - Map each original column → normalized date string in target_format
   - Where two columns share the same date but differ in label (e.g. 'Revenue 2024-01'
     and 'Cost 2024-01'), make column names unique using '__' separator: e.g. '2024-01-01__Revenue'
2. Also builds `label_map`: original_col → label_text (None if no label found)
3. Merges llm_resolved into rename_map
4. Renames df columns using rename_map
5. Melts df into long format with var_name='_col_key', value_name='value'
6. Splits '_col_key' back into 'date' and 'label' columns (splitting on '__')
7. Drops '_col_key' column
8. Returns tuple: (result_df, rename_map)

The output df must have columns: {true_id_cols} + ['date', 'column_suffix_label', 'value']
Uses ONLY pandas, re, and datetime standard libraries.

Return ONLY a valid JSON object, no explanation, no markdown, no code fences:
{{
    "response": "def build_rename_and_melt(df, datetime_cols, llm_resolved, true_id_cols, all_datetime_cols, target_format):\\n    ...",
    "reasoning": "2 sentence max explaining how mixed content columns are split and how label text is preserved without data loss."
}}"""
        )
    ]

    result_df, rename_map = llm_exec_with_retry(
        fn_name="build_rename_and_melt",
        messages=messages,
        fn_kwargs={
            "df": df.copy(),
            "datetime_cols": datetime_cols,
            "llm_resolved": llm_resolved,
            "true_id_cols": true_id_cols,
            "all_datetime_cols": all_datetime_cols,
            "target_format": target_format,
        },
        exec_globals={"pd": pd, "re": re},
        max_retries=3,
    )

    if result_df is None or not isinstance(result_df, pd.DataFrame):
        raise ValueError("LLM exec did not produce a valid result_df")

    return result_df, rename_map


def _fallback_rename_and_melt(
    df: pd.DataFrame,
    datetime_cols: list,
    llm_resolved: dict,
    true_id_cols: list,
    all_datetime_cols: list,
    target_format: str,
) -> tuple[pd.DataFrame, dict]:

    date_pattern = r"(\d{4}-\d{2}(?:-\d{2})?|[A-Za-z]{3,9}\s\d{4}|Q[1-4]\s?\d{4})"
    rename_map = {}
    label_map = {}

    for col in datetime_cols:
        match = re.search(date_pattern, str(col))
        if match:
            try:
                normalized = pd.to_datetime(match.group()).strftime(target_format)
            except Exception:
                normalized = str(col)
            label = re.sub(date_pattern, "", str(col)).strip(" _-")
            rename_map[col] = normalized
            label_map[normalized] = label or None
        else:
            rename_map[col] = str(col)

    rename_map.update(llm_resolved)
    df = df.rename(columns=rename_map)
    new_datetime_cols = [rename_map.get(c, c) for c in all_datetime_cols]

    df = df.melt(
        id_vars=true_id_cols,
        value_vars=new_datetime_cols,
        var_name="date",
        value_name="value",
    )

    if any(v for v in label_map.values()):
        df["label"] = df["date"].map(label_map)

    return df, rename_map


# ─────────────────────────────────────────────
# STEP 2: Detect datetime VALUE columns (normal tall/long table)
# ─────────────────────────────────────────────


def detect_datetime_value_columns(df: pd.DataFrame) -> list[str]:
    """
    Detect columns whose VALUES are datetimes, using:
    1. dtype check
    2. column name keyword check
    3. sampling fallback
    """
    datetime_cols = []

    for col in df.columns:
        # Already a datetime dtype
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            datetime_cols.append(col)
            continue

        # Column name contains datetime keywords
        if any(kw in col.lower() for kw in DATETIME_KEYWORDS):
            datetime_cols.append(col)
            continue

        # Fallback: try parsing a sample
        if df[col].dtype == object:
            sample = df[col].dropna().head(10)
            try:
                pd.to_datetime(sample)
                datetime_cols.append(col)
            except Exception:
                pass

    return datetime_cols


# ─────────────────────────────────────────────
# STEP 3: LLM parses & standardizes datetime VALUES
# ─────────────────────────────────────────────


def llm_parse_and_standardize_values(
    df: pd.DataFrame, col: str, target_format: str = "%Y-%m-%d %H:%M:%S"
) -> tuple[pd.Series, dict]:
    """Use LLM to generate and exec a parser for any datetime column format.

    Delegates code generation, safety checking, execution, and retry to
    ``llm_exec_with_retry``.  If the generated ``parse_dates`` function leaves
    more than 10 % of originally non-null values unparsed, a ``ValueError`` is
    raised inside the exec call so the wrapper feeds the failure back to the
    LLM for a corrected version.
    """
    import datetime as _datetime

    sample_values = (
        df[col]
        .dropna()
        .sample(min(15, len(df[col].dropna())), random_state=42)
        .tolist()
    )
    original_nulls = int(df[col].isna().sum())

    messages = [
        HumanMessage(
            content=f"""You are a data engineering assistant.

Column name: "{col}"
Sample values from this column:
{sample_values}

Task:
Write a Python function called `parse_dates(series: pd.Series) -> pd.Series` that:
1. Correctly parses ALL date/time formats present in these samples
2. Handles edge cases: week numbers, ordinal dates (1st, 2nd, 3rd),
   month names, weekday names, quarters, fiscal periods, mixed formats, etc.
3. Returns the series as strings in this EXACT target format: {target_format}
4. Sets unparseable or null values to None
5. Uses ONLY pandas and datetime standard libraries

Return ONLY a valid JSON object, no explanation, no markdown, no code fences:
{{
    "response": "def parse_dates(series: pd.Series) -> pd.Series:\\n    ...",
    "reasoning": "2 sentence max explaining what formats were detected and how they are handled."
}}"""
        )
    ]

    parsed_series: pd.Series = llm_exec_with_retry(
        fn_name="parse_dates",
        messages=messages,
        fn_kwargs={"series": df[col]},
        exec_globals={"pd": pd, "datetime": _datetime},
        max_retries=3,
    )
    new_nulls = int(parsed_series.isna().sum())
    failed_count = max(0, new_nulls - original_nulls)
    failure_rate = failed_count / max(len(df), 1)

    report = {
        "col": col,
        "sample_input": sample_values,
        "original_nulls": original_nulls,
        "failed_to_parse": failed_count,
        "failure_rate_pct": round(failure_rate * 100, 2),
        "target_format": target_format,
        "sample_output": parsed_series.dropna().head(3).tolist(),
    }

    return parsed_series, report


# ─────────────────────────────────────────────
# MASTER FUNCTION
# ─────────────────────────────────────────────


def process_datetimes(
    df: pd.DataFrame, target_format: str = "%Y-%m-%d %H:%M:%S"
) -> tuple[pd.DataFrame, dict]:
    """
    Master function that handles ALL datetime scenarios:

    1. Wide/pivoted table where column NAMES are dates → standardize + melt
    2. Normal table where column VALUES are dates → parse + standardize values

    Returns (processed_df, full_report)
    """
    full_report = {}

    # ── Step 1: Handle wide format (datetime column names) ──
    df, wide_report = handle_wide_datetime_columns(
        df, target_format=target_format.split(" ")[0]
    )  # date-only for col names
    full_report["wide_format"] = wide_report

    # ── Step 2: Handle datetime values in columns ──
    datetime_value_cols = detect_datetime_value_columns(df)
    full_report["datetime_value_columns"] = {}
    for col in datetime_value_cols:
        parsed_series, col_report = llm_parse_and_standardize_values(
            df, col, target_format
        )
        df[col] = parsed_series
        full_report["datetime_value_columns"][col] = col_report

    full_report["final_shape"] = df.shape
    full_report["final_columns"] = list(df.columns)
    full_report["datetime_cols_processed"] = datetime_value_cols
    return df, full_report
