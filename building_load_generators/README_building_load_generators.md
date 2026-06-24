# Building-side EnergyPlus load generators for ACWS domain models

This folder adds building-side IDF models for generating weather-consistent hourly cooling loads from Meteonorm EPW files.

## Recommended structure

The ACWS plant models remain the final chiller-plant simulation models. The building-side models in this folder are used only to generate the 8760-hour cooling-load CSV files read by `LoadProfile:Plant`.

Workflow:

1. Generate EPW files in Meteonorm 8:
   - `Guangzhou_Meteonorm8.epw`
   - `HongKong_Meteonorm8.epw`
2. Run the building-side load-generator IDF with EnergyPlus 24.2.0.
3. Use `extract_load_profile.py` to convert `eplusout.csv` into `S1_acws_load_profile.csv`, etc.
4. Run the corresponding ACWS plant-side IDF.

## Why six load-generator IDFs?

The load-generator models are derived from two literature/location anchors:

- Guangzhou equivalent large commercial / office / mixed-use cooling-load model.
- Hong Kong high-humidity office/lab cooling-load model.

Six IDFs are provided because each ACWS domain needs a reproducible target load profile:

| Domain | Building load generator | EPW |
|---|---|---|
| S1 | S1_LoadGen_Guangzhou_LiteratureBase.idf | Guangzhou_Meteonorm8.epw |
| S2 | S2_LoadGen_Guangzhou_CapacityScaled.idf | Guangzhou_Meteonorm8.epw |
| S3 | S3_LoadGen_Guangzhou_ActionBoundMismatch.idf | Guangzhou_Meteonorm8.epw |
| T1 | T1_LoadGen_Guangzhou_SimilarTarget.idf | Guangzhou_Meteonorm8.epw |
| T2 | T2_LoadGen_Guangzhou_MediumMismatch.idf | Guangzhou_Meteonorm8.epw |
| T3 | T3_LoadGen_HongKong_HighRisk.idf | HongKong_Meteonorm8.epw |

This is preferable to making only two raw building models because the six ACWS domains need slightly different load/risk conditions. It is also preferable to making six unrelated buildings because the domain differences remain controlled.

## Example command

```bash
energyplus -r -w Guangzhou_Meteonorm8.epw -d output_load_S1 building_load_generators/S1_LoadGen_Guangzhou_LiteratureBase.idf
python building_load_generators/extract_load_profile.py --domain S1 --eplusout output_load_S1/eplusout.csv --out S1_acws_load_profile.csv --scale-to-target
```

For Windows, use `run_load_generation_examples.bat`.

## About optional scaling

The `--scale-to-target` option scales the raw annual building-load profile so the peak load matches the intended plant-side risk/capacity ratio. This is an equivalent-load calibration step, not a weather replacement step. Use it if the raw building load does not match the plant-side chiller capacity.

To inspect raw loads first, omit `--scale-to-target`:

```bash
python building_load_generators/extract_load_profile.py --domain S1 --eplusout output_load_S1/eplusout.csv --out S1_raw_load_profile.csv
```

## Output CSV format

The output file matches the ACWS plant models:

```csv
Hour,CoolingLoad_W
1,5200000
2,5100000
...
8760,4800000
```

Units are W. The file has 8760 data rows plus one header row.

## EnergyPlus output variables

The models request:

- `Zone Ideal Loads Supply Air Total Cooling Energy`
- `Zone Ideal Loads Zone Total Cooling Energy`
- `DistrictCooling:Facility`

The extraction script prefers `Zone Ideal Loads Supply Air Total Cooling Energy` because it corresponds to the ideal cooling coil load including outdoor-air conditioning impact.
