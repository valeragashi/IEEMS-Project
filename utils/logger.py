"""Audit logger — all agents append to audit.log via this function."""

from pathlib import Path

AUDIT_FILENAME = "audit.log"


def audit(run_dir: Path | str, agent: str, message: str) -> None:
    """Append one standardized line to <run_dir>/audit.log.

    Format (no timestamps — preserves determinism):
        [Agent X] <message>

    Args:
        run_dir: The active run directory.
        agent:   Single letter identifying the agent (e.g. "A", "B").
        message: Free-text description of the step or outcome.
    """
    line = f"[Agent {agent}] {message}\n"
    (Path(run_dir) / AUDIT_FILENAME).open("a", encoding="utf-8").write(line)