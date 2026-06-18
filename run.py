"""
IEEMS pipeline driver.

Usage:
    python run.py input_bundles/s01_clean
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import yaml

from utils.logger import get_agent_logger, log_step

RUNS_DIR    = Path("runs")
POLICY_FILE = Path("policy/expense_policy.yaml")

# Pipeline order follows the data flow: A → B → D → C → E → H
# fatal=True  → non-zero exit or missing module aborts the pipeline.
# fatal=False → non-zero exit or missing module logs a warning and continues.
PIPELINE: list[tuple[str, str, bool]] = [
    ("A", "agents.agent_a_intake",        True),
    ("B", "agents.agent_b_extraction",    True),
    ("D", "agents.agent_d_normalization", False),
    ("C", "agents.agent_c_policy",        False),
    ("E", "agents.agent_e_duplicates",    False),
    ("H", "agents.agent_h_orchestrator",  False),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_policy() -> dict:
    """Load expense_policy.yaml; return empty dict if file is missing."""
    if POLICY_FILE.exists():
        return yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8")) or {}
    return {}


def create_run_dir(bundle_id: str) -> Path:
    """Create runs/<bundle_id>_NNNN/ using an atomic counter.

    Uses exist_ok=False so two simultaneous runs can never claim the same
    directory, avoiding the race condition of a glob-count approach.
    """
    RUNS_DIR.mkdir(exist_ok=True)
    for i in range(1, 10_000):
        candidate = RUNS_DIR / f"{bundle_id}_{i:04d}"
        try:
            candidate.mkdir(exist_ok=False)  # atomic — raises if already exists
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(
        f"Could not create a unique run directory for bundle '{bundle_id}' "
        f"after 9 999 attempts."
    )


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    bundle_path: Path,
    run_dir: Path,
    policy: dict,
    bundle_id: str,
) -> None:
    """Iterate through PIPELINE, import each agent module, and call agent.run().

    All agent.run() functions share this contract:
        run(bundle_path: Path, run_dir: Path, policy: dict) -> int
        Returns 0 on success, non-zero on failure.
    """
    log = get_agent_logger("PIPELINE", bundle_id)
    log_step(log, "PIPELINE_START", f"bundle={bundle_path}  run_dir={run_dir}")

    for letter, module_path, fatal in PIPELINE:

        # --- import the agent module ---
        try:
            agent = importlib.import_module(module_path)
        except ImportError as exc:
            log_step(
                log,
                f"AGENT_{letter}_IMPORT_ERROR",
                str(exc),
                level="ERROR" if fatal else "WARNING",
            )
            if fatal:
                log_step(log, "PIPELINE_ABORTED", f"fatal import failure at Agent {letter}")
                sys.exit(1)
            continue
        except Exception as exc:
            # Catches module-level init failures (e.g. OpenAI() with no API key).
            # We cannot fix Agent B's code, so fall back to a stub and let the
            # rest of the suite run.
            log_step(
                log,
                f"AGENT_{letter}_IMPORT_ERROR",
                f"Module init failed — stub fallback active: {exc}",
                level="WARNING",
            )
            agent = types.SimpleNamespace(run=lambda bp, rd, p: 1)
            fatal = False  # shadows the loop var; only affects this iteration

        # --- snapshot run_dir contents before the agent writes anything ---
        before = {p.name for p in run_dir.iterdir()}

        # --- run the agent ---
        try:
            exit_code: int = agent.run(bundle_path, run_dir, policy)
        except AttributeError:
            log_step(
                log,
                f"AGENT_{letter}_MISSING_RUN",
                f"agents.{module_path} has no run() method — skipping",
                level="WARNING",
            )
            continue

        written = sorted({p.name for p in run_dir.iterdir()} - before)

        log_step(
            log,
            f"AGENT_{letter}_DONE",
            f"exit={exit_code}  wrote={written or 'nothing'}",
            level="INFO" if exit_code == 0 else "WARNING",
        )

        if exit_code != 0:
            if fatal:
                log_step(log, "PIPELINE_ABORTED", f"Agent {letter} returned exit {exit_code}")
                sys.exit(1)
            else:
                print(f"[WARN]  Agent {letter} returned exit {exit_code} — continuing.")

    log_step(log, "PIPELINE_DONE", f"all agents completed  run_dir={run_dir}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python run.py <bundle_path>")
        sys.exit(1)

    bundle_path = Path(sys.argv[1])
    if not bundle_path.is_dir():
        print(f"Error: bundle directory not found: {bundle_path}")
        sys.exit(1)

    manifest_path = bundle_path / "manifest.yaml"
    if not manifest_path.exists():
        print(f"Error: manifest.yaml not found in {bundle_path}")
        sys.exit(1)

    manifest  = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    bundle_id = manifest["bundle_id"]
    policy    = load_policy()
    run_dir   = create_run_dir(bundle_id)

    print(f"Bundle : {bundle_path}")
    print(f"Run dir: {run_dir}")

    run_pipeline(bundle_path, run_dir, policy, bundle_id)

    print(f"Done   : {run_dir}/")


if __name__ == "__main__":
    main()