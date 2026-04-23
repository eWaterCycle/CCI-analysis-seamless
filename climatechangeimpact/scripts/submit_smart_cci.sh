#!/bin/bash
CONCURRENCY=3  # regions running in parallel per country (recommend, start with 3 and then later you can do more)

for country in regions/*
do
    country_name=$(basename "$country")
    jobids=()  # rolling list of recent job IDs for this country

    for region in "$country"/*
    do
        region_name=$(basename "$region")

        # Chain on the job CONCURRENCY positions back, if it exists
        dep_args=()
        if (( ${#jobids[@]} >= CONCURRENCY )); then
            dep_jobid="${jobids[-CONCURRENCY]}"
            dep_args=(--dependency=afterany:"$dep_jobid")
        fi

        jobid=$(sbatch --parsable \
            "${dep_args[@]}" \
            --job-name="$region_name" \
            --error="regions/$country_name/$region_name/$region_name.err" \
            --output="regions/$country_name/$region_name/$region_name.out" \
            --export=REGION_ID="$region_name",COUNTRY="$country_name" \
            scripts/run_cci.slurm)

        jobids+=("$jobid")
    done
done