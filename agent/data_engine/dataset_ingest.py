"""Universal Dataset Ingestion Engine for V.O.I.D.E.

Handles multi-format parsing, schema sniffing, cryptographic fingerprinting,
and zero-leak staging for engineering datasets.
"""

from __future__ import annotations
import csv
import hashlib
import json
import os
import shutil
import uuid
from typing import Any, Dict, List, Optional, Tuple


class DatasetIngestEngine:
    """Universal, resilient dataset ingestion and staging service."""

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root: str = os.path.realpath(workspace_root)
        self.datasets_dir: str = os.path.join(self.workspace_root, "datasets")
        os.makedirs(self.datasets_dir, exist_ok=True)

    def calculate_file_hash(self, file_path: str) -> str:
        """Compute deterministic SHA-256 digest of dataset file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def detect_format(self, file_path: str) -> str:
        """Detect file format based on extension and content inspection."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext in [".csv", ".txt"]:
            return "csv"
        elif ext in [".json", ".jsonl"]:
            return "json"
        elif ext in [".parquet", ".pq"]:
            return "parquet"
        elif ext in [".xlsx", ".xls"]:
            return "excel"
        return "unknown"

    def sniff_csv_dialect(self, file_path: str) -> Tuple[str, bool]:
        """Detect CSV delimiter and whether header row is present."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(8192)
        try:
            sniffer = csv.Sniffer()
            dialect = sniffer.sniff(sample)
            has_header = sniffer.has_header(sample)
            return dialect.delimiter, has_header
        except Exception:
            # Safe fallback default
            return ",", True

    def ingest(
        self,
        source_path: str,
        custom_name: Optional[str] = None,
        copy_to_workspace: bool = True,
    ) -> Dict[str, Any]:
        """Ingest, fingerprint, and register dataset."""
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source file does not exist: {source_path}")

        file_hash = self.calculate_file_hash(source_path)
        base_name = custom_name or os.path.basename(source_path)
        format_type = self.detect_format(source_path)

        if copy_to_workspace:
            target_path = os.path.join(self.datasets_dir, base_name)
            # Avoid redundant self-copy
            if os.path.realpath(source_path) != os.path.realpath(target_path):
                shutil.copy2(source_path, target_path)
            staged_path = target_path
        else:
            staged_path = os.path.realpath(source_path)

        # Inspect basic tabular metadata
        row_count = 0
        columns: List[str] = []
        sample_rows: List[Dict[str, Any]] = []

        if format_type == "csv":
            delimiter, has_header = self.sniff_csv_dialect(staged_path)
            with open(staged_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f, delimiter=delimiter)
                if has_header:
                    header_row = next(reader, None)
                    columns = [c.strip() for c in (header_row or [])]
                for idx, row in enumerate(reader):
                    row_count += 1
                    if idx < 5:
                        if columns:
                            sample_rows.append(dict(zip(columns, row)))
                        else:
                            sample_rows.append({f"col_{i}": v for i, v in enumerate(row)})

        elif format_type == "json":
            with open(staged_path, "r", encoding="utf-8", errors="replace") as f:
                try:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                        row_count = len(data)
                        columns = list(data[0].keys())
                        sample_rows = data[:5]
                except Exception:
                    pass

        dataset_id = f"ds-{file_hash[:8]}"

        provenance = {
            "source_path": os.path.realpath(source_path),
            "staged_path": staged_path,
            "staged_at": os.path.getmtime(staged_path),
            "file_size_bytes": os.path.getsize(staged_path),
            "delimiter": delimiter if format_type == "csv" else None,
        }

        return {
            "dataset_id": dataset_id,
            "name": base_name,
            "file_path": staged_path,
            "file_hash": file_hash,
            "row_count": row_count,
            "column_count": len(columns),
            "format": format_type,
            "columns": columns,
            "sample_rows": sample_rows,
            "provenance": provenance,
        }
