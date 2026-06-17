"""
utils/file_utils.py
===================
Run-directory path resolution for the IEEMS pipeline.

Every agent call is scoped to a single *run directory*:

    runs/
    └── <bundle_id>/
        ├── context_packet.json
        ├── extracted_expenses.json
        ├── normalization_results.json
        ├── policy_findings.json
        ├── duplicate_findings.json
        ├── final_decision.json
        └── audit.log

Agents should call ``get_run_dir()`` to locate their working directory and
``get_output_path()`` to build paths to specific output files.  Neither
function requires callers to know where ``runs/`` lives relative to their
own ``__file__``.
"""

from pathlib import Path

from utils.constants import RUNS_ROOT


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Return the absolute path of the IEEMS-Project root directory.

    Resolution strategy (first match wins):
      1. Walk up from this file until we find a directory that contains
         both a ``runs/`` folder *or* a ``schemas/`` folder — that is the
         project root.
      2. Fall back to three levels up from this file's location
         (utils/ → project root).
    """
    anchor_markers = {"schemas", "runs", "requirements.txt"}
    candidate = Path(__file__).resolve().parent  # utils/

    for parent in [candidate, *candidate.parents]:
        contents = {p.name for p in parent.iterdir()}
        if anchor_markers & contents:
            return parent

    # Fallback: assume utils/ is one level below the project root.
    return candidate.parent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_run_dir(bundle_id: str, *, create: bool = True) -> Path:
    """Return (and optionally create) the run directory for *bundle_id*.

    Parameters
    ----------
    bundle_id:
        Unique identifier for the expense bundle being processed,
        e.g. ``"BUNDLE-2024-001"``.
    create:
        When ``True`` (default), the directory is created if it does not
        exist yet.  Pass ``False`` when you only want to resolve the path
        without side-effects.

    Returns
    -------
    Path
        Absolute path to ``<project_root>/runs/<bundle_id>/``.

    Raises
    ------
    ValueError
        If *bundle_id* is empty or contains path-separator characters
        that would escape the ``runs/`` directory.
    """
    if not bundle_id or not bundle_id.strip():
        raise ValueError("bundle_id must be a non-empty string.")

    # Guard against path traversal (e.g. bundle_id = "../../etc")
    clean_id = Path(bundle_id)
    if clean_id != Path(clean_id.name):
        raise ValueError(
            f"bundle_id must not contain path separators: {bundle_id!r}"
        )

    run_dir = _project_root() / RUNS_ROOT / bundle_id

    if create:
        run_dir.mkdir(parents=True, exist_ok=True)

    return run_dir


def get_output_path(bundle_id: str, filename: str) -> Path:
    """Return the absolute path for a named output file inside a run dir.

    The run directory is created automatically if it does not exist.

    Parameters
    ----------
    bundle_id:
        The bundle being processed.
    filename:
        The filename constant from ``utils.constants``, e.g.
        ``FILENAME_EXTRACTED_EXPENSES``.

    Returns
    -------
    Path
        ``<project_root>/runs/<bundle_id>/<filename>``

    Example
    -------
    >>> from utils.constants import FILENAME_EXTRACTED_EXPENSES
    >>> path = get_output_path("BUNDLE-001", FILENAME_EXTRACTED_EXPENSES)
    >>> # Path('.../runs/BUNDLE-001/extracted_expenses.json')
    """
    return get_run_dir(bundle_id) / filename


def get_all_bundle_ids() -> list[str]:
    """Return a sorted list of all bundle IDs that have a run directory.

    Useful for batch re-processing or monitoring tools.
    """
    runs_root = _project_root() / RUNS_ROOT
    if not runs_root.exists():
        return []
    return sorted(
        p.name for p in runs_root.iterdir() if p.is_dir()
    )