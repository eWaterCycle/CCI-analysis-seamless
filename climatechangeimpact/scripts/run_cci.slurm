#!/bin/bash
#SBATCH -N 1
#SBATCH -c 2
#SBATCH -t 04:00:00
#SBATCH -p short

set -euo pipefail

export PATH=/home/ewater-mmelotto/miniconda3/bin:$PATH
eval "$(conda shell.bash hook)"

conda activate base

ENV_NAME=ewatercycle_job_${SLURM_JOB_ID}

conda env remove -n "$ENV_NAME" -y 2>/dev/null || true
rm -rf /home/ewater-mmelotto/miniforge3/envs/$ENV_NAME

# Clone environment
conda create --clone ewatercycle_spider --name "$ENV_NAME" -y
conda activate "$ENV_NAME"

cleanup() {
    conda deactivate || true
    conda env remove --name "$ENV_NAME" -y || true
}
trap cleanup EXIT

mkdir -p /project/ewater/Data/climate_data
mkdir -p /home/ewater-mmelotto/climate_data
mkdir -p /project/ewater/Data/caravan_data

rclone mount --read-only --allow-non-empty dcache:/climate-data/obs6 /project/ewater/Data/climate_data &
rclone mount --read-only --allow-non-empty dcache:/climate-data/obs6 /home/ewater-mmelotto/climate_data &
rclone mount --read-only --allow-non-empty dcache:/climate-data/caravan /project/ewater/Data/caravan_data &

sleep 10

cd /home/ewater-mmelotto/seamless_spider/climatechangeimpact
python scripts/cci.py "$REGION_ID" "$COUNTRY"