#!/bin/bash
#SBATCH -N 1
#SBATCH -c 2
#SBATCH -t 00:10:00
#SBATCH -p short

conda init
conda activate ewatercycle_spider

mkdir /project/ewater/Data/climate_data
rclone mount --read-only --allow-non-empty dcache:/climate-data/obs6 /project/ewater/Data/climate_data &

mkdir /home/ewater-mmelotto/climate_data
rclone mount --read-only --allow-non-empty dcache:/climate-data/obs6 /home/ewater-mmelotto/climate_data &

mkdir /project/ewater/Data/caravan_data
rclone mount --read-only --allow-non-empty dcache:/climate-data/caravan /project/ewater/Data/caravan_data &

cd /home/ewater-mmelotto/seamless_spider/climatechangeimpact

python scripts/cci.py $REGION_ID $COUNTRY