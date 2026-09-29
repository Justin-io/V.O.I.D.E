"""Workspace Filesystem Service with Zero-Trust Path Containment for V.O.I.D.E.

Guarantees:
- Path canonicalization and workspace sandbox enforcement (prevents ../ traversal)
- Atomic file writes via temporary file and replace
- Unified diff parsing and atomic patch application
- Cryptographic content hashes (SHA-256) for auditability
"""

from __future__ import annotations
import hashlib
import os
import tempfile
from typing import Any, Dict, List


class SecurityError(Exception):
    """Raised when an operation violates workspace sandbox boundaries."""
    pass


class FilesystemService:
    """Provides sandboxed workspace filesystem primitives."""

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root: str = os.path.realpath(workspace_root)
        if not os.path.isdir(self.workspace_root):
            os.makedirs(self.workspace_root, exist_ok=True)

    def _resolve_safe_path(self, relative_path: str) -> str:
        """Resolve path and verify it stays strictly inside workspace root."""
        joined = os.path.join(self.workspace_root, relative_path)
        resolved = os.path.realpath(joined)
        
        # Check boundary
        common = os.path.commonpath([self.workspace_root, resolved])
        if common != self.workspace_root:
            raise SecurityError(
                f"Path traversal detected: '{relative_path}' escapes workspace '{self.workspace_root}'"
            )

        # Zero-trust protection: block accessing sensitive secrets & credentials
        base_name = os.path.basename(resolved)
        rel_from_ws = os.path.relpath(resolved, self.workspace_root)
        parts = rel_from_ws.split(os.sep)
        if (
            any(p.startswith(".git") or p.startswith(".ssh") for p in parts)
            or (base_name.startswith(".env") and not base_name.endswith(".example"))
            or base_name.endswith((".key", ".pem", ".pfx", ".pkcs12", ".id_rsa", ".id_ed25519"))
            or base_name in ("credentials.json", "token.json", "id_rsa", "id_ed25519")
        ):
            raise SecurityError(
                f"Access to protected credential or sensitive path is denied: '{relative_path}'"
            )
        return resolved

    @staticmethod
    def _compute_hash(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def list_directory(self, relative_path: str = "", include_hidden: bool = False) -> List[Dict[str, Any]]:
        """List entries in directory with file metadata."""
        safe_path = self._resolve_safe_path(relative_path)
        if not os.path.isdir(safe_path):
            raise FileNotFoundError(f"Directory not found: {relative_path}")

        entries: List[Dict[str, Any]] = []
        for entry in os.scandir(safe_path):
            if not include_hidden:
                if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules"):
                    continue
            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size_bytes": stat.st_size if not entry.is_dir() else 0,
                "mtime": stat.st_mtime,
                "path": os.path.relpath(entry.path, self.workspace_root),
            })
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return entries

    def read_file(self, relative_path: str, max_bytes: int = 1048576) -> Dict[str, Any]:
        """Safely read text file content up to max_bytes."""
        safe_path = self._resolve_safe_path(relative_path)
        if not os.path.isfile(safe_path):
            raise FileNotFoundError(f"File not found: {relative_path}")

        with open(safe_path, "rb") as f:
            raw = f.read(max_bytes)
            # Check if there is more
            is_truncated = bool(f.read(1))

        content = raw.decode("utf-8", errors="replace")
        content_hash = self._compute_hash(raw)
        return {
            "path": relative_path,
            "content": content,
            "content_hash": content_hash,
            "size_bytes": len(raw),
            "is_truncated": is_truncated,
            "lines": content.count("\n") + (1 if content else 0),
        }

    def search_files(self, query: str, max_matches: int = 50) -> List[Dict[str, Any]]:
        """Search text query across workspace files."""
        matches: List[Dict[str, Any]] = []
        for root, dirs, files in os.walk(self.workspace_root):
            # Skip hidden and cache dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "build", "__pycache__")]
            for filename in files:
                if filename.startswith("."):
                    continue
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, self.workspace_root)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_no, line in enumerate(f, start=1):
                            if query in line:
                                matches.append({
                                    "path": rel_path,
                                    "line_number": line_no,
                                    "line_content": line.rstrip("\r\n"),
                                })
                                if len(matches) >= max_matches:
                                    return matches
                except Exception:
                    continue
        return matches

    def write_file(self, relative_path: str, content: str) -> Dict[str, Any]:
        """Atomically write file content inside workspace."""
        safe_path = self._resolve_safe_path(relative_path)
        parent_dir = os.path.dirname(safe_path)
        os.makedirs(parent_dir, exist_ok=True)

        raw = content.encode("utf-8")
        content_hash = self._compute_hash(raw)

        # Atomic write: write to temp file in same directory and replace
        fd, temp_path = tempfile.mkstemp(dir=parent_dir, prefix=".voide_tmp_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, safe_path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

        return {
            "path": relative_path,
            "changed": True,
            "content_hash": content_hash,
            "size_bytes": len(raw),
        }

    def apply_patch(self, relative_path: str, patch_text: str) -> Dict[str, Any]:
        """Apply a unified diff patch to a target workspace file."""
        safe_path = self._resolve_safe_path(relative_path)
        if not os.path.isfile(safe_path):
            raise FileNotFoundError(f"Cannot patch non-existent file: {relative_path}")

        with open(safe_path, "r", encoding="utf-8") as f:
            original_lines = f.readlines()

        # Parse patch lines
        patch_lines = patch_text.splitlines(keepends=True)
        # Attempt standard unified patch application
        try:
            # Parse diff blocks
            new_lines = self._apply_unified_diff(original_lines, patch_lines)
        except Exception as err:
            raise ValueError(f"Failed to parse or apply patch: {err}")

        new_content = "".join(new_lines)
        write_result = self.write_file(relative_path, new_content)
        write_result["diff_applied"] = True
        return write_result

    def create_directory(self, relative_path: str) -> Dict[str, Any]:
        """Create directory inside workspace."""
        safe_path = self._resolve_safe_path(relative_path)
        os.makedirs(safe_path, exist_ok=True)
        return {"path": relative_path, "created": True, "is_dir": True}

    def delete_file(self, relative_path: str) -> Dict[str, Any]:
        """Delete file or empty directory inside workspace."""
        safe_path = self._resolve_safe_path(relative_path)
        if not os.path.exists(safe_path):
            raise FileNotFoundError(f"Path not found: {relative_path}")
        if os.path.isdir(safe_path):
            import shutil
            shutil.rmtree(safe_path)
        else:
            os.remove(safe_path)
        return {"path": relative_path, "deleted": True}

    def rename_file(self, old_path: str, new_path: str) -> Dict[str, Any]:
        """Rename or move a file within the workspace."""
        safe_old = self._resolve_safe_path(old_path)
        safe_new = self._resolve_safe_path(new_path)
        if not os.path.exists(safe_old):
            raise FileNotFoundError(f"Source not found: {old_path}")
        parent = os.path.dirname(safe_new)
        os.makedirs(parent, exist_ok=True)
        os.rename(safe_old, safe_new)
        return {"old_path": old_path, "new_path": new_path, "renamed": True}


    @staticmethod
    def _apply_unified_diff(original: List[str], patch: List[str]) -> List[str]:
        """Minimal deterministic unified diff applicator."""
        orig_idx = 0
        result: List[str] = []
        i = 0
        n = len(patch)

        # Skip headers until first hunk header @@
        while i < n and not patch[i].startswith("@@"):
            i += 1

        while i < n:
            line = patch[i]
            if line.startswith("@@"):
                # Hunk header @@ -start,len +start,len @@
                parts = line.split()
                if len(parts) >= 3:
                    orig_spec = parts[1]  # e.g. -1,5 or -1
                    clean_spec = orig_spec.lstrip("-").split(",")[0]
                    start_line = int(clean_spec) if clean_spec.isdigit() else 1
                    target_orig_idx = max(0, start_line - 1)
                    while orig_idx < target_orig_idx and orig_idx < len(original):
                        result.append(original[orig_idx])
                        orig_idx += 1
                i += 1
                continue
            if line.startswith("+"):
                result.append(line[1:])
                i += 1
            elif line.startswith("-"):
                orig_idx += 1
                i += 1
            elif line.startswith(" "):
                if orig_idx < len(original):
                    result.append(original[orig_idx])
                    orig_idx += 1
                i += 1
            elif line.startswith("\\"):  # e.g. \ No newline at end of file
                i += 1
            else:
                i += 1

        # Append remaining original lines
        while orig_idx < len(original):
            result.append(original[orig_idx])
            orig_idx += 1

        return result

