"""eWaterCycle wrapper for the Leaky Bucket model.

The BMI is implemented directly here — no external leakybucket-bmi package needed.
Only dependencies are bmipy, numpy, xarray, and pandas, all present in eWaterCycle.
"""
import json
from collections.abc import ItemsView
from pathlib import Path
from typing import Any, Type

import numpy as np
import pandas as pd
import xarray as xr
from bmipy import Bmi

from ewatercycle.base.model import LocalModel, eWaterCycleModel
from ewatercycle.forcing import LumpedMakkinkForcing, CaravanForcing


# ── Self-contained BMI ────────────────────────────────────────────────────────

class LeakyBucketBmi(Bmi):
    """BMI implementation of the Leaky Bucket rainfall-runoff model.

    At each timestep precipitation fills the bucket and a fraction leaks out:

        Q  = leakiness × S          [m d⁻¹]
        dS = P·dt − Q·dt            [m]

    where S is storage [m] and leakiness is in [d⁻¹].

    Config file (JSON):
        precipitation_file : path to a NetCDF with a daily 'pr' variable [kg m⁻² s⁻¹]
        leakiness          : leakiness coefficient [d⁻¹]
        initial_storage    : starting storage [m], default 0
    """

    def initialize(self, config_file: str) -> None:
        with open(config_file) as f:
            config = json.load(f)

        ds = xr.open_dataset(config["precipitation_file"])
        self._pr = ds["pr"]
        self._time_data = self._pr["time"]

        # Timestep size in seconds
        self._dt = float(
            (self._time_data.values[1] - self._time_data.values[0])
            / np.timedelta64(1, "s")
        )
        self._current_step = 0
        self._end_step = self._time_data.size

        self._storage = float(config.get("initial_storage", 0.0))
        self._discharge = 0.0
        self._leakiness = float(config["leakiness"])

    def update(self) -> None:
        if self._current_step < self._end_step:
            pr = float(self._pr.isel(time=self._current_step).to_numpy())
            # Add precipitation [kg m⁻² s⁻¹ → m] over the timestep
            self._storage += pr * self._dt
            # Discharge [m d⁻¹] leaks proportional to storage
            self._discharge = self._storage * self._leakiness
            # Remove discharge from storage (convert m d⁻¹ → m per timestep)
            self._storage -= self._discharge * (self._dt / 86400.0)
            self._current_step += 1

    def update_until(self, time: float) -> None:
        while self.get_current_time() < time:
            self.update()

    def finalize(self) -> None:
        pass

    # ── Info ──────────────────────────────────────────────────────────────────

    def get_component_name(self) -> str:
        return "leakybucket"

    def get_input_item_count(self) -> int:
        return 0

    def get_output_item_count(self) -> int:
        return 2

    def get_input_var_names(self):
        return ()

    def get_output_var_names(self):
        return ("storage", "discharge")

    # ── Variable metadata ─────────────────────────────────────────────────────

    def get_var_grid(self, name: str) -> int:
        return 0

    def get_var_type(self, name: str) -> str:
        return "float64"

    def get_var_units(self, name: str) -> str:
        if name == "storage":
            return "m"
        if name == "discharge":
            return "m d-1"
        raise ValueError(f"Unknown variable: {name}")

    def get_var_itemsize(self, name: str) -> int:
        return 8

    def get_var_nbytes(self, name: str) -> int:
        return 8

    def get_var_location(self, name: str) -> str:
        return "node"

    # ── Time ──────────────────────────────────────────────────────────────────

    def get_start_time(self) -> float:
        return 0.0

    def get_current_time(self) -> float:
        return self._current_step * self._dt

    def get_end_time(self) -> float:
        return self._end_step * self._dt

    def get_time_step(self) -> float:
        return self._dt

    def get_time_units(self) -> str:
        t0 = pd.Timestamp(self._time_data.values[0])
        return f"seconds since {t0.strftime('%Y-%m-%d %H:%M:%S')}"

    # ── Values ────────────────────────────────────────────────────────────────

    def get_value(self, name: str, dest: np.ndarray) -> np.ndarray:
        if name == "storage":
            dest[:] = self._storage
        elif name == "discharge":
            # Convert from [m d⁻¹ · dt/86400] back to [m d⁻¹]
            dest[:] = self._discharge
        else:
            raise ValueError(f"Unknown variable: {name}")
        return dest

    def get_value_ptr(self, name: str):
        raise NotImplementedError

    def get_value_at_indices(self, name: str, dest: np.ndarray, inds: np.ndarray) -> np.ndarray:
        return self.get_value(name, dest)

    def set_value(self, name: str, src: np.ndarray) -> None:
        if name == "storage":
            self._storage = float(src[0])
        else:
            raise ValueError(f"Cannot set variable: {name}")

    def set_value_at_indices(self, name: str, inds: np.ndarray, src: np.ndarray) -> None:
        self.set_value(name, src)

    # ── Grid ──────────────────────────────────────────────────────────────────

    def get_grid_rank(self, grid: int) -> int:
        return 1

    def get_grid_size(self, grid: int) -> int:
        return 1

    def get_grid_type(self, grid: int) -> str:
        return "scalar"

    def get_grid_shape(self, grid: int, shape: np.ndarray) -> np.ndarray:
        shape[:] = [1]
        return shape

    def get_grid_node_count(self, grid: int) -> int:
        return 1

    # Remaining grid methods are unused for a lumped scalar model
    def get_grid_spacing(self, grid, spacing): raise NotImplementedError
    def get_grid_origin(self, grid, origin): raise NotImplementedError
    def get_grid_x(self, grid, x): raise NotImplementedError
    def get_grid_y(self, grid, y): raise NotImplementedError
    def get_grid_z(self, grid, z): raise NotImplementedError
    def get_grid_edge_count(self, grid): raise NotImplementedError
    def get_grid_face_count(self, grid): raise NotImplementedError
    def get_grid_edge_nodes(self, grid, edge_nodes): raise NotImplementedError
    def get_grid_face_edges(self, grid, face_edges): raise NotImplementedError
    def get_grid_face_nodes(self, grid, face_nodes): raise NotImplementedError
    def get_grid_nodes_per_face(self, grid, nodes_per_face): raise NotImplementedError


# ── eWaterCycle wrapper ───────────────────────────────────────────────────────

LEAKYBUCKET_PARAMS = ("leakiness", "initial_storage")
LEAKYBUCKET_STATES = ("storage",)


class LeakyBucketMethods(eWaterCycleModel):
    """Shared logic for the Leaky Bucket eWaterCycle model.

    The Leaky Bucket is a minimal single-parameter rainfall-runoff model.
    At each timestep precipitation fills a bucket and discharge leaks out
    proportional to the current storage:

        Q = leakiness × S

    where leakiness is in [d⁻¹] and storage S is in [m].

    Parameters
    ----------
    leakiness : float
        Fraction of storage released as discharge per day [d⁻¹].
    initial_storage : float, optional
        Initial water storage in the bucket [m]. Defaults to 0.
    """

    forcing: LumpedMakkinkForcing | CaravanForcing
    parameter_set: None  # No parameter set files needed.

    _config: dict = {
        "precipitation_file": "",
        "leakiness": 0.5,
        "initial_storage": 0.0,
    }

    def _make_cfg_file(self, **kwargs) -> Path:
        """Write the model configuration file.

        Args:
            leakiness: Leakiness parameter [d⁻¹]. Required.
            initial_storage: Initial bucket storage [m]. Defaults to 0.

        Returns:
            Path to the written JSON config file.
        """
        if "leakiness" not in kwargs:
            raise ValueError(
                "The model requires the 'leakiness' parameter [d⁻¹]. "
                "Pass it as: model.setup(leakiness=0.5)"
            )

        self._config["leakiness"] = float(kwargs["leakiness"])
        self._config["initial_storage"] = float(kwargs.get("initial_storage", 0.0))
        self._config["precipitation_file"] = str(
            self.forcing.directory / self.forcing["pr"]
        )

        config_file = self._cfg_dir / "leakybucket_config.json"
        with config_file.open(mode="w") as f:
            f.write(json.dumps(self._config, indent=4))

        return config_file

    def initialize(self, config_file: str) -> None:
        """Initialize the BMI and apply the initial storage value."""
        super().initialize(config_file)
        self._bmi.set_value("storage", np.array([self._config["initial_storage"]]))

    @property
    def parameters(self) -> ItemsView[str, Any]:
        """Exposed Leaky Bucket parameters.

        leakiness (d⁻¹): fraction of bucket storage released as discharge each day.
        initial_storage (m): water depth in the bucket at t=0.
        """
        return {
            "leakiness":       self._config["leakiness"],
            "initial_storage": self._config["initial_storage"],
        }.items()

    @property
    def states(self) -> ItemsView[str, Any]:
        """Exposed Leaky Bucket states.

        storage (m): current water depth stored in the bucket.
        """
        storage = self._bmi.get_value("storage", dest=np.zeros(1))[0]
        return {"storage": float(storage)}.items()

    def finalize(self) -> None:
        """Tear down the model. After this the instance should not be used."""
        self._bmi.finalize()
        del self._bmi


class LeakyBucketLocal(LocalModel, LeakyBucketMethods):
    """The Leaky Bucket eWaterCycle model, running locally.

    No external BMI package required — the model logic is embedded directly.

    Example usage
    -------------
    >>> from scripts.leakybucket_model import LeakyBucketLocal
    >>> model = LeakyBucketLocal(forcing=my_forcing)
    >>> cfg_file, cfg_dir = model.setup(leakiness=0.5, initial_storage=0.0)
    >>> model.initialize(cfg_file)
    >>> while model.time < model.end_time:
    ...     model.update()
    ...     discharge = model.get_value("discharge", dest=np.zeros(1))[0]
    >>> model.finalize()
    """

    bmi_class: Type[Bmi] = LeakyBucketBmi
