import pandas as pd
import numpy as np
from typing import Dict, Any, List, TypedDict, Optional
import re
from pathlib import Path
from agent.llm_utils import llm_service, llm_exec_with_retry
from utils.ingestion_service.standard_data_pipeline import standard_data_pipeline
from utils.ingestion_service.processed_registry import ParquetRegistry
from langchain_core.messages import HumanMessage, SystemMessage
import json


class IngestedMetadata(TypedDict):
    """Structured metadata for ingested dataframes"""

    Path: str  # Original file path
    sheet_name: Optional[str]  # For Excel files, the sheet name; else None
    LLMInsights: Optional[Dict[str, str]]  # Column name to inferred definition
    BaseProfile: Dict[str, Any]  # Basic profile info (row count, column count, etc.)
    ColumnProfiles: Dict[str, Dict[str, Any]]  # Detailed profile for each column
    CategoricalInsights: Dict[str, Dict[str, Any]]  # Insights for categorical columns
    SavedParquetPath: str


class DataIngestionService:
    """Service for handling data upload, parsing, and profiling"""

    def __init__(self, index_filepath=None):
        self.processed_registry = ParquetRegistry()
        self.index_filepath = index_filepath

    def register_data(self, user_id: str, data_paths: Dict[str, str]) -> Dict[str, Any]:
        """Register dataframes from provided paths and generate metadata"""
        df_registry = {}
        for identifier, path in data_paths.items():
            df_registry[f"{identifier}"] = []
            try:
                pre_data_snippets = self.parse_file(path)
                for key, value in pre_data_snippets.items():
                    if isinstance(value, pd.DataFrame):
                        processed_id, processed_df = self.peek_and_transform(
                            value, path, sheet_name=key, user_id=user_id
                        )
                        profile = self.profile_dataframe(processed_df)
                        column_types = self.detect_column_types(processed_df)
                        categorical_insights = self.gather_categorical_insights(
                            processed_df, column_types
                        )
                        llm_insights = self.get_llm_insights(processed_df)
                        df_registry[f"{identifier}"].append(
                            IngestedMetadata(
                                Path=path,
                                sheet_name=key,
                                LLMInsights=llm_insights,
                                BaseProfile=profile,
                                ColumnProfiles=column_types,
                                CategoricalInsights=categorical_insights,
                                SavedParquetPath=processed_id,
                            )
                        )

            except Exception as e:
                # TODO log the error with more context
                print(f"Error processing {identifier} at {path}: {e}")
                df_registry[identifier] = False

        return df_registry

    def parse_file(self, file_path: str) -> pd.DataFrame:
        """Parse uploaded file into DataFrame"""
        file_ext = Path(file_path).suffix.lower()

        try:
            if file_ext == ".csv":
                df = pd.read_csv(file_path, header=None)
                response = {"default": df}
            elif file_ext in [".xlsx", ".xls"]:
                response = pd.read_excel(
                    file_path, sheet_name=None, header=None, engine="openpyxl"
                )
            elif file_ext == ".json":
                df = pd.read_json(file_path)
                if not isinstance(df, pd.DataFrame):
                    raise ValueError(
                        f"File did not produce a tabular DataFrame: {file_path}"
                    )
                response = {"default": df}
            elif file_ext == ".parquet":
                df = pd.read_parquet(file_path)
                if not isinstance(df, pd.DataFrame):
                    raise ValueError(
                        f"File did not produce a tabular DataFrame: {file_path}"
                    )
                response = {"default": df}
            else:
                raise ValueError(f"Unsupported file format: {file_ext}")

            return response
        except Exception as e:
            raise Exception(f"Error parsing file: {str(e)}")

    def profile_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate comprehensive profile of the dataframe"""
        profile = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": {},
            "missing_values": {},
            "data_types": {},
        }

        for col in df.columns:
            profile["columns"][col] = {
                "dtype": str(df[col].dtype),
                "unique_count": df[col].nunique(),
                "missing_count": df[col].isna().sum(),
                "missing_percentage": (df[col].isna().sum() / len(df)) * 100,
            }

            # Add statistics for numeric columns
            if pd.api.types.is_numeric_dtype(df[col]):
                profile["columns"][col].update(
                    {
                        "mean": (
                            float(df[col].mean()) if not df[col].isna().all() else None
                        ),
                        "median": (
                            float(df[col].median())
                            if not df[col].isna().all()
                            else None
                        ),
                        "std": (
                            float(df[col].std()) if not df[col].isna().all() else None
                        ),
                        "min": (
                            float(df[col].min()) if not df[col].isna().all() else None
                        ),
                        "max": (
                            float(df[col].max()) if not df[col].isna().all() else None
                        ),
                    }
                )

        return profile

    def detect_column_types(self, df: pd.DataFrame) -> Dict[str, str]:
        """Intelligently detect column types"""
        column_types = {}

        for col in df.columns:
            # Skip if mostly null
            if df[col].isna().sum() / len(df) > 0.9:
                column_types[col] = "unknown"
                continue

            # Check for datetime
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                column_types[col] = "datetime"
                continue
            if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(
                df[col]
            ):
                # Try to convert to datetime
                try:
                    pd.to_datetime(df[col].dropna().head(100))
                    column_types[col] = "datetime"
                    continue
                except:
                    pass

            # Check for numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                unique_ratio = df[col].nunique() / len(df)

                # If few unique values, it's categorical
                if df[col].nunique() < 20 or unique_ratio < 0.05:
                    column_types[col] = "categorical_numeric"
                else:
                    column_types[col] = "continuous"
                continue

            # Check for categorical
            unique_ratio = df[col].nunique() / len(df)
            if unique_ratio < 0.5:
                column_types[col] = "categorical"
            else:
                # Check for special types
                sample = df[col].dropna().astype(str).head(100)

                if self._is_email(sample):
                    column_types[col] = "email"
                elif self._is_url(sample):
                    column_types[col] = "url"
                elif self._is_phone(sample):
                    column_types[col] = "phone"
                else:
                    column_types[col] = "text"

        return column_types

    def _is_email(self, series: pd.Series) -> bool:
        """Check if series contains emails"""
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        matches = series.str.match(email_pattern).sum()
        return matches / len(series) > 0.8

    def _is_url(self, series: pd.Series) -> bool:
        """Check if series contains URLs"""
        url_pattern = r"^https?://"
        matches = series.str.match(url_pattern).sum()
        return matches / len(series) > 0.8

    def _is_phone(self, series: pd.Series) -> bool:
        """Check if series contains phone numbers"""
        phone_pattern = r"^[\d\s\-\+\(\)]+$"
        matches = series.str.match(phone_pattern).sum()
        return matches / len(series) > 0.8

    def peek_and_transform(
        self,
        peek_df: pd.DataFrame,
        original_filename: str,
        sheet_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """Transform a raw header=None DataFrame using LLM-guided header detection.

        The caller is responsible for reading the file with ``header=None`` and
        for any downstream saving. This method handles only structural cleaning
        and datetime standardisation.

        Steps performed:
        1. Take the first 10 rows of ``peek_df`` as a sample to send to the LLM.
        2. The LLM detects header count and hierarchy, then returns a Python
           function ``flatten_columns(df: pd.DataFrame) -> pd.DataFrame`` that
           operates on the full in-memory DataFrame.
        3. Validate the generated code with ``is_safe_code`` and execute it in
           a sandboxed ``exec`` environment, passing ``peek_df`` directly.
        4. Standardise all datetime columns via ``process_datetimes``.

        Parameters
        ----------
        peek_df:
            Full DataFrame already read with ``header=None``. The first 10 rows
            are used as context for the LLM; the entire DataFrame is transformed.

        Returns
        -------
        pd.DataFrame
            Cleaned DataFrame with flat column names and standardised dates.

        Raises
        ------
        ValueError
            If the LLM returns unsafe or malformed code.
        """
        try:

            # ------------------------------------------------------------------
            # 4. Standardise datetime columns via datetime_util
            # ------------------------------------------------------------------
            df = standard_data_pipeline(peek_df)
            # TODO log datetime report
            saved_id = self.processed_registry.register(
                df, original_filename, sheet_name, user_id=user_id
            )
            return (saved_id, df)

        except Exception as exc:
            raise ValueError(f"peek_and_transform failed: {exc}") from exc

    def get_categorical_insights(self, df: pd.DataFrame, column):
        """Return insights for a categorical column.

        The returned dict contains counts, percentages, top values, missing info,
        uniqueness/cardinality signals and a few sample unique values.

        Raises
        ------
        ValueError
            If the column is not present or does not appear to be categorical.
        """
        if column not in df.columns:
            raise ValueError(f"Column '{column}' not found in dataframe")

        series = df[column]
        total = len(series)
        missing_count = int(series.isna().sum())
        missing_percentage = (missing_count / total * 100) if total > 0 else 0.0
        unique_count = int(series.nunique(dropna=True))
        unique_ratio = (unique_count / total) if total > 0 else 0.0

        # Decide if the column is categorical-like
        is_categorical_dtype = isinstance(series.dtype, pd.CategoricalDtype)
        is_object_dtype = pd.api.types.is_object_dtype(series)
        # treat as categorical if dtype is categorical/object or low cardinality
        categorical_like = (
            is_categorical_dtype
            or is_object_dtype
            or unique_ratio < 0.5
            or unique_count < 50
        )

        if not categorical_like:
            raise ValueError(f"Column '{column}' does not appear to be categorical")

        # Value counts including NaNs
        counts = series.value_counts(dropna=False)

        # Compose top values list (value, count, percentage)
        top_n = 10
        top_values = []
        for val, cnt in counts.head(top_n).items():
            pct = (int(cnt) / total * 100) if total > 0 else 0.0
            top_values.append(
                {
                    "value": None if pd.isna(val) else val,
                    "count": int(cnt),
                    "percentage": round(pct, 2),
                }
            )

        # High-cardinality heuristic: many unique values
        high_cardinality = unique_count > max(50, 0.1 * total)

        # Full unique values (stringified) for downstream semantic search
        unique_values = [str(x) for x in pd.Series(series.dropna().unique())]

        # Full value counts (including NaNs) as list of dicts for complete insights
        value_counts = []
        for val, cnt in counts.items():
            pct = (int(cnt) / total * 100) if total > 0 else 0.0
            value_counts.append(
                {
                    "value": None if pd.isna(val) else val,
                    "count": int(cnt),
                    "percentage": round(pct, 2),
                }
            )

        # Detect whether category values are numeric-like (e.g., encoded numbers)
        non_null = series.dropna().astype(str)
        if len(non_null) > 0:
            num_converted = pd.to_numeric(non_null, errors="coerce").notna().sum()
            numeric_like_ratio = num_converted / len(non_null)
        else:
            numeric_like_ratio = 0.0
        numeric_like = numeric_like_ratio > 0.8

        insights: Dict[str, Any] = {
            "column": column,
            "total": int(total),
            "missing_count": missing_count,
            "missing_percentage": round(missing_percentage, 2),
            "unique_count": unique_count,
            "unique_ratio": round(unique_ratio, 4),
            "high_cardinality": bool(high_cardinality),
            "numeric_like": bool(numeric_like),
            "numeric_like_ratio": round(numeric_like_ratio, 4),
            "top_values": top_values,
            "unique_values": unique_values,
            "value_counts": value_counts,
        }

        return insights

    def get_llm_insights(self, df: pd.DataFrame):
        snippet = {}
        for column in df.columns:
            snippet[column] = {
                "dtype": str(df[column].dtype),
                "unique_count": df[column].nunique(),
                "missing_count": df[column].isna().sum(),
                "values": df[column].dropna().unique().tolist()[:10],
            }
        messages = [
            SystemMessage(
                content='You are a data analyst. Given column metadata, return a JSON object in this exact format: {"data": {"column_name": "description", ...}, "reasoning": "brief explanation of how you inferred the definitions"}'
            ),
            HumanMessage(
                content=f"Here is the column metadata:\n\n{json.dumps(snippet, indent=2, default=str)}\n\nReturn only the JSON object with no extra text."
            ),
        ]

        response = llm_service(messages)

        # TODO  logging response reasoning
        check_response = response.get("data", False)
        if not check_response:
            raise ValueError("LLM did not return expected 'data' field in response")
        return response["data"]

    def gather_categorical_insights(
        self, df: pd.DataFrame, column_types: Dict[str, str]
    ):
        """Gather insights for all categorical columns and return as dict"""
        insights = {}
        for col, col_type in column_types.items():
            if col_type in ["categorical", "categorical_numeric"]:
                try:
                    insights[col] = self.get_categorical_insights(df, col)
                except Exception as e:
                    insights[col] = {"error": str(e)}
        return insights
