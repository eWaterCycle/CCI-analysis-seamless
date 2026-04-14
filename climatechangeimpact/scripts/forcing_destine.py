import xarray as xr
import pandas as pd
import numpy as np
import os
import shutil
import zipfile
from pathlib import Path
# For taking destinE data
import geopandas as gpd
import rioxarray
import json
import yaml
import earthkit.data
import earthkit.regrid
from dask.diagnostics import ProgressBar
from datetime import datetime

import fiona
import urllib3
from cartopy.io import shapereader

# General eWaterCycle
import ewatercycle
import ewatercycle.models
import ewatercycle.forcing


from ewatercycle.base.forcing import DefaultForcing
from ewatercycle.util import get_time

from dask.diagnostics import ProgressBar

import logging

# Suppress specific loggers
for logger_name in ["earthkit", "polytope", "earthkit.data"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)
# from cacheb_authentication_new import authenticate

# token = authenticate()

# netrc_content = f"""machine cacheb.dcms.destine.eu
#     login anonymous
#     password {token}
# """

# with open(Path.home() / ".netrc", "a") as fp:
#     fp.write(netrc_content)

DESTINE_CLIMATE_DATA_URL = "https://cacheb.dcms.destine.eu/d1-climate-dt/ScenarioMIP-SSP3-7.0-IFS-NEMO-0001-high-sfc-v0.zarr"  # https://destine.ecmwf.int/climate-change-adaptation-digital-twin-climate-dt/#1730973047014-709bbfad-4970

# Polytope endpoint for retrieving historical data (not available as zarr on Cache B).
# The LUMI endpoint is used by default; MN5 alternative: polytope.mn5.apps.dte.destination-earth.eu
DESTINE_HISTORICAL_POLYTOPE_ADDRESS = "polytope.lumi.apps.dte.destination-earth.eu"

# GRIB parameter IDs for the DestinE Climate DT historical simulation
DESTINE_HISTORICAL_PARAMS = ["167", "228", "169"]  # t2m, tp (total precip), ssrd

PROPERTY_VARS = [
    "timezone",
    "name",
    "country",
    "lat",
    "lon",
    "area",
    "p_mean",
    "pet_mean",
    "aridity",
    "frac_snow",
    "moisture_index",
    "seasonality",
    "high_prec_freq",
    "high_prec_dur",
    "low_prec_freq",
    "low_prec_dur",
]

RENAME_DESTINE = {
    "tp": "pr",
    # "potential_evaporation_sum": "evspsblpot",
    "t2m": "tas",
    # "temperature_2m_min": "tasmin",
    # "temperature_2m_max": "tasmax",
    "ssrd": "rsds",
}

CORRECT_UNITS = {
    'tas': 'K', 
    'pr': 'kg m-2 s-1', 
    'rsds': 'W m-2', 
    'evspsblpot': 'kg m-2 s-1'
}

def _write_forcing_yaml(directory: str, start_time: str, end_time: str, shape, files: dict) -> None:
    """Write an ewatercycle_forcing.yaml with basenames so the directory is self-contained."""
    yaml_data = {
        "start_time": start_time,
        "end_time": end_time,
        "shape": Path(str(shape)).name,
        "filenames": {var: Path(path).name for var, path in files.items()},
    }
    with open(Path(directory) / "ewatercycle_forcing.yaml", "w") as f:
        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)


class DestinEForcing(DefaultForcing):
    """Retrieves specified part of the destinE dataset from the zarr server.

    FOR NOW: redundant, because not everything is in zarr yet

    Examples:
        The caravan dataset is an already prepared set by Frederik Kratzert,
        (see https://doi.org/10.1038/s41597-023-01975-w).

        This retrieves it from the OpenDAP server of 4TU,
        (see https://doi.org/10.4121/bf0eaf7c-f2fa-46f6-b8cd-77ad939dd350.v4).

        This can be done by specifying the

        .. code-block:: python

            from pathlib import Path
            from ewatercycle.forcing import sources

            path = Path.cwd()
            forcing_path = path / "Forcing" / "Camels"
            forcing_path.mkdir(parents=True, exist_ok=True)
            experiment_start_date = "1997-08-01T00:00:00Z"
            experiment_end_date = "2005-09-01T00:00:00Z"
            HRU_id = 1022500

            camels_forcing = sources['CaravanForcing'].generate(
                                        start_time = experiment_start_date,
                                        end_time = experiment_end_date,
                                        directory = forcing_path,
                                        basin_id = f"camels_0{HRU_id}"
                                                                    )

        which gives something like:

        .. code-block:: python

            CaravanForcing(
            start_time='1997-08-01T00:00:00Z',
            end_time='2005-09-01T00:00:00Z',
            directory=PosixPath('/home/davidhaasnoot/eWaterCycle-WSL-WIP/Forcing/Camels'),
            shape=PosixPath('/home/davidhaasnoot/eWaterCycle-WSL-WIP/Forcing/Camels/shapefiles/camels_01022500.shp'),
            filenames={
                'tasmax':
                'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_tasmax.nc',
                'tasmin':
                'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_tasmin.nc',
                'evspsblpot':
                'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_evspsblpot.nc',
                'pr': 'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_pr.nc',
                'tas': 'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_tas.nc',
                'Q': 'camels_01022500_1997-08-01T00:00:00Z_2005-09-01T00:00:00Z_Q.nc'
            }
            )


        More in depth notebook van be found here:
        https://gist.github.com/Daafip/ac1b030eb5563a76f4d02175f2716fd7
    """  # noqa: E501

    @classmethod
    def load(
        cls: type["DestinEForcing"],
        directory: str,
    ) -> "LumpedMakkinkForcing":

        directory = str(directory)

        with open(Path(directory) / "ewatercycle_forcing.yaml", "r") as f:
            config = yaml.safe_load(f)

        files = {var: str(Path(directory) / fname) for var, fname in config["filenames"].items()}

        return ewatercycle.forcing.sources["LumpedMakkinkForcing"](
            directory=directory,
            start_time=config["start_time"],
            end_time=config["end_time"],
            shape=str(Path(directory) / config["shape"]),
            filenames=files,
        )
            
    
    @classmethod
    def generate(  # type: ignore[override]
        cls: type["DestinEForcing"],
        start_time: str,
        end_time: str,
        directory: str,
        variables: tuple[str, ...] = (),
        shape: str | Path | None = None,
        **kwargs,
    ) -> "LumpedMakkinkForcing":
        """Retrieve caravan for a model.

        Args:
            start_time: Start time of forcing in UTC and ISO format string e.g.
                'YYYY-MM-DDTHH:MM:SSZ'.
            end_time: nd time of forcing in UTC and ISO format string e.g.
                'YYYY-MM-DDTHH:MM:SSZ'.
            directory: Directory in which forcing should be written.
            variables: Variables which are needed for model,
                if not specified will default to all.
            shape: (Optional) Path to a shape file.
                If none is specified, will be downloaded automatically.
            kwargs: Additional keyword arguments.
                basin_id: The ID of the desired basin. Data sets can be explored using
                `CaravanForcing.get_dataset(dataset_name)` or
                `CaravanForcing.get_basin_id(dataset_name)`
                where `dataset_name` is the name of a dataset in Caravan
                (for example, "camels" or "camelsgb").
                For more information do `help(CaravanForcing.get_basin_id)` or see
                https://www.ewatercycle.org/caravan-map/.
        """
        # authenticate_destinE()

        ds = xr.open_dataset(
            DESTINE_CLIMATE_DATA_URL,
            storage_options={"client_kwargs":{"trust_env":"true"}},
            # chunks={},
            chunks="auto",
            engine="zarr",
        )

        ds = ds[['t2m', 'tp', 'ssrd']]

        ds_time = ds.sel(time=slice(start_time[:10], end_time[:10]))

        # Getting the correct shape
        # Load shapefile
        gdf = gpd.read_file(shape)
        
        # Ensure CRS is defined (example WGS84)
        ds_time = ds_time.rio.write_crs("EPSG:4326")
        
        # Clip
        shaped_ds = ds_time.rio.clip(gdf.geometry, gdf.crs)

        # Making the data daily and lumped and renaming
        ds_daily = shaped_ds.resample(time="1D").mean()
        
        ds_lumped = ds_daily.mean(dim=["latitude", "longitude"])  # this is not correct, I am aware

        ds_lumped = ds_lumped.rename(RENAME_DESTINE)

        ds_lumped["tas"].attrs = {
            "units": CORRECT_UNITS["tas"],
            "long_name": "Air temperature at 2 m"
        }

        ds_lumped["pr"] = ds_lumped["pr"] / 3.6
        ds_lumped["pr"].attrs = {
            "units": CORRECT_UNITS["pr"],
            "long_name": "Precipitation"
        }
        
        ds_lumped["rsds"] = ds_lumped["rsds"] / 3600
        ds_lumped["rsds"].attrs = {
            "units": CORRECT_UNITS["rsds"],
            "long_name": "Surface downwelling shortwave radiation"
        }

        with ProgressBar(dt=10.0):  # update every 10 seconds
            ds_lumped = ds_lumped.compute()

        ds_lumped = cls.derive_e_pot(ds_lumped)

        if isinstance(directory, Path):
            directory = str(directory)

        start_string = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y_%m_%d")
        end_string = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y_%m_%d")
        name_string = "DestinE_future_day"
        
        files = {
            "pr": str(directory + f"/{name_string}_pr_{start_string}-{end_string}.nc"),
            "tas": str(directory + f"/{name_string}_tas_{start_string}-{end_string}.nc"),
            "rsds": str(directory + f"/{name_string}_rsds_{start_string}-{end_string}.nc"),
            "evspsblpot": str(directory + f"/{name_string}_evspsblpot_{start_string}-{end_string}.nc")
        }

        
        # Save intermediate files
        ds_lumped["pr"].to_netcdf(files["pr"])
        ds_lumped["tas"].to_netcdf(files["tas"])
        ds_lumped["rsds"].to_netcdf(files["rsds"])
        ds_lumped["evspsblpot"].to_netcdf(files["evspsblpot"])

        _write_forcing_yaml(directory, start_time, end_time, shape, files)

        # Make the forcing
        forcing_destinE = ewatercycle.forcing.sources["LumpedMakkinkForcing"](
            directory=directory,
            start_time=start_time,
            end_time=end_time,
            shape=shape,
            filenames=files,
        )

        return forcing_destinE

    # @staticmethod
    # def authenticate_destinE():
    #     token = authenticate()

    #     netrc_content = f"""machine cacheb.dcms.destine.eu
    #         login anonymous
    #         password {token}
    #     """
        
    #     with open(Path.home() / ".netrc", "a") as fp:
    #         fp.write(netrc_content)

    @staticmethod
    def derive_e_pot(ds):

        T = ds["tas"]  # temperature °K
        if T.attrs["units"] == "K":
            T = T - 273.15
            # print(f"converting temperature")
        Rs = ds["rsds"]  # radiation W m-2

        t = T
        a = 6.1078
        b = 17.294
        c = 237.74
        # saturation vapor pressure (kPa)
        es = (a * b * c) / (c + t) ** 2 * np.exp(b * t / (c + t))
        
        c1 = 0.65
        c2 = 0.0
        gamma = 0.66
        labda = 2.45e6
    
        s = es
    
        pet = (c1 * s / (s + gamma) * Rs + c2) / labda
    
        ds["evspsblpot"] = pet
        ds["evspsblpot"].attrs.update({
            "units": CORRECT_UNITS["evspsblpot"],
            "long_name": "Potential evaporation (Makkink)"
        })

        return ds


RENAME_DESTINE_HIST = {
    "t2m": "tas",
    "tp": "pr",
    "ssrd": "rsds",
}


class DestinEHistoricalForcing(DefaultForcing):
    """Retrieves DestinE Climate DT CMIP6 historical data via the polytope API.

    The historical simulation (ICON model, 1990–~2020) is not available as a zarr
    store on Cache B. Instead it is accessed via the polytope API using earthkit.data,
    which returns GRIB data on a HEALPix grid. The class regrids to a regular lat/lon
    grid, clips to the catchment, and computes potential evaporation using the same
    Makkink approach as DestinEForcing.

    Authentication uses the same DESP credentials as DestinEForcing (via dest_auth).
    Polytope auth is handled by earthkit using the DESP_USERNAME / DESP_PASSWORD
    environment variables, or a previously written ~/.netrc entry.

    Requirements:
        pip install earthkit-data earthkit-regrid

    Note:
        Unit conversions for tp (total precipitation) and ssrd (surface solar radiation
        downwards) assume the GRIB fields contain hourly accumulated values (m and J/m²
        respectively). Verify against actual data if results look off.
    """

    @classmethod
    def load(
        cls: type["DestinEForcing"],
        directory: str,
    ) -> "LumpedMakkinkForcing":
    
        directory = str(directory)

        with open(Path(directory) / "ewatercycle_forcing.yaml", "r") as f:
            config = yaml.safe_load(f)

        files = {var: str(Path(directory) / fname) for var, fname in config["filenames"].items()}

        return ewatercycle.forcing.sources["LumpedMakkinkForcing"](
            directory=directory,
            start_time=config["start_time"],
            end_time=config["end_time"],
            shape=str(Path(directory) / config["shape"]),
            filenames=files,
        )


    @classmethod
    def generate(
            cls: type["DestinEForcing"],
            start_time: str,
            end_time: str,
            directory: str,
            variables: tuple[str, ...] = (),
            shape: str | Path | None = None,
            polytope_address: str = DESTINE_HISTORICAL_POLYTOPE_ADDRESS,
            **kwargs,
        ):
    
        time_windows = cls.generate_time_windows(start_time, end_time)
        ds_chunks = []
    
        gdf = gpd.read_file(shape)
        centroid = gdf.geometry.centroid.union_all().centroid
        lat, lon = centroid.y, centroid.x
    
        points_list = [[pt.y, pt.x] for pt in gdf.geometry.representative_point()]
    
        gdf = gdf.to_crs("EPSG:4326")
        
        polygon = gdf.geometry.union_all()
        coords = list(polygon.exterior.coords)
        polygon_points = [[lat, lon] for lon, lat in coords]
    
        for window_number in range(len(time_windows)):
    
            print(f"Data is split up in parts\nRunning {window_number+1} of {len(time_windows)}")
            start = time_windows[window_number][0]
            print(f"{start = }")
            end = time_windows[window_number][1]
            print(f"{end = }")
        
            request = {
                "class": "ng",
                "activity": "CMIP6",
                "experiment": "hist",
                "expver": "0001",
                "model": "IFS-FESOM",
                "generation": "1",
                "realization": "1",
                "resolution": "high",
                "stream": "clte",
                "type": "fc",
                "levtype": "sfc",
                "param": "167/260048/169",
                "date": f"{start}/to/{end}",
                "time": "0000/0100/0200/0300/0400/0500/0600/0700/0800/0900/1000/1100/1200/1300/1400/1500/1600/1700/1800/1900/2000/2100/2200/2300",
                "feature": {
                    "type": "polygon",
                    "shape": polygon_points,
                }
            }
        
            LIVE_REQUEST = os.getenv("LIVE_REQUEST", "true").lower() == "true"
    
            if LIVE_REQUEST:
                data = earthkit.data.from_source("polytope", "destination-earth", request, address=polytope_address, stream=False)
        
            ds = data.to_xarray()
            ds = ds.rename({
                "2t": "tas",
                "ssrd": "rsds",
                "tprate": "pr"
            })
    
            # # DIAGNOSTIC 1: Raw data
            # print(f"=== RAW DATA ===")
            # print(f"Dimensions: {ds.dims}")
            # print(f"pr mean: {ds['pr'].mean().values:.2e}")
            # print(f"pr max:  {ds['pr'].max().values:.2e}")
            
            # 1. Convert string datetimes to proper datetime64
            ds['datetimes'] = pd.to_datetime(ds['datetimes'].values)
            
            # 2. Rename to 'time'
            ds = ds.rename({'datetimes': 'time'})
            
            # 3. Squeeze out singleton dimensions
            ds = ds.squeeze(dim=['number', 'steps'], drop=True)
            
            # # DIAGNOSTIC 2: After squeeze
            # print(f"=== AFTER SQUEEZE ===")
            # print(f"Dimensions: {ds.dims}")
            # print(f"pr mean: {ds['pr'].mean().values:.2e}")
            # print(f"pr max:  {ds['pr'].max().values:.2e}")
            
            # 4. Daily aggregation
            ds_daily = xr.Dataset()
            ds_daily['tas'] = ds['tas'].resample(time='1D').mean()
            ds_daily['pr'] = ds['pr'].resample(time='1D').mean()
            ds_daily['rsds'] = ds['rsds'].resample(time='1D').mean()
            
            # # DIAGNOSTIC 3: After daily aggregation
            # print(f"=== AFTER DAILY AGG ===")
            # print(f"Dimensions: {ds_daily.dims}")
            # print(f"pr mean: {ds_daily['pr'].mean().values:.2e}")
            # print(f"pr max:  {ds_daily['pr'].max().values:.2e}")
            
            # 5. Spatial averaging over 'points' dimension
            ds_lumped = ds_daily.mean(dim='points')
            
            # # DIAGNOSTIC 4: After spatial averaging
            # print(f"=== AFTER SPATIAL AVG ===")
            # print(f"Dimensions: {ds_lumped.dims}")
            # print(f"pr mean: {ds_lumped['pr'].mean().values:.2e}")
            # print(f"pr max:  {ds_lumped['pr'].max().values:.2e}")
    
            ds_chunks.append(ds_lumped)
    
        print("Concatenating all windows...")
        ds_total = xr.concat(ds_chunks, dim='time')
        ds_total = ds_total.sortby('time')
    
        # # DIAGNOSTIC 5: After concat
        # print(f"=== AFTER CONCAT ===")
        # print(f"pr mean: {ds_total['pr'].mean().values:.2e}")
        # print(f"pr max:  {ds_total['pr'].max().values:.2e}")
    
        # Set attributes (no conversion needed for pr - already in kg m-2 s-1)
        ds_total["tas"].attrs = {"units": CORRECT_UNITS["tas"], "long_name": "Air temperature at 2 m"}
        ds_total["pr"].attrs = {"units": CORRECT_UNITS["pr"], "long_name": "Precipitation"}
    
        # ssrd: accumulated J/m²/hr → W m-2
        ds_total["rsds"] = ds_total["rsds"] / 3600 
        ds_total["rsds"].attrs = {"units": CORRECT_UNITS["rsds"], "long_name": "Surface downwelling shortwave radiation"}
    
        with ProgressBar(dt=10.0):
            ds_total = ds_total.compute()
    
        ds_total = cls.derive_e_pot(ds_total)
        ds_total["time"] = pd.to_datetime(ds_total["time"].values).tz_localize(None)
        
        if isinstance(directory, Path):
            directory = str(directory)
    
        start_string = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y_%m_%d")
        end_string = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y_%m_%d")
        name_string = "DestinE_historic_day"
        
        files = {
            "pr": str(directory + f"/{name_string}_pr_{start_string}-{end_string}.nc"),
            "tas": str(directory + f"/{name_string}_tas_{start_string}-{end_string}.nc"),
            "rsds": str(directory + f"/{name_string}_rsds_{start_string}-{end_string}.nc"),
            "evspsblpot": str(directory + f"/{name_string}_evspsblpot_{start_string}-{end_string}.nc")
        }
    
        ds_total["pr"].to_netcdf(files["pr"])
        ds_total["tas"].to_netcdf(files["tas"])
        ds_total["rsds"].to_netcdf(files["rsds"])
        ds_total["evspsblpot"].to_netcdf(files["evspsblpot"])
    
        _write_forcing_yaml(directory, start_time, end_time, shape, files)

        forcing_destinE = ewatercycle.forcing.sources["LumpedMakkinkForcing"](
            directory=directory,
            start_time=start_time,
            end_time=end_time,
            shape=shape,
            filenames=files,
        )

        return forcing_destinE

    @staticmethod
    def derive_e_pot(ds):
        return DestinEForcing.derive_e_pot(ds)

    @staticmethod
    def generate_time_windows(start_date, end_date, window_years=5):
        start = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ")
    
        windows = []
        current_start = start
    
        while current_start <= end:
            end_year = current_start.year + window_years - 1
            current_end = current_start.replace(year=end_year, month=12, day=31)
    
            if current_end > end:
                current_end = end
    
            windows.append((
                current_start.strftime("%Y%m%d"),
                current_end.strftime("%Y%m%d")
            ))
    
            # next window
            current_start = current_end.replace(
                year=current_end.year + 1, month=1, day=1
            )
    
        return windows


class DestinEFutureForcing(DefaultForcing):
    """Retrieves DestinE Climate DT future scenario data via the polytope API.

    The future projection (IFS-FESOM model, SSP3-7.0 scenario) is accessed via the
    polytope API using earthkit.data, which returns GRIB data on an unstructured grid.
    The class performs spatial averaging over the catchment polygon and daily
    aggregation, then computes potential evaporation using the same Makkink approach
    as DestinEForcing.

    Authentication uses the same DESP credentials as DestinEForcing. Polytope auth is
    handled by earthkit using the DESP_USERNAME / DESP_PASSWORD environment variables,
    or a previously written ~/.netrc entry.

    Requirements:
        pip install earthkit-data earthkit-regrid

    Note:
        ssrd (surface solar radiation downwards) is converted from hourly accumulated
        J/m² to W/m² by dividing by 3600. Precipitation (tprate) is already in
        kg m⁻² s⁻¹ and requires no conversion. Verify against actual data if results
        look off.
    """

    @classmethod
    def load(
            cls: type["DestinEForcing"],
            directory: str,
    ) -> "LumpedMakkinkForcing":
        """Load previously generated future forcing from a directory.

        Reads the ewatercycle_forcing.yaml written by generate() to reconstruct
        the start/end times, shapefile, and file paths, then returns a
        LumpedMakkinkForcing instance pointing to the saved NetCDF files.

        Args:
            directory: Path to the directory containing ewatercycle_forcing.yaml
                and the NetCDF files produced by generate().

        Returns:
            A LumpedMakkinkForcing instance configured with the saved forcing files.
        """
        directory = str(directory)

        with open(Path(directory) / "ewatercycle_forcing.yaml", "r") as f:
            config = yaml.safe_load(f)

        files = {var: str(Path(directory) / fname) for var, fname in config["filenames"].items()}

        return ewatercycle.forcing.sources["LumpedMakkinkForcing"](
            directory=directory,
            start_time=config["start_time"],
            end_time=config["end_time"],
            shape=str(Path(directory) / config["shape"]),
            filenames=files,
        )

    @classmethod
    def generate(
            cls: type["DestinEForcing"],
            start_time: str,
            end_time: str,
            directory: str,
            variables: tuple[str, ...] = (),
            shape: str | Path | None = None,
            polytope_address: str = DESTINE_HISTORICAL_POLYTOPE_ADDRESS,
            **kwargs,
    ):
        """Download and process future scenario forcing data from the polytope API.

        Splits the requested period into 5-year windows and fetches hourly GRIB data
        for 2m temperature (167), precipitation rate (260048), and surface solar
        radiation downwards (169) from the IFS-FESOM SSP3-7.0 run. Data are spatially
        averaged over the catchment polygon, aggregated to daily means, unit-converted,
        and written to NetCDF files. Potential evaporation is computed via Makkink.

        Args:
            start_time: ISO 8601 start datetime string, e.g. "2020-01-01T00:00:00Z".
            end_time: ISO 8601 end datetime string, e.g. "2030-12-31T00:00:00Z".
            directory: Output directory for NetCDF files and ewatercycle_forcing.yaml.
            variables: Unused; kept for interface compatibility.
            shape: Path to the catchment shapefile used to define the polygon query.
            polytope_address: URL of the polytope server. Defaults to
                DESTINE_HISTORICAL_POLYTOPE_ADDRESS.
            **kwargs: Unused; kept for interface compatibility.

        Returns:
            A LumpedMakkinkForcing instance pointing to the saved NetCDF files.
        """
        time_windows = cls.generate_time_windows(start_time, end_time)
        ds_chunks = []

        gdf = gpd.read_file(shape)
        centroid = gdf.geometry.centroid.union_all().centroid
        lat, lon = centroid.y, centroid.x

        points_list = [[pt.y, pt.x] for pt in gdf.geometry.representative_point()]

        gdf = gdf.to_crs("EPSG:4326")

        polygon = gdf.geometry.union_all()
        coords = list(polygon.exterior.coords)
        polygon_points = [[lat, lon] for lon, lat in coords]

        for window_number in range(len(time_windows)):

            print(f"Data is split up in parts\nRunning {window_number + 1} of {len(time_windows)}")
            start = time_windows[window_number][0]
            print(f"{start = }")
            end = time_windows[window_number][1]
            print(f"{end = }")

            # https://confluence.ecmwf.int/display/DDCZ/NextGEMS+data+catalogue
            request = {
                "class": "d1",
                "activity": "ScenarioMIP",
                "experiment": "SSP3-7.0",
                "expver": "0001",
                "model": "IFS-FESOM",
                "generation": "1",
                "realization": "2",
                "resolution": "high",
                "stream": "clte",
                "type": "fc",
                "levtype": "sfc",
                "param": "167/260048/169",
                "date": f"{start}/to/{end}",
                "time": "0000/0100/0200/0300/0400/0500/0600/0700/0800/0900/1000/1100/1200/1300/1400/1500/1600/1700/1800/1900/2000/2100/2200/2300",
                "feature": {
                    "type": "polygon",
                    "shape": polygon_points,
                }
            }

            LIVE_REQUEST = os.getenv("LIVE_REQUEST", "true").lower() == "true"

            if LIVE_REQUEST:
                data = earthkit.data.from_source("polytope", "destination-earth", request, address=polytope_address,
                                                 stream=False)

            ds = data.to_xarray()
            ds = ds.rename({
                "2t": "tas",
                "ssrd": "rsds",
                "tprate": "pr"
            })

            # 1. Convert string datetimes to proper datetime64
            ds['datetimes'] = pd.to_datetime(ds['datetimes'].values)

            # 2. Rename to 'time'
            ds = ds.rename({'datetimes': 'time'})

            # 3. Squeeze out singleton dimensions
            ds = ds.squeeze(dim=['number', 'steps'], drop=True)

            # 4. Daily aggregation
            ds_daily = xr.Dataset()
            ds_daily['tas'] = ds['tas'].resample(time='1D').mean()
            ds_daily['pr'] = ds['pr'].resample(time='1D').mean()
            ds_daily['rsds'] = ds['rsds'].resample(time='1D').mean()

            # 5. Spatial averaging over 'points' dimension
            ds_lumped = ds_daily.mean(dim='points')

            ds_chunks.append(ds_lumped)

        print("Concatenating all windows...")
        ds_total = xr.concat(ds_chunks, dim='time')
        ds_total = ds_total.sortby('time')

        # Set attributes (no conversion needed for pr - already in kg m-2 s-1)
        ds_total["tas"].attrs = {"units": CORRECT_UNITS["tas"], "long_name": "Air temperature at 2 m"}
        ds_total["pr"].attrs = {"units": CORRECT_UNITS["pr"], "long_name": "Precipitation"}

        # ssrd: accumulated J/m²/hr → W m-2
        ds_total["rsds"] = ds_total["rsds"] / 3600
        ds_total["rsds"].attrs = {"units": CORRECT_UNITS["rsds"],
                                  "long_name": "Surface downwelling shortwave radiation"}

        with ProgressBar(dt=10.0):
            ds_total = ds_total.compute()

        ds_total = cls.derive_e_pot(ds_total)
        ds_total["time"] = pd.to_datetime(ds_total["time"].values).tz_localize(None)

        if isinstance(directory, Path):
            directory = str(directory)

        start_string = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y_%m_%d")
        end_string = datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y_%m_%d")
        name_string = "DestinE_future_day"

        files = {
            "pr": str(directory + f"/{name_string}_pr_{start_string}-{end_string}.nc"),
            "tas": str(directory + f"/{name_string}_tas_{start_string}-{end_string}.nc"),
            "rsds": str(directory + f"/{name_string}_rsds_{start_string}-{end_string}.nc"),
            "evspsblpot": str(directory + f"/{name_string}_evspsblpot_{start_string}-{end_string}.nc")
        }

        ds_total["pr"].to_netcdf(files["pr"])
        ds_total["tas"].to_netcdf(files["tas"])
        ds_total["rsds"].to_netcdf(files["rsds"])
        ds_total["evspsblpot"].to_netcdf(files["evspsblpot"])

        _write_forcing_yaml(directory, start_time, end_time, shape, files)

        forcing_destinE = ewatercycle.forcing.sources["LumpedMakkinkForcing"](
            directory=directory,
            start_time=start_time,
            end_time=end_time,
            shape=shape,
            filenames=files,
        )

        return forcing_destinE

    @staticmethod
    def derive_e_pot(ds):
        """Compute potential evaporation using the Makkink method.

        Delegates to DestinEForcing.derive_e_pot. See that method for details.
        """
        return DestinEForcing.derive_e_pot(ds)

    @staticmethod
    def generate_time_windows(start_date, end_date, window_years=5):
        """Split a date range into consecutive windows of up to window_years years.

        Delegates to DestinEHistoricalForcing.generate_time_windows. See that method
        for details.
        """
        return DestinEHistoricalForcing.generate_time_windows(start_date, end_date, window_years)