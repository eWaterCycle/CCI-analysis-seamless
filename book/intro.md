# Climate Change Impact Analysis using eWaterCycle

This book presents a workflow for assessing the impact of climate change on river discharge. It is built on top of [eWaterCycle](https://www.ewatercycle.org/), a platform for reproducible hydrological modelling, and demonstrates a seamless eWaterCycle application: a workflow that runs at a single catchment during development and scales to many catchments on HPC infrastructure without modification.

The workflow uses the [HBV](https://doi.org/10.1002/hyp.10510) and LeakyBucket conceptual hydrological models and [Caravan](https://doi.org/10.1038/s41597-023-01975-w) catchment data, driven by ERA5 reanalysis, CMIP6 & DestinE climate projections.

Results in an [interactive map](https://www.ewatercycle.org/CCI-analysis-seamless/caravan_catchments_KG_map_world.html).

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

The result is a comparison of discharge behaviour under historical conditions (CMIP & DestinE Historic) versus four future climate scenarios (SSP1-2.6, SSP2-4.5, SSP3-7.0, SSP5-8.5). For SSP3-7.0, high-resolution Destination Earth data is used for future projections.

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

All settings are stored in `settings.json` after `step_0a` and shared across all subsequent notebooks.

## This book

Use the sidebar to navigate:

- **Results** — Multi-catchment Köppen-Geiger analysis across all processed regions
- **Interactive Results** — Explore discharge projections interactively
- **The Workflow** — Step-by-step notebooks that make up the full analysis pipeline
- **Regions** — Per-catchment executed notebooks and outputs

The source code and instructions for running the workflow yourself are available on [GitHub](https://github.com/eWaterCycle/CCI-analysis-seamless).
