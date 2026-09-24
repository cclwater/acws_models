"""Create EnergyPlus LoadProfile:Plant schedules from positive load magnitudes.

The building-load extractor stores cooling-load magnitudes as positive watts.
The ACWS plant IDFs use EnergyPlus LoadProfile:Plant, where cooling loads are
represented by negative schedule values. This script performs only that sign
conversion and records hashes for traceability.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 8760:
        raise RuntimeError(f"Expected 8760 rows, got {len(rows)}: {args.input}")

    output_rows: list[dict[str, str]] = []
    positive_count = 0
    peak_magnitude_w = 0.0
    for expected_hour, row in enumerate(rows, start=1):
        hour = int(row["Hour"])
        if hour != expected_hour:
            raise RuntimeError(f"Unexpected hour {hour}; expected {expected_hour}")
        magnitude = max(float(row["CoolingLoad_W"]), 0.0)
        peak_magnitude_w = max(peak_magnitude_w, magnitude)
        if magnitude > 0:
            positive_count += 1
        plant_load = -magnitude
        output_rows.append(
            {
                "Hour": str(hour),
                "CoolingLoad_W": f"{plant_load:.3f}",
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Hour", "CoolingLoad_W"])
        writer.writeheader()
        writer.writerows(output_rows)

    metadata = {
        "source_file": str(args.input.resolve()),
        "source_sha256": sha256(args.input),
        "output_file": str(args.output.resolve()),
        "output_sha256": sha256(args.output),
        "rows": len(output_rows),
        "nonzero_hours": positive_count,
        "peak_magnitude_kw": peak_magnitude_w / 1000.0,
        "plant_schedule_min_kw": -peak_magnitude_w / 1000.0,
        "plant_schedule_max_kw": 0.0,
        "sign_convention": "negative schedule values represent cooling load in LoadProfile:Plant",
        "status": "PASS",
    }
    metadata_path = args.output.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

