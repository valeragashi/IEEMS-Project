"""
IEEMS — Agent A: Intake
Reads a submission bundle, builds a ContextPacket, and writes context_packet.json.

Usage:
    python -m agents.agent_a_intake --bundle input_bundles/s01_clean --run-dir runs/s01_clean_0001
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import yaml

from schemas.models import ContextPacket, FileEntry
from utils.constants import AGENT_A, FILENAME_CONTEXT_PACKET
from utils.json_utils import model_to_dict, write_json
from utils.logger import get_agent_logger, log_step

MANIFEST = "manifest.yaml"


def classify_file(path: Path) -> str:
    """Return the file_type string for a given path."""
    name   = path.name.lower()
    suffix = path.suffix.lower()
    if name == "card_export.csv":
        return "card_export"
    if suffix == ".pdf":
        return "receipt_pdf"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "receipt_image"
    return "unknown"


def hash_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's raw bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_context(bundle_path: Path) -> ContextPacket:
    """Parse the bundle manifest and file listing; return a ContextPacket."""
    manifest_path = bundle_path / MANIFEST
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.yaml not found in {bundle_path}")

    with manifest_path.open("r", encoding="utf-8") as fh:
        m = yaml.safe_load(fh)

    # Collect receipts/ subdirectory + card_export.csv at bundle root
    receipt_dir = bundle_path / "receipts"
    candidates: list[Path] = []
    if receipt_dir.is_dir():
        candidates.extend(receipt_dir.iterdir())
    card_export = bundle_path / "card_export.csv"
    if card_export.exists():
        candidates.append(card_export)

    files: list[FileEntry] = [
        FileEntry(
            file_id=f"F{i + 1:03d}",
            filename=p.name,
            file_type=classify_file(p),
            sha256=hash_file(p),
        )
        for i, p in enumerate(sorted(candidates, key=lambda p: p.name))
    ]

    # NOTE: risk_flags is intentionally NOT passed — ContextPacket schema
    # does not include it. Risk signals are logged only (see run() below).
    return ContextPacket(
        bundle_id=m["bundle_id"],
        employee_id=m["employee_id"],
        employee_name=m["employee_name"],
        cost_center=m["cost_center"],
        submission_date=m["submission_date"],
        trip_purpose=m["trip_purpose"],
        files=files,
    )


def detect_risk_flags(submission_date: str, file_count: int) -> list[str]:
    """Return intake-level risk flag strings (logged only, not stored in packet)."""
    from datetime import datetime
    flags: list[str] = []
    try:
        d = datetime.strptime(str(submission_date), "%Y-%m-%d").date()
        if d.weekday() >= 5:
            flags.append("WEEKEND_SUBMISSION")
    except ValueError:
        pass
    if file_count > 15:
        flags.append("LARGE_BUNDLE")
    return flags


def run(bundle_path: Path, run_dir: Path, policy: dict | None = None) -> int:
    """Agent entry-point.

    Contract (all agents share this signature):
        bundle_path : Path  — root of the input bundle directory
        run_dir     : Path  — where all output JSON files are written
        policy      : dict  — loaded expense_policy.yaml (may be empty dict)

    Returns 0 on success, 1 on failure.
    """
    # Logger is initialised here; bundle_id is read from manifest if possible.
    # We use a temporary ID until we have parsed the manifest successfully.
    log = get_agent_logger(AGENT_A, bundle_path.name)

    log_step(log, "START", f"bundle={bundle_path}")

    try:
        packet = build_context(bundle_path)
    except (FileNotFoundError, KeyError, yaml.YAMLError) as exc:
        log_step(log, "FAIL", str(exc), level="ERROR")
        return 1

    # Re-bind logger now that we have the real bundle_id.
    log = get_agent_logger(AGENT_A, packet.bundle_id)

    # Detect and log risk flags without touching the frozen schema.
    flags = detect_risk_flags(packet.submission_date, len(packet.files))
    if flags:
        log_step(log, "RISK_FLAGS", ", ".join(flags), level="WARNING")
    else:
        log_step(log, "RISK_FLAGS", "none")

    # Write output using the shared deterministic utility (sorted keys,
    # atomic write, Decimal-safe) — never raw model_dump_json().
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / FILENAME_CONTEXT_PACKET
    write_json(model_to_dict(packet), output_path)

    log_step(log, "DONE", f"wrote {output_path} ({len(packet.files)} file(s))")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="IEEMS Agent A — Intake")
    parser.add_argument("--bundle",  type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.exit(run(args.bundle, args.run_dir))


if __name__ == "__main__":
    main()