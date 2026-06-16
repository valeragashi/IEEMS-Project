"""Run-directory path helpers."""

from pathlib import Path


def resolve_run_dir(runs_base: Path | str, run_id: str) -> Path:
    """Return the full path for a run directory, creating it if necessary.

    Args:
        runs_base: The top-level runs/ folder (e.g. Path("runs")).
        run_id:    The specific run identifier (e.g. "s01_clean_0001").

    Returns:
        A Path to the run directory, guaranteed to exist.
    """
    run_dir = Path(runs_base) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir