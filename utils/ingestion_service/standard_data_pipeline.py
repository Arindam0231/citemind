from utils.ingestion_service.datetime_util import process_datetimes
from agent.llm_utils import llm_exec_with_retry, is_safe_code
from langchain_core.messages import HumanMessage, SystemMessage
import json
import pandas as pd
import logging
import numpy as np
import re


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("data_pipeline.log"),  # writes to file
        logging.StreamHandler(),  # also prints to console
    ],
)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _handle_hierarchical_columns(df):
    # ------------------------------------------------------------------
    # 1. Extract top-10 rows as the LLM context sample
    # ------------------------------------------------------------------
    raw_rows = df.iloc[:10].fillna("").values.tolist()

    # ------------------------------------------------------------------
    # 2. Build messages and delegate to llm_exec_with_retry
    # ------------------------------------------------------------------
    messages = [
        HumanMessage(
            content=f"""You are a data engineering assistant.

Here are the first 10 raw rows of a DataFrame that was read with header=None \
(so all rows, including any header rows, appear as plain data rows):
{json.dumps(raw_rows, indent=2)}

Task:
Analyse the rows above to detect:
- How many rows at the top are acting as headers (0, 1, or more)
- Whether the headers are hierarchical / multi-level

Then write a Python function called `flatten_columns(df: pd.DataFrame) -> pd.DataFrame` that:
1. Receives the FULL DataFrame (already read with header=None) as its only argument
2. Promotes the correct number of rows as the header (using iloc + set as columns)
   and drops those rows from the data
3. Flattens any hierarchical headers into clean, unique, lowercase snake_case names
   (join meaningful levels with `_`; skip filler values like "Unnamed", "nan", empty strings)
4. Strips whitespace from all column names
5. Resets the index and returns the resulting DataFrame

Rules:
- Use ONLY `pandas` (imported as `pd`) — no other dependencies
- Do NOT perform any file I/O (no pd.read_csv, open, etc.)
- Do NOT use os, subprocess, shutil, or __import__
- Return ONLY a valid JSON object with no markdown or code fences:
  {{"response": "def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:\\n    ...",
    "reasoning": "2-sentence explanation of what header structure was detected."}}"""
        )
    ]

    code_response = llm_exec_with_retry(
        fn_name="flatten_columns",
        messages=messages,
        fn_kwargs={"df": df},
        exec_globals={"pd": pd},
        max_retries=3,
    )
    df: pd.DataFrame = code_response["result"]
    reasoning = code_response["response"].get("reasoning", "")
    if not isinstance(df, pd.DataFrame):
        raise ValueError("flatten_columns did not return a pandas DataFrame.")
    return (df, reasoning)


def standardize_numerical_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Detects and standardizes all numerical columns including
    accounting notation, currency, percentages, and mixed types.
    Tries deterministic cleaning first, falls back to LLM only if it fails.
    """
    report = {
        "numerical_cols_processed": [],
        "conversions_applied": {},
        "llm_fallback_used": [],
    }

    # ── Pre-detect candidate columns ────────────────────
    candidate_cols = {}
    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna().astype(str).head(50)
            patterns = {
                "accounting": sample.str.match(r"^\([\d,\.]+\)$").any(),
                "currency": sample.str.match(r"^[$₹€£][\d,\.]+$").any(),
                "percentage": sample.str.match(r"^\d+\.?\d*%$").any(),
                "comma_num": sample.str.match(r"^\d{1,3}(,\d{3})*(\.\d+)?$").any(),
                "plain_num": sample.str.match(r"^-?\d+\.?\d*$").any(),
            }
            detected = [k for k, v in patterns.items() if v]
            if detected:
                candidate_cols[col] = {
                    "detected_patterns": detected,
                    "sample_values": sample.tolist()[:10],
                }

    if not candidate_cols:
        return df, report

    # ── Deterministic cleaner ────────────────────────────
    def clean_value(val) -> float | None:
        if not isinstance(val, str):
            return val
        val = val.strip()
        if not val:
            return None

        # accounting: (2933.93) → -2933.93
        if re.match(r"^\([\d,\.]+\)$", val):
            val = "-" + val[1:-1]

        # currency: strip symbols
        val = re.sub(r"[$₹€£]", "", val).strip()

        # percentage: 45% → 0.45
        if val.endswith("%"):
            try:
                return float(val[:-1]) / 100
            except:
                return None

        # thousands commas
        val = val.replace(",", "")

        try:
            result = float(val)
            return None if np.isinf(result) else result
        except:
            return None

    # ── Try deterministic, track failures ───────────────
    failed_cols = {}

    for col, meta in candidate_cols.items():
        try:
            original_null_pct = df[col].isnull().mean()
            cleaned = df[col].astype(str).apply(clean_value)
            new_null_pct = cleaned.isnull().mean()

            # Quality gate — >30% new nulls means patterns not fully handled
            if new_null_pct > original_null_pct + 0.3:
                failed_cols[col] = {
                    **meta,
                    "failure_reason": f"null_pct jumped {original_null_pct:.2f} → {new_null_pct:.2f}",
                }
            else:
                df[col] = cleaned
                report["conversions_applied"][col] = meta["detected_patterns"]
                report["numerical_cols_processed"].append(col)

        except Exception as e:
            failed_cols[col] = {**meta, "failure_reason": str(e)}

    # ── LLM fallback — only for genuinely failed cols ───
    if failed_cols:
        print("Deterministic cleaning failed for columns:", list(failed_cols.keys()))
        messages = [
            HumanMessage(
                content=f"""You are a Python data engineering assistant.
These numerical columns failed standard cleaning — handle their specific edge cases.

Failed columns with sample values and failure reasons:
{failed_cols}

Write a Python function called `standardize_numerical(df, candidate_cols)` that:
1. For each column in candidate_cols:
   - Strips currency symbols: $, ₹, €, £
   - Converts accounting negatives: (2933.93) → -2933.93
   - Removes thousands commas: 1,000,000 → 1000000
   - Converts percentages: 45% → 0.45
   - Handles scientific notation: 1.2e6 → 1200000.0
   - Replaces inf/-inf with None
   - Strips whitespace
   - Converts to float, sets unparseable values to None
   - Handles any additional edge cases visible in the sample values
2. Replaces original column in df with cleaned float Series
3. Returns tuple: (df, conversions_applied)
   where conversions_applied is dict of {{col: list_of_patterns_applied}}
Uses ONLY pandas, re, and numpy.
Return ONLY valid JSON, no markdown, no code fences:
{{
    "response": "def standardize_numerical(df, candidate_cols):\\n    ...",
    "reasoning": "2 sentence max explaining the approach."
}}"""
            )
        ]

        try:
            code_response = llm_exec_with_retry(
                fn_name="standardize_numerical",
                messages=messages,
                fn_kwargs={"df": df.copy(), "candidate_cols": failed_cols},
                exec_globals={"pd": pd, "re": re, "np": np},
                max_retries=3,
            )
            llm_conversions = code_response["response"].get("reasoning", "")
            df = code_response["result"]
            report["conversions_applied"].update(llm_conversions)
            report["numerical_cols_processed"].extend(list(failed_cols.keys()))
            report["llm_fallback_used"] = list(failed_cols.keys())

        except Exception as e:
            # LLM also failed — log and move on, don't crash ingestion
            report["conversions_applied"].update(
                {
                    col: {"error": f"both deterministic and LLM failed: {str(e)}"}
                    for col in failed_cols
                }
            )

    return df, report


def standardize_categorical_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Detects and standardizes all categorical columns including
    casing, null-likes, booleans, encoding artifacts, and whitespace.
    """
    report = {"categorical_cols_processed": [], "flags": {}}

    # Pre-detect categorical columns and their characteristics
    candidate_cols = {}
    NULL_LIKES = {"na", "n/a", "none", "null", "-", "--", "nan", "nil", ""}
    BOOL_LIKES = {"yes", "no", "y", "n", "true", "false", "1", "0"}

    for col in df.columns:
        if df[col].dtype == object:
            sample = df[col].dropna().astype(str).head(50)
            unique_vals = df[col].dropna().astype(str).unique()
            lower_vals = set(v.strip().lower() for v in unique_vals)

            characteristics = {
                "sample_values": sample.tolist()[:10],
                "unique_count": int(df[col].nunique()),
                "has_null_likes": bool(lower_vals & NULL_LIKES),
                "has_bool_likes": bool(lower_vals & BOOL_LIKES),
                "has_mixed_casing": len(set(v.lower() for v in unique_vals))
                < len(unique_vals),
                "has_whitespace": any(v != v.strip() for v in unique_vals),
                "high_cardinality": df[col].nunique() > 50,
                "null_like_values": list(lower_vals & NULL_LIKES),
            }
            candidate_cols[col] = characteristics

    if not candidate_cols:
        return df, report

    messages = [
        HumanMessage(
            content=f"""You are a Python data engineering assistant.

Candidate categorical columns and their characteristics:
{candidate_cols}

Task:
Write a Python function called `standardize_categorical(df, candidate_cols)` that:
1. For each column in candidate_cols:
   - Strip leading/trailing whitespace, normalize internal whitespace to single space
   - Fix encoding artifacts using str.encode('latin1').decode('utf-8') where applicable
   - Convert null-like strings to None: {list({"na","n/a","none","null","-","--","nan","nil",""})}
   - Unify boolean-like strings → 'True'/'False':
     yes/y/true/1 → 'True', no/n/false/0 → 'False'
   - Normalize casing: strip + title case as default unless column looks like codes/IDs
   - For high_cardinality=True columns: apply only null-like and whitespace fixes,
     skip casing normalization, add col to flags dict with reason 'high_cardinality'
2. Returns tuple: (df, flags)
   where flags is dict of {{col: reason}} for any columns that were skipped or need review

Uses ONLY pandas and standard libraries.

Return ONLY a valid JSON object, no explanation, no markdown, no code fences:
{{
    "response": "def standardize_categorical(df, candidate_cols):\\n    ...",
    "reasoning": "2 sentence max explaining the approach."
}}"""
        )
    ]

    code_response = llm_exec_with_retry(
        fn_name="standardize_categorical",
        messages=messages,
        fn_kwargs={"df": df.copy(), "candidate_cols": candidate_cols},
        exec_globals={"pd": pd, "re": re},
        max_retries=3,
    )
    flags = code_response["response"].get("reasoning", "")
    df = code_response["result"]

    report["categorical_cols_processed"] = list(candidate_cols.keys())
    report["flags"] = flags
    return df, report


def standard_data_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    standard_data_report = {}
    # Step 1: Handle hierarchical columns
    df, _hierarchy_report = _handle_hierarchical_columns(df)
    standard_data_report["Hierarchy report"] = _hierarchy_report

    if isinstance(df, pd.DataFrame) and not df.empty:
        logger.debug("Hierarchical columns processed successfully.")

    # Step 2: Clean numeric columns (accounting notation, currency, % etc.)
    df, _numerical_report = standardize_numerical_columns(df)
    standard_data_report["Numerical Report"] = _numerical_report
    print(
        f"Numerical columns processed: {_numerical_report['numerical_cols_processed']}"
    )
    if isinstance(df, pd.DataFrame) and not df.empty:
        logger.debug("Numerical columns processed successfully.")

    # Step 3: Clean categorical columns (casing, nulls, booleans, encoding)
    df, _categorical_report = standardize_categorical_columns(df)
    print(
        f"Categorical columns processed: {_categorical_report['categorical_cols_processed']}"
    )
    standard_data_report["Categorical Report"] = _categorical_report
    if isinstance(df, pd.DataFrame) and not df.empty:
        logger.debug("Categorical columns processed successfully.")
    # Step 4: Process datetime columns
    df, _datetime_report = process_datetimes(df)
    standard_data_report["Date Time Report"] = _datetime_report
    print(f"Datetime columns processed: {_datetime_report['datetime_cols_processed']}")
    if isinstance(df, pd.DataFrame) and not df.empty:
        logger.debug("Datetime columns processed successfully.")

    # TODO create comparison of two dataframes.
    # TODO to explain report using LLM to user as a message
    # TODO Convert standard data pipeline into an AI Agent, with all these tools

    return df, standard_data_report
