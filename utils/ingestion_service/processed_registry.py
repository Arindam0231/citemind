import uuid
import json
import hashlib
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List


class ParquetRegistry:
    """
    Manages processed parquet files with UUID-based storage.

    Every upload always gets a new UUID — even if the same file
    is uploaded again. Use file_hash to detect duplicates if needed.

    Directory structure:
        processed/
            registry.json
            <uuid>.parquet
            <uuid>.parquet
    """

    def __init__(self, base_dir: str = "processed"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.base_dir / "registry.json"
        self._load()

    # ------------------------------------------------------------------ #
    #  Internal helpers
    # ------------------------------------------------------------------ #

    def _load(self):
        """Load registry from disk, or start fresh."""
        if self.registry_path.exists():
            self.registry: Dict[str, Any] = json.loads(
                self.registry_path.read_text(encoding="utf-8")
            )
        else:
            self.registry = {}

    def _save(self):
        """Persist registry to disk."""
        self.registry_path.write_text(
            json.dumps(self.registry, indent=2, default=str),
            encoding="utf-8",
        )

    def _new_uuid(self) -> str:
        """
        Generate a UUID4 guaranteed to not already exist
        as a parquet file or registry entry.
        Collision is astronomically rare but we check anyway.
        """
        while True:
            candidate = str(uuid.uuid4())
            parquet_path = self.base_dir / f"{candidate}.parquet"

            if candidate not in self.registry and not parquet_path.exists():
                return candidate

            # If we ever reach here, something very unusual is happening
            print(
                f"[ParquetRegistry] UUID collision detected: {candidate}, regenerating..."
            )

    @staticmethod
    def _hash_df(df: pd.DataFrame) -> str:
        """
        Compute a stable hash of the dataframe content.
        Useful for detecting if the same data was uploaded twice
        WITHOUT blocking the new registration (we still create a new UUID).
        """
        return hashlib.md5(
            pd.util.hash_pandas_object(df, index=True).values.tobytes()
        ).hexdigest()

    # ------------------------------------------------------------------ #
    #  Core API
    # ------------------------------------------------------------------ #

    def register(
        self,
        df: pd.DataFrame,
        original_filename: str,
        sheet_name: Optional[str] = None,
        transformations_applied: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Save a processed dataframe as a new parquet file and record it
        in the registry. Always creates a new UUID — never overwrites.

        Parameters
        ----------
        df                    : Cleaned/transformed dataframe to persist
        original_filename     : The name the user uploaded (e.g. "Sales Q1.xlsx")
        transformations_applied: List of transformation labels applied
        user_id               : Optional user scoping (multi-user apps)
        extra_meta            : Any additional metadata to store

        Returns
        -------
        file_id (UUID string)
        """
        file_id = self._new_uuid()
        parquet_path = self.base_dir / f"{file_id}.parquet"
        # Last line of defense — _new_uuid already checks this,
        # but we guard again in case of any race condition or inconsistency
        if parquet_path.exists():
            raise RuntimeError(
                f"Parquet file already exists for UUID {file_id}. "
                "This should never happen — check for filesystem inconsistencies."
            )
        # Save parquet
        df.to_parquet(parquet_path, index=False)
        # Detect if same content was uploaded before (informational only)
        content_hash = self._hash_df(df)
        duplicate_of = self._find_duplicate(content_hash, user_id)

        # Build registry entry
        entry: Dict[str, Any] = {
            "file_id": file_id,
            "original_filename": original_filename,
            "user_label": Path(original_filename).stem,  # "Sales Q1" (no extension)
            "parquet_path": str(parquet_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "transformations_applied": transformations_applied or [],
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": df.columns.tolist(),
            "content_hash": content_hash,
            "duplicate_of": duplicate_of,  # None or prior UUID
            "user_id": user_id,
            "active": True,  # soft-delete flag
        }
        if sheet_name:
            entry["sheet_name"] = sheet_name
        if extra_meta:
            entry.update(extra_meta)

        self.registry[file_id] = entry
        self._save()

        return file_id

    def load(self, file_id: str) -> pd.DataFrame:
        """Load a dataframe by its UUID."""
        meta = self._get_entry(file_id)
        return pd.read_parquet(meta["parquet_path"])

    def get_meta(self, file_id: str) -> Dict[str, Any]:
        """Get registry metadata for a given UUID."""
        return self._get_entry(file_id)

    def delete(self, file_id: str, hard: bool = False):
        """
        Remove a registered file.

        hard=False  → soft delete (marks active=False, keeps parquet)
        hard=True   → deletes parquet from disk and removes registry entry
        """
        meta = self._get_entry(file_id)

        if hard:
            parquet_path = Path(meta["parquet_path"])
            if parquet_path.exists():
                parquet_path.unlink()
            del self.registry[file_id]
        else:
            self.registry[file_id]["active"] = False

        self._save()

    # ------------------------------------------------------------------ #
    #  Lookup helpers  (user-facing — by name, not UUID)
    # ------------------------------------------------------------------ #

    def find_by_label(
        self,
        user_label: str,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Find all registry entries matching a user-facing label.
        Returns a list because the same filename can be uploaded multiple times.
        Most recent first.

        Example
        -------
        entries = registry.find_by_label("Sales Q1")
        latest  = entries[0]   # most recent upload
        """
        matches = [
            entry
            for entry in self.registry.values()
            if entry.get("active", True)
            and entry["user_label"].lower() == user_label.lower()
            and (user_id is None or entry.get("user_id") == user_id)
        ]
        return sorted(matches, key=lambda e: e["created_at"], reverse=True)

    def find_latest_by_label(
        self,
        user_label: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Convenience method — returns only the most recent upload for a label.
        Raises ValueError if not found.
        """
        matches = self.find_by_label(user_label, user_id)
        if not matches:
            raise ValueError(
                f"No active file found with label '{user_label}'"
                + (f" for user '{user_id}'" if user_id else "")
            )
        return matches[0]

    def list_all(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all active registry entries, most recent first."""
        entries = [
            entry
            for entry in self.registry.values()
            if entry.get("active", True)
            and (user_id is None or entry.get("user_id") == user_id)
        ]
        return sorted(entries, key=lambda e: e["created_at"], reverse=True)

    # ------------------------------------------------------------------ #
    #  Internal
    # ------------------------------------------------------------------ #

    def _get_entry(self, file_id: str) -> Dict[str, Any]:
        entry = self.registry.get(file_id)
        if not entry:
            raise ValueError(f"No file registered with id: {file_id}")
        if not entry.get("active", True):
            raise ValueError(f"File '{file_id}' has been deleted")
        return entry

    def _find_duplicate(
        self,
        content_hash: str,
        user_id: Optional[str],
    ) -> Optional[str]:
        """
        Check if the same content hash already exists in the registry.
        Returns the prior UUID if found, None otherwise.
        Does NOT block registration — always informational only.
        """
        for file_id, entry in self.registry.items():
            if (
                entry.get("content_hash") == content_hash
                and entry.get("active", True)
                and (user_id is None or entry.get("user_id") == user_id)
            ):
                return file_id
        return None

    def _delete_user_files(self, user_id: str, hard: bool = True):
        """Delete all files for a given user (e.g. on account deletion)."""
        for entry in self.registry.values():
            if entry.get("user_id") == user_id:
                print(entry.get("original_filename"))
                self.delete(entry["file_id"], hard=hard)
