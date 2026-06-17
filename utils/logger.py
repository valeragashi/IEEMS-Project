"""
utils/logger.py
===============
Uniform audit logging for all IEEMS pipeline agents.

Every agent calls ``get_agent_logger()`` once at startup, then uses the
returned logger for all structured log lines.  This guarantees:

  • Every log line is written to the run-specific ``audit.log`` file AND
    to the console (stderr), at configurable levels.
  • The format is fixed:
        2024-05-10 14:32:01.123 | INFO     | AGENT_B | BUNDLE-001 | message
  • Loguru is used as the backend (listed in requirements.txt) so callers
    get structured context-binding via ``.bind()``.
  • Each call to ``get_agent_logger()`` is idempotent — calling it twice
    for the same (agent, bundle) pair reuses the already-configured sink.
"""

import sys
from pathlib import Path

from loguru import logger as _root_logger

from utils.constants import FILENAME_AUDIT_LOG
from utils.file_utils import get_run_dir


# ---------------------------------------------------------------------------
# Internal state: track which (bundle_id, log_path) sinks are registered
# so we don't add duplicate file sinks on repeated calls.
# ---------------------------------------------------------------------------
_registered_sinks: dict[str, int] = {}   # log_path_str → loguru sink id


# ---------------------------------------------------------------------------
# Log format
# ---------------------------------------------------------------------------
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
    "{extra[agent]} | {extra[bundle_id]} | {message}"
)
_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[agent]}</cyan> | "
    "<white>{extra[bundle_id]}</white> | "
    "{message}"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_agent_logger(
    agent_id: str,
    bundle_id: str,
    *,
    file_level: str = "DEBUG",
    console_level: str = "INFO",
):
    """Configure and return a bound Loguru logger for one agent / bundle.

    Parameters
    ----------
    agent_id:
        Single-letter agent identifier, e.g. ``"B"`` or ``"H"``.
        Use the ``AGENT_*`` constants from ``utils.constants``.
    bundle_id:
        The bundle being processed.  Used to locate the run directory and
        to stamp every log line.
    file_level:
        Minimum log level written to ``audit.log``.  Default ``"DEBUG"``
        so nothing is dropped.
    console_level:
        Minimum log level echoed to stderr.  Default ``"INFO"`` to avoid
        flooding CI output.

    Returns
    -------
    loguru.Logger
        A logger pre-bound with ``agent`` and ``bundle_id`` context.
        Use it exactly like the standard loguru logger:
        ``log.info("Done")``, ``log.warning("Low confidence")``, …

    Example
    -------
    >>> log = get_agent_logger("B", "BUNDLE-001")
    >>> log.info("Extraction complete — {} expenses found", 7)
    """
    run_dir: Path = get_run_dir(bundle_id)
    log_path: Path = run_dir / FILENAME_AUDIT_LOG
    log_path_str: str = str(log_path)

    # --- Ensure a console sink exists (only once per process) -------------
    # Loguru ships with a default stderr sink (id=0).  We remove it and
    # add our own so the format matches; guard with a module-level flag.
    if not _registered_sinks:
        # Remove the default sink added by loguru at import time.
        try:
            _root_logger.remove(0)
        except ValueError:
            pass  # Already removed in a previous call.
        _root_logger.add(
            sys.stderr,
            format=_CONSOLE_FORMAT,
            level=console_level,
            colorize=True,
            filter=lambda record: "agent" in record["extra"],
        )

    # --- File sink (one per run directory) --------------------------------
    if log_path_str not in _registered_sinks:
        sink_id = _root_logger.add(
            log_path_str,
            format=_FILE_FORMAT,
            level=file_level,
            encoding="utf-8",
            rotation=None,   # pipeline runs are short; no rotation needed
            filter=lambda record: "agent" in record["extra"],
        )
        _registered_sinks[log_path_str] = sink_id

    # Return a logger bound with the agent and bundle context.
    return _root_logger.bind(agent=agent_id, bundle_id=bundle_id)


def log_step(
    log,  # bound loguru logger returned by get_agent_logger()
    step: str,
    detail: str = "",
    level: str = "INFO",
) -> None:
    """Write a single structured step entry to the audit log.

    Parameters
    ----------
    log:
        Bound logger from ``get_agent_logger()``.
    step:
        Short machine-readable step name, e.g. ``"PARSE_RECEIPT"``.
    detail:
        Human-readable detail string.  Optional.
    level:
        Log level string: ``"DEBUG"``, ``"INFO"``, ``"WARNING"``,
        ``"ERROR"``, ``"CRITICAL"``.

    Example
    -------
    >>> log_step(log, "PARSE_RECEIPT", "F001 parsed — 3 line items found")
    >>> # → 2024-05-10 14:32:01.123 | INFO     | B | BUNDLE-001 | PARSE_RECEIPT | F001 parsed — 3 line items found
    """
    message = step if not detail else f"{step} | {detail}"
    log.log(level.upper(), message)