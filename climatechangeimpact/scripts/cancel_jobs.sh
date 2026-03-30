#!/usr/bin/env bash

USER_NAME="ewater-mmelotto"

# Get all job IDs for the user and cancel them
job_ids=$(squeue --user "$USER_NAME" --noheader --format="%i")

if [[ -z "$job_ids" ]]; then
    echo "No jobs found for user $USER_NAME"
    exit 0
fi

echo "Cancelling jobs:"
echo "$job_ids"

# Cancel all jobs
scancel $job_ids

echo "Done."