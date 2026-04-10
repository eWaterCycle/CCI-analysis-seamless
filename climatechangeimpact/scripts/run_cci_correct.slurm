#!/bin/bash
#SBATCH -N 1
#SBATCH -c 2
#SBATCH -t 04:00:00
#SBATCH -p short

conda init
source ~/.bashrc

conda activate ewatercycle_spider


## Clone the environment for this specific job
#conda create --clone ewatercycle_spider --name ewatercycle_job_${REGION_ID} -y
#conda activate ewatercycle_job_${REGION_ID}
#
## Cleanup function to remove the cloned env when job ends (or fails)
#cleanup() {
#    conda deactivate
#    conda env remove --name ewatercycle_job_${REGION_ID} -y
#}
#trap cleanup EXIT

mkdir -p /project/ewater/Data/climate_data
rclone mount --read-only --allow-non-empty dcache:/climate-data/obs6 /project/ewater/Data/climate_data &
mkdir -p /home/ewater-mmelotto/climate_data
rclone mount --read-only --allow-non-empty dcache:/climate-data/obs6 /home/ewater-mmelotto/climate_data &
mkdir -p /project/ewater/Data/caravan_data
rclone mount --read-only --allow-non-empty dcache:/climate-data/caravan /project/ewater/Data/caravan_data &

cd /home/ewater-mmelotto/seamless_spider/climatechangeimpact
python scripts/cci.py $REGION_ID $COUNTRY

