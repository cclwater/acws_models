# Cross-year EnergyPlus inputs

This folder contains the 2019 and 2022 ERA5-based inputs used for the
unseen-weather-year validation.

## Contents

- `weather/`: Guangzhou and Hong Kong EPW files for 2019 and 2022.
- `models/scaled/`: risk-matched cases preserving the study's intended
  peak-load/capacity ratios (T1 = 0.92, T2 = 0.93, T3 = 1.15).
- `models/raw/`: sensitivity cases retaining natural ERA5-driven load levels.
- `qa/`: conversion metadata and physical-range checks for the four EPWs.
- `results/`: compact annual, contrast, bootstrap, and pooled summary tables.
- `scripts/`: utilities for converting source NetCDF files and producing
  EnergyPlus plant schedule CSV files.

Each model directory contains an IDF and its local `Schedule:File` CSV. The
three policies reuse the same weather and cooling-load schedule for a given
domain/year/load-mode combination; only the frozen supervisory schedule
differs.

## Naming convention

```text
models/<load-mode>/<domain>_<year>_<policy>/
```

where:

- `<load-mode>` is `scaled` or `raw`;
- `<domain>` is `T1`, `T2`, or `T3`;
- `<year>` is `2019` or `2022`;
- `<policy>` is `llm`, `deterministic`, or `bounded_rule`.

The `llm` label denotes a previously saved and frozen routing table. These
EnergyPlus runs do not make API calls.

## Recreating EPW files from ERA5 NetCDF

The raw NetCDF downloads are not included. After downloading an ERA5 hourly
single-level point time series, install the optional dependencies and run, for
example:

```bash
python -m pip install -r requirements-optional.txt
python cross_year/scripts/convert_timeseries_nc_to_epw.py \
  --input source_nc/guangzhou.nc \
  --year 2019 \
  --city Guangzhou \
  --state Guangdong \
  --elevation 21 \
  --output cross_year/weather/Guangzhou_ERA5_2019.epw \
  --qa-output cross_year/qa/Guangzhou_ERA5_2019_QA.json
```

The QA JSON files distributed here refer to the source NetCDF by a portable
placeholder path and preserve its SHA-256 hash for provenance checking.

## Reported protocol

The primary revision result uses `scaled`; paired daily differences are
computed within each weather year rather than pooling years. The `raw` cases
are a sensitivity analysis connecting the overloaded T3 boundary test to
ordinary below-capacity operation.

