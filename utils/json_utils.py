"""
utils/json_utils.py
===================
Deterministic JSON reading and writing for the IEEMS pipeline.

Rules enforced here so every agent produces identical bytes:
  • Keys are always sorted alphabetically (sort_keys=True).
  • Indentation is always 2 spaces.
  • Decimal values are serialised as plain numeric strings (no scientific
    notation, no floating-point drift).
  • Non-ASCII characters are kept as-is (ensure_ascii=False) so vendor
    names with accents survive the round-trip unchanged.
  • Files are written atomically via a temp file + rename to prevent
    a crashed agent from leaving a half-written JSON behind.
"""

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Custom JSON encoder
# ---------------------------------------------------------------------------

class _IEEMSEncoder(json.JSONEncoder):
    """Extend the standard encoder to handle types the pipeline uses."""

    def default(self, obj: Any) -> Any:  # noqa: ANN401
        if isinstance(obj, Decimal):
            # Normalise trailing zeros: Decimal("1.50") → "1.50"
            # Use str() which preserves the stored precision exactly.
            return str(obj)
        # Let the base class raise TypeError for anything else.
        return super().default(obj)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_json(data: Any, path: str | Path) -> None:
    """Serialise *data* to *path* in a deterministic, atomic way.

    Parameters
    ----------
    data:
        Any JSON-serialisable value (dict, list, Pydantic `.model_dump()`,
        or a nested mix of those types).
    path:
        Destination file path.  Parent directories must already exist.

    Raises
    ------
    TypeError
        If *data* contains a type that cannot be serialised.
    OSError
        If the file cannot be written (permissions, disk full, …).
    """
    path = Path(path)
    json_bytes = json.dumps(
        data,
        cls=_IEEMSEncoder,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")

    # Atomic write: write to a sibling temp file, then rename.
    dir_ = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=dir_, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(json_bytes)
            fh.write(b"\n")          # trailing newline — friendly for git diffs
        os.replace(tmp_path, path)   # atomic on POSIX; best-effort on Windows
    except Exception:
        # Clean up the temp file if anything went wrong.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_json(path: str | Path) -> Any:  # noqa: ANN401
    """Read and parse a JSON file produced by this pipeline.

    Parameters
    ----------
    path:
        Path to the JSON file.

    Returns
    -------
    Any
        Parsed Python object (usually a ``dict``).

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    json.JSONDecodeError
        If the file is not valid JSON.

    Notes
    -----
    Decimal fields arrive as plain strings after serialisation.  Pass the
    parsed dict straight into the relevant Pydantic model — Pydantic will
    coerce those strings back to ``Decimal`` automatically.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def model_to_dict(model: Any) -> dict:  # noqa: ANN401
    """Convert a Pydantic v2 model to a plain dict ready for *write_json*.

    Uses ``model_dump(mode="json")`` so Decimal values are already strings
    before our encoder sees them, which is the safest route in Pydantic v2.
    """
    return model.model_dump(mode="json")