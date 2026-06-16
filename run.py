"""
IEEMS pipeline driver.
Usage: python run.py input_bundles/s01_clean
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import yaml

RUNS_DIR    = Path("runs")
POLICY_FILE = Path("policy/expense_policy.yaml")
AUDIT_LOG   = "audit_log.md"

# Pipeline order follows the data flow in models.py: A→B→D→C→E→H
# fatal=True  → ImportError or non-zero exit aborts the pipeline immediately.
# fatal=False → ImportError or non-zero exit logs a warning and continues.
PIPELINE: list[tuple[str, str, bool]] = [
    ("A", "agents.agent_a_intake",        True),
    ("B", "agents.agent_b_extraction",    True),
    ("D", "agents.agent_d_normalization", False),
    ("C", "agents.agent_c_policy",        False),
    ("E", "agents.agent_e_duplicates",    False),
    ("H", "agents.agent_h_orchestrator",  False),
]


def load_policy() -> dict:
    if POLICY_FILE.exists():
        return yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8")) or {}
    return {}


def create_run_dir(bundle_id: str) -> Path:
    """Create runs/<bundle_id>_NNNN/ using a counter, never a timestamp."""
    RUNS_DIR.mkdir(exist_ok=True)
    counter = len(list(RUNS_DIR.glob(f"{bundle_id}_*"))) + 1
    run_dir = RUNS_DIR / f"{bundle_id}_{counter:04d}"
    run_dir.mkdir()
    return run_dir


def append_audit(run_dir: Path, letter: str, exit_code: int, written: list[str], note: str = "") -> None:
    files = ", ".join(written) if written else "nothing"
    line  = f"Agent {letter}: exit {exit_code}, wrote {files}"
    if note:
        line += f" [{note}]"
    (run_dir / AUDIT_LOG).open("a", encoding="utf-8").write(line + "\n")


def run_pipeline(bundle_path: Path, run_dir: Path, policy: dict) -> None:
    for letter, module_path, fatal in PIPELINE:

        # --- try to import the agent module ---
        try:
            agent = importlib.import_module(module_path)
        except ImportError:
            msg = f"Agent {letter}: module '{module_path}' not found — skipped (stub placeholder)."
            print(f"[{'FATAL' if fatal else 'WARN'}] {msg}")
            append_audit(run_dir, letter, -1, [], note="module not found")
            if fatal:
                sys.exit(1)
            continue

        # --- run the agent ---
        before    = {p.name for p in run_dir.iterdir() if p.name != AUDIT_LOG}
        exit_code = agent.run(bundle_path, run_dir, policy)
        written   = sorted({p.name for p in run_dir.iterdir() if p.name != AUDIT_LOG} - before)

        append_audit(run_dir, letter, exit_code, written)

        if exit_code != 0:
            msg = f"Agent {letter} returned exit {exit_code}."
            if fatal:
                print(f"[FATAL] {msg} Pipeline aborted.")
                sys.exit(1)
            else:
                print(f"[WARN]  {msg} Continuing.")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python run.py <bundle_path>")
        sys.exit(1)

    bundle_path = Path(sys.argv[1])
    if not bundle_path.is_dir():
        print(f"Error: bundle not found: {bundle_path}")
        sys.exit(1)

    manifest  = yaml.safe_load((bundle_path / "manifest.yaml").read_text(encoding="utf-8"))
    bundle_id = manifest["bundle_id"]

    run_dir = create_run_dir(bundle_id)
    policy  = load_policy()

    print(f"Bundle : {bundle_path}")
    print(f"Run dir: {run_dir}")
    run_pipeline(bundle_path, run_dir, policy)
    print(f"Done   : {run_dir}/")


if __name__ == "__main__":
    main()