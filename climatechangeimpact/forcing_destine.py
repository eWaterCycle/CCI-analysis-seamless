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
        other_data = str(directory / "config.json")
        files = {
            "pr": str(directory / "pr.nc"),
            "tas": str(directory / "tas.nc"),
            "rsds": str(directory / "rsds.nc"),
            "evspsblpot": str(directory / "evspsblpot.nc")
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

        with ProgressBar():
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

        config_file_path = str(directory / "config.json")
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