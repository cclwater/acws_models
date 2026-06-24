#!/usr/bin/env python3
"""
Extract hourly cooling loads from EnergyPlus ReadVarsESO CSV and write the 8760-hour
LoadProfile:Plant CSV used by the ACWS plant-side IDF files.

Recommended EnergyPlus command:
    energyplus -r -w Guangzhou_Meteonorm8.epw -d output_S1 building_load_generators/S1_LoadGen_Guangzhou_LiteratureBase.idf

Then:
    python building_load_generators/extract_load_profile.py --domain S1 --eplusout output_S1/eplusout.csv --out S1_acws_load_profile.csv
    python building_load_generators/extract_load_profile.py --domain S1 --eplusout output_S1/eplusout.csv --out S1_acws_load_profile.csv --scale-to-target

The --scale-to-target option is an optional calibration step to align the peak load with the
plant-side chiller capacity/risk design used in the ACWS domain profile. It should be documented
if used in a paper.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np

PROFILE_FILE = Path(__file__).with_name("building_load_generator_profiles.json")

def load_profiles() -> dict:
    with PROFILE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def find_cooling_columns(df: pd.DataFrame) -> tuple[list[str], str]:
    cols = list(df.columns)
    lower = {c: c.lower() for c in cols}

    # Prefer the ideal cooling coil / supply-air total cooling energy.
    candidates = [
        c for c in cols
        if "zone ideal loads supply air total cooling energy" in lower[c]
        and ("[j]" in lower[c] or "(j)" in lower[c])
    ]
    if candidates:
        return candidates, "Zone Ideal Loads Supply Air Total Cooling Energy [J]"

    # Fallback: DistrictCooling meter, which is usually equal to ideal-load cooling energy.
    candidates = [
        c for c in cols
        if "districtcooling:facility" in lower[c]
        and ("[j]" in lower[c] or "(j)" in lower[c])
    ]
    if candidates:
        return candidates, "DistrictCooling:Facility [J]"

    # Fallback: zone total cooling energy.
    candidates = [
        c for c in cols
        if "zone ideal loads zone total cooling energy" in lower[c]
        and ("[j]" in lower[c] or "(j)" in lower[c])
    ]
    if candidates:
        return candidates, "Zone Ideal Loads Zone Total Cooling Energy [J]"

    # Fallback to rate columns. These are already W, not J.
    candidates = [
        c for c in cols
        if "zone ideal loads supply air total cooling rate" in lower[c]
        and ("[w]" in lower[c] or "(w)" in lower[c])
    ]
    if candidates:
        return candidates, "Zone Ideal Loads Supply Air Total Cooling Rate [W]"

    raise ValueError(
        "Could not find ideal-load cooling columns in eplusout.csv. "
        "Check that the IDF requests Zone Ideal Loads Supply Air Total Cooling Energy "
        "and that EnergyPlus was run with the -r option."
    )

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, choices=["S1","S2","S3","T1","T2","T3"])
    parser.add_argument("--eplusout", required=True, help="Path to EnergyPlus ReadVarsESO CSV, usually output_*/eplusout.csv")
    parser.add_argument("--out", required=True, help="Output CSV path, e.g., S1_acws_load_profile.csv")
    parser.add_argument("--scale-to-target", action="store_true",
                        help="Optionally scale annual profile so peak equals domain target peak.")
    args = parser.parse_args()

    profiles = load_profiles()
    prof = profiles[args.domain]
    eplusout = Path(args.eplusout)
    out = Path(args.out)

    df = pd.read_csv(eplusout)
    cols, source = find_cooling_columns(df)
    raw = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)

    if source.endswith("[J]"):
        load_w = raw / 3600.0
    else:
        load_w = raw

    load_w = load_w.clip(lower=0)

    # Keep only 8760 hourly values for LoadProfile:Plant.
    if len(load_w) < 8760:
        raise ValueError(f"Expected at least 8760 hourly rows, but found {len(load_w)} rows.")
    if len(load_w) > 8760:
        print(f"Warning: found {len(load_w)} rows; using the first 8760 rows.")
        load_w = load_w.iloc[:8760]

    raw_peak_w = float(load_w.max())
    scale_factor = 1.0
    target_peak_kw = float(prof.get("target_peak_kw", prof["plant_capacity_kw"] * prof["target_peak_ratio"]))

    if args.scale_to_target:
        target_peak_w = target_peak_kw * 1000.0
        if raw_peak_w <= 0:
            raise ValueError("Raw peak load is zero; cannot scale.")
        scale_factor = target_peak_w / raw_peak_w
        load_w = load_w * scale_factor

    out_df = pd.DataFrame({
        "Hour": np.arange(1, 8761, dtype=int),
        "CoolingLoad_W": np.round(load_w.values, 3),
    })
    out_df.to_csv(out, index=False)

    metadata = {
        "domain": args.domain,
        "source_eplusout": str(eplusout),
        "source_columns": cols,
        "source_variable_used": source,
        "raw_peak_kw": raw_peak_w / 1000.0,
        "scaled_peak_kw": float(load_w.max()) / 1000.0,
        "scale_factor": scale_factor,
        "scale_to_target": bool(args.scale_to_target),
        "target_peak_kw_if_scaled": target_peak_kw,
        "annual_cooling_MWh_thermal": float(load_w.sum()) / 1_000_000.0,
        "output_csv": str(out),
    }
    meta_path = out.with_suffix(".metadata.json")
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))

if __name__ == "__main__":
    main()
