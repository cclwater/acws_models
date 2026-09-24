# ACWS EnergyPlus simulation package

This repository contains the EnergyPlus inputs used for the multi-domain
air-conditioning water system (ACWS) study and its revision experiments.
It is limited to the simulation layer: EnergyPlus models, weather files,
cooling-load schedules, weather-conversion utilities, and compact result
summaries. Reinforcement-learning checkpoints, LLM credentials/responses,
paper drafts, and large EnergyPlus runtime outputs are not included.

## Requirements

- EnergyPlus 24.2
- Python 3.10 or newer for the helper scripts
- Optional Python packages in `requirements-optional.txt` only when converting
  ERA5 NetCDF files to EPW

## Repository layout

```text
.
|-- models/                    # six baseline ACWS plant models
|-- load_profiles/             # 8760-hour schedules used by baseline models
|-- weather/                   # Guangzhou and Hong Kong baseline EPW files
|-- building_load_generators/  # supporting building-side load models
|-- cross_year/
|   |-- models/                # 2019/2022 raw and risk-matched IDFs
|   |-- weather/               # four ERA5-derived EPW files
|   |-- qa/                    # weather conversion checks
|   |-- results/               # compact cross-year summary tables
|   `-- scripts/               # NetCDF-to-EPW and schedule utilities
`-- run_energyplus.py          # portable baseline/cross-year runner
```

## Baseline domain mapping

| Domain | Model | Weather | Purpose |
|---|---|---|---|
| S1 | `models/S1_3Chiller_LiteratureBase_Guangzhou_buildingload_test.idf` | Guangzhou | literature-based source |
| S2 | `models/S2_3Chiller_CapacityScaled_Guangzhou_buildingload_test.idf` | Guangzhou | capacity-scaled source |
| S3 | `models/S3_3Chiller_ActionBoundMismatch_Guangzhou_buildingload_test.idf` | Guangzhou | action-bound-mismatch source |
| T1 | `models/T1_3Chiller_SimilarTarget_Guangzhou_buildingload_test.idf` | Guangzhou | similar target |
| T2 | `models/T2_3Chiller_MediumMismatch_Guangzhou_buildingload_test.idf` | Guangzhou | moderate-mismatch target |
| T3 | `models/T3_3Chiller_HighRisk_HongKong_physical_matched_buildingload_test.idf` | Hong Kong | high-risk boundary target |

The T3 file is the physically matched version used in the reported study.
Each baseline IDF reads its corresponding CSV under `load_profiles/` through
an EnergyPlus `Schedule:File` object.

## Run examples

Show a command without starting EnergyPlus:

```bash
python run_energyplus.py --suite base --domain S1 --dry-run
```

Run one baseline domain:

```bash
python run_energyplus.py --suite base --domain T3
```

Run the 2019 risk-matched T3 model with the frozen LLM route:

```bash
python run_energyplus.py --suite cross-year --domain T3 --year 2019 --mode scaled --policy llm
```

Run every risk-matched cross-year case (18 annual simulations):

```bash
python run_energyplus.py --suite cross-year --domain all --year all --mode scaled --policy all
```

If EnergyPlus is not on `PATH`, pass the executable explicitly:

```bash
python run_energyplus.py --energyplus "C:/EnergyPlusV24-2-0/energyplus.exe" --suite base --domain S1
```

Outputs are written below `runs/`, which is excluded by `.gitignore`. By
default the runner also invokes the `ReadVarsESO` utility distributed with
EnergyPlus and creates `eplusout.csv`; use `--skip-readvars` to keep only the
native ESO output.

## Cross-year validation

The `cross_year/` folder contains the unseen-year 2019 and 2022 inputs used in
the revision. `scaled` denotes the risk-matched protocol that preserves the
submitted peak-load/capacity ratios; `raw` retains the natural ERA5-driven
load magnitude. The `llm`, `deterministic`, and `bounded_rule` names identify
the frozen supervisory schedule embedded in each generated IDF. Running these
IDFs does not query an online LLM.

See [`cross_year/README.md`](cross_year/README.md) for details and limitations.

## Reproducibility notes

- Run commands from the repository root or use `run_energyplus.py`; the script
  selects the correct working directory for `Schedule:File` paths.
- Weather QA metadata record the ERA5 grid point, year, row count, hashes, and
  physical-range checks.
- Raw downloaded NetCDF files are intentionally not committed. They can be
  regenerated from Copernicus ERA5 and converted with the included utility.
- Full `eplusout.*`, timestep transition files, trained policies, and API audit
  records are intentionally excluded because they are not EnergyPlus inputs.

## License and citation

No open-source license has yet been selected. Add a `LICENSE` file before
advertising reuse permissions. When the associated article is published, add
its final citation and DOI here.

Before making the repository public, also confirm that the two legacy baseline
EPW files under `weather/` may be redistributed under their original provider
terms. The ERA5-derived files should be accompanied by the applicable
Copernicus/ERA5 acknowledgement in the final repository description.
