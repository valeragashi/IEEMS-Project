"""
IEEMS — Agent A: Intake
Reads a submission bundle, builds a ContextPacket, and writes context_packet.json.

Usage:
    python -m agents.agent_a_intake --bundle input_bundles/s01_clean --run-dir runs/s01_clean_0001
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

from schemas.models import ContextPacket, FileEntry

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

MANIFEST = "manifest.yaml"
OUTPUT   = "context_packet.json"


def classify_file(path: Path) -> str:
    """Return the file_type Literal for a given path."""
    name = path.name.lower()
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
    """Parse the bundle and return a ContextPacket."""
    manifest_path = bundle_path / MANIFEST
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.yaml not found in {bundle_path}")

    with manifest_path.open("r", encoding="utf-8") as fh:
        m = yaml.safe_load(fh)

    # Collect all files: receipts/ subdirectory + card_export.csv at bundle root
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

    packet = ContextPacket(
        bundle_id=m["bundle_id"],
        employee_id=m["employee_id"],
        employee_name=m["employee_name"],
        cost_center=m["cost_center"],
        submission_date=m["submission_date"],
        trip_purpose=m["trip_purpose"],
        files=files,
        risk_flags=detect_risk_flags(m["submission_date"], len(files)),
    )
    return packet


def detect_risk_flags(submission_date: str, file_count: int) -> list[str]:
    """Return any intake-level risk flags."""
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
    """Agent entry-point. Returns 0 on success, 1 on failure."""
    try:
        packet = build_context(bundle_path)
    except (FileNotFoundError, KeyError, yaml.YAMLError) as exc:
        log.error("Intake failed: %s", exc)
        return 1

    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / OUTPUT
    output_path.write_text(packet.model_dump_json(indent=2), encoding="utf-8")
    log.info("Wrote %s  (%d file(s))", output_path, len(packet.files))
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