import json
import papermill as pm
import time
from pathlib import Path
import subprocess
import sys
import os
from filelock import FileLock
import csv

region_id = sys.argv[1]
country = sys.argv[2]

HOME_PATH = "/project/ewater/Data/"

# All notebooks to run
NOTEBOOKS = [
    "notebooks/step_0a_select_caravan_region_time_and_scenarios.ipynb",   # produces settings.json
    "notebooks/step_0b_select_CMIP_forcing.ipynb",
    "notebooks/step_1a_generate_historical_forcing.ipynb",
    "notebooks/step_1b_generate_future_forcing.ipynb",
    "notebooks/step_2a_calibrate_HBV_SCE.ipynb",
    "notebooks/step_3a_model_run_historical.ipynb",
    "notebooks/step_3b_model_run_future.ipynb",
    "notebooks/step_4_analyse.ipynb"
]

# Output directory for executed notebooks
outdir = Path(f"regions/{country}/{region_id}")
outdir.mkdir(parents=True, exist_ok=True)

done_dir = Path(f"done")
done_dir.mkdir(parents=True, exist_ok=True)

# Directory where the settings file will appear
settings_dir = outdir
settings_path = settings_dir / "settings.json"

#################################################
# STEP 0 — Check if region is already done before
#################################################

def is_region_done(region_id, csv_file):
    """Check if region is already recorded in CSV."""
    if not os.path.exists(csv_file):
        return False

    with FileLock(str(csv_file) + ".lock", timeout=60*3):
        with open(csv_file, "r", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if row and row[0] == str(region_id):
                    return True
    return False

def add_region_to_csv(region_id, csv_file):
    lock_file = str(csv_file) + ".lock"

    # Ensure CSV exists
    if not os.path.exists(csv_file):
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["region"])

    # Safely acquire lock (wait indefinitely if needed)
    with FileLock(lock_file, timeout=60*3):
        # Read existing regions
        existing = set()
        with open(csv_file, "r", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row:
                    existing.add(row[0])

        # Write only if region not present
        if str(region_id) not in existing:
            with open(csv_file, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([region_id])
            print(f"Added region {region_id} to CSV.")
        else:
            print(f"Region {region_id} already in CSV.")

csv_dir = done_dir / f"{country}"  # switch up to separate csv files due to bigger number of runs
csv_dir.mkdir(parents=True, exist_ok=True)

csv_file = csv_dir / "regions_done.csv"
lock_file = str(csv_file) + ".lock"

if is_region_done(region_id, csv_file):
    print(f"Region {region_id} in {country} is already done: TERMINATING")

    sys.exit()  # stops notebook execution
    
#######################################
# STEP 1 — RUN NOTEBOOK 1 (creates settings)
#######################################

first_nb = NOTEBOOKS[0]
pm.execute_notebook(
    first_nb,
    outdir / f"{Path(first_nb).stem}_executed.ipynb",
    parameters={
        "country": country,
        "region_id": region_id
    },
)

# Wait until settings.json exists
while not settings_path.exists():
    print(f"Waiting for settings.json for region {region_id}...")
    time.sleep(1)

# Load settings (for passing to notebooks 2–8)
with open(settings_path) as f:
    settings = json.load(f)


#######################################
# STEP 2 — RUN THE OTHER NOTEBOOKS
#######################################

for nb in NOTEBOOKS[1:]:
    name = Path(nb).stem

    if "step_2a_calibrate_HBV_SCE" in name:
        file_parameters_path = HOME_PATH + "/ewatercycleClimateImpact/HBV/output_data" + f"/{country}/{region_id}/{region_id}_params_SCE.csv"
        if os.path.exists(file_parameters_path):
            print(f"Skipping {name} because calibration is already complete")
            continue
            
    pm.execute_notebook(
        nb,
        outdir / f"{name}_executed.ipynb",
        parameters={
            # "country": country,
            # "region_id": region_id,
            "settings_path": str(settings_path)
        },
    )


# Finished successfully — now record region so it isn't run again
add_region_to_csv(region_id, csv_file)

