#!/bin/bash

for country in regions/*
do
    country_name=$(basename "$country")

    for region in "$country"/*
    do
        region_name=$(basename "$region")

        sbatch \
            --job-name="$region_name" \
            --error="regions/$country_name/$region_name/$region_name.err" \
            --output="regions/$country_name/$region_name/$region_name.out" \
            --export=REGION_ID="$region_name",COUNTRY="$country_name" \
            scripts/run_cci.slurm

        break 2  # done as testing to see if this works
#       break 1  # done as testing to see if this works
        # sleep 1  # for small workloads use this
    done
done