# ACWS EnergyPlus 24.2 model and weather files

This repository contains the EnergyPlus model and weather inputs used for the
multi-domain air-conditioning water system (ACWS) control study.

## Scope

Only model-side files and weather inputs are included here. Training scripts,
reinforcement-learning checkpoints, paper drafts, result tables, and reference
PDFs are not included.

## EnergyPlus version

- EnergyPlus version: 24.2
- Model type: water-side chiller plant / ACWS models with building-side cooling
  load schedules

## Domain mapping

| Domain | Model file | Weather file | Role in the paper |
|---|---|---|---|
| S1 | `models/S1_3Chiller_LiteratureBase_Guangzhou_buildingload_test.idf` | `weather/Guangzhou_CH-hour_inter.epw` | Literature-based source domain |
| S2 | `models/S2_3Chiller_CapacityScaled_Guangzhou_buildingload_test.idf` | `weather/Guangzhou_CH-hour_inter.epw` | Capacity-scaled source domain |
| S3 | `models/S3_3Chiller_ActionBoundMismatch_Guangzhou_buildingload_test.idf` | `weather/Guangzhou_CH-hour_inter.epw` | Action-bound-mismatch source domain |
| T1 | `models/T1_3Chiller_SimilarTarget_Guangzhou_buildingload_test.idf` | `weather/Guangzhou_CH-hour_inter.epw` | Similar low-risk target domain |
| T2 | `models/T2_3Chiller_MediumMismatch_Guangzhou_buildingload_test.idf` | `weather/Guangzhou_CH-hour_inter.epw` | Medium-mismatch target domain |
| T3 | `models/T3_3Chiller_HighRisk_HongKong_physical_matched_buildingload_test.idf` | `weather/Hong_Kong_Observatory-hour_station.epw` | High-risk hot-humid target domain |

The T3 model is the physically matched/calibrated version used after correcting
the original high-load target-domain capacity mismatch.

## Load-profile inputs

The IDF files use `Schedule:File` objects. Therefore, the following CSV files in
`load_profiles/` are part of the model input package and should be kept with the
IDF files:

- `S1_generated_load_profile_test_eplus_cooling.csv`
- `S2_generated_load_profile_test_eplus_cooling.csv`
- `S3_generated_load_profile_test_eplus_cooling.csv`
- `T1_generated_load_profile_test_eplus_cooling.csv`
- `T2_generated_load_profile_test_eplus_cooling.csv`
- `T3_generated_load_profile_test_eplus_cooling.csv`

Each file contains 8760 hourly values. The second column is the cooling load in
W as used by EnergyPlus `LoadProfile:Plant`.

## Building-load generator models

The `building_load_generators/` folder contains the simplified EnergyPlus
building-side load generator IDFs used to create the cooling-load schedules for
the six domains. These files are included only as model-supporting materials.

## Suggested run command

Example for S1:

```powershell
energyplus -w .\weather\Guangzhou_CH-hour_inter.epw -d .\runs\S1 .\models\S1_3Chiller_LiteratureBase_Guangzhou_buildingload_test.idf
```

Example for T3:

```powershell
energyplus -w .\weather\Hong_Kong_Observatory-hour_station.epw -d .\runs\T3 .\models\T3_3Chiller_HighRisk_HongKong_physical_matched_buildingload_test.idf
```

If EnergyPlus is installed outside the system path, replace `energyplus` with
the full path to the EnergyPlus 24.2 executable.
