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

class DestinEForcing(DefaultForcing):
    """Retrieves specified part of the destinE dataset from the zarr server.

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

        if isinstance(directory, Path):
            directory = str(directory)
        
        other_data = str(directory + "/config.json")
        files = {
            "pr": str(directory + "/pr.nc"),
            "tas": str(directory + "/tas.nc"),
            "rsds": str(directory + "/rsds.nc"),
            "evspsblpot": str(directory + "/evspsblpot.nc")
        }
        with open(other_data, "r") as json_file:
            config_data = json.load(json_file)
            
        return ewatercycle.forcing.sources["LumpedMakkinkForcing"](
                directory=directory,
                start_time=config_data["start"],
                end_time=config_data["end"],
                shape=config_data["shape"],
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
        
        files = {
            "pr": str(directory + "/pr.nc"),
            "tas": str(directory + "/tas.nc"),
            "rsds": str(directory + "/rsds.nc"),
            "evspsblpot": str(directory + "/evspsblpot.nc")
        }

        
        # Save intermediate files
        ds_lumped["pr"].to_netcdf(files["pr"])
        ds_lumped["tas"].to_netcdf(files["tas"])
        ds_lumped["rsds"].to_netcdf(files["rsds"])
        ds_lumped["evspsblpot"].to_netcdf(files["evspsblpot"])

        config_file_path = str(directory + "/config.json")
        config_file = dict()
        config_file["start"] = str(start_time)
        config_file["end"] = str(end_time)
        config_file["shape"] = str(shape)
        

        # Write to a JSON file
        with open(config_file_path, "w") as json_file:
            json.dump(config_file, json_file, indent=4)

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
        # pet.name = "evspsblpot"
        # pet.attrs = {
        #     "standard_name": "water_potential_evaporation_flux",
        #     "units": "kg m-2 s-1",
        #     "long_name": "potential evaporation",
        # }
        # # slope vapor pressure curve (kPa °C−1)
        # delta = 4098 * es / (T + 237.3) ** 2
    
        # # psychrometric constant (kPa °C−1)
        # gamma = 0.066
    
        # # latent heat of vaporization (MJ kg−1)
        # lam = 2.45
    
        # # convert radiation W/m2 -> MJ/m2/day
        # Rs_MJ = Rs * 86400 / 1e6
    
        # # Makkink PET
        # pet = 0.61 * (delta / (delta + gamma)) * (Rs_MJ / lam)
    
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
        cls: type["DestinEHistoricalForcing"],
        directory: str,
    ) -> "LumpedMakkinkForcing":
        if isinstance(directory, Path):
            directory = str(directory)

        other_data = str(directory + "/config.json")
        files = {
            "pr": str(directory + "/pr.nc"),
            "tas": str(directory + "/tas.nc"),
            "rsds": str(directory + "/rsds.nc"),
            "evspsblpot": str(directory + "/evspsblpot.nc")
        }
        with open(other_data, "r") as json_file:
            config_data = json.load(json_file)

        return ewatercycle.forcing.sources["LumpedMakkinkForcing"](
            directory=directory,
            start_time=config_data["start"],
            end_time=config_data["end"],
            shape=config_data["shape"],
            filenames=files,
        )

    @classmethod
    def generate(
        cls: type["DestinEHistoricalForcing"],
        start_time: str,
        end_time: str,
        directory: str,
        variables: tuple[str, ...] = (),
        shape: str | Path | None = None,
        polytope_address: str = DESTINE_HISTORICAL_POLYTOPE_ADDRESS,
        **kwargs,
    ) -> "LumpedMakkinkForcing":
        """Retrieve DestinE Climate DT CMIP6 historical forcing via polytope.

        Args:
            start_time: Start time in UTC ISO format string, e.g. 'YYYY-MM-DDTHH:MM:SSZ'.
            end_time: End time in UTC ISO format string, e.g. 'YYYY-MM-DDTHH:MM:SSZ'.
            directory: Directory in which forcing should be written.
            shape: Path to a shapefile of the catchment.
            polytope_address: Polytope server address. Defaults to LUMI endpoint.
                Use 'polytope.mn5.apps.dte.destination-earth.eu' for MN5.
        """
        import earthkit.data
        import earthkit.regrid

        start = pd.Timestamp(start_time[:10])
        end = pd.Timestamp(end_time[:10])

        request = {
            "class": "d1",
            "dataset": "climate-dt",
            "generation": "1",
            "expver": "0001",
            "stream": "clte",
            "type": "fc",
            "realization": "1",
            "activity": "CMIP6",
            "experiment": "hist",
            "model": "icon",
            "levtype": "sfc",
            "param": DESTINE_HISTORICAL_PARAMS,  # t2m, tp, ssrd
            "date": f"{start.strftime('%Y%m%d')}/to/{end.strftime('%Y%m%d')}",
            "time": "0000",
            "resolution": "standard",  # H128 ≈ 0.4° resolution; use "high" (H1024) if needed
        }

        fields = earthkit.data.from_source(
            "polytope",
            "destination-earth",
            request,
            address=polytope_address,
        )

        # Regrid from HEALPix to a regular 0.5° lat/lon grid so rioxarray can clip it
        fields_regular = earthkit.regrid.interpolate(fields, out_grid={"grid": [0.5, 0.5]})

        ds = fields_regular.to_xarray()

        # Clip to catchment shape
        gdf = gpd.read_file(shape)
        ds = ds.rio.write_crs("EPSG:4326")
        ds = ds.rio.clip(gdf.geometry, gdf.crs)

        # Daily mean and spatial lumping
        ds_daily = ds.resample(time="1D").mean()
        ds_lumped = ds_daily.mean(dim=["latitude", "longitude"])

        ds_lumped = ds_lumped.rename(RENAME_DESTINE_HIST)

        # Unit conversions — consistent with DestinEForcing (zarr SSP3-7.0).
        # tp: accumulated m/hr → kg m-2 s-1 (1 m/hr = 1/3.6 kg m-2 s-1)
        # TODO: verify units in actual polytope GRIB output and adjust if needed
        ds_lumped["tas"].attrs = {"units": CORRECT_UNITS["tas"], "long_name": "Air temperature at 2 m"}

        ds_lumped["pr"] = ds_lumped["pr"] / 3.6
        ds_lumped["pr"].attrs = {"units": CORRECT_UNITS["pr"], "long_name": "Precipitation"}

        # ssrd: accumulated J/m²/hr → W m-2 (divide by 3600 s)
        ds_lumped["rsds"] = ds_lumped["rsds"] / 3600
        ds_lumped["rsds"].attrs = {"units": CORRECT_UNITS["rsds"], "long_name": "Surface downwelling shortwave radiation"}

        from dask.diagnostics import ProgressBar
        with ProgressBar(dt=10.0):
            ds_lumped = ds_lumped.compute()

        ds_lumped = cls.derive_e_pot(ds_lumped)

        if isinstance(directory, Path):
            directory = str(directory)

        files = {
            "pr": str(directory + "/pr.nc"),
            "tas": str(directory + "/tas.nc"),
            "rsds": str(directory + "/rsds.nc"),
            "evspsblpot": str(directory + "/evspsblpot.nc")
        }

        ds_lumped["pr"].to_netcdf(files["pr"])
        ds_lumped["tas"].to_netcdf(files["tas"])
        ds_lumped["rsds"].to_netcdf(files["rsds"])
        ds_lumped["evspsblpot"].to_netcdf(files["evspsblpot"])

        config_file_path = str(directory + "/config.json")
        config_file = {"start": str(start_time), "end": str(end_time), "shape": str(shape)}
        with open(config_file_path, "w") as json_file:
            json.dump(config_file, json_file, indent=4)

        return ewatercycle.forcing.sources["LumpedMakkinkForcing"](
            directory=directory,
            start_time=start_time,
            end_time=end_time,
            shape=shape,
            filenames=files,
        )

    @staticmethod
    def derive_e_pot(ds):
        return DestinEForcing.derive_e_pot(ds)