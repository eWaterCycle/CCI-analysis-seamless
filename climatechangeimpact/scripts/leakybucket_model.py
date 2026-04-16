"""eWaterCycle wrapper for the Leaky Bucket model."""
import json
from collections.abc import ItemsView
from pathlib import Path
from typing import Any, Type

import numpy as np

from ewatercycle.base.model import LocalModel, eWaterCycleModel
from ewatercycle.forcing import LumpedMakkinkForcing, CaravanForcing
from bmipy import Bmi


def import_bmi() -> Type[Bmi]:
    """Return LeakyBucketBmi, or a stub that raises a clear error on instantiation.

    The stub approach lets the module import cleanly even when leakybucket-bmi is
    not installed — the error is only raised when the model is actually used.
    """
    try:
        from leakybucket.leakybucket_bmi import LeakyBucketBmi
        return LeakyBucketBmi
    except ModuleNotFoundError:
        class _MissingLeakyBucketBmi:
            def __init__(self, *args, **kwargs):
                raise ModuleNotFoundError(
                    "leakybucket-bmi package not found. "
                    "Install it with: pip install leakybucket-bmi"
                )
        return _MissingLeakyBucketBmi


LEAKYBUCKET_PARAMS = ("leakiness",)
LEAKYBUCKET_STATES = ("storage",)


class LeakyBucketMethods(eWaterCycleModel):
    """Shared logic for the Leaky Bucket eWaterCycle model.

    The Leaky Bucket is a minimal single-parameter rainfall-runoff model.
    At each timestep, precipitation fills a bucket and discharge leaks out
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
    """The Leaky Bucket eWaterCycle model using a local BMI.

    Example usage
    -------------
    >>> from scripts.leakybucket_model import LeakyBucketLocal
    >>> model = LeakyBucketLocal(forcing=my_forcing)
    >>> cfg_file, cfg_dir = model.setup(leakiness=0.5)
    >>> model.initialize(cfg_file)
    >>> for _ in range(model.end_time_as_isostr):
    ...     model.update()
    ...     discharge = model.get_value("discharge")
    >>> model.finalize()
    """

    bmi_class: Type[Bmi] = import_bmi()
