"""Run the packaged ACWS EnergyPlus 24.2 simulations.

The script uses only the Python standard library. It deliberately keeps the
working directory compatible with each IDF's Schedule:File reference.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent

BASE_MODELS = {
    "S1": "S1_3Chiller_LiteratureBase_Guangzhou_buildingload_test.idf",
    "S2": "S2_3Chiller_CapacityScaled_Guangzhou_buildingload_test.idf",
    "S3": "S3_3Chiller_ActionBoundMismatch_Guangzhou_buildingload_test.idf",
    "T1": "T1_3Chiller_SimilarTarget_Guangzhou_buildingload_test.idf",
    "T2": "T2_3Chiller_MediumMismatch_Guangzhou_buildingload_test.idf",
    "T3": "T3_3Chiller_HighRisk_HongKong_physical_matched_buildingload_test.idf",
}


@dataclass(frozen=True)
class Case:
    name: str
    idf: Path
    weather: Path
    workdir: Path
    output: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--energyplus",
        default=os.environ.get("ENERGYPLUS_EXE", "energyplus"),
        help="EnergyPlus executable or ENERGYPLUS_EXE environment variable",
    )
    parser.add_argument("--suite", choices=("base", "cross-year"), default="base")
    parser.add_argument(
        "--domain",
        choices=("all", "S1", "S2", "S3", "T1", "T2", "T3"),
        default="all",
    )
    parser.add_argument("--year", choices=("all", "2019", "2022"), default="all")
    parser.add_argument("--mode", choices=("scaled", "raw"), default="scaled")
    parser.add_argument(
        "--policy",
        choices=("all", "llm", "deterministic", "bounded_rule"),
        default="all",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "runs")
    parser.add_argument(
        "--skip-readvars",
        action="store_true",
        help="Keep the ESO output without converting it to eplusout.csv",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def weather_for(domain: str, year: str | None = None) -> Path:
    city = "HongKong" if domain == "T3" else "Guangzhou"
    if year is None:
        filename = (
            "Hong_Kong_Observatory-hour_station.epw"
            if city == "HongKong"
            else "Guangzhou_CH-hour_inter.epw"
        )
        return ROOT / "weather" / filename
    return ROOT / "cross_year" / "weather" / f"{city}_ERA5_{year}.epw"


def base_cases(args: argparse.Namespace) -> list[Case]:
    domains = list(BASE_MODELS) if args.domain == "all" else [args.domain]
    cases: list[Case] = []
    for domain in domains:
        idf = ROOT / "models" / BASE_MODELS[domain]
        cases.append(
            Case(
                name=f"base_{domain}",
                idf=idf,
                weather=weather_for(domain),
                workdir=ROOT,
                output=args.output_dir / "base" / domain,
            )
        )
    return cases


def cross_year_cases(args: argparse.Namespace) -> list[Case]:
    if args.domain in {"S1", "S2", "S3"}:
        raise ValueError("Cross-year inputs are provided only for T1, T2, and T3")
    domains = ["T1", "T2", "T3"] if args.domain == "all" else [args.domain]
    years = ["2019", "2022"] if args.year == "all" else [args.year]
    policies = (
        ["llm", "deterministic", "bounded_rule"]
        if args.policy == "all"
        else [args.policy]
    )
    cases: list[Case] = []
    for domain in domains:
        for year in years:
            for policy in policies:
                dirname = f"{domain}_{year}_{policy}"
                model_dir = ROOT / "cross_year" / "models" / args.mode / dirname
                idf = model_dir / f"{domain}_ERA5_{year}_{policy}_{args.mode}.idf"
                cases.append(
                    Case(
                        name=f"{args.mode}_{dirname}",
                        idf=idf,
                        weather=weather_for(domain, year),
                        workdir=model_dir,
                        output=args.output_dir / "cross_year" / args.mode / dirname,
                    )
                )
    return cases


def validate_case(case: Case) -> None:
    missing = [path for path in (case.idf, case.weather) if not path.is_file()]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing input for {case.name}: {joined}")


def command_for(executable: str, case: Case) -> list[str]:
    return [
        executable,
        "-w",
        str(case.weather.resolve()),
        "-d",
        str(case.output.resolve()),
        str(case.idf.resolve()),
    ]


def resolve_readvars(executable: str) -> Path | None:
    resolved = Path(executable) if Path(executable).is_file() else None
    if resolved is None:
        found = shutil.which(executable)
        resolved = Path(found) if found else None
    if resolved is None:
        return None
    names = ("ReadVarsESO.exe", "ReadVarsESO")
    candidates = [resolved.parent / "PostProcess" / name for name in names]
    candidates.extend(resolved.parent / name for name in names)
    return next((path for path in candidates if path.is_file()), None)


def convert_eso_to_csv(readvars: Path, output: Path) -> int:
    rvi = output / "eplusout.rvi"
    rvi.write_text("eplusout.eso\neplusout.csv\n0\n", encoding="ascii")
    completed = subprocess.run(
        [str(readvars), rvi.name, "unlimited"], cwd=output, check=False
    )
    return completed.returncode


def main() -> int:
    args = parse_args()
    try:
        cases = base_cases(args) if args.suite == "base" else cross_year_cases(args)
        for case in cases:
            validate_case(case)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    executable = args.energyplus
    if not args.dry_run and not Path(executable).is_file() and shutil.which(executable) is None:
        print(
            "error: EnergyPlus executable not found; use --energyplus or set ENERGYPLUS_EXE",
            file=sys.stderr,
        )
        return 2

    readvars = None if args.skip_readvars or args.dry_run else resolve_readvars(executable)
    if not args.skip_readvars and not args.dry_run and readvars is None:
        print(
            "error: ReadVarsESO was not found beside the EnergyPlus installation; "
            "use --skip-readvars to keep only the ESO output",
            file=sys.stderr,
        )
        return 2

    for index, case in enumerate(cases, start=1):
        command = command_for(executable, case)
        print(f"[{index}/{len(cases)}] {case.name}")
        print("  " + shlex.join(command))
        if args.dry_run:
            continue
        case.output.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(command, cwd=case.workdir, check=False)
        if completed.returncode != 0:
            print(f"error: {case.name} failed with code {completed.returncode}", file=sys.stderr)
            return completed.returncode
        if readvars is not None:
            conversion_code = convert_eso_to_csv(readvars, case.output)
            if conversion_code != 0:
                print(
                    f"error: ReadVarsESO failed for {case.name} with code {conversion_code}",
                    file=sys.stderr,
                )
                return conversion_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
