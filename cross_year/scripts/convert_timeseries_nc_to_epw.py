"""Convert multi-year ERA5 point time series to local-time AMY EPW files.

Inputs are the CDS ERA5 single-level time-series NetCDF files downloaded for
one point. The script extracts a complete local standard-time year, converts
hourly accumulated radiation/precipitation fields, derives DNI and DHI from
ERA5 horizontal direct and global radiation, and writes an auditable EPW plus
JSON QA report. It does not download data or call an LLM.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr


REQUIRED_VARIABLES = {
    "t2m",
    "d2m",
    "sp",
    "u10",
    "v10",
    "tcc",
    "ssrd",
    "fdir",
    "strd",
    "tp",
}

EPW_COLUMNS = [
    "Year",
    "Month",
    "Day",
    "Hour",
    "Minute",
    "Data Source and Uncertainty Flags",
    "Dry Bulb Temperature",
    "Dew Point Temperature",
    "Relative Humidity",
    "Atmospheric Station Pressure",
    "Extraterrestrial Horizontal Radiation",
    "Extraterrestrial Direct Normal Radiation",
    "Horizontal Infrared Radiation Intensity",
    "Global Horizontal Radiation",
    "Direct Normal Radiation",
    "Diffuse Horizontal Radiation",
    "Global Horizontal Illuminance",
    "Direct Normal Illuminance",
    "Diffuse Horizontal Illuminance",
    "Zenith Luminance",
    "Wind Direction",
    "Wind Speed",
    "Total Sky Cover",
    "Opaque Sky Cover",
    "Visibility",
    "Ceiling Height",
    "Present Weather Observation",
    "Present Weather Codes",
    "Precipitable Water",
    "Aerosol Optical Depth",
    "Snow Depth",
    "Days Since Last Snowfall",
    "Albedo",
    "Liquid Precipitation Depth",
    "Liquid Precipitation Quantity",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--city", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--country", default="CHN")
    parser.add_argument("--timezone", type=float, default=8.0)
    parser.add_argument("--elevation", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qa-output", type=Path, required=True)
    parser.add_argument(
        "--ascii-temp-dir",
        type=Path,
        default=Path(tempfile.gettempdir()),
        help="Temporary directory used when libraries cannot read a non-ASCII path",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def open_unicode_safe(path: Path, ascii_temp_dir: Path) -> tuple[xr.Dataset, Path | None]:
    if str(path).isascii():
        print(f"[1/8] Using ASCII-safe NetCDF path: {path}", flush=True)
        dataset = xr.open_dataset(path)
        print(f"[2/8] Opened NetCDF: rows={dataset.sizes.get('valid_time', 0)}", flush=True)
        return dataset, None
    print(f"[1/8] Copying NetCDF to ASCII-safe temporary path: {path.name}", flush=True)
    ascii_temp_dir.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=ascii_temp_dir,
        prefix="era5_epw_",
        suffix=".nc",
        delete=False,
    )
    temp_path = Path(handle.name)
    handle.close()
    shutil.copyfile(path, temp_path)
    dataset = xr.open_dataset(temp_path)
    print(f"[2/8] Opened NetCDF: rows={dataset.sizes.get('valid_time', 0)}", flush=True)
    return dataset, temp_path


def relative_humidity_percent(temp_c: np.ndarray, dew_c: np.ndarray) -> np.ndarray:
    saturation = np.exp((17.625 * temp_c) / (243.04 + temp_c))
    actual = np.exp((17.625 * dew_c) / (243.04 + dew_c))
    return np.clip(100.0 * actual / saturation, 0.0, 100.0)


def solar_cosine_zenith(
    local_hour_start: pd.DatetimeIndex,
    latitude: float,
    longitude: float,
    timezone: float,
) -> np.ndarray:
    """NOAA fractional-year approximation evaluated at hourly midpoints."""
    midpoint = local_hour_start + pd.Timedelta(minutes=30)
    day = midpoint.dayofyear.to_numpy(dtype=float)
    hour = (
        midpoint.hour.to_numpy(dtype=float)
        + midpoint.minute.to_numpy(dtype=float) / 60.0
        + midpoint.second.to_numpy(dtype=float) / 3600.0
    )
    year_length = np.where(midpoint.is_leap_year, 366.0, 365.0)
    gamma = 2.0 * np.pi / year_length * (day - 1.0 + (hour - 12.0) / 24.0)
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2.0 * gamma)
        - 0.040849 * np.sin(2.0 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2.0 * gamma)
        + 0.000907 * np.sin(2.0 * gamma)
        - 0.002697 * np.cos(3.0 * gamma)
        + 0.00148 * np.sin(3.0 * gamma)
    )
    time_offset_min = equation_of_time + 4.0 * longitude - 60.0 * timezone
    true_solar_time_min = hour * 60.0 + time_offset_min
    hour_angle = np.deg2rad(true_solar_time_min / 4.0 - 180.0)
    latitude_rad = math.radians(latitude)
    cosine = (
        math.sin(latitude_rad) * np.sin(declination)
        + math.cos(latitude_rad) * np.cos(declination) * np.cos(hour_angle)
    )
    return np.clip(cosine, -1.0, 1.0)


def build_epw_frame(
    source: pd.DataFrame,
    local_index: pd.DatetimeIndex,
    latitude: float,
    longitude: float,
    timezone: float,
) -> tuple[pd.DataFrame, dict]:
    temp_c = source["t2m"].to_numpy(dtype=float) - 273.15
    dew_c = source["d2m"].to_numpy(dtype=float) - 273.15
    rh = relative_humidity_percent(temp_c, dew_c)

    ghi = np.maximum(source["ssrd"].to_numpy(dtype=float) / 3600.0, 0.0)
    direct_horizontal_raw = np.maximum(source["fdir"].to_numpy(dtype=float) / 3600.0, 0.0)
    direct_horizontal = np.minimum(direct_horizontal_raw, ghi)
    horizontal_ir = np.maximum(source["strd"].to_numpy(dtype=float) / 3600.0, 0.0)

    cosine_zenith = solar_cosine_zenith(local_index, latitude, longitude, timezone)
    sun_sufficiently_high = cosine_zenith > 0.065
    dni = np.zeros(len(source), dtype=float)
    dni[sun_sufficiently_high] = (
        direct_horizontal[sun_sufficiently_high] / cosine_zenith[sun_sufficiently_high]
    )
    dni_clipped_count = int(np.sum(dni > 1400.0))
    dni = np.clip(dni, 0.0, 1400.0)
    direct_horizontal_reconstructed = dni * np.maximum(cosine_zenith, 0.0)
    dhi = np.maximum(ghi - direct_horizontal_reconstructed, 0.0)

    u10 = source["u10"].to_numpy(dtype=float)
    v10 = source["v10"].to_numpy(dtype=float)
    wind_speed = np.sqrt(u10**2 + v10**2)
    wind_direction = (180.0 + np.degrees(np.arctan2(u10, v10))) % 360.0
    sky_cover = np.clip(np.rint(source["tcc"].to_numpy(dtype=float) * 10.0), 0, 10)
    precipitation_mm = np.maximum(source["tp"].to_numpy(dtype=float) * 1000.0, 0.0)

    data = {
        "Year": local_index.year,
        "Month": local_index.month,
        "Day": local_index.day,
        "Hour": local_index.hour + 1,
        "Minute": 60,
        "Data Source and Uncertainty Flags": "9",
        "Dry Bulb Temperature": np.round(temp_c, 1),
        "Dew Point Temperature": np.round(dew_c, 1),
        "Relative Humidity": np.rint(rh).astype(int),
        "Atmospheric Station Pressure": np.rint(source["sp"].to_numpy(dtype=float)).astype(int),
        "Extraterrestrial Horizontal Radiation": 9999,
        "Extraterrestrial Direct Normal Radiation": 9999,
        "Horizontal Infrared Radiation Intensity": np.rint(horizontal_ir).astype(int),
        "Global Horizontal Radiation": np.rint(ghi).astype(int),
        "Direct Normal Radiation": np.rint(dni).astype(int),
        "Diffuse Horizontal Radiation": np.rint(dhi).astype(int),
        "Global Horizontal Illuminance": np.rint(110.0 * ghi).astype(int),
        "Direct Normal Illuminance": np.rint(105.0 * dni).astype(int),
        "Diffuse Horizontal Illuminance": np.rint(119.0 * dhi).astype(int),
        "Zenith Luminance": 9999,
        "Wind Direction": np.rint(wind_direction).astype(int),
        "Wind Speed": np.round(wind_speed, 1),
        "Total Sky Cover": sky_cover.astype(int),
        "Opaque Sky Cover": sky_cover.astype(int),
        "Visibility": 9999,
        "Ceiling Height": 77777,
        "Present Weather Observation": 9,
        "Present Weather Codes": 999999999,
        "Precipitable Water": 999,
        "Aerosol Optical Depth": 0.999,
        "Snow Depth": 999,
        "Days Since Last Snowfall": 99,
        "Albedo": 0.2,
        "Liquid Precipitation Depth": np.round(precipitation_mm, 3),
        "Liquid Precipitation Quantity": 1,
    }
    frame = pd.DataFrame(data, columns=EPW_COLUMNS)
    diagnostics = {
        "negative_ssrd_values_clipped": int(np.sum(source["ssrd"].to_numpy(dtype=float) < 0.0)),
        "fdir_greater_than_ssrd_values_clipped": int(np.sum(direct_horizontal_raw > ghi)),
        "dni_values_clipped_above_1400": dni_clipped_count,
        "solar_balance_max_abs_wh_m2": float(
            np.max(np.abs(ghi - (dhi + dni * np.maximum(cosine_zenith, 0.0))))
        ),
        "solar_cosine_threshold": 0.065,
        "dni_upper_bound_wh_m2": 1400.0,
    }
    return frame, diagnostics


def write_epw(
    output: Path,
    frame: pd.DataFrame,
    city: str,
    state: str,
    country: str,
    latitude: float,
    longitude: float,
    timezone: float,
    elevation: float,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    first_weekday = calendar.day_name[pd.Timestamp(int(frame.iloc[0]["Year"]), 1, 1).weekday()]
    header = [
        f"LOCATION,{city},{state},{country},ERA5,999999,{latitude:.2f},{longitude:.2f},{timezone:g},{elevation:g}",
        "DESIGN CONDITIONS,0",
        "TYPICAL/EXTREME PERIODS,0",
        "GROUND TEMPERATURES,0",
        "HOLIDAYS/DAYLIGHT SAVINGS,No,0,0,0",
        "COMMENTS 1,ERA5 hourly point time series from the Copernicus Climate Data Store",
        "COMMENTS 2,UTC shifted to local standard time; ERA5 hourly radiation converted from J/m2 to Wh/m2",
        f"DATA PERIODS,1,1,Data,{first_weekday},1/1,12/31",
    ]
    with output.open("w", encoding="utf-8", newline="") as handle:
        for line in header:
            handle.write(line + "\n")
        frame.to_csv(handle, index=False, header=False, lineterminator="\n")


def main() -> None:
    args = parse_args()
    dataset, temp_path = open_unicode_safe(args.input.resolve(), args.ascii_temp_dir.resolve())
    try:
        missing_variables = sorted(REQUIRED_VARIABLES - set(dataset.data_vars))
        if missing_variables:
            raise RuntimeError(f"Missing required variables: {missing_variables}")
        latitude = float(dataset["latitude"].item())
        longitude = float(dataset["longitude"].item())
        utc_index = pd.DatetimeIndex(pd.to_datetime(dataset["valid_time"].values))
        print(f"[3/8] Validated coordinates and UTC index: {latitude}, {longitude}", flush=True)
        if utc_index.has_duplicates or not utc_index.is_monotonic_increasing:
            raise RuntimeError("Input time coordinate is duplicated or unsorted")
        source = dataset[list(sorted(REQUIRED_VARIABLES))].to_dataframe()
        source.index = utc_index
        print(f"[4/8] Loaded required variables into memory: rows={len(source)}", flush=True)

        local_index_all = utc_index + pd.Timedelta(hours=args.timezone)
        mask = local_index_all.year == args.year
        source_year = source.loc[mask].copy()
        local_index = pd.DatetimeIndex(local_index_all[mask])
        expected_rows = 8784 if calendar.isleap(args.year) else 8760
        if len(source_year) != expected_rows:
            raise RuntimeError(
                f"Expected {expected_rows} local-year rows for {args.year}, got {len(source_year)}"
            )
        expected_local = pd.date_range(
            f"{args.year}-01-01 00:00:00",
            f"{args.year}-12-31 23:00:00",
            freq="h",
        )
        if not local_index.equals(expected_local):
            raise RuntimeError("Local standard-time index is not a complete hourly calendar year")
        print(f"[5/8] Extracted complete local year {args.year}: rows={len(source_year)}", flush=True)

        frame, solar_diagnostics = build_epw_frame(
            source_year,
            local_index,
            latitude,
            longitude,
            args.timezone,
        )
        if frame.isna().any().any():
            raise RuntimeError("NaN found in generated EPW frame")
        print("[6/8] Derived EPW meteorological and solar fields", flush=True)
        write_epw(
            args.output,
            frame,
            args.city,
            args.state,
            args.country,
            latitude,
            longitude,
            args.timezone,
            args.elevation,
        )
        print(f"[7/8] Wrote EPW: {args.output}", flush=True)

        qa = {
            "input_file": str(args.input.resolve()),
            "input_sha256": sha256(args.input.resolve()),
            "output_file": str(args.output.resolve()),
            "output_sha256": sha256(args.output.resolve()),
            "source": "ERA5 hourly single-level point time series",
            "source_coordinates": {"latitude": latitude, "longitude": longitude},
            "timezone_hours": args.timezone,
            "year": args.year,
            "rows": len(frame),
            "first_local_timestamp": str(local_index[0]),
            "last_local_timestamp": str(local_index[-1]),
            "dry_bulb_c": {
                "min": float(frame["Dry Bulb Temperature"].min()),
                "max": float(frame["Dry Bulb Temperature"].max()),
                "mean": float(frame["Dry Bulb Temperature"].mean()),
            },
            "dew_point_c": {
                "min": float(frame["Dew Point Temperature"].min()),
                "max": float(frame["Dew Point Temperature"].max()),
                "mean": float(frame["Dew Point Temperature"].mean()),
            },
            "relative_humidity_percent": {
                "min": int(frame["Relative Humidity"].min()),
                "max": int(frame["Relative Humidity"].max()),
                "mean": float(frame["Relative Humidity"].mean()),
            },
            "radiation_wh_m2": {
                "ghi_max": int(frame["Global Horizontal Radiation"].max()),
                "dni_max": int(frame["Direct Normal Radiation"].max()),
                "dhi_max": int(frame["Diffuse Horizontal Radiation"].max()),
                "horizontal_ir_max": int(frame["Horizontal Infrared Radiation Intensity"].max()),
            },
            "wind_speed_m_s": {
                "min": float(frame["Wind Speed"].min()),
                "max": float(frame["Wind Speed"].max()),
                "mean": float(frame["Wind Speed"].mean()),
            },
            "precipitation_mm_sum": float(frame["Liquid Precipitation Depth"].sum()),
            "solar_derivation": {
                "ghi": "max(ssrd / 3600, 0)",
                "direct_horizontal": "clip(fdir / 3600, 0, ghi)",
                "dni": "direct_horizontal / cos(solar_zenith) when cos(zenith)>0.065; clipped to 1400",
                "dhi": "ghi - dni*cos(solar_zenith)",
                "solar_position": "NOAA fractional-year approximation at hourly midpoint",
                **solar_diagnostics,
            },
            "status": "PASS",
        }
        args.qa_output.parent.mkdir(parents=True, exist_ok=True)
        args.qa_output.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[8/8] Wrote QA: {args.qa_output}", flush=True)
        print(json.dumps(qa, ensure_ascii=False, indent=2))
    finally:
        dataset.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
