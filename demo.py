"""IEEMS — Demo / Test Harness
Runs all test bundles through the pipeline and checks results against
the expected outcomes declared in each bundle's manifest.yaml.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

import yaml

from utils.constants import FILENAME_FINAL_DECISION
from utils.json_utils import read_json
from utils.logger import get_agent_logger, log_step

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BUNDLES_DIR   = Path("input_bundles")
RUNS_DIR      = Path("runs")
FIXTURES_DIR  = Path("fixtures")          # hand-crafted JSONs for stub mode
POLICY_FILE   = Path("policy/expense_policy.yaml")
USE_FIXTURES  = os.getenv("DEMO_USE_FIXTURES", "0") == "1"

# ANSI colours (disabled on Windows CI that doesn't support them)
_COLOR = sys.stdout.isatty()
GREEN  = "\033[32m" if _COLOR else ""
RED    = "\033[31m" if _COLOR else ""
YELLOW = "\033[33m" if _COLOR else ""
RESET  = "\033[0m"  if _COLOR else ""
BOLD   = "\033[1m"  if _COLOR else ""

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExpectedDecision:
    expense_id: str
    decision:   str
    approver:   str | None = None          # optional — omit to skip approver check


@dataclass
class ExpectedTotals:
    approved_usd: Decimal | None = None
    blocked_usd:  Decimal | None = None


@dataclass
class BundleExpectation:
    bundle_id:  str
    decisions:  list[ExpectedDecision] = field(default_factory=list)
    totals:     ExpectedTotals         = field(default_factory=ExpectedTotals)


@dataclass
class CheckResult:
    expense_id: str
    passed:     bool
    detail:     str                        # human-readable diff on failure


@dataclass
class BundleResult:
    bundle_id:  str
    passed:     bool
    checks:     list[CheckResult] = field(default_factory=list)
    error:      str | None        = None   # pipeline / IO error message


# ---------------------------------------------------------------------------
# Manifest parsing
# ---------------------------------------------------------------------------

def load_manifest(bundle_path: Path) -> dict:
    path = bundle_path / "manifest.yaml"
    if not path.exists():
        raise FileNotFoundError(f"manifest.yaml not found in {bundle_path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def parse_expectations(manifest: dict, bundle_id: str) -> BundleExpectation:
    """Extract the `expected` block from the manifest into typed objects."""
    raw = manifest.get("expected", {})

    decisions = [
        ExpectedDecision(
            expense_id=d["expense_id"],
            decision=d["decision"],
            approver=d.get("approver"),
        )
        for d in raw.get("decisions", [])
    ]

    raw_totals = raw.get("totals", {})
    totals = ExpectedTotals(
        approved_usd=Decimal(str(raw_totals["approved_usd"])) if "approved_usd" in raw_totals else None,
        blocked_usd =Decimal(str(raw_totals["blocked_usd"]))  if "blocked_usd"  in raw_totals else None,
    )

    return BundleExpectation(bundle_id=bundle_id, decisions=decisions, totals=totals)


# ---------------------------------------------------------------------------
# Pipeline runner (or fixture loader)
# ---------------------------------------------------------------------------

def _latest_run_dir(bundle_id: str) -> Path | None:
    """Return the most recently created run-dir for this bundle, or None."""
    candidates = sorted(RUNS_DIR.glob(f"{bundle_id}_*"))
    return candidates[-1] if candidates else None


def _fixture_path(bundle_id: str) -> Path:
    return FIXTURES_DIR / bundle_id / FILENAME_FINAL_DECISION


def run_pipeline_for_bundle(
    bundle_path: Path,
    bundle_id: str,
    policy: dict,
    log,
) -> Path:
    """Run the pipeline and return the path to final_decision.json."""
    if USE_FIXTURES:
        fixture = _fixture_path(bundle_id)
        if not fixture.exists():
            raise FileNotFoundError(
                f"Fixture not found: {fixture}\n"
                f"  Create it manually or run without DEMO_USE_FIXTURES=1."
            )
        log_step(log, "FIXTURE_MODE", str(fixture))
        return fixture

    try:
        import run as pipeline_driver  # noqa: PLC0415
    except ImportError:
        log_step(log, "STUB_FALLBACK", "run.py not importable — trying fixture", level="WARNING")
        fixture = _fixture_path(bundle_id)
        if fixture.exists():
            return fixture
        raise RuntimeError(
            "run.py could not be imported and no fixture exists for "
            f"'{bundle_id}'.  Create fixtures/{bundle_id}/final_decision.json "
            "to test the harness before the agents are merged."
        )

    run_dir = pipeline_driver.create_run_dir(bundle_id)
    log_step(log, "RUN_DIR", str(run_dir))
    pipeline_driver.run_pipeline(bundle_path, run_dir, str(POLICY_FILE), bundle_id)
    return run_dir / FILENAME_FINAL_DECISION


# ---------------------------------------------------------------------------
# Result checker
# ---------------------------------------------------------------------------

def check_bundle(
    expectation: BundleExpectation,
    decision_path: Path,
) -> list[CheckResult]:
    """Compare final_decision.json against the manifest expectations."""
    raw     = read_json(decision_path)
    results = []

    actual: dict[str, dict] = {
        d["expense_id"]: d for d in raw.get("decisions", [])
    }

    for exp in expectation.decisions:
        if exp.expense_id not in actual:
            results.append(CheckResult(
                expense_id=exp.expense_id,
                passed=False,
                detail=f"expense_id '{exp.expense_id}' missing from final_decision.json",
            ))
            continue

        act = actual[exp.expense_id]
        failures: list[str] = []

        if act.get("decision") != exp.decision:
            failures.append(
                f"decision: expected '{exp.decision}' got '{act.get('decision')}'"
            )
        if exp.approver is not None and act.get("approver") != exp.approver:
            failures.append(
                f"approver: expected '{exp.approver}' got '{act.get('approver')}'"
            )

        results.append(CheckResult(
            expense_id=exp.expense_id,
            passed=not failures,
            detail="; ".join(failures) if failures else "OK",
        ))

    raw_totals = raw.get("totals", {})

    if expectation.totals.approved_usd is not None:
        actual_approved = Decimal(str(raw_totals.get("approved_usd", "0")))
        ok = actual_approved == expectation.totals.approved_usd
        results.append(CheckResult(
            expense_id="TOTALS.approved_usd",
            passed=ok,
            detail="OK" if ok else (
                f"approved_usd: expected {expectation.totals.approved_usd} "
                f"got {actual_approved}"
            ),
        ))

    if expectation.totals.blocked_usd is not None:
        actual_blocked = Decimal(str(raw_totals.get("blocked_usd", "0")))
        ok = actual_blocked == expectation.totals.blocked_usd
        results.append(CheckResult(
            expense_id="TOTALS.blocked_usd",
            passed=ok,
            detail="OK" if ok else (
                f"blocked_usd: expected {expectation.totals.blocked_usd} "
                f"got {actual_blocked}"
            ),
        ))

    return results


# ---------------------------------------------------------------------------
# Per-bundle orchestration
# ---------------------------------------------------------------------------

def run_bundle(
    bundle_path: Path,
    policy: dict,
    verbose: bool,
) -> BundleResult:
    """Run one bundle end-to-end and return its BundleResult."""
    bundle_id = bundle_path.name
    log = get_agent_logger("DEMO", bundle_id)

    log_step(log, "BUNDLE_START", str(bundle_path))

    try:
        manifest    = load_manifest(bundle_path)
        expectation = parse_expectations(manifest, bundle_id)

        if not expectation.decisions:
            return BundleResult(
                bundle_id=bundle_id,
                passed=False,
                error="manifest.yaml has no 'expected.decisions' block — nothing to check.",
            )

        decision_path = run_pipeline_for_bundle(bundle_path, bundle_id, policy, log)

        if not decision_path.exists():
            return BundleResult(
                bundle_id=bundle_id,
                passed=False,
                error=f"final_decision.json was not produced at {decision_path}",
            )

        checks = check_bundle(expectation, decision_path)

    except Exception as exc:  # noqa: BLE001
        log_step(log, "BUNDLE_ERROR", str(exc), level="ERROR")
        return BundleResult(bundle_id=bundle_id, passed=False, error=str(exc))

    passed = all(c.passed for c in checks)
    log_step(log, "BUNDLE_DONE", f"{'PASS' if passed else 'FAIL'}")
    return BundleResult(bundle_id=bundle_id, passed=passed, checks=checks)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_bundle_result(result: BundleResult, verbose: bool) -> None:
    badge = f"{GREEN}PASS{RESET}" if result.passed else f"{RED}FAIL{RESET}"
    print(f"  {badge}  {BOLD}{result.bundle_id}{RESET}")

    if result.error:
        print(f"        {YELLOW}Error:{RESET} {result.error}")
        return

    if not result.passed or verbose:
        for chk in result.checks:
            icon = f"{GREEN}✓{RESET}" if chk.passed else f"{RED}✗{RESET}"
            line = f"        {icon}  {chk.expense_id}"
            if not chk.passed or verbose:
                line += f"  — {chk.detail}"
            print(line)


def print_summary(results: list[BundleResult]) -> None:
    total  = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    print()
    print(f"{BOLD}{'─' * 52}{RESET}")
    print(f"{BOLD}  Results: {passed}/{total} bundles passed{RESET}")
    if failed:
        print(f"  {RED}{failed} bundle(s) FAILED:{RESET}")
        for r in results:
            if not r.passed:
                print(f"    • {r.bundle_id}")
    print(f"{BOLD}{'─' * 52}{RESET}")


# ---------------------------------------------------------------------------
# Determinism check
# ---------------------------------------------------------------------------

def _normalize_for_diff(text: str, run_dir: Path) -> str:
    """Normalise *text* so two pipeline runs can be compared byte-by-byte.

    Handles the three most common sources of non-determinism:
      1. JSON key ordering or float formatting — re-parse then re-dump.
      2. Run-directory paths embedded in file content (Windows \\, /, JSON \\\\ forms).
      3. Timestamps in loguru format ("2024-05-10 14:32:01.123") and
         ISO-8601 ("2024-05-10T14:32:01.123456Z").
    """
    # Re-serialise JSON to fix unsorted keys or float-representation drift.
    try:
        obj = json.loads(text)
        text = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        pass  # Not JSON — leave as-is.

    # Replace the run-directory path in all common string forms.
    run_dir_str = str(run_dir)
    for variant in (
        run_dir_str,                            # native OS form
        run_dir_str.replace("\\", "/"),         # forward-slash form
        run_dir_str.replace("\\", "\\\\"),      # JSON-escaped backslashes
    ):
        text = text.replace(variant, "<RUN_DIR>")

    # Loguru audit-log timestamps: "2024-05-10 14:32:01.123"
    text = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+", "<TIMESTAMP>", text)
    # ISO-8601 timestamps: "2024-05-10T14:32:01.123456Z"
    text = re.sub(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?",
        "<TIMESTAMP>",
        text,
    )

    return text


def determinism_check(bundle_path: Path, policy: dict) -> bool:
    """Run the pipeline twice on *bundle_path* and verify identical outputs.

    Steps
    -----
    1. Execute the full pipeline into two separate temporary directories.
    2. Normalise each output file via _normalize_for_diff() to remove
       run-directory paths, timestamps, and key-ordering noise.
    3. Diff every file that appears in both directories.
    4. Report the first differing line (or success if all files match).

    Returns True when all files are identical after normalisation.
    """
    try:
        import run as pipeline_driver  # noqa: PLC0415
    except ImportError as exc:
        print(f"  {RED}Cannot import run.py: {exc}{RESET}")
        return False

    bundle_id = bundle_path.name
    print(f"\n{BOLD}Determinism check{RESET}  bundle={bundle_id}")

    run_dirs: list[Path] = []
    all_identical = True

    try:
        # ── Run the pipeline twice ──────────────────────────────────────────
        for run_num in (1, 2):
            tmp = Path(tempfile.mkdtemp(prefix=f"ieems_det_{bundle_id}_r{run_num}_"))
            run_dirs.append(tmp)
            print(f"  Run {run_num}: {tmp}")

            # Seed a minimal normalization_results.json so Agent C can run
            # even when Agent D is not yet implemented.  Agent D overwrites
            # this file when present; it stays as-is (empty) otherwise.
            (tmp / "normalization_results.json").write_text(
                json.dumps({"bundle_id": bundle_id, "normalized": [], "findings": []}, indent=2),
                encoding="utf-8",
            )

            try:
                pipeline_driver.run_pipeline(bundle_path, tmp, str(POLICY_FILE), bundle_id)
            except SystemExit as exc:
                print(f"  {RED}Run {run_num} aborted (exit {exc.code}).{RESET}")
                return False

        dir1, dir2 = run_dirs[0], run_dirs[1]

        # ── Collect files written to the temp directories ───────────────────
        # audit.log is written to runs/<bundle_id>/ by the logger (not the
        # temp dir), so it will never appear here — no special-casing needed.
        files1 = {p.name for p in dir1.iterdir() if p.is_file()}
        files2 = {p.name for p in dir2.iterdir() if p.is_file()}

        only_in_1 = files1 - files2
        only_in_2 = files2 - files1

        if only_in_1:
            print(f"  {RED}✗{RESET}  files only in run 1: {sorted(only_in_1)}")
            all_identical = False
        if only_in_2:
            print(f"  {RED}✗{RESET}  files only in run 2: {sorted(only_in_2)}")
            all_identical = False

        # ── Compare each shared file ────────────────────────────────────────
        for filename in sorted(files1 & files2):
            text1 = _normalize_for_diff(
                (dir1 / filename).read_text(encoding="utf-8"), dir1
            )
            text2 = _normalize_for_diff(
                (dir2 / filename).read_text(encoding="utf-8"), dir2
            )

            if text1 == text2:
                print(f"  {GREEN}✓{RESET}  {filename}")
                continue

            # Find and report the first differing line.
            lines1, lines2 = text1.splitlines(), text2.splitlines()
            diff_detail: str = ""
            for lineno, (l1, l2) in enumerate(zip(lines1, lines2), start=1):
                if l1 != l2:
                    diff_detail = (
                        f"line {lineno}:\n"
                        f"          run1: {l1!r}\n"
                        f"          run2: {l2!r}"
                    )
                    break
            if not diff_detail:
                diff_detail = (
                    f"line count differs: run1={len(lines1)} run2={len(lines2)}"
                )

            print(f"  {RED}✗{RESET}  {filename}  —  {diff_detail}")
            all_identical = False

    finally:
        for d in run_dirs:
            shutil.rmtree(d, ignore_errors=True)

    if all_identical:
        print(f"\n  {GREEN}{BOLD}All outputs identical — pipeline is deterministic.{RESET}")
    else:
        print(f"\n  {RED}{BOLD}Determinism check FAILED.{RESET}")

    return all_identical


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def load_policy() -> dict:
    if POLICY_FILE.exists():
        return yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8")) or {}
    return {}


def discover_bundles(only: str | None) -> list[Path]:
    """Return sorted list of bundle directories to test."""
    if not BUNDLES_DIR.is_dir():
        print(f"Error: input_bundles/ directory not found at {BUNDLES_DIR.resolve()}")
        sys.exit(1)

    if only:
        target = BUNDLES_DIR / only
        if not target.is_dir():
            print(f"Error: bundle '{only}' not found in {BUNDLES_DIR}")
            sys.exit(1)
        return [target]

    return sorted(p for p in BUNDLES_DIR.iterdir() if p.is_dir())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IEEMS Demo — automatic test harness for all bundles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bundle",       metavar="NAME", help="Run a single bundle by name.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-expense detail for all checks.")
    parser.add_argument("--stop-on-fail", action="store_true", help="Abort after the first FAIL.")
    parser.add_argument(
        "--determinism",
        action="store_true",
        help=(
            "Run the pipeline twice on the same bundle(s) and diff outputs. "
            "Use --bundle to restrict to one bundle."
        ),
    )
    args = parser.parse_args()

    if args.determinism:
        policy  = load_policy()
        bundles = discover_bundles(args.bundle)
        print(f"\n{BOLD}IEEMS Determinism Check{RESET}  ({len(bundles)} bundle(s))")
        ok = all(determinism_check(b, policy) for b in bundles)
        sys.exit(0 if ok else 1)

    policy  = load_policy()
    bundles = discover_bundles(args.bundle)

    print(f"\n{BOLD}IEEMS Test Harness{RESET}  ({len(bundles)} bundle(s))")
    if USE_FIXTURES:
        print(f"  {YELLOW}[FIXTURE MODE — pipeline not invoked]{RESET}")
    print()

    results: list[BundleResult] = []

    for bundle_path in bundles:
        result = run_bundle(bundle_path, policy, verbose=args.verbose)
        results.append(result)
        print_bundle_result(result, verbose=args.verbose)

        if args.stop_on_fail and not result.passed:
            print(f"\n{RED}Stopped after first failure (--stop-on-fail).{RESET}")
            break

    print_summary(results)
    sys.exit(0 if all(r.passed for r in results) else 1)


if __name__ == "__main__":
    main()