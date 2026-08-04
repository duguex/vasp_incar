"""Version envelope handling for DFT data files."""

import json
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dft_utils import DATA_VERSION


def load_json(path: Path) -> Any | None:
    """Load a JSON file, returning None if it doesn't exist."""
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


def load_data(
    path: Path,
    default: Any = None,
    model: type[BaseModel] | None = None,
) -> Any | None:
    """Load a data file, check version envelope, strip it transparently.

    Supports two on-disk formats:
      ``{"_version": "...", "data": <content>}``  — wrapped envelope (preferred)
      ``<content>``                                — raw (backward-compat)

    Returns ``default`` (or ``None``) if the file does not exist.
    """
    raw = load_json(path)
    if raw is None:
        return default

    data = raw
    if isinstance(raw, dict) and "_version" in raw:
        ver = raw["_version"]
        raw = {key: value for key, value in raw.items() if key != "_version"}
        if ver != DATA_VERSION:
            warnings.warn(
                f"{path.name} version {ver!r} != expected {DATA_VERSION!r}. "
                "Run data regeneration for this package.",
                stacklevel=2,
            )
        data = raw.get("data") if "data" in raw else raw

    if model is not None:
        if isinstance(data, list):
            return [model.model_validate(item) for item in data]
        return model.model_validate(data)

    return data


def check_version(db_version: str, source_name: str = "data") -> bool:
    """Compare a stored version string against DATA_VERSION.

    Prints a warning on mismatch.  Returns True if OK, False on mismatch.
    """
    if db_version != DATA_VERSION:
        warnings.warn(
            f"{source_name} version {db_version!r} != expected {DATA_VERSION!r}. "
            "Run data regeneration for this package.",
            stacklevel=2,
        )
        return False
    return True
