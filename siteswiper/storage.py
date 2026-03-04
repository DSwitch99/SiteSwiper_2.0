"""Save and load captured requests as JSON files."""

import json
from datetime import datetime, timezone
from pathlib import Path

from siteswiper.config import STORAGE_DIR


def _ensure_storage_dir() -> Path:
    """Create the storage directory if it doesn't exist."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return STORAGE_DIR


def _sanitize_name(name: str) -> str:
    """Sanitize a request name for use as a filename."""
    # Replace spaces and special chars with underscores
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return safe.strip("_") or "unnamed"


def save_request(name: str, parsed_request: dict, notes: str = "",
                 pre_commit: dict | None = None) -> Path:
    """Save a parsed request to disk.

    Args:
        name: Human-friendly name for this request.
        parsed_request: The parsed cURL dict from curl_parser.parse_curl().
        notes: Optional notes about this request.
        pre_commit: Optional parsed pre-commit (step 1) request dict.
            When present, SiteSwiper will fire this request first at booking
            time, extract fresh session UUIDs from its response, and inject
            them into the commit body before firing the main request.

    Returns:
        Path to the saved file.
    """
    storage_dir = _ensure_storage_dir()
    safe_name = _sanitize_name(name)
    file_path = storage_dir / f"{safe_name}.json"

    data = {
        "name": name,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
        "request": parsed_request,
    }
    if pre_commit is not None:
        data["pre_commit"] = pre_commit

    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

    return file_path


def load_request(name: str) -> dict:
    """Load a saved request by name.

    Args:
        name: The name (or sanitized filename stem) to load.

    Returns:
        The full saved data dict (name, saved_at, notes, request).

    Raises:
        FileNotFoundError: If no request with that name exists.
    """
    storage_dir = _ensure_storage_dir()
    safe_name = _sanitize_name(name)
    file_path = storage_dir / f"{safe_name}.json"

    if not file_path.exists():
        # Try exact match on disk
        for f in storage_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("name") == name:
                    return data
            except (json.JSONDecodeError, KeyError):
                continue
        raise FileNotFoundError(f"No saved request found with name: {name}")

    with open(file_path) as f:
        return json.load(f)


def list_requests() -> list[dict]:
    """List all saved requests.

    Returns:
        List of dicts with keys: name, saved_at, filename, method, url, host.
    """
    storage_dir = _ensure_storage_dir()
    results = []

    for file_path in sorted(storage_dir.glob("*.json")):
        try:
            with open(file_path) as f:
                data = json.load(f)
            req = data.get("request", {})
            results.append({
                "name": data.get("name", file_path.stem),
                "saved_at": data.get("saved_at", "unknown"),
                "filename": file_path.stem,
                "method": req.get("method", "?"),
                "url": req.get("url", "?"),
                "host": req.get("host", "?"),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return results


def delete_request(name: str) -> bool:
    """Delete a saved request by name.

    Returns:
        True if deleted, False if not found.
    """
    storage_dir = _ensure_storage_dir()
    safe_name = _sanitize_name(name)
    file_path = storage_dir / f"{safe_name}.json"

    if file_path.exists():
        file_path.unlink()
        return True
    return False


def get_request_age_hours(saved_data: dict) -> float | None:
    """Get the age of a saved request in hours.

    Returns:
        Age in hours, or None if the saved_at timestamp is missing/invalid.
    """
    saved_at_str = saved_data.get("saved_at")
    if not saved_at_str:
        return None

    try:
        saved_at = datetime.fromisoformat(saved_at_str)
        now = datetime.now(timezone.utc)
        if saved_at.tzinfo is None:
            saved_at = saved_at.replace(tzinfo=timezone.utc)
        delta = now - saved_at
        return delta.total_seconds() / 3600
    except (ValueError, TypeError):
        return None
