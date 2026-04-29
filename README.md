# Climate Change Impact Analysis using eWaterCycle

This repository contains a workflow for assessing the impact of climate change on river discharge. It is built on top of [eWaterCycle](https://www.ewatercycle.org/), a platform for reproducible hydrological modelling, and serves as an example of a seamless eWaterCycle application: a workflow that can run at a single catchment during development and then scale to many catchments on HPC infrastructure without modification.

The workflow uses the [HBV](https://doi.org/10.1002/hyp.3360050103) and LeakyBucket conceptual hydrological models and [Caravan](https://doi.org/10.1038/s41597-023-01975-w) catchment data, driven by ERA5 reanalysis, CMIP6 & DestinE climate projections.

## What it does

For a given catchment, the workflow:

1. Downloads observational discharge data and a catchment shapefile from Caravan
2. Queries available CMIP6 climate model data from ESGF
3. Generates historical and future meteorological forcing from ERA5, CMIP6, and Destination Earth
4. Calibrates the HBV model against observed discharge using Shuffled Complex Evolution
5. Bias-corrects CMIP6 and DestinE forcing against ERA5
6. Calibrates a LeakyBucket model as a lightweight second model
7. Runs both models with historical and future forcing across multiple climate scenarios
8. Analyses changes in discharge extremes using cumulative distributions and return period plots
9. Classifies the catchment by Köppen-Geiger climate zone

The result is a comparison of discharge behaviour under historical conditions (CMIP & DestinE Historic) versus four future climate scenarios (SSP1-2.6, SSP2-4.5, SSP3-7.0, SSP5-8.5), based on one or more CMIP6 models and ensemble members. For SSP3-7.0, high-resolution Destination Earth data is used for future projections.

## Workflow overview

The notebooks are numbered and should be run in order:

| Notebook | Description |
|---|---|
| `step_0a` | Select catchment, time periods, and CMIP6 model; save settings |
| `step_0b` | Query ESGF to confirm which ensemble members are available (optional) |
| `step_1a` | Generate historical forcing (ERA5 + CMIP6 historical) |
| `step_1b` | Generate future forcing (CMIP6 SSP scenarios + DestinE SSP3-7.0) |
| `step_2a` | Calibrate HBV model parameters using Shuffled Complex Evolution |
| `step_2b` | Bias-correct CMIP6 and DestinE forcing against ERA5 |
| `step_2c` | Calibrate LeakyBucket model using bounded optimisation |
| `step_3a` | Run HBV with historical forcing; compare against observations |
| `step_3b` | Run HBV with future forcing across all scenarios |
| `step_4` | Analyse discharge changes using CDFs and return period plots |
| `step_5` | Classify catchment by Köppen-Geiger climate zone |

All settings are stored in `settings.json` after `step_0a` and shared across all subsequent notebooks. This makes the workflow easy to reconfigure for a different catchment.

## Running at scale

The workflow is designed to run seamlessly for a single catchment during development and for many catchments in parallel on HPC. The script `climatechangeimpact/scripts/cci.py` executes the full notebook sequence for a given catchment using [papermill](https://papermill.readthedocs.io/), skipping regions that have already been completed.

To submit jobs for all regions on Spider HPC:

```bash
cd climatechangeimpact
. scripts/submit_cci.sh
```

This iterates over all subdirectories in `regions/` and submits a SLURM job per catchment via `scripts/run_cci.slurm`. Each job runs `scripts/cci.py` with the region ID and country derived from the folder structure. Use `submit_smart_cci.sh` to skip catchments that are already recorded as done.

`step_0b` is skipped in automated HPC runs — ensemble members are assumed to be pre-selected. It can be run manually to verify availability before a large batch.

## Getting started (single catchment)

1. Open `step_0a` and set your catchment ID and time periods. Catchment IDs can be found using the [eWaterCycle Caravan map](https://www.ewatercycle.org/caravan-map/).
2. Run `step_0a`, then `step_1a` through `step_5` in order (skip `step_0b` unless you need to check ESGF availability).
3. Examine the output plots in `step_4` to assess climate change impacts for your catchment.

## Data sources

| Data | Purpose | Access |
|---|---|---|
| [Caravan](https://doi.org/10.1038/s41597-023-01975-w) | Observed discharge + catchment shapefile | Via eWaterCycle |
| [ERA5](https://doi.org/10.24381/cds.adbb2d47) | Historical meteorological forcing | Must be available on the system |
| [CMIP6 via ESGF](https://esgf-node.llnl.gov/) | Climate model projections | Queried automatically |
| [Destination Earth](https://destination-earth.eu/) | High-resolution future forcing (optional) | Requires DestinE credentials |

ERA5 data is expected to be pre-downloaded on the system. On the eWaterCycle Research Cloud (SRC) this is handled by the platform. On Spider HPC it is available under `/data/shared/climate-data/`.

## Dependencies

This workflow runs inside the eWaterCycle environment. The main dependencies are:

- [eWaterCycle](https://ewatercycle.readthedocs.io/)
- [ESMValTool](https://www.esmvaltool.org/) (used internally by eWaterCycle for CMIP6 forcing)
- [papermill](https://papermill.readthedocs.io/) (for running notebooks programmatically)
- [sceua](https://pypi.org/project/sceua/) (for HBV calibration — note: requires numpy >= 2, which conflicts with ESMValTool; install separately if needed)
- [cmethods](https://pypi.org/project/cmethods/) (for bias correction of CMIP6/DestinE forcing)
- [hydrobm](https://pypi.org/project/hydrobm/) (for KGE/NSE metrics used in calibration)

## Repository structure

```
climatechangeimpact/
    notebooks/          # Main workflow notebooks (step_0a through step_5)
    scripts/
        cci.py                  # Runs full workflow for one catchment via papermill
        cara.py                 # CaravanForcing class for eWaterCycle
        forcing_destine.py      # DestinE forcing support
        dest_auth.py            # DestinE authentication
        leakybucket_model.py    # eWaterCycle BMI wrapper for the LeakyBucket model
        koppen_geiger.py        # Köppen-Geiger climate classification utilities
        run_cci.slurm           # SLURM job script for Spider HPC
        submit_cci.sh           # Batch job submission script
        submit_smart_cci.sh     # Smart submission (skips already-completed catchments)
        cancel_jobs.sh          # Cancel running SLURM jobs
        remove_done_files.sh    # Remove completed-job artefacts
        all_regions.csv         # List of all catchment regions to process
    regions/                    # Executed notebooks and settings per catchment (by country)
    koppen_geiger_results.ipynb             # Multi-catchment Köppen-Geiger results
    koppen_geiger_results_interactive.ipynb # Interactive Köppen-Geiger results
    preliminary_results.ipynb               # Aggregated results across catchments
    preprocess_results.py                   # Aggregates per-catchment results.json files
    generate_interactive_map.ipynb          # Interactive map of available Caravan catchments
    generate_json_region_structure.ipynb    # Prepares directory structure for HPC runs
managing_seamless_spider.ipynb  # Job monitoring and management for Spider HPC
```

## License

See [LICENSE](LICENSE).